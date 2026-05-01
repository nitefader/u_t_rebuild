from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerSync,
)
from backend.app.control_plane import ControlPlane
from backend.app.domain import TradingMode
from backend.app.governor import GovernorPolicy, PortfolioGovernor
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderManager, OrderManagerError
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime import RuntimeRecoveryOrchestrator, RuntimeState, RuntimeStatus
from backend.tests.fixtures.modern_order import make_signal_plan_order
import backend.app.runtime.recovery_orchestrator as recovery_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


class RecoveryAdapter:
    def __init__(
        self,
        *,
        snapshot: BrokerAccountSnapshot | None = None,
        open_orders: tuple[BrokerOpenOrderSnapshot, ...] = (),
        results_by_client_order_id: dict[str, BrokerOrderResult] | None = None,
        missing_client_order_ids: set[str] | None = None,
    ) -> None:
        self.snapshot = snapshot or _snapshot()
        self.open_orders = open_orders
        self.results_by_client_order_id = results_by_client_order_id or {}
        self.missing_client_order_ids = missing_client_order_ids or set()
        self.calls: list[str] = []

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        self.calls.append("get_account_snapshot")
        assert account_id == ACCOUNT_ID
        return self.snapshot

    def get_positions(self, account_id: UUID) -> tuple:
        self.calls.append("get_positions")
        assert account_id == ACCOUNT_ID
        return ()

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        self.calls.append("list_open_orders")
        assert account_id == ACCOUNT_ID
        return self.open_orders

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        self.calls.append("get_order")
        if order.client_order_id in self.missing_client_order_ids:
            raise BrokerAdapterError("missing broker order")
        return self.results_by_client_order_id[order.client_order_id]


def _snapshot(*, stale: bool = False) -> BrokerAccountSnapshot:
    timestamp = datetime.now(timezone.utc) - timedelta(minutes=5) if stale else datetime.now(timezone.utc)
    return BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        equity=100_000,
        cash=100_000,
        buying_power=100_000,
        provider="fake",
        mode=TradingMode.BROKER_PAPER,
        timestamp=timestamp,
    )


def _runtime(db_path, *, adapter: RecoveryAdapter) -> tuple[SQLiteRuntimeStore, RuntimeRecoveryOrchestrator]:
    store = SQLiteRuntimeStore(db_path)
    control_plane = ControlPlane(state_store=store)
    governor = PortfolioGovernor(GovernorPolicy(), state_store=store)
    ledger = SQLiteOrderLedger(db_path)
    broker_sync = BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="fake")
    orchestrator = RuntimeRecoveryOrchestrator(
        persistence_store=store,
        broker_adapter=adapter,
        broker_sync=broker_sync,
        governor_service=governor,
        control_plane=control_plane,
        runtime_state_store=store,
    )
    return store, orchestrator


def _order(db_path) -> InternalOrder:
    store = SQLiteRuntimeStore(db_path)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.RUNNING))
    store.save_broker_account_snapshot(_snapshot())
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    return make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)


def _open_snapshot(order: InternalOrder, *, broker_order_id: str = "broker-1") -> BrokerOpenOrderSnapshot:
    return BrokerOpenOrderSnapshot(
        account_id=order.account_id,
        broker_order_id=broker_order_id,
        client_order_id=order.client_order_id,
        symbol=order.symbol,
        side=order.side.value,
        qty=order.quantity,
        filled_qty=0,
        status=BrokerOrderStatus.ACCEPTED,
        order_type=order.order_type.value,
        timestamp=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
    )


def _result(order: InternalOrder, status: BrokerOrderStatus = BrokerOrderStatus.ACCEPTED) -> BrokerOrderResult:
    return BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=status,
        broker_order_id=f"broker-{order.client_order_id}",
        broker_status=status.value,
        remaining_quantity=order.quantity,
        received_at=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
    )


def test_restart_with_open_orders_reconciles_correctly(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    order = _order(db_path)
    adapter = RecoveryAdapter(open_orders=(_open_snapshot(order),), results_by_client_order_id={order.client_order_id: _result(order)})
    store, orchestrator = _runtime(db_path, adapter=adapter)

    result = orchestrator.run_startup_recovery()

    persisted = store.load_order(order.order_id)
    assert persisted.status == InternalOrderStatus.ACCEPTED
    assert store.lookup_broker_mapping_by_internal_order_id(order.order_id).broker_order_id == f"broker-{order.client_order_id}"
    assert result.recovered_accounts == 1
    assert adapter.calls[:3] == ["get_account_snapshot", "get_positions", "list_open_orders"]


def test_restart_with_missing_broker_order_marks_internal_order_terminal(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    order = _order(db_path)
    adapter = RecoveryAdapter(missing_client_order_ids={order.client_order_id})
    store, orchestrator = _runtime(db_path, adapter=adapter)

    result = orchestrator.run_startup_recovery()

    persisted = store.load_order(order.order_id)
    assert persisted.status == InternalOrderStatus.CANCELED
    assert persisted.reason == "recovery_missing_broker_order"
    assert any("missing_broker_order" in issue for issue in result.reconciliation_issues)


def test_restart_with_unknown_broker_order_is_safely_ingested(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    store.save_broker_account_snapshot(_snapshot())
    unknown = BrokerOpenOrderSnapshot(
        account_id=ACCOUNT_ID,
        broker_order_id="unknown-broker-1",
        client_order_id="external-client-order",
        symbol="SPY",
        side="buy",
        qty=1,
        status=BrokerOrderStatus.ACCEPTED,
        order_type="market",
    )
    adapter = RecoveryAdapter(open_orders=(unknown,))
    store, orchestrator = _runtime(db_path, adapter=adapter)

    result = orchestrator.run_startup_recovery()

    assert store.list_orders() == ()
    assert store.list_broker_open_order_snapshots(ACCOUNT_ID) == (unknown,)
    assert any("unknown_broker_order_ingested" in issue for issue in result.reconciliation_issues)


def test_restart_with_stale_broker_sync_blocks_trading(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    order = _order(db_path)
    stale_snapshot = _snapshot(stale=True)
    SQLiteRuntimeStore(db_path).save_broker_account_snapshot(stale_snapshot)
    adapter = RecoveryAdapter(
        snapshot=stale_snapshot,
        open_orders=(_open_snapshot(order),),
        results_by_client_order_id={order.client_order_id: _result(order)},
    )
    store, orchestrator = _runtime(db_path, adapter=adapter)

    result = orchestrator.run_startup_recovery()

    assert store.load_broker_sync_freshness(ACCOUNT_ID).is_stale is True
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).status == RuntimeStatus.BLOCKED_RECOVERY
    assert any("trading_blocked_reason=broker_sync_stale" in issue for issue in result.reconciliation_issues)


def test_restart_preserves_global_kill_active(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    order = _order(db_path)
    store = SQLiteRuntimeStore(db_path)
    control_plane = ControlPlane(state_store=store)
    control_plane.activate_global_kill()
    adapter = RecoveryAdapter(open_orders=(_open_snapshot(order),), results_by_client_order_id={order.client_order_id: _result(order)})
    store, orchestrator = _runtime(db_path, adapter=adapter)

    result = orchestrator.run_startup_recovery()

    assert ControlPlane(state_store=store).global_kill_active is True
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).status == RuntimeStatus.BLOCKED_RECOVERY
    assert result.blocked_deployments == 1


def test_restart_preserves_deployment_pause(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    order = _order(db_path)
    store = SQLiteRuntimeStore(db_path)
    control_plane = ControlPlane(state_store=store)
    control_plane.pause_deployment(DEPLOYMENT_ID)
    adapter = RecoveryAdapter(open_orders=(_open_snapshot(order),), results_by_client_order_id={order.client_order_id: _result(order)})
    store, orchestrator = _runtime(db_path, adapter=adapter)

    orchestrator.run_startup_recovery()

    assert ControlPlane(state_store=store).is_deployment_paused(DEPLOYMENT_ID) is True
    assert store.load_deployment_runtime_state(DEPLOYMENT_ID).status == RuntimeStatus.BLOCKED_RECOVERY


def test_recovery_mode_blocks_new_order_creation() -> None:
    control_plane = ControlPlane()
    control_plane.set_system_recovery_active(True)
    manager = OrderManager(control_plane=control_plane)

    with pytest.raises(OrderManagerError, match="system recovery"):
        make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)


def test_recovery_does_not_create_new_orders(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    store.save_broker_account_snapshot(_snapshot())
    adapter = RecoveryAdapter(open_orders=())
    store, orchestrator = _runtime(db_path, adapter=adapter)

    orchestrator.run_startup_recovery()

    assert store.list_orders() == ()
    assert "OrderManager" not in inspect.getsource(recovery_module)
    assert ".create_order(" not in inspect.getsource(recovery_module)


def test_recovery_does_not_call_feature_engine_or_signal_engine() -> None:
    source = inspect.getsource(recovery_module)

    assert "FeatureEngine" not in source
    assert "SignalEngine" not in source


def test_recovery_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    order = _order(db_path)
    adapter = RecoveryAdapter(open_orders=(_open_snapshot(order),), results_by_client_order_id={order.client_order_id: _result(order)})
    store, orchestrator = _runtime(db_path, adapter=adapter)

    first = orchestrator.run_startup_recovery()
    first_state = _store_snapshot(store)
    second = orchestrator.run_startup_recovery()
    second_state = _store_snapshot(store)

    assert first == second
    assert first_state == second_state


def _store_snapshot(store: SQLiteRuntimeStore) -> dict[str, object]:
    return {
        "orders": [order.model_dump(mode="json") for order in store.list_orders()],
        "runtime": [state.model_dump(mode="json") for state in store.list_deployment_runtime_states()],
        "mappings": [mapping.model_dump(mode="json") for mapping in store.list_broker_order_mappings()],
        "snapshots": [snapshot.model_dump(mode="json") for snapshot in store.list_broker_account_snapshots()],
        "freshness": [freshness.model_dump(mode="json") for freshness in store.list_broker_sync_freshness()],
        "control": store.load_control_plane_state("default").model_dump(mode="json"),
    }
