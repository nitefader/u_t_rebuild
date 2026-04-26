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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from backend.app.api.system_settings_store import setting
from backend.app.features import NormalizedBar
from backend.app.market_data import (
    AlpacaMarketDataAdapter,
    MarketDataStreamHub,
    Provider,
    ServicePurpose,
)


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
        """Operator-driven Service purpose tags take precedence over env vars.

        If a Market Data Service is tagged ``default_for=test_streaming``,
        Chart Lab opens the FAKEPACA synthetic stream. If a Service is
        tagged ``default_for=live_streaming``, Chart Lab opens that
        Service's data feed. Only when no relevant tags exist do we fall
        back to ``ALPACA_USE_TEST_STREAM`` / ``ALPACA_DATA_FEED`` env vars
        (legacy / dev path).
        """
        test_service = _alpaca_service_for_purpose(ServicePurpose.TEST_STREAMING)
        live_service = _alpaca_service_for_purpose(ServicePurpose.LIVE_STREAMING)
        use_tags = test_service is not None or live_service is not None

        if use_tags:
            test_stream = test_service is not None
        else:
            test_stream_raw = setting("alpaca_use_test_stream", fallback_env="ALPACA_USE_TEST_STREAM", default="0")
            test_stream = str(test_stream_raw) in ("1", "true", "True", True)

        has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
        configured_symbol = setting("chart_lab_default_symbol", fallback_env="CHART_LAB_DEFAULT_SYMBOL", default="SPY")
        default_symbol = AlpacaMarketDataAdapter.TEST_SYMBOL if test_stream else str(configured_symbol)
        if test_stream:
            data_feed = "test"
        else:
            data_feed = str(setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex")).lower()
        return cls(
            streaming_enabled=has_creds,
            test_stream=test_stream,
            default_symbol=default_symbol,
            data_feed=data_feed,
        )


def _alpaca_service_for_purpose(purpose: ServicePurpose):
    """Return the Alpaca Market Data Service tagged with ``purpose``, or ``None``.

    Lazy-imports the catalog so test contexts that don't hit the catalog
    don't pay the import cost. Catalog errors are swallowed — Chart Lab
    must still degrade gracefully if the catalog file is unavailable.
    """
    try:
        from backend.app.market_data.runtime import (
            create_market_data_catalog_from_environment,
        )

        catalog = create_market_data_catalog_from_environment()
        return catalog.find_default_for(purpose, provider=Provider.ALPACA)
    except Exception:  # noqa: BLE001 - catalog must not break Chart Lab
        return None


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


@router.websocket("/stream")
async def chart_lab_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    config = ChartLabConfig.from_env()
    symbol = resolve_symbol(websocket.query_params.get("symbol"), config)

    if not config.streaming_enabled:
        await websocket.send_text(json.dumps({"type": "error", "code": "missing_credentials"}))
        await websocket.close()
        return

    from backend.app.domain import TradingMode
    from backend.app.runtime.runtime_context import HubKey, hub_registry

    loop = asyncio.get_running_loop()
    hub = hub_registry().get_or_create(
        HubKey(
            provider="alpaca",
            trading_mode=TradingMode.BROKER_PAPER.value,
            data_feed=config.data_feed,
        )
    )
    consumer_id = f"chart-lab:{uuid4().hex[:8]}"
    ws_open = True

    def on_bar(bar: NormalizedBar) -> None:
        if not ws_open:
            return
        payload = json.dumps({"type": "bar", "data": serialize_bar(bar)})
        future = asyncio.run_coroutine_threadsafe(websocket.send_text(payload), loop)
        future.add_done_callback(lambda done: done.exception())

    try:
        hub.register(consumer_id, [symbol], on_bar)
        if not hub.is_running:
            hub.start()
        await websocket.send_text(json.dumps({"type": "ready", "symbol": symbol, "test_stream": config.test_stream}))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - report and close
        await websocket.send_text(json.dumps({"type": "error", "code": "stream_error", "message": str(exc)}))
    finally:
        ws_open = False
        hub.unregister(consumer_id)
