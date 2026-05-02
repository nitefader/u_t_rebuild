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
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import FeaturePlanError, ResolvedDeploymentComponents, build_feature_plan


def _components(
    *,
    strategy_feature_refs: list[str] | None = None,
    controls_feature_refs: list[str] | None = None,
    controls_regime_refs: list[str] | None = None,
    risk_feature_refs: list[str] | None = None,
    execution_feature_refs: list[str] | None = None,
) -> ResolvedDeploymentComponents:
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
    return ResolvedDeploymentComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _v4_components() -> ResolvedDeploymentComponents:
    components = _components()
    strategy_v4 = StrategyVersionV4(
        version=1,
        name="V4 ATR",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(expression_text="1m.close < 1m.open")
        ),
        stops=(
            StrategyStopV4(
                mode="simple",
                scope="all",
                simple_type="ATR",
                simple_value=2.0,
            ),
        ),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="ATR",
                target_value=4.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        feature_requirements=("1m.close", "1m.open", "atr:length=14[0]"),
    )
    return components.model_copy(
        update={
            "strategy": None,
            "strategy_version_v4": strategy_v4,
        }
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


def test_feature_plan_serializes_immutable_feature_params_to_json() -> None:
    components = _components(strategy_feature_refs=["5m.ema:length=20[0]"])

    plan = build_feature_plan(components, consumer="chart_lab")

    payload = plan.model_dump(mode="json")
    ema_spec = next(spec for spec in payload["feature_specs"] if spec["kind"] == "ema")
    assert ema_spec["params"] == {"length": 20}
    assert '"params":{"length":20}' in plan.model_dump_json()


def test_feature_plan_defaults_bare_bar_refs_to_strategy_controls_timeframe() -> None:
    components = _components(strategy_feature_refs=["close", "open"])

    plan = build_feature_plan(components, consumer="backtest")

    specs = {(spec.timeframe, spec.kind) for spec in plan.feature_specs}
    assert ("5m", "close") in specs
    assert ("5m", "open") in specs


def test_v4_atr_stop_and_target_use_declared_deployment_timeframe_atr_requirement() -> None:
    plan = build_feature_plan(_v4_components(), consumer="runtime")

    specs = {(spec.timeframe, spec.kind) for spec in plan.feature_specs}
    assert ("5m", "atr") in specs


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
    components = _components(risk_feature_refs=["5m.bollinger_bands:length=10[0]"])

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


# ---------------------------------------------------------------------------
# data_requirements (Phase 1 §11 deliverable 1)
# ---------------------------------------------------------------------------


def test_feature_plan_exposes_one_data_requirement_per_feature_key() -> None:
    components = _components(
        strategy_feature_refs=["5m.close[0]", "5m.ema:length=20[0]"],
        controls_regime_refs=["1d.prior_day_high[0]"],
    )

    plan = build_feature_plan(components, consumer="sim_replay")

    assert len(plan.data_requirements) == len(plan.feature_keys)
    assert {req.feature_key for req in plan.data_requirements} == set(plan.feature_keys)


def test_data_requirements_match_per_feature_key_timeframe() -> None:
    components = _components(
        strategy_feature_refs=["5m.close[0]"],
        controls_regime_refs=["1d.prior_day_high[0]"],
    )

    plan = build_feature_plan(components, consumer="sim_replay")
    by_kind_timeframe = {(spec.kind, spec.timeframe): key for key, spec in zip(plan.feature_keys, plan.feature_specs)}
    requirements_by_key = {req.feature_key: req for req in plan.data_requirements}

    five_min_close_key = by_kind_timeframe[("close", "5m")]
    daily_high_key = by_kind_timeframe[("prior_day_high", "1d")]
    assert requirements_by_key[five_min_close_key].timeframe == "5m"
    assert requirements_by_key[daily_high_key].timeframe == "1d"


def test_data_requirement_marks_streaming_for_live_consumer() -> None:
    components = _components(strategy_feature_refs=["5m.close[0]"])

    plan = build_feature_plan(components, consumer="paper")

    req = plan.data_requirements[0]
    assert req.requires_streaming is True
    assert req.requires_realtime is True
    assert req.requires_intraday is True
    assert req.requires_historical is False


def test_data_requirement_marks_historical_for_backtest_consumer() -> None:
    components = _components(strategy_feature_refs=["5m.close[0]"])

    plan = build_feature_plan(components, consumer="backtest")

    req = plan.data_requirements[0]
    assert req.requires_streaming is False
    assert req.requires_realtime is False
    assert req.requires_historical is True


def test_data_requirement_marks_long_range_for_daily_backtest() -> None:
    components = _components(strategy_feature_refs=["1d.ema:length=50[0]"])

    plan = build_feature_plan(components, consumer="backtest")

    req = plan.data_requirements[0]
    assert req.requires_long_range_history is True
    assert req.requires_intraday is False


def test_data_requirement_intraday_long_range_is_false_even_for_backtest() -> None:
    components = _components(strategy_feature_refs=["5m.close[0]"])

    plan = build_feature_plan(components, consumer="backtest")

    req = plan.data_requirements[0]
    assert req.requires_long_range_history is False


def test_data_requirement_inherits_instrument_class_from_registry() -> None:
    components = _components(strategy_feature_refs=["5m.close[0]"])

    plan = build_feature_plan(components, consumer="paper")

    assert plan.data_requirements[0].instrument_class == "equity"


def test_data_requirements_carry_warmup_per_feature_key() -> None:
    components = _components(strategy_feature_refs=["5m.ema:length=20[0]"])

    plan = build_feature_plan(components, consumer="backtest")

    requirements_by_kind = {
        spec.kind: req
        for spec, req in zip(plan.feature_specs, plan.data_requirements)
    }
    assert requirements_by_kind["ema"].warmup_bars >= 20
    assert requirements_by_kind["atr"].warmup_bars >= 14


def test_data_requirements_are_dedup_by_feature_key() -> None:
    """Repeated canonical FeatureKey references produce one data_requirement."""
    components = _components(
        strategy_feature_refs=["5m.close[0]", "5m.close", "5m.close[0]"],
    )

    plan = build_feature_plan(components, consumer="paper")

    # The three duplicate close refs collapse to a single canonical FeatureKey.
    close_requirements = [
        req for req, spec in zip(plan.data_requirements, plan.feature_specs)
        if spec.kind == "close" and spec.timeframe == "5m"
    ]
    assert len(close_requirements) == 1
    # And data_requirements count == feature_keys count (one row per unique key).
    assert len(plan.data_requirements) == len(plan.feature_keys)


def test_portfolio_feature_data_requirement_does_not_demand_market_data(monkeypatch) -> None:
    """Portfolio features operate on internal portfolio state, not a feed."""
    components = _components(controls_regime_refs=["5m.broker_sync_stale[0]"])

    plan = build_feature_plan(components, consumer="portfolio_governor")

    portfolio_reqs = [req for req in plan.data_requirements if req.instrument_class == "portfolio_state"]
    assert portfolio_reqs, "expected at least one portfolio-state requirement"
    for req in portfolio_reqs:
        assert req.requires_streaming is False
        assert req.requires_realtime is False
        assert req.requires_historical is False
