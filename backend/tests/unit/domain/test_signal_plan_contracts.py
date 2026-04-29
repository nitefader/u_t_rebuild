from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain import (
    AccountSignalPlanEvaluation,
    AccountEvaluationStatus,
    AccountParticipationDecision,
    ConditionNode,
    ConditionOperator,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    LogicalExitRule,
    LogicalExitRuleKind,
    OrderType,
    PositionExplanationContext,
    RiskResolvedLegAllocation,
    RiskResolverResult,
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanLogicalExit,
    SignalPlanLogicalExitScope,
    SignalPlanRunner,
    SignalPlanRunnerManagement,
    SignalPlanSide,
    SignalPlanStatus,
    SignalPlanTarget,
    SignalPlanTargetAction,
    TimeInForce,
)


def _ids() -> dict[str, object]:
    return {
        "signal_plan_id": uuid4(),
        "deployment_id": uuid4(),
        "strategy_id": uuid4(),
        "strategy_version_id": uuid4(),
    }


def test_open_signal_plan_is_neutral_and_supports_multileg_lifecycle() -> None:
    plan = SignalPlan(
        **_ids(),
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(
            order_type=OrderType.LIMIT,
            limit_price=500,
            time_in_force_preference=TimeInForce.DAY,
        ),
        targets=(
            SignalPlanTarget(label="T1", action=SignalPlanTargetAction.REDUCE, quantity_pct=25, price=505),
            SignalPlanTarget(label="T2", action=SignalPlanTargetAction.REDUCE, quantity_pct=25, price=510),
        ),
        runner=SignalPlanRunner(quantity_pct=50, management=SignalPlanRunnerManagement.TRAIL, trail_rule="atr_2x"),
    )

    assert plan.intent == SignalPlanIntent.OPEN
    assert plan.entry is not None
    assert plan.entry.limit_price == 500
    assert sum(target.quantity_pct for target in plan.targets) + plan.runner.quantity_pct == 100
    assert not hasattr(plan, "account_id")
    assert not hasattr(plan, "quantity")


def test_signal_plan_status_is_not_account_specific() -> None:
    account_specific_statuses = {"accepted_by_account", "rejected_by_account", "blocked_by_account"}

    assert account_specific_statuses.isdisjoint({status.value for status in SignalPlanStatus})


@pytest.mark.parametrize("field_name", ["account_id", "qty", "quantity", "notional", "order_id", "governor_approved"])
def test_signal_plan_rejects_account_execution_fields(field_name: str) -> None:
    payload = {
        **_ids(),
        "symbol": "SPY",
        "side": SignalPlanSide.LONG,
        "intent": SignalPlanIntent.OPEN,
        field_name: uuid4() if field_name.endswith("id") else 1,
    }

    with pytest.raises(ValidationError):
        SignalPlan(**payload)


def test_position_management_signal_plan_requires_lineage() -> None:
    with pytest.raises(ValidationError):
        SignalPlan(
            **_ids(),
            symbol="SPY",
            side=SignalPlanSide.LONG,
            intent=SignalPlanIntent.REDUCE,
        )


def test_position_management_signal_plan_can_reference_opening_signal_plan() -> None:
    plan = SignalPlan(
        **_ids(),
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.LOGICAL_EXIT,
        opening_signal_plan_id=uuid4(),
        logical_exit=SignalPlanLogicalExit(
            rule=LogicalExitRule(
                kind=LogicalExitRuleKind.FEATURE_CONDITION,
                feature_condition=ConditionNode(
                    left_feature="5m.RSI_21[0]",
                    operator=ConditionOperator.CROSS_ABOVE,
                    right_feature="15m.RSI_21[0]",
                ),
                label="RSI cross",
            ),
            action=SignalPlanTargetAction.CLOSE,
            applies_to=SignalPlanLogicalExitScope.REMAINING_QUANTITY,
        ),
    )

    assert plan.logical_exit is not None
    assert plan.logical_exit.action == SignalPlanTargetAction.CLOSE


def test_target_and_runner_percentages_cannot_exceed_full_position() -> None:
    with pytest.raises(ValidationError):
        SignalPlan(
            **_ids(),
            symbol="SPY",
            side=SignalPlanSide.LONG,
            intent=SignalPlanIntent.OPEN,
            targets=(SignalPlanTarget(label="T1", quantity_pct=80),),
            runner=SignalPlanRunner(quantity_pct=30),
        )


def test_target_labels_must_be_unique_and_not_conflict_with_lifecycle_legs() -> None:
    with pytest.raises(ValidationError, match="target labels must be unique"):
        SignalPlan(
            **_ids(),
            symbol="SPY",
            side=SignalPlanSide.LONG,
            intent=SignalPlanIntent.OPEN,
            targets=(
                SignalPlanTarget(label="T1", quantity_pct=25),
                SignalPlanTarget(label="t1", quantity_pct=25),
            ),
        )

    with pytest.raises(ValidationError, match="reserved lifecycle labels"):
        SignalPlan(
            **_ids(),
            symbol="SPY",
            side=SignalPlanSide.LONG,
            intent=SignalPlanIntent.OPEN,
            targets=(SignalPlanTarget(label="runner", quantity_pct=25),),
        )


def test_risk_resolver_is_first_contract_with_final_quantity() -> None:
    result = RiskResolverResult(
        account_id=uuid4(),
        signal_plan_id=uuid4(),
        allowed=True,
        resolved_quantity=12,
        max_loss=50,
    )

    assert result.resolved_quantity == 12


def test_risk_result_can_carry_account_specific_leg_allocations() -> None:
    result = RiskResolverResult(
        account_id=uuid4(),
        signal_plan_id=uuid4(),
        allowed=True,
        resolved_quantity=100,
        leg_allocations=(
            RiskResolvedLegAllocation(
                leg_label="entry",
                lifecycle_intent=SignalPlanIntent.OPEN,
                resolved_quantity=100,
                quantity_pct=100,
            ),
            RiskResolvedLegAllocation(
                leg_label="T1",
                lifecycle_intent=SignalPlanIntent.TARGET,
                resolved_quantity=25,
                quantity_pct=25,
            ),
        ),
        fractional_quantity_allowed=False,
        quantity_rounding_policy="floor_targets_remainder_to_runner",
    )

    assert result.leg_allocations[1].leg_label == "T1"
    assert result.leg_allocations[1].resolved_quantity == 25


def test_allowed_risk_result_requires_size() -> None:
    with pytest.raises(ValidationError):
        RiskResolverResult(account_id=uuid4(), signal_plan_id=uuid4(), allowed=True)


def test_account_evaluation_can_carry_risk_and_governor_decision() -> None:
    account_id = uuid4()
    signal_plan_id = uuid4()
    risk = RiskResolverResult(account_id=account_id, signal_plan_id=signal_plan_id, allowed=True, resolved_quantity=5)
    decision = GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan_id,
        status=GovernorDecisionStatus.APPROVED,
        approved=True,
    )

    evaluation = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan_id,
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
        risk_resolver_result=risk,
        governor_decision=decision,
    )

    assert evaluation.risk_resolver_result == risk
    assert evaluation.governor_decision == decision


def test_position_explanation_context_links_signal_plan_to_orders_and_fills() -> None:
    context = PositionExplanationContext(
        account_id=uuid4(),
        position_lineage_id=uuid4(),
        symbol="SPY",
        side=SignalPlanSide.LONG,
        current_quantity=10,
        opening_signal_plan_id=uuid4(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        order_ids=(uuid4(),),
        fill_ids=(uuid4(),),
    )

    assert context.current_quantity == 10
    assert context.order_ids
