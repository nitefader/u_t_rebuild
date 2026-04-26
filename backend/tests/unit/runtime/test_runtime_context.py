from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.app.runtime import runtime_context
from backend.app.runtime.runtime_context import (
    HubKey,
    HubRegistry,
    TradeEventDispatcher,
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
    key = HubKey(provider="alpaca", trading_mode="paper", data_feed="iex")
    h1 = registry.get_or_create(key)
    h2 = registry.get_or_create(key)
    assert h1 is h2
    assert built == [key]  # built only once


def test_hub_registry_builds_separate_hubs_for_different_keys() -> None:
    registry = HubRegistry(hub_factory=lambda key: MagicMock(spec=["stop"]))
    iex = registry.get_or_create(HubKey("alpaca", "paper", "iex"))
    sip = registry.get_or_create(HubKey("alpaca", "paper", "sip"))
    assert iex is not sip
    assert len(registry.keys()) == 2


def test_hub_registry_shutdown_stops_all_hubs() -> None:
    stops: list[Any] = []

    def factory(key: HubKey):
        m = MagicMock()
        m.stop = lambda timeout=2.0: stops.append(key)
        return m

    registry = HubRegistry(hub_factory=factory)
    registry.get_or_create(HubKey("alpaca", "paper", "iex"))
    registry.get_or_create(HubKey("alpaca", "paper", "sip"))
    registry.shutdown()
    assert len(stops) == 2
    assert registry.keys() == ()


def test_trade_event_dispatcher_lazy_starts_on_first_subscribe() -> None:
    dispatcher = TradeEventDispatcher()
    # Patch the start side-effect so we don't open a real Alpaca connection.
    started = {"count": 0}
    stopped = {"count": 0}

    def fake_start_locked() -> None:
        started["count"] += 1
        dispatcher._runner = MagicMock()
        dispatcher._runner.is_running = True
        dispatcher._runner.stop = lambda timeout=2.0: stopped.update(count=stopped["count"] + 1)

    dispatcher._start_locked = fake_start_locked  # type: ignore[method-assign]

    sub_id = dispatcher.subscribe(lambda event: None)
    assert started["count"] == 1
    assert dispatcher.subscriber_ids == (sub_id,)


def test_trade_event_dispatcher_stops_when_last_subscriber_leaves() -> None:
    dispatcher = TradeEventDispatcher()
    started = {"count": 0}
    stopped = {"count": 0}

    def fake_start() -> None:
        started["count"] += 1
        dispatcher._runner = MagicMock()
        dispatcher._runner.is_running = True
        dispatcher._runner.stop = lambda timeout=2.0: stopped.update(count=stopped["count"] + 1)

    dispatcher._start_locked = fake_start  # type: ignore[method-assign]

    a = dispatcher.subscribe(lambda e: None)
    b = dispatcher.subscribe(lambda e: None)
    assert started["count"] == 1  # not restarted
    dispatcher.unsubscribe(a)
    assert stopped["count"] == 0  # b is still subscribed
    dispatcher.unsubscribe(b)
    assert stopped["count"] == 1


def test_trade_event_dispatcher_fans_out_to_all_subscribers() -> None:
    dispatcher = TradeEventDispatcher()
    dispatcher._start_locked = lambda: None  # type: ignore[method-assign]
    dispatcher._runner = MagicMock()
    dispatcher._runner.is_running = True

    received_a: list[object] = []
    received_b: list[object] = []
    dispatcher.subscribe(received_a.append)
    dispatcher.subscribe(received_b.append)

    event = {"type": "order", "id": "abc"}
    dispatcher._fan_out(event)

    assert received_a == [event]
    assert received_b == [event]


def test_trade_event_dispatcher_isolates_failing_subscriber() -> None:
    """One subscriber raising must not stop other subscribers from receiving."""
    dispatcher = TradeEventDispatcher()
    dispatcher._start_locked = lambda: None  # type: ignore[method-assign]
    dispatcher._runner = MagicMock()
    dispatcher._runner.is_running = True

    good_received: list[object] = []
    dispatcher.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("boom")))
    dispatcher.subscribe(good_received.append)

    dispatcher._fan_out({"event": "x"})
    assert good_received == [{"event": "x"}]


def test_module_singletons_are_shared_across_calls() -> None:
    r1 = runtime_context.hub_registry()
    r2 = runtime_context.hub_registry()
    assert r1 is r2
    d1 = runtime_context.trade_event_dispatcher()
    d2 = runtime_context.trade_event_dispatcher()
    assert d1 is d2


def test_shutdown_runtime_context_clears_singletons() -> None:
    r1 = runtime_context.hub_registry()
    runtime_context.shutdown_runtime_context()
    r2 = runtime_context.hub_registry()
    assert r1 is not r2
