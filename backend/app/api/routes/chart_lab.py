"""Chart Lab — live bar stream surface for the operator UI.

The route opens one WebSocket per browser tab, builds a single-consumer
``MarketDataStreamHub`` for that connection, and pushes serialized
``NormalizedBar`` JSON to the client as bars arrive. On disconnect the
hub is stopped, the stream client closes, and resources are released.

Chart Lab shows **bars only**. Order/fill/account events live on the
Operations Center surface — Chart Lab is for chart viewing.

Account-derived routing:
- The Alpaca adapter reads ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY``
  from environment; the same code path works for paper or live (paper
  vs live is decided by ``ALPACA_BASE_URL`` and the broker_account mode
  upstream — neither is the chart's concern).
- ``ALPACA_USE_TEST_STREAM=1`` flips the adapter to Alpaca's 24/7
  synthetic ``FAKEPACA`` test stream. Use this for weekend / off-hours
  development. The route still accepts a ``?symbol=`` argument but
  silently overrides it to ``FAKEPACA`` when test mode is on, so the
  UI behaves identically in both modes.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.app.features import NormalizedBar
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataStreamHub


try:  # pragma: no cover - alpaca-py optional in tests.
    from alpaca.data.enums import DataFeed
except ImportError:  # pragma: no cover
    DataFeed = None  # type: ignore[assignment]


_DATA_FEED_ALIASES = {
    "iex": "IEX",
    "sip": "SIP",
    "delayed_sip": "DELAYED_SIP",
    "delayed-sip": "DELAYED_SIP",
    "boats": "BOATS",
    "overnight": "OVERNIGHT",
    "otc": "OTC",
}


def resolve_data_feed(env_value: str | None) -> Any:
    """Return the alpaca-py ``DataFeed`` enum for ``env_value`` or None.

    None means "let alpaca-py default to IEX". Unknown values raise so the
    operator gets a clear error rather than silently falling back to a
    different feed than they configured.
    """
    if not env_value or DataFeed is None:
        return None
    name = _DATA_FEED_ALIASES.get(env_value.lower(), env_value.upper())
    feed = getattr(DataFeed, name, None)
    if feed is None:
        raise ValueError(f"unknown ALPACA_DATA_FEED: {env_value!r}")
    return feed


try:  # pragma: no cover - exercised when FastAPI is installed.
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    WebSocket = None  # type: ignore[assignment]
    WebSocketDisconnect = None  # type: ignore[assignment]


class ChartLabHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    streaming_enabled: bool
    test_stream: bool
    default_symbol: str
    data_feed: str
    websocket_path: str


@dataclass(frozen=True)
class ChartLabConfig:
    """Resolved Chart Lab streaming config from env."""

    streaming_enabled: bool
    test_stream: bool
    default_symbol: str
    data_feed: str

    @classmethod
    def from_env(cls) -> "ChartLabConfig":
        test_stream = os.getenv("ALPACA_USE_TEST_STREAM") == "1"
        has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
        default_symbol = AlpacaMarketDataAdapter.TEST_SYMBOL if test_stream else os.getenv("CHART_LAB_DEFAULT_SYMBOL", "SPY")
        data_feed = "test" if test_stream else (os.getenv("ALPACA_DATA_FEED") or "iex").lower()
        return cls(
            streaming_enabled=has_creds,
            test_stream=test_stream,
            default_symbol=default_symbol,
            data_feed=data_feed,
        )


def build_market_data_adapter(config: ChartLabConfig) -> AlpacaMarketDataAdapter:
    if config.test_stream:
        return AlpacaMarketDataAdapter(url_override=AlpacaMarketDataAdapter.TEST_STREAM_URL)
    feed = resolve_data_feed(config.data_feed)
    return AlpacaMarketDataAdapter(feed=feed)


def serialize_bar(bar: NormalizedBar) -> dict[str, Any]:
    return {
        "symbol": bar.symbol,
        "timeframe": bar.timeframe,
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def resolve_symbol(requested: str | None, config: ChartLabConfig) -> str:
    if config.test_stream:
        return AlpacaMarketDataAdapter.TEST_SYMBOL
    return (requested or config.default_symbol).upper()


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/chart-lab", tags=["chart-lab"])
else:
    router = APIRouter(prefix="/api/v1/chart-lab", tags=["chart-lab"])


@router.get("/health", response_model=ChartLabHealthResponse)
def chart_lab_health() -> ChartLabHealthResponse:
    config = ChartLabConfig.from_env()
    return ChartLabHealthResponse(
        streaming_enabled=config.streaming_enabled,
        test_stream=config.test_stream,
        default_symbol=config.default_symbol,
        data_feed=config.data_feed,
        websocket_path="/api/v1/chart-lab/stream",
    )


if APIRouter is not None:  # pragma: no cover - WebSocket only registers with real FastAPI.

    @router.websocket("/stream")
    async def chart_lab_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        config = ChartLabConfig.from_env()
        symbol = resolve_symbol(websocket.query_params.get("symbol"), config)

        if not config.streaming_enabled:
            await websocket.send_text(json.dumps({"type": "error", "code": "missing_credentials"}))
            await websocket.close()
            return

        loop = asyncio.get_running_loop()
        hub = MarketDataStreamHub(market_data_adapter=build_market_data_adapter(config))
        consumer_id = f"chart-lab:{uuid4().hex[:8]}"

        def on_bar(bar: NormalizedBar) -> None:
            payload = json.dumps({"type": "bar", "data": serialize_bar(bar)})
            asyncio.run_coroutine_threadsafe(websocket.send_text(payload), loop)

        try:
            hub.register(consumer_id, [symbol], on_bar)
            hub.start()
            await websocket.send_text(json.dumps({"type": "ready", "symbol": symbol, "test_stream": config.test_stream}))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001 - report and close
            try:
                await websocket.send_text(json.dumps({"type": "error", "code": "stream_error", "message": str(exc)}))
            except Exception:  # noqa: BLE001
                pass
        finally:
            await loop.run_in_executor(None, hub.stop)
