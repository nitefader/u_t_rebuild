from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from backend.app.features import NormalizedBar
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataSubscription
import backend.app.market_data.alpaca as alpaca_market_data_module
import tools.stream_market_data_check as stream_check


def test_adapter_maps_alpaca_bar_to_normalized_bar() -> None:
    adapter = AlpacaMarketDataAdapter(load_env=False)

    bar = adapter.normalize_bar(
        {
            "S": "spy",
            "t": "2026-01-02T14:30:00Z",
            "o": "100.5",
            "h": "101.0",
            "l": "99.75",
            "c": "100.8",
            "v": "12345",
        },
        timeframe="1m",
    )

    assert bar == NormalizedBar(
        symbol="SPY",
        timeframe="1m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=100.5,
        high=101.0,
        low=99.75,
        close=100.8,
        volume=12345,
    )


def test_adapter_does_not_compute_features() -> None:
    source = inspect.getsource(alpaca_market_data_module)

    assert "FeatureEngine" not in source
    assert "BatchFeatureEngine" not in source
    assert "IncrementalFeatureEngine" not in source
    assert ".compute(" not in source
    assert ".update(" not in source


def test_adapter_does_not_import_order_manager() -> None:
    source = inspect.getsource(alpaca_market_data_module)

    assert "OrderManager" not in source
    assert "backend.app.orders" not in source


def test_adapter_does_not_import_broker_adapter() -> None:
    source = inspect.getsource(alpaca_market_data_module)

    assert "BrokerAdapter" not in source
    assert "backend.app.brokers" not in source


def test_invalid_symbol_handled_cleanly() -> None:
    with pytest.raises(ValueError, match="invalid market data symbol"):
        MarketDataSubscription(symbol="SPY;DROP", timeframe="1m")


def test_injected_bar_source_collects_normalized_bars_without_network() -> None:
    adapter = AlpacaMarketDataAdapter(
        bar_source=[
            {
                "symbol": "SPY",
                "timestamp": "2026-01-02T14:30:00Z",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 1000,
            }
        ],
        load_env=False,
    )

    bars = adapter.collect_bars_sync(subscription=MarketDataSubscription(symbol="spy", timeframe="1m", limit=1))

    assert len(bars) == 1
    assert bars[0].symbol == "SPY"
    assert bars[0].timeframe == "1m"


class FakeStreamToolAdapter:
    submit_count = 0

    def collect_bars_sync(self, *, subscription: MarketDataSubscription, timeout_seconds: float):
        _ = timeout_seconds
        return (
            NormalizedBar(
                symbol=subscription.symbol,
                timeframe=subscription.timeframe,
                timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
                open=100,
                high=101,
                low=99,
                close=100.5,
                volume=1000,
            ),
        )


def test_stream_tool_submits_no_orders(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    monkeypatch.setattr(stream_check, "load_dotenv", lambda: False)
    monkeypatch.setattr(stream_check, "AlpacaMarketDataAdapter", FakeStreamToolAdapter)
    FakeStreamToolAdapter.submit_count = 0

    code = stream_check.main(["--symbol", "SPY", "--limit", "1"])

    output = capsys.readouterr().out
    assert code == 0
    assert '"orders_submitted": 0' in output
    assert FakeStreamToolAdapter.submit_count == 0
    source = inspect.getsource(stream_check)
    assert "OrderManager" not in source
    assert "AlpacaBrokerAdapter" not in source
    assert ".submit_order(" not in source
