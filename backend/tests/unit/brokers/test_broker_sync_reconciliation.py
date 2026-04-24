from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerReconciliationIssueType,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.governor import BrokerSyncFreshness, GovernorRequest, PortfolioGovernor, PortfolioSnapshot
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderManager
from backend.app.runtime import ExecutionIntent, RuntimeState


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
    ) -> None:
        self.account_snapshot = account_snapshot or BrokerAccountSnapshot(
            account_id=ACCOUNT_ID,
            provider="fake",
            mode=BrokerAccountMode.PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )
        self.order_results_by_client_id = order_results_by_client_id or {}
        self.open_orders = open_orders
        self.positions = positions
        self.missing_client_order_ids = missing_client_order_ids or set()
        self.submitted_orders: list[InternalOrder] = []

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        self.submitted_orders.append(order)
        return _result(order, BrokerOrderStatus.ACCEPTED)

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        if order.client_order_id in self.missing_client_order_ids:
            raise BrokerAdapterError("missing broker order")
        return self.order_results_by_client_id.get(order.client_order_id, _result(order, BrokerOrderStatus.ACCEPTED))

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        assert account_id == ACCOUNT_ID
        return self.open_orders

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        assert account_id == ACCOUNT_ID
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
    return manager, manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent())


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


def test_missing_local_order_flagged() -> None:
    manager = OrderManager()
    adapter = ReconciliationAdapter(open_orders=(_external_snapshot(),))

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    assert report.has_issues is True
    issue = report.issues[0]
    assert issue.issue_type == BrokerReconciliationIssueType.MISSING_LOCAL_ORDER
    assert issue.action == "preserve_external_order_and_flag"
    assert issue.actual == "unknown_intent"


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
        mode=BrokerAccountMode.PAPER,
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
