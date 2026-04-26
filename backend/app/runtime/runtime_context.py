"""Process-singletons for live market data + broker streams.

Per the DE review: each browser tab spinning up its own ``StockDataStream``
or ``TradingStream`` is a stop condition (Alpaca rate-limits concurrent
connections per stream type, and per ``final_roadmap §3`` "Pipelines own
streams… one paid stream can serve many accounts"). This module is the
one place that owns those singletons.

Two surfaces:

- ``hub_registry()`` returns a ``HubRegistry`` keyed by
  ``(provider, trading_mode, data_feed)``. Today only one entry exists
  (Alpaca / paper / current data_feed), but the registry shape lines up
  with the future Pipeline-FK refactor where ``pipeline_key`` becomes
  ``pipeline.id``.
- ``trade_event_dispatcher()`` returns a ``TradeEventDispatcher`` —
  one ``TradingStream`` connection, many subscribers. The Operations
  Center trade-stream WebSocket adds a callback per browser tab; the
  underlying TradingStream connects exactly once for the whole process.

Lifecycle:
  - Lazy-built on first request.
  - ``shutdown_runtime_context()`` stops streams + clears singletons
    (use it from FastAPI's shutdown event or in tests).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple
from uuid import UUID, uuid4

from backend.app.brokers import (
    AlpacaAccountStreamAdapter,
    AlpacaBrokerAdapter,
    BrokerStreamRunner,
)
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataStreamHub


class HubKey(NamedTuple):
    """Subscription identity. Two consumers with the same HubKey share one stream."""

    provider: str
    trading_mode: str
    data_feed: str


class HubRegistry:
    """One ``MarketDataStreamHub`` per ``HubKey``. Lazy-built; thread-safe."""

    def __init__(self, hub_factory: Callable[[HubKey], MarketDataStreamHub] | None = None) -> None:
        self._hubs: dict[HubKey, MarketDataStreamHub] = {}
        self._hub_factory = hub_factory or _default_hub_factory
        self._lock = threading.Lock()

    def get_or_create(self, key: HubKey) -> MarketDataStreamHub:
        with self._lock:
            hub = self._hubs.get(key)
            if hub is None:
                hub = self._hub_factory(key)
                self._hubs[key] = hub
            return hub

    def keys(self) -> tuple[HubKey, ...]:
        return tuple(self._hubs)

    def shutdown(self) -> None:
        with self._lock:
            hubs = list(self._hubs.values())
            self._hubs.clear()
        for hub in hubs:
            try:
                hub.stop(timeout=2.0)
            except Exception:  # noqa: BLE001 - best-effort shutdown
                pass


def _default_hub_factory(key: HubKey) -> MarketDataStreamHub:
    if key.provider != "alpaca":
        raise ValueError(f"unsupported provider: {key.provider}")
    if key.data_feed == "test":
        adapter = AlpacaMarketDataAdapter(url_override=AlpacaMarketDataAdapter.TEST_STREAM_URL)
    else:
        try:  # pragma: no cover - alpaca-py optional
            from alpaca.data.enums import DataFeed
            feed = getattr(DataFeed, key.data_feed.upper(), None)
        except ImportError:  # pragma: no cover
            feed = None
        adapter = AlpacaMarketDataAdapter(feed=feed) if feed is not None else AlpacaMarketDataAdapter()
    return MarketDataStreamHub(market_data_adapter=adapter)


@dataclass
class _TradeSubscriber:
    callback: Callable[[Any], None]
    subscriber_id: str


class TradeEventDispatcher:
    """Single Alpaca ``TradingStream`` → many local subscribers.

    Replaces the previous "build a fresh ``TradingStream`` per browser
    tab" pattern. The first ``subscribe()`` call lazy-builds the
    underlying client and starts its daemon-thread runner. ``unsubscribe()``
    removes a callback; when the last subscriber leaves, the stream is
    stopped to release the broker-side connection.
    """

    def __init__(
        self,
        *,
        broker_adapter: AlpacaBrokerAdapter | None = None,
        account_id: UUID | None = None,
    ) -> None:
        self._broker_adapter = broker_adapter
        self._account_id = account_id
        self._subscribers: dict[str, _TradeSubscriber] = {}
        self._stream_client: Any | None = None
        self._stream_adapter: AlpacaAccountStreamAdapter | None = None
        self._runner: BrokerStreamRunner | None = None
        self._lock = threading.Lock()

    @property
    def subscriber_ids(self) -> tuple[str, ...]:
        return tuple(self._subscribers)

    @property
    def is_running(self) -> bool:
        return self._runner is not None and self._runner.is_running

    def subscribe(self, callback: Callable[[Any], None]) -> str:
        subscriber_id = f"trade-sub:{uuid4().hex[:8]}"
        with self._lock:
            self._subscribers[subscriber_id] = _TradeSubscriber(callback=callback, subscriber_id=subscriber_id)
            if self._runner is None:
                self._start_locked()
        return subscriber_id

    def unsubscribe(self, subscriber_id: str) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)
            if not self._subscribers:
                self._stop_locked()

    def shutdown(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._stop_locked()

    def _start_locked(self) -> None:
        if self._broker_adapter is None:
            self._broker_adapter = AlpacaBrokerAdapter()
        if self._account_id is None:
            self._account_id = uuid4()  # synthetic viewer-only id; events are not persisted
        self._stream_client = self._broker_adapter.build_trading_stream()
        self._stream_adapter = AlpacaAccountStreamAdapter(
            account_id=self._account_id,
            stream_client=self._stream_client,
            normalizer=self._broker_adapter,
        )
        self._stream_adapter.subscribe(self._fan_out)
        self._runner = BrokerStreamRunner(self._stream_client)
        self._runner.start()

    def _stop_locked(self) -> None:
        runner = self._runner
        self._runner = None
        self._stream_client = None
        self._stream_adapter = None
        if runner is not None:
            try:
                runner.stop(timeout=2.0)
            except Exception:  # noqa: BLE001
                pass

    def _fan_out(self, event: Any) -> None:
        # Snapshot under lock so a concurrent unsubscribe doesn't tear iteration.
        with self._lock:
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            try:
                subscriber.callback(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not block others
                pass


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------


_hub_registry: HubRegistry | None = None
_trade_dispatcher: TradeEventDispatcher | None = None
_lock = threading.Lock()


def hub_registry() -> HubRegistry:
    global _hub_registry
    with _lock:
        if _hub_registry is None:
            _hub_registry = HubRegistry()
        return _hub_registry


def trade_event_dispatcher() -> TradeEventDispatcher:
    global _trade_dispatcher
    with _lock:
        if _trade_dispatcher is None:
            _trade_dispatcher = TradeEventDispatcher()
        return _trade_dispatcher


def shutdown_runtime_context() -> None:
    global _hub_registry, _trade_dispatcher
    with _lock:
        registry = _hub_registry
        dispatcher = _trade_dispatcher
        _hub_registry = None
        _trade_dispatcher = None
    if registry is not None:
        registry.shutdown()
    if dispatcher is not None:
        dispatcher.shutdown()
