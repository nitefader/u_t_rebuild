from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import AlpacaBrokerAdapter, BrokerOrderStatus, BrokerPositionSide, BrokerPositionSnapshot, FakeBrokerAdapter
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.control_plane import ControlPlane
from backend.app.decision import SignalEvaluation
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    CandidateSide,
    CandidateTradeIntent,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    IntentType,
    LogicalExitRuleKind,
    OrderType,
    RiskProfileVersion,
    RiskResolverResult,
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanSide,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    TradingMode,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyLogicalExitV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import FeatureHydrationBarsRequest, IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.governor import BrokerSyncFreshness, GovernorPolicy, PortfolioGovernor, PortfolioSnapshot
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext
import backend.app.pipeline.orchestrator as orchestrator_module
import backend.app.brokers.alpaca as alpaca_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _components(*, symbols: list[str] | None = None, include_exit_rule: bool = False) -> ResolvedDeploymentComponents:
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
        exit_rules=[
            SignalRule(
                name="close_below_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.EXIT,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.LESS_THAN,
                    right_feature="5m.open[0]",
                ),
            )
        ]
        if include_exit_rule
        else [],
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
    return ResolvedDeploymentComponents(
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _components_v4(*, bars_since: int = 5) -> ResolvedDeploymentComponents:
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="V4 Bars Exit",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="1m.close < 1m.open",
                feature_requirements=("1m.close", "1m.open"),
            )
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0),),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=3.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        logical_exits=StrategyLogicalExitsV4(
            long=(StrategyLogicalExitV4(template_id="bars_since", params={"bars": bars_since}),),
        ),
        feature_requirements=("1m.close", "1m.open"),
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="1m Controls",
        timeframe="1m",
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
        name="V4 Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    return ResolvedDeploymentComponents(
        strategy=None,
        strategy_version_v4=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _deployment(components: ResolvedDeploymentComponents) -> DeploymentContext:
    if components.strategy_version_v4 is not None and components.strategy is None:
        return DeploymentContext(
            deployment_id=DEPLOYMENT_ID,
            strategy_version_id=components.strategy_version_v4.id,
            strategy_version=components.strategy_version_v4.version,
        )
    return DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
    )


def _strategy_artifact_resolver(
    components: ResolvedDeploymentComponents,
) -> StrategyArtifactResolver:
    registry = SignalSourceRegistry()
    registry.register(
        StrategyArtifactKind.EXPRESSION_V1,
        lambda _metadata: V4ExpressionSignalSource(),
    )

    def lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        sv4 = components.strategy_version_v4
        if sv4 is None or sv4.id != strategy_version_v4_id:
            raise KeyError(strategy_version_v4_id)
        return sv4

    return StrategyArtifactResolver(
        registry=registry,
        strategy_v4_lookup=lookup,
    )


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


def _bar_1m(index: int = 0, *, open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="1m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=index),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000 + index,
    )


def _position(
    *,
    account_id: UUID = ACCOUNT_ID,
    deployment_id: UUID = DEPLOYMENT_ID,
    strategy_id: UUID | None = None,
    opening_signal_plan_id: UUID | None = None,
    position_lineage_id: UUID | None = None,
    qty: float = 10,
    status: str | None = None,
) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=account_id,
        symbol="SPY",
        qty=qty,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=qty * 100,
        unrealized_pl=0,
        deployment_id=deployment_id,
        strategy_id=strategy_id or uuid4(),
        opening_signal_plan_id=opening_signal_plan_id or uuid4(),
        position_lineage_id=position_lineage_id or uuid4(),
        status=status,
    )


def _filled_signal_plan_open_order(
    *,
    components: ResolvedDeploymentComponents,
    opening_signal_plan_id: UUID,
    position_lineage_id: UUID,
    created_at: datetime,
    qty: float = 10,
) -> InternalOrder:
    strategy_id = (
        components.strategy_version_v4.strategy_v4_id
        if components.strategy_version_v4 is not None
        else components.strategy.strategy_id
    )
    strategy_version_id = (
        components.strategy_version_v4.id
        if components.strategy_version_v4 is not None
        else components.strategy.id
    )
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"sp-{uuid4()}",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        signal_plan_id=opening_signal_plan_id,
        opening_signal_plan_id=opening_signal_plan_id,
        current_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=qty,
        filled_quantity=qty,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.FILLED,
        created_at=created_at,
        updated_at=created_at,
    )


class PositionReader:
    def __init__(self, positions: tuple[BrokerPositionSnapshot, ...]) -> None:
        self.positions = positions
        self.deployment_queries: list[UUID] = []

    def list_broker_position_snapshots_by_deployment(self, deployment_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        self.deployment_queries.append(deployment_id)
        return tuple(position for position in self.positions if position.deployment_id == deployment_id)


class HydrationBarsSource:
    def __init__(self, bars_by_key: dict[tuple[str, str], tuple[NormalizedBar, ...]]) -> None:
        self.bars_by_key = bars_by_key
        self.requests: list[FeatureHydrationBarsRequest] = []

    def fetch_bars(self, request: FeatureHydrationBarsRequest):
        self.requests.append(request)
        return self.bars_by_key.get((request.symbol.upper(), request.timeframe), ())


class ExitOnlySignalEngine:
    def evaluate(self, strategy, snapshot, *, position_contexts=None):  # type: ignore[no-untyped-def]
        # Honor the new doctrine: exit candidates only fire when there's an
        # open position to exit. The orchestrator now supplies position_contexts
        # built from the position_reader.
        ctx = (position_contexts or {}).get(snapshot.symbol)
        if ctx is None or not ctx.has_position:
            return SignalEvaluation(intents=())
        return SignalEvaluation(
            intents=(
                CandidateTradeIntent(
                    timestamp=snapshot.timestamp,
                    symbol=snapshot.symbol,
                    side=CandidateSide.LONG,
                    intent_type=IntentType.EXIT,
                    signal_name="logical_exit",
                    reason="signal_condition_true",
                    feature_values_used={},
                ),
            )
        )


def _orchestrator(
    *,
    components: ResolvedDeploymentComponents | None = None,
    governor: PortfolioGovernor | None = None,
    broker_adapter: FakeBrokerAdapter | None = None,
    order_manager: OrderManager | None = None,
    control_plane: ControlPlane | None = None,
    account_ids: tuple[UUID, ...] | None = None,
    position_reader: object | None = None,
    signal_engine: object | None = None,
    portfolio_snapshot: PortfolioSnapshot | None = None,
) -> RuntimeOrchestrator:
    resolved = components or _components()
    # W2-A-1b: tests that don't intentionally exercise the new
    # portfolio_equity_unavailable fail-closed rule get a default snapshot
    # with non-None equity. Tests that probe equity=None must pass an
    # explicit ``portfolio_snapshot=PortfolioSnapshot()``.
    return RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        account_ids=account_ids,
        deployment=_deployment(resolved),
        components=resolved,
        governor=governor,
        broker_adapter=broker_adapter,
        order_manager=order_manager,
        control_plane=control_plane,
        position_reader=position_reader,
        signal_engine=signal_engine,  # type: ignore[arg-type]
        portfolio_snapshot=(
            portfolio_snapshot
            if portfolio_snapshot is not None
            else PortfolioSnapshot(equity=100_000)
        ),
        strategy_artifact_resolver=(
            _strategy_artifact_resolver(resolved)
            if resolved.strategy_version_v4 is not None
            else None
        ),
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

    def evaluate(self, request, **kwargs):  # type: ignore[no-untyped-def]
        # Slice A: accept and forward **kwargs so this subclass stays
        # compatible if a future test wires a resolver alongside it
        # (the resolver passes policy_override=...).
        self.evaluate_calls += 1
        return super().evaluate(request, **kwargs)


def _protective_signal_plan(components: ResolvedDeploymentComponents) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=components.strategy.strategy_id,
        strategy_version_id=components.strategy.id,
        watchlist_snapshot_id=components.universe.id,
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.STOP,
        opening_signal_plan_id=uuid4(),
        related_position_lineage_id=uuid4(),
        created_at=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        reason="protective_exit",
    )


def test_end_to_end_signal_to_order_created() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(broker_adapter=broker)

    result = pipeline.process_bar(_bar())

    assert len(result.candidate_intents) == 1
    assert len(result.signal_plans) == 1
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
    assert len(result.signal_plans) == 1
    assert result.governor_decisions[0].approved is False
    assert result.orders == ()
    assert pipeline.order_manager.ledger.all() == ()


def test_protective_orders_pass_under_pause() -> None:
    components = _components()
    position_lineage_id = uuid4()
    opening_signal_plan_id = uuid4()
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
        position_reader=PositionReader(
            (
                _position(
                    strategy_id=components.strategy.strategy_id,
                    opening_signal_plan_id=opening_signal_plan_id,
                    position_lineage_id=position_lineage_id,
                ),
            )
        ),
    )

    result = pipeline.process_protective_signal_plan(
        signal_plan=_protective_signal_plan(components),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    assert result.governor_decisions[0].approved is True
    assert result.governor_decisions[0].reason == "protective_exit_allowed"
    assert len(result.orders) == 1
    assert result.signal_plans[0].intent.value == "stop"
    assert result.account_evaluations[0].signal_plan_id == result.signal_plans[0].signal_plan_id
    assert result.orders[0].origin.value == "signal_plan"
    assert result.orders[0].signal_plan_id == result.signal_plans[0].signal_plan_id
    assert result.signal_plans[0].opening_signal_plan_id == opening_signal_plan_id
    assert result.orders[0].opening_signal_plan_id == opening_signal_plan_id
    assert result.orders[0].position_lineage_id == position_lineage_id
    assert result.orders[0].side == CandidateSide.SHORT
    assert result.orders[0].intent == InternalOrderIntent.STOP_LOSS
    assert result.ledger_updates[0].status == InternalOrderStatus.FILLED


def test_attribution_preserved_account_deployment_signal_plan() -> None:
    components = _components()
    result = _orchestrator(components=components).process_bar(_bar())

    ledger_update = result.ledger_updates[0]
    signal_plan = result.signal_plans[0]
    evaluation = result.account_evaluations[0]
    assert ledger_update.account_id == ACCOUNT_ID
    assert ledger_update.deployment_id == DEPLOYMENT_ID
    assert ledger_update.strategy_id == components.strategy.strategy_id
    assert ledger_update.strategy_version_id == components.strategy.id
    assert ledger_update.signal_plan_id == signal_plan.signal_plan_id
    assert ledger_update.account_evaluation_id == evaluation.evaluation_id
    assert ledger_update.client_order_id.startswith(f"sigplan-{ACCOUNT_ID.hex[:8]}-{signal_plan.signal_plan_id.hex[:8]}-open-")


def test_one_signal_plan_fans_out_to_multiple_account_evaluations_and_orders() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(
        broker_adapter=broker,
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
    )

    result = pipeline.process_bar(_bar())

    assert len(result.signal_plans) == 1
    signal_plan_id = result.signal_plans[0].signal_plan_id
    assert [evaluation.account_id for evaluation in result.account_evaluations] == [ACCOUNT_ID, OTHER_ACCOUNT_ID]
    assert {evaluation.signal_plan_id for evaluation in result.account_evaluations} == {signal_plan_id}
    assert [order.account_id for order in result.orders] == [ACCOUNT_ID, OTHER_ACCOUNT_ID]
    assert {order.signal_plan_id for order in result.orders} == {signal_plan_id}
    assert len(broker.submitted_orders) == 2


def test_deployment_entry_signal_plan_comes_from_watchlist_universe() -> None:
    components = _components(symbols=["SPY"])
    result = _orchestrator(components=components).process_bar(_bar(open_=99, close=100))

    assert len(result.signal_plans) == 1
    assert result.signal_plans[0].intent == SignalPlanIntent.OPEN
    assert result.signal_plans[0].deployment_id == DEPLOYMENT_ID
    assert result.signal_plans[0].strategy_id == components.strategy.strategy_id
    assert result.signal_plans[0].watchlist_snapshot_id == components.universe.id
    allocations = result.account_evaluations[0].risk_resolver_result.leg_allocations
    assert [allocation.leg_label for allocation in allocations] == ["entry", "stop", "T1"]
    assert allocations[0].resolved_quantity == 10
    assert allocations[1].lifecycle_intent == SignalPlanIntent.STOP
    assert allocations[2].lifecycle_intent == SignalPlanIntent.TARGET


def test_deployment_exit_signal_plan_comes_from_account_position() -> None:
    components = _components(include_exit_rule=True)
    position_lineage_id = uuid4()
    opening_signal_plan_id = uuid4()
    position = _position(
        strategy_id=components.strategy.strategy_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )
    reader = PositionReader((position,))
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])

    result = _orchestrator(
        components=components,
        broker_adapter=broker,
        position_reader=reader,
    ).process_bar(_bar(open_=100, close=99))

    assert reader.deployment_queries == [DEPLOYMENT_ID]
    assert len(result.signal_plans) == 1
    assert result.signal_plans[0].intent == SignalPlanIntent.LOGICAL_EXIT
    assert result.signal_plans[0].deployment_id == DEPLOYMENT_ID
    assert result.signal_plans[0].opening_signal_plan_id == opening_signal_plan_id
    assert result.signal_plans[0].related_position_lineage_id == position_lineage_id
    assert result.orders[0].position_lineage_id == position_lineage_id
    assert result.orders[0].intent == InternalOrderIntent.LOGICAL_EXIT
    assert len(broker.submitted_orders) == 1


def test_logical_exit_feature_condition_can_fire_on_first_live_bar_after_hydration() -> None:
    components = _components(include_exit_rule=True)
    exit_rule = components.strategy.exit_rules[0].model_copy(
        update={
            "condition": ConditionNode(
                left_feature="5m.close[0]",
                operator=ConditionOperator.LESS_THAN,
                right_feature="5m.low[1]",
            )
        }
    )
    components = components.model_copy(
        update={
            "strategy": components.strategy.model_copy(update={"exit_rules": (exit_rule,)})
        }
    )
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    position = _position(
        strategy_id=components.strategy.strategy_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(
        components=components,
        broker_adapter=broker,
        position_reader=PositionReader((position,)),
    )
    warmup_bars = (
        _bar(0, open_=100, close=105),
        _bar(1, open_=100, close=105),
    )

    hydration = pipeline.hydrate_features(
        symbols=("SPY",),
        as_of=warmup_bars[-1].timestamp,
        bars_source=HydrationBarsSource({("SPY", "5m"): warmup_bars}),
    )
    result = pipeline.process_bar(_bar(2, open_=100, close=97))

    assert hydration.success is True
    assert len(result.signal_plans) == 1
    assert result.signal_plans[0].intent == SignalPlanIntent.LOGICAL_EXIT
    assert result.signal_plans[0].opening_signal_plan_id == opening_signal_plan_id
    assert result.signal_plans[0].related_position_lineage_id == position_lineage_id
    assert result.orders[0].intent == InternalOrderIntent.LOGICAL_EXIT
    assert len(broker.submitted_orders) == 1


def test_v4_bars_since_logical_exit_uses_position_lineage_order_age() -> None:
    components = _components_v4(bars_since=5)
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    current_bar = _bar_1m(index=5, open_=100, close=101)
    position = _position(
        strategy_id=components.strategy_version_v4.strategy_v4_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    manager = OrderManager(broker_adapter=broker)
    manager.ledger.add(
        _filled_signal_plan_open_order(
            components=components,
            opening_signal_plan_id=opening_signal_plan_id,
            position_lineage_id=position_lineage_id,
            created_at=current_bar.timestamp - timedelta(minutes=5),
        )
    )

    result = _orchestrator(
        components=components,
        broker_adapter=broker,
        order_manager=manager,
        position_reader=PositionReader((position,)),
    ).process_bar(current_bar)

    assert len(result.signal_plans) == 1
    plan = result.signal_plans[0]
    assert plan.intent == SignalPlanIntent.LOGICAL_EXIT
    assert plan.logical_exit is not None
    assert plan.logical_exit.rule.kind == LogicalExitRuleKind.BARS_SINCE_ENTRY
    assert plan.logical_exit.rule.bars == 5
    assert plan.opening_signal_plan_id == opening_signal_plan_id
    assert plan.related_position_lineage_id == position_lineage_id
    assert result.orders[0].intent == InternalOrderIntent.LOGICAL_EXIT
    assert result.orders[0].position_lineage_id == position_lineage_id
    assert len(broker.submitted_orders) == 1


def test_v4_bars_since_logical_exit_waits_before_configured_bar_count() -> None:
    components = _components_v4(bars_since=5)
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    current_bar = _bar_1m(index=4, open_=100, close=101)
    position = _position(
        strategy_id=components.strategy_version_v4.strategy_v4_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )
    manager = OrderManager()
    manager.ledger.add(
        _filled_signal_plan_open_order(
            components=components,
            opening_signal_plan_id=opening_signal_plan_id,
            position_lineage_id=position_lineage_id,
            created_at=current_bar.timestamp - timedelta(minutes=4),
        )
    )

    result = _orchestrator(
        components=components,
        order_manager=manager,
        position_reader=PositionReader((position,)),
    ).process_bar(current_bar)

    assert result.signal_plans == ()
    assert result.orders == ()


def test_logical_exit_cancels_superseded_passive_exit_before_submit() -> None:
    components = _components(include_exit_rule=True)
    position_lineage_id = uuid4()
    opening_signal_plan_id = uuid4()
    position = _position(
        strategy_id=components.strategy.strategy_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED])
    manager = OrderManager(broker_adapter=broker)
    target_plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=components.strategy.strategy_id,
        strategy_version_id=components.strategy.id,
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.TARGET,
        opening_signal_plan_id=opening_signal_plan_id,
        related_position_lineage_id=position_lineage_id,
        reason="target",
    )
    target_order = manager.create_signal_plan_order(
        account_id=ACCOUNT_ID,
        signal_plan=target_plan,
        account_evaluation=AccountSignalPlanEvaluation(
            evaluation_id=uuid4(),
            account_id=ACCOUNT_ID,
            signal_plan_id=target_plan.signal_plan_id,
            deployment_id=DEPLOYMENT_ID,
            strategy_id=components.strategy.strategy_id,
            status=AccountEvaluationStatus.ACCEPTED,
            participation_decision=AccountParticipationDecision.PARTICIPATE,
        ),
        risk_result=RiskResolverResult(
            account_id=ACCOUNT_ID,
            signal_plan_id=target_plan.signal_plan_id,
            allowed=True,
            resolved_quantity=5,
        ),
        governor_decision=GovernorDecisionTrace(
            governor_decision_id=uuid4(),
            account_id=ACCOUNT_ID,
            signal_plan_id=target_plan.signal_plan_id,
            status=GovernorDecisionStatus.APPROVED,
            approved=True,
            reasons=("approved",),
        ),
        leg_label="T1",
    )
    broker.submit_order(target_order)

    result = _orchestrator(
        components=components,
        broker_adapter=broker,
        order_manager=manager,
        position_reader=PositionReader((position,)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    target_update = manager.ledger.get(target_order.order_id)
    assert target_update.status == InternalOrderStatus.CANCELED
    assert target_update.cancel_requested_at is not None
    assert broker.canceled_client_order_ids == [target_order.client_order_id]
    assert len(result.orders) == 1
    assert result.orders[0].intent == InternalOrderIntent.LOGICAL_EXIT
    assert broker.submitted_orders[-1].client_order_id == result.orders[0].client_order_id


def test_deployment_exit_does_not_depend_on_current_watchlist_membership() -> None:
    components = _components(symbols=["QQQ"], include_exit_rule=True)
    position = _position(strategy_id=components.strategy.strategy_id)
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])

    result = _orchestrator(
        components=components,
        broker_adapter=broker,
        position_reader=PositionReader((position,)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    assert len(result.signal_plans) == 1
    assert result.signal_plans[0].symbol == "SPY"
    assert result.signal_plans[0].intent == SignalPlanIntent.LOGICAL_EXIT
    assert len(result.orders) == 1
    assert len(broker.submitted_orders) == 1


def test_deployment_exit_multi_account_act_ignore_independently() -> None:
    third_account_id = UUID("33333333-4444-5555-6666-777777777777")
    components = _components(include_exit_rule=True)
    active_position = _position(account_id=ACCOUNT_ID, strategy_id=components.strategy.strategy_id)
    closed_position = _position(
        account_id=OTHER_ACCOUNT_ID,
        strategy_id=components.strategy.strategy_id,
        qty=0,
        status="closed",
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])

    result = _orchestrator(
        components=components,
        broker_adapter=broker,
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID, third_account_id),
        position_reader=PositionReader((active_position, closed_position)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    assert len(result.signal_plans) == 1
    assert [evaluation.account_id for evaluation in result.account_evaluations] == [
        ACCOUNT_ID,
        OTHER_ACCOUNT_ID,
        third_account_id,
    ]
    assert result.account_evaluations[0].participation_decision == AccountParticipationDecision.PARTICIPATE
    assert result.account_evaluations[1].participation_decision == AccountParticipationDecision.IGNORE
    assert result.account_evaluations[1].rejection_reasons == ("position_already_closed",)
    assert result.account_evaluations[2].participation_decision == AccountParticipationDecision.IGNORE
    assert result.account_evaluations[2].rejection_reasons == ("account_has_no_matching_position",)
    assert [order.account_id for order in result.orders] == [ACCOUNT_ID]


def test_deployment_exit_blocks_ambiguous_multiple_active_lineages_for_same_account() -> None:
    components = _components(include_exit_rule=True)
    first = _position(account_id=ACCOUNT_ID, strategy_id=components.strategy.strategy_id)
    second = _position(account_id=ACCOUNT_ID, strategy_id=components.strategy.strategy_id)

    result = _orchestrator(
        components=components,
        broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED]),
        position_reader=PositionReader((first, second)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    assert result.orders == ()
    assert len(result.account_evaluations) == 1
    assert result.account_evaluations[0].status == AccountEvaluationStatus.BLOCKED
    assert result.account_evaluations[0].rejection_reasons == ("multiple_active_position_lineages_for_account",)


def test_deployment_exit_preserves_account_specific_opening_lineage_and_side() -> None:
    components = _components(include_exit_rule=True)
    long_opening_id = uuid4()
    long_lineage_id = uuid4()
    short_opening_id = uuid4()
    short_lineage_id = uuid4()
    long_position = _position(
        account_id=ACCOUNT_ID,
        strategy_id=components.strategy.strategy_id,
        opening_signal_plan_id=long_opening_id,
        position_lineage_id=long_lineage_id,
    )
    short_position = BrokerPositionSnapshot(
        account_id=OTHER_ACCOUNT_ID,
        symbol="SPY",
        qty=-4,
        side=BrokerPositionSide.SHORT,
        avg_entry_price=100,
        market_value=-400,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=components.strategy.strategy_id,
        opening_signal_plan_id=short_opening_id,
        position_lineage_id=short_lineage_id,
    )

    result = _orchestrator(
        components=components,
        broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED]),
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
        position_reader=PositionReader((long_position, short_position)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    orders_by_account = {order.account_id: order for order in result.orders}
    assert orders_by_account[ACCOUNT_ID].opening_signal_plan_id == long_opening_id
    assert orders_by_account[ACCOUNT_ID].position_lineage_id == long_lineage_id
    assert orders_by_account[ACCOUNT_ID].side == CandidateSide.SHORT
    assert orders_by_account[OTHER_ACCOUNT_ID].opening_signal_plan_id == short_opening_id
    assert orders_by_account[OTHER_ACCOUNT_ID].position_lineage_id == short_lineage_id
    assert orders_by_account[OTHER_ACCOUNT_ID].side == CandidateSide.LONG


def test_deployment_exit_ignores_positions_from_other_deployments() -> None:
    components = _components(include_exit_rule=True)
    other_deployment_position = _position(
        deployment_id=UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff"),
        strategy_id=components.strategy.strategy_id,
    )
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])

    result = _orchestrator(
        components=components,
        broker_adapter=broker,
        position_reader=PositionReader((other_deployment_position,)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    assert result.signal_plans == ()
    assert result.account_evaluations == ()
    assert result.orders == ()
    assert broker.submitted_orders == []


def test_deployment_exit_reads_positions_without_mutating_broker_truth() -> None:
    components = _components(include_exit_rule=True)
    position = _position(strategy_id=components.strategy.strategy_id)
    reader = PositionReader((position,))
    before = reader.positions

    result = _orchestrator(
        components=components,
        position_reader=reader,
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    assert reader.positions == before
    assert result.signal_plans[0].deployment_id == DEPLOYMENT_ID
    assert result.orders[0].deployment_id == DEPLOYMENT_ID


def test_account_without_position_ignores_exit_signal_plan() -> None:
    components = _components(include_exit_rule=True)

    result = _orchestrator(
        components=components,
        account_ids=(ACCOUNT_ID,),
        position_reader=PositionReader((_position(account_id=OTHER_ACCOUNT_ID, strategy_id=components.strategy.strategy_id),)),
        signal_engine=ExitOnlySignalEngine(),
    ).process_bar(_bar(open_=100, close=99))

    assert len(result.signal_plans) == 1
    assert result.account_evaluations[0].account_id == ACCOUNT_ID
    assert result.account_evaluations[0].participation_decision == AccountParticipationDecision.IGNORE
    assert result.account_evaluations[0].rejection_reasons == ("account_has_no_matching_position",)
    assert result.orders == ()


def test_multi_account_fanout_rejects_one_account_without_blocking_other() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    pipeline = _orchestrator(
        broker_adapter=broker,
        governor=PortfolioGovernor(GovernorPolicy(paused_account_ids=frozenset({OTHER_ACCOUNT_ID}))),
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
    )

    result = pipeline.process_bar(_bar())

    assert len(result.signal_plans) == 1
    assert [evaluation.account_id for evaluation in result.account_evaluations] == [ACCOUNT_ID, OTHER_ACCOUNT_ID]
    assert result.account_evaluations[0].status == AccountEvaluationStatus.ACCEPTED
    assert result.account_evaluations[1].status == AccountEvaluationStatus.BLOCKED
    assert [order.account_id for order in result.orders] == [ACCOUNT_ID]
    assert len(broker.submitted_orders) == 1


def test_multi_account_governor_uses_account_specific_broker_freshness() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    resolved = _components()
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
        deployment=_deployment(resolved),
        components=resolved,
        broker_adapter=broker,
        broker_freshness_by_account={
            ACCOUNT_ID: BrokerSyncFreshness(is_stale=False),
            OTHER_ACCOUNT_ID: BrokerSyncFreshness(is_stale=True, reason="other_account_stale"),
        },
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )

    result = pipeline.process_bar(_bar())

    assert [evaluation.account_id for evaluation in result.account_evaluations] == [ACCOUNT_ID, OTHER_ACCOUNT_ID]
    assert result.account_evaluations[0].status == AccountEvaluationStatus.ACCEPTED
    assert result.account_evaluations[1].status == AccountEvaluationStatus.BLOCKED
    assert result.account_evaluations[1].rejection_reasons == ("other_account_stale",)
    assert [order.account_id for order in result.orders] == [ACCOUNT_ID]


def test_reprocessing_same_account_signal_plan_does_not_resubmit_broker_order() -> None:
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    resolved = _components()
    signal_plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=resolved.strategy.strategy_id,
        strategy_version_id=resolved.strategy.id,
        watchlist_snapshot_id=resolved.universe.id,
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY),
    )

    class FixedSignalPlanBuilder:
        def build_from_candidate(self, **kwargs):  # type: ignore[no-untyped-def]
            return signal_plan

    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(resolved),
        components=resolved,
        broker_adapter=broker,
        signal_plan_builder=FixedSignalPlanBuilder(),  # type: ignore[arg-type]
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )

    first = pipeline.process_bar(_bar())
    second = pipeline.process_bar(_bar(1))

    assert len(first.orders) == 1
    assert len(first.broker_results) == 1
    assert len(second.orders) == 1
    assert second.orders[0].order_id == first.orders[0].order_id
    assert second.orders[0].client_order_id == first.orders[0].client_order_id
    assert second.broker_results == ()
    assert len(broker.submitted_orders) == 1


def test_live_broker_adapter_requires_explicit_runtime_submit_enablement() -> None:
    class LiveFakeBrokerAdapter(FakeBrokerAdapter):
        mode = TradingMode.BROKER_LIVE

    broker = LiveFakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    result = _orchestrator(broker_adapter=broker).process_bar(_bar())

    assert len(result.orders) == 1
    assert len(result.broker_results) == 1
    assert result.broker_results[0].status == BrokerOrderStatus.REJECTED
    assert result.broker_results[0].reason == "live_submission_disabled"
    assert result.ledger_updates[0].status == InternalOrderStatus.REJECTED
    assert broker.submitted_orders == []


def test_account_routed_live_broker_adapter_requires_explicit_runtime_submit_enablement() -> None:
    class AccountRoutedLiveFakeBrokerAdapter(FakeBrokerAdapter):
        def mode_for_account(self, account_id):  # type: ignore[no-untyped-def]
            assert account_id == ACCOUNT_ID
            return TradingMode.BROKER_LIVE

    broker = AccountRoutedLiveFakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    result = _orchestrator(broker_adapter=broker).process_bar(_bar())

    assert len(result.orders) == 1
    assert len(result.broker_results) == 1
    assert result.broker_results[0].status == BrokerOrderStatus.REJECTED
    assert result.broker_results[0].reason == "live_submission_disabled"
    assert result.ledger_updates[0].status == InternalOrderStatus.REJECTED
    assert broker.submitted_orders == []


def test_live_broker_adapter_submits_when_runtime_submit_is_explicitly_enabled() -> None:
    class LiveFakeBrokerAdapter(FakeBrokerAdapter):
        mode = TradingMode.BROKER_LIVE

    broker = LiveFakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    resolved = _components()
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(resolved),
        components=resolved,
        broker_adapter=broker,
        live_order_submission_enabled=True,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )

    result = pipeline.process_bar(_bar())

    assert len(result.orders) == 1
    assert len(result.broker_results) == 1
    assert result.broker_results[0].status == BrokerOrderStatus.ACCEPTED
    assert len(broker.submitted_orders) == 1


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
    assert PipelineEventType.CANDIDATE_TRADE_INTENT in event_types
    assert PipelineEventType.GOVERNOR_DECISION in event_types
    assert PipelineEventType.BROKER_RESULT in event_types
    assert PipelineEventType.LEDGER_UPDATE in event_types


def test_no_component_bypass() -> None:
    source = inspect.getsource(orchestrator_module)

    assert ".compute(" not in source
    assert "InternalOrder(" not in source
    assert "build_signal_plan_from_v4(" not in source
    assert ".can_open_new_position(" in source
    assert ".create_signal_plan_order(" in source
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
        position_reader=PositionReader((_position(strategy_id=components.strategy.strategy_id),)),
    )

    result = pipeline.process_protective_signal_plan(
        signal_plan=_protective_signal_plan(components),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    assert len(result.orders) == 1
    assert result.orders[0].origin.value == "signal_plan"
    assert result.orders[0].signal_plan_id == result.signal_plans[0].signal_plan_id
    assert result.orders[0].intent == InternalOrderIntent.STOP_LOSS


def test_protective_intent_without_active_position_creates_no_order() -> None:
    components = _components()
    pipeline = _orchestrator(
        components=components,
        broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.FILLED]),
        position_reader=PositionReader(()),
    )

    result = pipeline.process_protective_signal_plan(
        signal_plan=_protective_signal_plan(components),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    assert result.orders == ()
    assert len(result.signal_plans) == 1
    assert result.broker_results == ()


def test_pipeline_matches_batch_signal_expectation() -> None:
    components = _components()
    bar = _bar()
    result = _orchestrator(components=components).process_bar(bar)
    pipeline_feature_values = result.signal_plans[0].feature_snapshot
    batch_snapshot = IncrementalFeatureEngine().compute(
        _orchestrator(components=components).feature_plan,
        [bar],
    ).frame_for("SPY", "5m").snapshots[0]

    assert pipeline_feature_values
    assert batch_snapshot.value_for(next(key for key in batch_snapshot.values if "price.close" in key)) == 100


def test_full_pipeline_governor_order_manager_alpaca_adapter_broker_sync(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeAlpacaOrderRequest)
    components = _components()
    client = PipelineAlpacaClient()
    adapter = AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=client)
    governor = CountingGovernor()
    pipeline = _orchestrator(components=components, governor=governor, broker_adapter=adapter)  # type: ignore[arg-type]

    result = pipeline.process_bar(_bar())

    assert governor.evaluate_calls == 1
    assert len(result.orders) == 1
    assert len(result.broker_results) == 1
    assert len(result.ledger_updates) == 1
    assert result.orders[0].signal_plan_id == result.signal_plans[0].signal_plan_id
    assert result.broker_results[0].client_order_id == result.orders[0].client_order_id
    assert result.ledger_updates[0].status == InternalOrderStatus.ACCEPTED
    assert client.submitted_client_order_ids == [result.orders[0].client_order_id]


def test_full_pipeline_preflight_blocks_invalid_alpaca_order_before_submit() -> None:
    components = _components()
    limit_execution = components.execution_style.model_copy(update={"entry_order_type": OrderType.LIMIT})
    components = components.model_copy(update={"execution_style": limit_execution})
    client = PipelineAlpacaClient()
    adapter = AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=client)
    pipeline = _orchestrator(components=components, broker_adapter=adapter)  # type: ignore[arg-type]

    result = pipeline.process_bar(_bar())

    assert len(result.orders) == 1
    assert client.submitted_client_order_ids == []
    assert result.broker_results[0].status == BrokerOrderStatus.REJECTED
    assert result.broker_results[0].reason == "broker_preflight:unsupported_order_type"
    assert result.ledger_updates[0].status == InternalOrderStatus.REJECTED


def test_full_pipeline_does_not_submit_when_governor_blocks_with_real_adapter(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeAlpacaOrderRequest)
    client = PipelineAlpacaClient()
    adapter = AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=client)
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


# ---------------------------------------------------------------------------
# Slice A: GovernorPolicyResolver wiring
# Doctrine: Operations_Turtle_Shell_Artifacts/GOVERNOR_WIRING_MAP.md §G-3.
# Confirms that AccountRiskConfig + per-horizon RiskPlanConfig actually gate
# orders at the orchestrator's three Governor call sites, instead of the
# silent-no-op behavior that shipped before.
# ---------------------------------------------------------------------------


def _make_account_config(**overrides):
    from datetime import datetime as _dt, timezone as _tz
    from backend.app.broker_accounts.models import AccountRiskConfig
    base = {
        "account_id": ACCOUNT_ID,
        "max_open_positions": None,
        "risk_per_trade_pct": 1.0,
        "sizing_method": "risk_percent_equity",
        "updated_at": _dt(2026, 4, 29, 18, 0, tzinfo=_tz.utc),
    }
    base.update(overrides)
    return AccountRiskConfig(**base)


def _make_plan_config(**overrides):
    from backend.app.domain.risk_plan import RiskPlanConfig, RiskPlanSizingMethod
    base = {
        "sizing_method": RiskPlanSizingMethod.RISK_PERCENT,
        "risk_per_trade_pct": 1.0,
    }
    base.update(overrides)
    return RiskPlanConfig(**base)


def _resolver_for(account_config=None, plan_config=None):
    from backend.app.governor import GovernorPolicyResolver
    # T-6: composite single-conn lookup. The helper folds the per-source
    # configs into the snapshot tuple the resolver now expects.
    return GovernorPolicyResolver(
        get_policy_inputs=lambda _aid, _h: (account_config, plan_config),
    )


def _portfolio_with_one_open_position():
    # Seed a single open position so max_open_positions=1 trips on the
    # NEXT entry signal. AccountRiskConfig requires limits > 0 (no zero
    # caps allowed), so we engineer the boundary by holding one position.
    from backend.app.governor import PortfolioSnapshot, PositionSummary
    return PortfolioSnapshot(
        equity=100_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="AAPL",
                quantity=10,
                market_value=1500,
                open_risk=50,
            ),
        ),
    )


def _orchestrator_with_resolver(*, resolver, components=None, broker_adapter=None, portfolio_snapshot=None):
    resolved = components or _components()
    # W2-A-1b: default to a non-None equity snapshot so the new
    # portfolio_equity_unavailable rule does not pre-empt the resolver tests
    # (which probe per-Account / per-Plan policy, not equity availability).
    return RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(resolved),
        components=resolved,
        broker_adapter=broker_adapter,
        governor_policy_resolver=resolver,
        portfolio_snapshot=(
            portfolio_snapshot
            if portfolio_snapshot is not None
            else PortfolioSnapshot(equity=100_000)
        ),
    )


def test_resolver_off_preserves_legacy_behavior() -> None:
    # No resolver wired → today's behavior (persisted GovernorPolicy is the
    # only policy). max_open_positions stays None on the persisted policy,
    # so the entry is approved.
    pipeline = _orchestrator()
    result = pipeline.process_bar(_bar())
    assert result.governor_decisions[0].approved is True


def test_resolver_account_max_open_positions_blocks_entry() -> None:
    # Operator sets AccountRiskConfig.max_open_positions=1 and the Account
    # already has one open position. Before this slice that cap did nothing;
    # after this slice the next entry signal must be blocked.
    # Slice B: also provide a plan_config so the missing-plan rule does not
    # fire before the positions-cap rule. The intent here is to test the
    # positions cap, not the missing-plan rejection.
    resolver = _resolver_for(
        account_config=_make_account_config(max_open_positions=1),
        plan_config=_make_plan_config(),
    )
    pipeline = _orchestrator_with_resolver(
        resolver=resolver,
        portfolio_snapshot=_portfolio_with_one_open_position(),
    )
    result = pipeline.process_bar(_bar())
    assert result.governor_decisions[0].approved is False
    assert result.governor_decisions[0].reason == "max_open_positions_exceeded"
    assert result.orders == ()


def test_resolver_plan_max_open_positions_blocks_entry() -> None:
    # RiskPlanConfig contributes max_open_positions=1; one existing open
    # position trips the cap on the next entry.
    resolver = _resolver_for(plan_config=_make_plan_config(max_open_positions=1))
    pipeline = _orchestrator_with_resolver(
        resolver=resolver,
        portfolio_snapshot=_portfolio_with_one_open_position(),
    )
    result = pipeline.process_bar(_bar())
    assert result.governor_decisions[0].approved is False
    assert result.governor_decisions[0].rule_id == "max_open_positions"


def test_resolver_min_of_both_account_tighter() -> None:
    # AccountRiskConfig caps at 1, RiskPlanConfig caps at 5 → account wins.
    resolver = _resolver_for(
        account_config=_make_account_config(max_open_positions=1),
        plan_config=_make_plan_config(max_open_positions=5),
    )
    pipeline = _orchestrator_with_resolver(
        resolver=resolver,
        portfolio_snapshot=_portfolio_with_one_open_position(),
    )
    result = pipeline.process_bar(_bar())
    assert result.governor_decisions[0].approved is False


def test_resolver_min_of_both_plan_tighter() -> None:
    # AccountRiskConfig caps at 5, RiskPlanConfig caps at 1 → plan wins.
    resolver = _resolver_for(
        account_config=_make_account_config(max_open_positions=5),
        plan_config=_make_plan_config(max_open_positions=1),
    )
    pipeline = _orchestrator_with_resolver(
        resolver=resolver,
        portfolio_snapshot=_portfolio_with_one_open_position(),
    )
    result = pipeline.process_bar(_bar())
    assert result.governor_decisions[0].approved is False


def test_resolver_off_means_per_account_limits_have_no_effect() -> None:
    # Regression guard for the silent-no-op state we just fixed: without a
    # resolver, even an aggressive AccountRiskConfig has zero effect — that
    # is what shipped before this slice. We're not removing that path; we're
    # adding the resolver as the way to get enforcement.
    pipeline = _orchestrator()  # no resolver
    result = pipeline.process_bar(_bar())
    # Order goes through because persisted GovernorPolicy.max_open_positions
    # is None — operator AccountRiskConfig is not consulted.
    assert result.governor_decisions[0].approved is True


def test_resolver_resolved_policy_does_not_mutate_persisted_floor() -> None:
    # The orchestrator must not rewrite self._governor.policy when applying
    # an override. Slice-A invariant.
    resolver = _resolver_for(account_config=_make_account_config(max_open_positions=1))
    pipeline = _orchestrator_with_resolver(
        resolver=resolver,
        portfolio_snapshot=_portfolio_with_one_open_position(),
    )
    floor_before = pipeline._governor.policy
    pipeline.process_bar(_bar())
    assert pipeline._governor.policy is floor_before
    assert pipeline._governor.policy.max_open_positions is None


def test_resolver_handles_multi_account_fanout_independently() -> None:
    # Slice A finding #5: prove the resolver's per-(account, horizon) lookup
    # actually fires once per account in a multi-account deployment, and that
    # the results don't leak between iterations. We capture every account_id
    # the lookup callable receives and verify both got called.
    captured_accounts: list[UUID] = []

    def _account_lookup(account_id):
        captured_accounts.append(account_id)
        return _make_account_config(max_open_positions=10)

    from backend.app.governor import GovernorPolicyResolver
    # Slice B: provide a plan_config so requires_risk_plan is False; this
    # test is specifically about multi-account fanout capturing, not the
    # missing-plan rejection. T-6: the per-source lookups are folded into
    # the composite get_policy_inputs callback; account_lookup runs inside
    # to keep the captured-account assertion intact.
    resolver = GovernorPolicyResolver(
        get_policy_inputs=lambda aid, _h: (_account_lookup(aid), _make_plan_config()),
    )
    resolved = _components()
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
        deployment=_deployment(resolved),
        components=resolved,
        governor_policy_resolver=resolver,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )
    result = pipeline.process_bar(_bar())
    # Two governor decisions, one per account, both approved (cap is 10).
    assert len(result.governor_decisions) == 2
    assert all(d.approved for d in result.governor_decisions)
    # Lookup fired for BOTH accounts — no caching/leak.
    assert ACCOUNT_ID in captured_accounts
    assert OTHER_ACCOUNT_ID in captured_accounts


def test_resolver_traces_carry_projected_state() -> None:
    # Slice A finding #8: the GovernorDecisionTrace must carry the
    # projected_state so the operator sees the gate's numeric snapshot.
    # Tests that the orchestrator forwards it from GovernorDecision into
    # the persisted trace.
    resolver = _resolver_for(account_config=_make_account_config(max_open_positions=5))
    pipeline = _orchestrator_with_resolver(resolver=resolver)
    result = pipeline.process_bar(_bar())
    trace = result.account_evaluations[0].governor_decision
    assert trace is not None
    assert trace.projected_state is not None
    # The slot count must reflect the resolver's policy (5), not the floor's None.
    assert trace.projected_state["new_open_slots_remaining"] == 4  # 5 - 1 projected


# ---------------------------------------------------------------------------
# Slice B: account_missing_risk_plan_for_horizon end-to-end test
# Wire a resolver whose plan lookup returns None for ALL inputs. Confirm the
# entry signal is rejected with rule_id="account_missing_risk_plan_for_horizon".
# ---------------------------------------------------------------------------


def test_resolver_missing_plan_rejects_entry_signal() -> None:
    """End-to-end: resolver with plan_lookup returning None triggers rejection.

    When the Deployment has an explicit risk_horizon AND the Account has no
    RiskPlan mapped for that horizon, the GovernorPolicyResolver sets
    requires_risk_plan=True, and the Governor must reject the entry with
    rule_id="account_missing_risk_plan_for_horizon".
    """
    from backend.app.governor import GovernorPolicyResolver

    # T-6: composite snapshot — both halves None so requires_risk_plan trips.
    resolver = GovernorPolicyResolver(
        get_policy_inputs=lambda _aid, _h: (None, None),
    )
    # Use a deployment with an explicit risk_horizon so enforce_plan_required=True.
    resolved = _components()
    deployment = DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=resolved.strategy.id,
        strategy_version=resolved.strategy.version,
        risk_horizon=TradingHorizon.INTRADAY,  # explicit horizon declared
    )
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=deployment,
        components=resolved,
        governor_policy_resolver=resolver,
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )

    result = pipeline.process_bar(_bar())

    # Signal plan is created (risk horizon applies after signal generation).
    assert len(result.signal_plans) == 1
    # Governor must reject the entry.
    assert len(result.governor_decisions) == 1
    assert result.governor_decisions[0].approved is False
    assert result.governor_decisions[0].rule_id == "account_missing_risk_plan_for_horizon"
    # No order should be created.
    assert result.orders == ()


def test_missing_explicit_risk_horizon_rejects_when_floor_requires_plan() -> None:
    """P1-4: fail closed when deployment risk_horizon is omitted.

    If the floor governor policy requires a risk plan, a deployment that does
    not set explicit risk_horizon must not bypass plan enforcement through the
    StrategyControls fallback. Reject with rule_id="risk_horizon_missing".
    """
    resolved = _components()
    deployment = _deployment(resolved)  # no explicit risk_horizon
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=deployment,
        components=resolved,
        governor=PortfolioGovernor(GovernorPolicy(requires_risk_plan=True)),
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )

    result = pipeline.process_bar(_bar())

    assert len(result.signal_plans) == 1
    assert len(result.governor_decisions) == 1
    assert result.governor_decisions[0].approved is False
    assert result.governor_decisions[0].rule_id == "risk_horizon_missing"
    assert result.orders == ()


# ---------------------------------------------------------------------------
# W2-A adversarial-critic fix #4: post_fill_pct cap at 100 in the Governor
# proxy. Direct unit test on _governor_candidate_inputs so the cap doesn't
# require running the downstream protective placer (which has its own
# constraint that stop_price > 0).
# ---------------------------------------------------------------------------


def test_governor_candidate_inputs_caps_post_fill_pct_at_100() -> None:
    from backend.app.domain import (
        SignalPlan,
        SignalPlanIntent,
        SignalPlanSide,
        SignalPlanStop,
    )
    from backend.app.decision.signal_plan_builder import post_fill_pct_rule

    pipeline = _orchestrator()  # equity=100k default
    plan = SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        watchlist_snapshot_id=uuid4(),
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        stop=SignalPlanStop(type="none", rule=post_fill_pct_rule(200.0)),
    )
    market_value, open_risk = pipeline._governor_candidate_inputs(  # type: ignore[attr-defined]
        account_id=ACCOUNT_ID,
        signal_plan=plan,
        order_intent=InternalOrderIntent.OPEN,
        candidate_quantity=10.0,
        reference_price=100.0,
        risk_result_stop_distance=None,
        timestamp=None,
    )
    # qty * ref = 10 * 100 = 1000.
    assert market_value == 1000.0
    # Cap at 100% means proxy_stop_distance = 100 * (100/100) = 100;
    # candidate_open_risk = 10 * 100 = 1000 (NOT 2000 which would be the
    # uncapped 200% calc).
    assert open_risk == 1000.0


def test_resolver_missing_plan_does_not_block_protective_exit() -> None:
    """Even with requires_risk_plan=True, protective exits must get through."""
    from backend.app.governor import GovernorPolicyResolver

    components = _components()
    position_lineage_id = uuid4()
    opening_signal_plan_id = uuid4()

    resolver = GovernorPolicyResolver(
        get_policy_inputs=lambda _aid, _h: (None, None),
    )
    # Deployment with explicit risk_horizon to activate the doctrine check.
    deployment = DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
        risk_horizon=TradingHorizon.SWING,  # explicit horizon
    )
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        account_ids=(ACCOUNT_ID,),
        deployment=deployment,
        components=components,
        governor_policy_resolver=resolver,
        broker_adapter=FakeBrokerAdapter([BrokerOrderStatus.FILLED]),
        position_reader=PositionReader(
            (
                _position(
                    strategy_id=components.strategy.strategy_id,
                    opening_signal_plan_id=opening_signal_plan_id,
                    position_lineage_id=position_lineage_id,
                ),
            )
        ),
    )

    result = pipeline.process_protective_signal_plan(
        signal_plan=_protective_signal_plan(components),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )

    assert result.governor_decisions[0].approved is True
    assert result.governor_decisions[0].reason == "protective_exit_allowed"
    assert len(result.orders) == 1
