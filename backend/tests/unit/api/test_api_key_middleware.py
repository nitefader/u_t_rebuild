from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

from backend.app.api.api_key_middleware import API_KEY_ENV
from backend.app.api.server import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    return TestClient(app)


def test_no_key_env_allows_request(client: TestClient) -> None:
    response = client.get("/api/v1/system/status")
    assert response.status_code in (200, 503)


def test_key_env_requires_header(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-test-key")
    fresh = TestClient(app)
    response = fresh.get("/api/v1/system/status")
    assert response.status_code == 401

    good = fresh.get("/api/v1/system/status", headers={"X-UTOS-API-Key": "secret-test-key"})
    assert good.status_code in (200, 503)


def test_key_accepts_bearer(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "bearer-token")
    fresh = TestClient(app)
    response = fresh.get(
        "/api/v1/system/status",
        headers={"Authorization": "Bearer bearer-token"},
    )
    assert response.status_code in (200, 503)


def test_openapi_docs_allowed_without_key(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "locked")
    fresh = TestClient(app)
    assert fresh.get("/docs").status_code == 200
    assert fresh.get("/openapi.json").status_code == 200
