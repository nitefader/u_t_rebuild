from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import BrokerOrderStatus, BrokerSync, FakeBrokerAdapter
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
from backend.app.features import NormalizedBar, ResolvedProgramComponents
from backend.app.market_data import AlpacaMarketDataAdapter
from backend.app.orders import OrderManager
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime import (
    BrokerRuntimeDeployment,
    BrokerRuntimeOrchestrator,
    DeploymentContext,
    PaperRuntimeSupervisor,
    PaperRuntimeSupervisorError,
    RuntimeState,
    RuntimeStatus,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID_A = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
DEPLOYMENT_ID_B = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")


def _components(*, symbol: str = "SPY") -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Supervisor Strategy",
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
    return ResolvedProgramComponents(
        program=ProgramVersion(
            id=uuid4(),
            program_id=uuid4(),
            name="Supervisor Program",
            version=1,
            strategy_version_id=strategy_id,
            strategy_controls_version_id=controls_id,
            risk_profile_version_id=risk_id,
            execution_style_version_id=execution_id,
            universe_snapshot_id=universe_id,
        ),
        strategy=strategy,
        strategy_controls=StrategyControlsVersion(
            id=controls_id,
            strategy_controls_id=uuid4(),
            version=1,
            name="5m",
            timeframe="5m",
        ),
        risk_profile=RiskProfileVersion(
            id=risk_id,
            risk_profile_id=uuid4(),
            version=1,
            name="Fixed",
            sizing_method=PositionSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
        execution_style=ExecutionStyleVersion(
            id=execution_id,
            execution_style_id=uuid4(),
            version=1,
            name="Market",
            entry_order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        ),
        universe=UniverseSnapshot(
            id=universe_id,
            universe_id=uuid4(),
            version=1,
            name="Universe",
            symbols=[UniverseSymbol(symbol=symbol)],
        ),
    )


def _bar(symbol: str = "SPY", *, close: float = 100, open_: float = 99) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000,
    )


def _seed_account(store: SQLiteRuntimeStore, account_id: UUID = ACCOUNT_ID, *, stale: bool = False) -> None:
    from backend.app.brokers import BrokerSyncState

    now = datetime.now(timezone.utc)
    store.save_broker_account(
        BrokerAccount(
            id=account_id,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=account_id,
            last_sync_at=now,
            last_successful_sync_at=None if stale else now,
            is_stale=stale,
            stale_reason="stale" if stale else None,
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
    runtime = BrokerRuntimeOrchestrator(
        deployments=deployments,
        runtime_store=store,
        broker_adapter=adapter,
        broker_sync=sync,
        order_manager=manager,
        control_plane=ControlPlane(state_store=store),
    )
    return runtime, store


class _RecordingMarketDataAdapter:
    """Stand-in for AlpacaMarketDataAdapter — records subscribe_bars calls."""

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


class _RecordingMarketDataRunner:
    def __init__(self, stream) -> None:  # type: ignore[no-untyped-def]
        self.stream = stream
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self, *, timeout: float = 5.0) -> None:  # noqa: ARG002
        self.stopped = True


class _RecordingBrokerStreamRunner:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self, *, timeout: float = 5.0) -> None:  # noqa: ARG002
        self.stopped = True


def test_supervisor_dispatches_bar_only_to_subscribed_deployments(tmp_path) -> None:
    spy_components = _components(symbol="SPY")
    qqq_components = _components(symbol="QQQ")
    deployments = (
        BrokerRuntimeDeployment(
            deployment=DeploymentContext(deployment_id=DEPLOYMENT_ID_A, program=spy_components.program, mode=TradingMode.BROKER_PAPER.value),
            components=spy_components,
            account_id=ACCOUNT_ID,
        ),
        BrokerRuntimeDeployment(
            deployment=DeploymentContext(deployment_id=DEPLOYMENT_ID_B, program=qqq_components.program, mode=TradingMode.BROKER_PAPER.value),
            components=qqq_components,
            account_id=ACCOUNT_ID,
        ),
    )
    runtime, _ = _build_runtime(tmp_path, deployments=deployments)
    market_data = _RecordingMarketDataAdapter()
    market_data_runner_holder: list[_RecordingMarketDataRunner] = []

    def runner_factory(stream):
        runner = _RecordingMarketDataRunner(stream)
        market_data_runner_holder.append(runner)
        return runner

    supervisor = PaperRuntimeSupervisor(
        broker_runtime=runtime,
        market_data_adapter=market_data,
        broker_stream_runner=_RecordingBrokerStreamRunner(),
        market_data_stream_factory=runner_factory,
    )
    supervisor.start(deployments)
    try:
        assert supervisor.is_running is True
        assert supervisor.subscribed_symbols == ("QQQ", "SPY")
        assert market_data.subscribed_symbols == ("QQQ", "SPY")
        assert market_data_runner_holder[0].started is True

        # Dispatch a SPY bar — only DEPLOYMENT_A should process it.
        supervisor.dispatch_bar(_bar(symbol="SPY"))
        # Dispatch a QQQ bar — only DEPLOYMENT_B.
        supervisor.dispatch_bar(_bar(symbol="QQQ"))
        # Dispatch an IWM bar — neither.
        supervisor.dispatch_bar(_bar(symbol="IWM"))

        spy_state = runtime.loop_status(DEPLOYMENT_ID_A)
        qqq_state = runtime.loop_status(DEPLOYMENT_ID_B)
        assert spy_state.last_bar_timestamp is not None
        assert qqq_state.last_bar_timestamp is not None
    finally:
        supervisor.stop()
        assert market_data_runner_holder[0].stopped is True


def test_supervisor_start_is_idempotent_in_one_session(tmp_path) -> None:
    components = _components(symbol="SPY")
    deployments = (
        BrokerRuntimeDeployment(
            deployment=DeploymentContext(deployment_id=DEPLOYMENT_ID_A, program=components.program),
            components=components,
            account_id=ACCOUNT_ID,
        ),
    )
    runtime, _ = _build_runtime(tmp_path, deployments=deployments)
    market_data = _RecordingMarketDataAdapter()
    supervisor = PaperRuntimeSupervisor(
        broker_runtime=runtime,
        market_data_adapter=market_data,
        market_data_stream_factory=_RecordingMarketDataRunner,
    )
    supervisor.start(deployments)
    try:
        with pytest.raises(PaperRuntimeSupervisorError):
            supervisor.start(deployments)
    finally:
        supervisor.stop()


def test_supervisor_stop_is_idempotent_when_not_running(tmp_path) -> None:
    components = _components(symbol="SPY")
    deployments = (
        BrokerRuntimeDeployment(
            deployment=DeploymentContext(deployment_id=DEPLOYMENT_ID_A, program=components.program),
            components=components,
            account_id=ACCOUNT_ID,
        ),
    )
    runtime, _ = _build_runtime(tmp_path, deployments=deployments)
    supervisor = PaperRuntimeSupervisor(
        broker_runtime=runtime,
        market_data_adapter=_RecordingMarketDataAdapter(),
    )
    # Should not raise.
    supervisor.stop()
    assert supervisor.is_running is False


def test_supervisor_starts_with_no_deployments_skips_market_data_subscription(tmp_path) -> None:
    runtime, _ = _build_runtime(tmp_path, deployments=())
    market_data = _RecordingMarketDataAdapter()
    supervisor = PaperRuntimeSupervisor(
        broker_runtime=runtime,
        market_data_adapter=market_data,
    )
    supervisor.start(())
    try:
        assert supervisor.is_running is True
        assert supervisor.subscribed_symbols == ()
        assert market_data.subscribed_symbols is None
    finally:
        supervisor.stop()


def test_market_data_adapter_subscribe_bars_registers_async_handler() -> None:
    """The handler we hand to alpaca-py is async; emit fires synchronously inside it."""
    import asyncio

    captured: list = []

    class FakeStream:
        def subscribe_bars(self, handler, *symbols):  # type: ignore[no-untyped-def]
            captured.append({"handler": handler, "symbols": symbols})

        def run(self) -> None: ...

    received: list[NormalizedBar] = []
    adapter = AlpacaMarketDataAdapter(stream_client=FakeStream(), load_env=False)
    adapter.subscribe_bars(["SPY", "qqq"], emit=received.append, timeframe="1m")

    assert len(captured) == 1
    assert captured[0]["symbols"] == ("SPY", "QQQ")

    handler = captured[0]["handler"]
    fake_bar = {
        "S": "SPY",
        "t": "2026-01-02T14:30:00+00:00",
        "o": 100,
        "h": 101,
        "l": 99,
        "c": 100.5,
        "v": 1000,
    }
    asyncio.run(handler(fake_bar))

    assert len(received) == 1
    assert received[0].symbol == "SPY"
    assert received[0].timeframe == "1m"
