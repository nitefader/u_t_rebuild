from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import (
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    FakeBrokerAdapter,
)
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.control_plane import ControlPlane
from backend.app.decision import SignalEngine
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
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanSide,
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    TradingMode,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.decision.signal_plan_builder import post_fill_pct_rule
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
from backend.app.governor import GovernorPolicy, PortfolioGovernor, PortfolioSnapshot
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderManagerError, OrderOrigin
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime.daily_account_state import DailyAccountState
from backend.app.runtime import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator, DeploymentContext, RuntimeState, RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
OTHER_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
_DEFAULT_STARTUP_WARMUP_SOURCE = object()


def _components(*, symbol: str = "SPY") -> ResolvedDeploymentComponents:
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
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
                ),
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
        name="Universe",
        symbols=[UniverseSymbol(symbol=symbol)],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Runtime Strategy Version",
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


def _components_with_v4_atr(*, symbol: str = "SPY") -> ResolvedDeploymentComponents:
    components = _components(symbol=symbol)
    strategy_v4 = StrategyVersionV4(
        version=1,
        name="Runtime ATR v4",
        entries=StrategyEntriesV4(long=StrategyEntryV4(expression_text="1m.close < 1m.open")),
        stops=(
            StrategyStopV4(
                mode="simple",
                scope="all",
                simple_type="ATR",
                simple_value=2.0,
                feature_requirements=("atr:length=14[0]",),
            ),
        ),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="ATR",
                target_value=4.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        feature_requirements=("1m.close", "1m.open", "atr:length=14[0]"),
    )
    return components.model_copy(update={"strategy_version_v4": strategy_v4})


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


def _components_without_feature_requirements(*, symbol: str = "SPY") -> ResolvedDeploymentComponents:
    components = _components(symbol=symbol)
    return components.model_copy(update={"strategy": components.strategy.model_copy(update={"entry_rules": ()})})


def _deployment(
    components: ResolvedDeploymentComponents,
    *,
    deployment_id: UUID = DEPLOYMENT_ID,
    mode: TradingMode = TradingMode.BROKER_PAPER,
) -> DeploymentContext:
    return DeploymentContext(
        deployment_id=deployment_id,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
        mode=mode.value,
        status=RuntimeStatus.RECOVERED_READY,
    )


def _bar(index: int = 0, *, symbol: str = "SPY", open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * index),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000 + index,
    )


def _seed_account(store: SQLiteRuntimeStore, account_id: UUID = ACCOUNT_ID, *, mode: TradingMode = TradingMode.BROKER_PAPER, stale: bool = False) -> None:
    now = datetime.now(timezone.utc)
    store.save_broker_account(
        BrokerAccount(
            id=account_id,
            display_name="Paper",
            provider="alpaca",
            mode=mode,
            credentials_ref="test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    from backend.app.brokers import BrokerSyncState

    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=account_id,
            last_sync_at=now,
            last_successful_sync_at=None if stale else now,
            is_stale=stale,
            stale_reason="stale" if stale else None,
        )
    )


def _bracket_signal_plan(components: ResolvedDeploymentComponents, *, symbol: str = "SPY") -> SignalPlan:
    strategy = components.strategy
    assert strategy is not None
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=strategy.strategy_id,
        strategy_version_id=strategy.id,
        watchlist_snapshot_id=components.universe.id,
        symbol=symbol.upper(),
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(order_type=OrderType.MARKET, time_in_force_preference=TimeInForce.DAY),
        stop=SignalPlanStop(type="percent", rule=post_fill_pct_rule(5.0), required=True),
        targets=(
            SignalPlanTarget(
                label="t1",
                action=SignalPlanTargetAction.CLOSE,
                quantity_pct=100.0,
                rule=post_fill_pct_rule(10.0),
            ),
        ),
        reason="restart_protection_fixture",
    )


def _filled_parent_order(
    signal_plan: SignalPlan,
    *,
    account_id: UUID = ACCOUNT_ID,
    deployment_id: UUID = DEPLOYMENT_ID,
    quantity: float = 10.0,
) -> InternalOrder:
    now = datetime.now(timezone.utc)
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"parent-{uuid4().hex[:12]}",
        account_id=account_id,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=deployment_id,
        strategy_id=signal_plan.strategy_id,
        strategy_version_id=signal_plan.strategy_version_id,
        signal_plan_id=signal_plan.signal_plan_id,
        opening_signal_plan_id=signal_plan.signal_plan_id,
        current_signal_plan_id=signal_plan.signal_plan_id,
        position_lineage_id=signal_plan.signal_plan_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        symbol=signal_plan.symbol,
        side=CandidateSide.LONG,
        quantity=quantity,
        filled_quantity=quantity,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.FILLED,
        created_at=now,
        updated_at=now,
        signal_name=signal_plan.reason,
        reason=signal_plan.reason,
    )


def _broker_position(*, account_id: UUID = ACCOUNT_ID, symbol: str = "SPY", qty: float = 10.0) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=account_id,
        symbol=symbol,
        qty=qty,
        side=BrokerPositionSide.LONG if qty > 0 else BrokerPositionSide.SHORT,
        avg_entry_price=100.0,
        market_value=abs(qty) * 100.0,
    )


class _StartupWarmupSource:
    def __call__(self, _entry, symbol: str, timeframe: str, warmup_bars: int):
        bars = max(int(warmup_bars), 1)
        return tuple(
            _bar(index - bars, symbol=symbol, open_=100.0, close=100.0).model_copy(update={"timeframe": timeframe})
            for index in range(bars)
        )

    def fetch_bars_for_hydration(self, _entry, request):
        bars = max(int(request.warmup_bars), 1)
        step = timedelta(minutes=self._minutes_for_timeframe(request.timeframe))
        return tuple(
            _bar(index, symbol=request.symbol, open_=100.0, close=100.0).model_copy(
                update={
                    "timeframe": request.timeframe,
                    "timestamp": request.as_of - step * (bars - index),
                }
            )
            for index in range(bars)
        )

    @staticmethod
    def _minutes_for_timeframe(timeframe: str) -> int:
        normalized = timeframe.strip().lower()
        if normalized.endswith("m") and normalized[:-1].isdigit():
            return max(int(normalized[:-1]), 1)
        if normalized.endswith("h") and normalized[:-1].isdigit():
            return max(int(normalized[:-1]) * 60, 1)
        return 5


_startup_warmup_source = _StartupWarmupSource()


def _runtime(
    tmp_path,
    *,
    account_id: UUID = ACCOUNT_ID,
    deployment_id: UUID = DEPLOYMENT_ID,
    components: ResolvedDeploymentComponents | None = None,
    broker: FakeBrokerAdapter | None = None,
    governor: PortfolioGovernor | None = None,
    control_plane: ControlPlane | None = None,
    order_manager: OrderManager | None = None,
    broker_sync: BrokerSync | None = None,
    bar_source=None,
    startup_warmup_bars_source=_DEFAULT_STARTUP_WARMUP_SOURCE,
    mode: TradingMode = TradingMode.BROKER_PAPER,
    live_order_submission_enabled: bool = False,
) -> tuple[BrokerRuntimeOrchestrator, SQLiteRuntimeStore, FakeBrokerAdapter]:
    store = SQLiteRuntimeStore(tmp_path / f"{deployment_id}.sqlite")
    _seed_account(store, account_id, mode=mode)
    resolved = components or _components()
    if startup_warmup_bars_source is _DEFAULT_STARTUP_WARMUP_SOURCE:
        startup_warmup_bars_source = _startup_warmup_source
    try:
        store.load_deployment_runtime_state(deployment_id)
    except KeyError:
        store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RECOVERED_READY))
    ledger = SQLiteOrderLedger(tmp_path / f"{deployment_id}.sqlite")
    manager = order_manager or OrderManager(ledger=ledger, control_plane=control_plane)
    adapter = broker or FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    sync = broker_sync or BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="alpaca")
    # W2-A-1b (audit P0 #2): provide a non-None equity factory so the new
    # portfolio_equity_unavailable rule does not pre-empt every test that
    # creates the orchestrator without explicit equity. Production wires a
    # real factory backed by BrokerSync account snapshots; this fixture
    # matches that contract by always returning a fixed equity value.
    runtime = BrokerRuntimeOrchestrator(
        deployments=(
            BrokerRuntimeDeployment(
                deployment=_deployment(resolved, deployment_id=deployment_id, mode=mode),
                components=resolved,
                account_id=account_id,
                live_order_submission_enabled=live_order_submission_enabled,
            ),
        ),
        runtime_store=store,
        broker_adapter=adapter,
        broker_sync=sync,
        order_manager=manager,
        control_plane=control_plane or ControlPlane(state_store=store),
        governor=governor,
        bar_source=bar_source,
        startup_warmup_bars_source=startup_warmup_bars_source,
        portfolio_snapshot_factory=lambda _aid: PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=(
            _strategy_artifact_resolver(resolved)
            if resolved.strategy_version_v4 is not None
            else None
        ),
    )
    return runtime, store, adapter


class CountingSignalEngine(SignalEngine):
    def __init__(self) -> None:
        super().__init__()
        self.evaluate_calls = 0

    def evaluate(self, strategy, snapshot, *, position_contexts=None):  # type: ignore[no-untyped-def]
        self.evaluate_calls += 1
        return super().evaluate(strategy, snapshot, position_contexts=position_contexts)


class FailingOrderManager(OrderManager):
    def create_order(self, **kwargs):  # type: ignore[no-untyped-def]
        raise OrderManagerError("create failed")

    def create_signal_plan_order(self, **kwargs):  # type: ignore[no-untyped-def]
        raise OrderManagerError("create failed")


class FailingBrokerSync(BrokerSync):
    def apply_result(self, result):  # type: ignore[no-untyped-def]
        raise OrderManagerError("sync failed")


def test_run_once_processes_completed_bar_through_feature_engine_and_signal_engine(tmp_path) -> None:
    signal_engine = CountingSignalEngine()
    bar = _bar()
    runtime, store, broker = _runtime(tmp_path, bar_source=lambda _deployment_id: bar)
    runtime._signal_engine = signal_engine

    result = runtime.run_once(DEPLOYMENT_ID)

    assert result is not None
    assert signal_engine.evaluate_calls == 1
    assert len(result.signal_plans) == 1
    assert len(broker.submitted_orders) == 1
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).last_bar_timestamp_by_symbol_timeframe["SPY:5m"] == bar.timestamp


def test_governor_rejection_creates_no_internal_order(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path, governor=PortfolioGovernor(GovernorPolicy(max_open_positions=0)))

    result = runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert result is not None
    assert result.governor_decisions[0].approved is False
    assert store.list_orders() == ()
    assert broker.submitted_orders == []


def test_control_plane_global_kill_blocks_new_open_orders(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path, control_plane=ControlPlane(global_kill_active=True))

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert store.list_orders() == ()
    assert broker.submitted_orders == []
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).last_error == "global_kill_active"


def test_account_pause_blocks_new_open_orders_for_that_account_only(tmp_path) -> None:
    control = ControlPlane(paused_account_ids={ACCOUNT_ID})
    runtime, _, broker = _runtime(tmp_path, control_plane=control)
    other_runtime, _, other_broker = _runtime(
        tmp_path,
        account_id=OTHER_ACCOUNT_ID,
        deployment_id=OTHER_DEPLOYMENT_ID,
        components=_components(symbol="QQQ"),
        control_plane=control,
    )

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None
    assert other_runtime.process_completed_bar(OTHER_DEPLOYMENT_ID, _bar(symbol="QQQ")) is not None
    assert broker.submitted_orders == []
    assert len(other_broker.submitted_orders) == 1


def test_deployment_pause_blocks_new_open_orders_for_that_deployment_only(tmp_path) -> None:
    control = ControlPlane(paused_deployment_ids={DEPLOYMENT_ID})
    runtime, _, broker = _runtime(tmp_path, control_plane=control)
    other_runtime, _, other_broker = _runtime(
        tmp_path,
        deployment_id=OTHER_DEPLOYMENT_ID,
        components=_components(symbol="QQQ"),
        control_plane=control,
    )

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None
    assert other_runtime.process_completed_bar(OTHER_DEPLOYMENT_ID, _bar(symbol="QQQ")) is not None
    assert broker.submitted_orders == []
    assert len(other_broker.submitted_orders) == 1


def test_stale_broker_sync_blocks_new_open_orders(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path)
    _seed_account(store, ACCOUNT_ID, stale=True)

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert store.list_orders() == ()
    assert broker.submitted_orders == []
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).last_error == "stale"


def test_order_manager_creates_internal_order_before_alpaca_broker_adapter_is_called(tmp_path) -> None:
    seen: list[bool] = []

    class InspectingBroker(FakeBrokerAdapter):
        def submit_order(self, order):  # type: ignore[no-untyped-def]
            seen.append(store.load_order(order.order_id).order_id == order.order_id)
            return super().submit_order(order)

    runtime, store, _broker = _runtime(tmp_path, broker=InspectingBroker([BrokerOrderStatus.ACCEPTED]))

    runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert seen == [True]


def test_broker_adapter_is_never_called_if_order_manager_fails(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path, order_manager=FailingOrderManager())

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert broker.submitted_orders == []
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).status == RuntimeStatus.DEGRADED


def test_broker_sync_is_called_after_broker_submit_result(tmp_path) -> None:
    calls: list[str] = []

    class RecordingBroker(FakeBrokerAdapter):
        def submit_order(self, order):  # type: ignore[no-untyped-def]
            calls.append("broker")
            return super().submit_order(order)

    class RecordingSync(BrokerSync):
        def apply_result(self, result):  # type: ignore[no-untyped-def]
            calls.append("sync")
            return super().apply_result(result)

    store = SQLiteRuntimeStore(tmp_path / "sync.sqlite")
    _seed_account(store)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.RECOVERED_READY))
    ledger = SQLiteOrderLedger(tmp_path / "sync.sqlite")
    broker = RecordingBroker([BrokerOrderStatus.ACCEPTED])
    sync = RecordingSync(ledger=ledger, adapter=broker, runtime_store=store, provider="alpaca")
    runtime = BrokerRuntimeOrchestrator(
        deployments=(BrokerRuntimeDeployment(deployment=_deployment(_components()), components=_components(), account_id=ACCOUNT_ID),),
        runtime_store=store,
        broker_adapter=broker,
        broker_sync=sync,
        order_manager=OrderManager(ledger=ledger),
        control_plane=ControlPlane(state_store=store),
        startup_warmup_bars_source=_startup_warmup_source,
        portfolio_snapshot_factory=lambda _aid: PortfolioSnapshot(equity=100_000),
    )

    runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert calls == ["broker", "sync"]


def test_broker_sync_failure_marks_runtime_degraded_and_blocks_further_opens(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "failing-sync.sqlite")
    _seed_account(store)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.RECOVERED_READY))
    ledger = SQLiteOrderLedger(tmp_path / "failing-sync.sqlite")
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED])
    runtime = BrokerRuntimeOrchestrator(
        deployments=(BrokerRuntimeDeployment(deployment=_deployment(_components()), components=_components(), account_id=ACCOUNT_ID),),
        runtime_store=store,
        broker_adapter=broker,
        broker_sync=FailingBrokerSync(ledger=ledger, adapter=broker, runtime_store=store),
        order_manager=OrderManager(ledger=ledger),
        control_plane=ControlPlane(state_store=store),
        startup_warmup_bars_source=_startup_warmup_source,
        portfolio_snapshot_factory=lambda _aid: PortfolioSnapshot(equity=100_000),
    )

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None
    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar(1)) is None

    state = store.load_deployment_runtime_state(DEPLOYMENT_ID)
    assert state.status == RuntimeStatus.DEGRADED
    assert len(broker.submitted_orders) == 1


def _degraded_runtime(tmp_path, *, last_error: str) -> tuple[BrokerRuntimeOrchestrator, SQLiteRuntimeStore, FakeBrokerAdapter]:
    store = SQLiteRuntimeStore(tmp_path / "degraded.sqlite")
    _seed_account(store)
    store.save_deployment_runtime_state(
        RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.DEGRADED, last_error=last_error)
    )
    ledger = SQLiteOrderLedger(tmp_path / "degraded.sqlite")
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    runtime = BrokerRuntimeOrchestrator(
        deployments=(BrokerRuntimeDeployment(deployment=_deployment(_components()), components=_components(), account_id=ACCOUNT_ID),),
        runtime_store=store,
        broker_adapter=broker,
        broker_sync=BrokerSync(ledger=ledger, adapter=broker, runtime_store=store, provider="alpaca"),
        order_manager=OrderManager(ledger=ledger),
        control_plane=ControlPlane(state_store=store),
        startup_warmup_bars_source=_startup_warmup_source,
        portfolio_snapshot_factory=lambda _aid: PortfolioSnapshot(equity=100_000),
    )
    runtime._recovery_completed.add(DEPLOYMENT_ID)
    return runtime, store, broker


def test_degraded_from_freshness_gap_auto_clears_when_sync_recovers(tmp_path) -> None:
    # Sticky-DEGRADED bug: when a transient broker-sync stale (e.g. post-
    # restart WS reconnect taking >30s) tripped the freshness gate, the
    # deployment stayed degraded forever even after sync caught up.
    # Regression: degradation tagged with a freshness-origin last_error
    # must auto-clear once load_broker_sync_freshness reports fresh.
    runtime, store, broker = _degraded_runtime(
        tmp_path, last_error="broker_sync_stale:broker_truth_age_exceeded_30s"
    )

    result = runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert result is not None, "expected the bar to be processed after auto-clear"
    state = store.load_deployment_runtime_state(DEPLOYMENT_ID)
    assert state.status == RuntimeStatus.RUNNING
    assert len(broker.submitted_orders) == 1


def test_degraded_from_non_freshness_fault_stays_sticky(tmp_path) -> None:
    # The auto-clear must NOT activate when DEGRADED was set by a non-
    # freshness fault (e.g. apply_result exception). Those represent
    # broker-side malfunctions and require operator action to clear.
    runtime, store, broker = _degraded_runtime(tmp_path, last_error="sync failed")

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    state = store.load_deployment_runtime_state(DEPLOYMENT_ID)
    assert state.status == RuntimeStatus.DEGRADED
    assert broker.submitted_orders == []


def test_broker_account_mode_must_match_deployment_mode(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path)
    _seed_account(store, ACCOUNT_ID, mode=TradingMode.BROKER_LIVE)

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert store.list_orders() == ()
    assert broker.submitted_orders == []
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).last_error == "broker_account_mode_mismatch"


def test_runtime_restart_resumes_idempotently_without_duplicate_order_submission(tmp_path) -> None:
    runtime, _store, broker = _runtime(tmp_path)

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is not None
    restarted, _store, _same_broker = _runtime(tmp_path, broker=broker)
    assert restarted.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert len(broker.submitted_orders) == 1


def test_startup_places_protective_oco_for_naked_filled_deployment_position(tmp_path) -> None:
    components = _components()
    position = _broker_position(qty=10.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )
    runtime, store, broker = _runtime(tmp_path, components=components, broker=broker)
    signal_plan = _bracket_signal_plan(components)
    parent = _filled_parent_order(signal_plan)
    store.save_signal_plan(signal_plan)
    store.save_order(parent)

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is True
    assert len(broker.submitted_orders) == 1
    child = broker.submitted_orders[0]
    assert child.intent == InternalOrderIntent.TAKE_PROFIT
    assert child.order_class == "oco"
    assert child.parent_order_id == parent.order_id
    assert child.quantity == 10.0
    assert child.limit_price == 110.0
    assert child.bracket_stop_loss_stop_price == 95.0
    assert store.load_order(child.order_id).status == InternalOrderStatus.ACCEPTED
    assert any(event.event_type.value == "protection_placed" for event in runtime.latest_events)


def test_startup_allows_empty_feature_plan_without_warmup_source(tmp_path) -> None:
    components = _components_without_feature_requirements()
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    _seed_account(store)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.RECOVERED_READY))
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED], positions_by_account={ACCOUNT_ID: ()})
    ledger = SQLiteOrderLedger(tmp_path / "runtime.db")
    order_manager = OrderManager(ledger=ledger)
    runtime = BrokerRuntimeOrchestrator(
        deployments=(
            BrokerRuntimeDeployment(
                deployment=_deployment(components),
                components=components,
                account_id=ACCOUNT_ID,
            ),
        ),
        runtime_store=store,
        broker_adapter=broker,
        broker_sync=BrokerSync(ledger=ledger, adapter=broker, runtime_store=store, provider="alpaca"),
        order_manager=order_manager,
        control_plane=ControlPlane(state_store=store),
        startup_warmup_bars_source=None,
        portfolio_snapshot_factory=lambda _aid: PortfolioSnapshot(equity=100_000),
    )

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is True
    assert status.last_error is None
    assert not [event for event in runtime.latest_events if event.event_type.value == "signal_blocked"]


def test_startup_protection_uses_signal_plan_feature_snapshot_without_atr_replay(tmp_path) -> None:
    components = _components_with_v4_atr(symbol="TQQQ")
    position = _broker_position(symbol="TQQQ", qty=1.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )
    runtime, store, broker = _runtime(tmp_path, components=components, broker=broker)
    signal_plan = _bracket_signal_plan(components, symbol="TQQQ").model_copy(
        update={
            "stop": SignalPlanStop(type="atr", rule="atr:2.0", required=True),
            "targets": (
                SignalPlanTarget(
                    label="t1",
                    action=SignalPlanTargetAction.CLOSE,
                    quantity_pct=100.0,
                    rule="atr:4.0",
                ),
            ),
            "feature_snapshot": {"atr:length=14[0]": 1.25},
        }
    )
    store.save_signal_plan(signal_plan)
    store.save_order(_filled_parent_order(signal_plan, quantity=1.0))

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is True
    assert len(broker.submitted_orders) == 1
    child = broker.submitted_orders[0]
    assert child.intent == InternalOrderIntent.TAKE_PROFIT
    assert child.order_class == "oco"
    assert child.quantity == 1.0
    assert child.limit_price == 105.0
    assert child.bracket_stop_loss_stop_price == 97.5


def test_startup_prices_atr_protection_from_hydrated_feature_cache(tmp_path) -> None:
    components = _components_with_v4_atr(symbol="TQQQ")
    position = _broker_position(symbol="TQQQ", qty=1.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )

    runtime, store, broker = _runtime(
        tmp_path,
        components=components,
        broker=broker,
    )
    signal_plan = _bracket_signal_plan(components, symbol="TQQQ").model_copy(
        update={
            "stop": SignalPlanStop(type="atr", rule="atr:2.0", required=True),
            "targets": (
                SignalPlanTarget(
                    label="t1",
                    action=SignalPlanTargetAction.CLOSE,
                    quantity_pct=100.0,
                    rule="atr:4.0",
                ),
            ),
            "feature_snapshot": {"1m.close": 65.1, "1m.open": 66.0},
        }
    )
    store.save_signal_plan(signal_plan)
    store.save_order(_filled_parent_order(signal_plan, quantity=1.0))

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is True
    assert len(broker.submitted_orders) == 1
    child = broker.submitted_orders[0]
    assert child.intent == InternalOrderIntent.TAKE_PROFIT
    assert child.order_class == "oco"
    assert child.quantity == 1.0
    assert child.limit_price == 116.0
    assert child.bracket_stop_loss_stop_price == 92.0
    persisted_plan = store.load_signal_plan(signal_plan.signal_plan_id)
    assert persisted_plan.stop is not None
    assert persisted_plan.stop.rule == "atr:2.0"
    assert persisted_plan.feature_snapshot == {"1m.close": 65.1, "1m.open": 66.0}


def test_startup_reports_exact_blocker_when_hydrated_features_are_unavailable(tmp_path) -> None:
    components = _components_with_v4_atr(symbol="TQQQ")
    position = _broker_position(symbol="TQQQ", qty=1.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )

    class InsufficientSource:
        def fetch_bars_for_hydration(self, _entry, request):
            return tuple(
                _bar(index, symbol=request.symbol, open_=100.0, close=100.0).model_copy(
                    update={
                        "timeframe": request.timeframe,
                        "timestamp": request.as_of - timedelta(minutes=5 * (5 - index)),
                    }
                )
                for index in range(5)
            )

    runtime, store, broker = _runtime(
        tmp_path,
        components=components,
        broker=broker,
        startup_warmup_bars_source=InsufficientSource(),
    )
    signal_plan = _bracket_signal_plan(components, symbol="TQQQ").model_copy(
        update={
            "stop": SignalPlanStop(type="atr", required=True),
            "targets": (
                SignalPlanTarget(
                    label="t1",
                    action=SignalPlanTargetAction.CLOSE,
                    quantity_pct=100.0,
                    rule="atr:4.0",
                ),
            ),
            "feature_snapshot": {"1m.close": 65.1, "1m.open": 66.0},
        }
    )
    store.save_signal_plan(signal_plan)
    store.save_order(_filled_parent_order(signal_plan, quantity=1.0))

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is False
    assert status.state == RuntimeStatus.BLOCKED
    assert status.last_error is not None
    assert "missing_historical_bars" in status.last_error
    assert "symbol=TQQQ" in status.last_error
    assert "timeframe=5m" in status.last_error
    assert "warmup_bars=42" in status.last_error
    assert "bars_seen=5" in status.last_error
    assert broker.submitted_orders == []
    blocked_events = [event for event in runtime.latest_events if event.event_type.value == "signal_blocked"]
    assert blocked_events
    details = next(event.details for event in blocked_events if event.details["reason"] == "missing_historical_bars")
    assert details["symbol"] == "TQQQ"
    assert details["timeframe"] == "5m"
    assert details["bars_seen"] == 5
    assert details["warmup_bars"] == 42
    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar(100, symbol="TQQQ")) is None
    assert runtime.loop_status(DEPLOYMENT_ID).last_bar_timestamp is None
    assert runtime.loop_status(DEPLOYMENT_ID).last_error == status.last_error


def test_startup_reports_exact_blocker_when_warmup_source_is_missing(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path, startup_warmup_bars_source=None)

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is False
    assert status.state == RuntimeStatus.BLOCKED
    assert status.last_error is not None
    assert "startup_feature_warmup_failed" in status.last_error
    assert "feature_key=" in status.last_error
    assert "symbol=SPY" in status.last_error
    assert "timeframe=5m" in status.last_error
    assert "warmup_bars=1" in status.last_error
    assert "bars_seen=0" in status.last_error
    assert "missing_historical_bars_source" in status.last_error
    blocked_events = [event for event in runtime.latest_events if event.event_type.value == "signal_blocked"]
    assert blocked_events
    first = blocked_events[0].details
    assert first["reason"] == "startup_feature_warmup_failed"
    assert first["symbol"] == "SPY"
    assert first["timeframe"] == "5m"
    assert first["feature_key"] is not None
    assert first["warmup_bars"] == 1
    assert first["bars_seen"] == 0
    assert first["error"] == "missing_historical_bars_source"
    assert broker.submitted_orders == []
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).last_error == status.last_error


def test_blocked_startup_hydration_state_is_not_retried_by_live_bar(tmp_path) -> None:
    calls = 0

    class FailsOnceWarmupSource:
        def fetch_bars_for_hydration(self, _entry, request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return ()
            return _startup_warmup_source.fetch_bars_for_hydration(_entry, request)

    runtime, store, broker = _runtime(tmp_path, startup_warmup_bars_source=FailsOnceWarmupSource())
    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)
    assert status.state == RuntimeStatus.BLOCKED
    assert status.last_error is not None
    assert "missing_historical_bars" in status.last_error

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar(100)) is None

    state = store.load_deployment_runtime_state(DEPLOYMENT_ID)
    assert state.status == RuntimeStatus.BLOCKED
    assert state.last_error == status.last_error
    assert state.last_bar_timestamp_by_symbol_timeframe == {}
    assert broker.submitted_orders == []


def test_stopped_runtime_state_is_not_restarted_by_live_bar(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path)

    runtime.stop_deployment_runtime(DEPLOYMENT_ID)

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None
    state = store.load_deployment_runtime_state(DEPLOYMENT_ID)
    assert state.status == RuntimeStatus.STOPPED
    assert state.last_bar_timestamp_by_symbol_timeframe == {}
    assert broker.submitted_orders == []


def test_startup_protection_is_idempotent_after_oco_is_accepted(tmp_path) -> None:
    components = _components()
    position = _broker_position(qty=10.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )
    runtime, store, broker = _runtime(tmp_path, components=components, broker=broker)
    signal_plan = _bracket_signal_plan(components)
    store.save_signal_plan(signal_plan)
    store.save_order(_filled_parent_order(signal_plan))

    assert runtime.start_deployment_runtime(DEPLOYMENT_ID).running is True
    assert runtime.start_deployment_runtime(DEPLOYMENT_ID).running is True

    assert len(broker.submitted_orders) == 1


def test_startup_protection_covers_current_broker_qty_when_historical_fills_are_larger(tmp_path) -> None:
    components = _components()
    position = _broker_position(qty=2.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )
    runtime, store, broker = _runtime(tmp_path, components=components, broker=broker)
    for _ in range(3):
        signal_plan = _bracket_signal_plan(components)
        store.save_signal_plan(signal_plan)
        store.save_order(_filled_parent_order(signal_plan, quantity=1.0))

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is True
    assert len(broker.submitted_orders) == 2
    assert sum(order.quantity for order in broker.submitted_orders) == 2.0
    assert all(order.order_class == "oco" for order in broker.submitted_orders)


def test_startup_protection_refuses_ambiguous_same_symbol_deployment_ownership(tmp_path) -> None:
    components = _components()
    position = _broker_position(qty=10.0)
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        positions_by_account={ACCOUNT_ID: (position,)},
    )
    runtime, store, broker = _runtime(tmp_path, components=components, broker=broker)
    signal_plan = _bracket_signal_plan(components)
    other_plan = signal_plan.model_copy(update={"signal_plan_id": uuid4(), "deployment_id": OTHER_DEPLOYMENT_ID})
    store.save_signal_plan(signal_plan)
    store.save_order(_filled_parent_order(signal_plan, quantity=10.0))
    store.save_order(
        _filled_parent_order(
            other_plan,
            deployment_id=OTHER_DEPLOYMENT_ID,
            quantity=10.0,
        )
    )

    status = runtime.start_deployment_runtime(DEPLOYMENT_ID)

    assert status.running is True
    assert broker.submitted_orders == []
    naked_events = [event for event in runtime.latest_events if event.event_type.value == "protection_naked"]
    assert naked_events
    assert naked_events[-1].details["reason"] == "ambiguous_position_ownership"


def test_multiple_broker_accounts_and_deployments_run_independently(tmp_path) -> None:
    first, _, first_broker = _runtime(tmp_path)
    second, _, second_broker = _runtime(
        tmp_path,
        account_id=OTHER_ACCOUNT_ID,
        deployment_id=OTHER_DEPLOYMENT_ID,
        components=_components(symbol="QQQ"),
    )

    assert first.process_completed_bar(DEPLOYMENT_ID, _bar()) is not None
    assert second.process_completed_bar(OTHER_DEPLOYMENT_ID, _bar(symbol="QQQ")) is not None

    assert first_broker.submitted_orders[0].account_id == ACCOUNT_ID
    assert second_broker.submitted_orders[0].account_id == OTHER_ACCOUNT_ID


def test_one_deployment_can_fan_out_signal_plan_to_multiple_accounts(tmp_path) -> None:
    components = _components()
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    _seed_account(store, ACCOUNT_ID)
    _seed_account(store, OTHER_ACCOUNT_ID)
    deployment = _deployment(components)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment.deployment_id, status=RuntimeStatus.RECOVERED_READY))
    broker = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED])
    order_manager = OrderManager()
    runtime = BrokerRuntimeOrchestrator(
        deployments=(
            BrokerRuntimeDeployment(
                deployment=deployment,
                components=components,
                account_id=ACCOUNT_ID,
                account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
            ),
        ),
        runtime_store=store,
        broker_adapter=broker,
        broker_sync=BrokerSync(ledger=order_manager.ledger, adapter=broker, runtime_store=store),
        order_manager=order_manager,
        control_plane=ControlPlane(state_store=store),
        startup_warmup_bars_source=_startup_warmup_source,
        portfolio_snapshot_factory=lambda _aid: PortfolioSnapshot(equity=100_000),
    )

    result = runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert result is not None
    assert len(result.signal_plans) == 1
    assert [evaluation.account_id for evaluation in result.account_evaluations] == [ACCOUNT_ID, OTHER_ACCOUNT_ID]
    assert [order.account_id for order in result.orders] == [ACCOUNT_ID, OTHER_ACCOUNT_ID]


def test_live_account_records_rejection_without_explicit_submit_enablement(tmp_path) -> None:
    class LiveFakeBrokerAdapter(FakeBrokerAdapter):
        mode = TradingMode.BROKER_LIVE

    runtime, _store, broker = _runtime(
        tmp_path,
        broker=LiveFakeBrokerAdapter([BrokerOrderStatus.ACCEPTED]),
        mode=TradingMode.BROKER_LIVE,
    )

    result = runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert result is not None
    assert result.broker_results[0].status == BrokerOrderStatus.REJECTED
    assert result.broker_results[0].reason == "live_submission_disabled"
    assert result.ledger_updates[0].status.value == "rejected"
    assert broker.submitted_orders == []
    assert runtime.loop_status(DEPLOYMENT_ID).state == RuntimeStatus.RUNNING


def test_live_account_submits_only_when_explicitly_enabled(tmp_path) -> None:
    class LiveFakeBrokerAdapter(FakeBrokerAdapter):
        mode = TradingMode.BROKER_LIVE

    runtime, _store, broker = _runtime(
        tmp_path,
        broker=LiveFakeBrokerAdapter([BrokerOrderStatus.ACCEPTED]),
        mode=TradingMode.BROKER_LIVE,
        live_order_submission_enabled=True,
    )

    result = runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    assert result is not None
    assert result.broker_results[0].status == BrokerOrderStatus.ACCEPTED
    assert len(broker.submitted_orders) == 1


def test_operations_center_detail_endpoint_returns_runtime_loop_status_and_timestamps(tmp_path) -> None:
    from backend.app.operations import OperationsCenterService

    runtime, store, _broker = _runtime(tmp_path)
    runtime.process_completed_bar(DEPLOYMENT_ID, _bar())

    operations = OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
        deployments=(_deployment(_components()),),
        latest_pipeline_events=runtime.latest_events,
    )
    detail = operations.get_deployment_operations(DEPLOYMENT_ID)

    assert detail.runtime_loop_state == RuntimeStatus.RUNNING
    assert detail.last_market_data_timestamp == _bar().timestamp
    assert detail.last_signal_timestamp == _bar().timestamp
    assert detail.last_governor_decision is not None
    assert detail.last_order_id is not None
    assert detail.last_broker_sync_timestamp is not None


def test_daily_state_factory_does_not_bleed_across_market_day_boundary(tmp_path) -> None:
    runtime, _store, _broker = _runtime(tmp_path)
    runtime._daily_states[ACCOUNT_ID] = DailyAccountState(
        account_id=ACCOUNT_ID,
        market_day="2000-01-01",
        realized_pnl=-250.0,
        total_loss_today=250.0,
        last_loss_at=datetime(2000, 1, 1, 20, 59, tzinfo=timezone.utc),
    )

    assert runtime._daily_state_for(ACCOUNT_ID) is None
