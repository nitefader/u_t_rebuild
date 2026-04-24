from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app.chart_lab import ChartLabPreviewService
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
from backend.app.features import BatchFeatureEngine, NormalizedBar, ResolvedProgramComponents


class CountingFeatureEngine(BatchFeatureEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def compute(self, plan, bars):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().compute(plan, bars)


def _components() -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Daily Breakout",
        entry_rules=[
            SignalRule(
                name="close_above_prior_high",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="1d.high[0]",
                ),
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="5m RTH",
        timeframe="5m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Risk",
        sizing_method=PositionSizingMethod.RISK_PERCENT_EQUITY,
        risk_per_trade_pct=0.5,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Market",
        entry_order_type=OrderType.MARKET,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="One Symbol",
        symbols=[UniverseSymbol(symbol="SPY")],
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


def _bars(close: float) -> list[NormalizedBar]:
    daily_ts = datetime(2026, 1, 1, 21, 0, tzinfo=timezone.utc)
    intraday_ts = daily_ts + timedelta(hours=18)
    return [
        NormalizedBar(
            symbol="SPY",
            timeframe="1d",
            timestamp=daily_ts,
            open=95,
            high=100,
            low=90,
            close=98,
            volume=1_000_000,
        ),
        NormalizedBar(
            symbol="SPY",
            timeframe="5m",
            timestamp=intraday_ts,
            open=close - 1,
            high=close + 1,
            low=close - 2,
            close=close,
            volume=100_000,
        ),
    ]


def _preview(close: float, feature_engine: BatchFeatureEngine | None = None):
    components = _components()
    bars = _bars(close)
    return ChartLabPreviewService(feature_engine=feature_engine).preview_program(
        components=components,
        bars=bars,
        symbol="SPY",
        timeframe="5m",
        start=bars[0].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
    )


def test_chart_lab_signal_fires_correctly() -> None:
    response = _preview(101)

    bar = response.bars[0]
    assert len(bar.signal_markers) == 1
    assert bar.signal_markers[0].marker_type == "candidate_entry"
    assert bar.condition_truth_tree["intent_count"] == 1


def test_chart_lab_signal_does_not_fire_with_reason() -> None:
    response = _preview(99)

    bar = response.bars[0]
    assert bar.signal_markers == ()
    assert bar.non_fire_reasons == ("signal_condition_false",)
    assert bar.condition_truth_tree["rules"][0]["condition"]["result"] is False


def test_chart_lab_feature_values_exposed_correctly() -> None:
    response = _preview(101)

    values = {value.feature_key: value.value for value in response.bars[0].feature_values}
    assert 101.0 in values.values()
    assert 100.0 in values.values()


def test_chart_lab_multi_timeframe_alignment_correct() -> None:
    response = _preview(101)

    daily_values = [
        value
        for value in response.bars[0].feature_values
        if "|1d|price.high|" in value.feature_key
    ]
    assert len(daily_values) == 1
    assert daily_values[0].value == 100.0
    assert daily_values[0].source_timeframe == "1d"
    assert daily_values[0].source_timestamp == _bars(101)[0].timestamp


def test_chart_lab_uses_feature_engine() -> None:
    feature_engine = CountingFeatureEngine()

    _preview(101, feature_engine=feature_engine)

    assert feature_engine.calls == 1


def test_chart_lab_response_has_no_execution_artifacts() -> None:
    response = _preview(101)
    bar = response.bars[0]

    for forbidden in ["orders", "fills", "positions", "pnl", "equity", "drawdown"]:
        assert not hasattr(response, forbidden)
        assert not hasattr(bar, forbidden)
        assert forbidden not in bar.model_dump()
