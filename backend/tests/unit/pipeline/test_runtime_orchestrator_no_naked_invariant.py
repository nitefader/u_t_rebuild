"""T-5 (Bracket Program) — no-naked-after-fill invariant.

Doctrine: when a SignalPlan declares stop/target intent and the entry
fills, the runtime MUST place protective children OR surface a
``protection_failed_after_fill`` alarm event so the operator sees the
naked exposure. There is no silent fallback.

Acceptance scenarios:

1. Entry fills, broker REJECTS the protective stop child -> orchestrator
   emits PROTECTION_NAKED with ``rule_id="protection_failed_after_fill"``
   referencing the parent_order_id and the child_order_id.
2. Entry fills with no fill price reported (broker shape error) ->
   orchestrator emits PROTECTION_NAKED with ``reason="missing_fill_price"``.

The protective_placer's empty-plan path (legs == ()) when the SignalPlan
declared intent is also covered as part of doctrine — but the production
SignalPlan always has stop/target rules when the ExecutionPlan preset is
a bracket variant, so the more interesting path is the broker-side
rejection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import BrokerOrderResult, BrokerOrderStatus, FakeBrokerAdapter
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.governor import PortfolioSnapshot
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
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
from backend.app.features import IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.orders import InternalOrderIntent
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


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
        name="No-Naked Strategy",
        entry_rules=[
            SignalRule(
                name="entry_rule",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
                ),
                stop_candidate_feature="5m.low[0]",
                target_candidate_feature="5m.high[0]",
            )
        ],
    )
    strategy_v4 = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="No-Naked Strategy v4",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="5m.close > 5m.open",
                feature_requirements=("5m.close", "5m.open"),
            )
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=5.0),),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=10.0,
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
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
        preset=BracketStopTargetPreset(stop_pct=5.0, target_pct=10.0),
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="No-Naked Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="No-Naked Program",
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


def _bar() -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=99,
        high=102,
        low=97,
        close=100,
        volume=100_000,
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


class _NoFillPriceFakeBroker(FakeBrokerAdapter):
    """A FakeBrokerAdapter variant that reports FILLED but with no
    ``filled_avg_price``. Simulates a broker shape bug. The orchestrator
    must surface PROTECTION_NAKED rather than crash."""

    def submit_order(self, order):  # type: ignore[no-untyped-def]
        result = super().submit_order(order)
        # Force the FILLED status to omit the fill price.
        return result.model_copy(update={"filled_avg_price": None})


def test_no_naked_invariant_emits_alarm_when_protective_child_rejected() -> None:
    """T-5 critic fix: broker REJECTED on a protective child must emit
    PROTECTION_NAKED with rule_id='protection_failed_after_fill' so the
    operator sees a parent-keyed alarm in addition to the per-child
    rejection ledger trail. Stop-leg rejection aborts the loop so the
    target leg is never submitted alone (a target-only "protection"
    consumes margin without downside cover and is worse than naked).
    """

    components = _components()
    # Entry FILLED, first child (stop) REJECTED. Second child slot is
    # never reached because the orchestrator aborts on stop-leg loss.
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.FILLED, BrokerOrderStatus.REJECTED, BrokerOrderStatus.REJECTED]
    )
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        feature_engine=IncrementalFeatureEngine(),
        broker_adapter=broker,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=_strategy_artifact_resolver(components),
    )

    result = pipeline.process_bar(_bar())

    # Per-child NAKED alarm fires.
    naked_events = [
        event for event in result.events if event.event_type == PipelineEventType.PROTECTION_NAKED
    ]
    assert any(
        event.details.get("rule_id") == "protection_failed_after_fill"
        for event in naked_events
    )
    # Parent-level NAKED alarm with reason='all_children_rejected' fires
    # because no child reached the broker successfully (stop rejected,
    # target never attempted).
    parent_naked = [e for e in naked_events if e.details.get("reason") == "all_children_rejected"]
    assert len(parent_naked) == 1

    # Doctrine guard: the entry parent is FILLED; the operator sees the
    # rejected stop child in the ledger plus a parent-keyed alarm event.
    parent = next(
        order for order in pipeline.order_manager.ledger.all() if order.parent_order_id is None
    )
    assert parent.status.value in {"filled", "partially_filled"}
    rejected_children = [
        order
        for order in pipeline.order_manager.ledger.all()
        if order.parent_order_id is not None and order.status.value == "rejected"
    ]
    # FOLLOWUP-A emits one native post-fill OCO child (primary TAKE_PROFIT
    # with attached stop-loss). A broker rejection on that child still means
    # no protective order reached the broker.
    assert len(rejected_children) == 1
    assert rejected_children[0].intent == InternalOrderIntent.TAKE_PROFIT


def test_no_naked_invariant_alarm_on_missing_fill_price() -> None:
    components = _components()
    broker = _NoFillPriceFakeBroker(
        [BrokerOrderStatus.FILLED]
    )
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        feature_engine=IncrementalFeatureEngine(),
        broker_adapter=broker,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=_strategy_artifact_resolver(components),
    )

    result = pipeline.process_bar(_bar())

    naked_events = [
        event for event in result.events if event.event_type == PipelineEventType.PROTECTION_NAKED
    ]
    assert len(naked_events) == 1
    naked = naked_events[0]
    assert naked.details.get("rule_id") == "protection_failed_after_fill"
    assert naked.details.get("reason") == "missing_fill_price"
    assert naked.details.get("parent_order_id") is not None
    # No protective children submitted in the absence of a fill price.
    assert len(broker.submitted_orders) == 1


def test_no_naked_invariant_logs_naked_when_signal_plan_intent_produces_no_legs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the SignalPlan carried intent but ProtectivePlacer produced
    no legs (bug or edge case), the orchestrator surfaces NAKED rather
    than silently leaving the position uncovered."""

    from backend.app.orders.protective_placer import ProtectivePlacementPlan

    components = _components()
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED])
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        feature_engine=IncrementalFeatureEngine(),
        broker_adapter=broker,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=_strategy_artifact_resolver(components),
    )

    # Force ProtectivePlacer to return an empty plan even though the
    # SignalPlan has stop+target intent.
    def _empty_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        return ProtectivePlacementPlan(
            parent_order_id=kwargs["parent_order_id"],
            signal_plan_id=kwargs["signal_plan"].signal_plan_id,
            account_id=kwargs["account_id"],
            covered_qty=0.0,
            legs=(),
        )

    monkeypatch.setattr(
        "backend.app.orders.protective_placer.ProtectiveOrderPlacer.compute_protective_plan",
        _empty_plan,
    )

    result = pipeline.process_bar(_bar())

    naked_events = [
        event for event in result.events if event.event_type == PipelineEventType.PROTECTION_NAKED
    ]
    assert len(naked_events) == 1
    naked = naked_events[0]
    assert naked.details.get("rule_id") == "protection_failed_after_fill"
    assert naked.details.get("reason") == "no_legs_from_intent"
