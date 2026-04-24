from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import BrokerOrderStatus, FakeBrokerAdapter
from backend.app.control_plane import ControlPlane
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
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.features import BatchFeatureEngine, NormalizedBar, ResolvedProgramComponents
from backend.app.governor import GovernorPolicy, PortfolioGovernor
from backend.app.orders import InternalOrderIntent, InternalOrderStatus, OrderManager
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext, ExecutionIntent
import backend.app.pipeline.orchestrator as orchestrator_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _components(*, symbols: list[str] | None = None) -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Pipeline Strategy",
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
        name="Market",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Pipeline Universe",
        symbols=[UniverseSymbol(symbol=symbol) for symbol in (symbols or ["SPY"])],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Pipeline Program",
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
    return DeploymentContext(deployment_id=DEPLOYMENT_ID, program=components.program)


def _bar(index: int = 0, *, open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * index),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000 + index,
    )


def _orchestrator(
    *,
    components: ResolvedProgramComponents | None = None,
    governor: PortfolioGovernor | None = None,
    broker_adapter: FakeBrokerAdapter | None = None,
    order_manager: OrderManager | None = None,
    control_plane: ControlPlane | None = None,
) -> RuntimeOrchestrator:
    resolved = components or _components()
    return RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(resolved),
        components=resolved,
        governor=governor,
        broker_adapter=broker_adapter,
        order_manager=order_manager,
        control_plane=control_plane,
    )


def _exit_intent(components: ResolvedProgramComponents, *, approved: bool = False) -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=DEPLOYMENT_ID,
        program_version_id=components.program.id,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=IntentType.EXIT,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        signal_name="protective_exit",
        reason="protective_exit",
        governor_approved=approved,
    )


def test_end_to_end_signal_to_order_created() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(broker_adapter=broker)

    result = pipeline.process_bar(_bar())

    assert len(result.candidate_intents) == 1
    assert len(result.execution_intents) == 1
    assert len(result.governor_decisions) == 1
    assert result.governor_decisions[0].approved is True
    assert len(result.orders) == 1
    assert result.orders[0].status == InternalOrderStatus.CREATED
    assert len(broker.submitted_orders) == 1
    assert any(event.event_type == PipelineEventType.CANDIDATE_TRADE_INTENT for event in result.events)
    assert any(event.event_type == PipelineEventType.ORDER_CREATED for event in result.events)


def test_governor_blocks_new_opens() -> None:
    pipeline = _orchestrator(governor=PortfolioGovernor(GovernorPolicy(global_kill_active=True)))

    result = pipeline.process_bar(_bar())

    assert len(result.candidate_intents) == 1
    assert len(result.execution_intents) == 1
    assert result.governor_decisions[0].approved is False
    assert result.orders == ()
    assert pipeline.order_manager.ledger.all() == ()


def test_protective_orders_pass_under_pause() -> None:
    components = _components()
    pipeline = _orchestrator(
        components=components,
        governor=PortfolioGovernor(
            GovernorPolicy(
                global_kill_active=True,
                paused_account_ids=frozenset({ACCOUNT_ID}),
                paused_deployment_ids=frozenset({DEPLOYMENT_ID}),
            )
        ),
        broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.FILLED]),
    )

    result = pipeline.process_protective_intent(
        execution_intent=_exit_intent(components),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    assert result.governor_decisions[0].approved is True
    assert result.governor_decisions[0].reason == "protective_exit_allowed"
    assert len(result.orders) == 1
    assert result.orders[0].intent == InternalOrderIntent.STOP_LOSS
    assert result.ledger_updates[0].status == InternalOrderStatus.FILLED


def test_attribution_preserved_account_deployment_program() -> None:
    components = _components()
    result = _orchestrator(components=components).process_bar(_bar())

    ledger_update = result.ledger_updates[0]
    assert ledger_update.account_id == ACCOUNT_ID
    assert ledger_update.deployment_id == DEPLOYMENT_ID
    assert ledger_update.program_id == components.program.id
    assert ledger_update.client_order_id.startswith("utos-aaaaaaaa-open-")


def test_fake_broker_responses_update_ledger() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.PARTIAL_FILL])
    pipeline = _orchestrator(broker_adapter=broker)

    result = pipeline.process_bar(_bar())

    assert result.broker_results[0].status == BrokerOrderStatus.PARTIAL_FILL
    assert result.ledger_updates[0].status == InternalOrderStatus.PARTIALLY_FILLED
    assert result.ledger_updates[0].filled_quantity == 5
    assert pipeline.order_manager.ledger.all()[0].status == InternalOrderStatus.PARTIALLY_FILLED


def test_output_events_include_broker_result_and_ledger_update() -> None:
    result = _orchestrator(broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.FILLED])).process_bar(_bar())

    event_types = [event.event_type for event in result.events]
    assert PipelineEventType.EXECUTION_INTENT in event_types
    assert PipelineEventType.GOVERNOR_DECISION in event_types
    assert PipelineEventType.BROKER_RESULT in event_types
    assert PipelineEventType.LEDGER_UPDATE in event_types


def test_no_component_bypass() -> None:
    source = inspect.getsource(orchestrator_module)

    assert "BatchFeatureEngine" not in source
    assert ".compute(" not in source
    assert "InternalOrder(" not in source
    assert ".can_open_new_position(" in source
    assert ".create_order(" in source
    assert ".submit_order(" in source


def test_control_plane_blocks_new_open_before_order_creation() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    control_plane = ControlPlane(global_kill_active=True)

    result = _orchestrator(broker_adapter=broker, control_plane=control_plane).process_bar(_bar())

    assert len(result.candidate_intents) == 1
    assert result.orders == ()
    assert broker.submitted_orders == []


def test_protective_exits_survive_control_plane_kill() -> None:
    components = _components()
    pipeline = _orchestrator(
        components=components,
        control_plane=ControlPlane(global_kill_active=True),
        broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.FILLED]),
    )

    result = pipeline.process_protective_intent(
        execution_intent=_exit_intent(components),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    assert len(result.orders) == 1
    assert result.orders[0].intent == InternalOrderIntent.STOP_LOSS


def test_pipeline_matches_batch_signal_expectation() -> None:
    components = _components()
    bar = _bar()
    result = _orchestrator(components=components).process_bar(bar)
    pipeline_feature_values = result.execution_intents[0].features_used
    batch_snapshot = BatchFeatureEngine().compute(
        _orchestrator(components=components).feature_plan,
        [bar],
    ).frame_for("SPY", "5m").snapshots[0]

    assert pipeline_feature_values
    assert batch_snapshot.value_for(next(key for key in batch_snapshot.values if "price.close" in key)) == 100
