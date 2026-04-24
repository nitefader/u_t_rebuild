from __future__ import annotations

from uuid import uuid4

import pytest

from backend.app.domain import (
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import CandidateSide, IntentType, SignalRule
from backend.app.features import FeaturePlanError, ResolvedProgramComponents, build_feature_plan


def _components(
    *,
    strategy_feature_refs: list[str] | None = None,
    controls_feature_refs: list[str] | None = None,
    controls_regime_refs: list[str] | None = None,
    risk_feature_refs: list[str] | None = None,
    execution_feature_refs: list[str] | None = None,
) -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    condition = ConditionNode(
        left_feature="5m.close[0]",
        operator=ConditionOperator.GT,
        right_feature="5m.ema:length=20[0]",
    )
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Breakout",
        feature_refs=strategy_feature_refs or [],
        entry_rules=[
            SignalRule(
                name="entry",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=condition,
                stop_candidate_feature="5m.atr:length=14[0]",
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="Controls",
        timeframe="5m",
        feature_refs=controls_feature_refs or [],
        regime_filter_refs=controls_regime_refs or [],
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Risk",
        sizing_method=PositionSizingMethod.RISK_PERCENT_EQUITY,
        risk_per_trade_pct=0.5,
        feature_refs=risk_feature_refs or [],
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Execution",
        entry_order_type=OrderType.MARKET,
        feature_refs=execution_feature_refs or [],
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Universe",
        symbols=[UniverseSymbol(symbol="spy"), UniverseSymbol(symbol="QQQ")],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Program",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedProgramComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def test_feature_plan_deduplicates_by_feature_key() -> None:
    components = _components(
        strategy_feature_refs=["5m.close[0]", "5m.close", "5m.ema:length=20[0]"],
        controls_feature_refs=["5m.close[0]"],
        risk_feature_refs=["5m.atr:length=14[0]"],
    )

    plan = build_feature_plan(components, consumer="chart_lab")

    assert len(plan.feature_keys) == len(set(plan.feature_keys))
    close_specs = [spec for spec in plan.feature_specs if spec.kind == "close"]
    assert len(close_specs) == 1
    assert plan.symbols == ("QQQ", "SPY")


def test_feature_plan_includes_multi_timeframe_requirements() -> None:
    components = _components(
        controls_regime_refs=["1d.prior_day_high[0]"],
        execution_feature_refs=["15m.opening_range_high:session=regular,window_minutes=15"],
    )

    plan = build_feature_plan(components, consumer="sim_replay")

    assert plan.timeframes == ("15m", "1d", "5m")
    assert any(spec.timeframe == "1d" and spec.kind == "prior_day_high" for spec in plan.feature_specs)
    assert any(spec.timeframe == "15m" and spec.kind == "opening_range_high" for spec in plan.feature_specs)


def test_feature_plan_computes_warmup_by_timeframe() -> None:
    components = _components(strategy_feature_refs=["5m.ema:length=20[0]", "1d.ema:length=50[0]"])

    plan = build_feature_plan(components, consumer="backtest")

    assert plan.warmup_by_timeframe["5m"] >= 60
    assert plan.warmup_by_timeframe["1d"] >= 150


def test_feature_plan_rejects_invalid_feature() -> None:
    components = _components(risk_feature_refs=["5m.supertrend:length=10[0]"])

    with pytest.raises(FeaturePlanError):
        build_feature_plan(components, consumer="chart_lab")


def test_feature_plan_rejects_invalid_feature_param() -> None:
    components = _components(execution_feature_refs=["5m.ema:period=20[0]"])

    with pytest.raises(FeaturePlanError):
        build_feature_plan(components, consumer="chart_lab")


def test_feature_plan_rejects_invalid_timeframe() -> None:
    components = _components(controls_feature_refs=["60m.close[0]"])

    with pytest.raises(FeaturePlanError):
        build_feature_plan(components, consumer="chart_lab")
