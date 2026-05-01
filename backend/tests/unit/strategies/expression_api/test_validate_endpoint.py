"""Tests for POST /api/v1/strategies/expression/validate."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.strategy_expression import router


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_valid_ema_crossover(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/expression/validate", json={"src": "5m.ema(9) crosses_above 5m.ema(21)"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []
    keys = {f["key"] for f in body["feature_requirements"]}
    assert "5m.ema(9)" in keys
    assert "5m.ema(21)" in keys


def test_parse_error_has_line_col(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/expression/validate", json={"src": "5m.ema("})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert len(body["errors"]) >= 1
    err = body["errors"][0]
    assert err["line"] is not None
    assert err["col"] is not None


def test_validation_error_unknown_feature(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/expression/validate", json={"src": "5m.bogus(9) > 5m.close"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert any("bogus" in e["message"] for e in body["errors"])


def test_with_variables(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/strategies/expression/validate",
        json={"src": "my_var > 5m.close", "variables": ["my_var"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert "my_var" in body["variables_used"]


def test_empty_source_is_valid(client: TestClient) -> None:
    # Empty source is "no condition" — treated as valid, not a parse error.
    resp = client.post("/api/v1/strategies/expression/validate", json={"src": ""})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []
