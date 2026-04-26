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
            except Exception as exc:  # noqa: BLE001
                logger.warning("market data hub shutdown failed: %s", exc, exc_info=True)


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
        adapter_resolver: Callable[[UUID], AlpacaBrokerAdapter] | None = None,
    ) -> None:
        self._account_id = account_id
        self._broker_adapter = broker_adapter
        # When an explicit adapter isn't supplied, the dispatcher uses
        # ``adapter_resolver`` to fetch a per-account adapter at start
        # time. The resolver is wired by the composition root and pulls
        # credentials from the encrypted ``BrokerCredentialStore``.
        self._adapter_resolver = adapter_resolver
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
                if self._adapter_resolver is None:
                    raise RuntimeError(
                        f"no broker adapter or resolver configured for account {self._account_id}"
                    )
                self._broker_adapter = self._adapter_resolver(self._account_id)
            self._stream_client = self._broker_adapter.build_trading_stream()
            self._stream_adapter = AlpacaAccountStreamAdapter(
                account_id=self._account_id,
                stream_client=self._stream_client,
                normalizer=self._broker_adapter,
            )
            self._stream_adapter.subscribe(self.deliver)
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
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"trade_stream_stop_failed:{exc}"
                logger.warning(
                    "trade stream stop failed for account %s: %s",
                    self._account_id,
                    exc,
                    exc_info=True,
                )

    def _fan_out(self, event: Any) -> None:
        self.deliver(event)

    def deliver(self, event: Any) -> None:
        """Public seam: deliver one event to every subscribed callback.

        Wired internally as the callback bound to
        ``AlpacaAccountStreamAdapter.subscribe`` so production calls land
        here. Also lets tests drive the dispatcher without spinning up a
        real TradingStream — the path delivered here is the *same* path
        a real broker-stream event would take.
        """
        from datetime import datetime as _dt, timezone as _tz

        # Snapshot under lock so a concurrent unsubscribe doesn't tear iteration.
        with self._lock:
            self._last_event_at = _dt.now(_tz.utc)
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            try:
                subscriber.callback(event)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"subscriber_callback_failed:{subscriber.subscriber_id}:{exc}"
                logger.warning(
                    "trade stream subscriber %s failed for account %s: %s",
                    subscriber.subscriber_id,
                    self._account_id,
                    exc,
                    exc_info=True,
                )


class TradeEventDispatcherRegistry:
    """One ``TradeEventDispatcher`` per BrokerAccount, indexed by account_id.

    Built at app startup from the BrokerAccount registry. Each Account's
    stream runs independently for the system's lifetime.
    """

    def __init__(
        self,
        *,
        adapter_resolver: Callable[[UUID], AlpacaBrokerAdapter] | None = None,
    ) -> None:
        self._dispatchers: dict[UUID, TradeEventDispatcher] = {}
        self._adapter_resolver = adapter_resolver
        self._lock = threading.Lock()

    def set_adapter_resolver(self, resolver: Callable[[UUID], AlpacaBrokerAdapter]) -> None:
        """Wire the per-account adapter resolver after construction.

        Bootstrap uses this so dispatchers built before the resolver was
        available still pick up the right per-account adapter on first
        ``start()``.
        """
        with self._lock:
            self._adapter_resolver = resolver

    def get(self, account_id: UUID) -> TradeEventDispatcher | None:
        with self._lock:
            return self._dispatchers.get(account_id)

    def get_or_create(self, account_id: UUID) -> TradeEventDispatcher:
        with self._lock:
            dispatcher = self._dispatchers.get(account_id)
            if dispatcher is None:
                dispatcher = TradeEventDispatcher(
                    account_id=account_id,
                    adapter_resolver=self._adapter_resolver,
                )
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
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "trade dispatcher shutdown failed for account %s: %s",
                    dispatcher.account_id,
                    exc,
                    exc_info=True,
                )


class ManualTradeRegistry:
    """Per-account ``OrderManager`` + ``BrokerSyncService`` for HTTP requests.

    The runtime supervisor owns its own copies of these for live trading; the
    HTTP route can't reach in to share them. To keep one source of truth for
    each account's ledger, this registry is the single composition root used
    by the manual-trade route. The same registry is consulted (or written
    by) the supervisor on startup so the per-account ledger stays unified.
    """

    def __init__(self) -> None:
        self._entries: dict[UUID, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(
        self,
        account_id: UUID,
        *,
        order_manager: Any,
        broker_sync_service: Any,
        broker_adapter: Any,
        runtime_store: Any | None = None,
    ) -> None:
        with self._lock:
            self._entries[account_id] = {
                "order_manager": order_manager,
                "broker_sync_service": broker_sync_service,
                "broker_adapter": broker_adapter,
                "runtime_store": runtime_store,
            }

    def get(self, account_id: UUID) -> dict[str, Any] | None:
        with self._lock:
            entry = self._entries.get(account_id)
            return dict(entry) if entry is not None else None

    def order_manager(self, account_id: UUID) -> Any | None:
        entry = self.get(account_id)
        return None if entry is None else entry["order_manager"]

    def broker_sync_service(self, account_id: UUID) -> Any | None:
        entry = self.get(account_id)
        return None if entry is None else entry["broker_sync_service"]

    def broker_adapter(self, account_id: UUID) -> Any | None:
        entry = self.get(account_id)
        return None if entry is None else entry["broker_adapter"]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def account_ids(self) -> tuple[UUID, ...]:
        with self._lock:
            return tuple(self._entries)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------


_hub_registry: HubRegistry | None = None
_trade_registry: TradeEventDispatcherRegistry | None = None
_manual_trade_registry: ManualTradeRegistry | None = None
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


def manual_trade_registry() -> ManualTradeRegistry:
    global _manual_trade_registry
    with _lock:
        if _manual_trade_registry is None:
            _manual_trade_registry = ManualTradeRegistry()
        return _manual_trade_registry


def bootstrap_streams(broker_account_service: Any | None = None) -> dict[str, Any]:
    """Boot-time start: enumerate ``BrokerAccount``s, start one trade-stream per account.

    Per the runtime architecture spec: every configured Account's
    Broker Trade Update Stream starts at boot, regardless of whether
    any Deployments have subscribed. The Market Data Pipeline (hub) is
    constructed but lazy-starts on first consumer — that is its
    "ready" state.

    Each per-account ``TradeEventDispatcher`` builds its underlying
    ``AlpacaBrokerAdapter`` from the encrypted ``BrokerCredentialStore``
    via the resolver wired here. Accounts without stored credentials
    are skipped with ``needs_credentials``; the dispatcher exposes the
    error via ``last_error`` for the system-streams panel.
    """
    hub_registry()  # construct the hub registry envelope

    if broker_account_service is None:
        try:
            from backend.app.broker_accounts.runtime_service import (
                create_broker_account_service_from_environment,
            )

            broker_account_service = create_broker_account_service_from_environment()
        except Exception as exc:  # noqa: BLE001
            logger.warning("stream bootstrap: broker-account service unavailable: %s", exc)
            return {"started_account_ids": [], "skipped": [], "total_accounts_seen": 0}

    try:
        accounts = list(broker_account_service.list_broker_accounts())
    except Exception as exc:  # noqa: BLE001
        logger.warning("stream bootstrap: could not list broker accounts: %s", exc)
        return {"started_account_ids": [], "skipped": [], "total_accounts_seen": 0}

    def adapter_resolver(account_id: UUID) -> AlpacaBrokerAdapter:
        # Resolve the latest persisted credentials at start-time so a
        # rotated key picks up cleanly when the dispatcher restarts.
        api_key, api_secret = broker_account_service.get_credentials(account_id)
        target = next((a for a in broker_account_service.list_broker_accounts() if a.id == account_id), None)
        if target is None:
            raise RuntimeError(f"unknown account {account_id}")
        return AlpacaBrokerAdapter(mode=target.mode, api_key=api_key, secret_key=api_secret)

    registry = trade_dispatcher_registry()
    registry.set_adapter_resolver(adapter_resolver)
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
        if bool(getattr(account, "is_archived", False)):
            skipped.append((account_id, "archived"))
            continue
        if bool(getattr(account, "needs_credentials", False)):
            skipped.append((account_id, "needs_credentials"))
            continue
        dispatcher = registry.get_or_create(account_id)
        try:
            dispatcher.start()
            started.append(account_id)
        except Exception as exc:  # noqa: BLE001 - failures surface via dispatcher.last_error
            skipped.append((account_id, str(exc)))
    return {
        "started_account_ids": [str(a) for a in started],
        "skipped": [(str(a), reason) for a, reason in skipped],
        "total_accounts_seen": len(accounts),
    }


def register_account_in_manual_trade_registry(broker_account_service: Any, account: Any) -> None:
    """Build the per-account composition stack and register it.

    Pulls the encrypted credentials from ``broker_account_service.get_credentials``,
    builds an ``AlpacaBrokerAdapter`` with the account's mode, wires
    ``OrderManager`` + ``BrokerSync`` + ``BrokerSyncService`` against
    one ledger per account, and registers in ``manual_trade_registry()``.

    Idempotent: re-registering an account replaces the prior entry so
    rotated credentials are picked up immediately without a restart.

    Raises ``CredentialStoreError`` (subclass of ``RuntimeError``) when
    the account has no stored credentials. Callers must surface this as
    ``needs_credentials`` to the operator — the route gates submit on
    the registry returning a wired entry.
    """
    from backend.app.brokers import AlpacaBrokerAdapter, BrokerSync, BrokerSyncService
    from backend.app.config.runtime_paths import get_runtime_db_path
    from backend.app.orders import OrderManager
    from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore, SQLiteTradeLedger

    if getattr(account, "is_archived", False):
        return
    if account.provider != "alpaca":
        raise RuntimeError(f"unsupported provider: {account.provider}")
    api_key, api_secret = broker_account_service.get_credentials(account.id)
    broker_adapter = AlpacaBrokerAdapter(
        mode=account.mode,
        api_key=api_key,
        secret_key=api_secret,
    )
    db_path = get_runtime_db_path()
    runtime_store = SQLiteRuntimeStore(db_path)
    order_manager = OrderManager(
        ledger=SQLiteOrderLedger(db_path),
        broker_adapter=broker_adapter,
    )
    broker_sync = BrokerSync(
        ledger=order_manager.ledger,
        adapter=broker_adapter,
        runtime_store=runtime_store,
        provider="alpaca",
    )
    order_manager._broker_sync = broker_sync
    sync_service = BrokerSyncService(
        adapter=broker_adapter,
        broker_sync=broker_sync,
        order_ledger=order_manager.ledger,
        trade_ledger=SQLiteTradeLedger(db_path),
        runtime_store=runtime_store,
    )
    order_manager.attach_broker_sync_service(sync_service)
    sync_service.record_successful_poll(account.id)
    manual_trade_registry().register(
        account.id,
        order_manager=order_manager,
        broker_sync_service=sync_service,
        broker_adapter=broker_adapter,
        runtime_store=runtime_store,
    )


def bootstrap_manual_trade_composition(broker_account_service: Any | None = None) -> dict[str, Any]:
    """Boot-time wiring of the per-account manual-trade composition root.

    For each non-archived account that has stored credentials, builds
    the per-account stack via ``register_account_in_manual_trade_registry``.
    Accounts without stored credentials are reported skipped — the
    operator must re-enter via the inline credentials surface.
    """
    if broker_account_service is None:
        try:
            from backend.app.broker_accounts.runtime_service import (
                create_broker_account_service_from_environment,
            )

            broker_account_service = create_broker_account_service_from_environment()
        except Exception as exc:  # noqa: BLE001
            logger.warning("manual-trade bootstrap: service unavailable: %s", exc)
            return {"registered_account_ids": [], "skipped": [], "total_accounts_seen": 0}

    try:
        accounts = list(broker_account_service.list_broker_accounts())
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual-trade bootstrap: could not list broker accounts: %s", exc)
        return {"registered_account_ids": [], "skipped": [], "total_accounts_seen": 0}

    registered: list[UUID] = []
    skipped: list[tuple[UUID, str]] = []
    for account in accounts:
        account_id = getattr(account, "id", None)
        if not isinstance(account_id, UUID):
            continue
        try:
            register_account_in_manual_trade_registry(broker_account_service, account)
            registered.append(account_id)
        except Exception as exc:  # noqa: BLE001 - one account's failure must not block others
            logger.warning(
                "manual-trade bootstrap: skipping account %s: %s",
                account_id,
                exc,
            )
            skipped.append((account_id, str(exc)))
    return {
        "registered_account_ids": [str(a) for a in registered],
        "skipped": [(str(a), reason) for a, reason in skipped],
        "total_accounts_seen": len(accounts),
    }


def shutdown_runtime_context() -> None:
    global _hub_registry, _trade_registry, _manual_trade_registry
    with _lock:
        hub_reg = _hub_registry
        trade_reg = _trade_registry
        manual_reg = _manual_trade_registry
        _hub_registry = None
        _trade_registry = None
        _manual_trade_registry = None
    if hub_reg is not None:
        hub_reg.shutdown()
    if trade_reg is not None:
        trade_reg.shutdown()
    if manual_reg is not None:
        manual_reg.clear()
