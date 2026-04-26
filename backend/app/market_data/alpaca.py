from __future__ import annotations

import asyncio
import os
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Thread
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.features import NormalizedBar

try:  # pragma: no cover - optional dependency in unit tests.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False


try:  # pragma: no cover - optional dependency in unit tests.
    from alpaca.data.live import StockDataStream
except ImportError:  # pragma: no cover
    StockDataStream = None  # type: ignore[assignment]


class AlpacaMarketDataError(ValueError):
    """Raised when Alpaca market data cannot be normalized or streamed safely."""


class MarketDataStreamRunner:
    """Drive a market-data stream client (StockDataStream / CryptoDataStream) in a daemon thread.

    Both alpaca-py data streams expose a blocking ``run()`` that owns its own
    asyncio event loop. The runner spawns ``run()`` in a daemon thread so the
    main process can keep flowing while bars are pushed into whatever
    handler was registered via ``AlpacaMarketDataAdapter.subscribe_bars``.
    """

    def __init__(self, stream_client: Any, *, name: str = "alpaca-market-data-stream") -> None:
        if not hasattr(stream_client, "run"):
            raise AlpacaMarketDataError("stream client must expose run()")
        self._client = stream_client
        self._name = name
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._client.run, daemon=True, name=self._name)
        self._thread.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        for method_name in ("stop_ws", "stop"):
            method = getattr(self._client, method_name, None)
            if method is None:
                continue
            try:
                result = method()
                if asyncio.iscoroutine(result):
                    asyncio.run(result)
            except Exception:  # noqa: BLE001 - best-effort shutdown
                pass
            break
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class MarketDataSubscription(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str = "1m"
    limit: int = Field(default=5, gt=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def normalize_and_validate_subscription(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        normalized_symbol = str(data.get("symbol", "")).upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", normalized_symbol):
            raise ValueError(f"invalid market data symbol: {data.get('symbol')}")
        if data.get("timeframe", "1m") != "1m":
            raise ValueError("Alpaca streaming skeleton supports 1m bars only")
        normalized = dict(data)
        normalized["symbol"] = normalized_symbol
        return normalized


@dataclass(frozen=True)
class _StreamResult:
    bars: tuple[NormalizedBar, ...]
    error: Exception | None = None


class AlpacaMarketDataAdapter:
    """Alpaca market data adapter.

    This class only maps external market data into NormalizedBar objects. It
    does not compute features, create orders, submit orders, or touch broker
    execution boundaries.

    For weekend / off-hours testing, point ``url_override`` at
    :attr:`TEST_STREAM_URL` and subscribe to :attr:`TEST_SYMBOL`
    (``FAKEPACA``) — Alpaca emits continuous synthetic trades, quotes,
    and bars on that endpoint 24/7.
    """

    provider = "alpaca"

    #: Alpaca's official 24/7 synthetic data stream. Subscribe to ``FAKEPACA``
    #: to receive a continuous fake trade/quote/bar feed for off-hours testing.
    #: See https://docs.alpaca.markets/docs/real-time-stock-pricing-data
    TEST_STREAM_URL = "wss://stream.data.alpaca.markets/v2/test"
    TEST_SYMBOL = "FAKEPACA"

    def __init__(
        self,
        *,
        stream_client: Any | None = None,
        bar_source: Iterable[object] | None = None,
        load_env: bool = True,
        feed: Any | None = None,
        url_override: str | None = None,
    ) -> None:
        self._stream_client = stream_client
        self._bar_source = tuple(bar_source) if bar_source is not None else None
        self._load_env = load_env
        self._feed = feed
        self._url_override = url_override

    def normalize_bar(self, bar: object, *, symbol: str | None = None, timeframe: str = "1m") -> NormalizedBar:
        payload = self._response_to_dict(bar)
        normalized_symbol = str(symbol or payload.get("symbol") or payload.get("S") or "").upper()
        if not normalized_symbol:
            raise AlpacaMarketDataError("Alpaca bar is missing symbol")
        try:
            return NormalizedBar(
                symbol=normalized_symbol,
                timeframe=timeframe,
                timestamp=self._timestamp(payload.get("timestamp") or payload.get("t")),
                open=self._float(payload.get("open") if "open" in payload else payload.get("o")),
                high=self._float(payload.get("high") if "high" in payload else payload.get("h")),
                low=self._float(payload.get("low") if "low" in payload else payload.get("l")),
                close=self._float(payload.get("close") if "close" in payload else payload.get("c")),
                volume=self._float(payload.get("volume") if "volume" in payload else payload.get("v")),
            )
        except (TypeError, ValueError) as exc:
            raise AlpacaMarketDataError(f"invalid Alpaca bar payload for {normalized_symbol}") from exc

    async def collect_bars(
        self,
        *,
        subscription: MarketDataSubscription,
        timeout_seconds: float = 60,
    ) -> tuple[NormalizedBar, ...]:
        if self._bar_source is not None:
            return tuple(
                self.normalize_bar(bar, symbol=subscription.symbol, timeframe=subscription.timeframe)
                for bar in self._bar_source[: subscription.limit]
            )
        stream = self._stream_client or self._build_stream_client()
        return await self._collect_from_stream(stream=stream, subscription=subscription, timeout_seconds=timeout_seconds)

    def collect_bars_sync(
        self,
        *,
        subscription: MarketDataSubscription,
        timeout_seconds: float = 60,
    ) -> tuple[NormalizedBar, ...]:
        return asyncio.run(self.collect_bars(subscription=subscription, timeout_seconds=timeout_seconds))

    def subscribe_bars(
        self,
        symbols: Iterable[str],
        *,
        emit: Callable[[NormalizedBar], None],
        timeframe: str = "1m",
    ) -> Any:
        """Subscribe a normalize-and-emit handler for ``symbols`` on the data stream.

        Returns the underlying stream client so a ``MarketDataStreamRunner``
        can drive its blocking ``run()`` in a background thread. The handler
        registered with the SDK is async (alpaca-py's ``subscribe_bars``
        invokes the handler with ``await``); the emit callback is a
        synchronous function and runs inside the async handler.
        """
        normalized_symbols = tuple(str(symbol).upper() for symbol in symbols)
        if not normalized_symbols:
            raise AlpacaMarketDataError("subscribe_bars requires at least one symbol")
        stream = self._stream_client or self._build_stream_client()

        async def _handler(bar: object) -> None:
            try:
                normalized = self.normalize_bar(bar, timeframe=timeframe)
            except AlpacaMarketDataError:
                return
            emit(normalized)

        stream.subscribe_bars(_handler, *normalized_symbols)
        return stream

    async def _collect_from_stream(
        self,
        *,
        stream: Any,
        subscription: MarketDataSubscription,
        timeout_seconds: float,
    ) -> tuple[NormalizedBar, ...]:
        queue: asyncio.Queue[NormalizedBar | Exception] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        async def handler(bar: object) -> None:
            try:
                normalized = self.normalize_bar(bar, symbol=subscription.symbol, timeframe=subscription.timeframe)
            except Exception as exc:  # noqa: BLE001 - isolate provider callback failures.
                await queue.put(exc)
                self._stop_stream(stream)
                return
            await queue.put(normalized)
            if queue.qsize() >= subscription.limit:
                self._stop_stream(stream)

        stream.subscribe_bars(handler, subscription.symbol)
        run_thread = Thread(target=stream.run, daemon=True)
        run_thread.start()

        bars: list[NormalizedBar] = []
        try:
            while len(bars) < subscription.limit:
                item = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
                if isinstance(item, Exception):
                    raise AlpacaMarketDataError(str(item)) from item
                bars.append(item)
        except TimeoutError as exc:
            self._stop_stream(stream)
            raise AlpacaMarketDataError("timed out waiting for Alpaca market data bars") from exc
        finally:
            self._stop_stream(stream)
            await loop.run_in_executor(None, run_thread.join, 5)
        return tuple(bars)

    def _build_stream_client(self) -> Any:
        if self._load_env:
            load_dotenv()
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        if not api_key or not secret_key:
            raise AlpacaMarketDataError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        if StockDataStream is None:
            raise AlpacaMarketDataError("alpaca-py StockDataStream is required for market data streaming")
        kwargs: dict[str, Any] = {}
        if self._feed is not None:
            kwargs["feed"] = self._feed
        if self._url_override is not None:
            kwargs["url_override"] = self._url_override
        return StockDataStream(api_key, secret_key, **kwargs)  # type: ignore[misc,operator]

    def _stop_stream(self, stream: Any) -> None:
        for method_name in ("stop_ws", "stop"):
            method = getattr(stream, method_name, None)
            if method is None:
                continue
            result = method()
            if asyncio.iscoroutine(result):
                try:
                    asyncio.create_task(result)
                except RuntimeError:
                    pass
            return

    def _response_to_dict(self, response: object) -> dict[str, Any]:
        if isinstance(response, dict):
            return dict(response)
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        keys = ["symbol", "S", "timestamp", "t", "open", "o", "high", "h", "low", "l", "close", "c", "volume", "v"]
        return {key: getattr(response, key) for key in keys if hasattr(response, key)}

    def _timestamp(self, value: object) -> datetime:
        if isinstance(value, datetime):
            timestamp = value
        elif value is not None:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        else:
            raise ValueError("timestamp is required")
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp

    def _float(self, value: object) -> float:
        if value is None:
            raise ValueError("numeric bar value is required")
        return float(value)
