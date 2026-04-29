from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import BrokerOrderResult, BrokerOrderStatus, BrokerSync, FakeBrokerAdapter
from backend.app.control_plane import ControlPlane
from backend.app.decision import SignalEngine
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
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.governor import GovernorPolicy, PortfolioGovernor
from backend.app.orders import OrderManager, OrderManagerError
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator, DeploymentContext, RuntimeState, RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
OTHER_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")


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
    mode: TradingMode = TradingMode.BROKER_PAPER,
    live_order_submission_enabled: bool = False,
) -> tuple[BrokerRuntimeOrchestrator, SQLiteRuntimeStore, FakeBrokerAdapter]:
    store = SQLiteRuntimeStore(tmp_path / f"{deployment_id}.sqlite")
    _seed_account(store, account_id, mode=mode)
    resolved = components or _components()
    try:
        store.load_deployment_runtime_state(deployment_id)
    except KeyError:
        store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RECOVERED_READY))
    ledger = SQLiteOrderLedger(tmp_path / f"{deployment_id}.sqlite")
    manager = order_manager or OrderManager(ledger=ledger, control_plane=control_plane)
    adapter = broker or FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    sync = broker_sync or BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="alpaca")
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
    )

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None
    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar(1)) is None

    state = store.load_deployment_runtime_state(DEPLOYMENT_ID)
    assert state.status == RuntimeStatus.DEGRADED
    assert len(broker.submitted_orders) == 1


def test_broker_account_mode_must_match_deployment_mode(tmp_path) -> None:
    runtime, store, broker = _runtime(tmp_path)
    _seed_account(store, ACCOUNT_ID, mode=TradingMode.BROKER_LIVE)

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert store.list_orders() == ()
    assert broker.submitted_orders == []
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).last_error == "broker_account_mode_mismatch"


def test_sim_lab_and_chart_lab_do_not_import_or_use_broker_adapter() -> None:
    import backend.app.chart_lab.preview_service as chart_preview
    import backend.app.simulation.engine as sim_engine

    sources = inspect.getsource(chart_preview) + inspect.getsource(sim_engine)

    assert "BrokerAdapter" not in sources
    assert "AlpacaBrokerAdapter" not in sources


def test_runtime_restart_resumes_idempotently_without_duplicate_order_submission(tmp_path) -> None:
    runtime, _store, broker = _runtime(tmp_path)

    assert runtime.process_completed_bar(DEPLOYMENT_ID, _bar()) is not None
    restarted, _store, _same_broker = _runtime(tmp_path, broker=broker)
    assert restarted.process_completed_bar(DEPLOYMENT_ID, _bar()) is None

    assert len(broker.submitted_orders) == 1


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
