from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from backend.app.features import (
    FixtureCalendar,
    NYSECalendar,
    SessionWindow,
    half_day_session,
    regular_session,
)


# ---------------------------------------------------------------------------
# NYSECalendar — session detection
# ---------------------------------------------------------------------------


def test_weekday_is_session_day_outside_holiday_set() -> None:
    calendar = NYSECalendar()
    # Apr 23 2026 is a Thursday and not a holiday.
    assert calendar.is_session_day(date(2026, 4, 23)) is True


def test_weekend_is_not_a_session_day() -> None:
    calendar = NYSECalendar()
    assert calendar.is_session_day(date(2026, 4, 25)) is False  # Saturday
    assert calendar.is_session_day(date(2026, 4, 26)) is False  # Sunday


def test_known_full_holidays_are_excluded() -> None:
    calendar = NYSECalendar()
    for holiday in (
        date(2024, 1, 1),    # New Year's Day
        date(2024, 12, 25),  # Christmas
        date(2025, 7, 4),    # Independence Day
        date(2026, 1, 19),   # MLK
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 7, 3),    # Independence Day observed (Jul 4 is Saturday)
    ):
        assert calendar.is_session_day(holiday) is False, f"{holiday} should be a holiday"


def test_outside_supported_range_is_not_a_session() -> None:
    calendar = NYSECalendar()
    assert calendar.is_session_day(date(2023, 12, 31)) is False
    assert calendar.is_session_day(date(2027, 1, 1)) is False


# ---------------------------------------------------------------------------
# DST-aware session windows
# ---------------------------------------------------------------------------


def test_edt_session_open_close_in_utc() -> None:
    """EDT (UTC-4): 09:30 ET = 13:30 UTC; 16:00 ET = 20:00 UTC."""
    window = NYSECalendar().session_window(date(2026, 4, 23))
    assert window is not None
    assert window.open_utc == datetime(2026, 4, 23, 13, 30, tzinfo=timezone.utc)
    assert window.close_utc == datetime(2026, 4, 23, 20, 0, tzinfo=timezone.utc)
    assert window.is_half_day is False


def test_est_session_open_close_in_utc() -> None:
    """EST (UTC-5): 09:30 ET = 14:30 UTC; 16:00 ET = 21:00 UTC."""
    window = NYSECalendar().session_window(date(2026, 1, 5))  # Monday in EST
    assert window is not None
    assert window.open_utc == datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    assert window.close_utc == datetime(2026, 1, 5, 21, 0, tzinfo=timezone.utc)


def test_half_day_close_at_thirteen_local_time() -> None:
    """Half-days close 13:00 ET. EST → 18:00 UTC; EDT → 17:00 UTC."""
    christmas_eve = NYSECalendar().session_window(date(2026, 12, 24))  # EST
    assert christmas_eve is not None
    assert christmas_eve.is_half_day is True
    assert christmas_eve.close_utc == datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)

    july_3 = NYSECalendar().session_window(date(2024, 7, 3))  # EDT
    assert july_3 is not None
    assert july_3.is_half_day is True
    assert july_3.close_utc == datetime(2024, 7, 3, 17, 0, tzinfo=timezone.utc)


def test_dst_transition_2026_spring_forward() -> None:
    """The Friday before DST (Mar 6) is EST; the Monday after (Mar 9) is EDT."""
    pre = NYSECalendar().session_window(date(2026, 3, 6))  # Fri, EST
    post = NYSECalendar().session_window(date(2026, 3, 9))  # Mon, EDT
    assert pre is not None and post is not None
    assert pre.open_utc.hour == 14  # EST: 09:30 ET = 14:30 UTC
    assert post.open_utc.hour == 13  # EDT: 09:30 ET = 13:30 UTC


# ---------------------------------------------------------------------------
# Previous / next session navigation
# ---------------------------------------------------------------------------


def test_previous_session_skips_weekend() -> None:
    """Monday's previous session is the prior Friday."""
    monday = date(2026, 4, 27)
    prev = NYSECalendar().previous_session(monday)
    assert prev is not None
    assert prev.session_date == date(2026, 4, 24)  # Friday


def test_previous_session_skips_memorial_day_weekend() -> None:
    """Memorial Day 2026 is Mon May 25; previous session of Tue May 26 is Fri May 22
    (Mon is holiday, Sat/Sun are weekend)."""
    prev = NYSECalendar().previous_session(date(2026, 5, 26))
    assert prev is not None
    assert prev.session_date == date(2026, 5, 22)


def test_next_session_skips_thanksgiving() -> None:
    """Wednesday Nov 26 2025 → Thanksgiving Thu Nov 27 → next session is half-day Fri Nov 28."""
    nxt = NYSECalendar().next_session(date(2025, 11, 26))
    assert nxt is not None
    assert nxt.session_date == date(2025, 11, 28)
    assert nxt.is_half_day is True


# ---------------------------------------------------------------------------
# FixtureCalendar
# ---------------------------------------------------------------------------


def test_fixture_calendar_is_explicit() -> None:
    sessions = {
        date(2026, 4, 20): regular_session(date(2026, 4, 20)),
        date(2026, 4, 21): regular_session(date(2026, 4, 21)),
        date(2026, 4, 22): half_day_session(date(2026, 4, 22)),
    }
    cal = FixtureCalendar(sessions)
    assert cal.is_session_day(date(2026, 4, 20)) is True
    assert cal.is_session_day(date(2026, 4, 19)) is False
    assert cal.session_window(date(2026, 4, 22)).is_half_day is True
    assert cal.previous_session(date(2026, 4, 22)).session_date == date(2026, 4, 21)
    assert cal.next_session(date(2026, 4, 21)).session_date == date(2026, 4, 22)


def test_fixture_calendar_returns_none_when_no_neighbor_session() -> None:
    cal = FixtureCalendar({date(2026, 4, 20): regular_session(date(2026, 4, 20))})
    assert cal.previous_session(date(2026, 4, 20)) is None
    assert cal.next_session(date(2026, 4, 20)) is None
