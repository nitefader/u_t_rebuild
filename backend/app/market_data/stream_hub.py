"""MarketDataStreamHub: one live stock bar stream, many consumers.

The hub owns the shared live stock stream boundary. Consumers register a
``(consumer_id, symbols, on_bar)`` triple; the hub keeps one provider
stream open and routes incoming ``NormalizedBar`` objects by symbol.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from backend.app.features import NormalizedBar

from .alpaca import AlpacaMarketDataAdapter, AlpacaMarketDataError, MarketDataStreamRunner
from .models import LiveStockMarketDataStreamState, LiveStockMarketDataStreamStatus


@dataclass(frozen=True)
class _ConsumerEntry:
    consumer_id: str
    symbols: frozenset[str]
    on_bar: Callable[[NormalizedBar], None]


class MarketDataStreamHubError(ValueError):
    """Raised when the hub cannot register, dispatch, or shut down safely."""


class MarketDataStreamHub:
    """Single live stock market-data stream with multi-consumer dispatch."""

    def __init__(
        self,
        *,
        market_data_adapter: AlpacaMarketDataAdapter,
        timeframe: str = "1m",
        runner_factory: Callable[[Any], Any] = MarketDataStreamRunner,
    ) -> None:
        self._adapter = market_data_adapter
        self._timeframe = timeframe
        self._runner_factory = runner_factory
        self._consumers: dict[str, _ConsumerEntry] = {}
        self._symbol_index: dict[str, set[str]] = defaultdict(set)
        self._runner: Any | None = None
        self._stream: Any | None = None
        self._started_at: datetime | None = None
        self._last_message_at: datetime | None = None
        self._last_bar_at_by_symbol: dict[str, datetime] = {}
        self._last_error: str | None = None
        self._reconnect_count = 0
        self._lock = Lock()

    @property
    def is_running(self) -> bool:
        return self._runner is not None and getattr(self._runner, "is_running", False)

    @property
    def subscribed_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._symbol_index))

    @property
    def consumer_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._consumers))

    def status(self) -> LiveStockMarketDataStreamStatus:
        running = self.is_running
        open_ = self._stream is not None
        return LiveStockMarketDataStreamStatus(
            stream_id="live-stock-data",
            enabled_by_settings=True,
            open=open_,
            connected=running,
            authenticated=open_ and self._last_error is None,
            status=self._status_state(open_=open_, running=running),
            subscribed_symbols=self.subscribed_symbols,
            consumer_ids=self.consumer_ids,
            last_message_at=self._last_message_at,
            last_bar_at_by_symbol=dict(self._last_bar_at_by_symbol),
            reconnect_count=self._reconnect_count,
            last_error=self._last_error,
            started_at=self._started_at,
        )

    def register(
        self,
        consumer_id: str,
        symbols: Iterable[str],
        on_bar: Callable[[NormalizedBar], None],
    ) -> None:
        """Register ``on_bar`` to receive bars for ``symbols``."""
        if not consumer_id:
            raise MarketDataStreamHubError("consumer_id is required")
        normalized = frozenset(str(symbol).upper() for symbol in symbols)
        if not normalized:
            raise MarketDataStreamHubError(f"consumer {consumer_id!r} requires at least one symbol")
        with self._lock:
            symbols_before = set(self._symbol_index)
            self._unregister_locked(consumer_id)
            self._consumers[consumer_id] = _ConsumerEntry(consumer_id=consumer_id, symbols=normalized, on_bar=on_bar)
            for symbol in normalized:
                self._symbol_index[symbol].add(consumer_id)
            if self._stream is not None:
                added = set(self._symbol_index) - symbols_before
                dropped = symbols_before - set(self._symbol_index)
                if added:
                    self._adapter.subscribe_bars(sorted(added), emit=self._dispatch, timeframe=self._timeframe, stream=self._stream)
                if dropped:
                    self._unsubscribe_symbols(dropped)

    def unregister(self, consumer_id: str) -> None:
        with self._lock:
            symbols_before = set(self._symbol_index)
            self._unregister_locked(consumer_id)
            if self._stream is not None:
                dropped = symbols_before - set(self._symbol_index)
                if dropped:
                    self._unsubscribe_symbols(dropped)

    def start(self) -> None:
        with self._lock:
            if self._runner is not None:
                raise MarketDataStreamHubError("hub is already running")
            try:
                if self._symbol_index:
                    stream = self._adapter.subscribe_bars(
                        sorted(self._symbol_index),
                        emit=self._dispatch,
                        timeframe=self._timeframe,
                    )
                else:
                    stream = self._adapter.open_stream()
            except AlpacaMarketDataError as exc:
                self._last_error = str(exc)
                raise MarketDataStreamHubError(str(exc)) from exc
            runner = self._runner_factory(stream)
            runner.start()
            self._stream = stream
            self._runner = runner
            self._started_at = datetime.now(timezone.utc)
            self._last_error = None

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            runner = self._runner
            self._runner = None
            self._stream = None
        if runner is not None:
            runner.stop(timeout=timeout)

    def dispatch_bar(self, bar: NormalizedBar) -> None:
        """Public dispatch hook so tests can feed bars without a real stream."""
        self._dispatch(bar)

    def _dispatch(self, bar: NormalizedBar) -> None:
        symbol = bar.symbol.upper()
        self._last_message_at = bar.timestamp
        self._last_bar_at_by_symbol[symbol] = bar.timestamp
        consumer_ids = self._symbol_index.get(symbol)
        if not consumer_ids:
            return
        for consumer_id in tuple(consumer_ids):
            entry = self._consumers.get(consumer_id)
            if entry is None:
                continue
            entry.on_bar(bar)

    def _unsubscribe_symbols(self, symbols: set[str]) -> None:
        if self._stream is None:
            return
        method = getattr(self._stream, "unsubscribe_bars", None)
        if method is None:
            return
        try:
            method(*sorted(symbols))
        except Exception:  # noqa: BLE001 - best-effort provider cleanup
            pass

    def _unregister_locked(self, consumer_id: str) -> None:
        entry = self._consumers.pop(consumer_id, None)
        if entry is None:
            return
        for symbol in entry.symbols:
            self._symbol_index[symbol].discard(consumer_id)
            if not self._symbol_index[symbol]:
                del self._symbol_index[symbol]

    def _status_state(
        self,
        *,
        open_: bool,
        running: bool,
    ) -> LiveStockMarketDataStreamState:
        if not open_:
            if self._last_error is not None:
                return LiveStockMarketDataStreamState.DOWN
            return LiveStockMarketDataStreamState.DISABLED
        if running:
            return LiveStockMarketDataStreamState.CONNECTED
        if self._last_error is not None:
            return LiveStockMarketDataStreamState.DOWN
        return LiveStockMarketDataStreamState.OPEN
