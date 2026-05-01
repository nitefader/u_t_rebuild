from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID

from backend.app.domain import CandidateSide
from backend.app.orders.ledger import OrderLedger
from backend.app.orders.models import (
    InternalOrder,
    InternalOrderIntent,
    InternalOrderStatus,
    OrderManagerError,
    OrderOrigin,
)

from .adapter import BrokerAdapter
from .models import (
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerOrderUpdateEvent,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionDelta,
    BrokerPositionSnapshot,
    BrokerReconciliationIssue,
    BrokerReconciliationIssueType,
    BrokerReconciliationReport,
    BrokerSyncState,
)


_LIVE_TERMINAL_STATUSES = frozenset(
    {
        InternalOrderStatus.FILLED,
        InternalOrderStatus.CANCELED,
        InternalOrderStatus.REJECTED,
        InternalOrderStatus.FAILED,
    }
)

_LOG = logging.getLogger(__name__)


class BrokerSync:
    """Apply broker boundary results to the internal OrderLedger."""

    def __init__(
        self,
        *,
        ledger: OrderLedger,
        adapter: BrokerAdapter | None = None,
        runtime_store: object | None = None,
        mapping_store: object | None = None,
        provider: str = "broker",
    ) -> None:
        self._ledger = ledger
        self._adapter = adapter
        self._runtime_store = runtime_store
        self._mapping_store = mapping_store
        self._provider = provider

    def apply_result(self, result: BrokerOrderResult) -> InternalOrder:
        order = self._ledger.get(result.order_id)
        if order.client_order_id != result.client_order_id:
            raise OrderManagerError("broker result client_order_id does not match internal order")
        status = self._map_status(result.status)
        filled_quantity = result.filled_quantity
        if result.status == BrokerOrderStatus.FILLED:
            filled_quantity = order.quantity
        if filled_quantity > order.quantity:
            raise OrderManagerError("broker result filled_quantity exceeds internal order quantity")
        previous_status = order.status
        updated = order.model_copy(
            update={
                "status": status,
                "filled_quantity": filled_quantity,
                "canceled_at": result.canceled_at or (result.received_at if status == InternalOrderStatus.CANCELED else order.canceled_at),
                "updated_at": result.received_at,
                "reason": result.reason if result.reason is not None else order.reason,
            }
        )
        persisted = self._ledger.replace(updated)
        self._persist_mapping(result=result, order=persisted)
        # P0-3 safety net: when an internal-OCO leg fills, cancel its sibling.
        # Until the AlpacaBrokerAdapter learns native OCO submission, the
        # post-fill bracket pair is two unlinked broker orders — without this
        # cancel a target fill leaves the stop live, and the next stop trigger
        # would invert the position (long → flat → silently short).
        if (
            status == InternalOrderStatus.FILLED
            and previous_status != InternalOrderStatus.FILLED
            and persisted.order_class == "oco"
            and persisted.parent_order_id is not None
        ):
            self._cancel_oco_siblings(persisted, received_at=result.received_at)
        return persisted

    def _cancel_oco_siblings(
        self,
        filled_leg: InternalOrder,
        *,
        received_at: datetime,
    ) -> None:
        """Cancel any live OCO siblings of *filled_leg*.

        Siblings share the same ``parent_order_id`` and the same slice suffix
        (``leg_label`` after the ``@`` separator), differ by ``order_id``, and
        are not yet terminal. When the broker adapter is unavailable (test
        path), the sibling is left untouched and the local ledger is not
        speculatively mutated — BrokerSync remains the only writer of broker
        truth.
        """
        if self._adapter is None:
            return
        slice_key = self._slice_suffix_of(filled_leg.leg_label)
        for candidate in self._ledger.by_account(filled_leg.account_id):
            if candidate.order_id == filled_leg.order_id:
                continue
            if candidate.parent_order_id != filled_leg.parent_order_id:
                continue
            if candidate.order_class != "oco":
                continue
            if candidate.status in _LIVE_TERMINAL_STATUSES:
                continue
            if candidate.cancel_requested_at is not None:
                continue
            if self._slice_suffix_of(candidate.leg_label) != slice_key:
                continue
            try:
                cancel_result = self._adapter.cancel_order(candidate)
            except Exception:
                # Cancel best-effort; broker reconciliation will surface a
                # stuck sibling on the next sync pass.
                continue
            self.apply_result(cancel_result)

    @staticmethod
    def _slice_suffix_of(leg_label: str | None) -> str | None:
        if leg_label is None:
            return None
        idx = leg_label.find("@")
        return leg_label[idx:] if idx >= 0 else None

    def sync_open_orders(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        adapter = self._require_adapter()
        local_by_client_order_id = {order.client_order_id: order for order in self._ledger.by_account(account_id)}
        updates: list[InternalOrder] = []
        for snapshot in adapter.list_open_orders(account_id):
            self.record_external_open_order(snapshot)
            order = local_by_client_order_id.get(snapshot.client_order_id)
            if order is None:
                continue
            result = adapter.get_order(order)
            updates.append(self.apply_result(result))
        return tuple(updates)

    def sync_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        positions = _enrich_position_snapshots_with_lineage(
            account_id,
            self._require_adapter().get_positions(account_id),
            self._ledger,
        )
        for position in positions:
            self.record_position_snapshot(position)
        return positions

    def sync_account(self, account_id: UUID) -> BrokerAccountSnapshot:
        snapshot = self._require_adapter().get_account_snapshot(account_id)
        self._persist_account_snapshot(snapshot)
        return snapshot

    def reconcile(
        self,
        account_id: UUID,
        *,
        expected_positions_by_symbol: dict[str, float] | None = None,
        max_sync_age_seconds: int = 60,
    ) -> BrokerReconciliationReport:
        return BrokerSyncService(
            adapter=self._require_adapter(),
            broker_sync=self,
            order_ledger=self._ledger,
            max_stale_seconds=max_sync_age_seconds,
        ).reconcile(
            account_id,
            expected_positions_by_symbol=expected_positions_by_symbol,
        )

    def _map_status(self, status: BrokerOrderStatus) -> InternalOrderStatus:
        if status == BrokerOrderStatus.ACCEPTED:
            return InternalOrderStatus.ACCEPTED
        if status == BrokerOrderStatus.REJECTED:
            return InternalOrderStatus.REJECTED
        if status == BrokerOrderStatus.PARTIAL_FILL:
            return InternalOrderStatus.PARTIALLY_FILLED
        if status == BrokerOrderStatus.FILLED:
            return InternalOrderStatus.FILLED
        if status == BrokerOrderStatus.CANCELED:
            return InternalOrderStatus.CANCELED
        if status in {
            BrokerOrderStatus.EXPIRED,
            BrokerOrderStatus.PENDING_CANCEL,
            BrokerOrderStatus.REPLACED,
            BrokerOrderStatus.SUSPENDED,
            BrokerOrderStatus.DONE_FOR_DAY,
        }:
            return InternalOrderStatus.SUBMITTED
        raise OrderManagerError(f"unsupported broker status: {status}")

    def _require_adapter(self) -> BrokerAdapter:
        if self._adapter is None:
            raise OrderManagerError("broker sync read operation requires a broker adapter")
        return self._adapter

    def _persist_mapping(self, *, result: BrokerOrderResult, order: InternalOrder) -> None:
        if result.broker_order_id is None:
            return
        target = self._mapping_store or self._runtime_store
        if target is None:
            return
        created_at = result.received_at
        try:
            if hasattr(target, "lookup_broker_mapping_by_internal_order_id"):
                created_at = target.lookup_broker_mapping_by_internal_order_id(order.order_id).created_at
            elif hasattr(target, "get_by_order_id"):
                created_at = target.get_by_order_id(order.order_id).created_at
        except KeyError:
            pass
        mapping = BrokerOrderMapping(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id=result.broker_order_id,
            provider=self._provider,
            account_id=order.account_id,
            created_at=created_at,
            last_synced_at=result.received_at,
        )
        if hasattr(target, "save_broker_order_mapping"):
            target.save_broker_order_mapping(mapping)
            return
        if hasattr(target, "save"):
            target.save(mapping)

    def _persist_account_snapshot(self, snapshot: BrokerAccountSnapshot) -> None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "save_broker_account_snapshot"):
            return
        self._runtime_store.save_broker_account_snapshot(snapshot)

    def record_external_open_order(self, snapshot: BrokerOpenOrderSnapshot) -> BrokerOpenOrderSnapshot:
        if self._runtime_store is not None and hasattr(self._runtime_store, "save_broker_open_order_snapshot"):
            self._runtime_store.save_broker_open_order_snapshot(snapshot)
        return snapshot

    def record_position_snapshot(self, snapshot: BrokerPositionSnapshot) -> BrokerPositionSnapshot:
        snapshot = _enrich_position_snapshot_with_lineage(
            snapshot,
            self._ledger.by_account(snapshot.account_id),
        )
        if self._runtime_store is not None and hasattr(self._runtime_store, "save_broker_position_snapshot"):
            self._runtime_store.save_broker_position_snapshot(snapshot)
        return snapshot

    def record_sync_freshness(
        self,
        account_snapshot: BrokerAccountSnapshot,
        *,
        max_stale_seconds: int = 30,
    ) -> BrokerSyncState:
        state = _snapshot_freshness_state(account_snapshot, max_stale_seconds=max_stale_seconds)
        _persist_sync_freshness(self._runtime_store, state)
        return state

    def mark_missing_broker_order(self, order: InternalOrder, *, reason: str = "recovery_missing_broker_order") -> InternalOrder:
        if order.status in {
            InternalOrderStatus.FILLED,
            InternalOrderStatus.CANCELED,
            InternalOrderStatus.REJECTED,
            InternalOrderStatus.FAILED,
        } and order.reason == reason:
            return order
        updated = order.model_copy(
            update={
                "status": InternalOrderStatus.CANCELED,
                "updated_at": datetime.now(timezone.utc),
                "reason": reason,
            }
        )
        return self._ledger.replace(updated)

    def _flag_stale_sync(
        self,
        *,
        account_snapshot: BrokerAccountSnapshot,
        max_sync_age_seconds: int,
        issues: list[BrokerReconciliationIssue],
    ) -> None:
        now = datetime.now(timezone.utc)
        last_synced_at = account_snapshot.last_synced_at
        if last_synced_at.tzinfo is None:
            last_synced_at = last_synced_at.replace(tzinfo=timezone.utc)
        age_seconds = (now - last_synced_at).total_seconds()
        if age_seconds <= max_sync_age_seconds:
            return
        issues.append(
            BrokerReconciliationIssue(
                issue_type=BrokerReconciliationIssueType.STALE_SYNC,
                account_id=account_snapshot.account_id,
                message="broker account snapshot is stale",
                expected=f"<= {max_sync_age_seconds}s",
                actual=f"{int(age_seconds)}s",
            )
        )

    def _flag_position_mismatches(
        self,
        *,
        account_id: UUID,
        positions: tuple[BrokerPositionSnapshot, ...],
        expected_positions_by_symbol: dict[str, float],
        issues: list[BrokerReconciliationIssue],
    ) -> None:
        if not expected_positions_by_symbol:
            return
        broker_qty_by_symbol = {position.symbol.upper(): position.qty for position in positions}
        symbols = set(broker_qty_by_symbol) | {symbol.upper() for symbol in expected_positions_by_symbol}
        for symbol in sorted(symbols):
            expected = float(expected_positions_by_symbol.get(symbol, 0))
            actual = float(broker_qty_by_symbol.get(symbol, 0))
            if expected == actual:
                continue
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=BrokerReconciliationIssueType.POSITION_MISMATCH,
                    account_id=account_id,
                    symbol=symbol,
                    message="broker position quantity does not match expected internal position quantity",
                    expected=expected,
                    actual=actual,
                )
            )


class BrokerSyncService:
    """Read broker truth and reconcile it through BrokerSync only."""

    def __init__(
        self,
        *,
        adapter: BrokerAdapter,
        broker_sync: BrokerSync,
        order_ledger: OrderLedger,
        trade_ledger: object | None = None,
        max_stale_seconds: int = 30,
        runtime_store: object | None = None,
        daily_state_aggregator: object | None = None,
        daily_states: "dict[UUID, object] | None" = None,
    ) -> None:
        self._adapter = adapter
        self._broker_sync = broker_sync
        self._order_ledger = order_ledger
        self._trade_ledger = trade_ledger
        self._max_stale_seconds = max_stale_seconds
        self._runtime_store = runtime_store
        self._daily_state_aggregator = daily_state_aggregator
        self._daily_states: dict[UUID, object] = daily_states if daily_states is not None else {}
        self._daily_state_locks_guard = threading.Lock()
        self._daily_state_locks: dict[UUID, threading.Lock] = {}
        self._last_event_at_by_account: dict[UUID, datetime] = {}
        self._last_poll_sync_at_by_account: dict[UUID, datetime] = {}
        self._last_successful_sync_at_by_account: dict[UUID, datetime] = {}
        self._stale_reason_by_account: dict[UUID, str] = {}
        self._account_snapshots_by_account: dict[UUID, BrokerAccountSnapshot] = {}
        self._positions_by_account: dict[UUID, dict[str, BrokerPositionSnapshot]] = {}
        self._fills: list[BrokerFillUpdateEvent] = []

    def sync_state(self, account_snapshot: BrokerAccountSnapshot) -> BrokerSyncState:
        checked_at = datetime.now(timezone.utc)
        snapshot_timestamp = _aware(account_snapshot.timestamp)
        account_id = account_snapshot.account_id
        last_event_at = self._last_event_at_by_account.get(account_id)
        last_poll_sync_at = self._last_poll_sync_at_by_account.get(account_id)
        last_successful_sync_at = self._last_successful_sync_at_by_account.get(account_id, snapshot_timestamp)
        latest_truth_at = max(
            (timestamp for timestamp in (last_event_at, last_poll_sync_at, snapshot_timestamp) if timestamp is not None),
            default=snapshot_timestamp,
        )
        age = checked_at - _aware(latest_truth_at)
        is_stale = age > timedelta(seconds=self._max_stale_seconds)
        stale_reason = None
        if is_stale:
            if self._stale_reason_by_account.get(account_id):
                stale_reason = self._stale_reason_by_account[account_id]
            elif latest_truth_at == snapshot_timestamp:
                stale_reason = f"broker_snapshot_age_exceeded_{self._max_stale_seconds}s"
            else:
                stale_reason = f"broker_truth_age_exceeded_{self._max_stale_seconds}s"
        state = BrokerSyncState(
            account_id=account_id,
            last_sync_at=checked_at,
            last_event_at=last_event_at,
            last_poll_sync_at=last_poll_sync_at,
            last_successful_sync_at=last_successful_sync_at,
            is_stale=is_stale,
            stale_reason=stale_reason,
        )
        self._persist_sync_state(state)
        return state

    def current_sync_state(self, account_id: UUID) -> BrokerSyncState:
        checked_at = datetime.now(timezone.utc)
        last_event_at = self._last_event_at_by_account.get(account_id)
        last_poll_sync_at = self._last_poll_sync_at_by_account.get(account_id)
        last_successful_sync_at = self._last_successful_sync_at_by_account.get(account_id)
        latest_truth_at = max(
            (timestamp for timestamp in (last_event_at, last_poll_sync_at) if timestamp is not None),
            default=None,
        )
        if latest_truth_at is None:
            state = BrokerSyncState(
                account_id=account_id,
                last_sync_at=checked_at,
                last_event_at=last_event_at,
                last_poll_sync_at=last_poll_sync_at,
                last_successful_sync_at=last_successful_sync_at,
                is_stale=True,
                stale_reason=self._stale_reason_by_account.get(account_id) or "broker_truth_never_synced",
            )
            self._persist_sync_state(state)
            return state
        age = checked_at - _aware(latest_truth_at)
        is_stale = age > timedelta(seconds=self._max_stale_seconds)
        stale_reason = None
        if is_stale:
            stale_reason = self._stale_reason_by_account.get(account_id) or f"broker_truth_age_exceeded_{self._max_stale_seconds}s"
        state = BrokerSyncState(
            account_id=account_id,
            last_sync_at=checked_at,
            last_event_at=last_event_at,
            last_poll_sync_at=last_poll_sync_at,
            last_successful_sync_at=last_successful_sync_at,
            is_stale=is_stale,
            stale_reason=stale_reason,
        )
        self._persist_sync_state(state)
        return state

    def record_successful_poll(self, account_id: UUID, *, at: datetime | None = None) -> BrokerSyncState:
        """Mark that a synchronous broker round-trip just succeeded.

        Synchronous submit/cancel paths call ``BrokerSync.apply_result``
        directly (not through ``handle_order_update``) so the service
        does not see a stream event. This method keeps the service's
        view of ``last_poll_sync_at`` fresh after such round-trips so
        downstream consumers (the OrderManager stale-sync gate, the
        governor's freshness signal) treat the account as up to date.
        """
        timestamp = _aware(at) if at is not None else datetime.now(timezone.utc)
        self._last_poll_sync_at_by_account[account_id] = timestamp
        self._last_successful_sync_at_by_account[account_id] = timestamp
        self._stale_reason_by_account.pop(account_id, None)
        return self.current_sync_state(account_id)

    def fetch_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return self._adapter.get_account_snapshot(account_id)

    def fetch_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return self._adapter.get_positions(account_id)

    def fetch_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        return self._adapter.list_open_orders(account_id)

    def latest_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot | None:
        return self._account_snapshots_by_account.get(account_id)

    def latest_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return tuple(self._positions_by_account.get(account_id, {}).values())

    def fills(self) -> tuple[BrokerFillUpdateEvent, ...]:
        return tuple(self._fills)

    def handle_order_update(self, event: BrokerOrderUpdateEvent) -> InternalOrder | None:
        try:
            order = self._order_by_client_order_id(event.account_id, event.client_order_id)
        except OrderManagerError:
            self._record_external_order_update(event)
            self._record_stream_event(event.account_id, event.event_at)
            return None
        result = BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=event.client_order_id,
            status=event.status,
            broker_order_id=event.broker_order_id,
            broker_status=event.broker_status,
            filled_quantity=event.filled_quantity,
            filled_avg_price=event.filled_avg_price,
            remaining_quantity=event.remaining_quantity,
            reason=event.reason,
            received_at=event.event_at,
            submitted_at=event.submitted_at,
            updated_at=event.updated_at,
            filled_at=event.filled_at,
            canceled_at=event.canceled_at,
            reject_code=event.reject_code,
            raw_status=event.raw_status,
            broker_reference=event.broker_reference,
        )
        updated = self._broker_sync.apply_result(result)
        self._record_stream_event(event.account_id, event.event_at)
        return updated

    def handle_fill_update(self, event: BrokerFillUpdateEvent) -> BrokerFillUpdateEvent:
        self._fills.append(event)
        if self._trade_ledger is not None:
            if hasattr(self._trade_ledger, "record_fill"):
                self._trade_ledger.record_fill(event)
            elif hasattr(self._trade_ledger, "add"):
                self._trade_ledger.add(event)
        self._record_stream_event(event.account_id, event.event_at)
        self._apply_daily_state_fill(event)
        return event

    def _apply_daily_state_fill(self, event: BrokerFillUpdateEvent) -> None:
        if self._daily_state_aggregator is None:
            return
        with self._daily_state_lock_for(event.account_id):
            current = self._daily_states.get(event.account_id)
            snapshot = self._account_snapshots_by_account.get(event.account_id)
            equity: float | None = float(snapshot.equity) if snapshot is not None and snapshot.equity > 0 else None
            try:
                updated = self._daily_state_aggregator.apply_fill(current, event, equity=equity)
            except Exception:
                return
            self._daily_states[event.account_id] = updated
            if self._runtime_store is not None and hasattr(self._runtime_store, "save_daily_account_state"):
                try:
                    self._runtime_store.save_daily_account_state(updated)
                except Exception:
                    _LOG.warning(
                        "BrokerSyncService: failed to persist daily account state for account %s market_day %s",
                        event.account_id,
                        updated.market_day,
                        exc_info=True,
                        extra={
                            "event": "broker_sync_daily_state_persist_failed",
                            "account_id": str(event.account_id),
                            "market_day": updated.market_day,
                        },
                    )

    def _daily_state_lock_for(self, account_id: UUID) -> threading.Lock:
        with self._daily_state_locks_guard:
            lock = self._daily_state_locks.get(account_id)
            if lock is None:
                lock = threading.Lock()
                self._daily_state_locks[account_id] = lock
            return lock

    def daily_state_for(self, account_id: UUID) -> object | None:
        return self._daily_states.get(account_id)

    def handle_position_update(self, event: BrokerPositionSnapshot) -> BrokerPositionSnapshot:
        event = _enrich_position_snapshot_with_lineage(
            event,
            self._order_ledger.by_account(event.account_id),
        )
        positions = self._positions_by_account.setdefault(event.account_id, {})
        positions[event.symbol.upper()] = event
        self._persist_position_snapshot(event)
        self._record_stream_event(event.account_id, event.timestamp)
        return event

    def handle_account_update(self, event: BrokerAccountSnapshot) -> BrokerAccountSnapshot:
        self._account_snapshots_by_account[event.account_id] = event
        self._persist_account_snapshot(event)
        self._record_stream_event(event.account_id, event.timestamp)
        return event

    def handle_stream_disconnect(self, account_id: UUID) -> BrokerReconciliationReport | None:
        try:
            return self.reconcile(account_id)
        except Exception:
            self._stale_reason_by_account[account_id] = "stream_disconnect_poll_failed"
            return None

    def reconcile(
        self,
        account_id: UUID,
        *,
        expected_positions_by_symbol: dict[str, float] | None = None,
    ) -> BrokerReconciliationReport:
        checked_at = datetime.now(timezone.utc)
        account_snapshot = self.fetch_account_snapshot(account_id)
        positions = self.fetch_positions(account_id)
        open_orders = self.fetch_open_orders(account_id)
        self._account_snapshots_by_account[account_id] = account_snapshot
        self._persist_account_snapshot(account_snapshot)
        self._persist_open_order_snapshots(account_id, open_orders)
        sync_status = self.sync_state(account_snapshot)
        self._last_poll_sync_at_by_account[account_id] = checked_at
        if not sync_status.is_stale:
            self._last_successful_sync_at_by_account[account_id] = checked_at
            self._stale_reason_by_account.pop(account_id, None)
        issues: list[BrokerReconciliationIssue] = []
        matched_orders: list[str] = []
        unmatched_internal_orders: list[str] = []
        unmatched_broker_orders: list[BrokerOpenOrderSnapshot] = []
        updated_order_count = 0

        if sync_status.is_stale:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=BrokerReconciliationIssueType.STALE_SYNC,
                    account_id=account_id,
                    message="broker account snapshot is stale",
                    expected=f"<= {self._max_stale_seconds}s",
                    actual=sync_status.stale_reason,
                )
            )

        local_orders = self._order_ledger.by_account(account_id)
        active_local_orders = tuple(order for order in local_orders if _requires_broker_order_reconcile(order))
        local_by_client_order_id = {order.client_order_id: order for order in local_orders}
        open_by_client_order_id = {order.client_order_id: order for order in open_orders}

        for order in active_local_orders:
            try:
                broker_result = self._adapter.get_order(order)
            except BrokerAdapterError:
                unmatched_internal_orders.append(order.client_order_id)
                issues.append(
                    BrokerReconciliationIssue(
                        issue_type=BrokerReconciliationIssueType.MISSING_BROKER_ORDER,
                        account_id=account_id,
                        symbol=order.symbol,
                        order_id=order.order_id,
                        client_order_id=order.client_order_id,
                        message="local internal order was not found at broker",
                    )
                )
                continue

            matched_orders.append(order.client_order_id)
            if broker_result.filled_quantity != order.filled_quantity:
                issues.append(
                    BrokerReconciliationIssue(
                        issue_type=BrokerReconciliationIssueType.MISMATCHED_FILL,
                        account_id=account_id,
                        symbol=order.symbol,
                        order_id=order.order_id,
                        client_order_id=order.client_order_id,
                        broker_order_id=broker_result.broker_order_id,
                        message="broker filled quantity differs from internal order filled quantity",
                        expected=order.filled_quantity,
                        actual=broker_result.filled_quantity,
                    )
                )
            self._broker_sync.apply_result(broker_result)
            updated_order_count += 1

        for broker_order in open_orders:
            if broker_order.client_order_id in local_by_client_order_id:
                continue
            unmatched_broker_orders.append(broker_order)
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=BrokerReconciliationIssueType.MISSING_LOCAL_ORDER,
                    account_id=account_id,
                    client_order_id=broker_order.client_order_id,
                    broker_order_id=broker_order.broker_order_id,
                    symbol=broker_order.symbol,
                    message="broker order has no matching internal order; intent is unknown and order is preserved",
                    actual="unknown_intent",
                    action="preserve_external_order_and_flag",
                )
            )

        for client_order_id, broker_order in open_by_client_order_id.items():
            local_order = local_by_client_order_id.get(client_order_id)
            if local_order is None or broker_order.filled_qty == local_order.filled_quantity:
                continue
            if not any(
                issue.issue_type == BrokerReconciliationIssueType.MISMATCHED_FILL
                and issue.client_order_id == client_order_id
                for issue in issues
            ):
                issues.append(
                    BrokerReconciliationIssue(
                        issue_type=BrokerReconciliationIssueType.MISMATCHED_FILL,
                        account_id=account_id,
                        symbol=broker_order.symbol,
                        order_id=local_order.order_id,
                        client_order_id=client_order_id,
                        broker_order_id=broker_order.broker_order_id,
                        message="broker open order filled quantity differs from internal order filled quantity",
                        expected=local_order.filled_quantity,
                        actual=broker_order.filled_qty,
                    )
                )

        positions = _enrich_position_snapshots_with_lineage(account_id, positions, self._order_ledger)
        self._persist_position_snapshots(account_id, positions)
        self._positions_by_account[account_id] = {position.symbol.upper(): position for position in positions}

        position_deltas = self._position_deltas(
            positions=positions,
            expected_positions_by_symbol=expected_positions_by_symbol or {},
        )
        for delta in position_deltas:
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=BrokerReconciliationIssueType.POSITION_MISMATCH,
                    account_id=account_id,
                    symbol=delta.symbol,
                    message="broker position quantity does not match expected internal position quantity",
                    expected=delta.expected_qty,
                    actual=delta.broker_qty,
                )
            )

        return BrokerReconciliationReport(
            account_id=account_id,
            updated_order_count=updated_order_count,
            broker_position_count=len(positions),
            issues=tuple(issues),
            matched_orders=tuple(matched_orders),
            unmatched_broker_orders=tuple(unmatched_broker_orders),
            unmatched_internal_orders=tuple(unmatched_internal_orders),
            position_deltas=tuple(position_deltas),
            sync_status=sync_status,
        )

    def _record_stream_event(self, account_id: UUID, event_at: datetime) -> None:
        aware_event_at = _aware(event_at)
        self._last_event_at_by_account[account_id] = aware_event_at
        self._last_successful_sync_at_by_account[account_id] = aware_event_at
        self._stale_reason_by_account.pop(account_id, None)
        self.current_sync_state(account_id)

    def _persist_account_snapshot(self, snapshot: BrokerAccountSnapshot) -> None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "save_broker_account_snapshot"):
            return
        self._runtime_store.save_broker_account_snapshot(snapshot)

    def _persist_position_snapshots(
        self,
        account_id: UUID,
        snapshots: tuple[BrokerPositionSnapshot, ...],
    ) -> None:
        if self._runtime_store is None:
            return
        if hasattr(self._runtime_store, "replace_broker_position_snapshots"):
            self._runtime_store.replace_broker_position_snapshots(account_id, snapshots)
            return
        if hasattr(self._runtime_store, "save_broker_position_snapshot"):
            for snapshot in snapshots:
                self._runtime_store.save_broker_position_snapshot(snapshot)

    def _persist_position_snapshot(self, snapshot: BrokerPositionSnapshot) -> None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "save_broker_position_snapshot"):
            return
        self._runtime_store.save_broker_position_snapshot(snapshot)

    def _persist_open_order_snapshots(
        self,
        account_id: UUID,
        snapshots: tuple[BrokerOpenOrderSnapshot, ...],
    ) -> None:
        if self._runtime_store is None:
            return
        if hasattr(self._runtime_store, "replace_broker_open_order_snapshots"):
            self._runtime_store.replace_broker_open_order_snapshots(account_id, snapshots)
            return
        if hasattr(self._runtime_store, "save_broker_open_order_snapshot"):
            for snapshot in snapshots:
                self._runtime_store.save_broker_open_order_snapshot(snapshot)

    def _persist_sync_state(self, state: BrokerSyncState) -> None:
        _persist_sync_freshness(self._runtime_store, state)

    def _order_by_client_order_id(self, account_id: UUID, client_order_id: str) -> InternalOrder:
        for order in self._order_ledger.by_account(account_id):
            if order.client_order_id == client_order_id:
                return order
        raise OrderManagerError(f"unknown internal order client_order_id: {client_order_id}")

    def _position_deltas(
        self,
        *,
        positions: tuple[BrokerPositionSnapshot, ...],
        expected_positions_by_symbol: dict[str, float],
    ) -> tuple[BrokerPositionDelta, ...]:
        if not expected_positions_by_symbol:
            return ()
        broker_qty_by_symbol = {position.symbol.upper(): position.qty for position in positions}
        symbols = set(broker_qty_by_symbol) | {symbol.upper() for symbol in expected_positions_by_symbol}
        deltas: list[BrokerPositionDelta] = []
        for symbol in sorted(symbols):
            expected = float(expected_positions_by_symbol.get(symbol, 0))
            actual = float(broker_qty_by_symbol.get(symbol, 0))
            if expected == actual:
                continue
            deltas.append(
                BrokerPositionDelta(
                    symbol=symbol,
                    expected_qty=expected,
                    broker_qty=actual,
                    delta_qty=actual - expected,
                )
            )
        return tuple(deltas)

    def _record_external_order_update(self, event: BrokerOrderUpdateEvent) -> None:
        if _broker_order_update_terminal(event.status):
            return
        if event.broker_order_id is None or event.symbol is None or event.side is None or event.qty is None:
            return
        self._broker_sync.record_external_open_order(
            BrokerOpenOrderSnapshot(
                account_id=event.account_id,
                broker_order_id=event.broker_order_id,
                client_order_id=event.client_order_id,
                symbol=event.symbol,
                side=event.side,
                qty=event.qty,
                filled_qty=event.filled_quantity,
                status=event.status,
                order_type=event.order_type or "unknown",
                limit_price=event.limit_price,
                stop_price=event.stop_price,
                timestamp=event.event_at,
            )
        )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _snapshot_freshness_state(
    account_snapshot: BrokerAccountSnapshot,
    *,
    max_stale_seconds: int,
) -> BrokerSyncState:
    """Compute a ``BrokerSyncState`` for a one-shot snapshot freshness check.

    Used by ``BrokerSync.record_sync_freshness`` for paths that do not own a
    ``BrokerSyncService`` (initial broker validation, recovery orchestrator).
    The reason format matches what ``BrokerSyncService.sync_state`` produces
    when the snapshot is the latest truth, so downstream consumers see a
    single ``broker_snapshot_age_exceeded_<n>s`` taxonomy.
    """
    snapshot_timestamp = _aware(account_snapshot.timestamp)
    age = datetime.now(timezone.utc) - snapshot_timestamp
    is_stale = age > timedelta(seconds=max_stale_seconds)
    return BrokerSyncState(
        account_id=account_snapshot.account_id,
        last_sync_at=snapshot_timestamp,
        last_poll_sync_at=snapshot_timestamp,
        last_successful_sync_at=None if is_stale else snapshot_timestamp,
        is_stale=is_stale,
        stale_reason=f"broker_snapshot_age_exceeded_{max_stale_seconds}s" if is_stale else None,
    )


def _persist_sync_freshness(runtime_store: object | None, state: BrokerSyncState) -> None:
    if runtime_store is None or not hasattr(runtime_store, "save_broker_sync_freshness"):
        return
    runtime_store.save_broker_sync_freshness(state)


def _enrich_position_snapshots_with_lineage(
    account_id: UUID,
    snapshots: tuple[BrokerPositionSnapshot, ...],
    order_ledger: OrderLedger,
) -> tuple[BrokerPositionSnapshot, ...]:
    orders = order_ledger.by_account(account_id)
    return tuple(_enrich_position_snapshot_with_lineage(snapshot, orders) for snapshot in snapshots)


def _enrich_position_snapshot_with_lineage(
    snapshot: BrokerPositionSnapshot,
    orders: tuple[InternalOrder, ...],
) -> BrokerPositionSnapshot:
    if snapshot.qty == 0:
        return snapshot
    if (
        snapshot.deployment_id is not None
        and snapshot.opening_signal_plan_id is not None
        and snapshot.position_lineage_id is not None
    ):
        return snapshot

    symbol = snapshot.symbol.upper()
    matching_orders = tuple(
        order
        for order in orders
        if order.origin == OrderOrigin.SIGNAL_PLAN
        and order.account_id == snapshot.account_id
        and order.symbol.upper() == symbol
        and order.deployment_id is not None
        and order.position_lineage_id is not None
        and order.filled_quantity > 0
    )
    if not matching_orders:
        return snapshot

    net_by_lineage: dict[tuple[UUID, UUID], float] = {}
    for order in matching_orders:
        assert order.deployment_id is not None
        assert order.position_lineage_id is not None
        key = (order.deployment_id, order.position_lineage_id)
        net_by_lineage[key] = net_by_lineage.get(key, 0.0) + _signed_order_quantity(order)

    candidates = tuple(
        key
        for key, net_qty in net_by_lineage.items()
        if _same_quantity(net_qty, snapshot.qty)
        and (snapshot.deployment_id is None or key[0] == snapshot.deployment_id)
        and (snapshot.position_lineage_id is None or key[1] == snapshot.position_lineage_id)
    )
    if len(candidates) != 1:
        deployment_enriched = _deployment_only_position_snapshot(snapshot, matching_orders)
        if deployment_enriched is not None:
            return deployment_enriched
        return snapshot

    deployment_id, position_lineage_id = candidates[0]
    anchor = _lineage_anchor_order(
        snapshot,
        matching_orders,
        deployment_id=deployment_id,
        position_lineage_id=position_lineage_id,
    )
    if anchor is None:
        return snapshot

    return snapshot.model_copy(
        update={
            "deployment_id": snapshot.deployment_id or deployment_id,
            "strategy_id": snapshot.strategy_id or anchor.strategy_id,
            "opening_signal_plan_id": snapshot.opening_signal_plan_id
            or anchor.opening_signal_plan_id
            or anchor.signal_plan_id,
            "position_lineage_id": snapshot.position_lineage_id or position_lineage_id,
        }
    )


def _deployment_only_position_snapshot(
    snapshot: BrokerPositionSnapshot,
    orders: tuple[InternalOrder, ...],
) -> BrokerPositionSnapshot | None:
    if snapshot.deployment_id is not None:
        return None
    net_by_deployment: dict[UUID, float] = {}
    for order in orders:
        if order.deployment_id is None:
            continue
        net_by_deployment[order.deployment_id] = net_by_deployment.get(order.deployment_id, 0.0) + _signed_order_quantity(order)
    candidates = tuple(
        deployment_id
        for deployment_id, net_qty in net_by_deployment.items()
        if _same_quantity(net_qty, snapshot.qty)
    )
    if len(candidates) != 1:
        return None
    deployment_id = candidates[0]
    deployment_orders = tuple(order for order in orders if order.deployment_id == deployment_id)
    if not deployment_orders:
        return None
    anchor = min(deployment_orders, key=lambda order: (order.created_at, order.order_id.hex))
    return snapshot.model_copy(
        update={
            "deployment_id": deployment_id,
            "strategy_id": snapshot.strategy_id or anchor.strategy_id,
        }
    )


def _lineage_anchor_order(
    snapshot: BrokerPositionSnapshot,
    orders: tuple[InternalOrder, ...],
    *,
    deployment_id: UUID,
    position_lineage_id: UUID,
) -> InternalOrder | None:
    lineage_orders = tuple(
        order
        for order in orders
        if order.deployment_id == deployment_id
        and order.position_lineage_id == position_lineage_id
        and order.filled_quantity > 0
    )
    opening_orders = tuple(
        order
        for order in lineage_orders
        if order.intent == InternalOrderIntent.OPEN
        and order.parent_order_id is None
        and _order_side_matches_position(order, snapshot)
    )
    candidates = opening_orders or lineage_orders
    if not candidates:
        return None
    return min(candidates, key=lambda order: (order.created_at, order.order_id.hex))


def _signed_order_quantity(order: InternalOrder) -> float:
    sign = 1.0 if order.side == CandidateSide.LONG else -1.0
    return sign * float(order.filled_quantity)


def _order_side_matches_position(order: InternalOrder, snapshot: BrokerPositionSnapshot) -> bool:
    if snapshot.qty > 0:
        return order.side == CandidateSide.LONG
    if snapshot.qty < 0:
        return order.side == CandidateSide.SHORT
    return False


def _same_quantity(left: float, right: float) -> bool:
    return abs(float(left) - float(right)) <= 1e-6


def _requires_broker_order_reconcile(order: InternalOrder) -> bool:
    """Return whether quiet polling should refresh this internal order.

    Stream events and prior BrokerSync reconciliation own terminal broker truth.
    The recurring REST poll only needs to chase orders that can still change at
    the broker, otherwise a long-lived account pays one get_order call forever
    for every historical fill/cancel/reject.
    """
    return order.status not in {
        InternalOrderStatus.FILLED,
        InternalOrderStatus.CANCELED,
        InternalOrderStatus.REJECTED,
        InternalOrderStatus.FAILED,
    }


def _broker_order_update_terminal(status: BrokerOrderStatus) -> bool:
    return status in {
        BrokerOrderStatus.FILLED,
        BrokerOrderStatus.CANCELED,
        BrokerOrderStatus.REJECTED,
        BrokerOrderStatus.EXPIRED,
        BrokerOrderStatus.REPLACED,
    }
