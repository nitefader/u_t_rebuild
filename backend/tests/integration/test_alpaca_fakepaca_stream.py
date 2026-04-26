"""Opt-in real-network test: Alpaca FAKEPACA test stream → MarketDataStreamHub.

Alpaca exposes a 24/7 synthetic data endpoint at
``wss://stream.data.alpaca.markets/v2/test`` that emits continuous fake
trades, quotes, and bars for the symbol ``FAKEPACA``. This test wires
the same production hub + adapter we ship to that endpoint and asserts
that at least one ``NormalizedBar`` lands in our consumer within a
reasonable wall-clock window — proving the bar-flow end-to-end without
waiting for equity market hours.

Skipped by default. To run on a Saturday/Sunday:

    set RUN_ALPACA_FAKEPACA_STREAM=1
    set ALPACA_API_KEY=...
    set ALPACA_SECRET_KEY=...
    pytest backend/tests/integration/test_alpaca_fakepaca_stream.py -v -s

The credentials only need to be valid for *streaming* — no orders are
submitted. Paper credentials work fine.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False

from backend.app.features import NormalizedBar
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataStreamHub


pytestmark = [
    pytest.mark.integration,
    pytest.mark.alpaca_paper,
    pytest.mark.skipif(
        os.getenv("RUN_ALPACA_FAKEPACA_STREAM") != "1",
        reason="set RUN_ALPACA_FAKEPACA_STREAM=1 to drive the Alpaca FAKEPACA test stream",
    ),
]


def test_fakepaca_test_stream_delivers_bars_through_market_data_hub() -> None:
    load_dotenv()
    _require_credentials_and_sdk()

    adapter = AlpacaMarketDataAdapter(
        url_override=AlpacaMarketDataAdapter.TEST_STREAM_URL,
    )
    hub = MarketDataStreamHub(market_data_adapter=adapter, timeframe="1m")

    received: list[NormalizedBar] = []
    bar_arrived = threading.Event()

    def on_bar(bar: NormalizedBar) -> None:
        received.append(bar)
        bar_arrived.set()

    hub.register("fakepaca-smoke", [AlpacaMarketDataAdapter.TEST_SYMBOL], on_bar)
    hub.start()
    try:
        # FAKEPACA emits bars every minute. Allow up to 90 s so the test is
        # robust against connection setup time and the first bar boundary.
        assert bar_arrived.wait(timeout=90.0), "no FAKEPACA bar arrived within 90s"
        assert received, "expected at least one normalized bar from FAKEPACA"
        first = received[0]
        assert first.symbol == AlpacaMarketDataAdapter.TEST_SYMBOL
        assert first.timeframe == "1m"
        assert first.close > 0
        assert first.volume >= 0
    finally:
        hub.stop(timeout=5.0)


def _require_credentials_and_sdk() -> None:
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        pytest.skip("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
    try:
        from alpaca.data.live import StockDataStream  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"alpaca-py is required: {exc}")
