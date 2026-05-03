"""Phase 2 §11.4-5 exit-gate evidence: broker truth wiring (slice 2C).

This test pins the four contracts the architect's gap analysis demanded for
the money-path:

1. Stream events are routed end-to-end (router → sync service → ledgers).
2. Partial-fill events accumulate ``filled_quantity`` cumulatively on the
   internal order; trades are recorded once per ``broker_execution_id``.
3. ``BrokerSyncService.current_sync_state`` reflects "fresh" after a stream
   event and "stale" once the staleness window has elapsed without
   subsequent truth.
4. ``OrderManager.create_signal_plan_order`` blocks new OPEN intents while broker sync
   is stale, but still allows CLOSE / protective orders.
"""

from __future__ import annotations

from time import sleep
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerStreamRouter,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    OrderType,
    RiskResolverResult,
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanSide,
    TimeInForce,
    TradingMode,
)
from backend.app.orders import (
    InternalOrderIntent,
    InternalOrderStatus,
    OrderManager,
    OrderManagerError,
    TradeLedger,
)

ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")


class _StaticAdapter:
    def __init__(self) -> None:
        self.account_snapshot = BrokerAccountSnapshot(
            account_id=ACCOUNT_ID,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return self.account_snapshot

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return ()

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        return ()

    def get_order(self, order) -> BrokerOrderResult:
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id=f"broker-{order.client_order_id}",
            broker_status="accepted",
            raw_status="accepted",
        )


def _create_signal_plan_order(
    manager: OrderManager,
    *,
    intent: SignalPlanIntent = SignalPlanIntent.OPEN,
):
    lineage_id = uuid4()
    plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=PROGRAM_ID,
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=intent,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY)
        if intent == SignalPlanIntent.OPEN
        else None,
        opening_signal_plan_id=None if intent == SignalPlanIntent.OPEN else lineage_id,
        related_position_lineage_id=None if intent == SignalPlanIntent.OPEN else lineage_id,
        reason="signal_condition_true",
    )
    return manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=AccountSignalPlanEvaluation(
            evaluation_id=uuid4(),
            account_id=ACCOUNT_ID,
            signal_plan_id=plan.signal_plan_id,
            deployment_id=plan.deployment_id,
            strategy_id=plan.strategy_id,
            status=AccountEvaluationStatus.ACCEPTED,
            participation_decision=AccountParticipationDecision.PARTICIPATE,
        ),
        risk_result=RiskResolverResult(
            account_id=ACCOUNT_ID,
            signal_plan_id=plan.signal_plan_id,
            allowed=True,
            resolved_quantity=10,
        ),
        governor_decision=GovernorDecisionTrace(
            governor_decision_id=uuid4(),
            account_id=ACCOUNT_ID,
            signal_plan_id=plan.signal_plan_id,
            status=GovernorDecisionStatus.APPROVED,
            approved=True,
            reasons=("approved",),
        ),
    )


def test_stream_routes_partial_fills_into_order_and_trade_ledgers() -> None:
    manager = OrderManager()
    trade_ledger = TradeLedger()
    service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
        trade_ledger=trade_ledger,
    )
    router = BrokerStreamRouter(service)
    order = _create_signal_plan_order(manager)

    for cumulative, status, exec_id in (
        (4.0, BrokerOrderStatus.PARTIAL_FILL, "exec-1"),
        (10.0, BrokerOrderStatus.FILLED, "exec-2"),
    ):
        router.route(
            BrokerOrderUpdateEvent(
                account_id=ACCOUNT_ID,
                client_order_id=order.client_order_id,
                status=status,
                broker_order_id=f"broker-{order.client_order_id}",
                broker_status=status.value,
                filled_quantity=cumulative,
                filled_avg_price=100,
                remaining_quantity=order.quantity - cumulative,
            )
        )
        router.route(
            BrokerFillUpdateEvent(
                account_id=ACCOUNT_ID,
                client_order_id=order.client_order_id,
                symbol="SPY",
                qty=cumulative if exec_id == "exec-1" else 6,
                price=100,
                side="buy",
                broker_execution_id=exec_id,
            )
        )

    final = manager.ledger.get(order.order_id)
    assert final.status == InternalOrderStatus.FILLED
    assert final.filled_quantity == order.quantity
    assert {trade.broker_execution_id for trade in trade_ledger.all()} == {"exec-1", "exec-2"}


def test_stale_broker_sync_blocks_new_opens_but_allows_closes() -> None:
    """Block-gate: while sync is stale, new OPEN orders raise; CLOSE still flows."""
    manager_factory = lambda service: OrderManager(broker_sync_service=service)
    service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        max_stale_seconds=0,
    )
    manager = manager_factory(service)

    # No stream events yet → never_synced is stale.
    assert service.current_sync_state(ACCOUNT_ID).is_stale is True

    with pytest.raises(OrderManagerError) as excinfo:
        _create_signal_plan_order(manager)
    assert "broker_sync_stale" in str(excinfo.value)

    # CLOSE intents are not gated — positions must remain exitable.
    closed = _create_signal_plan_order(manager, intent=SignalPlanIntent.CLOSE)
    assert closed.intent == InternalOrderIntent.CLOSE


def test_stream_event_clears_stale_flag_and_subsequent_window_marks_stale_again() -> None:
    """A stream event clears stale; once max_stale_seconds elapses, stale returns."""
    service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        max_stale_seconds=10,
    )
    router = BrokerStreamRouter(service)

    # Before any event the service reports never-synced.
    assert service.current_sync_state(ACCOUNT_ID).is_stale is True

    router.route(
        BrokerPositionSnapshot(
            account_id=ACCOUNT_ID,
            symbol="SPY",
            qty=10,
            side=BrokerPositionSide.LONG,
            avg_entry_price=100,
            market_value=1000,
        )
    )
    assert service.current_sync_state(ACCOUNT_ID).is_stale is False

    # Tighten the window so the just-applied event is now considered stale.
    aged_service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        max_stale_seconds=0,
    )
    aged_router = BrokerStreamRouter(aged_service)
    aged_router.route(
        BrokerPositionSnapshot(
            account_id=ACCOUNT_ID,
            symbol="SPY",
            qty=10,
            side=BrokerPositionSide.LONG,
            avg_entry_price=100,
            market_value=1000,
        )
    )
    sleep(0.01)
    aged_state = aged_service.current_sync_state(ACCOUNT_ID)
    assert aged_state.is_stale is True
    assert "broker_truth_age_exceeded_0s" in (aged_state.stale_reason or "")
