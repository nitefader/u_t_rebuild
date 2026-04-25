from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.features import (
    BarBuilder,
    BarBuilderError,
    BarBuilderRegistry,
    NormalizedBar,
)


def _bar(symbol: str, ts: datetime, *, open: float = 100.0, high: float = 100.5, low: float = 99.5, close: float = 100.2, volume: float = 1000.0) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe="1m",
        timestamp=ts,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _stream_minutes(symbol: str, start: datetime, count: int) -> Iterator[NormalizedBar]:
    for index in range(count):
        ts = start + timedelta(minutes=index)
        yield _bar(symbol, ts, open=100 + index, high=100 + index + 0.5, low=100 + index - 0.3, close=100 + index + 0.2, volume=1000)


# ---------------------------------------------------------------------------
# Aggregation correctness
# ---------------------------------------------------------------------------


def test_three_minute_aggregation_emits_on_bucket_cross() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    emitted: list[NormalizedBar] = []
    for bar in _stream_minutes("SPY", start, 12):
        emitted.extend(builder.on_bar(bar))

    # 12 1m bars cover four 3m buckets (14:00, 14:03, 14:06, 14:09). The last
    # bucket is still forming; only the first three should be emitted.
    assert len(emitted) == 3
    assert [b.timestamp for b in emitted] == [
        start,
        start + timedelta(minutes=3),
        start + timedelta(minutes=6),
    ]
    assert all(b.timeframe == "3m" for b in emitted)


def test_three_minute_ohlcv_is_correctly_aggregated() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    bars = [
        _bar("SPY", start + timedelta(minutes=0), open=100, high=101, low=99.5, close=100.5, volume=1000),
        _bar("SPY", start + timedelta(minutes=1), open=100.5, high=102, low=100, close=101.5, volume=1500),
        _bar("SPY", start + timedelta(minutes=2), open=101.5, high=101.8, low=100.8, close=101.0, volume=2000),
        _bar("SPY", start + timedelta(minutes=3), open=101.0, high=101.2, low=100.5, close=100.8, volume=500),
    ]
    emitted: list[NormalizedBar] = []
    for bar in bars:
        emitted.extend(builder.on_bar(bar))

    assert len(emitted) == 1
    bucket = emitted[0]
    assert bucket.timestamp == start
    assert bucket.open == 100  # first 1m bar's open
    assert bucket.high == 102  # max across all three
    assert bucket.low == 99.5  # min across all three
    assert bucket.close == 101.0  # last 1m bar's close
    assert bucket.volume == 4500  # sum


def test_one_hour_aggregation_aligns_to_wall_clock_hour() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("1h",))
    # Start at 14:30 — the first 1m bar belongs to the 14:00 hour bucket.
    start = datetime(2026, 4, 25, 14, 30, tzinfo=timezone.utc)
    emitted: list[NormalizedBar] = []
    for bar in _stream_minutes("SPY", start, 95):  # crosses two hour buckets
        emitted.extend(builder.on_bar(bar))

    # 14:30 → 16:04 covers buckets 14:00 and 15:00. The 14:00 bucket emits when
    # 15:00 arrives; the 15:00 bucket emits when 16:00 arrives. The 16:00 bucket
    # is forming and must not be emitted.
    assert len(emitted) == 2
    assert [b.timestamp for b in emitted] == [
        datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 25, 15, 0, tzinfo=timezone.utc),
    ]


def test_multiple_timeframes_emit_independently_per_input() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("3m", "5m", "15m", "1h"))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)

    emitted: dict[str, list[NormalizedBar]] = {tf: [] for tf in builder.timeframes}
    for bar in _stream_minutes("SPY", start, 70):
        for completed in builder.on_bar(bar):
            emitted[completed.timeframe].append(completed)

    assert len(emitted["3m"]) == 23
    assert len(emitted["5m"]) == 13
    assert len(emitted["15m"]) == 4
    assert len(emitted["1h"]) == 1


# ---------------------------------------------------------------------------
# Completed-bar-only enforcement (§16 + §11.3)
# ---------------------------------------------------------------------------


def test_forming_bar_never_leaks_through_on_bar() -> None:
    """Per §16 default 'completed bars over forming bars' — until a bucket
    closes, on_bar must not emit anything for that bucket.
    """
    builder = BarBuilder(symbol="SPY", timeframes=("15m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    # Feed 14 bars (14:00 → 14:13). All in bucket 14:00. Bucket 14:15 hasn't started.
    for bar in _stream_minutes("SPY", start, 14):
        emitted = builder.on_bar(bar)
        assert emitted == (), f"forming-bar leak at minute {bar.timestamp.isoformat()}"


def test_no_public_accessor_exposes_forming_bar() -> None:
    """The forming accumulator must remain internal — there is no
    ``current()`` / ``forming()`` / ``pending()`` method.
    """
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    builder.on_bar(_bar("SPY", start))
    public_attrs = {name for name in dir(builder) if not name.startswith("_")}
    forbidden = {"current", "forming", "pending", "in_progress"}
    assert public_attrs.isdisjoint(forbidden), f"forming-bar accessor leaked: {public_attrs & forbidden}"


def test_flush_at_is_a_no_op_in_slice_2a() -> None:
    """Slice 2A: flush_at is a stub. Calendar-aware session-close emission lands in 2B."""
    builder = BarBuilder(symbol="SPY", timeframes=("1h",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    for bar in _stream_minutes("SPY", start, 30):
        builder.on_bar(bar)
    # The 14:00 hour is forming. flush_at must be a no-op in 2A.
    assert builder.flush_at(start + timedelta(hours=1)) == ()


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_rejects_non_one_minute_input_bar() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    bar_5m = NormalizedBar(
        symbol="SPY", timeframe="5m",
        timestamp=datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc),
        open=100, high=101, low=99, close=100.5, volume=1000,
    )
    with pytest.raises(BarBuilderError, match="1m"):
        builder.on_bar(bar_5m)


def test_rejects_symbol_mismatch() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    aapl = _bar("AAPL", datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc))
    with pytest.raises(BarBuilderError, match="SPY"):
        builder.on_bar(aapl)


def test_rejects_non_strictly_increasing_timestamps() -> None:
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)
    builder.on_bar(_bar("SPY", start))
    with pytest.raises(BarBuilderError, match="strictly increasing"):
        builder.on_bar(_bar("SPY", start))  # same timestamp


def test_rejects_unsupported_timeframe_in_2a() -> None:
    """Slice 2A supports {3m, 5m, 15m, 30m, 1h}; 4h/1d/1w are 2B."""
    with pytest.raises(BarBuilderError, match="2B"):
        BarBuilder(symbol="SPY", timeframes=("4h",))
    with pytest.raises(BarBuilderError, match="2B"):
        BarBuilder(symbol="SPY", timeframes=("1d",))
    with pytest.raises(BarBuilderError, match="2B"):
        BarBuilder(symbol="SPY", timeframes=("1w",))


def test_rejects_empty_timeframes() -> None:
    with pytest.raises(BarBuilderError):
        BarBuilder(symbol="SPY", timeframes=())


def test_rejects_empty_symbol() -> None:
    with pytest.raises(BarBuilderError):
        BarBuilder(symbol="", timeframes=("3m",))


def test_normalizes_naive_timestamp_to_utc() -> None:
    """Naive timestamps are treated as UTC — no silent timezone surprise."""
    builder = BarBuilder(symbol="SPY", timeframes=("3m",))
    naive = datetime(2026, 4, 25, 14, 0)  # no tzinfo
    bar = NormalizedBar(
        symbol="SPY", timeframe="1m", timestamp=naive,
        open=100, high=101, low=99, close=100.5, volume=1000,
    )
    builder.on_bar(bar)
    # No exception → naive accepted as UTC.


# ---------------------------------------------------------------------------
# BarBuilderRegistry — multi-symbol fan-out
# ---------------------------------------------------------------------------


def test_registry_routes_bars_by_symbol() -> None:
    registry = BarBuilderRegistry(timeframes=("3m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)

    spy_bars = list(_stream_minutes("SPY", start, 6))
    aapl_bars = list(_stream_minutes("AAPL", start, 6))

    spy_emitted: list[NormalizedBar] = []
    aapl_emitted: list[NormalizedBar] = []
    for spy_bar, aapl_bar in zip(spy_bars, aapl_bars):
        spy_emitted.extend(registry.feed(spy_bar))
        aapl_emitted.extend(registry.feed(aapl_bar))

    assert {b.symbol for b in spy_emitted} == {"SPY"}
    assert {b.symbol for b in aapl_emitted} == {"AAPL"}
    assert "SPY" in registry.known_symbols()
    assert "AAPL" in registry.known_symbols()


def test_registry_lazy_instantiates_one_builder_per_symbol() -> None:
    registry = BarBuilderRegistry(timeframes=("3m",))
    assert registry.known_symbols() == ()
    assert registry.builder_for("SPY") is registry.builder_for("SPY")
    assert registry.builder_for("SPY") is registry.builder_for("spy")  # case-insensitive
    assert registry.known_symbols() == ("SPY",)


def test_registry_per_symbol_state_is_isolated() -> None:
    """A bad bar on one symbol must not corrupt another symbol's accumulator."""
    registry = BarBuilderRegistry(timeframes=("3m",))
    start = datetime(2026, 4, 25, 14, 0, tzinfo=timezone.utc)

    registry.feed(_bar("SPY", start))
    with pytest.raises(BarBuilderError):
        registry.feed(_bar("SPY", start))  # same ts → reject

    # AAPL state is untouched and accepts new input cleanly.
    registry.feed(_bar("AAPL", start))
    registry.feed(_bar("AAPL", start + timedelta(minutes=1)))
    # No exceptions → independent state.
