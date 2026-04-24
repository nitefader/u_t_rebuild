from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app.decision import SignalEngine
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
from backend.app.features import (
    BatchFeatureEngine,
    FeatureCache,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedProgramComponents,
    build_feature_plan,
)
from backend.app.runtime import DeploymentContext, RuntimeEngine, RuntimeEventType
import backend.app.runtime.engine as runtime_engine_module


class CountingIncrementalFeatureEngine(IncrementalFeatureEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def update(self, *, plan, bar, cache):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().update(plan=plan, bar=bar, cache=cache)


def _components(*, symbols: list[str] | None = None, timeframe: str = "5m") -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Runtime Strategy",
        entry_rules=[
            SignalRule(
                name="close_above_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature=f"{timeframe}.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature=f"{timeframe}.open[0]",
                ),
                stop_candidate_feature=f"{timeframe}.low[0]",
                target_candidate_feature=f"{timeframe}.high[0]",
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="Runtime Controls",
        timeframe=timeframe,
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=5,
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
        name="Runtime Universe",
        symbols=[UniverseSymbol(symbol=symbol) for symbol in (symbols or ["SPY"])],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Runtime Program",
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


def _deployment(components: ResolvedProgramComponents) -> DeploymentContext:
    return DeploymentContext(deployment_id=uuid4(), program=components.program)


def _bar(index: int, *, symbol: str = "SPY", timeframe: str = "5m", open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * index),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000 + index,
    )


def test_processing_one_bar_updates_features_incrementally() -> None:
    components = _components()
    feature_engine = CountingIncrementalFeatureEngine()
    runtime = RuntimeEngine(
        deployment=_deployment(components),
        components=components,
        feature_engine=feature_engine,
    )

    result = runtime.process_bar(_bar(0))

    assert feature_engine.calls == 1
    assert runtime.feature_cache.processed_bar_count == 1
    assert result.state.processed_bar_count == 1
    assert any(event.event_type == RuntimeEventType.FEATURE_UPDATED for event in result.events)


def test_signal_fires_correctly_in_streaming_mode() -> None:
    components = _components()
    runtime = RuntimeEngine(deployment=_deployment(components), components=components)

    result = runtime.process_bar(_bar(0, open_=99, close=100))

    assert len(result.execution_intents) == 1
    intent = result.execution_intents[0]
    assert intent.symbol == "SPY"
    assert intent.qty == 5
    assert intent.governor_approved is True
    assert any(event.event_type == RuntimeEventType.SIGNAL_CANDIDATE for event in result.events)
    assert any(event.event_type == RuntimeEventType.EXECUTION_INTENT_CREATED for event in result.events)


def test_no_recompute_of_full_history() -> None:
    components = _components()
    feature_engine = CountingIncrementalFeatureEngine()
    runtime = RuntimeEngine(
        deployment=_deployment(components),
        components=components,
        feature_engine=feature_engine,
    )

    runtime.process_bars([_bar(0), _bar(1), _bar(2)])
    source = inspect.getsource(runtime_engine_module)

    assert feature_engine.calls == 3
    assert "BatchFeatureEngine" not in source
    assert ".compute(" not in source


def test_multi_symbol_handling_works() -> None:
    components = _components(symbols=["SPY", "QQQ"])
    runtime = RuntimeEngine(deployment=_deployment(components), components=components)

    first = runtime.process_bar(_bar(0, symbol="SPY", open_=99, close=100))
    second = runtime.process_bar(_bar(0, symbol="QQQ", open_=199, close=200))

    assert len(first.execution_intents) == 1
    assert len(second.execution_intents) == 1
    assert first.execution_intents[0].symbol == "SPY"
    assert second.execution_intents[0].symbol == "QQQ"
    assert second.state.processed_bar_count == 2
    assert second.state.candidate_intent_count == 2


def test_output_events_match_batch_expectations() -> None:
    components = _components()
    bar = _bar(0, open_=99, close=100)
    runtime = RuntimeEngine(deployment=_deployment(components), components=components)

    runtime_result = runtime.process_bar(bar)
    plan = build_feature_plan(components, consumer="runtime")
    batch_snapshot = BatchFeatureEngine().compute(plan, [bar]).frame_for("SPY", "5m").snapshots[0]
    batch_result = SignalEngine().evaluate(components.strategy, batch_snapshot)

    assert len(runtime_result.execution_intents) == len(batch_result.intents) == 1
    assert runtime_result.execution_intents[0].signal_name == batch_result.intents[0].signal_name
    assert runtime_result.execution_intents[0].features_used == batch_result.intents[0].feature_values_used


def test_runtime_has_no_broker_or_fill_artifacts() -> None:
    components = _components()
    runtime = RuntimeEngine(deployment=_deployment(components), components=components)

    result = runtime.process_bar(_bar(0))
    dumped = result.model_dump()

    for forbidden in ["alpaca", "broker_order_id", "client_order_id", "fill", "filled_qty", "position"]:
        assert forbidden not in str(dumped).lower()
