from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.features import (
    BatchFeatureEngine,
    FeatureAvailability,
    FeatureCache,
    FeaturePlan,
    IncrementalFeatureEngine,
    IncrementalFeatureEngineError,
    NormalizedBar,
    make_feature_key,
    parse_feature_expression,
)
import backend.app.features.incremental as incremental_module


def _bar(
    index: int,
    *,
    symbol: str = "spy",
    timeframe: str = "5m",
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=5 * index),
        open=close - 1,
        high=high if high is not None else close + 1,
        low=low if low is not None else close - 1,
        close=close,
        volume=1000 + index,
    )


def _plan(*expressions: str, symbols: tuple[str, ...] = ("SPY",), timeframes: tuple[str, ...] | None = None) -> FeaturePlan:
    parsed = tuple(parse_feature_expression(expr) for expr in expressions)
    keys = tuple(sorted(make_feature_key(spec) for spec in parsed))
    spec_by_key = {make_feature_key(spec): spec for spec in parsed}
    return FeaturePlan(
        program_version_id=uuid4(),
        consumer="paper",
        symbols=symbols,
        timeframes=timeframes or tuple(sorted({spec.timeframe for spec in parsed})),
        feature_specs=tuple(spec_by_key[key] for key in keys),
        feature_keys=keys,
        warmup_by_timeframe={timeframe: 0 for timeframe in (timeframes or tuple(sorted({spec.timeframe for spec in parsed})))},
    )


def _incremental_snapshots(plan: FeaturePlan, bars: list[NormalizedBar]):
    cache = FeatureCache()
    engine = IncrementalFeatureEngine()
    snapshots = []
    for bar in bars:
        snapshots.append(engine.update(plan=plan, bar=bar, cache=cache).snapshot)
    return snapshots, cache


def test_incremental_update_equals_batch_result() -> None:
    plan = _plan(
        "5m.close[0]",
        "5m.sma:length=3[0]",
        "5m.ema:length=3[0]",
        "5m.highest:length=3,source=high[0]",
        "5m.lowest:length=3,source=low[0]",
    )
    bars = [_bar(index, close=float(index + 1), high=float(index + 3), low=float(index)) for index in range(9)]

    incremental_snapshots, _ = _incremental_snapshots(plan, bars)
    batch_snapshots = BatchFeatureEngine().compute(plan, bars).frame_for("SPY", "5m").snapshots

    assert len(incremental_snapshots) == len(batch_snapshots)
    for incremental, batch in zip(incremental_snapshots, batch_snapshots, strict=True):
        assert incremental.values == batch.values


def test_incremental_warmup_behavior_correct() -> None:
    plan = _plan("5m.sma:length=3[0]", "5m.ema:length=3[0]")
    bars = [_bar(index, close=float(index + 1)) for index in range(9)]

    snapshots, _ = _incremental_snapshots(plan, bars)
    sma_key = next(key for key in plan.feature_keys if "technical.sma" in key)
    ema_key = next(key for key in plan.feature_keys if "technical.ema" in key)

    assert snapshots[0].availability_for(sma_key) == FeatureAvailability.WARMUP
    assert snapshots[1].availability_for(sma_key) == FeatureAvailability.WARMUP
    assert snapshots[2].availability_for(sma_key) == FeatureAvailability.AVAILABLE
    assert snapshots[7].availability_for(ema_key) == FeatureAvailability.WARMUP
    assert snapshots[8].availability_for(ema_key) == FeatureAvailability.AVAILABLE


def test_incremental_multi_timeframe_alignment_holds_in_cache() -> None:
    plan = _plan(
        "1d.close[0]",
        "5m.close[0]",
        timeframes=("1d", "5m"),
    )
    cache = FeatureCache()
    engine = IncrementalFeatureEngine()
    daily = NormalizedBar(
        symbol="SPY",
        timeframe="1d",
        timestamp=datetime(2026, 1, 1, 21, 0, tzinfo=timezone.utc),
        open=100,
        high=105,
        low=95,
        close=102,
        volume=1_000_000,
    )
    intraday = NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=103,
        high=104,
        low=102,
        close=103.5,
        volume=100_000,
    )

    engine.update(plan=plan, bar=daily, cache=cache)
    engine.update(plan=plan, bar=intraday, cache=cache)
    aligned_daily = cache.latest_snapshot_at_or_before(symbol="SPY", timeframe="1d", timestamp=intraday.timestamp)

    assert aligned_daily is not None
    assert aligned_daily.timestamp == daily.timestamp
    assert next(value.value for value in aligned_daily.values.values()) == 102


def test_cache_state_persists_correctly() -> None:
    plan = _plan("5m.close[0]", "5m.sma:length=2[0]")
    bars = [_bar(0, close=10), _bar(1, close=12), _bar(2, close=14)]
    cache = FeatureCache()
    engine = IncrementalFeatureEngine()

    first = engine.update(plan=plan, bar=bars[0], cache=cache)
    second = engine.update(plan=plan, bar=bars[1], cache=cache)
    third = engine.update(plan=plan, bar=bars[2], cache=cache)
    sma_key = next(key for key in plan.feature_keys if "technical.sma" in key)

    assert cache.processed_bar_count == 3
    assert len(third.frame.snapshots) == 3
    assert first.snapshot.timestamp == bars[0].timestamp
    assert second.snapshot.value_for(sma_key) == pytest.approx(11)
    assert third.snapshot.value_for(sma_key) == pytest.approx(13)


def test_incremental_rejects_out_of_order_or_duplicate_bars() -> None:
    plan = _plan("5m.close[0]")
    cache = FeatureCache()
    engine = IncrementalFeatureEngine()
    bar = _bar(0, close=10)

    engine.update(plan=plan, bar=bar, cache=cache)

    with pytest.raises(IncrementalFeatureEngineError):
        engine.update(plan=plan, bar=bar, cache=cache)


def test_no_full_recomputation_on_new_bar() -> None:
    source = inspect.getsource(incremental_module)

    assert "BatchFeatureEngine" not in source
    assert ".compute(" not in source
