from __future__ import annotations

from uuid import UUID, uuid4

from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    CandidateSide,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    OrderType,
    RiskResolverResult,
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanSide,
    TimeInForce,
)
from backend.app.orders import InternalOrder, InternalOrderIntent, OrderManager


DEFAULT_STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
DEFAULT_STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")


def make_signal_plan(
    *,
    deployment_id: UUID,
    symbol: str = "SPY",
    side: SignalPlanSide | CandidateSide | str = SignalPlanSide.LONG,
    intent: SignalPlanIntent = SignalPlanIntent.OPEN,
    strategy_id: UUID = DEFAULT_STRATEGY_ID,
    strategy_version_id: UUID = DEFAULT_STRATEGY_VERSION_ID,
    signal_plan_id: UUID | None = None,
    opening_signal_plan_id: UUID | None = None,
    related_position_lineage_id: UUID | None = None,
) -> SignalPlan:
    normalized_side = side.value if isinstance(side, CandidateSide | SignalPlanSide) else str(side)
    if intent != SignalPlanIntent.OPEN and opening_signal_plan_id is None and related_position_lineage_id is None:
        opening_signal_plan_id = uuid4()
        related_position_lineage_id = opening_signal_plan_id
    return SignalPlan(
        signal_plan_id=signal_plan_id or uuid4(),
        deployment_id=deployment_id,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        symbol=symbol.upper(),
        side=SignalPlanSide(normalized_side),
        intent=intent,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY)
        if intent == SignalPlanIntent.OPEN
        else None,
        opening_signal_plan_id=opening_signal_plan_id,
        related_position_lineage_id=related_position_lineage_id,
        reason="signal_condition_true",
    )


def make_account_evaluation(*, account_id: UUID, signal_plan: SignalPlan) -> AccountSignalPlanEvaluation:
    return AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        deployment_id=signal_plan.deployment_id,
        strategy_id=signal_plan.strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
    )


def make_risk_result(
    *,
    account_id: UUID,
    signal_plan: SignalPlan,
    quantity: float = 10,
) -> RiskResolverResult:
    return RiskResolverResult(
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        allowed=True,
        resolved_quantity=quantity,
    )


def make_governor_trace(*, account_id: UUID, signal_plan: SignalPlan) -> GovernorDecisionTrace:
    return GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        status=GovernorDecisionStatus.APPROVED,
        approved=True,
        reasons=("approved",),
    )


def make_signal_plan_order(
    manager: OrderManager,
    *,
    account_id: UUID,
    deployment_id: UUID,
    symbol: str = "SPY",
    side: SignalPlanSide | CandidateSide | str = SignalPlanSide.LONG,
    intent: SignalPlanIntent = SignalPlanIntent.OPEN,
    quantity: float = 10,
    strategy_id: UUID = DEFAULT_STRATEGY_ID,
    strategy_version_id: UUID = DEFAULT_STRATEGY_VERSION_ID,
    signal_plan_id: UUID | None = None,
    opening_signal_plan_id: UUID | None = None,
    position_lineage_id: UUID | None = None,
    order_intent: InternalOrderIntent | str | None = None,
    leg_label: str | None = None,
) -> InternalOrder:
    plan = make_signal_plan(
        deployment_id=deployment_id,
        symbol=symbol,
        side=side,
        intent=intent,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        signal_plan_id=signal_plan_id,
        opening_signal_plan_id=opening_signal_plan_id,
        related_position_lineage_id=position_lineage_id,
    )
    return manager.create_signal_plan_order(
        account_id=account_id,
        signal_plan=plan,
        account_evaluation=make_account_evaluation(account_id=account_id, signal_plan=plan),
        risk_result=make_risk_result(account_id=account_id, signal_plan=plan, quantity=quantity),
        governor_decision=make_governor_trace(account_id=account_id, signal_plan=plan),
        order_intent=order_intent,
        position_side=side,
        leg_label=leg_label,
    )
