"""Tests for GET /api/v1/strategies/expression/features."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes.strategy_expression import router

_REQUIRED_CATEGORIES = {"trend", "momentum", "volatility", "volume", "bb", "time", "bar"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(scope="module")
def features(client: TestClient) -> list[dict]:
    resp = client.get("/api/v1/strategies/expression/features")
    assert resp.status_code == 200
    return resp.json()["features"]


def test_at_least_50_features(features: list[dict]) -> None:
    assert len(features) >= 50


def test_all_required_categories_present(features: list[dict]) -> None:
    found = {f["category"] for f in features}
    for cat in _REQUIRED_CATEGORIES:
        assert cat in found, f"Missing category: {cat}"


def test_timeframed_feature_key_style(features: list[dict]) -> None:
    # Timeframed features should have a short key like "ema", no dot prefix.
    tf_features = [f for f in features if f["timeframe_bound"]]
    assert len(tf_features) > 0
    for f in tf_features:
        # The key should NOT start with a namespace dot prefix; it equals the name.
        assert f["key"] == f["name"], f"Unexpected key shape for timeframed feature: {f['key']!r}"


def test_nontf_feature_key_style(features: list[dict]) -> None:
    # Non-timeframed features have keys like "session.is_open".
    nontf_features = [f for f in features if not f["timeframe_bound"] and f["namespace"]]
    assert len(nontf_features) > 0
    for f in nontf_features:
        assert "." in f["key"], f"Non-tf feature key should contain dot: {f['key']!r}"
        assert f["key"] == f"{f['namespace']}.{f['name']}"


def test_session_is_open_present(features: list[dict]) -> None:
    keys = {f["key"] for f in features}
    assert "session.is_open" in keys


def test_ema_present_with_expected_shape(features: list[dict]) -> None:
    ema = next((f for f in features if f["key"] == "ema"), None)
    assert ema is not None
    assert ema["timeframe_bound"] is True
    assert ema["arity"] == 1
    assert ema["category"] == "trend"
    assert ema["return_type"] == "float"


def test_session_is_open_shape(features: list[dict]) -> None:
    entry = next((f for f in features if f["key"] == "session.is_open"), None)
    assert entry is not None
    assert entry["timeframe_bound"] is False
    assert entry["namespace"] == "session"
    assert entry["return_type"] == "bool"
    assert entry["category"] == "time"
