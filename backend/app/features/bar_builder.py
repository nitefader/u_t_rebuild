"""BarBuilder — calendar-naive intra-day aggregation (Phase 2 §11.1-3, slice 2A).

Aggregates a stream of 1-minute ``NormalizedBar`` instances into completed
higher-timeframe bars using bucket-cross emission. Per ``final_roadmap`` §16
("completed bars over forming bars") and §11.3 ("no incomplete higher
timeframe bars leak into decisions"), the builder:

- Maintains a per-timeframe ``_Accumulator`` for the *currently forming* bar.
- Emits the prior accumulator as a completed bar only when a new 1m bar
  arrives whose bucket key differs from the pending accumulator's.
- Never exposes the forming accumulator on the public surface.

Scope (slice 2A):
- Intra-day timeframes only: ``3m``, ``5m``, ``15m``, ``30m``, ``1h``.
- ``4h``/``1d``/``1w`` are deferred to slice 2B (calendar-aware aggregation —
  4h crosses RTH session ambiguously without a calendar).
- ``flush_at(ts)`` is a no-op stub here; slice 2B wires it to the calendar.

Push contract:
- ``BarBuilder.on_bar(bar_1m) -> tuple[NormalizedBar, ...]`` returns *zero or
  more* completed bars (one per timeframe whose bucket the new bar pushed
  past). The push contract matches ``IncrementalFeatureEngine.update(...)``
  so the FeatureEngine pipeline can chain with no buffering layer in between.

Bucket alignment:
- Wall-clock UTC. For an N-minute timeframe, bucket_open =
  ``ts.replace(second=0, microsecond=0, minute=(ts.minute // N) * N)``.
- 1h aligns to wall-clock hour (09:00, 10:00, …). The first NYSE RTH hour
  may therefore yield a "complete" bar containing only 30 minutes of data
  (09:30 → 10:00); that is a calendar concern handled in 2B, not a
  correctness issue for 2A.

Hard rule (§12 stop 1): this module imports no provider SDK. All input is
``NormalizedBar`` (already normalized upstream by the market-data pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .frames import NormalizedBar


SUPPORTED_TIMEFRAMES: frozenset[str] = frozenset({"3m", "5m", "15m", "30m", "1h"})

INPUT_TIMEFRAME = "1m"


_TIMEFRAME_SECONDS: dict[str, int] = {
    "3m": 3 * 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
}


class BarBuilderError(ValueError):
    """Raised when BarBuilder receives malformed or out-of-order input."""


@dataclass
class _Accumulator:
    """Forming higher-timeframe bar. Never exposed publicly — emit-on-cross only."""

    bucket_open: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def fold(self, bar: NormalizedBar) -> None:
        if bar.high > self.high:
            self.high = bar.high
        if bar.low < self.low:
            self.low = bar.low
        self.close = bar.close
        self.volume += bar.volume


class BarBuilder:
    """Per-symbol stateful 1m-to-higher-timeframe aggregator.

    Construction takes the symbol and a tuple of target timeframes (subset
    of ``SUPPORTED_TIMEFRAMES``). The builder is stateful: it tracks one
    forming accumulator per timeframe.
    """

    def __init__(self, *, symbol: str, timeframes: tuple[str, ...]) -> None:
        if not symbol:
            raise BarBuilderError("BarBuilder requires a non-empty symbol")
        if not timeframes:
            raise BarBuilderError("BarBuilder requires at least one target timeframe")
        unsupported = set(timeframes) - SUPPORTED_TIMEFRAMES
        if unsupported:
            raise BarBuilderError(
                f"BarBuilder slice 2A supports {sorted(SUPPORTED_TIMEFRAMES)}; "
                f"unsupported in this slice: {sorted(unsupported)} "
                f"(4h/1d/1w land in slice 2B with calendar-aware aggregation)"
            )
        self._symbol = symbol.upper()
        self._timeframes = tuple(timeframes)
        self._pending: dict[str, _Accumulator] = {}
        self._last_input_ts: datetime | None = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframes(self) -> tuple[str, ...]:
        return self._timeframes

    def on_bar(self, bar: NormalizedBar) -> tuple[NormalizedBar, ...]:
        """Accept a 1m bar; return any higher-timeframe bars whose buckets just closed.

        Raises :class:`BarBuilderError` for non-1m input, symbol mismatch,
        or non-strictly-increasing timestamps.
        """
        if bar.timeframe != INPUT_TIMEFRAME:
            raise BarBuilderError(
                f"BarBuilder accepts only {INPUT_TIMEFRAME!r} input bars; got {bar.timeframe!r}"
            )
        if bar.symbol.upper() != self._symbol:
            raise BarBuilderError(
                f"BarBuilder bound to symbol {self._symbol!r}; received bar for {bar.symbol!r}"
            )
        normalized_ts = _ensure_aware(bar.timestamp)
        if self._last_input_ts is not None and normalized_ts <= self._last_input_ts:
            raise BarBuilderError(
                "BarBuilder requires strictly increasing 1m bar timestamps "
                f"(last={self._last_input_ts.isoformat()}, got={normalized_ts.isoformat()})"
            )
        self._last_input_ts = normalized_ts

        emitted: list[NormalizedBar] = []
        for timeframe in self._timeframes:
            completed = self._fold_into_timeframe(timeframe, bar, normalized_ts)
            if completed is not None:
                emitted.append(completed)
        return tuple(emitted)

    def flush_at(self, _ts: datetime) -> tuple[NormalizedBar, ...]:
        """Force-emit all forming bars at ``ts``. Slice 2A no-op stub.

        Slice 2B wires this to the calendar so the last 1h bar of a session
        emits at the session close instead of waiting for the next-day open
        (which would falsely fold the next session's first bar into the prior
        session's last bucket). Returns an empty tuple in 2A.
        """
        return ()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fold_into_timeframe(
        self,
        timeframe: str,
        bar: NormalizedBar,
        normalized_ts: datetime,
    ) -> NormalizedBar | None:
        bucket_open = _bucket_open(normalized_ts, timeframe)
        pending = self._pending.get(timeframe)

        if pending is None:
            self._pending[timeframe] = _Accumulator(
                bucket_open=bucket_open,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            return None

        if pending.bucket_open == bucket_open:
            pending.fold(bar)
            return None

        # Bucket crossed: emit completed prior bar, start fresh accumulator.
        completed = NormalizedBar(
            symbol=self._symbol,
            timeframe=timeframe,
            timestamp=pending.bucket_open,
            open=pending.open,
            high=pending.high,
            low=pending.low,
            close=pending.close,
            volume=pending.volume,
        )
        self._pending[timeframe] = _Accumulator(
            bucket_open=bucket_open,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        return completed


class BarBuilderRegistry:
    """Multi-symbol BarBuilder fan-out.

    The market-data pipeline calls ``feed(bar)`` per inbound 1m bar; the
    registry routes by symbol to the right per-symbol BarBuilder and returns
    completed higher-timeframe bars for the FeatureEngine to consume.
    """

    def __init__(self, *, timeframes: tuple[str, ...]) -> None:
        if not timeframes:
            raise BarBuilderError("BarBuilderRegistry requires at least one target timeframe")
        unsupported = set(timeframes) - SUPPORTED_TIMEFRAMES
        if unsupported:
            raise BarBuilderError(
                f"BarBuilderRegistry slice 2A supports {sorted(SUPPORTED_TIMEFRAMES)}; "
                f"unsupported in this slice: {sorted(unsupported)}"
            )
        self._timeframes = tuple(timeframes)
        self._builders: dict[str, BarBuilder] = {}

    @property
    def timeframes(self) -> tuple[str, ...]:
        return self._timeframes

    def builder_for(self, symbol: str) -> BarBuilder:
        canonical = symbol.upper()
        if canonical not in self._builders:
            self._builders[canonical] = BarBuilder(symbol=canonical, timeframes=self._timeframes)
        return self._builders[canonical]

    def feed(self, bar: NormalizedBar) -> tuple[NormalizedBar, ...]:
        return self.builder_for(bar.symbol).on_bar(bar)

    def known_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_aware(ts: datetime) -> datetime:
    """Ensure timezone-aware UTC. Naive inputs are treated as UTC explicitly."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _bucket_open(ts: datetime, timeframe: str) -> datetime:
    """Floor ``ts`` to the start of its bucket for ``timeframe`` (UTC wall-clock)."""
    seconds = _TIMEFRAME_SECONDS[timeframe]
    if timeframe == "1h":
        return ts.replace(minute=0, second=0, microsecond=0)
    minutes_per_bucket = seconds // 60
    floored_minute = (ts.minute // minutes_per_bucket) * minutes_per_bucket
    return ts.replace(minute=floored_minute, second=0, microsecond=0)
