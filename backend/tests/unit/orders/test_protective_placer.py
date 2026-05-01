"""T-4 (Bracket Program) — ProtectiveOrderPlacer tests.

Acceptance matrix from STRATEGY_TO_BROKER_BRACKET_PROGRAM.md §5:

    1. Long market + 5% stop + 10% target, post-fill
    2. Short market + 5% stop + 10% target, post-fill
    5. Partial fill idempotency
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.app.decision.signal_plan_builder import post_fill_pct_rule
from backend.app.domain.signal_plan import (
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanSide,
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
)
from backend.app.orders.protective_placer import (
    ProtectiveOrderPlacer,
    ProtectiveOrderPlacerError,
)


def _open_signal_plan(
    *,
    side: SignalPlanSide,
    stop_pct: float | None = 5.0,
    target_pct: float | None = 10.0,
    target_quantity_pct: float = 100.0,
    stop_rule: str | None = None,
    target_rule: str | None = None,
    feature_snapshot: dict[str, float] | None = None,
) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        symbol="AAPL",
        side=side,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(),
        stop=SignalPlanStop(
            type="percent",
            rule=stop_rule or post_fill_pct_rule(stop_pct),
            required=True,
        ) if stop_pct is not None else None,
        targets=tuple(
            [
                SignalPlanTarget(
                    label="t1",
                    action=SignalPlanTargetAction.CLOSE,
                    quantity_pct=target_quantity_pct,
                    rule=target_rule or post_fill_pct_rule(target_pct),
                )
            ]
            if target_pct is not None
            else []
        ),
        created_at=datetime.now(timezone.utc),
        feature_snapshot=feature_snapshot or {},
    )


def test_long_market_5pct_stop_10pct_target_post_fill_concrete_prices() -> None:
    """Acceptance #1: long, 5% stop, 10% target, fill at $100."""

    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG, stop_pct=5.0, target_pct=10.0)
    parent_id = uuid4()
    placer = ProtectiveOrderPlacer()

    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=parent_id,
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )

    assert plan.parent_order_id == parent_id
    assert plan.covered_qty == 10.0
    assert len(plan.legs) == 2

    stop_leg = plan.legs[0]
    assert stop_leg.label == "stop"
    assert stop_leg.side == "sell"  # exit side for long
    assert stop_leg.stop_price == pytest.approx(95.0)  # 100 * (1 - 0.05)
    assert stop_leg.limit_price is None
    assert stop_leg.quantity == 10.0

    target_leg = plan.legs[1]
    assert target_leg.label == "t1"
    assert target_leg.side == "sell"
    assert target_leg.limit_price == pytest.approx(110.0)  # 100 * (1 + 0.10)
    assert target_leg.stop_price is None
    assert target_leg.quantity == 10.0


def test_short_market_5pct_stop_10pct_target_post_fill_concrete_prices() -> None:
    """Acceptance #2: short, 5% stop, 10% target, fill at $100."""

    signal_plan = _open_signal_plan(side=SignalPlanSide.SHORT, stop_pct=5.0, target_pct=10.0)
    placer = ProtectiveOrderPlacer()

    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )

    assert len(plan.legs) == 2
    stop_leg = plan.legs[0]
    target_leg = plan.legs[1]

    # Short: exit side is BUY; stop is ABOVE fill, target is BELOW fill.
    assert stop_leg.side == "buy"
    assert stop_leg.stop_price == pytest.approx(105.0)  # 100 * (1 + 0.05)
    assert target_leg.side == "buy"
    assert target_leg.limit_price == pytest.approx(90.0)  # 100 * (1 - 0.10)


def test_long_atr_stop_and_target_post_fill_concrete_prices() -> None:
    signal_plan = _open_signal_plan(
        side=SignalPlanSide.LONG,
        stop_rule="atr:2.0",
        target_rule="atr:4.0",
        feature_snapshot={"atr:length=14[0]": 1.25},
    )

    plan = ProtectiveOrderPlacer().compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=3.0,
    )

    assert len(plan.legs) == 2
    assert plan.legs[0].side == "sell"
    assert plan.legs[0].stop_price == pytest.approx(97.5)
    assert plan.legs[1].side == "sell"
    assert plan.legs[1].limit_price == pytest.approx(105.0)


def test_atr_rules_without_atr_snapshot_emit_no_legs() -> None:
    signal_plan = _open_signal_plan(
        side=SignalPlanSide.LONG,
        stop_rule="atr:2.0",
        target_rule="atr:4.0",
    )

    plan = ProtectiveOrderPlacer().compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=3.0,
    )

    assert plan.legs == ()


def test_partial_fill_idempotency_same_event_no_double_placement() -> None:
    """Acceptance #5a: same fill event re-emitted produces a no-op plan."""

    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG)
    placer = ProtectiveOrderPlacer()

    plan_first = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
        already_covered_qty=0.0,
    )
    assert len(plan_first.legs) == 2
    assert plan_first.covered_qty == 10.0

    plan_replay = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=plan_first.parent_order_id,
        account_id=plan_first.account_id,
        fill_price=100.0,
        cumulative_filled_qty=10.0,
        already_covered_qty=10.0,
    )
    assert plan_replay.legs == ()
    assert plan_replay.covered_qty == 0.0


def test_partial_fill_incremental_coverage_only_uncovered_qty() -> None:
    """Acceptance #5b: cumulative fill grows -> incremental protection on the new shares."""

    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG)
    placer = ProtectiveOrderPlacer()

    plan_partial = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=4.0,
        already_covered_qty=0.0,
    )
    assert len(plan_partial.legs) == 2
    assert plan_partial.covered_qty == 4.0
    assert plan_partial.legs[0].quantity == 4.0

    plan_remainder = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=plan_partial.parent_order_id,
        account_id=plan_partial.account_id,
        fill_price=100.5,
        cumulative_filled_qty=10.0,
        already_covered_qty=4.0,
    )
    assert len(plan_remainder.legs) == 2
    assert plan_remainder.covered_qty == 6.0
    assert plan_remainder.legs[0].quantity == 6.0
    # New average fill price drives new protective prices for the new slice.
    assert plan_remainder.legs[0].stop_price == pytest.approx(100.5 * 0.95)


def test_signal_plan_without_stop_or_target_produces_no_legs() -> None:
    signal_plan = _open_signal_plan(
        side=SignalPlanSide.LONG, stop_pct=None, target_pct=None
    )
    placer = ProtectiveOrderPlacer()
    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    assert plan.legs == ()


def test_signal_plan_with_only_stop_emits_only_stop_leg() -> None:
    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG, target_pct=None)
    placer = ProtectiveOrderPlacer()
    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    assert len(plan.legs) == 1
    assert plan.legs[0].label == "stop"


def test_signal_plan_with_only_target_emits_only_target_leg() -> None:
    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG, stop_pct=None)
    placer = ProtectiveOrderPlacer()
    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    assert len(plan.legs) == 1
    assert plan.legs[0].label == "t1"


def test_target_quantity_is_proportional_to_target_quantity_pct() -> None:
    """Multi-target preset slices: each target gets its share of the new uncovered qty."""

    signal_plan = _open_signal_plan(
        side=SignalPlanSide.LONG, target_quantity_pct=50.0
    )
    placer = ProtectiveOrderPlacer()
    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    target_leg = next(leg for leg in plan.legs if leg.label == "t1")
    assert target_leg.quantity == pytest.approx(5.0)


def test_close_intent_signal_plan_produces_no_legs() -> None:
    """Doctrine: only OPEN-intent signal plans need post-fill bracket protection."""

    placer = ProtectiveOrderPlacer()
    close_plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        symbol="AAPL",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.CLOSE,
        related_position_lineage_id=uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    plan = placer.compute_protective_plan(
        signal_plan=close_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    assert plan.legs == ()


def test_zero_or_negative_fill_price_raises() -> None:
    placer = ProtectiveOrderPlacer()
    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG)
    with pytest.raises(ProtectiveOrderPlacerError, match="fill_price"):
        placer.compute_protective_plan(
            signal_plan=signal_plan,
            parent_order_id=uuid4(),
            account_id=uuid4(),
            fill_price=0.0,
            cumulative_filled_qty=10.0,
        )


def test_already_covered_greater_than_cumulative_is_noop_not_error() -> None:
    """Reordered events shouldn't crash; they just produce a no-op plan."""

    placer = ProtectiveOrderPlacer()
    signal_plan = _open_signal_plan(side=SignalPlanSide.LONG)
    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=5.0,
        already_covered_qty=10.0,
    )
    assert plan.legs == ()


def test_concrete_price_signal_plan_legs_do_not_emit_post_fill_bracket() -> None:
    """When SignalPlan.stop has a concrete stop_price (legacy path) and no
    post_fill_pct rule, the placer emits no legs. A different component
    (the existing stop/target leg flow in OrderManager) handles those.
    """

    placer = ProtectiveOrderPlacer()
    signal_plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        symbol="AAPL",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(),
        stop=SignalPlanStop(type="fixed", stop_price=95.0, required=True),
        targets=(
            SignalPlanTarget(
                label="t1",
                action=SignalPlanTargetAction.CLOSE,
                quantity_pct=100,
                price=110.0,
            ),
        ),
        created_at=datetime.now(timezone.utc),
    )
    plan = placer.compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=uuid4(),
        fill_price=100.0,
        cumulative_filled_qty=10.0,
    )
    assert plan.legs == ()
