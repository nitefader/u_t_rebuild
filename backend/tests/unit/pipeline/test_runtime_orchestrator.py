from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import AlpacaBrokerAdapter, BrokerOrderStatus, FakeBrokerAdapter
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
import backend.app.brokers.alpaca as alpaca_module


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


class FakeAlpacaOrderRequest:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class PipelineAlpacaClient:
    def __init__(self) -> None:
        self.submitted_client_order_ids: list[str] = []
        self.existing_by_client_order_id: dict[str, dict] = {}

    def get_order_by_client_id(self, client_order_id: str):
        try:
            return self.existing_by_client_order_id[client_order_id]
        except KeyError as exc:
            raise RuntimeError("order not found") from exc

    def submit_order(self, *, order_data):
        client_order_id = order_data.kwargs["client_order_id"]
        self.submitted_client_order_ids.append(client_order_id)
        payload = {
            "id": f"alpaca-{client_order_id}",
            "client_order_id": client_order_id,
            "symbol": order_data.kwargs["symbol"],
            "side": "buy",
            "type": "market",
            "qty": str(order_data.kwargs["qty"]),
            "status": "new",
            "filled_qty": "0",
        }
        self.existing_by_client_order_id[client_order_id] = payload
        return payload


class CountingGovernor(PortfolioGovernor):
    def __init__(self) -> None:
        super().__init__()
        self.evaluate_calls = 0

    def evaluate(self, request):  # type: ignore[no-untyped-def]
        self.evaluate_calls += 1
        return super().evaluate(request)


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


def test_full_pipeline_governor_order_manager_alpaca_adapter_broker_sync(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeAlpacaOrderRequest)
    components = _components()
    client = PipelineAlpacaClient()
    adapter = AlpacaBrokerAdapter(trading_client=client, load_env=False)
    governor = CountingGovernor()
    pipeline = _orchestrator(components=components, governor=governor, broker_adapter=adapter)  # type: ignore[arg-type]

    result = pipeline.process_bar(_bar())

    assert governor.evaluate_calls == 1
    assert len(result.orders) == 1
    assert len(result.broker_results) == 1
    assert len(result.ledger_updates) == 1
    assert result.orders[0].program_id == components.program.id
    assert result.broker_results[0].client_order_id == result.orders[0].client_order_id
    assert result.ledger_updates[0].status == InternalOrderStatus.ACCEPTED
    assert client.submitted_client_order_ids == [result.orders[0].client_order_id]


def test_full_pipeline_does_not_submit_when_governor_blocks_with_real_adapter(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeAlpacaOrderRequest)
    client = PipelineAlpacaClient()
    adapter = AlpacaBrokerAdapter(trading_client=client, load_env=False)
    pipeline = _orchestrator(
        governor=PortfolioGovernor(GovernorPolicy(global_kill_active=True)),
        broker_adapter=adapter,  # type: ignore[arg-type]
    )

    result = pipeline.process_bar(_bar())

    assert result.orders == ()
    assert client.submitted_client_order_ids == []


# ---------------------------------------------------------------------------
# Composition-root wiring (Phase 2 slice 2C-followup)
# ---------------------------------------------------------------------------


def test_orchestrator_owns_trade_ledger_and_broker_sync_service() -> None:
    """Construction wires TradeLedger + BrokerSyncService into the order manager."""
    from backend.app.brokers import BrokerSyncService
    from backend.app.orders import TradeLedger

    pipeline = _orchestrator()

    assert isinstance(pipeline.trade_ledger, TradeLedger)
    assert isinstance(pipeline.broker_sync_service, BrokerSyncService)
    # Late binding hooked up.
    assert pipeline.order_manager._broker_sync_service is pipeline.broker_sync_service


def test_orchestrator_seeds_broker_sync_service_freshness_on_construction() -> None:
    """Without the seed, the gate would block the very first opening order."""
    pipeline = _orchestrator()

    state = pipeline.broker_sync_service.current_sync_state(ACCOUNT_ID)
    assert state.is_stale is False


def test_orchestrator_records_successful_poll_after_each_broker_submit() -> None:
    """The synchronous submit path must keep BrokerSyncService freshness alive."""
    pipeline = _orchestrator()

    pipeline.process_bar(_bar(0))
    pipeline.process_bar(_bar(1, open_=99, close=100))
    state = pipeline.broker_sync_service.current_sync_state(ACCOUNT_ID)
    assert state.is_stale is False
    assert state.last_poll_sync_at is not None


def test_orchestrator_attaches_stream_router_to_provided_stream_adapter() -> None:
    """A stream adapter exposing subscribe(emit) gets bound to the router."""

    class FakeStreamAdapter:
        def __init__(self) -> None:
            self.subscribed_callbacks: list = []

        def subscribe(self, emit) -> None:  # type: ignore[no-untyped-def]
            self.subscribed_callbacks.append(emit)

    stream_adapter = FakeStreamAdapter()
    resolved = _components()
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(resolved),
        components=resolved,
        stream_adapter=stream_adapter,
    )

    assert len(stream_adapter.subscribed_callbacks) == 1
    assert stream_adapter.subscribed_callbacks[0] == pipeline.stream_router.route


def test_stream_event_routes_through_orchestrator_router_into_trade_ledger() -> None:
    """A fill event delivered via the router lands as a Trade and updates freshness."""
    from backend.app.brokers import BrokerFillUpdateEvent

    pipeline = _orchestrator()

    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="client-end-to-end",
        symbol="SPY",
        qty=5,
        price=101,
        side="buy",
        broker_execution_id="exec-1",
    )
    pipeline.stream_router.route(fill)

    trades = pipeline.trade_ledger.all()
    assert len(trades) == 1
    assert trades[0].broker_execution_id == "exec-1"
    assert pipeline.broker_sync_service.current_sync_state(ACCOUNT_ID).is_stale is False
