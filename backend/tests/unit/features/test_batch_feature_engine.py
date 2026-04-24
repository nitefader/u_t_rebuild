from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.features import (
    BatchFeatureEngine,
    FeatureAvailability,
    FeaturePlan,
    NormalizedBar,
    UnsupportedBatchFeatureError,
    make_feature_key,
    parse_feature_expression,
    registry,
)


def _bars(values: list[float], *, field: str = "close") -> list[NormalizedBar]:
    start = datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc)
    bars: list[NormalizedBar] = []
    for index, value in enumerate(values):
        payload = {
            "open": 10.0 + index,
            "high": 12.0 + index,
            "low": 9.0 + index,
            "close": 11.0 + index,
            "volume": 1000.0 + index,
        }
        payload[field] = value
        bars.append(
            NormalizedBar(
                symbol="spy",
                timeframe="5m",
                timestamp=start + timedelta(minutes=5 * index),
                **payload,
            )
        )
    return bars


def _plan(*expressions: str) -> FeaturePlan:
    parsed = tuple(parse_feature_expression(expr) for expr in expressions)
    keys = tuple(sorted(make_feature_key(spec) for spec in parsed))
    spec_by_key = {make_feature_key(spec): spec for spec in parsed}
    return FeaturePlan(
        program_version_id=uuid4(),
        consumer="backtest",
        symbols=("SPY",),
        timeframes=tuple(sorted({spec.timeframe for spec in parsed})),
        feature_specs=tuple(spec_by_key[key] for key in keys),
        feature_keys=keys,
        warmup_by_timeframe={"5m": 0},
    )


def _snapshots(plan: FeaturePlan, bars: list[NormalizedBar]):
    return BatchFeatureEngine().compute(plan, bars).frame_for("SPY", "5m").snapshots


def test_batch_passthrough_features() -> None:
    plan = _plan("5m.open[0]", "5m.high[0]", "5m.low[0]", "5m.close[0]", "5m.volume[0]")
    bars = _bars([100, 101], field="close")
    snapshots = _snapshots(plan, bars)

    values = {key: snapshots[0].values[key].value for key in snapshots[0].values}
    assert 10.0 in values.values()
    assert 12.0 in values.values()
    assert 9.0 in values.values()
    assert 100.0 in values.values()
    assert 1000.0 in values.values()


def test_sma_correctness() -> None:
    plan = _plan("5m.sma:length=3[0]")
    key = plan.feature_keys[0]
    snapshots = _snapshots(plan, _bars([1, 2, 3, 4, 5], field="close"))

    assert snapshots[0].availability_for(key) == FeatureAvailability.WARMUP
    assert snapshots[1].availability_for(key) == FeatureAvailability.WARMUP
    assert snapshots[2].value_for(key) == pytest.approx(2.0)
    assert snapshots[4].value_for(key) == pytest.approx(4.0)


def test_ema_deterministic_output() -> None:
    plan = _plan("5m.ema:length=3[0]")
    key = plan.feature_keys[0]
    snapshots = _snapshots(plan, _bars([1, 2, 3, 4, 5, 6, 7, 8, 9], field="close"))

    assert snapshots[-1].availability_for(key) == FeatureAvailability.AVAILABLE
    assert snapshots[-1].value_for(key) == pytest.approx(8.00390625)


def test_highest_lowest_correctness() -> None:
    plan = _plan("5m.highest:length=3,source=high[0]", "5m.lowest:length=3,source=low[0]")
    snapshots = _snapshots(plan, _bars([1, 7, 3, 5], field="high"))
    highest_key = next(key for key in plan.feature_keys if "technical.highest" in key)
    lowest_key = next(key for key in plan.feature_keys if "technical.lowest" in key)

    assert snapshots[2].value_for(highest_key) == pytest.approx(7.0)
    assert snapshots[3].value_for(highest_key) == pytest.approx(7.0)
    assert snapshots[2].value_for(lowest_key) == pytest.approx(9.0)


def test_unsupported_feature_fails() -> None:
    plan = _plan("5m.rsi:length=14[0]")

    with pytest.raises(UnsupportedBatchFeatureError):
        BatchFeatureEngine().compute(plan, _bars([1, 2, 3, 4], field="close"))


def test_sma_has_no_lookahead_behavior() -> None:
    plan = _plan("5m.sma:length=2[0]")
    key = plan.feature_keys[0]
    snapshots = _snapshots(plan, _bars([1, 1, 100], field="close"))

    assert snapshots[1].value_for(key) == pytest.approx(1.0)
    assert snapshots[2].value_for(key) == pytest.approx(50.5)
