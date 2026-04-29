from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from backend.app.runtime import runtime_context
from backend.app.brokers import AccountTradeSyncState, BrokerFillUpdateEvent
from backend.app.domain import TradingMode
from backend.app.runtime.runtime_context import (
    HubKey,
    HubRegistry,
    TradeEventDispatcher,
    TradeEventDispatcherRegistry,
    shutdown_runtime_context,
)


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    shutdown_runtime_context()
    yield
    shutdown_runtime_context()


def test_hub_registry_returns_same_hub_for_same_key() -> None:
    built: list[HubKey] = []

    def factory(key: HubKey):
        built.append(key)
        return MagicMock(spec=["stop"])

    registry = HubRegistry(hub_factory=factory)
    key = HubKey(provider="alpaca", data_feed="iex")
    h1 = registry.get_or_create(key)
    h2 = registry.get_or_create(key)
    assert h1 is h2
    assert built == [key]  # built only once


def test_hub_registry_builds_separate_hubs_for_different_keys() -> None:
    registry = HubRegistry(hub_factory=lambda key: MagicMock(spec=["stop"]))
    iex = registry.get_or_create(HubKey("alpaca", "iex"))
    sip = registry.get_or_create(HubKey("alpaca", "sip"))
    assert iex is not sip
    assert len(registry.keys()) == 2


def test_hub_registry_shutdown_stops_all_hubs() -> None:
    stops: list[Any] = []

    def factory(key: HubKey):
        m = MagicMock()
        m.stop = lambda timeout=2.0: stops.append(key)
        return m

    registry = HubRegistry(hub_factory=factory)
    registry.get_or_create(HubKey("alpaca", "iex"))
    registry.get_or_create(HubKey("alpaca", "sip"))
    registry.shutdown()
    assert len(stops) == 2
    assert registry.keys() == ()


def _stubbed_dispatcher(account_id) -> TradeEventDispatcher:
    """Build a dispatcher whose start does not open a real Alpaca connection."""
    dispatcher = TradeEventDispatcher(account_id=account_id)
    started = {"count": 0}

    def fake_start_locked() -> None:
        started["count"] += 1
        dispatcher._runner = MagicMock()
        dispatcher._runner.is_running = True

    dispatcher._start_locked = fake_start_locked  # type: ignore[method-assign]
    dispatcher._started_count = started  # type: ignore[attr-defined]
    return dispatcher


def test_trade_event_dispatcher_carries_real_account_id() -> None:
    account_id = uuid4()
    dispatcher = TradeEventDispatcher(account_id=account_id)
    assert dispatcher.account_id == account_id


def test_trade_event_dispatcher_starts_eagerly_via_start() -> None:
    """Per spec: streams auto-start at boot, not lazily on first subscriber."""
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.start()
    assert dispatcher._started_count["count"] == 1
    # A second start is a no-op while running.
    dispatcher.start()
    assert dispatcher._started_count["count"] == 1


def test_trade_event_dispatcher_does_not_stop_when_last_subscriber_leaves() -> None:
    """Per spec: streams keep running for the system's lifetime regardless of subscribers."""
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.start()
    a = dispatcher.subscribe(lambda e: None)
    b = dispatcher.subscribe(lambda e: None)
    dispatcher.unsubscribe(a)
    dispatcher.unsubscribe(b)
    # Stream still running after every subscriber left.
    assert dispatcher.is_running is True


def test_trade_event_dispatcher_subscribe_does_not_lazy_start() -> None:
    """Browser subscriptions must never be the source of live sync startup."""
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.subscribe(lambda e: None)
    assert dispatcher.is_running is False
    assert dispatcher._started_count["count"] == 0


def test_trade_event_dispatcher_fans_out_to_all_subscribers() -> None:
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.start()
    received_a: list[object] = []
    received_b: list[object] = []
    dispatcher.subscribe(received_a.append)
    dispatcher.subscribe(received_b.append)
    dispatcher._fan_out({"type": "order", "id": "abc"})
    assert received_a == [{"type": "order", "id": "abc"}]
    assert received_b == [{"type": "order", "id": "abc"}]


def test_trade_event_dispatcher_routes_through_broker_sync_before_fanout() -> None:
    account_id = uuid4()
    calls: list[str] = []
    event = BrokerFillUpdateEvent(
        account_id=account_id,
        client_order_id="client-1",
        symbol="SPY",
        qty=1,
        price=100,
        side="buy",
    )

    class SyncService:
        def handle_fill_update(self, routed_event):  # type: ignore[no-untyped-def]
            assert routed_event is event
            calls.append("sync")

    dispatcher = TradeEventDispatcher(account_id=account_id, broker_sync_service=SyncService())
    dispatcher.subscribe(lambda routed_event: calls.append("subscriber"))

    dispatcher.deliver(event)

    assert calls == ["sync", "subscriber"]


def test_trade_event_dispatcher_does_not_fanout_when_broker_sync_route_fails() -> None:
    account_id = uuid4()
    received: list[object] = []
    event = BrokerFillUpdateEvent(
        account_id=account_id,
        client_order_id="client-1",
        symbol="SPY",
        qty=1,
        price=100,
        side="buy",
    )

    class SyncService:
        def handle_fill_update(self, routed_event):  # type: ignore[no-untyped-def]
            _ = routed_event
            raise RuntimeError("sync failed")

    dispatcher = TradeEventDispatcher(account_id=account_id, broker_sync_service=SyncService())
    dispatcher.subscribe(received.append)

    dispatcher.deliver(event)

    assert received == []
    assert "broker_sync_route_failed" in (dispatcher.last_error or "")


def test_trade_event_dispatcher_isolates_failing_subscriber() -> None:
    """One subscriber raising must not stop other subscribers from receiving."""
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.start()
    good_received: list[object] = []
    dispatcher.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    dispatcher.subscribe(good_received.append)
    dispatcher._fan_out({"event": "x"})
    assert good_received == [{"event": "x"}]


def test_trade_event_dispatcher_records_last_event_at() -> None:
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.start()
    assert dispatcher.last_event_at is None
    dispatcher._fan_out({})
    assert dispatcher.last_event_at is not None


def test_trade_event_dispatcher_records_last_error_when_start_fails() -> None:
    """Boot must not crash on broker-stream construction failure; surface via status."""
    dispatcher = TradeEventDispatcher(account_id=uuid4())

    def boom() -> None:
        raise RuntimeError("alpaca-py exploded")

    # Patch the inner adapter build path by replacing _start_locked itself
    # (this test asserts the dispatcher's error-handling contract).
    original_start = dispatcher._start_locked

    def failing_start() -> None:
        try:
            raise RuntimeError("alpaca-py exploded")
        except Exception as exc:
            dispatcher._last_error = str(exc)

    dispatcher._start_locked = failing_start  # type: ignore[method-assign]
    dispatcher.start()
    assert dispatcher.is_running is False
    assert "alpaca-py exploded" in (dispatcher.last_error or "")


def test_trade_event_dispatcher_exposes_account_trade_sync_status() -> None:
    account_id = uuid4()
    dispatcher = _stubbed_dispatcher(account_id)
    dispatcher.start()

    status = dispatcher.status()

    assert status.account_id == account_id
    assert status.status == AccountTradeSyncState.CONNECTED
    assert status.open is True
    assert status.connected is True


def test_trade_event_dispatcher_polls_broker_sync_after_stream_start() -> None:
    account_id = uuid4()
    stream_stop = threading.Event()
    poll_seen = threading.Event()
    calls: list[Any] = []

    class _Stream:
        def subscribe_trade_updates(self, handler):  # type: ignore[no-untyped-def]
            self.handler = handler

        def run(self):  # type: ignore[no-untyped-def]
            stream_stop.wait()

        def stop(self):  # type: ignore[no-untyped-def]
            stream_stop.set()

    class _Adapter:
        mode = TradingMode.BROKER_PAPER

        def build_trading_stream(self):  # type: ignore[no-untyped-def]
            return _Stream()

    class _SyncService:
        def reconcile(self, target_account_id):  # type: ignore[no-untyped-def]
            calls.append(target_account_id)
            poll_seen.set()

    dispatcher = TradeEventDispatcher(
        account_id=account_id,
        broker_adapter=_Adapter(),  # type: ignore[arg-type]
        broker_sync_service=_SyncService(),
        sync_poll_interval_seconds=60.0,
    )

    dispatcher.start()
    assert poll_seen.wait(timeout=2.0)
    dispatcher.shutdown()

    assert calls[0] == account_id


def test_trade_event_dispatcher_polls_broker_sync_even_when_stream_start_fails() -> None:
    account_id = uuid4()
    poll_seen = threading.Event()
    calls: list[Any] = []

    class _Adapter:
        mode = TradingMode.BROKER_PAPER

        def build_trading_stream(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("stream unavailable")

    class _SyncService:
        def reconcile(self, target_account_id):  # type: ignore[no-untyped-def]
            calls.append(target_account_id)
            poll_seen.set()

    dispatcher = TradeEventDispatcher(
        account_id=account_id,
        broker_adapter=_Adapter(),  # type: ignore[arg-type]
        broker_sync_service=_SyncService(),
        sync_poll_interval_seconds=60.0,
    )

    dispatcher.start()
    assert poll_seen.wait(timeout=2.0)
    dispatcher.shutdown()

    assert calls[0] == account_id
    assert "stream unavailable" in (dispatcher.last_error or "")


def test_operator_paused_trade_sync_does_not_restart_on_subscribe() -> None:
    dispatcher = _stubbed_dispatcher(uuid4())
    dispatcher.start()
    dispatcher.pause_for_operator()

    dispatcher.subscribe(lambda event: None)
    status = dispatcher.status()

    assert status.status == AccountTradeSyncState.OPERATOR_PAUSED
    assert status.open is False
    assert status.operator_paused_at is not None
    assert dispatcher._started_count["count"] == 1


def test_trade_dispatcher_registry_returns_all_account_trade_sync_statuses() -> None:
    registry = TradeEventDispatcherRegistry()
    account_a = uuid4()
    account_b = uuid4()
    registry._dispatchers[account_a] = _stubbed_dispatcher(account_a)
    registry._dispatchers[account_b] = _stubbed_dispatcher(account_b)
    registry.start_all()

    statuses = registry.statuses()

    assert {status.account_id for status in statuses} == {account_a, account_b}
    assert all(status.status == AccountTradeSyncState.CONNECTED for status in statuses)


# ---------------------------------------------------------------------------
# Trade dispatcher registry
# ---------------------------------------------------------------------------


def test_dispatcher_registry_returns_same_dispatcher_for_same_account() -> None:
    registry = TradeEventDispatcherRegistry()
    account_id = uuid4()
    a = registry.get_or_create(account_id)
    b = registry.get_or_create(account_id)
    assert a is b
    assert registry.account_ids() == (account_id,)


def test_dispatcher_registry_builds_one_per_account() -> None:
    registry = TradeEventDispatcherRegistry()
    a = registry.get_or_create(uuid4())
    b = registry.get_or_create(uuid4())
    assert a is not b
    assert len(registry.all()) == 2


def test_dispatcher_registry_wires_sync_service_resolver_into_new_dispatchers() -> None:
    account_id = uuid4()
    sync_service = object()
    registry = TradeEventDispatcherRegistry(broker_sync_service_resolver=lambda target: sync_service)

    dispatcher = registry.get_or_create(account_id)

    assert dispatcher._broker_sync_service_resolver(account_id) is sync_service


def test_dispatcher_registry_bind_account_refreshes_concrete_adapter_and_sync() -> None:
    account_id = uuid4()
    registry = TradeEventDispatcherRegistry()
    first_adapter = object()
    second_adapter = object()
    sync_service = object()

    dispatcher = registry.bind_account(account_id, broker_adapter=first_adapter)  # type: ignore[arg-type]
    refreshed = registry.bind_account(
        account_id,
        broker_adapter=second_adapter,  # type: ignore[arg-type]
        broker_sync_service=sync_service,
    )

    assert refreshed is dispatcher
    assert dispatcher._broker_adapter is second_adapter
    assert dispatcher._broker_sync_service is sync_service
    assert dispatcher._broker_stream_router is not None


def test_dispatcher_resolves_sync_service_on_first_event_after_late_registry_wiring() -> None:
    account_id = uuid4()
    calls: list[str] = []
    event = BrokerFillUpdateEvent(
        account_id=account_id,
        client_order_id="client-1",
        symbol="SPY",
        qty=1,
        price=100,
        side="buy",
    )

    class SyncService:
        def handle_fill_update(self, routed_event):  # type: ignore[no-untyped-def]
            assert routed_event is event
            calls.append("sync")

    dispatcher = TradeEventDispatcher(
        account_id=account_id,
        broker_sync_service_resolver=lambda target: SyncService(),
    )
    dispatcher.subscribe(lambda routed_event: calls.append("subscriber"))

    dispatcher.deliver(event)

    assert calls == ["sync", "subscriber"]


def test_dispatcher_registry_shutdown_clears_all() -> None:
    registry = TradeEventDispatcherRegistry()
    registry.get_or_create(uuid4())
    registry.get_or_create(uuid4())
    registry.shutdown()
    assert registry.account_ids() == ()


def test_module_singletons_are_shared_across_calls() -> None:
    r1 = runtime_context.hub_registry()
    r2 = runtime_context.hub_registry()
    assert r1 is r2
    d1 = runtime_context.trade_dispatcher_registry()
    d2 = runtime_context.trade_dispatcher_registry()
    assert d1 is d2


def test_shutdown_runtime_context_clears_singletons() -> None:
    r1 = runtime_context.hub_registry()
    runtime_context.shutdown_runtime_context()
    r2 = runtime_context.hub_registry()
    assert r1 is not r2


# ---------------------------------------------------------------------------
# bootstrap_streams
# ---------------------------------------------------------------------------


def test_bootstrap_streams_starts_one_dispatcher_per_active_alpaca_account() -> None:
    from types import SimpleNamespace

    account_a = SimpleNamespace(id=uuid4(), provider="alpaca", is_archived=False)
    account_b = SimpleNamespace(id=uuid4(), provider="alpaca", is_archived=False)

    class _Service:
        def list_broker_accounts(self):
            return (account_a, account_b)

        def get_credentials(self, account_id):
            return ("K", "S")

    # Replace the registry's dispatcher class so start() doesn't call Alpaca.
    registry = runtime_context.trade_dispatcher_registry()

    started_ids: list = []

    class _StubDispatcher:
        def __init__(self, *, account_id):
            self.account_id = account_id

        def start(self):
            started_ids.append(self.account_id)

        def shutdown(self):
            pass

        is_running = True
        subscriber_ids = ()
        last_event_at = None
        last_error = None

    # Inject stub-dispatchers via direct dict insertion.
    registry._dispatchers[account_a.id] = _StubDispatcher(account_id=account_a.id)
    registry._dispatchers[account_b.id] = _StubDispatcher(account_id=account_b.id)

    result = runtime_context.bootstrap_streams(broker_account_service=_Service())
    assert account_a.id in [a for a in registry.account_ids()]
    assert account_b.id in [a for a in registry.account_ids()]
    assert sorted(started_ids) == sorted([account_a.id, account_b.id])
    assert result["total_accounts_seen"] == 2
    assert len(result["started_account_ids"]) == 2
    assert result["skipped"] == []


def test_bootstrap_streams_starts_live_stock_hub_from_platform_data_feed_not_chart_lab(monkeypatch) -> None:
    started_keys: list[HubKey] = []

    class _Hub:
        def __init__(self, key: HubKey) -> None:
            self.key = key
            self.is_running = False

        def start(self) -> None:
            started_keys.append(self.key)
            self.is_running = True

        def stop(self, *, timeout: float = 2.0) -> None:  # noqa: ARG002
            pass

    runtime_context._hub_registry = HubRegistry(hub_factory=lambda key: _Hub(key))  # type: ignore[attr-defined]

    import backend.app.api.system_settings_store as system_settings_store

    monkeypatch.setattr(
        system_settings_store,
        "setting",
        lambda key, *, fallback_env=None, default=None: "sip" if key == "alpaca_data_feed" else default,
    )

    class _Service:
        def list_broker_accounts(self):
            return ()

    result = runtime_context.bootstrap_streams(broker_account_service=_Service())

    assert runtime_context.hub_registry().keys() == (HubKey("alpaca", "sip"),)
    assert started_keys == [HubKey("alpaca", "sip")]
    assert result["total_accounts_seen"] == 0


def test_platform_live_stock_feed_never_uses_chart_lab_test_stream(monkeypatch) -> None:
    import backend.app.api.system_settings_store as system_settings_store

    monkeypatch.setattr(
        system_settings_store,
        "setting",
        lambda key, *, fallback_env=None, default=None: "test" if key == "alpaca_data_feed" else default,
    )

    assert runtime_context._platform_live_stock_data_feed() == "iex"


def test_default_market_data_hub_uses_frontend_configured_provider_credentials(monkeypatch) -> None:
    service_id = uuid4()

    class _Catalog:
        def find_default_for(self, purpose, *, provider=None):  # type: ignore[no-untyped-def]
            return type("Svc", (), {"id": service_id})()

        def get_credentials(self, target_service_id):  # type: ignore[no-untyped-def]
            assert target_service_id == service_id
            return ("configured-key", "configured-secret")

    import backend.app.market_data.runtime as market_data_runtime

    monkeypatch.setattr(market_data_runtime, "create_market_data_catalog_from_environment", lambda: _Catalog())

    hub = runtime_context._default_hub_factory(HubKey("alpaca", "iex"))

    assert hub._adapter._api_key == "configured-key"
    assert hub._adapter._secret_key == "configured-secret"


def test_bootstrap_streams_skips_archived_and_non_alpaca_and_needs_credentials() -> None:
    from types import SimpleNamespace

    archived = SimpleNamespace(id=uuid4(), provider="alpaca", is_archived=True, needs_credentials=False)
    other_provider = SimpleNamespace(id=uuid4(), provider="future", is_archived=False, needs_credentials=False)
    needs_creds = SimpleNamespace(id=uuid4(), provider="alpaca", is_archived=False, needs_credentials=True)

    class _Service:
        def list_broker_accounts(self):
            return (archived, other_provider, needs_creds)

        def get_credentials(self, account_id):
            raise AssertionError("must not resolve credentials for skipped accounts")

    result = runtime_context.bootstrap_streams(broker_account_service=_Service())
    assert result["started_account_ids"] == []
    skipped_ids = [pair[0] for pair in result["skipped"]]
    assert str(archived.id) in skipped_ids
    assert str(other_provider.id) in skipped_ids
    assert str(needs_creds.id) in skipped_ids


def test_ensure_account_trade_sync_started_uses_registered_manual_trade_stack() -> None:
    from types import SimpleNamespace

    account_id = uuid4()
    stream_stop = threading.Event()

    class _Stream:
        def subscribe_trade_updates(self, handler):  # type: ignore[no-untyped-def]
            self.handler = handler

        def run(self):  # type: ignore[no-untyped-def]
            stream_stop.wait()

        def stop(self):  # type: ignore[no-untyped-def]
            stream_stop.set()

    class _Adapter:
        mode = TradingMode.BROKER_PAPER

        def build_trading_stream(self):  # type: ignore[no-untyped-def]
            return _Stream()

    class _SyncService:
        def reconcile(self, target_account_id):  # type: ignore[no-untyped-def]
            assert target_account_id == account_id

    class _Service:
        def get_credentials(self, target_account_id):  # type: ignore[no-untyped-def]
            raise AssertionError("registered manual stack should provide the adapter")

        def list_broker_accounts(self):  # type: ignore[no-untyped-def]
            return ()

    account = SimpleNamespace(
        id=account_id,
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        is_archived=False,
        needs_credentials=False,
    )
    runtime_context.manual_trade_registry().register(
        account_id,
        order_manager=object(),
        broker_sync_service=_SyncService(),
        broker_adapter=_Adapter(),
    )

    started = runtime_context.ensure_account_trade_sync_started(_Service(), account)
    dispatcher = runtime_context.trade_dispatcher_registry().get(account_id)

    assert started is True
    assert dispatcher is not None
    assert dispatcher.is_running is True
