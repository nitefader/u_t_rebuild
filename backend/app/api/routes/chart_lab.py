"""Chart Lab — live bar stream surface for the operator UI.

The route opens one WebSocket per browser tab and registers that tab as a
consumer on the process-wide ``MarketDataStreamHub``. The hub owns the
single live stock market-data stream shared by all components.

Chart Lab shows **bars only**. Order/fill/account events live on the
Operations Center surface — Chart Lab is for chart viewing.

Account-derived routing:
- The Alpaca adapter reads ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY``
  from environment; the same code path works for paper or live (paper
  vs live is decided by ``ALPACA_BASE_URL`` and the broker_account mode
  upstream — neither is the chart's concern).
- **This route is only Chart Lab’s one-symbol bar WebSocket.** Broker
  Trade Update Streams (orders/fills per account on Operations) are a
  different surface and do **not** read ``chart_lab_one_symbol_fakepaca``
  or the streaming-purpose tags below.
- ``ALPACA_USE_TEST_STREAM=1`` (or system settings) flips this adapter
  to Alpaca's 24/7 synthetic ``FAKEPACA`` test stream when no operator
  override is set. The route accepts ``?symbol=`` but overrides it to
  ``FAKEPACA`` when test mode is on.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.system_settings_store import setting
from backend.app.chart_lab import ChartLabPreviewResponse, ChartLabPreviewService
from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.data_center.historical_catalog import configure_persistence
from backend.app.data_center.ingest_service import (
    HistoricalBarIngestRequest,
    HistoricalBarIngestService,
    YahooBarsSource,
    alpaca_bars_source_from_runtime,
)
from backend.app.domain import StrategyVersion
from backend.app.features import FeaturePlanError, NormalizedBar
from backend.app.market_data import (
    AlpacaMarketDataAdapter,
    MarketDataStreamHub,
    Provider,
    ServicePurpose,
)
from backend.app.persistence import SQLiteRuntimeStore


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
    routing_note: str = ""


@dataclass(frozen=True)
class ChartLabConfig:
    """Resolved Chart Lab streaming config from env."""

    streaming_enabled: bool
    test_stream: bool
    default_symbol: str
    data_feed: str
    routing_note: str = ""

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

        operator_override = _chart_lab_one_symbol_stream_override()
        if operator_override is not None:
            test_stream = operator_override
        elif use_tags:
            test_stream = test_service is not None
        else:
            test_stream_raw = setting("alpaca_use_test_stream", fallback_env="ALPACA_USE_TEST_STREAM", default="0")
            test_stream = str(test_stream_raw) in ("1", "true", "True", True)

        selected_service = test_service if test_stream else live_service
        has_configured_service_creds = bool(
            selected_service is not None
            and getattr(selected_service, "has_api_key", False)
            and getattr(selected_service, "has_api_secret", False)
        )
        has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")) or has_configured_service_creds
        configured_symbol = setting("chart_lab_default_symbol", fallback_env="CHART_LAB_DEFAULT_SYMBOL", default="SPY")
        default_symbol = AlpacaMarketDataAdapter.TEST_SYMBOL if test_stream else str(configured_symbol)
        if test_stream:
            data_feed = "test"
        else:
            data_feed = str(setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex")).lower()

        if operator_override is True:
            routing_note = (
                "FAKEPACA is forced on for Chart Lab’s one-symbol bar stream by the Market Data page toggle "
                "(system setting chart_lab_one_symbol_fakepaca). Broker Trade Update Streams on Operations are unchanged."
            )
        elif operator_override is False:
            routing_note = (
                "Chart Lab’s one-symbol bar stream uses real symbols and your configured data feed "
                "(Market Data toggle = Live). Broker Trade Update Streams on Operations are unchanged."
            )
        elif use_tags and test_service is not None:
            routing_note = (
                "FAKEPACA is on because an Alpaca Market Data provider on the Providers page is tagged for "
                "Test streaming. Open Roles on that provider and clear Test streaming to chart real symbols, "
                "or tag Live streaming on the Alpaca provider you want for SIP/IEX bars."
            )
        elif use_tags and live_service is not None:
            routing_note = (
                "Chart Lab follows your Alpaca provider tagged for Live streaming. "
                "This WebSocket is market data (bars), not broker order/fill updates on Operations."
            )
        elif test_stream:
            routing_note = (
                "FAKEPACA is on from Settings (Test stream) or ALPACA_USE_TEST_STREAM in .env. "
                "Turn off the toggle in Settings or set the env var to 0 and restart the API."
            )
        else:
            routing_note = (
                "Chart Lab uses the symbol you enter and your data feed from Settings (or ALPACA_DATA_FEED). "
                "Broker Trade Update Streams on Operations are a different connection (orders/fills)."
            )

        return cls(
            streaming_enabled=has_creds,
            test_stream=test_stream,
            default_symbol=default_symbol,
            data_feed=data_feed,
            routing_note=routing_note,
        )


def _chart_lab_one_symbol_stream_override() -> bool | None:
    """Operator override from ``data/system_settings.json`` (Market Data UI).

    When present, **only** Chart Lab’s one-symbol stream uses FAKEPACA (``True``)
    or real bars (``False``), ignoring catalog ``test_streaming`` / ``live_streaming``
    tags for this decision path. ``None`` = fall back to tags / legacy env.

    Broker trade streams never consult this key.
    """
    try:
        from backend.app.api.system_settings_store import get_store

        raw = get_store().load()
        if "chart_lab_one_symbol_fakepaca" not in raw:
            return None
        return bool(raw["chart_lab_one_symbol_fakepaca"])
    except Exception:  # noqa: BLE001 - Chart Lab must degrade if store fails
        return None


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
        routing_note=config.routing_note,
    )


def _runtime_store() -> SQLiteRuntimeStore:
    store = SQLiteRuntimeStore(get_runtime_db_path())
    configure_persistence(store)
    return store


def _strategy_lookup() -> Any:
    from backend.app.api.routes.strategies import get_strategy_service

    return get_strategy_service()


def _dependency(default: object) -> object:
    return Depends(default)


RuntimeStoreDep = Annotated[Any, _dependency(_runtime_store)]


class ChartLabPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_version_id: UUID
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    start: datetime
    end: datetime
    source: Literal["alpaca", "yahoo"] = "alpaca"
    adjustment_policy: Literal[
        "split_dividend_adjusted", "split_only", "raw"
    ] = "split_dividend_adjusted"


@router.post("/preview", response_model=ChartLabPreviewResponse)
def chart_lab_preview(
    request: ChartLabPreviewRequest,
    store: RuntimeStoreDep,
) -> ChartLabPreviewResponse:
    """Replay a saved StrategyVersion against historical bars and return
    auto-derived features per bar so the operator can plot + verify visually.

    Strategy-only: no Deployment binding required. Drafts and frozen versions
    both work — Chart Lab is research, not deployment.
    """
    if request.start >= request.end:
        raise HTTPException(status_code=422, detail="start must be before end")

    lookup = _strategy_lookup()
    try:
        record = lookup.get_version(request.strategy_version_id)
    except Exception as exc:  # noqa: BLE001 - operator-readable surface
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = getattr(record, "payload", record)
    if not isinstance(payload, StrategyVersion):
        raise HTTPException(
            status_code=422,
            detail=f"strategy_version {request.strategy_version_id} is not a StrategyVersion",
        )

    sources = {"yahoo": YahooBarsSource(), "alpaca": alpaca_bars_source_from_runtime(store)}
    ingest_service = HistoricalBarIngestService(store=store, sources=sources)
    try:
        ingest_result = ingest_service.ensure_bars(
            HistoricalBarIngestRequest(
                provider=request.source,
                symbol=request.symbol,
                timeframe=request.timeframe,
                start=request.start,
                end=request.end,
                adjustment_policy=request.adjustment_policy,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not ingest_result.bars:
        raise HTTPException(
            status_code=422,
            detail=f"no bars available for {request.symbol} {request.timeframe} in window",
        )

    service = ChartLabPreviewService(evidence_recorder=store)
    try:
        return service.preview_strategy(
            strategy=payload,
            bars=ingest_result.bars,
            symbol=request.symbol,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
        )
    except FeaturePlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.websocket("/stream")
async def chart_lab_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    config = ChartLabConfig.from_env()
    symbol = resolve_symbol(websocket.query_params.get("symbol"), config)

    if not config.streaming_enabled:
        await websocket.send_text(json.dumps({"type": "error", "code": "missing_credentials"}))
        await websocket.close()
        return

    from backend.app.runtime.runtime_context import HubKey, hub_registry

    loop = asyncio.get_running_loop()
    hub = hub_registry().get_or_create(
        HubKey(
            provider="alpaca",
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
