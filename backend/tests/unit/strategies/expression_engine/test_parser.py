"""Tests for the expression engine recursive-descent parser."""
from __future__ import annotations

import pytest

from backend.app.strategies.expression_engine.ast_nodes import (
    BinaryOp,
    BoolLit,
    FeatureRef,
    FunctionCall,
    NumberLit,
    TimeframedFeature,
    TimeframeVarFeature,
    UnaryOp,
    VariableRef,
)
from backend.app.strategies.expression_engine.errors import ParseError
from backend.app.strategies.expression_engine.parser import parse


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

def test_parse_integer():
    node = parse("42")
    assert node == NumberLit(42.0)


def test_parse_float():
    node = parse("3.14")
    assert isinstance(node, NumberLit)
    assert abs(node.value - 3.14) < 1e-9


def test_parse_true():
    assert parse("true") == BoolLit(True)


def test_parse_false():
    assert parse("false") == BoolLit(False)


# ---------------------------------------------------------------------------
# Timeframed features
# ---------------------------------------------------------------------------

def test_timeframed_no_args():
    node = parse("5m.volume")
    assert isinstance(node, TimeframedFeature)
    assert node.timeframe == "5m"
    assert node.name == "volume"
    assert node.args == ()


def test_timeframed_one_arg():
    node = parse("5m.ema(9)")
    assert isinstance(node, TimeframedFeature)
    assert node.timeframe == "5m"
    assert node.name == "ema"
    assert node.args == (NumberLit(9.0),)


def test_timeframed_two_args():
    node = parse("5m.bb_upper(20, 2)")
    assert isinstance(node, TimeframedFeature)
    assert node.name == "bb_upper"
    assert len(node.args) == 2


def test_timeframed_three_args():
    node = parse("5m.macd_line(12,26,9)")
    assert isinstance(node, TimeframedFeature)
    assert node.name == "macd_line"
    assert len(node.args) == 3


def test_timeframe_1d():
    node = parse("1d.rsi(2)")
    assert isinstance(node, TimeframedFeature)
    assert node.timeframe == "1d"


def test_timeframe_1h():
    node = parse("1h.ema(20)")
    assert isinstance(node, TimeframedFeature)
    assert node.timeframe == "1h"


# ---------------------------------------------------------------------------
# Non-timeframed feature refs
# ---------------------------------------------------------------------------

def test_session_is_open():
    node = parse("session.is_open")
    assert isinstance(node, FeatureRef)
    assert node.path == ("session", "is_open")
    assert node.args == ()


def test_session_minutes_since_open():
    node = parse("session.minutes_since_open")
    assert isinstance(node, FeatureRef)
    assert node.path == ("session", "minutes_since_open")


def test_orb_high_with_arg():
    node = parse("orb.high(15)")
    assert isinstance(node, FeatureRef)
    assert node.path == ("orb", "high")
    assert node.args == (NumberLit(15.0),)


def test_prior_day_close():
    node = parse("prior_day.close")
    assert isinstance(node, FeatureRef)
    assert node.path == ("prior_day", "close")


# ---------------------------------------------------------------------------
# Bar lookback
# ---------------------------------------------------------------------------

def test_bar_negative_offset():
    node = parse("bar[-1].close")
    assert isinstance(node, FeatureRef)
    assert node.bar_offset == -1
    assert node.bar_field == "close"
    assert node.path == ("bar",)


def test_bar_negative_offset_3():
    node = parse("bar[-3].high")
    assert isinstance(node, FeatureRef)
    assert node.bar_offset == -3
    assert node.bar_field == "high"


def test_bar_invalid_field_raises():
    with pytest.raises(ParseError):
        parse("bar[-1].volume")   # volume is not a bar field


# ---------------------------------------------------------------------------
# Operators and precedence
# ---------------------------------------------------------------------------

def test_comparison_gt():
    node = parse("5m.close > 100")
    assert isinstance(node, BinaryOp)
    assert node.op == ">"


def test_comparison_lt():
    node = parse("5m.rsi(14) < 70")
    assert isinstance(node, BinaryOp)
    assert node.op == "<"


def test_comparison_gte():
    node = parse("5m.close >= 5m.ema(20)")
    assert isinstance(node, BinaryOp)
    assert node.op == ">="


def test_comparison_lte():
    node = parse("5m.close <= 5m.ema(20)")
    assert isinstance(node, BinaryOp)
    assert node.op == "<="


def test_comparison_eq():
    node = parse("5m.close == 5m.ema(20)")
    assert isinstance(node, BinaryOp)
    assert node.op == "=="


def test_comparison_ne():
    node = parse("5m.close != 5m.ema(20)")
    assert isinstance(node, BinaryOp)
    assert node.op == "!="


def test_crosses_above():
    node = parse("5m.ema(9) crosses_above 5m.ema(21)")
    assert isinstance(node, BinaryOp)
    assert node.op == "crosses_above"


def test_crosses_below():
    node = parse("5m.ema(9) crosses_below 5m.ema(21)")
    assert isinstance(node, BinaryOp)
    assert node.op == "crosses_below"


def test_arithmetic_add():
    node = parse("5m.close + 1")
    assert isinstance(node, BinaryOp)
    assert node.op == "+"


def test_arithmetic_mul():
    node = parse("1.5 * 5m.volume_sma(20)")
    assert isinstance(node, BinaryOp)
    assert node.op == "*"
    assert isinstance(node.left, NumberLit)


def test_arithmetic_div():
    node = parse("(5m.close - 5m.ema(20)) / 5m.atr(14)")
    assert isinstance(node, BinaryOp)
    assert node.op == "/"


# Operator precedence: * binds tighter than +
def test_precedence_mul_over_add():
    # 1 + 2 * 3 should parse as 1 + (2 * 3)
    node = parse("1 + 2 * 3")
    assert isinstance(node, BinaryOp)
    assert node.op == "+"
    assert isinstance(node.right, BinaryOp)
    assert node.right.op == "*"


def test_precedence_add_over_comparison():
    # a > b + 1 should parse as a > (b + 1)
    node = parse("5m.close > 5m.ema(20) + 1")
    assert isinstance(node, BinaryOp)
    assert node.op == ">"
    assert isinstance(node.right, BinaryOp)
    assert node.right.op == "+"


def test_precedence_comparison_over_and():
    # A > B AND C < D should parse as (A > B) AND (C < D)
    node = parse("5m.close > 100 AND 5m.rsi(14) < 70")
    assert isinstance(node, BinaryOp)
    assert node.op == "AND"
    assert isinstance(node.left, BinaryOp)
    assert node.left.op == ">"
    assert isinstance(node.right, BinaryOp)
    assert node.right.op == "<"


def test_precedence_and_over_or():
    # A OR B AND C → A OR (B AND C)
    node = parse("true OR false AND true")
    assert isinstance(node, BinaryOp)
    assert node.op == "OR"
    assert isinstance(node.right, BinaryOp)
    assert node.right.op == "AND"


# ---------------------------------------------------------------------------
# Unary NOT and negation
# ---------------------------------------------------------------------------

def test_unary_not():
    node = parse("NOT session.is_open")
    assert isinstance(node, UnaryOp)
    assert node.op == "NOT"


def test_unary_not_nested():
    node = parse("NOT NOT true")
    assert isinstance(node, UnaryOp)
    assert isinstance(node.operand, UnaryOp)


def test_unary_minus():
    node = parse("-5")
    assert isinstance(node, UnaryOp)
    assert node.op == "-"
    assert node.operand == NumberLit(5.0)


def test_not_does_not_bind_comparison():
    # NOT A > B should be NOT (A > B)
    node = parse("NOT 5m.rsi(14) > 70")
    assert isinstance(node, UnaryOp)
    assert node.op == "NOT"
    assert isinstance(node.operand, BinaryOp)
    assert node.operand.op == ">"


# ---------------------------------------------------------------------------
# Parentheses
# ---------------------------------------------------------------------------

def test_parens_override_precedence():
    # (1 + 2) * 3 should parse as ((1+2) * 3)
    node = parse("(1 + 2) * 3")
    assert isinstance(node, BinaryOp)
    assert node.op == "*"
    assert isinstance(node.left, BinaryOp)
    assert node.left.op == "+"


def test_parens_complex():
    node = parse("(5m.close - 5m.ema(20)) / 5m.atr(14) > 0.5")
    assert isinstance(node, BinaryOp)
    assert node.op == ">"
    assert isinstance(node.left, BinaryOp)
    assert node.left.op == "/"


# ---------------------------------------------------------------------------
# AND / OR chains
# ---------------------------------------------------------------------------

def test_and_chain():
    node = parse("true AND false AND true")
    # Should be left-associative: (true AND false) AND true
    assert isinstance(node, BinaryOp)
    assert node.op == "AND"
    assert isinstance(node.left, BinaryOp)
    assert node.left.op == "AND"


def test_or_chain():
    node = parse("true OR false OR true")
    assert isinstance(node, BinaryOp)
    assert node.op == "OR"


# ---------------------------------------------------------------------------
# Variable references
# ---------------------------------------------------------------------------

def test_variable_ref():
    node = parse("short_ema")
    assert isinstance(node, VariableRef)
    assert node.name == "short_ema"


def test_variable_in_expression():
    node = parse("short_ema crosses_above long_ema")
    assert isinstance(node, BinaryOp)
    assert isinstance(node.left, VariableRef)
    assert isinstance(node.right, VariableRef)


# ---------------------------------------------------------------------------
# Keyword functions
# ---------------------------------------------------------------------------

def test_within_function():
    node = parse("within(5m.rsi(14), 30, 70)")
    assert isinstance(node, FunctionCall)
    assert node.name == "within"
    assert len(node.args) == 3


def test_any_of_function():
    node = parse("any_of(true, false, true)")
    assert isinstance(node, FunctionCall)
    assert node.name == "any_of"


def test_all_of_function():
    node = parse("all_of(true, true)")
    assert isinstance(node, FunctionCall)
    assert node.name == "all_of"


# ---------------------------------------------------------------------------
# ParseError cases
# ---------------------------------------------------------------------------

def test_parse_error_on_unclosed_paren():
    with pytest.raises(ParseError) as exc_info:
        parse("5m.ema(9")
    err = exc_info.value
    assert err.line >= 1
    assert err.col >= 1


def test_parse_error_on_trailing_token():
    with pytest.raises(ParseError) as exc_info:
        parse("5m.ema(9) 5m.rsi(14)")
    err = exc_info.value
    assert err.line >= 1


def test_parse_error_on_missing_operand():
    with pytest.raises(ParseError):
        parse("5m.ema(9) >")


def test_parse_error_carries_position():
    with pytest.raises(ParseError) as exc_info:
        parse("5m.ema(9) crosses_above")
    # crosses_above with no RHS
    err = exc_info.value
    assert err.line >= 1
    assert err.col >= 1


def test_parse_error_empty_parens_in_function():
    # f() with no args is fine for zero-arity features
    # But a bare () expression should fail
    with pytest.raises(ParseError):
        parse("()")


def test_parse_timeframe_variable_prefix():
    node = parse("sig_tf.ema(9)", timeframe_variable_names=frozenset({"sig_tf"}))
    assert isinstance(node, TimeframeVarFeature)
    assert node.timeframe_variable == "sig_tf"
    assert node.name == "ema"
    assert len(node.args) == 1


def test_parse_unknown_timeframe_variable_parsed_as_ident_chain():
    node = parse("sig_tf.ema(9)")
    assert isinstance(node, FeatureRef)


def test_parse_timeframe_var_volume_zero_arg():
    node = parse("sig_tf.volume", timeframe_variable_names=frozenset({"sig_tf"}))
    assert isinstance(node, TimeframeVarFeature)
