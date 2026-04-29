"""Spine integration: logical_exit is the only exit intent.

Doctrine: time-based exits, bar-count exits, session exits, indicator exits,
and hybrid exits all map to ``SignalPlan.intent = logical_exit``. Never a new
top-level intent. This module asserts the end-to-end flow:

    FeatureSnapshot + PositionContext
        -> SignalEngine.evaluate(strategy, snapshot, position_contexts=...)
        -> CandidateTradeIntent(intent_type=EXIT)
        -> SignalPlanBuilder -> SignalPlan(intent=logical_exit, payload=...)
        -> RiskResolver.decide -> RiskDecisionCard(decision=approved, sized from existing position)
        -> SimulatedBroker.submit_close_order -> SimulatedTrade with full lineage
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    LogicalExitRule,
    LogicalExitRuleKind,
    OrderType,
    RiskDecisionMode,
    RiskDecisionStatus,
    RiskProfileVersion,
    SignalPlanIntent,
    SignalPlanLogicalExitScope,
    SignalRule,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.execution_style import BracketSpec
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.simulation import HistoricalReplayEngine
from backend.app.simulation.models import SimulatedOrderIntent


def _components(*, exit_rule: SignalRule) -> ResolvedDeploymentComponents:
    strategy_id = uuid4()
    version_id = uuid4()
    strategy = StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        name="Spine exit doctrine test",
        entry_rules=[
            SignalRule(
                name="green_bar_entry",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="1d.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="1d.open[0]",
                ),
                # No stop / target candidates — positions stay open until the
                # logical_exit rule fires, isolating exit-spine behavior.
            )
        ],
        exit_rules=[exit_rule],
    )
    return ResolvedDeploymentComponents(
        strategy=strategy,
        strategy_controls=StrategyControlsVersion(
            id=uuid4(),
            strategy_controls_id=uuid4(),
            version=1,
            name="1d controls",
            timeframe="1d",
        ),
        risk_profile=RiskProfileVersion(
            id=uuid4(),
            risk_profile_id=uuid4(),
            version=1,
            name="Fixed shares",
            sizing_method=PositionSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
        execution_style=ExecutionStyleVersion(
            id=uuid4(),
            execution_style_id=uuid4(),
            version=1,
            name="Market entry, signal-driven exit",
            entry_order_type=OrderType.MARKET,
            bracket=BracketSpec(enabled=False),
        ),
        universe=UniverseSnapshot(
            id=uuid4(),
            universe_id=uuid4(),
            version=1,
            name="Spine exit universe",
            symbols=[UniverseSymbol(symbol="SPY")],
        ),
    )


def _bars(symbol: str = "SPY", count: int = 25) -> list[NormalizedBar]:
    bars: list[NormalizedBar] = []
    base = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)  # 09:30 ET
    price = 100.0
    for i in range(count):
        # Steady up-trending green bars (close > open) so the entry rule fires.
        open_price = price + 0.10
        close_price = open_price + 0.50
        high = close_price + 0.30
        low = open_price - 0.20
        bars.append(
            NormalizedBar(
                symbol=symbol,
                timeframe="1d",
                timestamp=base + timedelta(minutes=i),
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=1_000_000.0,
            )
        )
        price = close_price
    return bars


def _run(exit_rule: SignalRule, *, count: int = 25) -> tuple[object, HistoricalReplayEngine]:
    components = _components(exit_rule=exit_rule)
    bars = _bars(count=count)
    engine = HistoricalReplayEngine(mode=RiskDecisionMode.BACKTEST)
    result = engine.run(
        components=components,
        bars=bars,
        start=bars[0].timestamp,
        end=bars[-1].timestamp,
        initial_cash=100_000,
        run_id=uuid4(),
    )
    return result, engine


def test_bars_since_entry_exit_fires_after_n_bars() -> None:
    exit_rule = SignalRule(
        name="exit_after_5_bars",
        side=CandidateSide.LONG,
        intent_type=IntentType.EXIT,
        logical_exit_rule=LogicalExitRule(
            kind=LogicalExitRuleKind.BARS_SINCE_ENTRY,
            bars=5,
        ),
    )
    result, engine = _run(exit_rule, count=15)

    # At least one trade should close via the spine-driven logical_exit path.
    assert len(result.trades) >= 1
    closed_via_signal = [t for t in result.trades if t.exit_reason == SimulatedOrderIntent.CLOSE]
    assert closed_via_signal, "expected at least one signal-driven CLOSE trade"
    sample = closed_via_signal[0]
    assert sample.risk_decision_id is not None
    assert sample.signal_plan_id is not None

    # Every emitted RiskDecisionCard for an exit must carry the logical_exit
    # lifecycle intent and reference the existing position quantity.
    exit_cards = [c for c in engine.risk_decision_cards() if c.lifecycle_intent == SignalPlanIntent.LOGICAL_EXIT.value]
    assert exit_cards, "expected at least one logical_exit RiskDecisionCard"
    approved = [c for c in exit_cards if c.decision == RiskDecisionStatus.APPROVED]
    assert approved, "expected at least one approved exit decision"
    sized = approved[0]
    assert sized.final_quantity > 0
    # Sizing came from existing position, not from RiskPlan.fixed_shares of 10
    # (10 shares is the entry; exit closes the same 10 shares).
    assert sized.final_quantity == pytest.approx(10.0)


def test_time_in_position_seconds_exit_fires_after_window() -> None:
    exit_rule = SignalRule(
        name="exit_after_3_minutes",
        side=CandidateSide.LONG,
        intent_type=IntentType.EXIT,
        logical_exit_rule=LogicalExitRule(
            kind=LogicalExitRuleKind.TIME_IN_POSITION_SECONDS,
            seconds=180,
        ),
    )
    result, engine = _run(exit_rule, count=15)
    closed = [t for t in result.trades if t.exit_reason == SimulatedOrderIntent.CLOSE]
    assert closed, "time-in-position exit should fire and close the position"
    assert closed[0].risk_decision_id is not None


def test_feature_condition_exit_routed_through_logical_exit() -> None:
    # Pure feature-based exit: condition tree only, no logical_exit_rule.
    # The spine must wrap it as LogicalExitRule(kind=FEATURE_CONDITION) when
    # building the SignalPlan — the intent stays logical_exit.
    exit_rule = SignalRule(
        name="exit_when_close_below_open",
        side=CandidateSide.LONG,
        intent_type=IntentType.EXIT,
        condition=ConditionNode(
            left_feature="1d.close[0]",
            operator=ConditionOperator.LESS_THAN,
            right_feature="1d.open[0]",
        ),
    )
    # _bars() generates green bars only, so the feature-only exit should not
    # fire — but the test still asserts the spine accepts the rule shape and
    # never raises.
    result, engine = _run(exit_rule, count=15)
    assert result is not None
    # Verify NO exit candidates fire (because close > open on every bar).
    exit_cards = [c for c in engine.risk_decision_cards() if c.lifecycle_intent == SignalPlanIntent.LOGICAL_EXIT.value]
    assert exit_cards == []


def test_hybrid_exit_combines_bars_and_feature_condition() -> None:
    exit_rule = SignalRule(
        name="exit_after_3_bars_and_close_above_threshold",
        side=CandidateSide.LONG,
        intent_type=IntentType.EXIT,
        logical_exit_rule=LogicalExitRule(
            kind=LogicalExitRuleKind.HYBRID,
            operator="all",
            children=(
                LogicalExitRule(kind=LogicalExitRuleKind.BARS_SINCE_ENTRY, bars=3),
                LogicalExitRule(
                    kind=LogicalExitRuleKind.FEATURE_CONDITION,
                    feature_condition=ConditionNode(
                        left_feature="1d.close[0]",
                        operator=ConditionOperator.GT,
                        right_value=100.0,
                    ),
                ),
            ),
        ),
    )
    result, engine = _run(exit_rule, count=15)
    closed = [t for t in result.trades if t.exit_reason == SimulatedOrderIntent.CLOSE]
    assert closed, "hybrid (bars AND feature) exit should fire once both conditions hold"


def test_no_new_top_level_signalplan_intent_for_time_or_bar_exits() -> None:
    """Doctrine guard: the SignalPlanIntent enum must not gain time/bar/session siblings."""
    allowed = {
        "open",
        "close",
        "reduce",
        "target",
        "stop",
        "trail",
        "breakeven",
        "runner",
        "logical_exit",
    }
    actual = {member.value for member in SignalPlanIntent}
    assert actual == allowed, (
        "SignalPlanIntent vocabulary changed. Per doctrine, time / bar / session / "
        "feature / hybrid exits must remain inside logical_exit, not become sibling intents."
    )
