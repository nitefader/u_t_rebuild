"""FastAPI TestClient end-to-end tests for the strategies/v4 routes."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.strategies_v4.persistence import StrategyV4Repository
from backend.app.strategies_v4.service import StrategyV4Service


# ---------------------------------------------------------------------------
# App fixture: minimal FastAPI app with only the strategies_v4 router
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Spin up an isolated TestClient wired to a temp DB."""
    from fastapi import FastAPI
    from backend.app.api.routes.strategies_v4 import router

    # Patch the runtime service factory to use a tmp DB
    import backend.app.api.routes.strategies_v4 as route_module

    repo = StrategyV4Repository(tmp_path / "test.db")
    svc = StrategyV4Service(repo)

    monkeypatch.setattr(
        route_module,
        "create_strategy_v4_service_from_environment",
        lambda: svc,
    )

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Shared draft payload
# ---------------------------------------------------------------------------

def _draft_payload(name: str = "Route Test Strategy") -> dict:
    return {
        "draft": {
            "name": name,
            "entries": {
                "long": {"expression_text": "5m.ema(9) > 5m.ema(21)"}
            },
            "stops": [
                {"mode": "simple", "scope": "all", "simple_type": "%", "simple_value": 2.0}
            ],
            "legs": [
                {
                    "position": 1,
                    "kind": "target",
                    "size_pct": 1.0,
                    "target_type": "%",
                    "target_value": 3.0,
                    "on_fill_action": {"kind": "leave"},
                }
            ],
        }
    }


def _invalid_draft_payload() -> dict:
    return {
        "draft": {
            "name": "Bad",
            "entries": {"long": {"expression_text": "!!! not valid !!!"}},
            "stops": [{"mode": "simple", "scope": "all", "simple_type": "%", "simple_value": 2.0}],
        }
    }


# ---------------------------------------------------------------------------
# POST /draft — validate only
# ---------------------------------------------------------------------------

def test_validate_draft_valid(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/v4/draft", json=_draft_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["validation_status"]["valid"] is True
    assert body["validation_status"]["errors"] == []


def test_validate_draft_invalid(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/v4/draft", json=_invalid_draft_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["validation_status"]["valid"] is False
    assert len(body["validation_status"]["errors"]) > 0


# ---------------------------------------------------------------------------
# POST / — create
# ---------------------------------------------------------------------------

def test_create_strategy(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/v4/", json=_draft_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 1
    assert body["name"] == "Route Test Strategy"
    assert "id" in body
    assert "strategy_v4_id" in body
    assert "compiled_blob" not in json.dumps(body)


def test_create_strategy_invalid_returns_422(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/v4/", json=_invalid_draft_payload())
    assert resp.status_code == 422


def test_create_aggregates_feature_requirements(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/v4/", json=_draft_payload())
    body = resp.json()
    assert "5m.ema(9)" in body["feature_requirements"]
    assert "5m.ema(21)" in body["feature_requirements"]


# ---------------------------------------------------------------------------
# GET /{strategy_version_v4_id}
# ---------------------------------------------------------------------------

def test_get_version(client: TestClient) -> None:
    created = client.post("/api/v1/strategies/v4/", json=_draft_payload()).json()
    vid = created["id"]
    resp = client.get(f"/api/v1/strategies/v4/{vid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == vid


def test_get_version_404(client: TestClient) -> None:
    resp = client.get(f"/api/v1/strategies/v4/{uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /by-strategy/{strategy_v4_id}
# ---------------------------------------------------------------------------

def test_list_versions(client: TestClient) -> None:
    created = client.post("/api/v1/strategies/v4/", json=_draft_payload()).json()
    sid = created["strategy_v4_id"]
    resp = client.get(f"/api/v1/strategies/v4/by-strategy/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["version"] == 1


def test_list_versions_empty(client: TestClient) -> None:
    resp = client.get(f"/api/v1/strategies/v4/by-strategy/{uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# PUT /by-strategy/{strategy_v4_id} — edit
# ---------------------------------------------------------------------------

def test_edit_strategy(client: TestClient) -> None:
    created = client.post("/api/v1/strategies/v4/", json=_draft_payload()).json()
    sid = created["strategy_v4_id"]
    resp = client.put(
        f"/api/v1/strategies/v4/by-strategy/{sid}",
        json=_draft_payload("Updated Name"),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["version"] == 2
    assert body["name"] == "Updated Name"
    assert body["strategy_v4_id"] == sid


# ---------------------------------------------------------------------------
# POST /{strategy_version_v4_id}/duplicate
# ---------------------------------------------------------------------------

def test_duplicate_version(client: TestClient) -> None:
    created = client.post("/api/v1/strategies/v4/", json=_draft_payload()).json()
    vid = created["id"]
    resp = client.post(
        f"/api/v1/strategies/v4/{vid}/duplicate",
        json={"new_name": "Duplicated"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Duplicated"
    assert body["version"] == 1
    assert body["strategy_v4_id"] != created["strategy_v4_id"]


def test_duplicate_not_found(client: TestClient) -> None:
    resp = client.post(
        f"/api/v1/strategies/v4/{uuid4()}/duplicate",
        json={"new_name": "X"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /by-strategy/{strategy_v4_id}
# ---------------------------------------------------------------------------

def test_delete_strategy(client: TestClient) -> None:
    created = client.post("/api/v1/strategies/v4/", json=_draft_payload()).json()
    sid = created["strategy_v4_id"]
    resp = client.delete(f"/api/v1/strategies/v4/by-strategy/{sid}")
    assert resp.status_code == 204

    # List should be empty
    list_resp = client.get(f"/api/v1/strategies/v4/by-strategy/{sid}")
    assert list_resp.json() == []
