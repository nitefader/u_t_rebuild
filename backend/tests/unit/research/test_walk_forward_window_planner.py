"""Tests for the walk-forward window planner."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.research.walk_forward.window_planner import (
    LengthSpec,
    WindowPlannerError,
    plan_fold_windows,
)


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def test_rolling_mode_advances_both_is_endpoints_each_fold() -> None:
    folds = plan_fold_windows(
        window_mode="rolling",
        start=_dt(2024, 1, 1),
        end=_dt(2025, 1, 1),
        is_length=LengthSpec(unit="days", value=180),
        oos_length=LengthSpec(unit="days", value=30),
        step=LengthSpec(unit="days", value=30),
        timeframe="1d",
    )
    assert len(folds) >= 5
    # In rolling mode, each successive fold's IS-start must advance by step.
    is_starts = [f.is_start for f in folds]
    diffs = [(b - a).days for a, b in zip(is_starts, is_starts[1:])]
    assert all(d == 30 for d in diffs)
    # OOS must immediately follow IS for every fold.
    for fold in folds:
        assert fold.oos_start == fold.is_end


def test_anchored_mode_keeps_is_start_fixed() -> None:
    folds = plan_fold_windows(
        window_mode="anchored",
        start=_dt(2024, 1, 1),
        end=_dt(2025, 1, 1),
        is_length=LengthSpec(unit="days", value=180),
        oos_length=LengthSpec(unit="days", value=30),
        step=LengthSpec(unit="days", value=30),
        timeframe="1d",
    )
    assert len(folds) >= 2
    anchor = folds[0].is_start
    assert all(f.is_start == anchor for f in folds)
    # IS-end advances by step
    is_ends = [f.is_end for f in folds]
    diffs = [(b - a).days for a, b in zip(is_ends, is_ends[1:])]
    assert all(d == 30 for d in diffs)


def test_max_folds_caps_the_sequence() -> None:
    folds = plan_fold_windows(
        window_mode="rolling",
        start=_dt(2024, 1, 1),
        end=_dt(2025, 1, 1),
        is_length=LengthSpec(unit="days", value=60),
        oos_length=LengthSpec(unit="days", value=30),
        step=LengthSpec(unit="days", value=30),
        timeframe="1d",
        max_folds=3,
    )
    assert len(folds) == 3


def test_window_too_short_raises() -> None:
    with pytest.raises(WindowPlannerError):
        plan_fold_windows(
            window_mode="rolling",
            start=_dt(2024, 1, 1),
            end=_dt(2024, 2, 1),
            is_length=LengthSpec(unit="days", value=180),
            oos_length=LengthSpec(unit="days", value=30),
            step=LengthSpec(unit="days", value=30),
            timeframe="1d",
        )


def test_bars_unit_translates_to_timeframe_seconds() -> None:
    folds = plan_fold_windows(
        window_mode="rolling",
        start=_dt(2024, 1, 1),
        end=_dt(2024, 12, 31),
        is_length=LengthSpec(unit="bars", value=100),
        oos_length=LengthSpec(unit="bars", value=20),
        step=LengthSpec(unit="bars", value=20),
        timeframe="1d",
    )
    assert len(folds) > 0
    # 1d timeframe ⇒ 100 bars ≈ 100 days
    delta_days = (folds[0].is_end - folds[0].is_start).days
    assert delta_days == 100
