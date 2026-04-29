from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import BrokerPositionSide, BrokerPositionSnapshot
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    CandidateSide,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    IntentType,
    OrderType,
    RiskResolvedLegAllocation,
    RiskResolverResult,
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanSide,
    TimeInForce,
)
from backend.app.orders import InternalOrderIntent, InternalOrderStatus, OrderLedger, OrderManager, OrderManagerError, OrderOrigin
from backend.tests.fixtures.legacy_intent import LegacyExecutionIntent as ExecutionIntent
import backend.app.orders.manager as order_manager_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")


def _execution_intent(
    *,
    deployment_id: UUID = DEPLOYMENT_ID,
    program_id: UUID = PROGRAM_ID,
    symbol: str = "spy",
    qty: float = 10,
    intent_type: IntentType = IntentType.ENTRY,
    side: CandidateSide = CandidateSide.LONG,
) -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=deployment_id,
        program_version_id=program_id,
        symbol=symbol,
        side=side,
        intent_type=intent_type,
        qty=qty,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        features_used={"5m.close[0]": 100.0},
        governor_approved=True,
        governor_reason="approved",
    )


def _signal_plan(
    *,
    side: SignalPlanSide = SignalPlanSide.LONG,
    intent: SignalPlanIntent = SignalPlanIntent.OPEN,
    opening_signal_plan_id: UUID | None = None,
    related_position_lineage_id: UUID | None = None,
) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        symbol="SPY",
        side=side,
        intent=intent,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY)
        if intent == SignalPlanIntent.OPEN
        else None,
        opening_signal_plan_id=opening_signal_plan_id,
        related_position_lineage_id=related_position_lineage_id,
        reason="entry_rule_true",
    )


def _accepted_evaluation(*, account_id: UUID, signal_plan: SignalPlan) -> AccountSignalPlanEvaluation:
    return AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        deployment_id=signal_plan.deployment_id,
        strategy_id=signal_plan.strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
    )


def _risk_result(*, account_id: UUID, signal_plan: SignalPlan) -> RiskResolverResult:
    return RiskResolverResult(
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        allowed=True,
        resolved_quantity=10,
    )


def _governor_trace(*, account_id: UUID, signal_plan: SignalPlan) -> GovernorDecisionTrace:
    return GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        status=GovernorDecisionStatus.APPROVED,
        approved=True,
        reasons=("approved",),
    )


def test_creates_internal_order_before_broker_submission() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert order.order_id is not None
    assert order.status == InternalOrderStatus.CREATED
    assert order.intent == InternalOrderIntent.OPEN
    assert manager.ledger.get(order.order_id) == order


def test_client_order_id_format_is_correct() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert re.fullmatch(r"utos-[0-9a-f]{8}-(open|close|tp|sl|scale)-[0-9a-f]{8}", order.client_order_id)


def test_rejects_invalid_intent() -> None:
    manager = OrderManager()

    with pytest.raises(OrderManagerError):
        manager.create_order(
            account_id=ACCOUNT_ID,
            execution_intent=_execution_intent(),
            order_intent="mystery",
        )


def test_preserves_attribution() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="qqq"))

    assert order.account_id == ACCOUNT_ID
    assert order.deployment_id == DEPLOYMENT_ID
    assert order.program_id == PROGRAM_ID
    assert order.symbol == "QQQ"
    assert order.quantity == 10
    assert order.order_type == OrderType.MARKET
    assert order.side == CandidateSide.LONG


def test_create_signal_plan_order_requires_account_evaluation_risk_and_governor_lineage() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    evaluation = _accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan)
    risk_result = _risk_result(account_id=ACCOUNT_ID, signal_plan=plan)
    governor_trace = _governor_trace(account_id=ACCOUNT_ID, signal_plan=plan)

    order = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=evaluation,
        risk_result=risk_result,
        governor_decision=governor_trace,
    )

    assert order.origin == OrderOrigin.SIGNAL_PLAN
    assert order.deployment_id == plan.deployment_id
    assert order.program_id is None
    assert order.strategy_id == plan.strategy_id
    assert order.strategy_version_id == plan.strategy_version_id
    assert order.signal_plan_id == plan.signal_plan_id
    assert order.opening_signal_plan_id == plan.signal_plan_id
    assert order.current_signal_plan_id == plan.signal_plan_id
    assert order.position_lineage_id == plan.signal_plan_id
    assert order.account_evaluation_id == evaluation.evaluation_id
    assert order.governor_decision_id == governor_trace.governor_decision_id
    assert order.lifecycle_intent == InternalOrderIntent.OPEN.value
    assert order.quantity == 10
    assert order.client_order_id.startswith(f"sigplan-{ACCOUNT_ID.hex[:8]}-{plan.signal_plan_id.hex[:8]}-open-")


def test_create_signal_plan_leg_orders_preserves_one_signal_plan_with_child_lifecycle_legs() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    evaluation = _accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan)
    risk_result = _risk_result(account_id=ACCOUNT_ID, signal_plan=plan).model_copy(
        update={
            "resolved_quantity": 100,
            "leg_allocations": (
                RiskResolvedLegAllocation(
                    leg_label="entry",
                    lifecycle_intent=SignalPlanIntent.OPEN,
                    resolved_quantity=100,
                    quantity_pct=100,
                ),
                RiskResolvedLegAllocation(
                    leg_label="stop",
                    lifecycle_intent=SignalPlanIntent.STOP,
                    resolved_quantity=100,
                    quantity_pct=100,
                ),
                RiskResolvedLegAllocation(
                    leg_label="T1",
                    lifecycle_intent=SignalPlanIntent.TARGET,
                    resolved_quantity=25,
                    quantity_pct=25,
                ),
                RiskResolvedLegAllocation(
                    leg_label="runner",
                    lifecycle_intent=SignalPlanIntent.RUNNER,
                    resolved_quantity=30,
                    quantity_pct=30,
                ),
            ),
        }
    )

    orders = manager.create_signal_plan_leg_orders(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=evaluation,
        risk_result=risk_result,
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
    )

    orders_by_leg = {order.leg_label: order for order in orders}
    assert len(orders) == 4
    assert {order.signal_plan_id for order in orders} == {plan.signal_plan_id}
    assert {order.position_lineage_id for order in orders} == {plan.signal_plan_id}
    assert orders_by_leg["entry"].intent == InternalOrderIntent.OPEN
    assert orders_by_leg["entry"].side == CandidateSide.LONG
    assert orders_by_leg["entry"].quantity == 100
    assert orders_by_leg["stop"].intent == InternalOrderIntent.STOP
    assert orders_by_leg["stop"].side == CandidateSide.SHORT
    assert orders_by_leg["stop"].quantity == 100
    assert orders_by_leg["T1"].intent == InternalOrderIntent.TARGET
    assert orders_by_leg["T1"].quantity == 25
    assert orders_by_leg["runner"].intent == InternalOrderIntent.RUNNER
    assert orders_by_leg["runner"].quantity == 30


def test_logical_exit_supersedes_passive_position_management_orders() -> None:
    manager = OrderManager()
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()

    def create_management_order(intent: SignalPlanIntent, label: str):
        plan = _signal_plan(
            intent=intent,
            opening_signal_plan_id=opening_signal_plan_id,
            related_position_lineage_id=position_lineage_id,
        )
        return manager.create_signal_plan_order(
            account_id=ACCOUNT_ID,
            signal_plan=plan,
            account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
            risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
            governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
            leg_label=label,
        )

    stop = create_management_order(SignalPlanIntent.STOP, "stop")
    target = create_management_order(SignalPlanIntent.TARGET, "T1")

    superseded = manager.superseded_position_management_orders(
        account_id=ACCOUNT_ID,
        position_lineage_id=position_lineage_id,
        incoming_intent=InternalOrderIntent.LOGICAL_EXIT,
    )

    assert superseded == (stop, target)


def test_logical_exit_cancel_request_can_cancel_superseded_protective_orders() -> None:
    manager = OrderManager()
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()

    def create_management_order(intent: SignalPlanIntent, label: str):
        plan = _signal_plan(
            intent=intent,
            opening_signal_plan_id=opening_signal_plan_id,
            related_position_lineage_id=position_lineage_id,
        )
        return manager.create_signal_plan_order(
            account_id=ACCOUNT_ID,
            signal_plan=plan,
            account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
            risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
            governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
            leg_label=label,
        )

    stop = create_management_order(SignalPlanIntent.STOP, "stop")
    target = create_management_order(SignalPlanIntent.TARGET, "T1")

    canceled = manager.request_superseded_position_management_cancels(
        account_id=ACCOUNT_ID,
        position_lineage_id=position_lineage_id,
        incoming_intent=InternalOrderIntent.LOGICAL_EXIT,
    )

    assert {order.order_id for order in canceled} == {stop.order_id, target.order_id}
    assert all(order.cancel_requested_at is not None for order in canceled)


def test_target_does_not_supersede_higher_priority_stop() -> None:
    manager = OrderManager()
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    stop_plan = _signal_plan(
        intent=SignalPlanIntent.STOP,
        opening_signal_plan_id=opening_signal_plan_id,
        related_position_lineage_id=position_lineage_id,
    )
    stop = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=stop_plan,
        account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=stop_plan),
        risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=stop_plan),
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=stop_plan),
        leg_label="stop",
    )

    superseded = manager.superseded_position_management_orders(
        account_id=ACCOUNT_ID,
        position_lineage_id=position_lineage_id,
        incoming_intent=InternalOrderIntent.TARGET,
    )

    assert manager.pending_position_management_orders(
        account_id=ACCOUNT_ID,
        position_lineage_id=position_lineage_id,
    ) == (stop,)
    assert superseded == ()


def test_create_signal_plan_order_is_idempotent_for_same_account_signal_plan_lifecycle() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    first = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
        risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
    )
    second = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
        risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
    )

    assert second == first
    assert second.client_order_id == first.client_order_id
    assert manager.ledger.all() == (first,)


def test_create_signal_plan_order_rejects_unapproved_governor_trace() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    governor_trace = GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=plan.signal_plan_id,
        status=GovernorDecisionStatus.REJECTED,
        approved=False,
        reasons=("blocked",),
    )

    with pytest.raises(OrderManagerError, match="not approved by Governor"):
        manager.create_signal_plan_order(
            account_id=ACCOUNT_ID,
            signal_plan=plan,
            account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
            risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
            governor_decision=governor_trace,
        )


def test_position_management_signal_plan_order_sells_to_exit_long_position() -> None:
    manager = OrderManager()
    position_lineage_id = uuid4()
    plan = _signal_plan(
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.LOGICAL_EXIT,
        opening_signal_plan_id=uuid4(),
        related_position_lineage_id=position_lineage_id,
    )

    order = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
        risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
        position_side=SignalPlanSide.LONG,
    )

    assert order.intent == InternalOrderIntent.LOGICAL_EXIT
    assert order.side == CandidateSide.SHORT
    assert order.position_lineage_id == position_lineage_id


def test_position_management_signal_plan_order_buys_to_cover_short_position() -> None:
    manager = OrderManager()
    position_lineage_id = uuid4()
    plan = _signal_plan(
        side=SignalPlanSide.SHORT,
        intent=SignalPlanIntent.CLOSE,
        opening_signal_plan_id=uuid4(),
        related_position_lineage_id=position_lineage_id,
    )

    order = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
        risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
        position_side=SignalPlanSide.SHORT,
    )

    assert order.intent == InternalOrderIntent.CLOSE
    assert order.side == CandidateSide.LONG
    assert order.position_lineage_id == position_lineage_id


def test_position_management_signal_plan_order_requires_opening_lineage() -> None:
    manager = OrderManager()
    plan = _signal_plan(
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.LOGICAL_EXIT,
        related_position_lineage_id=uuid4(),
    )

    with pytest.raises(OrderManagerError, match="opening_signal_plan_id"):
        manager.create_signal_plan_order(
            account_id=ACCOUNT_ID,
            signal_plan=plan,
            account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
            risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
            governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
        )


@pytest.mark.parametrize(
    "intent",
    [
        SignalPlanIntent.CLOSE,
        SignalPlanIntent.REDUCE,
        SignalPlanIntent.TARGET,
        SignalPlanIntent.STOP,
        SignalPlanIntent.TRAIL,
        SignalPlanIntent.BREAKEVEN,
        SignalPlanIntent.RUNNER,
        SignalPlanIntent.LOGICAL_EXIT,
    ],
)
def test_all_position_management_signal_plan_intents_use_exit_side(intent: SignalPlanIntent) -> None:
    manager = OrderManager()
    plan = _signal_plan(
        side=SignalPlanSide.LONG,
        intent=intent,
        opening_signal_plan_id=uuid4(),
        related_position_lineage_id=uuid4(),
    )

    order = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=_accepted_evaluation(account_id=ACCOUNT_ID, signal_plan=plan),
        risk_result=_risk_result(account_id=ACCOUNT_ID, signal_plan=plan),
        governor_decision=_governor_trace(account_id=ACCOUNT_ID, signal_plan=plan),
    )

    assert order.side == CandidateSide.SHORT
    assert order.intent.value == intent.value


def test_updates_order_status() -> None:
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    updated = manager.update_status(order_id=order.order_id, status=InternalOrderStatus.PENDING_SUBMISSION)

    assert updated.status == InternalOrderStatus.PENDING_SUBMISSION
    assert manager.ledger.get(order.order_id).status == InternalOrderStatus.PENDING_SUBMISSION
    assert updated.updated_at >= order.updated_at


def test_supports_lookup_by_deployment_account_program() -> None:
    ledger = OrderLedger()
    manager = OrderManager(ledger=ledger)
    other_account_id = uuid4()
    other_deployment_id = uuid4()
    other_program_id = uuid4()
    first = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="SPY"))
    second = manager.create_order(
        account_id=other_account_id,
        execution_intent=_execution_intent(
            deployment_id=other_deployment_id,
            program_id=other_program_id,
            symbol="QQQ",
        ),
    )

    assert ledger.by_account(ACCOUNT_ID) == (first,)
    assert ledger.by_deployment(DEPLOYMENT_ID) == (first,)
    assert ledger.by_program(PROGRAM_ID) == (first,)
    assert ledger.by_account(other_account_id) == (second,)
    assert ledger.by_deployment(other_deployment_id) == (second,)
    assert ledger.by_program(other_program_id) == (second,)


def test_creates_close_tp_sl_and_scale_intents() -> None:
    manager = OrderManager()
    close_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(intent_type=IntentType.EXIT),
    )
    tp_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.TAKE_PROFIT,
    )
    sl_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )
    scale_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.SCALE,
    )

    assert close_order.intent == InternalOrderIntent.CLOSE
    assert tp_order.intent == InternalOrderIntent.TAKE_PROFIT
    assert sl_order.intent == InternalOrderIntent.STOP_LOSS
    assert scale_order.intent == InternalOrderIntent.SCALE
    assert "-tp-" in tp_order.client_order_id
    assert "-sl-" in sl_order.client_order_id
    assert "-scale-" in scale_order.client_order_id


def test_legacy_execution_intent_exit_sells_to_exit_long_position() -> None:
    manager = OrderManager()

    order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(intent_type=IntentType.EXIT, side=CandidateSide.LONG),
    )

    assert order.intent == InternalOrderIntent.CLOSE
    assert order.side == CandidateSide.SHORT


def test_legacy_execution_intent_exit_buys_to_cover_short_position() -> None:
    manager = OrderManager()

    order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(intent_type=IntentType.EXIT, side=CandidateSide.SHORT),
    )

    assert order.intent == InternalOrderIntent.CLOSE
    assert order.side == CandidateSide.LONG


def test_no_external_calls() -> None:
    source = inspect.getsource(order_manager_module)

    for forbidden in ["alpaca", "requests", "httpx", "websocket", "submit_order"]:
        assert forbidden not in source.lower()


def test_request_cancel_marks_open_order_without_position() -> None:
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    canceled = manager.request_cancel(order.order_id)

    assert canceled.cancel_requested_at is not None
    assert canceled.status == InternalOrderStatus.CREATED


def test_request_cancel_preserves_protective_order() -> None:
    manager = OrderManager()
    order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    skipped = manager.request_cancel(order.order_id)

    assert skipped == order
    assert manager.ledger.get(order.order_id).cancel_requested_at is None


def test_request_cancel_preserves_open_order_with_backing_position() -> None:
    class Adapter:
        def get_positions(self, account_id):
            return (
                BrokerPositionSnapshot(
                    account_id=account_id,
                    symbol="SPY",
                    quantity=10,
                    market_value=1000,
                    avg_entry_price=100,
                    side=BrokerPositionSide.LONG,
                ),
            )

    manager = OrderManager(broker_adapter=Adapter())
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    skipped = manager.request_cancel(order.order_id)

    assert skipped == order


def test_request_replace_updates_open_order_params() -> None:
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    replaced = manager.request_replace(order.order_id, {"limit_price": 101.25})

    assert replaced.limit_price == 101.25
    assert replaced.account_id == order.account_id
    assert replaced.deployment_id == order.deployment_id
    assert replaced.program_id == order.program_id
    assert replaced.intent == InternalOrderIntent.OPEN


def test_request_replace_rejects_filled_order() -> None:
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())
    manager.update_status(order_id=order.order_id, status=InternalOrderStatus.FILLED)

    with pytest.raises(OrderManagerError):
        manager.request_replace(order.order_id, {"limit_price": 101.25})


def test_deployment_cancel_scope_does_not_affect_other_deployments() -> None:
    manager = OrderManager()
    other_deployment_id = uuid4()
    target = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="SPY"))
    other = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(deployment_id=other_deployment_id, symbol="QQQ"),
    )

    canceled = manager.request_cancel_scope(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        scope="deployment",
    )

    assert canceled == (manager.ledger.get(target.order_id),)
    assert manager.ledger.get(target.order_id).cancel_requested_at is not None
    assert manager.ledger.get(other.order_id).cancel_requested_at is None


def test_account_cancel_scope_affects_all_deployments_on_account() -> None:
    manager = OrderManager()
    other_deployment_id = uuid4()
    first = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="SPY"))
    second = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(deployment_id=other_deployment_id, symbol="QQQ"),
    )

    canceled = manager.request_cancel_scope(account_id=ACCOUNT_ID, scope="account")

    assert {order.order_id for order in canceled} == {first.order_id, second.order_id}


def test_global_cancel_scope_affects_all_accounts() -> None:
    manager = OrderManager()
    other_account_id = uuid4()
    first = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="SPY"))
    second = manager.create_order(account_id=other_account_id, execution_intent=_execution_intent(symbol="QQQ"))

    canceled = manager.request_cancel_scope(account_id=ACCOUNT_ID, scope="global")

    assert {order.order_id for order in canceled} == {first.order_id, second.order_id}


# ---------------------------------------------------------------------------
# Stale broker-sync gating (Phase 2 §11.4)
# ---------------------------------------------------------------------------


class _StubBrokerSyncService:
    """Minimal duck-typed stand-in for BrokerSyncService.current_sync_state."""

    def __init__(self, *, is_stale: bool, reason: str | None = None) -> None:
        self._is_stale = is_stale
        self._reason = reason
        self.calls: list[UUID] = []

    def current_sync_state(self, account_id: UUID):
        self.calls.append(account_id)

        class _State:
            is_stale = self._is_stale
            stale_reason = self._reason

        return _State()


def test_create_order_is_blocked_when_broker_sync_is_stale() -> None:
    service = _StubBrokerSyncService(is_stale=True, reason="broker_truth_age_exceeded_30s")
    manager = OrderManager(broker_sync_service=service)

    with pytest.raises(OrderManagerError) as excinfo:
        manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert "broker_sync_stale" in str(excinfo.value)
    assert "broker_truth_age_exceeded_30s" in str(excinfo.value)
    assert service.calls == [ACCOUNT_ID]
    assert manager.ledger.all() == ()


def test_create_order_is_allowed_when_broker_sync_is_fresh() -> None:
    service = _StubBrokerSyncService(is_stale=False)
    manager = OrderManager(broker_sync_service=service)

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert order.intent == InternalOrderIntent.OPEN
    assert service.calls == [ACCOUNT_ID]


def test_stale_broker_sync_does_not_block_close_intents() -> None:
    """Closes must remain available so positions can be exited under sync loss."""
    service = _StubBrokerSyncService(is_stale=True, reason="broker_truth_age_exceeded_30s")
    manager = OrderManager(broker_sync_service=service)

    closed = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(intent_type=IntentType.EXIT),
    )

    assert closed.intent == InternalOrderIntent.CLOSE


def test_stale_broker_sync_does_not_block_protective_intents() -> None:
    service = _StubBrokerSyncService(is_stale=True, reason="broker_truth_age_exceeded_30s")
    manager = OrderManager(broker_sync_service=service)

    sl = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )
    tp = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.TAKE_PROFIT,
    )

    assert sl.intent == InternalOrderIntent.STOP_LOSS
    assert tp.intent == InternalOrderIntent.TAKE_PROFIT


def test_create_order_skips_sync_check_when_no_service_provided() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert order.intent == InternalOrderIntent.OPEN
