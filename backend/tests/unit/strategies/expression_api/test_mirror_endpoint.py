"""Tests for POST /api/v1/strategies/expression/mirror."""
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


def test_crosses_above_becomes_crosses_below(client: TestClient) -> None:
    resp = client.post("/api/v1/strategies/expression/mirror", json={"src": "5m.ema(9) crosses_above 5m.ema(21)"})
    assert resp.status_code == 200
    body = resp.json()
    assert "crosses_below" in body["mirrored_text"]
    assert "crosses_above" not in body["mirrored_text"].split("//", 1)[-1]


def test_header_comment_prepended_or_replaced(client: TestClient) -> None:
    # Source without header comment: should get the standard header prepended.
    src = "5m.ema(9) crosses_above 5m.ema(21)"
    resp = client.post("/api/v1/strategies/expression/mirror", json={"src": src})
    assert resp.status_code == 200
    mirrored = resp.json()["mirrored_text"]
    assert "Auto-mirrored" in mirrored


def test_existing_header_comment_replaced(client: TestClient) -> None:
    # Source with an existing // header: the mirror should replace it.
    src = "// My original comment\n5m.ema(9) crosses_above 5m.ema(21)"
    resp = client.post("/api/v1/strategies/expression/mirror", json={"src": src})
    assert resp.status_code == 200
    mirrored = resp.json()["mirrored_text"]
    assert "Auto-mirrored" in mirrored
    # The original comment text should be replaced, not doubled.
    assert mirrored.count("My original comment") == 0


def test_bad_input_returns_422(client: TestClient) -> None:
    # '@' is an unexpected character that triggers ParseError in the lexer.
    resp = client.post("/api/v1/strategies/expression/mirror", json={"src": "@invalid"})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
