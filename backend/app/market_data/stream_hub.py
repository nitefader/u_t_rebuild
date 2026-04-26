"""MarketDataStreamHub — one bar stream, many consumers.

Per ``final_roadmap`` §market-data: subscribe once at the lowest required
live bar timeframe (1m), then dispatch by symbol to every consumer that
asked for that symbol. Higher timeframes are built inside each consumer.

Consumers register a ``(consumer_id, symbols, on_bar)`` triple. The hub
takes the union of all consumers' symbols, asks the adapter to subscribe
to that union exactly once, runs the underlying stream client in a daemon
thread, and routes each incoming ``NormalizedBar`` to every consumer
that asked for that symbol.

Consumers today: ``BrokerRuntimeSupervisor`` (paper, later live), Sim Lab
Live Simulation, Chart Lab Live Preview, anything else needing live bars.
The hub does not care what a consumer does with the bar — it only routes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from backend.app.features import NormalizedBar

from .alpaca import AlpacaMarketDataAdapter, AlpacaMarketDataError, MarketDataStreamRunner


@dataclass(frozen=True)
class _ConsumerEntry:
    consumer_id: str
    symbols: frozenset[str]
    on_bar: Callable[[NormalizedBar], None]


class MarketDataStreamHubError(ValueError):
    """Raised when the hub cannot register, dispatch, or shut down safely."""


class MarketDataStreamHub:
    """Single market-data stream, multi-consumer dispatch by symbol."""

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

    def register(
        self,
        consumer_id: str,
        symbols: Iterable[str],
        on_bar: Callable[[NormalizedBar], None],
    ) -> None:
        """Register ``on_bar`` to receive bars for ``symbols``.

        Live-safe — supports register / unregister while the hub is running.
        Re-registering with the same ``consumer_id`` replaces the prior
        subscription. Symbols not previously subscribed to are added to
        the underlying stream client; symbols no longer needed by any
        consumer are removed.
        """
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
            if not self._symbol_index:
                # Nothing to subscribe to — leave the hub idle. Calling
                # stop() on an idle hub is a no-op.
                return
            try:
                stream = self._adapter.subscribe_bars(
                    sorted(self._symbol_index),
                    emit=self._dispatch,
                    timeframe=self._timeframe,
                )
            except AlpacaMarketDataError as exc:
                raise MarketDataStreamHubError(str(exc)) from exc
            runner = self._runner_factory(stream)
            runner.start()
            self._stream = stream
            self._runner = runner

    def stop(self, *, timeout: float = 5.0) -> None:
        # Don't hold the registration lock for the full join — a slow stream
        # shutdown shouldn't block parallel register/unregister calls.
        with self._lock:
            runner = self._runner
            self._runner = None
            self._stream = None
        if runner is not None:
            runner.stop(timeout=timeout)

    def _unsubscribe_symbols(self, symbols: set[str]) -> None:
        """Best-effort: ask the underlying stream to drop ``symbols``.

        alpaca-py's StockDataStream exposes ``unsubscribe_bars(*symbols)``;
        if the client doesn't, log-and-skip rather than crash. Either way,
        the hub's dispatch already skips symbols with no consumers.
        """
        if self._stream is None:
            return
        method = getattr(self._stream, "unsubscribe_bars", None)
        if method is None:
            return
        try:
            method(*sorted(symbols))
        except Exception:  # noqa: BLE001 - best-effort
            pass

    def dispatch_bar(self, bar: NormalizedBar) -> None:
        """Public dispatch hook so tests can feed bars without a real stream."""
        self._dispatch(bar)

    def _dispatch(self, bar: NormalizedBar) -> None:
        symbol = bar.symbol.upper()
        consumer_ids = self._symbol_index.get(symbol)
        if not consumer_ids:
            return
        for consumer_id in tuple(consumer_ids):
            entry = self._consumers.get(consumer_id)
            if entry is None:
                continue
            entry.on_bar(bar)

    def _unregister_locked(self, consumer_id: str) -> None:
        entry = self._consumers.pop(consumer_id, None)
        if entry is None:
            return
        for symbol in entry.symbols:
            self._symbol_index[symbol].discard(consumer_id)
            if not self._symbol_index[symbol]:
                del self._symbol_index[symbol]
