"""BarBuilder — calendar-aware aggregation (Phase 2 §11.1-3, slices 2A + 2B).

Aggregates a stream of 1-minute ``NormalizedBar`` instances into completed
higher-timeframe bars. Per ``final_roadmap`` §16 ("completed bars over forming
bars") and §11.3 ("no incomplete higher timeframe bars leak into decisions"):

- Maintains a per-timeframe ``_Accumulator`` for the *currently forming* bar.
- Emits the prior accumulator as a completed bar when a new 1m bar arrives
  whose bucket key differs from the pending accumulator's, OR when
  ``flush_at(session_close_utc)`` is called by the caller (calendar-driven
  session-close emission).
- Never exposes the forming accumulator on the public surface.

Supported timeframes
--------------------
- Without ``calendar``: intra-day only — ``3m``, ``5m``, ``15m``, ``30m``,
  ``1h``, ``4h``. UTC wall-clock bucket alignment.
- With ``calendar``: adds ``1d`` and ``1w``. Daily bars are session-bounded
  (one bar per trading session); weekly bars aggregate by ISO calendar week.
  ``flush_at`` becomes a real operation: the caller passes the session-close
  UTC instant and any forming bars are emitted.

DST is handled by the calendar: session_open_utc and session_close_utc are
correct across the EST/EDT boundary.

Hard rule (§12 stop 1): this module imports no provider SDK. All input is
``NormalizedBar`` (already normalized upstream by the market-data pipeline).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from .calendar import MarketCalendar
from .frames import NormalizedBar


INTRADAY_SUPPORTED: frozenset[str] = frozenset({"3m", "5m", "15m", "30m", "1h", "4h"})
SESSION_SUPPORTED: frozenset[str] = frozenset({"1d", "1w"})
SUPPORTED_TIMEFRAMES: frozenset[str] = INTRADAY_SUPPORTED | SESSION_SUPPORTED

INPUT_TIMEFRAME = "1m"


_TIMEFRAME_SECONDS: dict[str, int] = {
    "3m": 3 * 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "30m": 30 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
}


class BarBuilderError(ValueError):
    """Raised when BarBuilder receives malformed or out-of-order input."""


@dataclass
class _Accumulator:
    """Forming higher-timeframe bar. Never exposed publicly — emit-on-cross only."""

    bucket_key: object  # datetime for intraday buckets; (iso_year, iso_week) for weekly; date for daily
    bucket_open_ts: datetime
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

    Construction takes the symbol, target timeframes, and (optionally) a
    market calendar. ``calendar`` is required when any session-bounded
    timeframe (``1d``, ``1w``) is requested.
    """

    def __init__(
        self,
        *,
        symbol: str,
        timeframes: tuple[str, ...],
        calendar: MarketCalendar | None = None,
    ) -> None:
        if not symbol:
            raise BarBuilderError("BarBuilder requires a non-empty symbol")
        if not timeframes:
            raise BarBuilderError("BarBuilder requires at least one target timeframe")
        unsupported = set(timeframes) - SUPPORTED_TIMEFRAMES
        if unsupported:
            raise BarBuilderError(
                f"BarBuilder supports {sorted(SUPPORTED_TIMEFRAMES)}; "
                f"unsupported: {sorted(unsupported)}"
            )
        session_required = set(timeframes) & SESSION_SUPPORTED
        if session_required and calendar is None:
            raise BarBuilderError(
                f"timeframes {sorted(session_required)} require a MarketCalendar; "
                f"pass calendar=NYSECalendar() (or a fixture) when constructing the BarBuilder"
            )
        self._symbol = symbol.upper()
        self._timeframes = tuple(timeframes)
        self._calendar = calendar
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

    def flush_at(self, ts: datetime) -> tuple[NormalizedBar, ...]:
        """Emit any forming session-bounded or intra-session bars at ``ts``.

        Calendar-driven: callers (typically the FeatureEngine integration)
        invoke this with the session-close UTC instant so the last 1h / 4h /
        1d bar of the session emits before the next session's first 1m bar
        arrives. Without a calendar the method is a no-op.

        Weekly bars span sessions — they are NOT flushed at session close.
        A forming weekly bucket emits naturally on bucket cross when the
        next ISO week's first 1m bar arrives.
        """
        if self._calendar is None:
            return ()
        normalized_ts = _ensure_aware(ts)
        emitted: list[NormalizedBar] = []
        for timeframe in self._timeframes:
            if timeframe == "1w":
                # Weekly bars persist across session boundaries.
                continue
            pending = self._pending.pop(timeframe, None)
            if pending is None:
                continue
            emitted.append(_completed_from(pending, symbol=self._symbol, timeframe=timeframe))
        # Last input ts advances if flush is past it (session end).
        if self._last_input_ts is None or normalized_ts > self._last_input_ts:
            self._last_input_ts = normalized_ts
        return tuple(emitted)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fold_into_timeframe(
        self,
        timeframe: str,
        bar: NormalizedBar,
        normalized_ts: datetime,
    ) -> NormalizedBar | None:
        bucket_key, bucket_open_ts = self._bucket_for(timeframe, normalized_ts)
        if bucket_key is None:
            # Bar falls outside any session for this calendar-bound timeframe — skip.
            return None
        pending = self._pending.get(timeframe)

        if pending is None:
            self._pending[timeframe] = _Accumulator(
                bucket_key=bucket_key,
                bucket_open_ts=bucket_open_ts,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            return None

        if pending.bucket_key == bucket_key:
            pending.fold(bar)
            return None

        # Bucket crossed: emit completed prior bar, start fresh accumulator.
        completed = _completed_from(pending, symbol=self._symbol, timeframe=timeframe)
        self._pending[timeframe] = _Accumulator(
            bucket_key=bucket_key,
            bucket_open_ts=bucket_open_ts,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        return completed

    def _bucket_for(self, timeframe: str, ts: datetime) -> tuple[object | None, datetime]:
        """Return ``(bucket_key, bucket_open_ts)`` for ``ts`` in ``timeframe``.

        ``bucket_key`` is an opaque value used only for equality comparison
        between adjacent bars to detect bucket crossings. ``bucket_open_ts``
        is the UTC instant used as the emitted bar's timestamp.

        Returns ``(None, ts)`` when the bar falls outside any session for a
        calendar-bound timeframe.
        """
        if timeframe in INTRADAY_SUPPORTED:
            bucket_open = _intraday_bucket_open(ts, timeframe)
            return bucket_open, bucket_open
        assert self._calendar is not None  # checked at construction
        if timeframe == "1d":
            return self._daily_bucket(ts)
        if timeframe == "1w":
            return self._weekly_bucket(ts)
        raise BarBuilderError(f"unhandled timeframe in bucket calculation: {timeframe!r}")

    def _daily_bucket(self, ts: datetime) -> tuple[date | None, datetime]:
        """Daily bucket = session date. Bar timestamp = session_open_utc."""
        session = self._session_for_ts(ts)
        if session is None:
            return None, ts
        return session.session_date, session.open_utc

    def _weekly_bucket(self, ts: datetime) -> tuple[tuple[int, int] | None, datetime]:
        """Weekly bucket = ISO (year, week) of the session date. Timestamp =
        session_open_utc of the first session of that week.
        """
        session = self._session_for_ts(ts)
        if session is None:
            return None, ts
        iso_year, iso_week, _ = session.session_date.isocalendar()
        # Walk back to the first session of this ISO week to get a stable bucket_open_ts.
        first_session_open = session.open_utc
        cursor_session = session
        for _ in range(7):
            previous = self._calendar.previous_session(cursor_session.session_date)
            if previous is None:
                break
            prev_iso = previous.session_date.isocalendar()
            if prev_iso.year != iso_year or prev_iso.week != iso_week:
                break
            first_session_open = previous.open_utc
            cursor_session = previous
        return (iso_year, iso_week), first_session_open

    def _session_for_ts(self, ts: datetime) -> "SessionWindow | None":  # noqa: F821
        """Find the session containing or following ``ts``.

        A bar timestamp may fall during a session (the common case), or in the
        gap between sessions (e.g., overnight tick that the pipeline shouldn't
        produce but we tolerate). When in-gap, attribute the bar to the
        following session.
        """
        assert self._calendar is not None
        candidate_date = ts.astimezone(timezone.utc).date()
        # Try the current UTC date first; if no session, look at adjacent days.
        for offset in (0, -1, 1):
            from datetime import timedelta

            day = candidate_date + timedelta(days=offset)
            window = self._calendar.session_window(day)
            if window is None:
                continue
            if window.open_utc <= ts <= window.close_utc:
                return window
        # Bar is between sessions — attribute to the next session.
        return self._calendar.next_session(candidate_date)


# ---------------------------------------------------------------------------
# Multi-symbol fan-out
# ---------------------------------------------------------------------------


class BarBuilderRegistry:
    """Multi-symbol BarBuilder fan-out.

    The market-data pipeline calls ``feed(bar)`` per inbound 1m bar; the
    registry routes by symbol to the right per-symbol BarBuilder and returns
    completed higher-timeframe bars for the FeatureEngine to consume.
    """

    def __init__(
        self,
        *,
        timeframes: tuple[str, ...],
        calendar: MarketCalendar | None = None,
    ) -> None:
        if not timeframes:
            raise BarBuilderError("BarBuilderRegistry requires at least one target timeframe")
        unsupported = set(timeframes) - SUPPORTED_TIMEFRAMES
        if unsupported:
            raise BarBuilderError(
                f"BarBuilderRegistry supports {sorted(SUPPORTED_TIMEFRAMES)}; "
                f"unsupported: {sorted(unsupported)}"
            )
        if (set(timeframes) & SESSION_SUPPORTED) and calendar is None:
            raise BarBuilderError(
                "session-bounded timeframes (1d / 1w) require a MarketCalendar"
            )
        self._timeframes = tuple(timeframes)
        self._calendar = calendar
        self._builders: dict[str, BarBuilder] = {}

    @property
    def timeframes(self) -> tuple[str, ...]:
        return self._timeframes

    def builder_for(self, symbol: str) -> BarBuilder:
        canonical = symbol.upper()
        if canonical not in self._builders:
            self._builders[canonical] = BarBuilder(
                symbol=canonical,
                timeframes=self._timeframes,
                calendar=self._calendar,
            )
        return self._builders[canonical]

    def feed(self, bar: NormalizedBar) -> tuple[NormalizedBar, ...]:
        return self.builder_for(bar.symbol).on_bar(bar)

    def flush_at(self, ts: datetime) -> dict[str, tuple[NormalizedBar, ...]]:
        """Flush every per-symbol builder. Returns ``{symbol: emitted_bars}``."""
        return {symbol: builder.flush_at(ts) for symbol, builder in self._builders.items()}

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


def _intraday_bucket_open(ts: datetime, timeframe: str) -> datetime:
    """Floor ``ts`` to the start of its bucket for an intraday timeframe."""
    seconds = _TIMEFRAME_SECONDS[timeframe]
    if timeframe == "1h":
        return ts.replace(minute=0, second=0, microsecond=0)
    if timeframe == "4h":
        floored_hour = (ts.hour // 4) * 4
        return ts.replace(hour=floored_hour, minute=0, second=0, microsecond=0)
    minutes_per_bucket = seconds // 60
    floored_minute = (ts.minute // minutes_per_bucket) * minutes_per_bucket
    return ts.replace(minute=floored_minute, second=0, microsecond=0)


def _completed_from(pending: _Accumulator, *, symbol: str, timeframe: str) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=pending.bucket_open_ts,
        open=pending.open,
        high=pending.high,
        low=pending.low,
        close=pending.close,
        volume=pending.volume,
    )
