from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.features import (
    FeatureAvailability,
    FeaturePlan,
    IncrementalFeatureEngine,
    NormalizedBar,
    UnsupportedBatchFeatureError,
    make_feature_key,
    parse_feature_expression,
    registry,
)


def _bars(values: list[float], *, field: str = "close") -> list[NormalizedBar]:
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
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


def _bars_full(
    *,
    closes: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> list[NormalizedBar]:
    """Build OHLCV bars where every field is explicitly set per index."""
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    bars: list[NormalizedBar] = []
    for index, close in enumerate(closes):
        high = highs[index] if highs is not None else close + 1.0
        low = lows[index] if lows is not None else close - 1.0
        volume = volumes[index] if volumes is not None else 1_000.0
        bars.append(
            NormalizedBar(
                symbol="spy",
                timeframe="5m",
                timestamp=start + timedelta(minutes=5 * index),
                open=close,
                high=high,
                low=low,
                close=close,
                volume=volume,
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
    return IncrementalFeatureEngine().compute(plan, bars).frame_for("SPY", "5m").snapshots


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


def test_session_namespace_feature_rejected_by_engine() -> None:
    """Session-scope features still cannot be computed by the unified engine —
    the canonical batch/incremental engine only handles SYMBOL-scoped price /
    technical features. RSI / ATR / VWAP are now supported (Slice 2); session
    + portfolio features remain out of scope."""
    plan = _plan("5m.prior_day_high[0]")

    with pytest.raises(UnsupportedBatchFeatureError):
        IncrementalFeatureEngine().compute(plan, _bars([1, 2, 3, 4], field="close"))


def test_sma_has_no_lookahead_behavior() -> None:
    plan = _plan("5m.sma:length=2[0]")
    key = plan.feature_keys[0]
    snapshots = _snapshots(plan, _bars([1, 1, 100], field="close"))

    assert snapshots[1].value_for(key) == pytest.approx(1.0)
    assert snapshots[2].value_for(key) == pytest.approx(50.5)


# ---------------------------------------------------------------------------
# Slice 2 — canonical RSI / ATR / VWAP values + parity-vs-fixture tests
# ---------------------------------------------------------------------------


def test_rsi_canonical_values_against_wilder_smoothing() -> None:
    """RSI(length=3) on a hand-rolled close series. The first 3*length-1 bars
    are WARMUP per the registry's `length_warmup`; the last bar is the first
    AVAILABLE bar and its value is derived analytically below."""
    plan = _plan("5m.rsi:length=3[0]")
    key = plan.feature_keys[0]
    closes = [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0]
    snapshots = _snapshots(plan, _bars_full(closes=closes))

    # Bars 0..7 are WARMUP (length=3 → 3*length = 9 bars warmup window).
    for index in range(8):
        assert snapshots[index].availability_for(key) == FeatureAvailability.WARMUP
        assert snapshots[index].value_for(key) is None

    # Close-to-close changes are gain=2, loss=1, gain=2, loss=1, ... (8 total).
    # Initial avg at change=3: avg_gain=4/3, avg_loss=1/3.
    # After 5 more Wilder steps the running averages reach
    #   avg_gain = 596/729 ; avg_loss = 431/729
    # → RSI = 100 * 596 / (596 + 431) = 59_600 / 1_027.
    assert snapshots[8].availability_for(key) == FeatureAvailability.AVAILABLE
    assert snapshots[8].value_for(key) == pytest.approx(59_600 / 1_027)


def test_rsi_all_gains_returns_one_hundred() -> None:
    plan = _plan("5m.rsi:length=3[0]")
    key = plan.feature_keys[0]
    snapshots = _snapshots(plan, _bars_full(closes=[float(i) for i in range(1, 11)]))

    # When avg_loss == 0, RSI is exactly 100 — division-by-zero guard.
    assert snapshots[-1].availability_for(key) == FeatureAvailability.AVAILABLE
    assert snapshots[-1].value_for(key) == pytest.approx(100.0)


def test_atr_canonical_values_against_wilder_smoothing() -> None:
    """ATR(length=3) with hand-rolled high/low/close series. TR alternates
    between gap-driven and intra-bar values; the AVAILABLE-boundary value at
    index 8 is the analytical Wilder result over 9 true-range observations."""
    plan = _plan("5m.atr:length=3[0]")
    key = plan.feature_keys[0]
    closes = [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0]
    highs = [11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0]
    lows = [9.0, 11.0, 10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0]
    snapshots = _snapshots(plan, _bars_full(closes=closes, highs=highs, lows=lows))

    # TR series: i=0 uses high-low=2; i>=1 uses max(h-l, |h-c_prev|, |l-c_prev|)
    # which alternates 3, 2, 3, 2, 3, 2, 3, 2 over the rest of the bars.
    for index in range(8):
        assert snapshots[index].availability_for(key) == FeatureAvailability.WARMUP
        assert snapshots[index].value_for(key) is None

    # Initial avg at i=2: (2+3+2)/3 = 7/3. Six Wilder smoothing steps later
    # the running ATR reaches 5_236/2_187 at the warmup boundary.
    assert snapshots[8].availability_for(key) == FeatureAvailability.AVAILABLE
    assert snapshots[8].value_for(key) == pytest.approx(5_236 / 2_187)


def test_vwap_canonical_values_within_session() -> None:
    """VWAP(session=regular) accumulates typical_price * volume / volume across
    bars sharing the same NYSE session date, then resets at the next session."""
    plan = _plan("5m.vwap:session=regular[0]")
    key = plan.feature_keys[0]
    # Three bars on 2026-01-05 (Monday); all in regular hours (14:30..14:40 UTC
    # = 09:30..09:40 EST). Typical = (h+l+c)/3.
    closes = [100.0, 101.0, 102.0]
    highs = [101.0, 102.0, 103.0]
    lows = [99.0, 100.0, 101.0]
    volumes = [1_000.0, 2_000.0, 3_000.0]
    snapshots = _snapshots(
        plan, _bars_full(closes=closes, highs=highs, lows=lows, volumes=volumes)
    )

    # Bar 0: typical=100, vwap = 100*1000/1000 = 100.
    assert snapshots[0].value_for(key) == pytest.approx(100.0)
    # Bar 1: typical=101, cum_pv = 100_000 + 202_000 = 302_000; cum_v = 3_000.
    assert snapshots[1].value_for(key) == pytest.approx(302_000 / 3_000)
    # Bar 2: typical=102, cum_pv = 302_000 + 306_000 = 608_000; cum_v = 6_000.
    assert snapshots[2].value_for(key) == pytest.approx(608_000 / 6_000)


def test_vwap_resets_across_session_boundary() -> None:
    """VWAP cumulative sums reset when bars cross into a new ET session date."""
    plan = _plan("5m.vwap:session=regular[0]")
    key = plan.feature_keys[0]
    # Two bars on Mon Jan 5 ; one bar on Tue Jan 6 (next ET session).
    bars = [
        NormalizedBar(
            symbol="spy",
            timeframe="5m",
            timestamp=datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1_000.0,
        ),
        NormalizedBar(
            symbol="spy",
            timeframe="5m",
            timestamp=datetime(2026, 1, 5, 14, 35, tzinfo=timezone.utc),
            open=101.0,
            high=102.0,
            low=100.0,
            close=101.0,
            volume=1_000.0,
        ),
        NormalizedBar(
            symbol="spy",
            timeframe="5m",
            timestamp=datetime(2026, 1, 6, 14, 30, tzinfo=timezone.utc),
            open=200.0,
            high=201.0,
            low=199.0,
            close=200.0,
            volume=500.0,
        ),
    ]
    snapshots = _snapshots(plan, bars)

    # Bar 2 is on a new session day → cumulative resets, vwap = typical(200).
    assert snapshots[2].value_for(key) == pytest.approx(200.0)


def test_compute_helper_matches_incremental_update_for_all_supported_kinds() -> None:
    """`IncrementalFeatureEngine.compute()` is the bulk-replay convenience that
    drives `.update()` per bar; the two paths MUST produce identical snapshots."""
    from backend.app.features import FeatureCache

    plan = _plan(
        "5m.close[0]",
        "5m.sma:length=3[0]",
        "5m.ema:length=3[0]",
        "5m.rsi:length=3[0]",
        "5m.atr:length=3[0]",
        "5m.vwap:session=regular[0]",
        "5m.highest:length=3,source=high[0]",
        "5m.lowest:length=3,source=low[0]",
    )
    closes = [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0]
    highs = [11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0]
    lows = [9.0, 11.0, 10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0]
    volumes = [1_000.0 + index for index in range(len(closes))]
    bars = _bars_full(closes=closes, highs=highs, lows=lows, volumes=volumes)

    compute_snapshots = IncrementalFeatureEngine().compute(plan, bars).frame_for("SPY", "5m").snapshots

    cache = FeatureCache()
    engine = IncrementalFeatureEngine()
    incremental_snapshots = [
        engine.update(plan=plan, bar=bar, cache=cache).snapshot for bar in bars
    ]

    assert len(compute_snapshots) == len(incremental_snapshots)
    for computed, incremental in zip(compute_snapshots, incremental_snapshots, strict=True):
        assert computed.values == incremental.values
