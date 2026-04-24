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
from backend.app.domain import CandidateSide, IntentType, OrderType, ProgramVersion, TimeInForce, TradingMode
from backend.app.governor import GovernorDecision, GovernorPolicy
from backend.app.operations import OperationsCenterService
import backend.app.operations.service as operations_service_module
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderManager
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.pipeline import PipelineEvent, PipelineEventType
from backend.app.runtime import DeploymentContext, ExecutionIntent, RuntimeState, RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
RECOVERED_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")
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


def _program(version: int = 3) -> ProgramVersion:
    return ProgramVersion(
        id=PROGRAM_ID,
        program_id=uuid4(),
        name="Paper Runtime Program",
        version=version,
        strategy_version_id=uuid4(),
        strategy_controls_version_id=uuid4(),
        risk_profile_version_id=uuid4(),
        execution_style_version_id=uuid4(),
        universe_snapshot_id=uuid4(),
    )


def _deployment(deployment_id: UUID = DEPLOYMENT_ID) -> DeploymentContext:
    return DeploymentContext(deployment_id=deployment_id, program=_program())


def _intent(deployment_id: UUID = DEPLOYMENT_ID) -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=deployment_id,
        program_version_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=NOW,
        signal_name="entry",
        reason="signal_condition_true",
        governor_approved=True,
        governor_reason="approved",
    )


def _order(status: InternalOrderStatus = InternalOrderStatus.ACCEPTED, deployment_id: UUID = DEPLOYMENT_ID) -> InternalOrder:
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent(deployment_id))
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
    store.save_deployment_runtime_state(
        RuntimeState(
            deployment_id=DEPLOYMENT_ID,
            status=RuntimeStatus.BLOCKED_RECOVERY if stale else RuntimeStatus.RUNNING,
            last_bar_timestamp_by_symbol_timeframe={"SPY:5m": NOW - timedelta(minutes=5)},
            last_execution_intent_timestamp=NOW,
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


def test_deployment_operations_shows_orders_trades_timestamps_and_governor_state(tmp_path) -> None:
    service, _, order = _service(tmp_path)

    operations = service.get_deployment_operations(DEPLOYMENT_ID)

    assert operations.runtime_status == RuntimeStatus.RUNNING
    assert operations.program_id == PROGRAM_ID
    assert operations.program_version == 3
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


def test_order_detail_unknown_broker_state_renders_unknown_stale(tmp_path) -> None:
    service, _store, order = _service(tmp_path)

    detail = service.get_order_detail(order.order_id)

    assert detail.broker_mapping is None
    assert detail.broker_status == "unknown_stale"
