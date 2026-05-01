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
from backend.app.features import IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.simulation import HistoricalReplayEngine, SimulatedEventType, SimulatedOrderIntent, SimulatedOrderStatus
from backend.app.simulation.models import SimulatedOrderSide
import backend.app.simulation.historical_replay as historical_replay


class CountingFeatureEngine(IncrementalFeatureEngine):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def compute(self, plan, bars):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().compute(plan, bars)


class RecordingResearchEvidenceStore:
    def __init__(self) -> None:
        self.saved: list[object] = []

    def save_research_evidence(self, evidence):  # type: ignore[no-untyped-def]
        self.saved.append(evidence)
        return evidence


def _components(*, with_protective: bool = True, trailing: bool = False) -> ResolvedDeploymentComponents:
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
    return ResolvedDeploymentComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _short_components(*, with_target: bool = True, trailing: bool = False) -> ResolvedDeploymentComponents:
    """SHORT-side strategy: red-bar entry, stop above entry (5m.high[0]), optional target below entry (5m.low[0])."""
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Short Replay Strategy",
        entry_rules=[
            SignalRule(
                name="red_bar_short_entry",
                side=CandidateSide.SHORT,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.LESS_THAN,
                    right_feature="5m.open[0]",
                ),
                stop_candidate_feature="5m.high[0]",
                target_candidate_feature="5m.low[0]" if with_target else None,
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
        name="Short Market Bracket",
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
        name="Short Replay Program",
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
    components: ResolvedDeploymentComponents | None = None,
    partial_fill_ratio: float = 1.0,
    feature_engine: IncrementalFeatureEngine | None = None,
    protective_placer=None,  # type: ignore[no-untyped-def]
):
    return HistoricalReplayEngine(
        feature_engine=feature_engine,
        partial_fill_ratio=partial_fill_ratio,
        protective_placer=protective_placer,
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
        dumped["evidence"]["created_at"] = None

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


def test_historical_replay_saves_simulation_run_evidence() -> None:
    bars = [
        _bar(0, open_=99, high=110, low=95, close=100),
        _bar(1, open_=111, high=112, low=109, close=109),
    ]
    components = _components()
    store = RecordingResearchEvidenceStore()

    result = HistoricalReplayEngine(evidence_recorder=store).run(
        components=components,
        bars=bars,
        start=bars[0].timestamp,
        end=bars[-1].timestamp + timedelta(minutes=5),
        initial_cash=100_000,
        session_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    assert result.evidence is not None
    assert result.evidence.run_id == result.session.id
    assert result.evidence.strategy_id == components.strategy.strategy_id
    assert result.evidence.strategy_version_id == components.strategy.id
    assert result.evidence.simulated_order_count == len(result.orders)
    assert result.evidence.simulated_fill_count == len(result.fills)
    assert store.saved == [result.evidence]


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
    assert "OrderManager" not in source.replace("SimulatedOrderManager", "")
    assert "BrokerAdapter" not in source
    assert "FakeBrokerAdapter" not in source
    assert "BrokerSync" not in source
    assert ".create_order(" in source
    assert ".submit_order(" not in source
    assert ".apply_result(" not in source


def test_replay_open_path_invokes_protective_placer() -> None:
    class RecordingPlacer:
        def __init__(self) -> None:
            self.calls = 0

        def compute_protective_plan(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls += 1
            from backend.app.orders.protective_placer import ProtectivePlacementPlan

            return ProtectivePlacementPlan(
                parent_order_id=kwargs["parent_order_id"],
                signal_plan_id=kwargs["signal_plan"].signal_plan_id,
                account_id=kwargs["account_id"],
                covered_qty=kwargs["cumulative_filled_qty"],
                legs=(),
            )

    placer = RecordingPlacer()
    _run(
        [
            _bar(0, open_=99, high=110, low=95, close=100),
            _bar(1, open_=111, high=112, low=109, close=109),
        ],
        protective_placer=placer,
    )
    assert placer.calls >= 1


def test_short_entry_routes_sell_to_open_and_records_short_position() -> None:
    # Red bar (close < open) triggers SHORT entry at close=100. Stop sits at
    # bar.high=110 (above entry). Position qty becomes negative (sold-short).
    result = _run(
        [
            _bar(0, open_=101, high=110, low=95, close=100),
            _bar(1, open_=99, high=99.5, low=98, close=98.5),
        ],
        components=_short_components(with_target=False),
    )

    open_orders = [order for order in result.orders if order.intent == SimulatedOrderIntent.OPEN]
    assert len(open_orders) == 1
    assert open_orders[0].side == SimulatedOrderSide.SELL
    assert open_orders[0].status == SimulatedOrderStatus.FILLED

    spy = next(position for position in result.positions if position.symbol == "SPY")
    # Last bar leaves the short open; qty must be negative for shorts.
    assert spy.qty == -10
    assert spy.avg_price == 100
    # Protective stop is a BUY-to-cover at 110 (above entry).
    stops = [order for order in result.orders if order.intent == SimulatedOrderIntent.STOP_LOSS]
    assert stops and stops[-1].side == SimulatedOrderSide.BUY
    assert stops[-1].stop_price == 110


def test_short_take_profit_triggers_when_low_reaches_target() -> None:
    # Red bar entry at 100, target at low=95 (below entry). Next bar dips
    # to 94 — target fires; cover at 95. Realized = (100 - 95) * 10 = 50.
    result = _run(
        [
            _bar(0, open_=101, high=102, low=95, close=100),
            _bar(1, open_=98, high=99, low=94, close=96),
        ],
        components=_short_components(with_target=True),
    )

    assert result.trades, "expected at least one closed trade"
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.exit_reason == SimulatedOrderIntent.TAKE_PROFIT
    assert trade.exit_price == 95
    assert trade.realized_pnl == 50
    assert result.realized_pnl == 50


def test_short_stop_loss_triggers_when_high_breaks_above_stop() -> None:
    # Red bar entry at 100, stop at bar.high=102. Next bar rallies and
    # bar.high (108) breaks the 102 stop. Cover at 102; realized loss = -20.
    result = _run(
        [
            _bar(0, open_=101, high=102, low=95, close=100),
            _bar(1, open_=104, high=108, low=103, close=107),
        ],
        components=_short_components(with_target=False),
    )

    assert result.trades
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.exit_reason == SimulatedOrderIntent.STOP_LOSS
    assert trade.exit_price == 102
    assert trade.realized_pnl == -20
    assert result.max_drawdown == 20


def test_short_trailing_stop_ratchets_down_and_covers_for_a_gain() -> None:
    # Red bar entry at 100, initial trailing stop at high=102 (distance 2).
    # Next bar drops to low=85 → trailing ratchets to 85 + 2 = 87. The same
    # bar's high (90) breaks the new stop → cover at 87; realized = (100-87)*10 = 130.
    result = _run(
        [
            _bar(0, open_=101, high=102, low=95, close=100),
            _bar(1, open_=98, high=90, low=85, close=88),
        ],
        components=_short_components(with_target=False, trailing=True),
    )

    assert any(event.event_type == SimulatedEventType.TRAILING_STOP_UPDATED for event in result.events)
    assert result.trades
    trade = result.trades[0]
    assert trade.side == "short"
    assert trade.exit_reason == SimulatedOrderIntent.TRAILING_STOP
    assert trade.exit_price == 87
    assert trade.realized_pnl == 130


def test_long_entry_blocked_when_short_position_open() -> None:
    # Mixed strategy: SHORT-on-red (fires bar 0) + LONG-on-green (fires bar 1)
    # — the long entry must be rejected with reason 'opposite_side_position_open'
    # because cross-side flips are not supported in this slice.
    short_components = _short_components(with_target=False)
    short_components.strategy.entry_rules.append(
        SignalRule(
            name="green_bar_long_entry",
            side=CandidateSide.LONG,
            intent_type=IntentType.ENTRY,
            condition=ConditionNode(
                left_feature="5m.close[0]",
                operator=ConditionOperator.GREATER_THAN,
                right_feature="5m.open[0]",
            ),
        )
    )
    result = _run(
        [
            _bar(0, open_=101, high=110, low=95, close=100),  # red → short open
            _bar(1, open_=98, high=105, low=97, close=104),   # green → long entry attempted
        ],
        components=short_components,
    )

    blocked = [
        event
        for event in result.events
        if event.event_type == SimulatedEventType.SIGNAL_BLOCKED
        and event.message == "opposite_side_position_open"
    ]
    assert blocked, "expected long entry to be blocked while a short is open"
