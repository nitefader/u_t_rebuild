from __future__ import annotations

from datetime import datetime, timezone

from backend.app.market_data import LiveStockMarketDataStreamState, LiveStockMarketDataStreamStatus


def test_live_stock_stream_status_can_be_open_with_zero_subscriptions() -> None:
    status = LiveStockMarketDataStreamStatus(
        stream_id="live-stock-data",
        enabled_by_settings=True,
        open=True,
        connected=True,
        authenticated=True,
        status=LiveStockMarketDataStreamState.CONNECTED,
        subscribed_symbols=(),
        consumer_ids=(),
        started_at=datetime.now(timezone.utc),
    )

    assert status.open is True
    assert status.subscribed_symbols == ()


def test_live_stock_stream_status_normalizes_symbols() -> None:
    status = LiveStockMarketDataStreamStatus(
        stream_id="live-stock-data",
        enabled_by_settings=True,
        open=True,
        connected=True,
        authenticated=True,
        status=LiveStockMarketDataStreamState.CONNECTED,
        subscribed_symbols=("spy", "qqq"),
    )

    assert status.subscribed_symbols == ("SPY", "QQQ")
