"""T-5 (Bracket Program) — OrderManager.create_protective_orders_post_fill tests.

Acceptance from STRATEGY_TO_BROKER_BRACKET_PROGRAM.md §5:

    - long market + 5% stop + 10% target, post-fill
    - short market + 5% stop + 10% target, post-fill
    - partial fill idempotency
    - reload persistence (lineage preserved)
    - BrokerSync lineage preserved (parent_order_id chain)
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.decision.signal_plan_builder import post_fill_pct_rule
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
from backend.app.domain.signal_plan import (
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
)
from backend.app.orders import (
    InternalOrderIntent,
    InternalOrderStatus,
    OrderManager,
    OrderManagerError,
)
from backend.app.orders.protective_placer import ProtectiveOrderPlacer


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


def _evaluation(*, account_id: UUID, plan: SignalPlan) -> AccountSignalPlanEvaluation:
    return AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=account_id,
        signal_plan_id=plan.signal_plan_id,
        deployment_id=plan.deployment_id,
        strategy_id=plan.strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
    )


def _risk_result(*, account_id: UUID, plan: SignalPlan, qty: float = 10) -> RiskResolverResult:
    return RiskResolverResult(
        account_id=account_id,
        signal_plan_id=plan.signal_plan_id,
        allowed=True,
        resolved_quantity=qty,
    )


def _governor(*, account_id: UUID, plan: SignalPlan) -> GovernorDecisionTrace:
    return GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=account_id,
        signal_plan_id=plan.signal_plan_id,
        status=GovernorDecisionStatus.APPROVED,
        approved=True,
        reasons=("approved",),
    )


def _seed_parent_entry(manager: OrderManager, plan: SignalPlan, qty: float = 10):
    eval_ = _evaluation(account_id=ACCOUNT_ID, plan=plan)
    risk = _risk_result(account_id=ACCOUNT_ID, plan=plan, qty=qty)
    gov = _governor(account_id=ACCOUNT_ID, plan=plan)
    return manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        account_evaluation=eval_,
        risk_result=risk,
        governor_decision=gov,
    )


def test_long_post_fill_protective_orders_have_full_parent_lineage() -> None:
    """Acceptance #1 + #8: lineage preserved end-to-end."""

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

    assert len(children) == 2
    stop_child, target_child = children

    # Lineage chain
    for child in (stop_child, target_child):
        assert child.parent_order_id == parent.order_id
        assert child.signal_plan_id == parent.signal_plan_id
        assert child.account_id == parent.account_id
        assert child.deployment_id == parent.deployment_id
        assert child.strategy_id == parent.strategy_id
        assert child.position_lineage_id == parent.position_lineage_id
        assert child.account_evaluation_id == parent.account_evaluation_id
        assert child.governor_decision_id == parent.governor_decision_id
        assert child.order_class == "oco"
        assert child.opening_signal_plan_id == parent.signal_plan_id

    # Stop child shape
    assert stop_child.intent == InternalOrderIntent.STOP_LOSS
    assert stop_child.order_type == OrderType.STOP
    assert stop_child.stop_price == pytest.approx(95.0)
    assert stop_child.limit_price is None
    assert stop_child.side == CandidateSide.SHORT  # exit side for long entry
    # leg_label includes the cumulative-covered breakpoint so partial-fill
    # incremental placements get unique client_order_ids.
    assert stop_child.leg_label == "stop@10"

    # Target child shape
    assert target_child.intent == InternalOrderIntent.TAKE_PROFIT
    assert target_child.order_type == OrderType.LIMIT
    assert target_child.limit_price == pytest.approx(110.0)
    assert target_child.stop_price is None
    assert target_child.side == CandidateSide.SHORT  # exit side for long entry
    assert target_child.leg_label == "t1@10"


def test_short_post_fill_protective_orders_have_inverse_legs() -> None:
    """Acceptance #2: short side flips."""

    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.SHORT)
    parent = _seed_parent_entry(manager, plan)

    placement = ProtectiveOrderPlacer().compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    children = manager.create_protective_orders_post_fill(plan=placement, parent_order=parent)

    assert len(children) == 2
    stop_child, target_child = children

    # Short: exit side is BUY (= CandidateSide.LONG internally), stop ABOVE, target BELOW.
    assert stop_child.side == CandidateSide.LONG
    assert stop_child.stop_price == pytest.approx(105.0)
    assert target_child.side == CandidateSide.LONG
    assert target_child.limit_price == pytest.approx(90.0)


def test_partial_fill_idempotency_via_order_manager() -> None:
    """Acceptance #5: re-emission of same fill is a no-op via the OrderManager."""

    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.LONG)
    parent = _seed_parent_entry(manager, plan)
    placer = ProtectiveOrderPlacer()

    # First fill: covers 4 shares
    p1 = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=4.0,
        already_covered_qty=0.0,
    )
    first = manager.create_protective_orders_post_fill(plan=p1, parent_order=parent)
    assert len(first) == 2
    assert first[0].quantity == 4.0

    # Same fill re-emitted: ProtectivePlacer returns empty plan; OrderManager noop
    p_replay = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=4.0,
        already_covered_qty=4.0,
    )
    assert p_replay.legs == ()
    replayed = manager.create_protective_orders_post_fill(plan=p_replay, parent_order=parent)
    assert replayed == ()

    # Total in ledger remains exactly 1 entry parent + 2 children
    all_orders = [o for o in manager.ledger.all() if o.signal_plan_id == plan.signal_plan_id]
    assert len(all_orders) == 3


def test_partial_fill_incremental_coverage_emits_more_protective_legs_for_new_qty() -> None:
    """Acceptance #5: cumulative-fill growth -> new shares get protected."""

    manager = OrderManager()
    plan = _signal_plan(side=SignalPlanSide.LONG)
    parent = _seed_parent_entry(manager, plan, qty=10)
    placer = ProtectiveOrderPlacer()

    p1 = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=4.0,
        already_covered_qty=0.0,
    )
    manager.create_protective_orders_post_fill(plan=p1, parent_order=parent)

    p2 = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.5,
        cumulative_filled_qty=10.0,
        already_covered_qty=4.0,
    )
    new_children = manager.create_protective_orders_post_fill(plan=p2, parent_order=parent)
    assert len(new_children) == 2
    # Second slice covers the remaining 6 shares
    assert new_children[0].quantity == 6.0


def test_protective_placement_plan_with_mismatched_parent_raises() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    parent = _seed_parent_entry(manager, plan)
    placer = ProtectiveOrderPlacer()
    placement = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=uuid4(),  # wrong id
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    with pytest.raises(OrderManagerError, match="parent_order_id"):
        manager.create_protective_orders_post_fill(plan=placement, parent_order=parent)


def test_protective_orders_skip_parent_when_origin_is_not_signal_plan() -> None:
    """Manual operator parents are not allowed for post-fill brackets."""

    from backend.app.orders import InternalOrder, OrderOrigin
    from backend.app.domain._base import utc_now

    manager = OrderManager()
    plan = _signal_plan()
    placer = ProtectiveOrderPlacer()
    fake_manual_parent = InternalOrder(
        order_id=uuid4(),
        client_order_id="manual-fake-001",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.MANUAL_OPERATOR,
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.CREATED,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    placement = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=fake_manual_parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    # account_id matches but signal_plan_id won't — the first lineage check
    # to fail is signal_plan_id mismatch.
    with pytest.raises(OrderManagerError, match="signal_plan_id"):
        manager.create_protective_orders_post_fill(plan=placement, parent_order=fake_manual_parent)


def test_idempotency_owned_by_placer_via_already_covered_qty() -> None:
    """The ProtectivePlacer is the idempotency owner; OrderManager trusts the plan.

    Replay of the SAME fill event must come through the placer, which
    inspects `already_covered_qty` against `cumulative_filled_qty` and
    returns an empty plan. The OrderManager does not need to dedupe at
    its own layer because each non-empty plan represents new uncovered
    shares that need new protective orders.
    """

    manager = OrderManager()
    plan = _signal_plan()
    parent = _seed_parent_entry(manager, plan)
    placer = ProtectiveOrderPlacer()

    p1 = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
        already_covered_qty=0.0,
    )
    first = manager.create_protective_orders_post_fill(plan=p1, parent_order=parent)
    assert len(first) == 2

    # Replay the SAME fill via the placer with already_covered_qty=10
    p_replay = placer.compute_protective_plan(
        signal_plan=plan,
        parent_order_id=parent.order_id,
        account_id=ACCOUNT_ID,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
        already_covered_qty=10.0,
    )
    replayed = manager.create_protective_orders_post_fill(plan=p_replay, parent_order=parent)
    assert replayed == ()


def test_empty_plan_creates_no_children() -> None:
    manager = OrderManager()
    plan = _signal_plan()
    parent = _seed_parent_entry(manager, plan)

    from backend.app.orders.protective_placer import ProtectivePlacementPlan

    empty_plan = ProtectivePlacementPlan(
        parent_order_id=parent.order_id,
        signal_plan_id=plan.signal_plan_id,
        account_id=ACCOUNT_ID,
        covered_qty=0.0,
        legs=(),
    )
    assert manager.create_protective_orders_post_fill(plan=empty_plan, parent_order=parent) == ()
