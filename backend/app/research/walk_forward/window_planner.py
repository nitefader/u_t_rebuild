"""Generate IS/OOS fold windows for walk-forward analysis.

Two modes:
- **rolling**: IS window slides forward each fold (both IS-start and IS-end
  advance by ``step``). Closer to "what would I have known the day I tuned?"
  in a non-stationary regime.
- **anchored**: IS window grows (anchor stays at ``start``); only IS-end +
  OOS advance. Useful when more history is uniformly informative.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal


WindowMode = Literal["rolling", "anchored"]
LengthUnit = Literal["bars", "days"]


class WindowPlannerError(ValueError):
    """Raised when the requested window configuration cannot generate any folds."""


@dataclass(frozen=True)
class LengthSpec:
    unit: LengthUnit
    value: int


@dataclass(frozen=True)
class FoldWindow:
    fold_index: int
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime


def _length_to_timedelta(spec: LengthSpec, *, bar_seconds: int) -> timedelta:
    if spec.value <= 0:
        raise WindowPlannerError(f"length must be > 0; got {spec.value}")
    if spec.unit == "days":
        return timedelta(days=spec.value)
    if spec.unit == "bars":
        return timedelta(seconds=bar_seconds * spec.value)
    raise WindowPlannerError(f"unsupported length unit '{spec.unit}'")


def _timeframe_seconds(timeframe: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 5 * 60,
        "15m": 15 * 60,
        "30m": 30 * 60,
        "1h": 60 * 60,
        "4h": 4 * 60 * 60,
        "1d": 24 * 60 * 60,
        "1w": 7 * 24 * 60 * 60,
    }
    return mapping.get(timeframe, 24 * 60 * 60)


def plan_fold_windows(
    *,
    window_mode: WindowMode,
    start: datetime,
    end: datetime,
    is_length: LengthSpec,
    oos_length: LengthSpec,
    step: LengthSpec,
    timeframe: str = "1d",
    max_folds: int | None = None,
) -> tuple[FoldWindow, ...]:
    """Return the (is_start, is_end, oos_start, oos_end) tuples for each fold.

    The fold sequence stops as soon as the next OOS window would extend past
    ``end``. ``max_folds`` caps the result; ``None`` means no cap.
    """
    if start >= end:
        raise WindowPlannerError("start must be before end")
    bar_seconds = _timeframe_seconds(timeframe)
    is_delta = _length_to_timedelta(is_length, bar_seconds=bar_seconds)
    oos_delta = _length_to_timedelta(oos_length, bar_seconds=bar_seconds)
    step_delta = _length_to_timedelta(step, bar_seconds=bar_seconds)
    if is_delta + oos_delta > end - start:
        raise WindowPlannerError(
            "is_length + oos_length must fit inside [start, end]"
        )

    folds: list[FoldWindow] = []
    fold_index = 0
    is_start = start
    is_end = start + is_delta
    while is_end + oos_delta <= end:
        oos_start = is_end
        oos_end = oos_start + oos_delta
        folds.append(
            FoldWindow(
                fold_index=fold_index,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
            )
        )
        fold_index += 1
        if max_folds is not None and fold_index >= max_folds:
            break
        if window_mode == "rolling":
            is_start = is_start + step_delta
            is_end = is_end + step_delta
        elif window_mode == "anchored":
            is_end = is_end + step_delta
        else:
            raise WindowPlannerError(f"unsupported window_mode '{window_mode}'")

    if not folds:
        raise WindowPlannerError(
            "no folds generated; check start/end/is_length/oos_length/step"
        )
    return tuple(folds)
