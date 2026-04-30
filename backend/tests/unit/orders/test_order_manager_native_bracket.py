"""T-5 (Bracket Program) — OrderManager.attach_native_bracket_to_entry tests.

Covers the native broker bracket runtime path on the entry leg:

- positive child prices populated on the InternalOrder
- order_class flipped to "bracket" so BrokerAdapter (T-4) attaches
  ``OrderClass.BRACKET`` + ``TakeProfitRequest`` + ``StopLossRequest``
- doctrine guards: only OPEN entries, no children, positive prices

Reference price selection (limit-vs-market) is exercised at the
orchestrator wiring level — this file validates the OrderManager
contract only.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.decision.signal_plan_builder import post_fill_pct_rule
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
)
from backend.app.domain.signal_plan import (
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
)
from backend.app.orders import (
    InternalOrderIntent,
    OrderManager,
    OrderManagerError,
)
from backend.app.orders.models import OrderOrigin


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")


def _signal_plan(*, side: SignalPlanSide = SignalPlanSide.LONG) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        symbol="SPY",
        side=side,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY),
        stop=SignalPlanStop(type="percent", rule=post_fill_pct_rule(5.0), required=True),
        targets=(
            SignalPlanTarget(
                label="t1",
                action=SignalPlanTargetAction.CLOSE,
                quantity_pct=100,
                rule=post_fill_pct_rule(10.0),
            ),
        ),
        reason="entry",
    )


def _seed_parent_entry(manager: OrderManager, plan: SignalPlan, qty: float = 10):
    eval_ = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=plan.signal_plan_id,
        deployment_id=plan.deployment_id,
        strategy_id=plan.strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
    )
    risk = RiskResolverResult(
        account_id=ACCOUNT_ID,
        signal_plan_id=plan.signal_plan_id,
        allowed=True,
        resolved_quantity=qty,
    )
    gov = GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=plan.signal_plan_id,
        status=GovernorDecisionStatus.APPROVED,
        approved=True,
        reasons=("approved",),
    )
    return manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=eval_,
        risk_result=risk,
        governor_decision=gov,
    )


def test_attach_native_bracket_marks_order_class_and_child_prices() -> None:
    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.LONG)
    parent = _seed_parent_entry(manager, plan)

    updated = manager.attach_native_bracket_to_entry(
        order_id=parent.order_id,
        take_profit_limit_price=110.0,
        stop_loss_stop_price=95.0,
    )

    assert updated.order_class == "bracket"
    assert updated.bracket_take_profit_limit_price == pytest.approx(110.0)
    assert updated.bracket_stop_loss_stop_price == pytest.approx(95.0)
    # Identity preserved (same lineage chain, same order id).
    assert updated.order_id == parent.order_id
    assert updated.signal_plan_id == parent.signal_plan_id
    assert updated.intent == InternalOrderIntent.OPEN
    assert updated.origin == OrderOrigin.SIGNAL_PLAN


def test_attach_native_bracket_rejects_zero_or_negative_prices() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    parent = _seed_parent_entry(manager, plan)

    with pytest.raises(OrderManagerError):
        manager.attach_native_bracket_to_entry(
            order_id=parent.order_id,
            take_profit_limit_price=0.0,
            stop_loss_stop_price=95.0,
        )
    with pytest.raises(OrderManagerError):
        manager.attach_native_bracket_to_entry(
            order_id=parent.order_id,
            take_profit_limit_price=110.0,
            stop_loss_stop_price=-1.0,
        )


def test_attach_native_bracket_short_entry_supports_inverted_prices() -> None:
    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.SHORT)
    parent = _seed_parent_entry(manager, plan)

    updated = manager.attach_native_bracket_to_entry(
        order_id=parent.order_id,
        take_profit_limit_price=90.0,  # SHORT target is BELOW entry
        stop_loss_stop_price=105.0,    # SHORT stop is ABOVE entry
    )
    assert updated.order_class == "bracket"
    assert updated.bracket_take_profit_limit_price == pytest.approx(90.0)
    assert updated.bracket_stop_loss_stop_price == pytest.approx(105.0)


def test_attach_native_bracket_does_not_mutate_unrelated_fields() -> None:
    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.LONG)
    parent = _seed_parent_entry(manager, plan)

    updated = manager.attach_native_bracket_to_entry(
        order_id=parent.order_id,
        take_profit_limit_price=110.0,
        stop_loss_stop_price=95.0,
    )
    # Quantity, symbol, side, time_in_force, intent, origin, lineage stay
    # identical — native bracket only attaches the child prices and
    # flips order_class.
    assert updated.quantity == parent.quantity
    assert updated.symbol == parent.symbol
    assert updated.side == parent.side
    assert updated.time_in_force == parent.time_in_force
    assert updated.intent == parent.intent
    assert updated.origin == parent.origin
    assert updated.deployment_id == parent.deployment_id
    assert updated.strategy_id == parent.strategy_id
    assert updated.signal_plan_id == parent.signal_plan_id
    assert updated.position_lineage_id == parent.position_lineage_id
    assert updated.account_evaluation_id == parent.account_evaluation_id
    assert updated.governor_decision_id == parent.governor_decision_id


def test_attach_native_bracket_rejects_child_orders() -> None:
    """Doctrine: native bracket attaches to the ENTRY leg only.

    Children (parent_order_id != None, intent != OPEN) cannot themselves
    be marked as a bracket.
    """

    from backend.app.orders.protective_placer import ProtectiveOrderPlacer

    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.LONG)
    parent = _seed_parent_entry(manager, plan)
    placer = ProtectiveOrderPlacer()
    placement = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    children = manager.create_protective_orders_post_fill(plan=placement, parent_order=parent)
    assert children
    child = children[0]

    with pytest.raises(OrderManagerError):
        manager.attach_native_bracket_to_entry(
            order_id=child.order_id,
            take_profit_limit_price=110.0,
            stop_loss_stop_price=95.0,
        )
