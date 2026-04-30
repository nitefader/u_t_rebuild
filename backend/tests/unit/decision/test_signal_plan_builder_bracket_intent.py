"""T-3 (Bracket Program) — SignalPlanBuilder resolves ExecutionPlan bracket intent.

Acceptance from STRATEGY_TO_BROKER_BRACKET_PROGRAM.md §3 T-3:

    "with the persisted ExecutionPlan from T-1, build a SignalPlan for symbol
    AAPL side=long. SignalPlan has stop.rule='post_fill_pct:5' and
    targets[0].label='t1', targets[0].quantity_pct=100, targets[0].rule=
    'post_fill_pct:10'. Short-side SignalPlan has the same payload, side flipped."
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.app.decision import SignalPlanBuilder
from backend.app.decision.signal_plan_builder import (
    POST_FILL_PCT_RULE_PREFIX,
    parse_post_fill_pct,
    post_fill_pct_rule,
)
from backend.app.domain import (
    CandidateSide,
    CandidateTradeIntent,
    IntentType,
    SignalPlanIntent,
    SignalPlanSide,
)
from backend.app.domain.execution_style import (
    BracketRunnerPreset,
    BracketStopTargetPreset,
    ExecutionMode,
    ExecutionStylePresetKind,
    ExecutionStyleVersion,
    MultiTargetScaleOutPreset,
    MultiTargetTier,
    OrderType,
    TimeInForce,
)
from backend.app.domain.signal_plan import SignalPlanTargetAction


def _candidate(*, side: CandidateSide = CandidateSide.LONG) -> CandidateTradeIntent:
    return CandidateTradeIntent(
        timestamp=datetime.now(timezone.utc),
        symbol="aapl",
        side=side,
        intent_type=IntentType.ENTRY,
        signal_name="bracket_entry",
        feature_values_used={"5m.close[0]": 200},
    )


def _bracket_plan(*, stop_pct: float = 5.0, target_pct: float = 10.0) -> ExecutionStyleVersion:
    return ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="bracket_stop_target plan",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
        preset=BracketStopTargetPreset(
            kind=ExecutionStylePresetKind.BRACKET_STOP_TARGET,
            stop_pct=stop_pct,
            target_pct=target_pct,
        ),
    )


def test_post_fill_pct_rule_round_trips() -> None:
    encoded = post_fill_pct_rule(7.5)
    assert encoded == f"{POST_FILL_PCT_RULE_PREFIX}:7.5"
    assert parse_post_fill_pct(encoded) == 7.5


def test_parse_post_fill_pct_rejects_garbage() -> None:
    assert parse_post_fill_pct(None) is None
    assert parse_post_fill_pct("") is None
    assert parse_post_fill_pct("fixed:5") is None
    assert parse_post_fill_pct("post_fill_pct:") is None
    assert parse_post_fill_pct("post_fill_pct:abc") is None
    assert parse_post_fill_pct("post_fill_pct:-1") is None
    assert parse_post_fill_pct("post_fill_pct:0") is None


def test_long_bracket_stop_target_post_fill_intent() -> None:
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(side=CandidateSide.LONG),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        execution_plan=_bracket_plan(stop_pct=5.0, target_pct=10.0),
    )

    assert plan.symbol == "AAPL"
    assert plan.intent == SignalPlanIntent.OPEN
    assert plan.side == SignalPlanSide.LONG

    # No quantity / no concrete prices — SignalPlan stays neutral.
    assert plan.entry is not None
    assert plan.entry.stop_price is None
    assert plan.entry.limit_price is None

    assert plan.stop is not None
    assert plan.stop.type == "percent"
    assert plan.stop.required is True
    assert plan.stop.stop_price is None  # post-fill resolution
    assert plan.stop.rule == "post_fill_pct:5.0"
    assert parse_post_fill_pct(plan.stop.rule) == 5.0

    assert len(plan.targets) == 1
    target = plan.targets[0]
    assert target.label == "t1"
    assert target.quantity_pct == 100
    assert target.action == SignalPlanTargetAction.CLOSE
    assert target.price is None
    assert target.rule == "post_fill_pct:10.0"
    assert parse_post_fill_pct(target.rule) == 10.0


def test_short_bracket_stop_target_has_same_payload_with_side_flipped() -> None:
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(side=CandidateSide.SHORT),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        execution_plan=_bracket_plan(stop_pct=5.0, target_pct=10.0),
    )

    assert plan.side == SignalPlanSide.SHORT
    assert plan.stop is not None
    assert plan.stop.rule == "post_fill_pct:5.0"
    assert plan.targets[0].rule == "post_fill_pct:10.0"
    # symmetry: long and short carry the same percent intent; side direction
    # is the only difference. Concrete prices flip at fill resolution.


def test_bracket_runner_preset_emits_trail_stop_and_first_target() -> None:
    runner_plan = ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="runner",
        entry_order_type=OrderType.MARKET,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
        preset=BracketRunnerPreset(
            kind=ExecutionStylePresetKind.BRACKET_RUNNER,
            first_target_pct=2.0,
            first_slice_pct=0.5,
            trail_pct=1.5,
        ),
    )
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        execution_plan=runner_plan,
    )

    assert plan.stop is not None
    assert plan.stop.type == "trail"
    assert parse_post_fill_pct(plan.stop.rule) == 1.5

    assert len(plan.targets) == 1
    assert plan.targets[0].label == "t1"
    assert plan.targets[0].action == SignalPlanTargetAction.REDUCE
    assert plan.targets[0].quantity_pct == 50.0
    assert parse_post_fill_pct(plan.targets[0].rule) == 2.0


def test_multi_target_scale_out_preset_emits_one_target_per_tier() -> None:
    multi_plan = ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="multi",
        entry_order_type=OrderType.MARKET,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
        preset=MultiTargetScaleOutPreset(
            kind=ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT,
            targets=(
                MultiTargetTier(target_pct=1.0, slice_pct=0.25),
                MultiTargetTier(target_pct=2.0, slice_pct=0.25),
                MultiTargetTier(target_pct=4.0, slice_pct=0.25),
            ),
            stop_pct=2.0,
        ),
    )
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        execution_plan=multi_plan,
    )

    assert plan.stop is not None
    assert parse_post_fill_pct(plan.stop.rule) == 2.0

    assert len(plan.targets) == 3
    assert [t.label for t in plan.targets] == ["t1", "t2", "t3"]
    assert all(t.quantity_pct == 25.0 for t in plan.targets)
    assert [parse_post_fill_pct(t.rule) for t in plan.targets] == [1.0, 2.0, 4.0]


def test_market_entry_market_exit_preset_emits_no_bracket_legs() -> None:
    plain_plan = ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="plain",
        entry_order_type=OrderType.MARKET,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
        preset=None,
    )
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        execution_plan=plain_plan,
    )
    # Without a preset and without candidate stop/target, SignalPlan has no legs.
    assert plan.stop is None
    assert plan.targets == ()


def test_signal_plan_remains_quantity_free_with_bracket_intent() -> None:
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        execution_plan=_bracket_plan(),
    )
    # Doctrine guard: SignalPlan must not contain account-execution fields.
    payload = plan.model_dump()
    forbidden = {"account_id", "qty", "quantity", "shares", "notional", "resolved_quantity"}
    assert not (forbidden & payload.keys())


def test_legacy_candidate_path_still_used_when_no_execution_plan() -> None:
    """Backwards-compat: candidate.stop_candidate/target_candidate path is preserved."""

    candidate = CandidateTradeIntent(
        timestamp=datetime.now(timezone.utc),
        symbol="spy",
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        signal_name="legacy",
        feature_values_used={},
        stop_candidate=495.0,
        target_candidate=510.0,
    )
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=candidate,
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
    )
    assert plan.stop is not None
    assert plan.stop.type == "fixed"
    assert plan.stop.stop_price == 495.0
    assert plan.targets[0].price == 510.0
