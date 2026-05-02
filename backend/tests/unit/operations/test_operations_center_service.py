from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSyncState,
)
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.control_plane import ControlPlane
from backend.app.deployments import Deployment
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    CandidateSide,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    OrderType,
    ProgramVersion,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
    TimeInForce,
    TradingMode,
)
from backend.app.governor import GovernorDecision, GovernorPolicy
from backend.app.operations import OperationsCenterService
import backend.app.operations.service as operations_service_module
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.pipeline import PipelineEvent, PipelineEventType
from backend.app.runtime import DeploymentContext, RuntimeState, RuntimeStatus
from backend.tests.fixtures.modern_order import make_signal_plan_order


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
RECOVERED_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")
STRATEGY_VERSION_ID = UUID("88888888-7777-6666-5555-444444444444")
NOW = datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc)


class ReadOnlyBrokerSyncState:
    def __init__(self, *, positions: tuple[BrokerPositionSnapshot, ...], fills: tuple[BrokerFillUpdateEvent, ...] = ()) -> None:
        self.positions = positions
        self._fills = fills

    def latest_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return tuple(position for position in self.positions if position.account_id == account_id)

    def fills(self) -> tuple[BrokerFillUpdateEvent, ...]:
        return self._fills

    def submit_order(self, order) -> None:  # type: ignore[no-untyped-def]
        raise AssertionError("operations center must not call broker-like submit_order")

    def get_account_snapshot(self, account_id: UUID) -> None:
        raise AssertionError("operations center must not fetch broker snapshots directly")

    def get_positions(self, account_id: UUID) -> None:
        raise AssertionError("operations center must not fetch positions directly")


class RecordingControlPlane(ControlPlane):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, UUID | str]] = []

    def pause_deployment(self, deployment_id: UUID) -> None:
        self.calls.append(("pause_deployment", deployment_id))
        super().pause_deployment(deployment_id)

    def resume_deployment(self, deployment_id: UUID) -> None:
        self.calls.append(("resume_deployment", deployment_id))
        super().resume_deployment(deployment_id)

    def pause_account(self, account_id: UUID) -> None:
        self.calls.append(("pause_account", account_id))
        super().pause_account(account_id)

    def resume_account(self, account_id: UUID) -> None:
        self.calls.append(("resume_account", account_id))
        super().resume_account(account_id)

    def activate_global_kill(self) -> None:
        self.calls.append(("activate_global_kill", "global"))
        super().activate_global_kill()

    def clear_global_kill(self) -> None:
        self.calls.append(("clear_global_kill", "global"))
        super().clear_global_kill()


class StaticDeploymentReader:
    def __init__(self, deployments: tuple[Deployment, ...]) -> None:
        self._deployments = deployments

    def list_deployments(self) -> tuple[Deployment, ...]:
        return self._deployments


def _program(version: int = 3) -> ProgramVersion:
    return ProgramVersion(
        id=PROGRAM_ID,
        program_id=uuid4(),
        name="Runtime Strategy Version",
        version=version,
        strategy_version_id=STRATEGY_VERSION_ID,
        strategy_controls_version_id=uuid4(),
        risk_profile_version_id=uuid4(),
        execution_style_version_id=uuid4(),
        universe_snapshot_id=uuid4(),
    )


def _deployment(deployment_id: UUID = DEPLOYMENT_ID) -> DeploymentContext:
    return DeploymentContext(deployment_id=deployment_id, program=_program())


def _order(status: InternalOrderStatus = InternalOrderStatus.ACCEPTED, deployment_id: UUID = DEPLOYMENT_ID) -> InternalOrder:
    manager = OrderManager()
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=deployment_id)
    if status == InternalOrderStatus.CREATED:
        return order
    return manager.ledger.update_status(order_id=order.order_id, status=status)


def _snapshot() -> BrokerAccountSnapshot:
    return BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        equity=100_000,
        cash=40_000,
        buying_power=80_000,
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        timestamp=NOW,
    )


def _position() -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=10,
        side=BrokerPositionSide.LONG,
        avg_entry_price=400,
        market_value=4_000,
        timestamp=NOW,
    )


def _open_broker_order(order: InternalOrder) -> BrokerOpenOrderSnapshot:
    return BrokerOpenOrderSnapshot(
        account_id=order.account_id,
        broker_order_id="broker-1",
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        side=order.side.value,
        qty=order.quantity,
        status=BrokerOrderStatus.ACCEPTED,
        order_type=order.order_type.value,
        timestamp=NOW,
    )


def _manual_order() -> InternalOrder:
    manager = OrderManager()
    order = manager.create_manual_order(
        account_id=ACCOUNT_ID,
        symbol="MRNA",
        side=CandidateSide.LONG,
        quantity=20,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        reason="operator smoke order",
    )
    return manager.ledger.update_status(order_id=order.order_id, status=InternalOrderStatus.FILLED)


def _signal_plan_order(
    *,
    account_id: UUID = ACCOUNT_ID,
    deployment_id: UUID = DEPLOYMENT_ID,
    signal_plan_id: UUID | None = None,
    created_at: datetime = NOW,
) -> InternalOrder:
    current_signal_plan_id = signal_plan_id or uuid4()
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"signal-plan:{account_id}:{current_signal_plan_id}",
        account_id=account_id,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=deployment_id,
        strategy_id=PROGRAM_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        signal_plan_id=current_signal_plan_id,
        opening_signal_plan_id=current_signal_plan_id,
        current_signal_plan_id=current_signal_plan_id,
        position_lineage_id=current_signal_plan_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        lifecycle_intent=InternalOrderIntent.OPEN.value,
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.CREATED,
        created_at=created_at,
        updated_at=created_at,
        signal_name="entry",
        reason="signal_condition_true",
    )


def _signal_plan(
    *,
    signal_plan_id: UUID | None = None,
    deployment_id: UUID = DEPLOYMENT_ID,
    symbol: str = "SPY",
    created_at: datetime = NOW,
) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=signal_plan_id or uuid4(),
        deployment_id=deployment_id,
        strategy_id=PROGRAM_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        symbol=symbol,
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        created_at=created_at,
    )


def _account_evaluation(
    *,
    account_id: UUID = ACCOUNT_ID,
    signal_plan: SignalPlan,
    governor_decision: GovernorDecisionTrace | None = None,
    evaluated_at: datetime = NOW,
) -> AccountSignalPlanEvaluation:
    return AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan.signal_plan_id,
        deployment_id=signal_plan.deployment_id,
        strategy_id=signal_plan.strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
        governor_decision=governor_decision,
        evaluated_at=evaluated_at,
    )


def _governor_trace(
    *,
    account_id: UUID = ACCOUNT_ID,
    signal_plan_id: UUID,
    approved: bool = True,
) -> GovernorDecisionTrace:
    return GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan_id,
        status=GovernorDecisionStatus.APPROVED if approved else GovernorDecisionStatus.REJECTED,
        approved=approved,
        reasons=("approved",) if approved else ("max_open_positions_exceeded",),
        evaluated_at=NOW,
    )


def _sync_state(*, stale: bool = False) -> BrokerSyncState:
    synced = NOW - timedelta(minutes=5) if stale else NOW
    return BrokerSyncState(
        account_id=ACCOUNT_ID,
        last_sync_at=synced,
        last_poll_sync_at=synced,
        last_successful_sync_at=None if stale else synced,
        is_stale=stale,
        stale_reason="broker_snapshot_age_exceeded_30s" if stale else None,
    )


def _pipeline_event(event_type: PipelineEventType, timestamp: datetime = NOW) -> PipelineEvent:
    return PipelineEvent(
        sequence=1,
        timestamp=timestamp,
        deployment_id=DEPLOYMENT_ID,
        event_type=event_type,
        symbol="SPY",
        message=event_type.value,
    )


def _decision(approved: bool = False) -> GovernorDecision:
    if approved:
        return GovernorDecision.approve(projected_state={"deployment_id": str(DEPLOYMENT_ID), "account_id": str(ACCOUNT_ID)})
    return GovernorDecision.reject(
        reason="broker_sync_stale",
        rule_id="stale_broker_sync_blocks_open",
        projected_state={"deployment_id": str(DEPLOYMENT_ID), "account_id": str(ACCOUNT_ID)},
    )


def _store(tmp_path, *, stale: bool = False) -> tuple[SQLiteRuntimeStore, InternalOrder]:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    order = _order()
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper account",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref=f"alpaca-paper:{ACCOUNT_ID}:test",
            validation_status=BrokerAccountValidationStatus.VALID,
            last_account_snapshot=_snapshot(),
            broker_sync_freshness=_sync_state(stale=stale),
            created_at=NOW,
        )
    )
    store.save_order(order)
    store.save_broker_account_snapshot(_snapshot())
    store.save_broker_sync_freshness(_sync_state(stale=stale))
    store.save_broker_open_order_snapshot(_open_broker_order(order))
    store.save_broker_position_snapshot(_position())
    store.save_deployment_runtime_state(
        RuntimeState(
            deployment_id=DEPLOYMENT_ID,
            status=RuntimeStatus.BLOCKED_RECOVERY if stale else RuntimeStatus.RUNNING,
            last_bar_timestamp_by_symbol_timeframe={"SPY:5m": NOW - timedelta(minutes=5)},
            last_signal_plan_timestamp=NOW,
        )
    )
    store.save_deployment_runtime_state(
        RuntimeState(deployment_id=RECOVERED_DEPLOYMENT_ID, status=RuntimeStatus.RECOVERED_READY)
    )
    store.save_portfolio_governor_state("portfolio-governor", GovernorPolicy(max_open_positions=5))
    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        qty=1,
        price=401,
        side=order.side.value,
        broker_order_id="broker-1",
        broker_execution_id="exec-1",
        event_at=NOW,
    )
    store.save_fill(fill, deployment_id=DEPLOYMENT_ID)
    return store, order


def _service(tmp_path, *, stale: bool = False) -> tuple[OperationsCenterService, SQLiteRuntimeStore, InternalOrder]:
    store, order = _store(tmp_path, stale=stale)
    service = OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
        broker_sync_reader=ReadOnlyBrokerSyncState(positions=(_position(),), fills=()),
        deployments=(_deployment(), _deployment(RECOVERED_DEPLOYMENT_ID)),
        latest_pipeline_events=(
            _pipeline_event(PipelineEventType.FEATURE_UPDATED, NOW - timedelta(minutes=5)),
            _pipeline_event(PipelineEventType.GOVERNOR_DECISION, NOW),
        ),
        latest_governor_decisions=(_decision(),),
    )
    return service, store, order


def test_runtime_overview_includes_recovery_control_broker_sync_deployment_order_and_governor_state(tmp_path) -> None:
    service, store, _ = _service(tmp_path, stale=True)
    control_plane = ControlPlane(state_store=store)
    control_plane.set_system_recovery_active(True)
    control_plane.activate_global_kill()
    service = OperationsCenterService(
        control_plane=control_plane,
        runtime_store=store,
        broker_sync_reader=ReadOnlyBrokerSyncState(positions=(_position(),)),
        deployments=(_deployment(), _deployment(RECOVERED_DEPLOYMENT_ID)),
        latest_pipeline_events=(_pipeline_event(PipelineEventType.GOVERNOR_DECISION, NOW),),
        latest_governor_decisions=(_decision(),),
    )

    overview = service.get_runtime_overview()

    assert overview.system_recovery_active is True
    assert overview.global_kill_active is True
    assert overview.broker_accounts[0].snapshot == _snapshot()
    assert overview.stale_sync_accounts[0].account_id == ACCOUNT_ID
    assert overview.open_orders_count == 1
    assert overview.open_positions_count == 1
    assert overview.latest_governor_decisions == (_decision(),)
    assert overview.latest_broker_sync_timestamp == NOW - timedelta(minutes=5)
    assert overview.latest_runtime_event_timestamp == NOW


def test_stale_and_recovery_deployments_are_visible_with_recovered_ready_not_running(tmp_path) -> None:
    service, _, _ = _service(tmp_path, stale=True)

    overview = service.get_runtime_overview()

    assert [deployment.deployment_id for deployment in overview.blocked_deployments] == [DEPLOYMENT_ID]
    recovered = next(deployment for deployment in overview.deployments if deployment.deployment_id == RECOVERED_DEPLOYMENT_ID)
    assert recovered.status == RuntimeStatus.RECOVERED_READY
    assert recovered.is_running is False


def test_account_operations_shows_broker_snapshot_positions_and_control_state(tmp_path) -> None:
    service, store, _ = _service(tmp_path)
    ControlPlane(state_store=store).pause_account(ACCOUNT_ID)

    operations = OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
        broker_sync_reader=ReadOnlyBrokerSyncState(positions=(_position(),)),
        deployments=(_deployment(),),
    ).get_account_operations(ACCOUNT_ID)

    assert operations.broker_account_snapshot == _snapshot()
    assert operations.broker_sync_freshness == _sync_state()
    assert len(operations.open_broker_orders) == 1
    assert operations.positions == (_position(),)
    assert operations.internal_order_ledger_summary.open_count == 1
    assert operations.deployments[0].deployment_id == DEPLOYMENT_ID
    assert operations.is_paused is True


def test_account_operations_open_orders_count_matches_visible_broker_orders(tmp_path) -> None:
    service, _, _ = _service(tmp_path)

    overview = service.get_runtime_overview()
    account_summary = next(account for account in overview.broker_accounts if account.account_id == ACCOUNT_ID)
    operations = service.get_account_operations(ACCOUNT_ID)

    assert account_summary.open_orders_count == len(operations.open_broker_orders) == 1


def test_runtime_overview_open_orders_count_includes_external_broker_orders(tmp_path) -> None:
    service, store, _ = _service(tmp_path)
    store.save_broker_open_order_snapshot(
        BrokerOpenOrderSnapshot(
            account_id=ACCOUNT_ID,
            broker_order_id="external-broker-1",
            client_order_id="external-client-order",
            symbol="NVDA",
            side="buy",
            qty=1,
            status=BrokerOrderStatus.ACCEPTED,
            order_type="limit",
            timestamp=NOW,
        )
    )

    overview = service.get_runtime_overview()
    account_summary = next(account for account in overview.broker_accounts if account.account_id == ACCOUNT_ID)

    assert account_summary.open_orders_count == 2
    assert overview.open_orders_count == 2


def test_manual_operator_order_without_deployment_lineage_does_not_break_operations_projection() -> None:
    ledger = OrderManager().ledger
    ledger.add(_manual_order())
    service = OperationsCenterService(control_plane=ControlPlane(), order_ledger=ledger)

    overview = service.get_runtime_overview()
    account = service.get_account_operations(ACCOUNT_ID)

    assert overview.deployments == ()
    assert account.deployments == ()
    assert account.internal_order_ledger_summary.total_count == 1


def test_runtime_overview_does_not_count_historical_order_or_event_deployment_lineage() -> None:
    ledger = OrderManager().ledger
    historical_order = _signal_plan_order()
    ledger.add(historical_order)
    service = OperationsCenterService(
        control_plane=ControlPlane(),
        order_ledger=ledger,
        latest_pipeline_events=(_pipeline_event(PipelineEventType.GOVERNOR_DECISION, NOW),),
    )

    overview = service.get_runtime_overview()
    account = service.get_account_operations(ACCOUNT_ID)

    assert overview.deployments == ()
    assert account.deployments[0].deployment_id == DEPLOYMENT_ID
    assert account.internal_order_ledger_summary.total_count == 1


def test_runtime_overview_counts_real_deployment_records_without_order_lineage() -> None:
    service = OperationsCenterService(
        control_plane=ControlPlane(),
        deployment_reader=StaticDeploymentReader(
            (
                Deployment(
                    deployment_id=DEPLOYMENT_ID,
                    name="Mean Reversion Deployment",
                    strategy_version_id=STRATEGY_VERSION_ID,
                    watchlist_ids=(uuid4(),),
                    subscribed_account_ids=(ACCOUNT_ID,),
                ),
            )
        ),
    )

    overview = service.get_runtime_overview()

    assert [deployment.deployment_id for deployment in overview.deployments] == [DEPLOYMENT_ID]
    assert overview.deployments[0].account_id == ACCOUNT_ID
    assert overview.deployments[0].strategy_version_id == STRATEGY_VERSION_ID


def test_account_signal_plan_evaluations_project_from_signal_plan_orders(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "utos.db")
    older_order = _signal_plan_order(created_at=NOW - timedelta(minutes=2))
    newer_order = _signal_plan_order(created_at=NOW)
    store.save_order(older_order)
    store.save_order(newer_order)
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    evaluations = service.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID, limit=1)

    assert len(evaluations) == 1
    assert evaluations[0].evaluation_id == newer_order.account_evaluation_id
    assert evaluations[0].account_id == ACCOUNT_ID
    assert evaluations[0].signal_plan_id == newer_order.signal_plan_id
    assert evaluations[0].deployment_id == DEPLOYMENT_ID
    assert evaluations[0].strategy_id == PROGRAM_ID
    assert evaluations[0].status.value == "accepted"
    assert evaluations[0].participation_decision.value == "participate"
    assert evaluations[0].governor_decision is not None
    assert evaluations[0].governor_decision.governor_decision_id == newer_order.governor_decision_id


def test_account_signal_plan_evaluations_filter_by_deployment_and_signal_plan(tmp_path) -> None:
    store, _ = _store(tmp_path)
    target_signal_plan_id = uuid4()
    target_order = _signal_plan_order(signal_plan_id=target_signal_plan_id)
    other_order = _signal_plan_order(deployment_id=RECOVERED_DEPLOYMENT_ID)
    store.save_order(target_order)
    store.save_order(other_order)
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    evaluations = service.list_account_signal_plan_evaluations(
        deployment_id=DEPLOYMENT_ID,
        signal_plan_id=target_signal_plan_id,
    )

    assert [evaluation.evaluation_id for evaluation in evaluations] == [target_order.account_evaluation_id]


def test_signal_plans_read_from_persisted_runtime_store_with_filters(tmp_path) -> None:
    store, _ = _store(tmp_path)
    target = _signal_plan(symbol="SPY", created_at=NOW)
    other_symbol = _signal_plan(symbol="QQQ", created_at=NOW - timedelta(minutes=1))
    other_deployment = _signal_plan(deployment_id=RECOVERED_DEPLOYMENT_ID, symbol="SPY")
    for plan in (target, other_symbol, other_deployment):
        store.save_signal_plan(plan)
    store.save_account_signal_plan_evaluation(_account_evaluation(signal_plan=target))
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    rows = service.list_signal_plans(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        symbol="spy",
    )

    assert rows == (target,)


def test_governor_decision_traces_project_from_persisted_evaluations_and_overview(tmp_path) -> None:
    store, _ = _store(tmp_path)
    plan = _signal_plan()
    trace = _governor_trace(signal_plan_id=plan.signal_plan_id, approved=False)
    store.save_signal_plan(plan)
    store.save_account_signal_plan_evaluation(_account_evaluation(signal_plan=plan, governor_decision=trace))
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    traces = service.list_governor_decision_traces(account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)
    overview = service.get_runtime_overview()

    assert traces == (trace,)
    assert len(overview.latest_governor_decisions) == 1
    assert overview.latest_governor_decisions[0].approved is False
    assert overview.latest_governor_decisions[0].reason == "max_open_positions_exceeded"


def test_runtime_overview_counts_persisted_broker_positions_without_live_reader(tmp_path) -> None:
    store, _ = _store(tmp_path)

    overview = OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
    ).get_runtime_overview()

    account_summary = next(account for account in overview.broker_accounts if account.account_id == ACCOUNT_ID)
    assert account_summary.positions_count == 1
    assert overview.open_positions_count == 1


def test_deployment_operations_shows_orders_trades_timestamps_and_governor_state(tmp_path) -> None:
    service, _, order = _service(tmp_path)

    operations = service.get_deployment_operations(DEPLOYMENT_ID)

    assert operations.runtime_status == RuntimeStatus.RUNNING
    assert operations.strategy_version_id == STRATEGY_VERSION_ID
    assert operations.strategy_version == 3
    assert operations.broker_account_id == ACCOUNT_ID
    assert operations.governor_state == GovernorPolicy(max_open_positions=5)
    assert operations.last_market_data_timestamp == NOW - timedelta(minutes=5)
    assert operations.last_broker_sync_timestamp == NOW
    assert operations.last_decision_timestamp == NOW
    assert operations.open_orders == (order,)
    assert len(operations.trades) == 1
    assert operations.latest_pipeline_events[-1].event_type == PipelineEventType.GOVERNOR_DECISION
    assert operations.latest_governor_decisions == (_decision(),)


def test_pause_resume_delegates_to_control_plane_only() -> None:
    control_plane = RecordingControlPlane()
    service = OperationsCenterService(control_plane=control_plane)

    service.pause_deployment(DEPLOYMENT_ID, "maintenance")
    service.resume_deployment(DEPLOYMENT_ID, "done")
    service.pause_account(ACCOUNT_ID, "risk")
    service.resume_account(ACCOUNT_ID, "done")

    assert control_plane.calls == [
        ("pause_deployment", DEPLOYMENT_ID),
        ("resume_deployment", DEPLOYMENT_ID),
        ("pause_account", ACCOUNT_ID),
        ("resume_account", ACCOUNT_ID),
    ]


def test_global_kill_resume_delegates_to_control_plane_only() -> None:
    control_plane = RecordingControlPlane()
    service = OperationsCenterService(control_plane=control_plane)

    service.global_kill("operator")
    service.global_resume("operator")

    assert control_plane.calls == [("activate_global_kill", "global"), ("clear_global_kill", "global")]


def test_global_kill_survives_restart_and_operations_overview_reports_it(tmp_path) -> None:
    store, _ = _store(tmp_path)
    ControlPlane(state_store=store).activate_global_kill()

    restarted_control_plane = ControlPlane(state_store=store)
    overview = OperationsCenterService(control_plane=restarted_control_plane, runtime_store=store).get_runtime_overview()
    decision = restarted_control_plane.can_open_new_position(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        symbol="SPY",
        side="long",
    )

    assert overview.global_kill_active is True
    assert decision.allowed is False
    assert decision.reason == "global_kill_active"


def test_flatten_returns_explicit_not_ready_when_control_plane_has_no_contract() -> None:
    response = OperationsCenterService(control_plane=ControlPlane()).request_flatten_account(ACCOUNT_ID, "operator")

    assert response.accepted is False
    assert response.status == "unsupported_not_ready"
    assert response.reason == "flatten_not_implemented_in_control_plane"


def test_operations_center_does_not_call_broker_adapter_directly_or_create_orders_or_mutate_broker_truth(tmp_path) -> None:
    store, order = _store(tmp_path)
    source = inspect.getsource(operations_service_module)

    service = OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
        broker_sync_reader=ReadOnlyBrokerSyncState(positions=(_position(),)),
    )
    before = store.load_broker_account_snapshot(ACCOUNT_ID)

    service.get_runtime_overview()
    service.get_account_operations(ACCOUNT_ID)
    service.get_deployment_operations(DEPLOYMENT_ID)

    assert store.load_order(order.order_id) == order
    assert store.load_broker_account_snapshot(ACCOUNT_ID) == before
    assert "BrokerAdapter" not in source
    assert "AlpacaBrokerAdapter" not in source
    assert ".submit_order(" not in source
    assert ".create_order(" not in source
    assert "OrderManager" not in source
    assert "save_broker_account_snapshot" not in source
    assert "save_broker_open_order_snapshot" not in source
    assert "save_broker_sync_freshness" not in source


def test_order_detail_returns_internal_truth_mapping_and_fill_summary(tmp_path) -> None:
    service, store, order = _service(tmp_path)
    store.save_broker_order_mapping(
        BrokerOrderMapping(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id="broker-1",
            provider="alpaca",
            account_id=ACCOUNT_ID,
            created_at=NOW,
            last_synced_at=NOW,
        )
    )

    detail = service.get_order_detail(order.order_id)

    assert detail.internal_order == order
    assert detail.broker_mapping is not None
    assert detail.broker_order_id == "broker-1"
    assert detail.broker_status == BrokerOrderStatus.ACCEPTED.value
    assert detail.broker_sync_timestamp == NOW
    assert detail.trade_summary["fill_count"] == 1
    assert detail.trade_summary["filled_quantity"] == 1
    assert "raw" not in detail.model_dump_json().lower()


def test_order_detail_can_be_loaded_by_broker_order_id(tmp_path) -> None:
    service, store, order = _service(tmp_path)
    store.save_broker_order_mapping(
        BrokerOrderMapping(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            broker_order_id="broker-1",
            provider="alpaca",
            account_id=ACCOUNT_ID,
            created_at=NOW,
            last_synced_at=NOW,
        )
    )

    detail = service.get_order_detail_by_broker_order_id("broker-1")

    assert detail.internal_order.order_id == order.order_id
    assert detail.broker_account_id == ACCOUNT_ID
    assert detail.deployment_id == DEPLOYMENT_ID
    assert detail.broker_order_id == "broker-1"


def test_manual_order_detail_allows_null_deployment_and_signal_plan_lineage(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    manual_order = _manual_order()
    store.save_order(manual_order)
    store.save_broker_sync_freshness(_sync_state())
    store.save_broker_order_mapping(
        BrokerOrderMapping(
            order_id=manual_order.order_id,
            client_order_id=manual_order.client_order_id,
            broker_order_id="manual-broker-1",
            provider="alpaca",
            account_id=ACCOUNT_ID,
            created_at=NOW,
            last_synced_at=NOW,
        )
    )
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    detail = service.get_order_detail_by_broker_order_id("manual-broker-1")

    assert detail.internal_order.origin.value == "manual_operator"
    assert detail.broker_account_id == ACCOUNT_ID
    assert detail.deployment_id is None
    assert detail.internal_order.signal_plan_id is None
    assert detail.internal_order.position_lineage_id is None
    assert detail.broker_status == InternalOrderStatus.FILLED.value


def test_order_detail_unknown_broker_state_renders_unknown_stale(tmp_path) -> None:
    service, _store, order = _service(tmp_path)

    detail = service.get_order_detail(order.order_id)

    assert detail.broker_mapping is None
    assert detail.broker_status == "unknown_stale"


# ---------------------------------------------------------------------------
# W2-A-3 (audit P0 #2 — pre-T-7 bundle, 2026-04-30):
# OperationsCenterService.list_account_signal_plan_evaluations reads the
# persisted store first; falls back to order-projection only when the
# store has no rows for the filter (legacy data).
# ---------------------------------------------------------------------------


def test_evaluations_read_from_persisted_store_when_present(tmp_path) -> None:
    """Audit-headline gap: REJECT/IGNORE outcomes that never created an
    order are now visible because the persisted store carries them."""
    from backend.app.domain import (
        AccountEvaluationStatus,
        AccountParticipationDecision,
        AccountSignalPlanEvaluation,
    )
    store, _ = _store(tmp_path)
    rejected = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=PROGRAM_ID,
        status=AccountEvaluationStatus.BLOCKED,
        participation_decision=AccountParticipationDecision.REJECT,
        evaluated_at=NOW,
        rejection_reasons=("portfolio_equity_unavailable",),
    )
    ignored = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=PROGRAM_ID,
        status=AccountEvaluationStatus.REJECTED,
        participation_decision=AccountParticipationDecision.IGNORE,
        evaluated_at=NOW,
        rejection_reasons=("account_has_no_matching_position",),
    )
    store.save_account_signal_plan_evaluation(rejected)
    store.save_account_signal_plan_evaluation(ignored)
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    rows = service.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)

    decisions = {row.participation_decision for row in rows}
    assert AccountParticipationDecision.REJECT in decisions
    assert AccountParticipationDecision.IGNORE in decisions


def test_evaluations_falls_back_to_order_projection_when_store_empty(tmp_path) -> None:
    """Backwards-compat: pre-W2-A databases have orders but no evaluation
    rows. The legacy order-projection path must still render those."""
    store = SQLiteRuntimeStore(tmp_path / "utos.db")
    legacy_order = _signal_plan_order(created_at=NOW)
    store.save_order(legacy_order)
    # NO save_account_signal_plan_evaluation call — simulates legacy data.
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    rows = service.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)

    assert len(rows) == 1
    assert rows[0].evaluation_id == legacy_order.account_evaluation_id


def test_evaluations_persisted_path_does_not_pull_in_legacy_orders(tmp_path) -> None:
    """When the persisted store has rows for an account, the legacy order
    projection is NOT also stitched in — that would be a hybrid contract.
    Operations sees what the orchestrator decided, not a mix.
    """
    from backend.app.domain import (
        AccountEvaluationStatus,
        AccountParticipationDecision,
        AccountSignalPlanEvaluation,
    )
    store, _ = _store(tmp_path)
    # Persist one evaluation row.
    persisted_eval = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=uuid4(),
        deployment_id=DEPLOYMENT_ID,
        strategy_id=PROGRAM_ID,
        status=AccountEvaluationStatus.BLOCKED,
        participation_decision=AccountParticipationDecision.REJECT,
        evaluated_at=NOW,
        rejection_reasons=("portfolio_equity_unavailable",),
    )
    store.save_account_signal_plan_evaluation(persisted_eval)
    # Also save a legacy-style order with a different evaluation_id.
    legacy_order = _signal_plan_order(created_at=NOW)
    store.save_order(legacy_order)
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    rows = service.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)

    # Only the persisted row appears; the legacy order projection does NOT
    # also show up alongside it.
    assert len(rows) == 1
    assert rows[0].evaluation_id == persisted_eval.evaluation_id


def test_evaluations_filter_by_signal_plan_id_through_persisted_store(tmp_path) -> None:
    """Filter still works when reading through the persisted store."""
    from backend.app.domain import (
        AccountEvaluationStatus,
        AccountParticipationDecision,
        AccountSignalPlanEvaluation,
    )
    store, _ = _store(tmp_path)
    target_plan = uuid4()
    other_plan = uuid4()
    target = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=target_plan,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=PROGRAM_ID,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
        evaluated_at=NOW,
    )
    other = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=other_plan,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=PROGRAM_ID,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
        evaluated_at=NOW,
    )
    store.save_account_signal_plan_evaluation(target)
    store.save_account_signal_plan_evaluation(other)
    service = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)

    rows = service.list_account_signal_plan_evaluations(signal_plan_id=target_plan)

    assert len(rows) == 1
    assert rows[0].signal_plan_id == target_plan
