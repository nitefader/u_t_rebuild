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

        Re-registering with the same ``consumer_id`` replaces the prior
        subscription — useful when a consumer's symbol set changes (a new
        deployment came online with a fresh universe).

        Must be called before ``start``. Once the hub is running, the
        adapter subscription is fixed; mutate the consumer set by stopping
        the hub, re-registering, and starting again. (Live add/remove of
        symbols on a running stream is a future hub capability.)
        """
        with self._lock:
            if self.is_running:
                raise MarketDataStreamHubError("cannot register a consumer while the hub is running")
            if not consumer_id:
                raise MarketDataStreamHubError("consumer_id is required")
            normalized = frozenset(str(symbol).upper() for symbol in symbols)
            if not normalized:
                raise MarketDataStreamHubError(f"consumer {consumer_id!r} requires at least one symbol")
            self._unregister_locked(consumer_id)
            self._consumers[consumer_id] = _ConsumerEntry(consumer_id=consumer_id, symbols=normalized, on_bar=on_bar)
            for symbol in normalized:
                self._symbol_index[symbol].add(consumer_id)

    def unregister(self, consumer_id: str) -> None:
        with self._lock:
            if self.is_running:
                raise MarketDataStreamHubError("cannot unregister a consumer while the hub is running")
            self._unregister_locked(consumer_id)

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
            self._runner = runner

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            if self._runner is None:
                return
            try:
                self._runner.stop(timeout=timeout)
            finally:
                self._runner = None

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
