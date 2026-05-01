"""Tests for the mirror_long_to_short function."""
from __future__ import annotations

import pytest

from backend.app.strategies.expression_engine.mirror import mirror_long_to_short


# ---------------------------------------------------------------------------
# Operator inversions
# ---------------------------------------------------------------------------

def test_gt_inverted_to_lt():
    result = mirror_long_to_short("5m.close > 5m.ema(20)")
    assert "5m.close < 5m.ema(20)" in result
    assert ">" not in result.split("//")[1] if "//" in result else ">" not in result.split("\n", 1)[1]


def test_lt_inverted_to_gt():
    result = mirror_long_to_short("5m.close < 5m.ema(20)")
    assert "<" not in _body(result) or ">" in _body(result)
    # More precise: the body should have > not <
    body = _body(result)
    # Allow for comparison: close > ema
    assert "close > 5m . ema ( 20 )" in body.replace("  ", " ") or "close > 5m.ema" in body or "> 5m" in body


def test_crosses_above_inverted():
    result = mirror_long_to_short("5m.ema(9) crosses_above 5m.ema(21)")
    body = _body(result)
    assert "crosses_below" in body
    assert "crosses_above" not in body


def test_crosses_below_inverted():
    result = mirror_long_to_short("5m.ema(9) crosses_below 5m.ema(21)")
    body = _body(result)
    assert "crosses_above" in body
    assert "crosses_below" not in body


def test_bb_lower_swapped_to_bb_upper():
    result = mirror_long_to_short("5m.close < 5m.bb_lower(20, 2)")
    body = _body(result)
    assert "bb_upper" in body
    assert "bb_lower" not in body


def test_bb_upper_swapped_to_bb_lower():
    result = mirror_long_to_short("5m.close > 5m.bb_upper(20, 2)")
    body = _body(result)
    assert "bb_lower" in body
    assert "bb_upper" not in body


def test_donchian_high_swapped():
    result = mirror_long_to_short("5m.close > 5m.donchian_high(20)")
    body = _body(result)
    assert "donchian_low" in body
    assert "donchian_high" not in body


def test_donchian_low_swapped():
    result = mirror_long_to_short("5m.close < 5m.donchian_low(20)")
    body = _body(result)
    assert "donchian_high" in body
    assert "donchian_low" not in body


def test_kc_lower_swapped():
    result = mirror_long_to_short("5m.close < 5m.kc_lower(20, 2)")
    body = _body(result)
    assert "kc_upper" in body
    assert "kc_lower" not in body


def test_orb_high_swapped():
    result = mirror_long_to_short("5m.close > orb.high(15)")
    body = _body(result)
    assert "orb" in body
    assert "low" in body
    assert "high" not in body


def test_orb_low_swapped():
    result = mirror_long_to_short("5m.close < orb.low(15)")
    body = _body(result)
    assert "orb" in body
    assert "high" in body
    assert "low" not in body


def test_prior_day_high_swapped():
    result = mirror_long_to_short("5m.close > prior_day.high")
    body = _body(result)
    assert "prior_day" in body
    assert "low" in body
    assert "high" not in body


def test_prior_day_low_swapped():
    result = mirror_long_to_short("5m.close < prior_day.low")
    body = _body(result)
    assert "prior_day" in body
    assert "high" in body
    assert "low" not in body


# ---------------------------------------------------------------------------
# Operators that are NOT inverted
# ---------------------------------------------------------------------------

def test_eq_not_inverted():
    result = mirror_long_to_short("5m.close == 100")
    body = _body(result)
    assert "==" in body


def test_ne_not_inverted():
    result = mirror_long_to_short("5m.close != 100")
    body = _body(result)
    assert "!=" in body


def test_and_not_inverted():
    result = mirror_long_to_short("5m.close > 100 AND 5m.rsi(14) < 70")
    body = _body(result)
    assert "AND" in body


def test_or_not_inverted():
    result = mirror_long_to_short("5m.close > 100 OR 5m.rsi(14) < 70")
    body = _body(result)
    assert "OR" in body


def test_not_not_inverted():
    result = mirror_long_to_short("NOT session.is_power_hour")
    body = _body(result)
    assert "NOT" in body


def test_math_ops_not_inverted():
    result = mirror_long_to_short("5m.volume > 1.5 * 5m.volume_sma(20)")
    body = _body(result)
    assert "*" in body


# ---------------------------------------------------------------------------
# Header comment handling
# ---------------------------------------------------------------------------

def test_header_added_when_missing():
    result = mirror_long_to_short("5m.close > 100")
    assert result.startswith("// Auto-mirrored from long entry")


def test_header_replaced_when_present():
    src = "// Original comment\n5m.close > 100"
    result = mirror_long_to_short(src)
    assert "Original comment" not in result
    assert result.startswith("// Auto-mirrored from long entry")


def test_header_replaced_when_already_mirrored():
    src = "// Auto-mirrored from long entry — review and adjust\n5m.close > 100"
    # Mirror twice → still has exactly one header
    result = mirror_long_to_short(src)
    lines = result.split("\n")
    header_lines = [l for l in lines if l.startswith("//")]
    assert len(header_lines) == 1


def test_header_exact_text():
    result = mirror_long_to_short("5m.close > 100")
    first_line = result.split("\n")[0]
    assert first_line == "// Auto-mirrored from long entry — review and adjust"


# ---------------------------------------------------------------------------
# Round-trip invertibility (double mirror = original)
# ---------------------------------------------------------------------------

def test_double_mirror_gt():
    src = "5m.close > 5m.ema(20)"
    once = _body(mirror_long_to_short(src))
    twice = _body(mirror_long_to_short("dummy_header_line\n" + once))
    # After two inversions, operators should be back to original
    assert ">" in twice


def test_double_mirror_crosses():
    src = "5m.ema(9) crosses_above 5m.ema(21)"
    once = mirror_long_to_short(src)
    twice = mirror_long_to_short(once)
    body = _body(twice)
    assert "crosses_above" in body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body(mirrored: str) -> str:
    """Return everything after the header comment line."""
    lines = mirrored.split("\n")
    non_comment = [l for l in lines if not l.strip().startswith("//")]
    return "\n".join(non_comment)
