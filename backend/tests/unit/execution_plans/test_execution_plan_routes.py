"""FastAPI TestClient tests for /api/v1/execution-plans routes."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.deployments.models import Deployment, DeploymentLifecycleStatus
from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain.execution_style import ExecutionMode, OrderType, TimeInForce
from backend.app.execution_plans.persistence import ExecutionPlanRepository
from backend.app.execution_plans.registry import ExecutionPlanRegistry
from backend.app.execution_plans.service import ExecutionPlanService
from backend.app.api.routes.execution_plans import router, get_execution_plan_service


def _make_service(db_path: Path) -> ExecutionPlanService:
    return ExecutionPlanService(
        repository=ExecutionPlanRepository(db_path),
        registry=ExecutionPlanRegistry(db_path),
        deployment_repository=DeploymentRepository(db_path),
    )


def _make_app(service: ExecutionPlanService) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_execution_plan_service] = lambda: service
    return app


def _client(tmp_path: Path) -> tuple[TestClient, ExecutionPlanService]:
    db = tmp_path / "test.db"
    service = _make_service(db)
    app = _make_app(service)
    return TestClient(app, raise_server_exceptions=True), service


_DRAFT = {
    "name": "Test Profile",
    "entry_order_type": "market",
    "exit_order_type": "market",
    "time_in_force": "day",
    "execution_mode": "post_fill_bracket",
    "trailing_stop_enabled": False,
    "scale_out_enabled": False,
}


def test_list_empty(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.get("/api/v1/execution-plans")
    assert r.status_code == 200
    assert r.json() == {"libraries": []}


def test_create_and_list(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.post("/api/v1/execution-plans", json={"name": "Test Profile", "draft": _DRAFT})
    assert r.status_code == 201
    body = r.json()
    assert body["payload"]["version"] == 1
    assert body["payload"]["name"] == "Test Profile"

    r2 = client.get("/api/v1/execution-plans")
    assert len(r2.json()["libraries"]) == 1
    assert r2.json()["libraries"][0]["head_version_number"] == 1


def test_get_library(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "Test Profile", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    r = client.get(f"/api/v1/execution-plans/{ep_id}")
    assert r.status_code == 200
    assert r.json()["execution_plan_id"] == ep_id
    assert len(r.json()["history"]) == 1


def test_get_library_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.get(f"/api/v1/execution-plans/{uuid4()}")
    assert r.status_code == 404


def test_get_version_by_number(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "Test Profile", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    r = client.get(f"/api/v1/execution-plans/{ep_id}/versions/1")
    assert r.status_code == 200
    assert r.json()["payload"]["version"] == 1


def test_get_version_by_number_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "Test Profile", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    r = client.get(f"/api/v1/execution-plans/{ep_id}/versions/99")
    assert r.status_code == 404


def test_edit_bumps_version(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "Original", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    updated_draft = dict(_DRAFT, name="Updated Name")
    r = client.put(f"/api/v1/execution-plans/{ep_id}", json={"draft": updated_draft})
    assert r.status_code == 200
    assert r.json()["payload"]["version"] == 2
    assert r.json()["payload"]["name"] == "Updated Name"


def test_edit_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.put(f"/api/v1/execution-plans/{uuid4()}", json={"draft": _DRAFT})
    assert r.status_code == 404


def test_duplicate(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "Original", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    r = client.post(f"/api/v1/execution-plans/{ep_id}/duplicate", json={"new_name": "Copy"})
    assert r.status_code == 201
    assert r.json()["payload"]["name"] == "Copy"
    assert r.json()["payload"]["version"] == 1
    assert r.json()["payload"]["execution_style_id"] != ep_id


def test_duplicate_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.post(f"/api/v1/execution-plans/{uuid4()}/duplicate", json={"new_name": "X"})
    assert r.status_code == 404


def test_retire_success(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "ToRetire", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    r = client.post(f"/api/v1/execution-plans/{ep_id}/retire")
    assert r.status_code == 204


def test_retire_409_when_bound(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    service = _make_service(db)
    app = _make_app(service)
    client = TestClient(app, raise_server_exceptions=True)

    create_r = client.post("/api/v1/execution-plans", json={"name": "Bound", "draft": _DRAFT})
    ep_version_id = create_r.json()["payload"]["id"]
    ep_id = create_r.json()["payload"]["execution_style_id"]

    dep = Deployment(
        deployment_id=uuid4(),
        name="Bound Deployment",
        strategy_version_v4_id=uuid4(),
        execution_plan_version_id=ep_version_id,
    )
    DeploymentRepository(db).save_deployment(dep)

    r = client.post(f"/api/v1/execution-plans/{ep_id}/retire")
    assert r.status_code == 409
    body = r.json()
    assert "bound_deployment_ids" in body["detail"]
    assert str(dep.deployment_id) in body["detail"]["bound_deployment_ids"]


def test_retire_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.post(f"/api/v1/execution-plans/{uuid4()}/retire")
    assert r.status_code == 404


def test_set_default(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    create_r = client.post("/api/v1/execution-plans", json={"name": "Default", "draft": _DRAFT})
    ep_id = create_r.json()["payload"]["execution_style_id"]

    r = client.post(f"/api/v1/execution-plans/{ep_id}/set-default")
    assert r.status_code == 204

    list_r = client.get("/api/v1/execution-plans")
    libraries = list_r.json()["libraries"]
    assert libraries[0]["is_default"] is True


def test_set_default_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.post(f"/api/v1/execution-plans/{uuid4()}/set-default")
    assert r.status_code == 404


def test_used_by(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    db = tmp_path / "test.db"
    create_r = client.post("/api/v1/execution-plans", json={"name": "UsedBy Test", "draft": _DRAFT})
    ep_version_id = create_r.json()["payload"]["id"]
    ep_id = create_r.json()["payload"]["execution_style_id"]

    dep = Deployment(
        deployment_id=uuid4(),
        name="User",
        strategy_version_v4_id=uuid4(),
        execution_plan_version_id=ep_version_id,
    )
    DeploymentRepository(db).save_deployment(dep)

    r = client.get(f"/api/v1/execution-plans/{ep_id}/used-by")
    assert r.status_code == 200
    assert str(dep.deployment_id) in r.json()["deployment_ids"]


def test_used_by_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.get(f"/api/v1/execution-plans/{uuid4()}/used-by")
    assert r.status_code == 404


def test_create_422_missing_name(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    r = client.post("/api/v1/execution-plans", json={"draft": _DRAFT})
    assert r.status_code == 422
