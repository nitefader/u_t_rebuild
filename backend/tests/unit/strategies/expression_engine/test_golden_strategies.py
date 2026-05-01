"""Golden strategy tests: all 20 strategies must parse, validate, compile, evaluate.

Each strategy is tested with a synthetic FeatureSnapshot that produces
a plausible evaluation result (True or False — we don't care which, only that
no exception is raised and the result is a bool or float).
"""
from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.strategies.expression_engine import (
    compile,
    default_catalog,
    evaluate,
    parse,
    validate,
)
from backend.app.strategies.expression_engine.ast_nodes import FeatureSnapshot


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run_strategy(
    src: str,
    values: dict,
    history: dict | None = None,
    variables: dict | None = None,
    var_names: list[str] | None = None,
) -> bool | float:
    """Parse → validate → compile → evaluate.  Returns the result."""
    ast = parse(src)
    vast = validate(ast, default_catalog(), variable_names=var_names or [])
    cexpr = compile(vast)
    snap = FeatureSnapshot(
        timestamp=datetime(2024, 1, 15, 10, 0),
        values=values,
        history=history or {},
        variables=variables or {},
    )
    return evaluate(cexpr, snap)


# ---------------------------------------------------------------------------
# 1. ORB breakout
# ---------------------------------------------------------------------------

def test_golden_01_orb_breakout():
    result = run_strategy(
        "5m.close > orb.high(15) AND 5m.volume > 1.5 * 5m.volume_sma(20)",
        values={
            "5m.close": 155.0,
            "orb.high(15)": 150.0,
            "5m.volume": 100_000.0,
            "5m.volume_sma(20)": 50_000.0,
        },
    )
    assert isinstance(result, bool)
    assert result is True


# ---------------------------------------------------------------------------
# 2. VWAP reclaim
# ---------------------------------------------------------------------------

def test_golden_02_vwap_reclaim():
    result = run_strategy(
        "5m.close crosses_above 5m.vwap() AND 5m.ema(9) > 5m.ema(21)",
        values={
            "5m.close": 151.0,
            "5m.vwap": 150.0,
            "5m.ema(9)": 152.0,
            "5m.ema(21)": 148.0,
        },
        history={
            "5m.close": (151.0, 149.0),   # was below vwap, now above
            "5m.vwap": (150.0, 150.0),
        },
    )
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 3. EMA crossover
# ---------------------------------------------------------------------------

def test_golden_03_ema_crossover():
    result = run_strategy(
        "5m.ema(9) crosses_above 5m.ema(21)",
        values={"5m.ema(9)": 12.0, "5m.ema(21)": 10.0},
        history={
            "5m.ema(9)": (12.0, 9.0),
            "5m.ema(21)": (10.0, 10.0),
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 4. MACD signal cross
# ---------------------------------------------------------------------------

def test_golden_04_macd_signal_cross():
    result = run_strategy(
        "5m.macd_line(12,26,9) crosses_above 5m.macd_signal(12,26,9)",
        values={
            "5m.macd_line(12,26,9)": 0.05,
            "5m.macd_signal(12,26,9)": 0.03,
        },
        history={
            "5m.macd_line(12,26,9)": (0.05, 0.02),
            "5m.macd_signal(12,26,9)": (0.03, 0.03),
        },
    )
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 5. RSI-2 mean reversion (daily)
# ---------------------------------------------------------------------------

def test_golden_05_rsi2_mean_reversion():
    result = run_strategy(
        "1d.rsi(2) < 5 AND 1d.close > 1d.sma(200)",
        values={
            "1d.rsi(2)": 3.0,
            "1d.close": 400.0,
            "1d.sma(200)": 350.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 6. Bollinger band reversal
# ---------------------------------------------------------------------------

def test_golden_06_bb_reversal():
    result = run_strategy(
        "5m.close < 5m.bb_lower(20, 2)",
        values={
            "5m.close": 140.0,
            "5m.bb_lower(20,2)": 145.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 7. BB squeeze breakout
# ---------------------------------------------------------------------------

def test_golden_07_bb_squeeze_breakout():
    result = run_strategy(
        "5m.bb_width(20, 2) < 0.5 AND 5m.close > 5m.bb_upper(20, 2)",
        values={
            "5m.bb_width(20,2)": 0.3,
            "5m.close": 155.0,
            "5m.bb_upper(20,2)": 150.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 8. Pullback to 20 EMA
# ---------------------------------------------------------------------------

def test_golden_08_pullback_to_ema20():
    result = run_strategy(
        "5m.close < 1.02 * 5m.ema(20) AND 5m.ema(20) > 5m.ema(200) AND 5m.rsi(14) > 40 AND 5m.rsi(14) < 55",
        values={
            "5m.close": 101.5,
            "5m.ema(20)": 100.0,
            "5m.ema(200)": 90.0,
            "5m.rsi(14)": 48.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 9. Gap-and-Go
# ---------------------------------------------------------------------------

def test_golden_09_gap_and_go():
    result = run_strategy(
        "5m.close > prior_day.close * 1.02 AND 5m.volume > 2 * 5m.volume_sma(20)",
        values={
            "5m.close": 110.0,
            "prior_day.close": 100.0,
            "5m.volume": 200_000.0,
            "5m.volume_sma(20)": 80_000.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 10. Supertrend + Ichimoku
# ---------------------------------------------------------------------------

def test_golden_10_supertrend_ichimoku():
    result = run_strategy(
        "5m.close > 5m.supertrend(10, 3) AND 5m.close > 5m.ichimoku_kijun()",
        values={
            "5m.close": 155.0,
            "5m.supertrend(10,3)": 148.0,
            "5m.ichimoku_kijun": 150.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 11. Donchian breakout (Turtle-lite)
# ---------------------------------------------------------------------------

def test_golden_11_donchian_breakout():
    result = run_strategy(
        "5m.close > 1d.donchian_high(20)",
        values={
            "5m.close": 155.0,
            "1d.donchian_high(20)": 150.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 12. NR7-ish (bar lookback)
# ---------------------------------------------------------------------------

def test_golden_12_nr7_bar_lookback():
    result = run_strategy(
        "5m.close > bar[-1].high AND 5m.atr(14) < bar[-1].close * 0.005",
        values={
            "5m.close": 155.0,
            "5m.atr(14)": 0.4,
        },
        history={
            "bar.high": (154.0, 152.0),    # index 0 current, index 1 = prev
            "bar.close": (154.0, 150.0),
        },
    )
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 13. CCI extreme
# ---------------------------------------------------------------------------

def test_golden_13_cci_extreme():
    result = run_strategy(
        "5m.cci(20) < -100 AND 1d.close > 1d.sma(50)",
        values={
            "5m.cci(20)": -150.0,
            "1d.close": 400.0,
            "1d.sma(50)": 380.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 14. Stoch oversold
# ---------------------------------------------------------------------------

def test_golden_14_stoch_oversold():
    result = run_strategy(
        "5m.stoch_k(14, 3) < 20 AND 5m.stoch_k(14, 3) crosses_above 5m.stoch_d(14, 3)",
        values={
            "5m.stoch_k(14,3)": 18.0,
            "5m.stoch_d(14,3)": 15.0,
        },
        history={
            "5m.stoch_k(14,3)": (18.0, 14.0),
            "5m.stoch_d(14,3)": (15.0, 15.0),
        },
    )
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 15. Williams %R bounce
# ---------------------------------------------------------------------------

def test_golden_15_williams_r_bounce():
    result = run_strategy(
        "5m.williams_r(14) < -80 AND 5m.close > bar[-1].close",
        values={
            "5m.williams_r(14)": -85.0,
            "5m.close": 151.0,
        },
        history={
            "bar.close": (151.0, 149.0),
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 16. ROC momentum
# ---------------------------------------------------------------------------

def test_golden_16_roc_momentum():
    result = run_strategy(
        "5m.roc(10) > 1.0 AND 5m.volume > 5m.volume_sma(20)",
        values={
            "5m.roc(10)": 2.5,
            "5m.volume": 60_000.0,
            "5m.volume_sma(20)": 50_000.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 17. CMF + price
# ---------------------------------------------------------------------------

def test_golden_17_cmf_price():
    result = run_strategy(
        "5m.cmf(20) > 0.1 AND 5m.close > 5m.ema(50)",
        values={
            "5m.cmf(20)": 0.25,
            "5m.close": 155.0,
            "5m.ema(50)": 148.0,
        },
    )
    assert result is True


# ---------------------------------------------------------------------------
# 18. Session-window filter
# ---------------------------------------------------------------------------

def test_golden_18_session_window():
    result = run_strategy(
        "session.is_open AND session.minutes_since_open > 30 AND NOT session.is_power_hour",
        values={
            "session.is_open": True,
            "session.minutes_since_open": 45.0,
            "session.is_power_hour": False,
        },
    )
    assert result is True


def test_golden_18_session_window_false_when_power_hour():
    result = run_strategy(
        "session.is_open AND session.minutes_since_open > 30 AND NOT session.is_power_hour",
        values={
            "session.is_open": True,
            "session.minutes_since_open": 45.0,
            "session.is_power_hour": True,
        },
    )
    assert result is False


# ---------------------------------------------------------------------------
# 19. With variables
# ---------------------------------------------------------------------------

def test_golden_19_with_variables():
    result = run_strategy(
        "short_ema crosses_above long_ema AND 5m.rsi(14) < 70",
        values={"5m.rsi(14)": 55.0},
        history={
            "short_ema": (12.0, 9.0),
            "long_ema": (10.0, 10.0),
        },
        variables={
            "short_ema": 12.0,
            "long_ema": 10.0,
        },
        var_names=["short_ema", "long_ema"],
    )
    assert result is True


# ---------------------------------------------------------------------------
# 20. Complex parens + math
# ---------------------------------------------------------------------------

def test_golden_20_complex_parens_math():
    result = run_strategy(
        "(5m.close - 5m.ema(20)) / 5m.atr(14) > 0.5 AND 5m.volume > 1.2 * 5m.volume_sma(20)",
        values={
            "5m.close": 112.0,
            "5m.ema(20)": 100.0,
            "5m.atr(14)": 2.0,
            "5m.volume": 72_000.0,
            "5m.volume_sma(20)": 50_000.0,
        },
    )
    # (112 - 100) / 2 = 6 > 0.5: True; 72000 > 60000: True → True
    assert result is True
