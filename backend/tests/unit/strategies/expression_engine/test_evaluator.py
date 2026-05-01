"""Tests for the expression engine evaluator."""
from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.strategies.expression_engine import (
    compile,
    evaluate,
    parse,
    validate,
    default_catalog,
)
from backend.app.strategies.expression_engine.ast_nodes import FeatureSnapshot
from backend.app.strategies.expression_engine.errors import EvalError


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------

def make_snapshot(
    values: dict | None = None,
    history: dict | None = None,
    variables: dict | None = None,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        timestamp=datetime(2024, 1, 1, 9, 30),
        values=values or {},
        history=history or {},
        variables=variables or {},
    )


def _eval(src: str, values=None, history=None, variables=None, var_names=()):
    ast = parse(src)
    vast = validate(ast, default_catalog(), variable_names=var_names)
    cexpr = compile(vast)
    snap = make_snapshot(values=values, history=history, variables=variables)
    return evaluate(cexpr, snap)


# ---------------------------------------------------------------------------
# Number literals / arithmetic
# ---------------------------------------------------------------------------

def test_eval_number_literal():
    ast = parse("42")
    from backend.app.strategies.expression_engine.compiler import compile_expr
    from backend.app.strategies.expression_engine.ast_nodes import ValidatedAst
    vast = ValidatedAst(root=ast, feature_requirements=(), variables_used=())
    cexpr = compile_expr(vast)
    result = evaluate(cexpr, make_snapshot())
    assert result == 42.0


def test_eval_addition():
    ast = parse("1 + 2")
    from backend.app.strategies.expression_engine.compiler import compile_expr
    from backend.app.strategies.expression_engine.ast_nodes import ValidatedAst
    vast = ValidatedAst(root=ast, feature_requirements=(), variables_used=())
    cexpr = compile_expr(vast)
    assert evaluate(cexpr, make_snapshot()) == 3.0


def test_eval_multiplication():
    ast = parse("3 * 4")
    from backend.app.strategies.expression_engine.compiler import compile_expr
    from backend.app.strategies.expression_engine.ast_nodes import ValidatedAst
    vast = ValidatedAst(root=ast, feature_requirements=(), variables_used=())
    cexpr = compile_expr(vast)
    assert evaluate(cexpr, make_snapshot()) == 12.0


def test_eval_division():
    ast = parse("10 / 4")
    from backend.app.strategies.expression_engine.compiler import compile_expr
    from backend.app.strategies.expression_engine.ast_nodes import ValidatedAst
    vast = ValidatedAst(root=ast, feature_requirements=(), variables_used=())
    cexpr = compile_expr(vast)
    assert abs(evaluate(cexpr, make_snapshot()) - 2.5) < 1e-9


def test_eval_subtraction():
    ast = parse("5 - 3")
    from backend.app.strategies.expression_engine.compiler import compile_expr
    from backend.app.strategies.expression_engine.ast_nodes import ValidatedAst
    vast = ValidatedAst(root=ast, feature_requirements=(), variables_used=())
    cexpr = compile_expr(vast)
    assert evaluate(cexpr, make_snapshot()) == 2.0


def test_eval_division_by_zero():
    ast = parse("1 / 0")
    from backend.app.strategies.expression_engine.compiler import compile_expr
    from backend.app.strategies.expression_engine.ast_nodes import ValidatedAst
    vast = ValidatedAst(root=ast, feature_requirements=(), variables_used=())
    cexpr = compile_expr(vast)
    with pytest.raises(EvalError):
        evaluate(cexpr, make_snapshot())


# ---------------------------------------------------------------------------
# Comparison operators
# ---------------------------------------------------------------------------

def test_eval_gt_true():
    result = _eval("5m.close > 100", values={"5m.close": 150.0})
    assert result is True


def test_eval_gt_false():
    result = _eval("5m.close > 100", values={"5m.close": 50.0})
    assert result is False


def test_eval_lt():
    result = _eval("5m.rsi(14) < 70", values={"5m.rsi(14)": 50.0})
    assert result is True


def test_eval_gte():
    result = _eval("5m.close >= 100", values={"5m.close": 100.0})
    assert result is True


def test_eval_lte():
    result = _eval("5m.close <= 99", values={"5m.close": 100.0})
    assert result is False


def test_eval_eq():
    result = _eval("5m.close == 100", values={"5m.close": 100.0})
    assert result is True


def test_eval_ne():
    result = _eval("5m.close != 100", values={"5m.close": 100.0})
    assert result is False


# ---------------------------------------------------------------------------
# AND / OR / NOT
# ---------------------------------------------------------------------------

def test_eval_and_both_true():
    result = _eval(
        "5m.close > 100 AND 5m.rsi(14) < 70",
        values={"5m.close": 150.0, "5m.rsi(14)": 50.0},
    )
    assert result is True


def test_eval_and_one_false():
    result = _eval(
        "5m.close > 100 AND 5m.rsi(14) < 70",
        values={"5m.close": 150.0, "5m.rsi(14)": 80.0},
    )
    assert result is False


def test_eval_or_one_true():
    result = _eval(
        "5m.close > 200 OR 5m.rsi(14) < 70",
        values={"5m.close": 150.0, "5m.rsi(14)": 50.0},
    )
    assert result is True


def test_eval_or_both_false():
    result = _eval(
        "5m.close > 200 OR 5m.rsi(14) > 80",
        values={"5m.close": 150.0, "5m.rsi(14)": 50.0},
    )
    assert result is False


def test_eval_not_true():
    result = _eval(
        "NOT session.is_power_hour",
        values={"session.is_power_hour": False},
    )
    assert result is True


def test_eval_not_false():
    result = _eval(
        "NOT session.is_open",
        values={"session.is_open": True},
    )
    assert result is False


# ---------------------------------------------------------------------------
# Crosses above/below with history
# ---------------------------------------------------------------------------

def test_eval_crosses_above_true():
    # curr: ema9=12, ema21=10  (12 > 10: yes)
    # prev: ema9=9, ema21=10  (9 <= 10: yes) → crosses_above = True
    result = _eval(
        "5m.ema(9) crosses_above 5m.ema(21)",
        values={"5m.ema(9)": 12.0, "5m.ema(21)": 10.0},
        history={"5m.ema(9)": (12.0, 9.0), "5m.ema(21)": (10.0, 10.0)},
    )
    assert result is True


def test_eval_crosses_above_false_no_cross():
    # curr: ema9=12, ema21=10  (12 > 10: yes)
    # prev: ema9=11, ema21=10  (11 > 10: yes) → no cross (already above)
    result = _eval(
        "5m.ema(9) crosses_above 5m.ema(21)",
        values={"5m.ema(9)": 12.0, "5m.ema(21)": 10.0},
        history={"5m.ema(9)": (12.0, 11.0), "5m.ema(21)": (10.0, 10.0)},
    )
    assert result is False


def test_eval_crosses_below_true():
    # curr: ema9=8, ema21=10  (8 < 10: yes)
    # prev: ema9=11, ema21=10  (11 >= 10: yes) → crosses_below = True
    result = _eval(
        "5m.ema(9) crosses_below 5m.ema(21)",
        values={"5m.ema(9)": 8.0, "5m.ema(21)": 10.0},
        history={"5m.ema(9)": (8.0, 11.0), "5m.ema(21)": (10.0, 10.0)},
    )
    assert result is True


def test_eval_crosses_above_missing_history():
    with pytest.raises(EvalError):
        _eval(
            "5m.ema(9) crosses_above 5m.ema(21)",
            values={"5m.ema(9)": 12.0, "5m.ema(21)": 10.0},
            # No history provided
        )


# ---------------------------------------------------------------------------
# Bar lookback
# ---------------------------------------------------------------------------

def test_eval_bar_lookback_close():
    result = _eval(
        "5m.close > bar[-1].high",
        values={"5m.close": 155.0},
        history={"bar.high": (150.0, 148.0, 145.0)},
    )
    assert result is True  # 155 > 150 (index 1 = abs(-1))


def test_eval_bar_lookback_out_of_range():
    with pytest.raises(EvalError):
        _eval(
            "5m.close > bar[-5].high",
            values={"5m.close": 155.0},
            history={"bar.high": (150.0, 148.0)},  # only 2 entries, need index 5
        )


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

def test_eval_variable():
    result = _eval(
        "my_var > 100",
        values={},
        variables={"my_var": 150.0},
        var_names=["my_var"],
    )
    assert result is True


def test_eval_variable_missing():
    ast = parse("short_ema crosses_above long_ema")
    vast = validate(ast, default_catalog(), variable_names=["short_ema", "long_ema"])
    cexpr = compile(vast)
    snap = make_snapshot(
        values={},
        history={"short_ema": (12.0, 9.0), "long_ema": (10.0, 10.0)},
        variables={},   # variables missing
    )
    with pytest.raises(EvalError):
        evaluate(cexpr, snap)


# ---------------------------------------------------------------------------
# Missing feature raises EvalError
# ---------------------------------------------------------------------------

def test_eval_missing_feature_raises():
    with pytest.raises(EvalError):
        _eval("5m.ema(9) > 100", values={})  # no "5m.ema(9)" in snapshot


def test_eval_missing_session_feature():
    with pytest.raises(EvalError):
        _eval("session.is_open", values={})
