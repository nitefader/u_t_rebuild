from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import BrokerOrderStatus, BrokerPositionSide, BrokerPositionSnapshot, BrokerSync, FakeBrokerAdapter
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
    TradingMode,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.features import IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.market_data import MarketDataStreamHub
from backend.app.orders import OrderManager
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime import (
    BrokerRuntimeDeployment,
    BrokerRuntimeOrchestrator,
    BrokerRuntimeSupervisor,
    BrokerRuntimeSupervisorError,
    DeploymentContext,
    RuntimeState,
    RuntimeStatus,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID_A = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
DEPLOYMENT_ID_B = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")


def _components(*, symbol: str = "SPY") -> ResolvedDeploymentComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    return ResolvedDeploymentComponents(
        program=ProgramVersion(
            id=uuid4(),
            program_id=uuid4(),
            name="P",
            version=1,
            strategy_version_id=strategy_id,
            strategy_controls_version_id=controls_id,
            risk_profile_version_id=risk_id,
            execution_style_version_id=execution_id,
            universe_snapshot_id=universe_id,
        ),
        strategy=StrategyVersion(
            id=strategy_id,
            strategy_id=uuid4(),
            version=1,
            name="S",
            entry_rules=[
                SignalRule(
                    name="r",
                    side=CandidateSide.LONG,
                    intent_type=IntentType.ENTRY,
                    condition=ConditionNode(
                        left_feature="5m.close[0]",
                        operator=ConditionOperator.GREATER_THAN,
                        right_feature="5m.open[0]",
                    ),
                )
            ],
        ),
        strategy_controls=StrategyControlsVersion(
            id=controls_id,
            strategy_controls_id=uuid4(),
            version=1,
            name="c",
            timeframe="5m",
        ),
        risk_profile=RiskProfileVersion(
            id=risk_id,
            risk_profile_id=uuid4(),
            version=1,
            name="r",
            sizing_method=PositionSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
        execution_style=ExecutionStyleVersion(
            id=execution_id,
            execution_style_id=uuid4(),
            version=1,
            name="e",
            entry_order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        ),
        universe=UniverseSnapshot(
            id=universe_id,
            universe_id=uuid4(),
            version=1,
            name="u",
            symbols=[UniverseSymbol(symbol=symbol)],
        ),
    )


def _deployment(deployment_id: UUID, components: ResolvedDeploymentComponents) -> DeploymentContext:
    return DeploymentContext(
        deployment_id=deployment_id,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
        mode=TradingMode.BROKER_PAPER.value,
    )


def _bar(symbol: str = "SPY", *, close: float = 100, open_: float = 99) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe="5m",
        timestamp=datetime.now(timezone.utc),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000,
    )


def _seed_account(store: SQLiteRuntimeStore) -> None:
    from backend.app.brokers import BrokerSyncState

    now = datetime.now(timezone.utc)
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=ACCOUNT_ID,
            last_sync_at=now,
            last_successful_sync_at=now,
            is_stale=False,
        )
    )


def _build_runtime(tmp_path, *, deployments) -> tuple[BrokerRuntimeOrchestrator, SQLiteRuntimeStore]:
    store = SQLiteRuntimeStore(tmp_path / "supervisor.sqlite")
    _seed_account(store)
    for entry in deployments:
        try:
            store.load_deployment_runtime_state(entry.deployment.deployment_id)
        except KeyError:
            store.save_deployment_runtime_state(
                RuntimeState(deployment_id=entry.deployment.deployment_id, status=RuntimeStatus.RECOVERED_READY)
            )
    ledger = SQLiteOrderLedger(tmp_path / "supervisor.sqlite")
    adapter = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    manager = OrderManager(ledger=ledger)
    sync = BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="alpaca")
    class StartupWarmupSource:
        def fetch_bars_for_hydration(self, _entry, request):  # type: ignore[no-untyped-def]
            bars = max(int(request.warmup_bars), 1)
            return tuple(
                _bar(request.symbol).model_copy(
                    update={
                        "timeframe": request.timeframe,
                        "timestamp": request.as_of - timedelta(minutes=5 * (bars - index)),
                    }
                )
                for index in range(bars)
            )

    runtime = BrokerRuntimeOrchestrator(
        deployments=deployments,
        runtime_store=store,
        broker_adapter=adapter,
        broker_sync=sync,
        order_manager=manager,
        control_plane=ControlPlane(state_store=store),
        feature_engine=IncrementalFeatureEngine(),
        startup_warmup_bars_source=StartupWarmupSource(),
    )
    return runtime, store


class _RecordingHubAdapter:
    def __init__(self) -> None:
        self.subscribed_symbols: tuple[str, ...] | None = None
        self.emit_callback = None

    def subscribe_bars(self, symbols, *, emit, timeframe="1m"):  # type: ignore[no-untyped-def]
        self.subscribed_symbols = tuple(symbols)
        self.emit_callback = emit

        class _FakeStream:
            def run(self) -> None: ...
            def stop(self) -> None: ...

        return _FakeStream()


class _FakeRunner:
    def __init__(self, stream) -> None:  # type: ignore[no-untyped-def]
        self.stream = stream
        self.is_running = False

    def start(self) -> None:
        self.is_running = True

    def stop(self, *, timeout: float = 5.0) -> None:  # noqa: ARG002
        self.is_running = False


class _RecordingBrokerStreamRunner:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self, *, timeout: float = 5.0) -> None:  # noqa: ARG002
        self.stopped = True


def _make_hub() -> MarketDataStreamHub:
    return MarketDataStreamHub(market_data_adapter=_RecordingHubAdapter(), runner_factory=_FakeRunner)


def test_supervisor_registers_with_hub_and_dispatches_bars_via_hub(tmp_path) -> None:
    spy_components = _components(symbol="SPY")
    qqq_components = _components(symbol="QQQ")
    deployments = (
        BrokerRuntimeDeployment(
            deployment=_deployment(DEPLOYMENT_ID_A, spy_components),
            components=spy_components,
            account_id=ACCOUNT_ID,
        ),
        BrokerRuntimeDeployment(
            deployment=_deployment(DEPLOYMENT_ID_B, qqq_components),
            components=qqq_components,
            account_id=ACCOUNT_ID,
        ),
    )
    runtime, _ = _build_runtime(tmp_path, deployments=deployments)
    hub = _make_hub()
    broker_runner = _RecordingBrokerStreamRunner()
    supervisor = BrokerRuntimeSupervisor(
        account_trading=runtime,
        market_data_hub=hub,
        broker_stream_runner=broker_runner,
    )

    supervisor.start(deployments)
    try:
        # Hub now knows about the supervisor and the union of its symbols.
        assert supervisor.consumer_id in hub.consumer_ids
        assert hub.subscribed_symbols == ("QQQ", "SPY")
        assert broker_runner.started is True

        # Bars dispatched through the hub reach the right deployments.
        hub.dispatch_bar(_bar("SPY"))
        hub.dispatch_bar(_bar("QQQ"))
        hub.dispatch_bar(_bar("IWM"))  # nobody subscribed

        spy_state = runtime.loop_status(DEPLOYMENT_ID_A)
        qqq_state = runtime.loop_status(DEPLOYMENT_ID_B)
        assert spy_state.last_bar_timestamp is not None
        assert qqq_state.last_bar_timestamp is not None
    finally:
        supervisor.stop()
        assert supervisor.consumer_id not in hub.consumer_ids
        assert broker_runner.stopped is True


def test_supervisor_subscribes_to_deployment_owned_position_symbols_outside_watchlist(tmp_path) -> None:
    components = _components(symbol="SPY")
    deployment = BrokerRuntimeDeployment(
        deployment=_deployment(DEPLOYMENT_ID_A, components),
        components=components,
        account_id=ACCOUNT_ID,
    )
    runtime, store = _build_runtime(tmp_path, deployments=(deployment,))
    store.save_broker_position_snapshot(
        BrokerPositionSnapshot(
            account_id=ACCOUNT_ID,
            symbol="TQQQ",
            qty=3.0,
            side=BrokerPositionSide.LONG,
            avg_entry_price=65.0,
            market_value=195.0,
            deployment_id=DEPLOYMENT_ID_A,
            status="open",
        )
    )
    hub = _make_hub()
    supervisor = BrokerRuntimeSupervisor(account_trading=runtime, market_data_hub=hub)

    supervisor.start((deployment,))
    try:
        assert hub.subscribed_symbols == ("SPY", "TQQQ")
        assert supervisor.subscribed_symbols == ("SPY", "TQQQ")
    finally:
        supervisor.stop()


def test_multiple_consumers_share_the_same_hub_subscription(tmp_path) -> None:
    """Supervisor + a sim-lab-live consumer on the same hub subscribe-once."""
    components = _components(symbol="SPY")
    deployments = (
        BrokerRuntimeDeployment(
            deployment=_deployment(DEPLOYMENT_ID_A, components),
            components=components,
            account_id=ACCOUNT_ID,
        ),
    )
    runtime, _ = _build_runtime(tmp_path, deployments=deployments)
    hub = _make_hub()
    sim_received: list[str] = []
    hub.register("sim-lab-live", ["SPY", "QQQ"], lambda bar: sim_received.append(bar.symbol))
    supervisor = BrokerRuntimeSupervisor(account_trading=runtime, market_data_hub=hub)
    supervisor.start(deployments)

    try:
        assert hub.subscribed_symbols == ("QQQ", "SPY")  # union: SPY (broker+sim) + QQQ (sim only)
        assert set(hub.consumer_ids) == {"sim-lab-live", supervisor.consumer_id}

        hub.dispatch_bar(_bar("SPY"))
        hub.dispatch_bar(_bar("QQQ"))

        # Sim lab sees both; broker supervisor only sees SPY (its only universe symbol).
        assert sim_received == ["SPY", "QQQ"]
        assert runtime.loop_status(DEPLOYMENT_ID_A).last_bar_timestamp is not None
    finally:
        supervisor.stop()
        # Sim lab consumer is still registered on the hub after broker stops.
        assert "sim-lab-live" in hub.consumer_ids


def test_double_start_raises(tmp_path) -> None:
    components = _components()
    deployments = (
        BrokerRuntimeDeployment(
            deployment=_deployment(DEPLOYMENT_ID_A, components),
            components=components,
            account_id=ACCOUNT_ID,
        ),
    )
    runtime, _ = _build_runtime(tmp_path, deployments=deployments)
    supervisor = BrokerRuntimeSupervisor(account_trading=runtime, market_data_hub=_make_hub())
    supervisor.start(deployments)
    try:
        with pytest.raises(BrokerRuntimeSupervisorError):
            supervisor.start(deployments)
    finally:
        supervisor.stop()


def test_stop_before_start_is_noop(tmp_path) -> None:
    runtime, _ = _build_runtime(tmp_path, deployments=())
    supervisor = BrokerRuntimeSupervisor(account_trading=runtime, market_data_hub=_make_hub())
    supervisor.stop()  # no exception
    assert supervisor.is_running is False


def test_supervisor_with_no_deployments_skips_hub_registration(tmp_path) -> None:
    runtime, _ = _build_runtime(tmp_path, deployments=())
    hub = _make_hub()
    supervisor = BrokerRuntimeSupervisor(account_trading=runtime, market_data_hub=hub)
    supervisor.start(())
    try:
        assert supervisor.is_running is True
        assert supervisor.consumer_id not in hub.consumer_ids
        assert hub.subscribed_symbols == ()
    finally:
        supervisor.stop()


def test_reload_deactivated_deployment_stops_runtime_and_unregisters_hub(tmp_path) -> None:
    components = _components(symbol="SPY")
    deployment = BrokerRuntimeDeployment(
        deployment=_deployment(DEPLOYMENT_ID_A, components),
        components=components,
        account_id=ACCOUNT_ID,
    )

    class FakeAccountTrading:
        def __init__(self) -> None:
            self.stopped: list[UUID] = []

        def start_deployment_runtime(self, deployment_id: UUID):
            assert deployment_id == DEPLOYMENT_ID_A
            return SimpleNamespace(running=True, last_error=None, state=RuntimeStatus.RUNNING)

        def evict_deployment_caches(self, deployment_id: UUID):
            assert deployment_id == DEPLOYMENT_ID_A
            return None

        def stop_deployment_runtime(self, deployment_id: UUID):
            self.stopped.append(deployment_id)
            return SimpleNamespace(running=False, last_error=None, state=RuntimeStatus.STOPPED)

        def process_completed_bar(self, deployment_id: UUID, bar: NormalizedBar) -> None:
            raise AssertionError("deactivated deployment should not receive bars")

    account_trading = FakeAccountTrading()
    hub = _make_hub()
    supervisor = BrokerRuntimeSupervisor(account_trading=account_trading, market_data_hub=hub)  # type: ignore[arg-type]
    supervisor.start((deployment,))

    reloaded = supervisor.reload_deployment(DEPLOYMENT_ID_A)

    assert reloaded is False
    assert supervisor.active_deployment_ids == ()
    assert supervisor.consumer_id not in hub.consumer_ids
    assert account_trading.stopped == [DEPLOYMENT_ID_A]
