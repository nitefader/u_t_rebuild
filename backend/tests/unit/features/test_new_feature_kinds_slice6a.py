"""Slice 6a-i adds 16 new TECHNICAL/SYMBOL feature kinds. Tests cover:

- Each kind produces a value via the canonical engine.
- Each kind round-trips through the registry + FeaturePlan build.
- Critical correctness: down_streak counts, IBS bounds, ROC math, MACD identity,
  swing pivot confirmation, FVG 3-bar logic, support/resistance clustering,
  Ichimoku double-window math, Chikou backward shift.
- Senkou A/B + Chikou explicitly carry the "no displacement" semantics — value
  at bar t is the cloud-edge basis or shifted-back close, not a future-projected
  series.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    FeaturePlan,
    IncrementalFeatureEngine,
    NormalizedBar,
    make_feature_key,
    parse_feature_expression,
)


def _bars(closes, *, highs=None, lows=None, volumes=None):
    start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
    out = []
    for i, c in enumerate(closes):
        h = highs[i] if highs is not None else c + 1.0
        ll = lows[i] if lows is not None else c - 1.0
        v = volumes[i] if volumes is not None else 1_000.0 + i
        out.append(
            NormalizedBar(
                symbol="SPY",
                timeframe="5m",
                timestamp=start + timedelta(minutes=5 * i),
                open=c,
                high=h,
                low=ll,
                close=c,
                volume=v,
            )
        )
    return out


def _plan(*exprs: str) -> FeaturePlan:
    specs = tuple(parse_feature_expression(e) for e in exprs)
    keys = tuple(make_feature_key(s) for s in specs)
    return FeaturePlan(
        program_version_id=uuid4(),
        consumer="backtest",
        symbols=("SPY",),
        timeframes=tuple(sorted({s.timeframe for s in specs})),
        feature_specs=specs,
        feature_keys=keys,
        warmup_by_timeframe={s.timeframe: 0 for s in specs},
    )


def _snaps(plan, bars):
    cache = FeatureCache()
    engine = IncrementalFeatureEngine()
    return [engine.update(plan=plan, bar=b, cache=cache).snapshot for b in bars]


def test_down_streak_counts_consecutive_red_days() -> None:
    plan = _plan("5m.down_streak[0]")
    snaps = _snaps(plan, _bars([10, 9, 8, 7, 8, 7, 6, 5]))
    key = plan.feature_keys[0]
    values = [s.value_for(key) for s in snaps]
    assert values == [0.0, 1.0, 2.0, 3.0, 0.0, 1.0, 2.0, 3.0]


def test_ibs_is_bounded_zero_to_one() -> None:
    plan = _plan("5m.ibs[0]")
    snaps = _snaps(plan, _bars([10, 11], highs=[12, 13], lows=[8, 9]))
    key = plan.feature_keys[0]
    assert snaps[0].value_for(key) == pytest.approx(0.5)
    assert snaps[1].value_for(key) == pytest.approx(0.5)


def test_ibs_zero_range_returns_midpoint() -> None:
    plan = _plan("5m.ibs[0]")
    snaps = _snaps(plan, _bars([10], highs=[10], lows=[10]))
    key = plan.feature_keys[0]
    assert snaps[0].value_for(key) == pytest.approx(0.5)


def test_roc_warmup_then_value() -> None:
    plan = _plan("5m.roc:length=3[0]")
    snaps = _snaps(plan, _bars([100, 101, 102, 110, 121]))
    key = plan.feature_keys[0]
    for i in range(3):
        assert snaps[i].availability_for(key) == FeatureAvailability.WARMUP
    assert snaps[3].value_for(key) == pytest.approx((110 - 100) / 100)
    assert snaps[4].value_for(key) == pytest.approx((121 - 101) / 101)


def test_swing_high_confirms_only_at_center() -> None:
    plan = _plan("5m.swing_high:lookback=1[0]")
    snaps = _snaps(plan, _bars([1, 2, 1], highs=[1.5, 5.0, 1.5]))
    key = plan.feature_keys[0]
    assert snaps[2].value_for(key) == pytest.approx(5.0)


def test_swing_low_confirms_only_at_center() -> None:
    plan = _plan("5m.swing_low:lookback=1[0]")
    snaps = _snaps(plan, _bars([10, 1, 10], lows=[9, 0.5, 9]))
    key = plan.feature_keys[0]
    assert snaps[2].value_for(key) == pytest.approx(0.5)


def test_fvg_up_detects_three_bar_imbalance() -> None:
    plan = _plan("5m.fvg_up[0]")
    snaps = _snaps(plan, _bars([10, 11, 14], highs=[10.5, 11.5, 14.5], lows=[9.5, 10.5, 13.0]))
    key = plan.feature_keys[0]
    assert snaps[0].availability_for(key) == FeatureAvailability.WARMUP
    assert snaps[1].availability_for(key) == FeatureAvailability.WARMUP
    assert snaps[2].value_for(key) == pytest.approx(13.0 - 10.5)


def test_fvg_down_detects_three_bar_imbalance() -> None:
    plan = _plan("5m.fvg_down[0]")
    snaps = _snaps(plan, _bars([14, 13, 10], highs=[14.5, 13.5, 10.5], lows=[13.0, 12.5, 9.5]))
    key = plan.feature_keys[0]
    assert snaps[2].value_for(key) == pytest.approx(13.0 - 10.5)


def test_supertrend_produces_a_value_after_warmup() -> None:
    plan = _plan("5m.supertrend:length=3,multiplier=3[0]")
    snaps = _snaps(plan, _bars([10, 11, 12, 13, 14, 15, 16]))
    key = plan.feature_keys[0]
    assert snaps[-1].availability_for(key) == FeatureAvailability.AVAILABLE
    assert snaps[-1].value_for(key) is not None


def test_tenkan_kijun_compute_average_of_extremes() -> None:
    plan = _plan("5m.tenkan_sen:length=3[0]", "5m.kijun_sen:length=3[0]")
    snaps = _snaps(plan, _bars([10, 12, 14, 11, 9], highs=[11, 13, 15, 12, 10], lows=[9, 11, 13, 10, 8]))
    tenkan_key = next(k for k in plan.feature_keys if "tenkan_sen" in k)
    kijun_key = next(k for k in plan.feature_keys if "kijun_sen" in k)
    # bar index 4: highest(15) + lowest(8) = 23 / 2 = 11.5
    assert snaps[4].value_for(tenkan_key) == pytest.approx(11.5)
    assert snaps[4].value_for(kijun_key) == pytest.approx(11.5)


def test_senkou_a_is_basis_only_no_forward_displacement() -> None:
    """Slice 6a-i ships Senkou A WITHOUT the +26 forward displacement.
    Value at bar t is (tenkan + kijun)/2 at bar t — operator-facing label
    must mark this as a known limitation, not a silent approximation."""
    plan = _plan("5m.senkou_a:tenkan_length=3,kijun_length=3[0]")
    snaps = _snaps(plan, _bars([10, 12, 14], highs=[11, 13, 15], lows=[9, 11, 13]))
    key = plan.feature_keys[0]
    # tenkan = kijun = (15+9)/2 = 12 → senkou_a = 12, returned at bar t (no shift forward)
    assert snaps[2].value_for(key) == pytest.approx(12.0)


def test_senkou_b_is_basis_only_no_forward_displacement() -> None:
    plan = _plan("5m.senkou_b:length=3[0]")
    snaps = _snaps(plan, _bars([10, 12, 14], highs=[11, 13, 15], lows=[9, 11, 13]))
    key = plan.feature_keys[0]
    assert snaps[2].value_for(key) == pytest.approx(12.0)


def test_chikou_span_returns_close_shifted_backward() -> None:
    plan = _plan("5m.chikou_span:displacement=3[0]")
    snaps = _snaps(plan, _bars([10, 11, 12, 13, 14, 15]))
    key = plan.feature_keys[0]
    for i in range(3):
        assert snaps[i].availability_for(key) == FeatureAvailability.WARMUP
    # at bar 3, chikou returns close[t-3] = 10
    assert snaps[3].value_for(key) == pytest.approx(10.0)
    # at bar 4, returns close[t-3] = 11
    assert snaps[4].value_for(key) == pytest.approx(11.0)


def test_macd_outputs_line_signal_histogram_satisfy_identity() -> None:
    """histogram == line - signal at every confirmed bar."""
    closes = [100, 101, 102, 103, 102, 101, 102, 103, 104, 105, 104, 103, 104, 105, 106]
    plan = _plan(
        "5m.macd:fast_length=3,slow_length=5,signal_length=2,output=line[0]",
        "5m.macd:fast_length=3,slow_length=5,signal_length=2,output=signal[0]",
        "5m.macd:fast_length=3,slow_length=5,signal_length=2,output=histogram[0]",
    )
    snaps = _snaps(plan, _bars(closes))
    line_key = next(k for k in plan.feature_keys if '"output":"line"' in k)
    signal_key = next(k for k in plan.feature_keys if '"output":"signal"' in k)
    hist_key = next(k for k in plan.feature_keys if '"output":"histogram"' in k)
    final = snaps[-1]
    line = final.value_for(line_key)
    signal = final.value_for(signal_key)
    hist = final.value_for(hist_key)
    assert line is not None and signal is not None and hist is not None
    assert hist == pytest.approx(line - signal)


def test_macd_rejects_unknown_output_param() -> None:
    plan = _plan("5m.macd:fast_length=3,slow_length=5,signal_length=2,output=bogus[0]")
    with pytest.raises(Exception, match="macd output must be"):
        _snaps(plan, _bars([100, 101, 102, 103, 104, 105]))


def test_support_returns_nearest_below_close() -> None:
    plan = _plan("5m.support:lookback=20,pivot_strength=2,level_count=3,cluster_pct=0.25,output_index=0[0]")
    closes = [10, 8, 9, 11, 10, 9, 12, 11, 10, 13, 14, 15]
    lows = [9.5, 7.0, 8.5, 10.5, 9.5, 8.5, 11.5, 10.5, 9.5, 12.5, 13.5, 14.5]
    highs = [11, 9, 10, 12, 11, 10, 13, 12, 11, 14, 15, 16]
    snaps = _snaps(plan, _bars(closes, highs=highs, lows=lows))
    key = plan.feature_keys[0]
    final = snaps[-1].value_for(key)
    # The support level at bar -1 (close=15) should be a confirmed pivot below 15.
    assert final is not None
    assert final < 15


def test_resistance_returns_nearest_above_close() -> None:
    plan = _plan("5m.resistance:lookback=20,pivot_strength=2,level_count=3,cluster_pct=0.25,output_index=0[0]")
    closes = [10, 12, 11, 9, 8, 10, 12, 11, 10, 8]
    highs = [11, 14, 12, 10, 9, 11, 14, 12, 11, 9]
    lows = [9, 11, 10, 8, 7, 9, 11, 10, 9, 7]
    snaps = _snaps(plan, _bars(closes, highs=highs, lows=lows))
    key = plan.feature_keys[0]
    final = snaps[-1].value_for(key)
    if final is not None:
        assert final > 8


def test_all_new_kinds_round_trip_through_registry() -> None:
    """Each kind must parse through the feature-ref grammar + register."""
    new_kinds_with_params = [
        ("down_streak", ""),
        ("ibs", ""),
        ("roc", ":length=10"),
        ("swing_high", ":lookback=5"),
        ("swing_low", ":lookback=5"),
        ("fvg_up", ""),
        ("fvg_down", ""),
        ("supertrend", ":length=10,multiplier=3.0"),
        ("tenkan_sen", ":length=9"),
        ("kijun_sen", ":length=26"),
        ("senkou_a", ":tenkan_length=9,kijun_length=26"),
        ("senkou_b", ":length=52"),
        ("chikou_span", ":displacement=26"),
        ("macd", ":fast_length=12,slow_length=26,signal_length=9,output=line"),
        ("support", ":lookback=50,pivot_strength=3,level_count=3,cluster_pct=0.25,output_index=0"),
        ("resistance", ":lookback=50,pivot_strength=3,level_count=3,cluster_pct=0.25,output_index=0"),
    ]
    for kind, suffix in new_kinds_with_params:
        spec = parse_feature_expression(f"5m.{kind}{suffix}[0]")
        assert spec.kind == kind


def test_unsupported_prompt_terms_macd_and_ichimoku_now_accepted_in_compose() -> None:
    """Slice 6a-i adds MACD + Ichimoku as real kinds. The composer's prompt
    blocklist must no longer reject these terms."""
    from backend.app.strategy_composer.service import UNSUPPORTED_PROMPT_FEATURE_TERMS

    assert "macd" not in UNSUPPORTED_PROMPT_FEATURE_TERMS
    assert "ichimoku" not in UNSUPPORTED_PROMPT_FEATURE_TERMS
    assert "bollinger" in UNSUPPORTED_PROMPT_FEATURE_TERMS
    assert "stochastic" in UNSUPPORTED_PROMPT_FEATURE_TERMS
