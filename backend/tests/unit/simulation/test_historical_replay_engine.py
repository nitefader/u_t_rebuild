from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

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
from backend.app.domain.execution_style import BracketSpec
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import CandidateSide, IntentType, SignalRule
from backend.app.features import BatchFeatureEngine, NormalizedBar, ResolvedProgramComponents
from backend.app.simulation import HistoricalReplayEngine, SimulatedEventType, SimulatedOrderIntent, SimulatedOrderStatus
import backend.app.simulation.historical_replay as historical_replay


class CountingFeatureEngine(BatchFeatureEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def compute(self, plan, bars):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().compute(plan, bars)


def _components(*, with_protective: bool = True, trailing: bool = False) -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Replay Strategy",
        entry_rules=[
            SignalRule(
                name="green_bar_entry",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
                ),
                stop_candidate_feature="5m.low[0]" if with_protective else None,
                target_candidate_feature="5m.high[0]" if with_protective else None,
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="5m Controls",
        timeframe="5m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=10,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Market Bracket",
        entry_order_type=OrderType.MARKET,
        bracket=BracketSpec(enabled=True, take_profit_r_multiple=2, stop_loss_r_multiple=1),
        trailing_stop_enabled=trailing,
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
        name="Replay Program",
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


def _bar(index: int, *, open_: float, high: float, low: float, close: float) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100_000,
    )


def _run(
    bars: list[NormalizedBar],
    *,
    components: ResolvedProgramComponents | None = None,
    partial_fill_ratio: float = 1.0,
    feature_engine: BatchFeatureEngine | None = None,
):
    return HistoricalReplayEngine(
        feature_engine=feature_engine,
        partial_fill_ratio=partial_fill_ratio,
    ).run(
        components=components or _components(),
        bars=bars,
        start=bars[0].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
        initial_cash=100_000,
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
    )


def test_deterministic_replay_produces_same_results() -> None:
    bars = [
        _bar(0, open_=99, high=110, low=95, close=100),
        _bar(1, open_=111, high=112, low=109, close=109),
    ]
    components = _components()

    first = _run(bars, components=components).model_dump()
    second = _run(bars, components=components).model_dump()
    for dumped in (first, second):
        dumped["session"]["created_at"] = None
        dumped["session"]["feature_plan_id"] = None

    assert first == second


def test_order_lifecycle_correct() -> None:
    result = _run([
        _bar(0, open_=99, high=110, low=95, close=100),
        _bar(1, open_=111, high=112, low=109, close=109),
    ])

    assert result.orders[0].intent == SimulatedOrderIntent.OPEN
    assert result.orders[0].status == SimulatedOrderStatus.FILLED
    assert any(order.intent == SimulatedOrderIntent.STOP_LOSS for order in result.orders)
    assert any(order.intent == SimulatedOrderIntent.TAKE_PROFIT for order in result.orders)
    assert any(event.event_type == SimulatedEventType.ORDER_CREATED for event in result.events)
    assert result.positions[0].qty == 0


def test_partial_fills_are_handled() -> None:
    result = _run(
        [
            _bar(0, open_=99, high=101, low=98, close=100),
            _bar(1, open_=100, high=102, low=99, close=101),
        ],
        components=_components(with_protective=False),
        partial_fill_ratio=0.5,
    )

    open_order = result.orders[0]
    assert open_order.status == SimulatedOrderStatus.PARTIALLY_FILLED
    assert open_order.filled_qty == 7.5
    assert result.positions[0].qty == 7.5
    assert any(event.event_type == SimulatedEventType.ORDER_PARTIALLY_FILLED for event in result.events)


def test_pnl_correct_when_target_fills() -> None:
    result = _run([
        _bar(0, open_=99, high=110, low=95, close=100),
        _bar(1, open_=111, high=112, low=109, close=109),
    ])

    assert result.trades[0].exit_reason == SimulatedOrderIntent.TAKE_PROFIT
    assert result.trades[0].realized_pnl == 100
    assert result.realized_pnl == 100


def test_stop_loss_logic_works() -> None:
    result = _run([
        _bar(0, open_=99, high=110, low=95, close=100),
        _bar(1, open_=96, high=97, low=94, close=95),
    ])

    assert result.trades[0].exit_reason == SimulatedOrderIntent.STOP_LOSS
    assert result.trades[0].realized_pnl == -50
    assert result.max_drawdown == 50


def test_trailing_stop_logic_updates_and_fills() -> None:
    result = _run(
        [
            _bar(0, open_=99, high=105, low=95, close=100),
            _bar(1, open_=104, high=110, low=104, close=109),
            _bar(2, open_=107, high=108, low=104, close=105),
        ],
        components=_components(trailing=True),
    )

    assert result.trades[0].exit_reason == SimulatedOrderIntent.TRAILING_STOP
    assert result.trades[0].exit_price == 105
    assert any(event.event_type == SimulatedEventType.TRAILING_STOP_UPDATED for event in result.events)


def test_sim_lab_uses_feature_engine_and_does_not_expose_external_broker_fields() -> None:
    feature_engine = CountingFeatureEngine()
    result = _run(
        [
            _bar(0, open_=99, high=110, low=95, close=100),
            _bar(1, open_=111, high=112, low=109, close=109),
        ],
        feature_engine=feature_engine,
    )

    assert feature_engine.calls == 1
    dumped = result.model_dump()
    for forbidden in ["alpaca", "broker_order_id", "client_order_id", "broker_account_id", "deployment_id"]:
        assert forbidden not in str(dumped).lower()


def test_simulation_module_makes_no_external_calls() -> None:
    source = inspect.getsource(historical_replay)

    for forbidden in ["alpaca", "requests", "httpx", "websocket"]:
        assert forbidden not in source.lower()


def test_simulation_uses_only_simulated_order_manager_boundary() -> None:
    source = inspect.getsource(historical_replay)

    assert "SimulatedOrderManager" in source
    assert "from backend.app.orders" not in source
    assert "OrderManager" not in source.replace("SimulatedOrderManager", "")
    assert "BrokerAdapter" not in source
    assert "FakeBrokerAdapter" not in source
    assert "BrokerSync" not in source
    assert ".create_order(" in source
    assert ".submit_order(" not in source
    assert ".apply_result(" not in source
