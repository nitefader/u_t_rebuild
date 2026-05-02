from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import (
    AlpacaAccountStreamAdapter,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerReconciliationIssueType,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce, TradingMode
from backend.app.governor import BrokerSyncFreshness, GovernorRequest, PortfolioGovernor, PortfolioSnapshot
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.runtime import RuntimeState
from backend.tests.fixtures.legacy_intent import LegacyExecutionIntent as ExecutionIntent
from backend.tests.fixtures.modern_order import make_signal_plan_order


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


class ReconciliationAdapter:
    def __init__(
        self,
        *,
        account_snapshot: BrokerAccountSnapshot | None = None,
        order_results_by_client_id: dict[str, BrokerOrderResult] | None = None,
        open_orders: tuple[BrokerOpenOrderSnapshot, ...] = (),
        positions: tuple[BrokerPositionSnapshot, ...] = (),
        missing_client_order_ids: set[str] | None = None,
        fail_account_snapshot: bool = False,
    ) -> None:
        self.account_snapshot = account_snapshot or BrokerAccountSnapshot(
            account_id=ACCOUNT_ID,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )
        self.order_results_by_client_id = order_results_by_client_id or {}
        self.open_orders = open_orders
        self.positions = positions
        self.missing_client_order_ids = missing_client_order_ids or set()
        self.fail_account_snapshot = fail_account_snapshot
        self.submitted_orders: list[InternalOrder] = []
        self.get_order_client_ids: list[str] = []

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        self.submitted_orders.append(order)
        return _result(order, BrokerOrderStatus.ACCEPTED)

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        self.get_order_client_ids.append(order.client_order_id)
        if order.client_order_id in self.missing_client_order_ids:
            raise BrokerAdapterError("missing broker order")
        return self.order_results_by_client_id.get(order.client_order_id, _result(order, BrokerOrderStatus.ACCEPTED))

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        assert account_id == ACCOUNT_ID
        return self.open_orders

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        assert account_id == ACCOUNT_ID
        if self.fail_account_snapshot:
            raise BrokerAdapterError("poll failed")
        return self.account_snapshot

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        assert account_id == ACCOUNT_ID
        return self.positions


def _intent() -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=DEPLOYMENT_ID,
        program_version_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        governor_approved=True,
        governor_reason="approved",
    )


def _manager_and_order() -> tuple[OrderManager, InternalOrder]:
    manager = OrderManager()
    return manager, make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)


def _result(order: InternalOrder, status: BrokerOrderStatus) -> BrokerOrderResult:
    filled_quantity = order.quantity if status == BrokerOrderStatus.FILLED else 0
    reason = "broker_rejected" if status == BrokerOrderStatus.REJECTED else None
    return BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=status,
        broker_order_id=f"broker-{order.client_order_id}",
        broker_status=status.value,
        filled_quantity=filled_quantity,
        filled_avg_price=100 if filled_quantity else None,
        remaining_quantity=order.quantity - filled_quantity,
        reason=reason,
        raw_status=status.value,
    )


def _filled_signal_plan_order(
    *,
    deployment_id: UUID = DEPLOYMENT_ID,
    symbol: str = "SPY",
    qty: float = 3,
    side: CandidateSide = CandidateSide.LONG,
    opening_signal_plan_id: UUID | None = None,
    position_lineage_id: UUID | None = None,
    strategy_id: UUID | None = None,
    strategy_version_id: UUID | None = None,
) -> InternalOrder:
    opening_id = opening_signal_plan_id or uuid4()
    lineage_id = position_lineage_id or opening_id
    created_at = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"sp-{uuid4()}",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=deployment_id,
        strategy_id=strategy_id or uuid4(),
        strategy_version_id=strategy_version_id or uuid4(),
        signal_plan_id=opening_id,
        opening_signal_plan_id=opening_id,
        current_signal_plan_id=opening_id,
        position_lineage_id=lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        symbol=symbol,
        side=side,
        quantity=abs(qty),
        filled_quantity=abs(qty),
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.FILLED,
        created_at=created_at,
        updated_at=created_at,
    )


def _external_snapshot(*, client_order_id: str = "external-client-order") -> BrokerOpenOrderSnapshot:
    return BrokerOpenOrderSnapshot(
        account_id=ACCOUNT_ID,
        broker_order_id="external-broker-order",
        client_order_id=client_order_id,
        symbol="SPY",
        side="buy",
        qty=1,
        filled_qty=0,
        status=BrokerOrderStatus.ACCEPTED,
        order_type="market",
    )


class RecordingTradeLedger:
    def __init__(self) -> None:
        self.fills: list[BrokerFillUpdateEvent] = []

    def record_fill(self, event: BrokerFillUpdateEvent) -> None:
        self.fills.append(event)


class RecordingRuntimeStore:
    def __init__(self) -> None:
        self.open_order_replacements: list[tuple[UUID, tuple[BrokerOpenOrderSnapshot, ...]]] = []
        self.open_order_saves: list[BrokerOpenOrderSnapshot] = []
        self.position_replacements: list[tuple[UUID, tuple[BrokerPositionSnapshot, ...]]] = []
        self.position_saves: list[BrokerPositionSnapshot] = []
        self.sync_states: list[object] = []

    def save_broker_account_snapshot(self, snapshot: BrokerAccountSnapshot) -> BrokerAccountSnapshot:
        return snapshot

    def replace_broker_position_snapshots(
        self,
        account_id: UUID,
        snapshots: tuple[BrokerPositionSnapshot, ...],
    ) -> tuple[BrokerPositionSnapshot, ...]:
        self.position_replacements.append((account_id, snapshots))
        return snapshots

    def save_broker_position_snapshot(self, snapshot: BrokerPositionSnapshot) -> BrokerPositionSnapshot:
        self.position_saves.append(snapshot)
        return snapshot

    def save_broker_sync_freshness(self, state):  # type: ignore[no-untyped-def]
        self.sync_states.append(state)
        return state

    def replace_broker_open_order_snapshots(
        self,
        account_id: UUID,
        snapshots: tuple[BrokerOpenOrderSnapshot, ...],
    ) -> tuple[BrokerOpenOrderSnapshot, ...]:
        self.open_order_replacements.append((account_id, snapshots))
        return snapshots

    def save_broker_open_order_snapshot(self, snapshot: BrokerOpenOrderSnapshot) -> BrokerOpenOrderSnapshot:
        self.open_order_saves.append(snapshot)
        return snapshot


class FailingDailyStateRuntimeStore(RecordingRuntimeStore):
    def save_daily_account_state(self, _state) -> None:  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")


def test_missing_local_order_flagged() -> None:
    manager = OrderManager()
    adapter = ReconciliationAdapter(open_orders=(_external_snapshot(),))

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    assert report.has_issues is True
    issue = report.issues[0]
    assert issue.issue_type == BrokerReconciliationIssueType.MISSING_LOCAL_ORDER
    assert issue.action == "preserve_external_order_and_flag"
    assert issue.actual == "unknown_intent"


def test_reconcile_persists_current_open_broker_order_snapshots_for_operations_visibility() -> None:
    manager = OrderManager()
    snapshot = _external_snapshot()
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=3,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=300,
    )
    store = RecordingRuntimeStore()
    adapter = ReconciliationAdapter(open_orders=(snapshot,), positions=(position,))

    BrokerSyncService(
        adapter=adapter,
        broker_sync=BrokerSync(ledger=manager.ledger, adapter=adapter, runtime_store=store),
        order_ledger=manager.ledger,
        runtime_store=store,
    ).reconcile(ACCOUNT_ID)

    assert store.open_order_replacements == [(ACCOUNT_ID, (snapshot,))]
    # M2 (HARD.MD P0-2): unmatched lineage → position is classified as
    # unmanaged before persistence so Governor concentration sees it.
    assert store.position_replacements == [
        (
            ACCOUNT_ID,
            (
                position.model_copy(
                    update={
                        "unmanaged_broker_position": True,
                        "adoption_status": "unmanaged",
                    }
                ),
            ),
        )
    ]


def test_reconcile_enriches_position_snapshot_with_signal_plan_lineage() -> None:
    manager = OrderManager()
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    strategy_id = uuid4()
    order = _filled_signal_plan_order(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_id=strategy_id,
    )
    manager.ledger.add(order)
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=3,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=300,
    )
    store = RecordingRuntimeStore()
    adapter = ReconciliationAdapter(positions=(position,))

    BrokerSyncService(
        adapter=adapter,
        broker_sync=BrokerSync(ledger=manager.ledger, adapter=adapter, runtime_store=store),
        order_ledger=manager.ledger,
        runtime_store=store,
    ).reconcile(ACCOUNT_ID)

    enriched = store.position_replacements[-1][1][0]
    assert enriched.deployment_id == DEPLOYMENT_ID
    assert enriched.strategy_id == strategy_id
    assert enriched.opening_signal_plan_id == opening_signal_plan_id
    assert enriched.position_lineage_id == position_lineage_id


def test_reconcile_does_not_guess_lineage_when_position_ownership_is_ambiguous() -> None:
    manager = OrderManager()
    other_deployment_id = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
    manager.ledger.add(_filled_signal_plan_order(deployment_id=DEPLOYMENT_ID, qty=3))
    manager.ledger.add(_filled_signal_plan_order(deployment_id=other_deployment_id, qty=3))
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=3,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=300,
    )
    store = RecordingRuntimeStore()
    adapter = ReconciliationAdapter(positions=(position,))

    BrokerSyncService(
        adapter=adapter,
        broker_sync=BrokerSync(ledger=manager.ledger, adapter=adapter, runtime_store=store),
        order_ledger=manager.ledger,
        runtime_store=store,
    ).reconcile(ACCOUNT_ID)

    enriched = store.position_replacements[-1][1][0]
    assert enriched.deployment_id is None
    assert enriched.opening_signal_plan_id is None
    assert enriched.position_lineage_id is None


def test_reconcile_stamps_deployment_only_when_single_deployment_has_multiple_lineages() -> None:
    manager = OrderManager()
    manager.ledger.add(_filled_signal_plan_order(deployment_id=DEPLOYMENT_ID, qty=1))
    manager.ledger.add(_filled_signal_plan_order(deployment_id=DEPLOYMENT_ID, qty=2))
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=3,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=300,
    )
    store = RecordingRuntimeStore()
    adapter = ReconciliationAdapter(positions=(position,))

    BrokerSyncService(
        adapter=adapter,
        broker_sync=BrokerSync(ledger=manager.ledger, adapter=adapter, runtime_store=store),
        order_ledger=manager.ledger,
        runtime_store=store,
    ).reconcile(ACCOUNT_ID)

    enriched = store.position_replacements[-1][1][0]
    assert enriched.deployment_id == DEPLOYMENT_ID
    assert enriched.strategy_id is not None
    assert enriched.opening_signal_plan_id is None
    assert enriched.position_lineage_id is None


def test_stream_position_update_persists_position_snapshot_for_operations_visibility() -> None:
    store = RecordingRuntimeStore()
    manager = OrderManager()
    adapter = ReconciliationAdapter()
    service = BrokerSyncService(
        adapter=adapter,
        broker_sync=BrokerSync(ledger=manager.ledger, adapter=adapter, runtime_store=store),
        order_ledger=manager.ledger,
        runtime_store=store,
    )
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=3,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=300,
    )

    service.handle_position_update(position)

    # M2: stream-emitted position with no lineage gets the unmanaged
    # classification before persistence so the saved snapshot already
    # carries the operator-visible flag.
    assert store.position_saves == [
        position.model_copy(
            update={"unmanaged_broker_position": True, "adoption_status": "unmanaged"}
        )
    ]


def test_missing_broker_order_flagged() -> None:
    manager, order = _manager_and_order()
    adapter = ReconciliationAdapter(missing_client_order_ids={order.client_order_id})

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    assert any(issue.issue_type == BrokerReconciliationIssueType.MISSING_BROKER_ORDER for issue in report.issues)
    assert manager.ledger.get(order.order_id).status == InternalOrderStatus.CREATED


def test_filled_order_reconciles() -> None:
    manager, order = _manager_and_order()
    adapter = ReconciliationAdapter(order_results_by_client_id={order.client_order_id: _result(order, BrokerOrderStatus.FILLED)})

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    updated = manager.ledger.get(order.order_id)
    assert report.updated_order_count == 1
    assert updated.status == InternalOrderStatus.FILLED
    assert updated.filled_quantity == order.quantity


def test_reconcile_skips_terminal_internal_orders_during_quiet_polling() -> None:
    manager, active_order = _manager_and_order()
    terminal_order = manager.ledger.update_status(
        order_id=active_order.order_id,
        status=InternalOrderStatus.FILLED,
    )
    second_order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)
    adapter = ReconciliationAdapter(
        order_results_by_client_id={second_order.client_order_id: _result(second_order, BrokerOrderStatus.ACCEPTED)}
    )

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    assert adapter.get_order_client_ids == [second_order.client_order_id]
    assert report.matched_orders == (second_order.client_order_id,)
    assert terminal_order.client_order_id not in report.unmatched_internal_orders


def test_reconciliation_reports_mismatched_fill_quantities() -> None:
    manager, order = _manager_and_order()
    broker_result = BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.PARTIAL_FILL,
        broker_order_id=f"broker-{order.client_order_id}",
        broker_status="partially_filled",
        filled_quantity=4,
        remaining_quantity=6,
        raw_status="partially_filled",
    )
    adapter = ReconciliationAdapter(order_results_by_client_id={order.client_order_id: broker_result})

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    issue = next(issue for issue in report.issues if issue.issue_type == BrokerReconciliationIssueType.MISMATCHED_FILL)
    assert issue.client_order_id == order.client_order_id
    assert issue.expected == 0
    assert issue.actual == 4


def test_rejected_order_reconciles() -> None:
    manager, order = _manager_and_order()
    adapter = ReconciliationAdapter(order_results_by_client_id={order.client_order_id: _result(order, BrokerOrderStatus.REJECTED)})

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    updated = manager.ledger.get(order.order_id)
    assert report.updated_order_count == 1
    assert updated.status == InternalOrderStatus.REJECTED
    assert updated.reason == "broker_rejected"


def test_position_mismatch_flagged() -> None:
    manager = OrderManager()
    adapter = ReconciliationAdapter(
        positions=(
            BrokerPositionSnapshot(
                account_id=ACCOUNT_ID,
                symbol="SPY",
                quantity=8,
                market_value=800,
                avg_entry_price=100,
                side=BrokerPositionSide.LONG,
            ),
        )
    )

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(
        ACCOUNT_ID,
        expected_positions_by_symbol={"SPY": 10},
    )

    issue = next(issue for issue in report.issues if issue.issue_type == BrokerReconciliationIssueType.POSITION_MISMATCH)
    assert issue.symbol == "SPY"
    assert issue.expected == 10
    assert issue.actual == 8


def test_stale_sync_blocks_opens() -> None:
    manager = OrderManager()
    stale_snapshot = BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        provider="fake",
        mode=TradingMode.BROKER_PAPER,
        buying_power=100_000,
        cash=100_000,
        equity=100_000,
        last_synced_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    report = BrokerSync(
        ledger=manager.ledger,
        adapter=ReconciliationAdapter(account_snapshot=stale_snapshot),
    ).reconcile(ACCOUNT_ID, max_sync_age_seconds=1)

    decision = PortfolioGovernor().evaluate(
        GovernorRequest(
            account_id=ACCOUNT_ID,
            execution_intent=_intent().model_copy(update={"governor_approved": False}),
            runtime_state=RuntimeState(deployment_id=DEPLOYMENT_ID),
            broker_sync=BrokerSyncFreshness(is_stale=report.is_stale, reason="reconciliation_stale"),
            portfolio=PortfolioSnapshot(),
        )
    )

    assert any(issue.issue_type == BrokerReconciliationIssueType.STALE_SYNC for issue in report.issues)
    assert decision.approved is False
    assert decision.reason == "broker_sync_stale"


def test_broker_sync_state_marks_fresh_and_stale_explicitly() -> None:
    manager = OrderManager()
    fresh_snapshot = BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        buying_power=100_000,
        cash=100_000,
        equity=100_000,
        timestamp=datetime.now(timezone.utc),
    )
    stale_snapshot = fresh_snapshot.model_copy(update={"timestamp": datetime.now(timezone.utc) - timedelta(minutes=1)})
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(account_snapshot=fresh_snapshot),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
        max_stale_seconds=10,
    )

    assert service.sync_state(fresh_snapshot).is_stale is False
    stale_state = service.sync_state(stale_snapshot)
    assert stale_state.is_stale is True
    assert stale_state.stale_reason == "broker_snapshot_age_exceeded_10s"


def test_broker_sync_service_writes_order_updates_only_through_broker_sync() -> None:
    class RecordingBrokerSync(BrokerSync):
        def __init__(self, *, ledger):
            super().__init__(ledger=ledger)
            self.applied_client_order_ids: list[str] = []

        def apply_result(self, result: BrokerOrderResult):
            self.applied_client_order_ids.append(result.client_order_id)
            return super().apply_result(result)

    manager, order = _manager_and_order()
    broker_result = _result(order, BrokerOrderStatus.ACCEPTED)
    recording_sync = RecordingBrokerSync(ledger=manager.ledger)
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(order_results_by_client_id={order.client_order_id: broker_result}),
        broker_sync=recording_sync,
        order_ledger=manager.ledger,
    )

    report = service.reconcile(ACCOUNT_ID)

    assert report.matched_orders == (order.client_order_id,)
    assert recording_sync.applied_client_order_ids == [order.client_order_id]


def test_unknown_order_intent_preserved_and_flagged() -> None:
    manager = OrderManager()
    external = _external_snapshot(client_order_id="unknown-external-intent")
    adapter = ReconciliationAdapter(open_orders=(external,))

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    assert manager.ledger.all() == ()
    issue = report.issues[0]
    assert issue.issue_type == BrokerReconciliationIssueType.MISSING_LOCAL_ORDER
    assert issue.client_order_id == "unknown-external-intent"
    assert issue.action == "preserve_external_order_and_flag"
    assert issue.actual == "unknown_intent"


def test_alpaca_account_stream_adapter_normalizes_order_fill_position_and_account_updates() -> None:
    adapter = AlpacaAccountStreamAdapter(account_id=ACCOUNT_ID)

    order_events = adapter.normalize(
        {
            "event": "fill",
            "price": "101.25",
            "qty": "10",
            "order": {
                "id": "alpaca-order-1",
                "client_order_id": "client-1",
                "symbol": "SPY",
                "side": "buy",
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "101.25",
            },
        }
    )
    position_events = adapter.normalize({"symbol": "SPY", "qty": "10", "market_value": "1012.5", "avg_entry_price": "101.25"})
    account_events = adapter.normalize({"buying_power": "90000", "cash": "90000", "equity": "100000"})

    assert isinstance(order_events[0], BrokerOrderUpdateEvent)
    assert isinstance(order_events[1], BrokerFillUpdateEvent)
    assert isinstance(position_events[0], BrokerPositionSnapshot)
    assert isinstance(account_events[0], BrokerAccountSnapshot)


def test_streaming_order_update_updates_order_ledger_through_broker_sync() -> None:
    manager, order = _manager_and_order()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
    )

    updated = service.handle_order_update(
        BrokerOrderUpdateEvent(
            account_id=ACCOUNT_ID,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.FILLED,
            broker_order_id="broker-stream-1",
            broker_status="filled",
            filled_quantity=order.quantity,
            filled_avg_price=100,
            remaining_quantity=0,
        )
    )

    assert updated.status == InternalOrderStatus.FILLED
    assert manager.ledger.get(order.order_id).filled_quantity == order.quantity
    assert service.current_sync_state(ACCOUNT_ID).is_stale is False


def test_streaming_external_open_order_update_is_preserved_for_operations_visibility() -> None:
    store = RecordingRuntimeStore()
    manager = OrderManager()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger, runtime_store=store),
        order_ledger=manager.ledger,
    )

    updated = service.handle_order_update(
        BrokerOrderUpdateEvent(
            account_id=ACCOUNT_ID,
            client_order_id="external-client-1",
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id="external-broker-1",
            symbol="SPY",
            side="buy",
            qty=2,
            order_type="limit",
            limit_price=700,
        )
    )

    assert updated is None
    assert len(store.open_order_saves) == 1
    snapshot = store.open_order_saves[0]
    assert snapshot.client_order_id == "external-client-1"
    assert snapshot.symbol == "SPY"
    assert snapshot.qty == 2
    assert service.current_sync_state(ACCOUNT_ID).is_stale is False


def test_streaming_fill_update_updates_trade_ledger() -> None:
    trade_ledger = RecordingTradeLedger()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        trade_ledger=trade_ledger,
    )
    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="client-1",
        symbol="SPY",
        qty=5,
        price=101,
        side="buy",
    )

    service.handle_fill_update(fill)

    assert service.fills() == (fill,)
    assert trade_ledger.fills == [fill]


def test_save_daily_account_state_failure_logs_warning(caplog) -> None:
    class _PassthroughAggregator:
        def apply_fill(self, _current, fill, *, equity):  # type: ignore[no-untyped-def]
            from backend.app.runtime.daily_account_state import DailyAccountStateAggregator

            return DailyAccountStateAggregator().apply_fill(None, fill, equity=equity)

    store = FailingDailyStateRuntimeStore()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        runtime_store=store,
        daily_state_aggregator=_PassthroughAggregator(),
        daily_states={},
    )
    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="client-1",
        symbol="SPY",
        qty=1,
        price=100,
        side="buy",
    )

    with caplog.at_level(logging.WARNING, logger="backend.app.brokers.sync"):
        service.handle_fill_update(fill)

    state = service.daily_state_for(ACCOUNT_ID)
    assert state is not None
    assert state.account_id == ACCOUNT_ID
    assert any(
        record.__dict__.get("event") == "broker_sync_daily_state_persist_failed"
        and record.__dict__.get("account_id") == str(ACCOUNT_ID)
        and record.__dict__.get("market_day") == state.market_day
        for record in caplog.records
    )


def test_daily_state_fill_updates_are_serialized_per_account() -> None:
    class _CounterAggregator:
        def __init__(self) -> None:
            self._guard = threading.Lock()
            self.in_flight = 0
            self.max_in_flight = 0

        def apply_fill(self, current, _fill, *, equity):  # type: ignore[no-untyped-def]
            import time

            with self._guard:
                self.in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self.in_flight)
            time.sleep(0.02)
            base = int(current) if current is not None else 0
            with self._guard:
                self.in_flight -= 1
            return base + 1

    aggregator = _CounterAggregator()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        daily_state_aggregator=aggregator,
        daily_states={},
    )
    fill_a = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="client-a",
        symbol="SPY",
        qty=1,
        price=100,
        side="buy",
    )
    fill_b = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="client-b",
        symbol="SPY",
        qty=1,
        price=100,
        side="buy",
    )
    t1 = threading.Thread(target=lambda: service.handle_fill_update(fill_a))
    t2 = threading.Thread(target=lambda: service.handle_fill_update(fill_b))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert service.daily_state_for(ACCOUNT_ID) == 2
    assert aggregator.max_in_flight == 1



def test_streaming_position_update_updates_snapshot() -> None:
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
    )
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=10,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=1000,
    )

    service.handle_position_update(position)

    # M2 (HARD.MD P0-2): a stream-emitted position with no SignalPlan
    # lineage is classified as `unmanaged_broker_position=True` /
    # `adoption_status="unmanaged"` by `_enrich_position_snapshot_with_lineage`
    # so Governor concentration sees the exposure and the operator UI
    # surfaces the Unmanaged badge. The classification is the only
    # delta from the input; everything else round-trips.
    persisted = service.latest_positions(ACCOUNT_ID)
    assert persisted == (
        position.model_copy(
            update={"unmanaged_broker_position": True, "adoption_status": "unmanaged"}
        ),
    )


def test_streaming_account_update_updates_buying_power() -> None:
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
    )
    snapshot = BrokerAccountSnapshot(account_id=ACCOUNT_ID, buying_power=50_000, cash=25_000, equity=75_000)

    service.handle_account_update(snapshot)

    assert service.latest_account_snapshot(ACCOUNT_ID).buying_power == 50_000


def test_stream_disconnect_triggers_fallback_poll() -> None:
    manager = OrderManager()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
    )

    report = service.handle_stream_disconnect(ACCOUNT_ID)

    assert report is not None
    assert service.current_sync_state(ACCOUNT_ID).is_stale is False
    assert service.current_sync_state(ACCOUNT_ID).last_poll_sync_at is not None


def test_stream_disconnect_poll_failure_marks_stale() -> None:
    manager = OrderManager()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(fail_account_snapshot=True),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
    )

    report = service.handle_stream_disconnect(ACCOUNT_ID)

    assert report is None
    state = service.current_sync_state(ACCOUNT_ID)
    assert state.is_stale is True
    assert state.stale_reason == "stream_disconnect_poll_failed"


def test_broker_sync_state_marks_stale_without_recent_event_or_poll() -> None:
    manager = OrderManager()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
    )

    state = service.current_sync_state(ACCOUNT_ID)

    assert state.is_stale is True
    assert state.stale_reason == "broker_truth_never_synced"


def test_no_stream_adapter_direct_mutation_outside_broker_sync_service() -> None:
    import inspect
    import backend.app.brokers.stream as stream_module

    source = inspect.getsource(stream_module.AlpacaAccountStreamAdapter)

    assert "OrderLedger" not in source
    assert "TradeLedger" not in source
    assert "BrokerSyncService" not in source
    assert "BrokerSync(" not in source


def test_partial_fill_stream_events_accumulate_filled_quantity() -> None:
    """Two partial fills then a full fill move filled_quantity 0 → 4 → 7 → 10.

    The broker delivers cumulative ``filled_quantity`` on each
    ``BrokerOrderUpdateEvent`` and the internal order must mirror that
    progression, never decreasing or double-counting.
    """
    manager, order = _manager_and_order()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
    )

    progress: list[float] = []
    for cumulative_filled, status in (
        (4.0, BrokerOrderStatus.PARTIAL_FILL),
        (7.0, BrokerOrderStatus.PARTIAL_FILL),
        (10.0, BrokerOrderStatus.FILLED),
    ):
        service.handle_order_update(
            BrokerOrderUpdateEvent(
                account_id=ACCOUNT_ID,
                client_order_id=order.client_order_id,
                status=status,
                broker_order_id=f"broker-{order.client_order_id}",
                broker_status=status.value,
                filled_quantity=cumulative_filled,
                filled_avg_price=100,
                remaining_quantity=order.quantity - cumulative_filled,
            )
        )
        progress.append(manager.ledger.get(order.order_id).filled_quantity)

    assert progress == [4.0, 7.0, 10.0]
    final = manager.ledger.get(order.order_id)
    assert final.status == InternalOrderStatus.FILLED
    assert final.filled_quantity == order.quantity


def test_partial_fill_stream_events_record_each_execution_in_trade_ledger() -> None:
    """Each fill stream event lands as one ``Trade`` entry, idempotent by execution id."""
    from backend.app.orders import TradeLedger

    trade_ledger = TradeLedger()
    service = BrokerSyncService(
        adapter=ReconciliationAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        trade_ledger=trade_ledger,
    )

    fills = [
        BrokerFillUpdateEvent(
            account_id=ACCOUNT_ID,
            client_order_id="client-1",
            symbol="SPY",
            qty=4,
            price=100,
            side="buy",
            broker_execution_id="exec-1",
        ),
        BrokerFillUpdateEvent(
            account_id=ACCOUNT_ID,
            client_order_id="client-1",
            symbol="SPY",
            qty=3,
            price=101,
            side="buy",
            broker_execution_id="exec-2",
        ),
    ]
    for fill in fills:
        service.handle_fill_update(fill)
    # Re-deliver to verify idempotency.
    service.handle_fill_update(fills[0])

    trades = trade_ledger.all()
    assert len(trades) == 2
    assert {trade.broker_execution_id for trade in trades} == {"exec-1", "exec-2"}
    assert sum(trade.qty for trade in trades) == 7
