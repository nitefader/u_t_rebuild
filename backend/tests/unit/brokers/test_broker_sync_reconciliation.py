from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerReconciliationIssueType,
    BrokerSync,
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
        open_orders: tuple[BrokerOrderResult, ...] = (),
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

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOrderResult, ...]:
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


def _external_result(*, client_order_id: str = "external-client-order") -> BrokerOrderResult:
    return BrokerOrderResult(
        order_id=uuid4(),
        client_order_id=client_order_id,
        status=BrokerOrderStatus.ACCEPTED,
        broker_order_id="external-broker-order",
        broker_status="new",
        raw_status="new",
    )


def test_missing_local_order_flagged() -> None:
    manager = OrderManager()
    adapter = ReconciliationAdapter(open_orders=(_external_result(),))

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


def test_unknown_order_intent_preserved_and_flagged() -> None:
    manager = OrderManager()
    external = _external_result(client_order_id="unknown-external-intent")
    adapter = ReconciliationAdapter(open_orders=(external,))

    report = BrokerSync(ledger=manager.ledger, adapter=adapter).reconcile(ACCOUNT_ID)

    assert manager.ledger.all() == ()
    issue = report.issues[0]
    assert issue.issue_type == BrokerReconciliationIssueType.MISSING_LOCAL_ORDER
    assert issue.client_order_id == "unknown-external-intent"
    assert issue.action == "preserve_external_order_and_flag"
    assert issue.actual == "unknown_intent"
