from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.api.routes import chart_lab
from backend.app.api.routes.chart_lab import (
    ChartLabConfig,
    ChartLabHealthResponse,
    build_market_data_adapter,
    chart_lab_health,
    resolve_symbol,
    serialize_bar,
)
from backend.app.features import NormalizedBar
from backend.app.market_data import AlpacaMarketDataAdapter


def _bar(**overrides) -> NormalizedBar:
    defaults = dict(
        symbol="SPY",
        timeframe="1m",
        timestamp=datetime(2026, 4, 25, 14, 30, tzinfo=timezone.utc),
        open=100.5,
        high=101.0,
        low=99.5,
        close=100.75,
        volume=1234,
    )
    defaults.update(overrides)
    return NormalizedBar(**defaults)


def test_health_with_no_creds_reports_streaming_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_USE_TEST_STREAM", raising=False)
    monkeypatch.delenv("ALPACA_DATA_FEED", raising=False)
    response = chart_lab_health()
    assert isinstance(response, ChartLabHealthResponse)
    assert response.streaming_enabled is False
    assert response.test_stream is False
    assert response.data_feed == "iex"
    assert response.websocket_path == "/api/v1/chart-lab/stream"


def test_health_with_creds_reports_streaming_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.delenv("ALPACA_USE_TEST_STREAM", raising=False)
    response = chart_lab_health()
    assert response.streaming_enabled is True
    assert response.test_stream is False


def test_health_with_test_stream_uses_fakepaca_default_symbol(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.setenv("ALPACA_USE_TEST_STREAM", "1")
    response = chart_lab_health()
    assert response.test_stream is True
    assert response.default_symbol == AlpacaMarketDataAdapter.TEST_SYMBOL
    assert response.data_feed == "test"


def test_health_reports_configured_data_feed(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.delenv("ALPACA_USE_TEST_STREAM", raising=False)
    monkeypatch.setenv("ALPACA_DATA_FEED", "sip")
    response = chart_lab_health()
    assert response.data_feed == "sip"


def test_resolve_data_feed_maps_known_aliases() -> None:
    from backend.app.api.routes.chart_lab import resolve_data_feed
    try:
        from alpaca.data.enums import DataFeed
    except ImportError:
        import pytest
        pytest.skip("alpaca-py not installed")
    assert resolve_data_feed("sip") is DataFeed.SIP
    assert resolve_data_feed("IEX") is DataFeed.IEX
    assert resolve_data_feed("delayed_sip") is DataFeed.DELAYED_SIP
    assert resolve_data_feed(None) is None
    assert resolve_data_feed("") is None


def test_resolve_data_feed_rejects_unknown_value() -> None:
    import pytest
    from backend.app.api.routes.chart_lab import resolve_data_feed
    try:
        from alpaca.data.enums import DataFeed  # noqa: F401
    except ImportError:
        pytest.skip("alpaca-py not installed")
    with pytest.raises(ValueError):
        resolve_data_feed("nonexistent_feed")


def test_resolve_symbol_forces_fakepaca_in_test_stream_mode() -> None:
    config = ChartLabConfig(streaming_enabled=True, test_stream=True, default_symbol="FAKEPACA", data_feed="test")
    assert resolve_symbol("SPY", config) == "FAKEPACA"
    assert resolve_symbol(None, config) == "FAKEPACA"


def test_resolve_symbol_uses_request_then_default_in_live_mode() -> None:
    config = ChartLabConfig(streaming_enabled=True, test_stream=False, default_symbol="QQQ", data_feed="iex")
    assert resolve_symbol("spy", config) == "SPY"
    assert resolve_symbol("", config) == "QQQ"
    assert resolve_symbol(None, config) == "QQQ"


def test_build_market_data_adapter_uses_test_url_when_test_stream_enabled() -> None:
    config = ChartLabConfig(streaming_enabled=True, test_stream=True, default_symbol="FAKEPACA", data_feed="test")
    adapter = build_market_data_adapter(config)
    assert adapter._url_override == AlpacaMarketDataAdapter.TEST_STREAM_URL


def test_build_market_data_adapter_uses_default_url_when_test_stream_disabled() -> None:
    config = ChartLabConfig(streaming_enabled=True, test_stream=False, default_symbol="SPY", data_feed="iex")
    adapter = build_market_data_adapter(config)
    assert adapter._url_override is None


def test_serialize_bar_emits_iso_timestamp_and_numeric_fields() -> None:
    payload = serialize_bar(_bar())
    assert payload == {
        "symbol": "SPY",
        "timeframe": "1m",
        "timestamp": "2026-04-25T14:30:00+00:00",
        "open": 100.5,
        "high": 101.0,
        "low": 99.5,
        "close": 100.75,
        "volume": 1234,
    }


def test_router_registers_health_endpoint() -> None:
    """Health endpoint is registered on the FastAPI router."""
    paths_and_methods = []
    if hasattr(chart_lab.router, "routes"):
        for route in chart_lab.router.routes:
            path = getattr(route, "path", None) or getattr(route, "path_format", None)
            method = getattr(route, "method", None) or next(iter(getattr(route, "methods", []) or []), None)
            if path is not None:
                paths_and_methods.append((path, method))
    assert any(path.endswith("/health") for path, _ in paths_and_methods)
