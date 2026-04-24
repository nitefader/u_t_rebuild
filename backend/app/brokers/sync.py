from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from backend.app.orders import InternalOrder, InternalOrderStatus, OrderLedger, OrderManagerError

from .adapter import BrokerAdapter
from .models import (
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSnapshot,
    BrokerReconciliationIssue,
    BrokerReconciliationIssueType,
    BrokerReconciliationReport,
)


class BrokerSync:
    """Apply broker boundary results to the internal OrderLedger."""

    def __init__(self, *, ledger: OrderLedger, adapter: BrokerAdapter | None = None) -> None:
        self._ledger = ledger
        self._adapter = adapter

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
        updated = order.model_copy(
            update={
                "status": status,
                "filled_quantity": filled_quantity,
                "updated_at": result.received_at,
                "reason": result.reason if result.reason is not None else order.reason,
            }
        )
        return self._ledger.replace(updated)

    def sync_open_orders(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        adapter = self._require_adapter()
        updates: list[InternalOrder] = []
        for result in adapter.list_open_orders(account_id):
            updates.append(self.apply_result(result))
        return tuple(updates)

    def sync_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return self._require_adapter().get_positions(account_id)

    def sync_account(self, account_id: UUID) -> BrokerAccountSnapshot:
        return self._require_adapter().get_account_snapshot(account_id)

    def reconcile(
        self,
        account_id: UUID,
        *,
        expected_positions_by_symbol: dict[str, float] | None = None,
        max_sync_age_seconds: int = 60,
    ) -> BrokerReconciliationReport:
        adapter = self._require_adapter()
        issues: list[BrokerReconciliationIssue] = []
        updated_orders: list[InternalOrder] = []

        account_snapshot = adapter.get_account_snapshot(account_id)
        self._flag_stale_sync(
            account_snapshot=account_snapshot,
            max_sync_age_seconds=max_sync_age_seconds,
            issues=issues,
        )

        local_orders = self._ledger.by_account(account_id)
        local_by_client_order_id = {order.client_order_id: order for order in local_orders}
        for order in local_orders:
            try:
                result = adapter.get_order(order)
            except BrokerAdapterError:
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
            updated_orders.append(self.apply_result(result))

        for result in adapter.list_open_orders(account_id):
            if result.client_order_id in local_by_client_order_id:
                continue
            issues.append(
                BrokerReconciliationIssue(
                    issue_type=BrokerReconciliationIssueType.MISSING_LOCAL_ORDER,
                    account_id=account_id,
                    order_id=result.order_id,
                    client_order_id=result.client_order_id,
                    broker_order_id=result.broker_order_id,
                    message="broker order has no matching internal order; intent is unknown and order is preserved",
                    actual="unknown_intent",
                    action="preserve_external_order_and_flag",
                )
            )

        positions = adapter.get_positions(account_id)
        self._flag_position_mismatches(
            account_id=account_id,
            positions=positions,
            expected_positions_by_symbol=expected_positions_by_symbol or {},
            issues=issues,
        )

        return BrokerReconciliationReport(
            account_id=account_id,
            updated_order_count=len(updated_orders),
            broker_position_count=len(positions),
            issues=tuple(issues),
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
        broker_qty_by_symbol = {position.symbol.upper(): position.quantity for position in positions}
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
