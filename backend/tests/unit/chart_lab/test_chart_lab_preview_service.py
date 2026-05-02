from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.chart_lab import ChartLabPreviewService
from backend.app.domain import (
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    OrderType,
    ProgramVersion,
    ResearchDataPolicy,
    ResearchRunKind,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import CandidateSide, IntentType, SignalRule
from backend.app.features import (
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedDeploymentComponents,
    build_feature_refs_plan,
)
from backend.app.research.artifacts import build_research_run_artifact


class RecordingResearchEvidenceStore:
    def __init__(self) -> None:
        self.saved: list[object] = []

    def save_research_evidence(self, evidence):  # type: ignore[no-untyped-def]
        self.saved.append(evidence)
        return evidence


class CountingFeatureEngine(IncrementalFeatureEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def compute(self, plan, bars):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().compute(plan, bars)


def _components() -> ResolvedDeploymentComponents:
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
    return ResolvedDeploymentComponents(
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


def _intraday_bars(count: int = 60) -> list[NormalizedBar]:
    start = datetime(2026, 1, 3, 14, 30, tzinfo=timezone.utc)
    bars: list[NormalizedBar] = []
    for index in range(count):
        price = 100.0 + index
        bars.append(
            NormalizedBar(
                symbol="SPY",
                timeframe="5m",
                timestamp=start + timedelta(minutes=5 * index),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price + 0.5,
                volume=100_000 + index,
            )
        )
    return bars


def _preview(close: float, feature_engine: IncrementalFeatureEngine | None = None):
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


def test_chart_lab_preview_program_attaches_research_artifact() -> None:
    components = _components()
    bars = _bars(101)
    store = RecordingResearchEvidenceStore()
    artifact = build_research_run_artifact(
        run_id=uuid4(),
        run_kind=ResearchRunKind.CHART_LAB,
        components=components,
        data_policy=ResearchDataPolicy(
            provider="alpaca",
            timeframe="5m",
            start=bars[0].timestamp,
            end=bars[-1].timestamp + timedelta(minutes=5),
        ),
        producer="chart_lab_preview",
    )

    response = ChartLabPreviewService(evidence_recorder=store).preview_program(
        components=components,
        bars=bars,
        symbol="SPY",
        timeframe="5m",
        start=bars[0].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
        artifact=artifact,
    )

    assert response.session.strategy_version_id == components.strategy.id
    assert response.feature_plan.symbols == ("SPY",)
    assert response.bars[0].signal_markers[0].marker_type == "candidate_entry"
    assert response.evidence is not None
    assert response.evidence.evidence_id == artifact.run_id
    assert response.evidence.artifact_id == artifact.artifact_id
    assert response.evidence.deployment_snapshot_id == artifact.deployment_snapshot.snapshot_id
    assert response.evidence.deployment_snapshot is not None
    assert response.evidence.signal_marker_count == 1
    assert store.saved == [response.evidence]


def test_chart_lab_preview_requires_resolved_strategy() -> None:
    components = _components()
    bars = _bars(101)

    with pytest.raises(ValueError, match="requires a resolved StrategyVersion"):
        ChartLabPreviewService().preview_program(
            components=components.model_copy(update={"strategy": None}),
            bars=bars,
            symbol="SPY",
            timeframe="5m",
            start=bars[0].timestamp,
            end=bars[-1].timestamp + timedelta(minutes=5),
        )


def test_chart_lab_preview_saves_research_evidence() -> None:
    components = _components()
    bars = _bars(101)
    store = RecordingResearchEvidenceStore()

    response = ChartLabPreviewService(evidence_recorder=store).preview_program(
        components=components,
        bars=bars,
        symbol="SPY",
        timeframe="5m",
        start=bars[0].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
    )

    assert response.evidence is not None
    assert response.evidence.strategy_id == components.strategy.strategy_id
    assert response.evidence.strategy_version_id == components.strategy.id
    assert response.evidence.signal_marker_count == 1
    assert store.saved == [response.evidence]


def test_chart_lab_feature_explorer_has_no_strategy_or_evidence() -> None:
    bars = _intraday_bars()
    plan = build_feature_refs_plan(
        strategy_version_id=uuid4(),
        feature_refs=("5m.rsi:length=14",),
        symbols=("SPY",),
        default_timeframe="5m",
    )
    store = RecordingResearchEvidenceStore()

    response = ChartLabPreviewService(evidence_recorder=store).preview_plan(
        strategy=None,
        plan=plan,
        bars=bars,
        symbol="SPY",
        timeframe="5m",
        start=bars[5].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
        feature_origins={plan.feature_keys[0]: "manual"},
    )

    assert response.session.strategy_version_id is None
    assert response.evidence is None
    assert store.saved == []
    assert response.features[0].origin == "manual"
    assert response.features[0].badge == "Manual"
    assert response.bars[0].is_warmup is True
    assert response.bars[-1].feature_values[0].value is not None
    assert all(bar.signal_markers == () for bar in response.bars)


# ---------------------------------------------------------------------------
# Timeframe mismatch tests (regression for KeyError: 'no feature frame …')
# ---------------------------------------------------------------------------

def test_chart_lab_matching_timeframe_returns_200() -> None:
    """When the requested timeframe matches a frame in the computed set, preview succeeds."""
    components = _components()
    bars = _bars(101)

    response = ChartLabPreviewService().preview_program(
        components=components,
        bars=bars,
        symbol="SPY",
        timeframe="5m",
        start=bars[0].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
    )

    assert len(response.bars) == 1


def _components_5m_only() -> ResolvedDeploymentComponents:
    """Strategy that only references 5m features — used to test timeframe mismatch."""
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="5m Only",
        entry_rules=[
            SignalRule(
                name="close_above_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
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
    return ResolvedDeploymentComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _bars_5m_only() -> list[NormalizedBar]:
    ts = datetime(2026, 1, 3, 14, 30, tzinfo=timezone.utc)
    return [
        NormalizedBar(
            symbol="SPY",
            timeframe="5m",
            timestamp=ts,
            open=480.0,
            high=482.0,
            low=479.0,
            close=481.0,
            volume=500_000,
        ),
    ]


def test_chart_lab_mismatched_timeframe_raises_mismatch_error() -> None:
    """When the requested timeframe has no feature frame (strategy uses only 5m
    features but caller requests 1d bars), ChartLabTimeframeMismatchError is
    raised with structured context."""
    from backend.app.chart_lab.preview_service import ChartLabTimeframeMismatchError

    components = _components_5m_only()
    bars = _bars_5m_only()

    with pytest.raises(ChartLabTimeframeMismatchError) as exc_info:
        ChartLabPreviewService().preview_program(
            components=components,
            bars=bars,
            symbol="SPY",
            timeframe="1d",
            start=bars[0].timestamp,
            end=bars[-1].timestamp + timedelta(minutes=5),
        )

    err = exc_info.value
    assert err.requested_timeframe == "1d"
    assert "5m" in err.required_timeframes
