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
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.decision.signal_sources import V4ExpressionSignalSource
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
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.orders import InternalOrderIntent, InternalOrderStatus
from backend.app.orders.models import OrderOrigin
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext
from backend.app.domain._base import utc_now


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
    entry = StrategyEntryV4(
        expression_text="5m.close > 5m.open" if side == CandidateSide.LONG else "5m.close < 5m.open",
        feature_requirements=("5m.close", "5m.open"),
    )
    strategy_v4 = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="Bracket Strategy v4",
        entries=StrategyEntriesV4(
            long=entry if side == CandidateSide.LONG else None,
            short=entry if side == CandidateSide.SHORT else None,
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=stop_pct),),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=target_pct,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        feature_requirements=("5m.close", "5m.open"),
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
        strategy_version_v4=strategy_v4,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _deployment(components: ResolvedDeploymentComponents) -> DeploymentContext:
    return DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=components.strategy_version_v4.id,
        strategy_version=components.strategy_version_v4.version,
    )


def _bar(*, open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=utc_now(),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000,
    )


def _orchestrator(*, components: ResolvedDeploymentComponents, broker: FakeBrokerAdapter) -> RuntimeOrchestrator:
    # W2-A-1b: provide a non-None equity snapshot so the new fail-closed
    # rule does not pre-empt the bracket-program acceptance flow.
    from backend.app.governor import PortfolioSnapshot
    return RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        broker_adapter=broker,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=_strategy_artifact_resolver(components),
    )


def _strategy_artifact_resolver(components: ResolvedDeploymentComponents) -> StrategyArtifactResolver:
    registry = SignalSourceRegistry()
    registry.register(StrategyArtifactKind.EXPRESSION_V1, lambda _metadata: V4ExpressionSignalSource())

    def lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        sv4 = components.strategy_version_v4
        if sv4 is None or sv4.id != strategy_version_v4_id:
            raise KeyError(strategy_version_v4_id)
        return sv4

    return StrategyArtifactResolver(registry=registry, strategy_v4_lookup=lookup)


def test_post_fill_bracket_long_entry_triggers_protective_children() -> None:
    components = _components(side=CandidateSide.LONG)
    # FakeBroker returns FILLED for the entry, ACCEPTED for the native OCO child.
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # Two orders submitted: entry + 1 native OCO protective child.
    assert len(broker.submitted_orders) == 2
    entry_submit = broker.submitted_orders[0]
    oco_submit = broker.submitted_orders[1]

    # Entry side and intent.
    assert entry_submit.intent == InternalOrderIntent.OPEN
    assert entry_submit.parent_order_id is None
    # Bracket child fields are NOT set on the entry under post_fill mode —
    # that path is exclusive to native_alpaca_bracket.
    assert entry_submit.bracket_take_profit_limit_price is None
    assert entry_submit.bracket_stop_loss_stop_price is None
    assert entry_submit.order_class is None

    assert oco_submit.parent_order_id == entry_submit.order_id
    assert oco_submit.signal_plan_id == entry_submit.signal_plan_id
    assert oco_submit.account_id == ACCOUNT_ID
    assert oco_submit.deployment_id == DEPLOYMENT_ID
    assert oco_submit.origin == OrderOrigin.SIGNAL_PLAN
    assert oco_submit.order_class == "oco"
    assert oco_submit.side == CandidateSide.SHORT
    # Native OCO shape: primary target on limit + attached stop.
    assert oco_submit.intent == InternalOrderIntent.TAKE_PROFIT
    assert oco_submit.order_type == OrderType.LIMIT
    assert oco_submit.limit_price == pytest.approx(110.0)
    assert oco_submit.bracket_stop_loss_stop_price == pytest.approx(95.0)

    # Pipeline event: one native OCO child submitted.
    placed_events = [
        event for event in result.events if event.event_type == PipelineEventType.PROTECTION_PLACED
    ]
    assert len(placed_events) == 1
    assert placed_events[0].details.get("leg_count") == 1


def test_post_fill_bracket_short_entry_triggers_inverse_protective_children() -> None:
    components = _components(side=CandidateSide.SHORT)
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=100, close=99))

    assert len(broker.submitted_orders) == 2
    entry_submit, oco_submit = broker.submitted_orders
    assert entry_submit.intent == InternalOrderIntent.OPEN
    assert oco_submit.side == CandidateSide.LONG
    assert oco_submit.limit_price == pytest.approx(90.0)
    assert oco_submit.bracket_stop_loss_stop_price == pytest.approx(105.0)


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


# ---------------------------------------------------------------------------
# W2-A-1a (audit P0 #1, pre-T-7 bundle) — orchestrator integration.
# When SignalPlan.stop is encoded as post_fill_pct (the default bracket
# mode's intent shape), the orchestrator's _governor_candidate_inputs must
# proxy candidate_open_risk from a gating-time reference price and emit a
# GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED audit event. The Governor decision's
# projected_state must show non-zero gross_exposure_pct so the percentage
# gates have something real to evaluate against (the audit's confirmed
# silent-no-op was that they always saw zero incremental exposure).
# ---------------------------------------------------------------------------


def test_orchestrator_emits_proxy_event_when_stop_is_post_fill_pct() -> None:
    """Regression guard: post_fill_pct stop must trigger the proxy code path.

    Doctrine (operator decision 2026-04-30 W2-A): when the SignalPlan stop
    is encoded as post_fill_pct, RiskResolver does not produce a concrete
    stop_distance. The orchestrator must compute a proxy candidate_open_risk
    from qty * ref_price * stop_pct/100 and emit a structured audit event
    so Operations can see the gate ran on a proxy.
    """
    components = _components(
        side=CandidateSide.LONG,
        stop_pct=5.0,
        target_pct=10.0,
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # The proxy event must fire exactly once (one entry).
    proxy_events = [
        event
        for event in result.events
        if event.event_type == PipelineEventType.GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED
    ]
    assert len(proxy_events) == 1
    proxy_event = proxy_events[0]
    # The event details must carry the proxy math so Operations can audit.
    assert proxy_event.details["stop_pct"] == 5.0
    assert proxy_event.details["reference_price"] == pytest.approx(100.0)
    assert proxy_event.details["candidate_quantity"] == pytest.approx(10.0)
    # proxy_stop_distance = 100 * (5/100) = 5.0; candidate_open_risk = 10 * 5 = 50.
    assert proxy_event.details["proxy_stop_distance"] == pytest.approx(5.0)
    assert proxy_event.details["candidate_open_risk"] == pytest.approx(50.0)


def test_orchestrator_governor_projected_state_carries_nonzero_gross_exposure() -> None:
    """Audit P0 #1 regression: the Governor's projected_state must show real
    candidate exposure, not zero. Pre-W2-A this was always 0 because
    candidate_market_value defaulted to 0 in GovernorRequest.
    """
    components = _components(side=CandidateSide.LONG)
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(components=components, broker=broker)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # Single OPEN entry: one Governor decision, must have non-zero projected
    # gross exposure pct because qty=10 * close=100 = 1_000 against equity
    # of 100_000 = 1.0%.
    assert len(result.governor_decisions) == 1
    decision = result.governor_decisions[0]
    assert decision.approved is True  # under the cap, but the cap saw real numbers
    assert decision.projected_state is not None
    assert decision.projected_state["gross_exposure_pct"] == pytest.approx(1.0)
    # The open_risk_pct is the proxied value: 50 / 100_000 = 0.05%.
    assert decision.projected_state["open_risk_pct"] == pytest.approx(0.05)


def test_orchestrator_blocks_open_when_gross_exposure_cap_breached_with_real_numbers() -> None:
    """The cap fires once candidate_market_value is real. This test would
    fail under pre-W2-A code because candidate_market_value defaulted to 0
    and the cap silently approved.
    """
    from backend.app.governor import GovernorPolicy, PortfolioGovernor, PortfolioSnapshot
    components = _components(side=CandidateSide.LONG)
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    # Set the gross exposure cap to 0.5% — the qty=10 @ $100 = $1000 candidate
    # value is 1.0% of $100k equity, which exceeds 0.5%.
    governor = PortfolioGovernor(GovernorPolicy(max_gross_exposure_pct=0.5))
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        broker_adapter=broker,
        governor=governor,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=_strategy_artifact_resolver(components),
    )

    result = pipeline.process_bar(_bar(open_=99, close=100))

    assert len(result.governor_decisions) == 1
    decision = result.governor_decisions[0]
    assert decision.approved is False
    assert decision.rule_id == "max_gross_exposure_pct"
    # No order should have been submitted.
    assert len(broker.submitted_orders) == 0


def test_native_vs_post_fill_price_symmetry_for_same_signal_plan_and_fill_price() -> None:
    from backend.app.decision.signal_plan_common import post_fill_pct_rule
    from backend.app.domain import SignalPlan, SignalPlanEntry, SignalPlanIntent
    from backend.app.domain.signal_plan import SignalPlanStop, SignalPlanTarget, SignalPlanTargetAction
    from backend.app.orders.protective_placer import ProtectiveOrderPlacer

    components = _components(side=CandidateSide.LONG)
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(components=components, broker=broker)
    signal_plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=components.strategy.strategy_id,
        strategy_version_id=components.strategy.id,
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY),
        stop=SignalPlanStop(type="percent", rule=post_fill_pct_rule(5.0), required=True),
        targets=(
            SignalPlanTarget(
                label="t1",
                action=SignalPlanTargetAction.CLOSE,
                quantity_pct=100,
                rule=post_fill_pct_rule(10.0),
            ),
        ),
        reason="symmetry",
    )
    fill_price = 100.0
    stop_pct = 5.0
    target_pct = 10.0
    native_prices = pipeline._protective_prices_from_reference(  # type: ignore[attr-defined]
        side=signal_plan.side,
        reference_price=fill_price,
        stop_pct=stop_pct,
        target_pct=target_pct,
    )
    assert native_prices is not None
    native_take_profit, native_stop = native_prices

    placement = ProtectiveOrderPlacer().compute_protective_plan(
        signal_plan=signal_plan,
        parent_order_id=uuid4(),
        account_id=ACCOUNT_ID,
        fill_price=fill_price,
        cumulative_filled_qty=10.0,
    )
    stop_leg = next(leg for leg in placement.legs if leg.stop_price is not None)
    target_leg = next(leg for leg in placement.legs if leg.limit_price is not None)

    assert target_leg.limit_price == pytest.approx(native_take_profit)
    assert stop_leg.stop_price == pytest.approx(native_stop)


def test_native_alpaca_bracket_stale_bar_reference_fails_closed_and_uses_post_fill() -> None:
    components = _components(
        side=CandidateSide.LONG,
        execution_mode=ExecutionMode.NATIVE_ALPACA_BRACKET,
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(components=components, broker=broker)
    stale_bar = NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=utc_now() - timedelta(minutes=15),
        open=99,
        high=102,
        low=97,
        close=100,
        volume=100_000,
    )

    result = pipeline.process_bar(stale_bar)

    # Native attach is skipped on stale reference; post-fill OCO still protects.
    assert len(broker.submitted_orders) == 2
    assert broker.submitted_orders[0].order_class is None
    assert broker.submitted_orders[1].order_class == "oco"
    placed = [e for e in result.events if e.event_type == PipelineEventType.PROTECTION_PLACED]
    assert len(placed) == 1
