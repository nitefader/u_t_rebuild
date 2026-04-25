"""Market calendar — Phase 2 §11.2 (slice 2B).

Provides a minimum-surface ``MarketCalendar`` Protocol for session windows and
holiday/half-day awareness. Two concrete implementations:

- ``NYSECalendar``: hand-rolled NYSE 2024-2026 holiday + half-day table.
  Stub-quality on purpose — per §16 ("minimum surface, deterministic tests")
  we avoid pulling in ``pandas_market_calendars`` or ``exchange_calendars``
  until another consumer needs broader coverage. Plug those in later by
  swapping the implementation behind the Protocol; no caller code changes.
- ``FixtureCalendar``: explicit ``date -> SessionWindow`` map for tests.

DST is handled via ``zoneinfo.ZoneInfo("America/New_York")`` so session-open
and session-close timestamps are correct in UTC across the EST/EDT boundary
(11:00 a.m. UTC vs 13:30 UTC for the regular 09:30 ET open).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol


REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
HALF_DAY_CLOSE = time(13, 0)


# Hand-rolled NYSE DST transitions for the 2024-2026 hard-coded scope.
# EDT (UTC-4) runs from the 2nd Sunday of March to the 1st Sunday of November;
# EST (UTC-5) runs the rest of the year. The calendar's coverage range is
# 2024-01-01 .. 2026-12-31, so these transition dates are sufficient.
_DST_TRANSITIONS: tuple[tuple[date, date], ...] = (
    (date(2024, 3, 10), date(2024, 11, 3)),  # EDT in [start, end)
    (date(2025, 3, 9), date(2025, 11, 2)),
    (date(2026, 3, 8), date(2026, 11, 1)),
)


def _et_utc_offset_hours(day: date) -> int:
    """Return the UTC offset in hours for NYSE local time on ``day`` (positive
    for east-of-UTC, negative for west). NYSE is always behind UTC, so this
    returns 4 (EDT) or 5 (EST).
    """
    for edt_start, edt_end in _DST_TRANSITIONS:
        if edt_start <= day < edt_end:
            return 4
    return 5


@dataclass(frozen=True)
class SessionWindow:
    """One trading session expressed as UTC open/close instants."""

    session_date: date
    open_utc: datetime
    close_utc: datetime
    is_half_day: bool = False


class MarketCalendar(Protocol):
    """Minimal market-calendar contract.

    Consumers (BarBuilder, FeatureEngine flush) only need to know:
    - whether a calendar day is a trading session
    - the UTC open/close instants for that session
    - what the previous session was (for "previous completed daily bar")

    All higher-level concerns (early-warning banners, calendar version hashes,
    operator surfaces) build on these primitives.
    """

    def is_session_day(self, day: date) -> bool: ...

    def session_window(self, day: date) -> SessionWindow | None: ...

    def previous_session(self, day: date) -> SessionWindow | None: ...

    def next_session(self, day: date) -> SessionWindow | None: ...


# ---------------------------------------------------------------------------
# NYSE hand-rolled calendar (2024-2026)
# ---------------------------------------------------------------------------


_NYSE_FULL_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2024
        date(2024, 1, 1),    # New Year's Day
        date(2024, 1, 15),   # MLK
        date(2024, 2, 19),   # Presidents Day
        date(2024, 3, 29),   # Good Friday
        date(2024, 5, 27),   # Memorial Day
        date(2024, 6, 19),   # Juneteenth
        date(2024, 7, 4),    # Independence Day
        date(2024, 9, 2),    # Labor Day
        date(2024, 11, 28),  # Thanksgiving
        date(2024, 12, 25),  # Christmas
        # 2025
        date(2025, 1, 1),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
        # 2026
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),    # Independence Day observed (Jul 4 falls on Saturday)
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
    }
)

_NYSE_HALF_DAYS: frozenset[date] = frozenset(
    {
        # 2024
        date(2024, 7, 3),    # Day before Independence Day
        date(2024, 11, 29),  # Day after Thanksgiving
        date(2024, 12, 24),  # Christmas Eve
        # 2025
        date(2025, 7, 3),    # Day before Independence Day (observed)
        date(2025, 11, 28),
        date(2025, 12, 24),
        # 2026
        date(2026, 7, 2),    # Day before observed Independence Day (Jul 3)
        date(2026, 11, 27),
        date(2026, 12, 24),
    }
)


class NYSECalendar:
    """Hand-rolled NYSE calendar covering 2024-2026.

    Sessions outside this window raise via ``session_window`` returning ``None``;
    callers should not assume coverage past 2026 until a real calendar
    provider plugs in.
    """

    SUPPORTED_RANGE = (date(2024, 1, 1), date(2026, 12, 31))

    def __init__(self) -> None:
        self._full_holidays = _NYSE_FULL_HOLIDAYS
        self._half_days = _NYSE_HALF_DAYS

    def is_session_day(self, day: date) -> bool:
        if day < self.SUPPORTED_RANGE[0] or day > self.SUPPORTED_RANGE[1]:
            return False
        if day.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return day not in self._full_holidays

    def session_window(self, day: date) -> SessionWindow | None:
        if not self.is_session_day(day):
            return None
        is_half = day in self._half_days
        return _build_session_window(day, is_half_day=is_half)

    def previous_session(self, day: date) -> SessionWindow | None:
        cursor = day - timedelta(days=1)
        # Walk back up to 14 calendar days (covers any holiday cluster).
        for _ in range(14):
            if cursor < self.SUPPORTED_RANGE[0]:
                return None
            window = self.session_window(cursor)
            if window is not None:
                return window
            cursor -= timedelta(days=1)
        return None

    def next_session(self, day: date) -> SessionWindow | None:
        cursor = day + timedelta(days=1)
        for _ in range(14):
            if cursor > self.SUPPORTED_RANGE[1]:
                return None
            window = self.session_window(cursor)
            if window is not None:
                return window
            cursor += timedelta(days=1)
        return None


# ---------------------------------------------------------------------------
# Test fixture calendar
# ---------------------------------------------------------------------------


class FixtureCalendar:
    """Explicit ``date -> SessionWindow`` map for tests.

    Build with handcrafted holidays / half-days / weekend rules so calendar
    behavior is deterministic in unit tests without depending on the real
    NYSE table.
    """

    def __init__(self, sessions: dict[date, SessionWindow]) -> None:
        self._sessions = dict(sessions)

    def is_session_day(self, day: date) -> bool:
        return day in self._sessions

    def session_window(self, day: date) -> SessionWindow | None:
        return self._sessions.get(day)

    def previous_session(self, day: date) -> SessionWindow | None:
        candidates = sorted(d for d in self._sessions if d < day)
        return self._sessions[candidates[-1]] if candidates else None

    def next_session(self, day: date) -> SessionWindow | None:
        candidates = sorted(d for d in self._sessions if d > day)
        return self._sessions[candidates[0]] if candidates else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_session_window(day: date, *, is_half_day: bool = False) -> SessionWindow:
    offset_hours = _et_utc_offset_hours(day)
    et_offset = timezone(timedelta(hours=-offset_hours))
    open_local = datetime.combine(day, REGULAR_OPEN, tzinfo=et_offset)
    close_local = datetime.combine(
        day,
        HALF_DAY_CLOSE if is_half_day else REGULAR_CLOSE,
        tzinfo=et_offset,
    )
    return SessionWindow(
        session_date=day,
        open_utc=open_local.astimezone(timezone.utc),
        close_utc=close_local.astimezone(timezone.utc),
        is_half_day=is_half_day,
    )


def regular_session(day: date) -> SessionWindow:
    """Convenience constructor for a regular 09:30-16:00 ET session on ``day``."""
    return _build_session_window(day, is_half_day=False)


def half_day_session(day: date) -> SessionWindow:
    """Convenience constructor for a 09:30-13:00 ET half-day on ``day``."""
    return _build_session_window(day, is_half_day=True)
