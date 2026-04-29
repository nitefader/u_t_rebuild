from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.api.server import app
from backend.app.data_center.ingest_service import (
    AlpacaBarsSource,
    HistoricalBarIngestRequest,
    HistoricalBarIngestService,
    YahooBarsSource,
)
from backend.app.features import NormalizedBar

_client = TestClient(app)


def test_alpaca_bars_source_uses_injected_stock_historical_client() -> None:
    timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)

    class FakeStockClient:
        def __init__(self) -> None:
            self.request = None

        def get_stock_bars(self, request: object) -> object:
            self.request = request
            return SimpleNamespace(
                data={
                    "SPY": [
                        SimpleNamespace(
                            timestamp=timestamp,
                            open=500.0,
                            high=501.0,
                            low=499.0,
                            close=500.5,
                            volume=1_000_000.0,
                        )
                    ]
                }
            )

    client = FakeStockClient()
    source = AlpacaBarsSource(client=client)

    bars, params = source.fetch(
        symbol="SPY",
        timeframe="1d",
        start=timestamp,
        end=timestamp,
        adjustment_policy="split_dividend_adjusted",
    )

    assert client.request is not None
    assert len(bars) == 1
    assert bars[0].open == pytest.approx(500.0)
    assert params["endpoint"] == "v2/stocks/SPY/bars"


def test_yahoo_bars_source_flattens_multi_index_columns() -> None:
    """Regression guard for the bug fixed on 2026-04-28.

    yfinance >= 0.2 returns a `pd.MultiIndex` on `.columns` even for a
    single-ticker download (e.g. `('Open', 'SPY')`), which makes
    `row["Open"]` resolve to a Series, not a scalar, and breaks
    `float(row["Open"])` with `TypeError: float() argument must be ... not
    'Series'`. The source flattens the columns to a single level so this
    works regardless of yfinance version.
    """

    timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    multi_index_df = pd.DataFrame(
        {
            ("Open", "SPY"): [500.0],
            ("High", "SPY"): [501.0],
            ("Low", "SPY"): [499.0],
            ("Close", "SPY"): [500.5],
            ("Volume", "SPY"): [1_000_000.0],
        },
        index=pd.DatetimeIndex([timestamp]),
    )
    assert isinstance(multi_index_df.columns, pd.MultiIndex)

    def fake_download(**kwargs: object) -> pd.DataFrame:  # noqa: ARG001
        return multi_index_df

    source = YahooBarsSource(downloader=fake_download)
    bars, _ = source.fetch(
        symbol="SPY",
        timeframe="1d",
        start=timestamp,
        end=timestamp,
        adjustment_policy="split_dividend_adjusted",
    )
    assert len(bars) == 1
    bar = bars[0]
    assert bar.symbol == "SPY"
    assert bar.open == pytest.approx(500.0)
    assert bar.high == pytest.approx(501.0)
    assert bar.low == pytest.approx(499.0)
    assert bar.close == pytest.approx(500.5)
    assert bar.volume == pytest.approx(1_000_000.0)


def test_yahoo_bars_source_handles_flat_single_level_columns() -> None:
    """Older yfinance / single-ticker single-level DataFrames must still work."""

    timestamp = datetime(2026, 4, 1, tzinfo=timezone.utc)
    flat_df = pd.DataFrame(
        {
            "Open": [500.0],
            "High": [501.0],
            "Low": [499.0],
            "Close": [500.5],
            "Volume": [1_000_000.0],
        },
        index=pd.DatetimeIndex([timestamp]),
    )
    assert not isinstance(flat_df.columns, pd.MultiIndex)

    source = YahooBarsSource(downloader=lambda **_: flat_df)
    bars, _ = source.fetch(
        symbol="SPY",
        timeframe="1d",
        start=timestamp,
        end=timestamp,
        adjustment_policy="split_dividend_adjusted",
    )
    assert len(bars) == 1
    assert bars[0].open == pytest.approx(500.0)


def test_historical_ingest_exact_cache_hit_makes_zero_provider_calls() -> None:
    start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    store = _MemoryHistoricalStore()
    source = _RecordingBarsSource()
    bars = (
        _bar("SPY", start),
        _bar("SPY", start + timedelta(days=1)),
        _bar("SPY", end),
    )
    store.save_historical_dataset(
        _dataset_payload(
            provider="yahoo",
            symbol="SPY",
            timeframe="1d",
            start=start,
            end=end,
            bars=bars,
        ),
        dataset_id=str(uuid4()),
    )
    service = HistoricalBarIngestService(store=store, sources={"yahoo": source})

    result = service.ensure_bars(
        HistoricalBarIngestRequest(
            provider="yahoo",
            symbol="SPY",
            timeframe="1d",
            start=start,
            end=end,
        )
    )

    assert result.fetched_from_provider is False
    assert source.calls == []
    assert [bar.timestamp for bar in result.bars] == [bar.timestamp for bar in bars]


def test_historical_ingest_fetches_only_missing_cache_gap_and_dedupes() -> None:
    warmup_start = datetime(2026, 3, 18, tzinfo=timezone.utc)
    cached_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
    end = cached_start + timedelta(days=2)
    store = _MemoryHistoricalStore()
    cached_bars = (
        _bar("SPY", cached_start),
        _bar("SPY", cached_start + timedelta(days=1)),
        _bar("SPY", end),
    )
    store.save_historical_dataset(
        _dataset_payload(
            provider="yahoo",
            symbol="SPY",
            timeframe="1d",
            start=cached_start,
            end=end,
            bars=cached_bars,
        ),
        dataset_id=str(uuid4()),
    )
    warmup_bars = (
        _bar("SPY", warmup_start),
        _bar("SPY", cached_start),  # inclusive provider boundary duplicate
    )
    source = _RecordingBarsSource(bars=warmup_bars)
    service = HistoricalBarIngestService(store=store, sources={"yahoo": source})

    result = service.ensure_bars(
        HistoricalBarIngestRequest(
            provider="yahoo",
            symbol="SPY",
            timeframe="1d",
            start=warmup_start,
            end=end,
        )
    )

    assert result.fetched_from_provider is True
    assert source.calls == [(warmup_start, cached_start)]
    assert [bar.timestamp for bar in result.bars] == [
        warmup_start,
        cached_start,
        cached_start + timedelta(days=1),
        end,
    ]
    persisted = store.find_historical_dataset(
        provider="yahoo",
        symbol="SPY",
        timeframe="1d",
        adjustment_policy="split_dividend_adjusted",
    )
    assert persisted is not None
    assert persisted["bar_count"] == 4


def test_historical_datasets_list_returns_items() -> None:
    r = _client.get("/api/v1/data-center/historical-datasets")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) >= 1
    row = body["items"][0]
    assert "dataset_id" in row
    assert "symbol" in row


def test_historical_dataset_detail_unknown_404() -> None:
    r = _client.get("/api/v1/data-center/historical-datasets/does-not-exist")
    assert r.status_code == 404


def test_historical_dataset_bars_page() -> None:
    r0 = _client.get("/api/v1/data-center/historical-datasets")
    dataset_id = r0.json()["items"][0]["dataset_id"]
    r = _client.get(f"/api/v1/data-center/historical-datasets/{dataset_id}/bars", params={"offset": 0, "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["dataset_id"] == dataset_id
    assert body["total"] >= 1
    assert len(body["bars"]) <= 10
    bar = body["bars"][0]
    assert "timestamp" in bar
    assert "open" in bar
    assert "provider" in bar
    assert "quality_status" in bar


class _MemoryHistoricalStore:
    def __init__(self) -> None:
        self.payloads: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    def find_historical_dataset(
        self,
        *,
        provider: str,
        symbol: str,
        timeframe: str,
        adjustment_policy: str,
    ) -> dict[str, Any] | None:
        return self.payloads.get((provider, symbol.upper(), timeframe, adjustment_policy))

    def save_historical_dataset(self, payload: dict[str, Any], *, dataset_id: str) -> None:
        stored = dict(payload)
        stored["dataset_id"] = dataset_id
        self.payloads[
            (
                str(stored["provider"]),
                str(stored["symbol"]).upper(),
                str(stored["timeframe"]),
                str(stored["adjustment_policy"]),
            )
        ] = stored

    def list_historical_datasets(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.payloads.values())


class _RecordingBarsSource:
    name = "yahoo"

    def __init__(self, bars: tuple[NormalizedBar, ...] = ()) -> None:
        self.bars = bars
        self.calls: list[tuple[datetime, datetime]] = []

    def fetch(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment_policy: str,
    ) -> tuple[tuple[NormalizedBar, ...], dict[str, Any]]:
        self.calls.append((start, end))
        return self.bars, {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()}


def _bar(symbol: str, timestamp: datetime) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe="1d",
        timestamp=timestamp,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000_000.0,
    )


def _dataset_payload(
    *,
    provider: str,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    bars: tuple[NormalizedBar, ...],
) -> dict[str, Any]:
    return {
        "dataset_id": str(uuid4()),
        "provider": provider,
        "symbol": symbol,
        "timeframe": timeframe,
        "adjustment_policy": "split_dividend_adjusted",
        "timezone": "UTC",
        "ingested_at": start.isoformat(),
        "source_request_parameters": {},
        "data_quality_warnings": [],
        "coverage_start": start.isoformat(),
        "coverage_end": end.isoformat(),
        "bar_count": len(bars),
        "aggregate_quality_status": "ok",
        "bars": [
            {
                "timestamp": bar.timestamp.isoformat(),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ],
    }
