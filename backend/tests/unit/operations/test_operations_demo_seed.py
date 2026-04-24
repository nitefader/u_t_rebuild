from __future__ import annotations

from backend.app.operations.demo_seed import DEMO_ACCOUNT_ID, DEMO_DEPLOYMENT_ID, DEMO_GOVERNOR_ID, seed_operations_demo_store
from backend.app.operations.runtime_service import (
    OPERATIONS_RUNTIME_DB_PATH_ENV,
    SEED_OPERATIONS_DEMO_ENV,
    create_operations_center_service_from_environment,
)
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.runtime import RuntimeStatus


def test_seed_operations_demo_store_creates_safe_local_visibility_state(tmp_path) -> None:
    db_path = tmp_path / "operations_demo.sqlite3"

    result = seed_operations_demo_store(db_path)
    store = SQLiteRuntimeStore(result.db_path)

    snapshot = store.load_broker_account_snapshot(DEMO_ACCOUNT_ID)
    sync = store.load_broker_sync_freshness(DEMO_ACCOUNT_ID)
    deployment_state = store.load_deployment_runtime_state(DEMO_DEPLOYMENT_ID)

    assert result.db_path == db_path
    assert snapshot.provider == "operations_demo"
    assert sync.is_stale is False
    assert deployment_state.status == RuntimeStatus.RECOVERED_READY
    assert store.list_orders() == ()
    assert store.list_broker_open_order_snapshots(DEMO_ACCOUNT_ID) == ()


def test_demo_seed_projects_to_operations_overview_and_detail_without_orders(tmp_path) -> None:
    db_path = tmp_path / "operations_demo.sqlite3"
    seed_operations_demo_store(db_path)
    service = create_operations_center_service_from_environment_for_test(db_path)

    overview = service.get_runtime_overview()
    account = service.get_account_operations(DEMO_ACCOUNT_ID)
    deployment = service.get_deployment_operations(DEMO_DEPLOYMENT_ID)

    assert [summary.account_id for summary in overview.broker_accounts] == [DEMO_ACCOUNT_ID]
    assert [summary.deployment_id for summary in overview.deployments] == [DEMO_DEPLOYMENT_ID]
    assert overview.deployments[0].status == RuntimeStatus.RECOVERED_READY
    assert overview.deployments[0].account_id == DEMO_ACCOUNT_ID
    assert overview.open_orders_count == 0
    assert overview.open_positions_count == 0
    assert account.open_broker_orders == ()
    assert account.positions == ()
    assert account.deployments[0].deployment_id == DEMO_DEPLOYMENT_ID
    assert deployment.runtime_status == RuntimeStatus.RECOVERED_READY
    assert deployment.broker_account_id == DEMO_ACCOUNT_ID
    assert deployment.open_orders == ()
    assert deployment.trades == ()
    assert deployment.fills == ()


def test_environment_service_seeds_demo_only_when_explicitly_enabled(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "operations_demo.sqlite3"
    monkeypatch.setenv(SEED_OPERATIONS_DEMO_ENV, "1")
    monkeypatch.setenv(OPERATIONS_RUNTIME_DB_PATH_ENV, str(db_path))

    service = create_operations_center_service_from_environment()
    overview = service.get_runtime_overview()

    assert overview.broker_accounts[0].account_id == DEMO_ACCOUNT_ID
    assert overview.deployments[0].deployment_id == DEMO_DEPLOYMENT_ID
    assert overview.deployments[0].account_id == DEMO_ACCOUNT_ID


def test_environment_service_does_not_seed_by_default(monkeypatch) -> None:
    monkeypatch.delenv(SEED_OPERATIONS_DEMO_ENV, raising=False)
    monkeypatch.delenv(OPERATIONS_RUNTIME_DB_PATH_ENV, raising=False)

    service = create_operations_center_service_from_environment()
    overview = service.get_runtime_overview()

    assert overview.broker_accounts == ()
    assert overview.deployments == ()


def create_operations_center_service_from_environment_for_test(db_path):
    from backend.app.control_plane import ControlPlane
    from backend.app.operations import OperationsCenterService
    from backend.app.operations.demo_seed import demo_deployment_context

    store = SQLiteRuntimeStore(db_path)
    return OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
        deployments=(demo_deployment_context(),),
        governor_id=DEMO_GOVERNOR_ID,
        deployment_account_ids={DEMO_DEPLOYMENT_ID: DEMO_ACCOUNT_ID},
    )
