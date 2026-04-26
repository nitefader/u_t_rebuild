from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.features import NormalizedBar
from backend.app.market_data import MarketDataStreamHub, MarketDataStreamHubError


def _bar(symbol: str = "SPY") -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe="1m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=99,
        high=101,
        low=98,
        close=100,
        volume=1000,
    )


class _RecordingAdapter:
    def __init__(self) -> None:
        self.subscribed_symbols: tuple[str, ...] | None = None
        self.subscribed_timeframe: str | None = None
        self.emit_callback = None

    def subscribe_bars(self, symbols, *, emit, timeframe="1m"):  # type: ignore[no-untyped-def]
        self.subscribed_symbols = tuple(symbols)
        self.subscribed_timeframe = timeframe
        self.emit_callback = emit

        class _FakeStream:
            def run(self) -> None: ...
            def stop(self) -> None: ...

        return _FakeStream()


class _FakeRunner:
    def __init__(self, stream) -> None:  # type: ignore[no-untyped-def]
        self.stream = stream
        self.started = False
        self.stopped = False
        self.is_running = False

    def start(self) -> None:
        self.started = True
        self.is_running = True

    def stop(self, *, timeout: float = 5.0) -> None:  # noqa: ARG002
        self.stopped = True
        self.is_running = False


def _make_hub() -> tuple[MarketDataStreamHub, _RecordingAdapter, list[_FakeRunner]]:
    adapter = _RecordingAdapter()
    runners: list[_FakeRunner] = []

    def factory(stream):
        runner = _FakeRunner(stream)
        runners.append(runner)
        return runner

    hub = MarketDataStreamHub(market_data_adapter=adapter, runner_factory=factory)
    return hub, adapter, runners


def test_hub_subscribes_to_union_of_consumer_symbols_on_start() -> None:
    hub, adapter, _ = _make_hub()
    hub.register("broker", ["SPY", "qqq"], lambda bar: None)
    hub.register("sim-lab-live", ["IWM", "qqq"], lambda bar: None)

    hub.start()

    assert adapter.subscribed_symbols == ("IWM", "QQQ", "SPY")
    assert hub.subscribed_symbols == ("IWM", "QQQ", "SPY")
    assert hub.is_running is True


def test_hub_dispatches_bar_only_to_consumers_subscribed_to_that_symbol() -> None:
    hub, _, _ = _make_hub()
    broker_received: list[str] = []
    sim_received: list[str] = []
    hub.register("broker", ["SPY"], lambda bar: broker_received.append(bar.symbol))
    hub.register("sim-lab-live", ["QQQ", "SPY"], lambda bar: sim_received.append(bar.symbol))

    hub.dispatch_bar(_bar("SPY"))
    hub.dispatch_bar(_bar("QQQ"))
    hub.dispatch_bar(_bar("IWM"))

    assert broker_received == ["SPY"]
    assert sim_received == ["SPY", "QQQ"]


def test_re_register_replaces_consumer_subscription() -> None:
    hub, _, _ = _make_hub()
    received_a: list[str] = []
    received_b: list[str] = []
    hub.register("broker", ["SPY"], lambda bar: received_a.append(bar.symbol))
    hub.register("broker", ["QQQ"], lambda bar: received_b.append(bar.symbol))

    hub.dispatch_bar(_bar("SPY"))
    hub.dispatch_bar(_bar("QQQ"))

    assert received_a == []  # original callback no longer registered
    assert received_b == ["QQQ"]


def test_unregister_removes_consumer_and_drops_unused_symbols() -> None:
    hub, _, _ = _make_hub()
    hub.register("broker", ["SPY"], lambda bar: None)
    hub.register("sim-lab-live", ["SPY", "QQQ"], lambda bar: None)

    hub.unregister("broker")

    assert hub.consumer_ids == ("sim-lab-live",)
    assert hub.subscribed_symbols == ("QQQ", "SPY")  # SPY still needed by sim-lab


def test_register_during_run_is_rejected() -> None:
    hub, _, _ = _make_hub()
    hub.register("broker", ["SPY"], lambda bar: None)
    hub.start()
    try:
        with pytest.raises(MarketDataStreamHubError):
            hub.register("sim-lab-live", ["QQQ"], lambda bar: None)
        with pytest.raises(MarketDataStreamHubError):
            hub.unregister("broker")
    finally:
        hub.stop()


def test_double_start_is_rejected() -> None:
    hub, _, _ = _make_hub()
    hub.register("broker", ["SPY"], lambda bar: None)
    hub.start()
    try:
        with pytest.raises(MarketDataStreamHubError):
            hub.start()
    finally:
        hub.stop()


def test_start_with_no_consumers_leaves_hub_idle() -> None:
    hub, adapter, runners = _make_hub()
    hub.start()
    assert adapter.subscribed_symbols is None
    assert hub.is_running is False
    assert runners == []


def test_stop_before_start_is_noop() -> None:
    hub, _, _ = _make_hub()
    hub.stop()  # no exception


def test_register_requires_at_least_one_symbol() -> None:
    hub, _, _ = _make_hub()
    with pytest.raises(MarketDataStreamHubError):
        hub.register("broker", [], lambda bar: None)
