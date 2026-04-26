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

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

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
    """One Alpaca ``TradingStream`` per BrokerAccount → many local subscribers.

    Per the runtime architecture spec: "There is one Broker Trade Update
    Stream per Account. These streams start automatically for every
    configured Account when the system boots, regardless of whether the
    Account has any Deployments subscribed."

    The stream stays running for the system's lifetime once started — it
    does NOT stop when the last UI subscriber leaves (a closed browser
    tab is not a reason to drop the broker connection). ``shutdown()`` is
    the only path that tears it down (process exit).
    """

    def __init__(
        self,
        *,
        account_id: UUID,
        broker_adapter: AlpacaBrokerAdapter | None = None,
    ) -> None:
        self._account_id = account_id
        self._broker_adapter = broker_adapter
        self._subscribers: dict[str, _TradeSubscriber] = {}
        self._stream_client: Any | None = None
        self._stream_adapter: AlpacaAccountStreamAdapter | None = None
        self._runner: BrokerStreamRunner | None = None
        self._last_event_at: datetime | None = None
        self._last_error: str | None = None
        self._lock = threading.Lock()

    @property
    def account_id(self) -> UUID:
        return self._account_id

    @property
    def subscriber_ids(self) -> tuple[str, ...]:
        return tuple(self._subscribers)

    @property
    def is_running(self) -> bool:
        return self._runner is not None and self._runner.is_running

    @property
    def last_event_at(self) -> datetime | None:
        return self._last_event_at

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start(self) -> None:
        """Eagerly start the underlying TradingStream — boot-time entrypoint."""
        with self._lock:
            if self._runner is None:
                self._start_locked()

    def subscribe(self, callback: Callable[[Any], None]) -> str:
        subscriber_id = f"trade-sub:{uuid4().hex[:8]}"
        with self._lock:
            self._subscribers[subscriber_id] = _TradeSubscriber(callback=callback, subscriber_id=subscriber_id)
            if self._runner is None:
                self._start_locked()
        return subscriber_id

    def unsubscribe(self, subscriber_id: str) -> None:
        # Per spec: streams keep running regardless of subscriber count.
        # We just drop the callback; the broker connection stays open.
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def shutdown(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._stop_locked()

    def _start_locked(self) -> None:
        try:
            if self._broker_adapter is None:
                self._broker_adapter = AlpacaBrokerAdapter()
            self._stream_client = self._broker_adapter.build_trading_stream()
            self._stream_adapter = AlpacaAccountStreamAdapter(
                account_id=self._account_id,
                stream_client=self._stream_client,
                normalizer=self._broker_adapter,
            )
            self._stream_adapter.subscribe(self._fan_out)
            self._runner = BrokerStreamRunner(self._stream_client)
            self._runner.start()
            self._last_error = None
        except Exception as exc:  # noqa: BLE001 - boot must not crash; surface via status
            self._last_error = str(exc)
            self._stream_client = None
            self._stream_adapter = None
            self._runner = None

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
        from datetime import datetime as _dt, timezone as _tz

        # Snapshot under lock so a concurrent unsubscribe doesn't tear iteration.
        with self._lock:
            self._last_event_at = _dt.now(_tz.utc)
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            try:
                subscriber.callback(event)
            except Exception:  # noqa: BLE001 - one bad subscriber must not block others
                pass


class TradeEventDispatcherRegistry:
    """One ``TradeEventDispatcher`` per BrokerAccount, indexed by account_id.

    Built at app startup from the BrokerAccount registry. Each Account's
    stream runs independently for the system's lifetime.
    """

    def __init__(self) -> None:
        self._dispatchers: dict[UUID, TradeEventDispatcher] = {}
        self._lock = threading.Lock()

    def get(self, account_id: UUID) -> TradeEventDispatcher | None:
        with self._lock:
            return self._dispatchers.get(account_id)

    def get_or_create(self, account_id: UUID) -> TradeEventDispatcher:
        with self._lock:
            dispatcher = self._dispatchers.get(account_id)
            if dispatcher is None:
                dispatcher = TradeEventDispatcher(account_id=account_id)
                self._dispatchers[account_id] = dispatcher
            return dispatcher

    def all(self) -> tuple[TradeEventDispatcher, ...]:
        with self._lock:
            return tuple(self._dispatchers.values())

    def account_ids(self) -> tuple[UUID, ...]:
        with self._lock:
            return tuple(self._dispatchers)

    def start_all(self) -> None:
        for dispatcher in self.all():
            dispatcher.start()

    def shutdown(self) -> None:
        with self._lock:
            dispatchers = list(self._dispatchers.values())
            self._dispatchers.clear()
        for dispatcher in dispatchers:
            try:
                dispatcher.shutdown()
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------


_hub_registry: HubRegistry | None = None
_trade_registry: TradeEventDispatcherRegistry | None = None
_lock = threading.Lock()


def hub_registry() -> HubRegistry:
    global _hub_registry
    with _lock:
        if _hub_registry is None:
            _hub_registry = HubRegistry()
        return _hub_registry


def trade_dispatcher_registry() -> TradeEventDispatcherRegistry:
    global _trade_registry
    with _lock:
        if _trade_registry is None:
            _trade_registry = TradeEventDispatcherRegistry()
        return _trade_registry


def bootstrap_streams(broker_accounts: Any | None = None) -> dict[str, Any]:
    """Boot-time start: enumerate ``BrokerAccount``s, start one trade-stream per account.

    Per the runtime architecture spec: every configured Account's
    Broker Trade Update Stream starts at boot, regardless of whether
    any Deployments have subscribed. The Market Data Pipeline (hub) is
    constructed but lazy-starts on first consumer — that is its
    "ready" state.

    ``broker_accounts`` is optional: if a runtime store / service is
    provided (anything with ``list_broker_accounts() -> Iterable[BrokerAccount]``),
    its accounts are enumerated. If None, we attempt to discover from
    the default ``SQLiteRuntimeStore``; failures are logged and result
    in zero dispatchers (the system still boots).

    Returns a small status dict for logging / status endpoints.
    """
    hub_registry()  # construct the hub registry envelope

    accounts: list[Any] = []
    if broker_accounts is not None and hasattr(broker_accounts, "list_broker_accounts"):
        try:
            accounts = list(broker_accounts.list_broker_accounts())
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not list broker accounts: %s", exc)
    else:
        try:
            from backend.app.config.runtime_paths import get_runtime_db_path
            from backend.app.persistence import SQLiteRuntimeStore

            store = SQLiteRuntimeStore(get_runtime_db_path())
            if hasattr(store, "list_broker_accounts"):
                accounts = list(store.list_broker_accounts())
        except Exception as exc:  # noqa: BLE001
            logger.warning("default runtime store unavailable for stream bootstrap: %s", exc)

    registry = trade_dispatcher_registry()
    started: list[UUID] = []
    skipped: list[tuple[UUID, str]] = []
    for account in accounts:
        account_id = getattr(account, "id", None)
        if not isinstance(account_id, UUID):
            continue
        provider = getattr(account, "provider", "")
        if provider != "alpaca":
            skipped.append((account_id, f"unsupported provider: {provider}"))
            continue
        is_archived = bool(getattr(account, "is_archived", False))
        if is_archived:
            skipped.append((account_id, "archived"))
            continue
        dispatcher = registry.get_or_create(account_id)
        try:
            dispatcher.start()
            started.append(account_id)
        except Exception as exc:  # noqa: BLE001
            skipped.append((account_id, str(exc)))
    return {
        "started_account_ids": [str(a) for a in started],
        "skipped": [(str(a), reason) for a, reason in skipped],
        "total_accounts_seen": len(accounts),
    }


def shutdown_runtime_context() -> None:
    global _hub_registry, _trade_registry
    with _lock:
        hub_reg = _hub_registry
        trade_reg = _trade_registry
        _hub_registry = None
        _trade_registry = None
    if hub_reg is not None:
        hub_reg.shutdown()
    if trade_reg is not None:
        trade_reg.shutdown()
