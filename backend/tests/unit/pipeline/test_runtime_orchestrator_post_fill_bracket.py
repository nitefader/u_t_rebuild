"""T-5 (Bracket Program) — orchestrator end-to-end acceptance.

Acceptance scenarios from STRATEGY_TO_BROKER_BRACKET_PROGRAM.md §5:
A live bar drives the full pipeline (signal -> SignalPlan -> Account
evaluation -> RiskResolver -> Governor -> OrderManager entry submit ->
fake fill -> ProtectiveOrderPlacer -> OrderManager protective children
-> BrokerAdapter submit) for both LONG and SHORT entries.

Validates:
- post_fill_bracket is the default mode (no native bracket fields on the
  entry; protective children land after the fill)
- LONG entry produces a SELL stop child and a SELL target child
- SHORT entry produces a BUY stop child and a BUY target child
- the BrokerAdapter receives BOTH the entry order AND the protective
  child orders (T-4 ProtectiveOrderPlacer + T-5 wiring closed the loop)
- protection_placed pipeline event is emitted with leg_count=2
- protection child stop_price + limit_price are computed from the fill
  price (FakeBrokerAdapter reports filled_avg_price=100.0 by default)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import BrokerOrderStatus, FakeBrokerAdapter
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    SignalPlanSide,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.execution_style import (
    BracketStopTargetPreset,
    ExecutionMode,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.orders import InternalOrderIntent, InternalOrderStatus
from backend.app.orders.models import OrderOrigin
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _components(
    *,
    side: CandidateSide,
    execution_mode: ExecutionMode = ExecutionMode.POST_FILL_BRACKET,
    stop_pct: float = 5.0,
    target_pct: float = 10.0,
) -> ResolvedDeploymentComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    rule_intent = IntentType.ENTRY
    if side == CandidateSide.LONG:
        condition = ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.GREATER_THAN,
            right_feature="5m.open[0]",
        )
    else:
        condition = ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.LESS_THAN,
            right_feature="5m.open[0]",
        )
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Bracket Strategy",
        entry_rules=[
            SignalRule(
                name="entry_rule",
                side=side,
                intent_type=rule_intent,
                condition=condition,
                stop_candidate_feature="5m.low[0]",
                target_candidate_feature="5m.high[0]",
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
        name="Bracket 5/10",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=execution_mode,
        preset=BracketStopTargetPreset(stop_pct=stop_pct, target_pct=target_pct),
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Bracket Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Bracket Program",
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


def _deployment(components: ResolvedDeploymentComponents) -> DeploymentContext:
    return DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
    )


def _bar(*, open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000,
    )


def _orchestrator(*, components: ResolvedDeploymentComponents, broker: FakeBrokerAdapter) -> RuntimeOrchestrator:
    return RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        broker_adapter=broker,
    )


def test_post_fill_bracket_long_entry_triggers_protective_children() -> None:
    components = _components(side=CandidateSide.LONG)
    # FakeBroker returns FILLED for the entry, ACCEPTED for both
    # protective children (stop + target).
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED]
    )
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # Three orders submitted: entry + 2 protective children.
    assert len(broker.submitted_orders) == 3
    entry_submit = broker.submitted_orders[0]
    child_submits = broker.submitted_orders[1:]

    # Entry side and intent.
    assert entry_submit.intent == InternalOrderIntent.OPEN
    assert entry_submit.parent_order_id is None
    # Bracket child fields are NOT set on the entry under post_fill mode —
    # that path is exclusive to native_alpaca_bracket.
    assert entry_submit.bracket_take_profit_limit_price is None
    assert entry_submit.bracket_stop_loss_stop_price is None
    assert entry_submit.order_class is None

    # Children: stop + target, both pointing at the entry as parent,
    # both labeled with the cumulative fill breakpoint.
    intents = {child.intent for child in child_submits}
    assert intents == {InternalOrderIntent.STOP_LOSS, InternalOrderIntent.TAKE_PROFIT}
    for child in child_submits:
        assert child.parent_order_id == entry_submit.order_id
        assert child.signal_plan_id == entry_submit.signal_plan_id
        assert child.account_id == ACCOUNT_ID
        assert child.deployment_id == DEPLOYMENT_ID
        assert child.origin == OrderOrigin.SIGNAL_PLAN
        assert child.order_class == "oco"
        # LONG entry -> children exit on SELL side (CandidateSide.SHORT
        # represents SELL on the internal side enum).
        assert child.side == CandidateSide.SHORT

    # Concrete prices off the FakeBroker fill price (100.0).
    stop_child = next(c for c in child_submits if c.intent == InternalOrderIntent.STOP_LOSS)
    target_child = next(c for c in child_submits if c.intent == InternalOrderIntent.TAKE_PROFIT)
    assert stop_child.order_type == OrderType.STOP
    assert stop_child.stop_price == pytest.approx(95.0)  # 100 * (1 - 5/100)
    assert stop_child.limit_price is None
    assert target_child.order_type == OrderType.LIMIT
    assert target_child.limit_price == pytest.approx(110.0)  # 100 * (1 + 10/100)
    assert target_child.stop_price is None

    # Pipeline event: protection_placed with leg_count=2.
    placed_events = [
        event for event in result.events if event.event_type == PipelineEventType.PROTECTION_PLACED
    ]
    assert len(placed_events) == 1
    assert placed_events[0].details.get("leg_count") == 2


def test_post_fill_bracket_short_entry_triggers_inverse_protective_children() -> None:
    components = _components(side=CandidateSide.SHORT)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED]
    )
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=100, close=99))

    assert len(broker.submitted_orders) == 3
    entry_submit, *child_submits = broker.submitted_orders
    assert entry_submit.intent == InternalOrderIntent.OPEN

    stop_child = next(c for c in child_submits if c.intent == InternalOrderIntent.STOP_LOSS)
    target_child = next(c for c in child_submits if c.intent == InternalOrderIntent.TAKE_PROFIT)

    # SHORT entry -> exit side flips to BUY (CandidateSide.LONG on internal enum).
    for child in child_submits:
        assert child.side == CandidateSide.LONG
    # SHORT stop is ABOVE entry, SHORT target is BELOW.
    assert stop_child.stop_price == pytest.approx(105.0)
    assert target_child.limit_price == pytest.approx(90.0)


def test_post_fill_bracket_does_not_fire_when_entry_is_rejected() -> None:
    components = _components(side=CandidateSide.LONG)
    broker = FakeBrokerAdapter([BrokerOrderStatus.REJECTED])
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar())

    # Only entry submitted; no protective children attempted.
    assert len(broker.submitted_orders) == 1
    placed = [e for e in result.events if e.event_type == PipelineEventType.PROTECTION_PLACED]
    assert placed == []


def test_native_alpaca_bracket_attaches_child_prices_on_entry_and_skips_post_fill_path() -> None:
    components = _components(
        side=CandidateSide.LONG,
        execution_mode=ExecutionMode.NATIVE_ALPACA_BRACKET,
    )
    # Native bracket: only the entry is submitted (children are attached
    # to the entry payload, not as independent orders). The FakeBroker
    # only sees the single entry submit.
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED])
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    assert len(broker.submitted_orders) == 1
    entry = broker.submitted_orders[0]
    # Entry now carries the bracket payload.
    assert entry.order_class == "bracket"
    assert entry.bracket_take_profit_limit_price == pytest.approx(110.0)  # close 100 * (1 + 10/100)
    assert entry.bracket_stop_loss_stop_price == pytest.approx(95.0)      # close 100 * (1 - 5/100)
    # No post-fill PROTECTION_PLACED event under native mode.
    placed = [e for e in result.events if e.event_type == PipelineEventType.PROTECTION_PLACED]
    assert placed == []
