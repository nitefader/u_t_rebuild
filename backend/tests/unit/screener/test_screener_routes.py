"""HTTP-level tests for the Screener routes — happy + edge cases.

These tests inject a fully wired in-memory ``ScreenerExecutionService``
via FastAPI's dependency-override mechanism so the routes never need to
touch the real Data Center or WatchlistService.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routes.screener import get_screener_service
from backend.app.api.server import app
from backend.app.features import NormalizedBar
from backend.app.screener.service import ScreenerExecutionService
from backend.app.screener.sources import (
    HistoricalBarsLookup,
    MetricSource,
    UniverseResolver,
    WatchlistLookup,
)
from backend.app.screener.store import ScreenerStore


def _make_bars(symbol: str, *, prices: list[float], volumes: list[float]) -> tuple[NormalizedBar, ...]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        NormalizedBar(
            symbol=symbol,
            timeframe="1d",
            timestamp=base + timedelta(days=i),
            open=close * 0.99,
            high=close * 1.01,
            low=close * 0.98,
            close=close,
            volume=vol,
        )
        for i, (close, vol) in enumerate(zip(prices, volumes))
    )


class _StaticBars(HistoricalBarsLookup):
    def __init__(self, table: dict[str, tuple[NormalizedBar, ...]]) -> None:
        self._table = table

    def get_bars(self, *, symbol, timeframe, start, end):  # noqa: D401, ARG002
        return self._table.get(symbol, ())


class _StaticWatchlist(WatchlistLookup):
    def get_watchlist_symbols(self, watchlist_id: UUID) -> tuple[str, ...]:  # noqa: D401, ARG002
        return ("SPY", "QQQ")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    bars = {
        "AAPL": _make_bars("AAPL", prices=[100 + i for i in range(40)], volumes=[1_000_000] * 39 + [3_000_000]),
        "TSLA": _make_bars("TSLA", prices=[200 - (i * 0.5) for i in range(40)], volumes=[2_000_000] * 40),
    }
    store = ScreenerStore(db_path=tmp_path / "screener.db")
    service = ScreenerExecutionService(
        store=store,
        universe_resolver=UniverseResolver(watchlists=_StaticWatchlist()),
        metric_source=MetricSource(bars=_StaticBars(bars)),
    )
    app.dependency_overrides[get_screener_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.pop(get_screener_service, None)


def test_list_screeners_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/v1/screeners")
    assert resp.status_code == 200
    assert resp.json() == {"screeners": []}


def test_list_presets_includes_liquid_large_caps(client: TestClient) -> None:
    resp = client.get("/api/v1/screeners/presets")
    assert resp.status_code == 200
    keys = [p["key"] for p in resp.json()["presets"]]
    assert "liquid_large_caps" in keys


def test_list_metrics_advertises_seven_core_metrics(client: TestClient) -> None:
    resp = client.get("/api/v1/screeners/metrics")
    assert resp.status_code == 200
    keys = {m["key"] for m in resp.json()["metrics"]}
    assert {"price", "avg_volume_20d", "relative_volume", "rsi_14", "atr_14_pct"} <= keys


def test_fields_templates_market_lists_and_ai_advisory_are_read_only(client: TestClient) -> None:
    fields = client.get("/api/v1/screeners/fields")
    assert fields.status_code == 200
    assert "broker.fractionable" in {field["key"] for field in fields.json()["fields"]}

    templates = client.get("/api/v1/screeners/templates")
    assert templates.status_code == 200
    assert "day_gainers" in {template["key"] for template in templates.json()["templates"]}

    market_lists = client.get("/api/v1/market-lists")
    assert market_lists.status_code == 200
    assert "most_active" in {item["key"] for item in market_lists.json()["market_lists"]}

    before = client.get("/api/v1/screeners").json()["screeners"]
    ai = client.post(
        "/api/v1/screeners/ai/interpret",
        json={"prompt": "Find fractionable stocks under $30 with RVOL over 3."},
    )
    assert ai.status_code == 200
    assert ai.json()["advisory_only"] is True
    after = client.get("/api/v1/screeners").json()["screeners"]
    assert after == before


def test_create_then_run_then_get_run_persists_results(client: TestClient) -> None:
    create_body = {
        "name": "Volume Surge",
        "description": None,
        "tags": [],
        "universe_source": {"kind": "explicit", "symbols": ["AAPL", "TSLA"]},
        "criteria": [
            {
                "metric": "relative_volume",
                "operator": "gte",
                "value": 1.5,
                "value_max": None,
                "label": None,
            }
        ],
        "timeframe": "1d",
        "sort_metric": "relative_volume",
        "sort_descending": True,
        "max_results": 200,
    }
    create = client.post("/api/v1/screeners", json=create_body)
    assert create.status_code == 201, create.text
    screener_id = create.json()["screener"]["id"]

    run = client.post(f"/api/v1/screeners/{screener_id}/run", json={})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["status"] == "completed"
    assert body["matched_count"] == 1
    assert body["results"][0]["symbol"] == "AAPL"

    # GET the run by id and confirm it round-trips with the same matched_count.
    fetched = client.get(f"/api/v1/screeners/runs/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["matched_count"] == 1

    rerun = client.post(f"/api/v1/screeners/runs/{body['id']}/rerun", json={})
    assert rerun.status_code == 200
    assert rerun.json()["parent_run_id"] == body["id"]

    diff = client.get(
        f"/api/v1/screeners/runs/{rerun.json()['id']}/diff",
        params={"against_run_id": body["id"]},
    )
    assert diff.status_code == 200
    assert diff.json()["stayed"] == ["AAPL"]


def test_run_unknown_screener_returns_404(client: TestClient) -> None:
    resp = client.post(f"/api/v1/screeners/{uuid4()}/run", json={})
    assert resp.status_code == 404


def test_create_rejects_blank_name(client: TestClient) -> None:
    body = {
        "name": "   ",
        "universe_source": {"kind": "explicit", "symbols": ["AAPL"]},
    }
    resp = client.post("/api/v1/screeners", json=body)
    assert resp.status_code in {422, 400}


def test_create_rejects_yahoo_source_preference(client: TestClient) -> None:
    body = {
        "name": "No Yahoo Screener",
        "universe_source": {"kind": "explicit", "symbols": ["AAPL"]},
        "criteria": [],
        "source_preference": "yahoo",
    }
    resp = client.post("/api/v1/screeners", json=body)
    assert resp.status_code == 422


def test_save_run_as_watchlist_returns_422_when_no_matched_symbols(
    client: TestClient,
) -> None:
    # Build a screener whose criteria match nothing; running it produces an
    # empty matched-set and the save action returns 422.
    create_body = {
        "name": "Impossible",
        "universe_source": {"kind": "explicit", "symbols": ["AAPL", "TSLA"]},
        "criteria": [
            {
                "metric": "price",
                "operator": "gte",
                "value": 1_000_000,
                "value_max": None,
                "label": None,
            }
        ],
    }
    create = client.post("/api/v1/screeners", json=create_body)
    screener_id = create.json()["screener"]["id"]
    run = client.post(f"/api/v1/screeners/{screener_id}/run", json={}).json()
    save = client.post(
        f"/api/v1/screeners/runs/{run['id']}/save-as-watchlist",
        json={"name": "From screener", "only_matched": True},
    )
    assert save.status_code == 422


def test_delete_with_run_history_blocks_and_archive_succeeds(client: TestClient) -> None:
    create = client.post(
        "/api/v1/screeners",
        json={
            "name": "Archive Me",
            "universe_source": {"kind": "explicit", "symbols": ["AAPL"]},
            "criteria": [],
        },
    )
    screener_id = create.json()["screener"]["id"]
    client.post(f"/api/v1/screeners/{screener_id}/run", json={})

    delete = client.post(f"/api/v1/screeners/{screener_id}/delete")
    assert delete.status_code == 409
    assert "archive" in delete.json()["detail"].lower()

    archive = client.post(f"/api/v1/screeners/{screener_id}/archive")
    assert archive.status_code == 200
    assert archive.json()["screener"]["status"] == "archived"


def test_extra_fields_in_create_request_are_rejected(client: TestClient) -> None:
    """Doctrine guard: ConfigDict(extra='forbid') prevents operator typos
    silently dropping criteria fields. Pydantic returns 422 with extra_forbidden."""
    body = {
        "name": "X",
        "universe_source": {"kind": "explicit", "symbols": ["AAPL"]},
        "criteria": [],
        "not_a_real_field": True,
    }
    resp = client.post("/api/v1/screeners", json=body)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any("not_a_real_field" in str(d) for d in detail), detail
