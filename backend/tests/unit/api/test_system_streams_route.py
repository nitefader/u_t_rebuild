from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone
from uuid import UUID

from backend.app.api.routes import system_streams
from backend.app.market_data.models import LiveStockMarketDataStreamState, LiveStockMarketDataStreamStatus


def test_hub_status_uses_asset_class_live_stock_identity() -> None:
    key = SimpleNamespace(provider="alpaca", asset_class="stock", data_feed="iex")
    status = LiveStockMarketDataStreamStatus(
        stream_id="live-stock-data",
        enabled_by_settings=True,
        open=True,
        connected=True,
        authenticated=True,
        status=LiveStockMarketDataStreamState.CONNECTED,
        subscribed_symbols=("SPY",),
        consumer_ids=("chart-lab:test",),
        last_message_at=datetime(2026, 4, 26, 20, 0, tzinfo=timezone.utc),
    )
    hub = SimpleNamespace(
        is_running=True,
        consumer_ids=("chart-lab:test",),
        subscribed_symbols=("SPY",),
        status=lambda: status,
    )

    projected = system_streams._hub_status(key, hub)

    assert projected.provider == "alpaca"
    assert projected.asset_class == "stock"
    assert projected.data_feed == "iex"
    assert projected.is_running is True
    assert projected.stream_status == "connected"
    assert projected.last_message_at == status.last_message_at
    assert projected.subscribed_symbols == ("SPY",)


def test_running_trade_stream_is_not_stale_only_because_no_trade_events_arrived() -> None:
    account_id = UUID("11111111-2222-3333-4444-555555555555")
    dispatcher = SimpleNamespace(
        account_id=account_id,
        is_running=True,
        last_event_at=datetime(2026, 4, 26, 20, 0, tzinfo=timezone.utc),
        last_error=None,
        subscriber_ids=("operations:1",),
        subscriber_summary_lines=lambda: ("Operations Center",),
    )

    projected = system_streams._trade_stream_status(dispatcher, {account_id: "Paper - tst"})

    assert projected.is_running is True
    assert projected.is_stale is False
    assert projected.stale_reason is None
    assert projected.idle_note is not None


def test_system_streams_route_is_registered() -> None:
    assert any(route.path == "/api/v1/system/streams" for route in system_streams.router.routes)
