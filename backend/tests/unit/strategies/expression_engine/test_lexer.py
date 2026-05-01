"""Tests for the expression engine lexer."""
from __future__ import annotations

import pytest

from backend.app.strategies.expression_engine.errors import ParseError
from backend.app.strategies.expression_engine.lexer import Token, tokenize


# ---------------------------------------------------------------------------
# Basic tokenization
# ---------------------------------------------------------------------------

def test_number_integer():
    tokens = tokenize("42")
    assert tokens[0] == Token("NUMBER", "42", 1, 1)
    assert tokens[-1].kind == "EOF"


def test_number_float():
    tokens = tokenize("3.14")
    assert tokens[0] == Token("NUMBER", "3.14", 1, 1)


def test_ident():
    tokens = tokenize("ema")
    assert tokens[0] == Token("IDENT", "ema", 1, 1)


def test_dot():
    tokens = tokenize("session.is_open")
    kinds = [t.kind for t in tokens[:-1]]
    values = [t.value for t in tokens[:-1]]
    assert kinds == ["IDENT", "DOT", "IDENT"]
    assert values == ["session", ".", "is_open"]


def test_operators():
    tokens = tokenize("> < >= <= == != + - * /")
    ops = [t.value for t in tokens if t.kind == "OP"]
    assert ops == [">", "<", ">=", "<=", "==", "!=", "+", "-", "*", "/"]


def test_parens_and_comma():
    tokens = tokenize("f(a, b)")
    values = [t.value for t in tokens[:-1]]
    assert values == ["f", "(", "a", ",", "b", ")"]


def test_brackets():
    tokens = tokenize("bar[-1]")
    kinds = [t.kind for t in tokens[:-1]]
    values = [t.value for t in tokens[:-1]]
    assert "OP" in kinds
    assert "[" in values
    assert "]" in values


# ---------------------------------------------------------------------------
# Keyword identifiers
# ---------------------------------------------------------------------------

def test_keywords_are_idents():
    for kw in ["AND", "OR", "NOT", "crosses_above", "crosses_below", "true", "false"]:
        tokens = tokenize(kw)
        assert tokens[0].kind == "IDENT"
        assert tokens[0].value == kw


def test_timeframe_tokens():
    for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]:
        tokens = tokenize(tf)
        assert tokens[0].kind == "IDENT"
        assert tokens[0].value == tf


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def test_line_comment_stripped():
    src = "// this is a comment\n5m.ema(9)"
    tokens = tokenize(src)
    # Only feature tokens should appear (no comment tokens)
    non_eof = [t for t in tokens if t.kind != "EOF"]
    values = [t.value for t in non_eof]
    assert "//" not in values
    assert "this" not in values
    assert "5m" in values


def test_inline_comment_stripped():
    src = "5m.ema(9) // trailing comment"
    tokens = tokenize(src)
    non_eof = [t for t in tokens if t.kind != "EOF"]
    assert all("//" not in t.value for t in non_eof)
    assert any(t.value == "5m" for t in non_eof)


def test_comment_only_source():
    tokens = tokenize("// just a comment")
    assert tokens[0].kind == "EOF"


# ---------------------------------------------------------------------------
# Line and column tracking
# ---------------------------------------------------------------------------

def test_line_tracking():
    src = "foo\nbar"
    tokens = tokenize(src)
    assert tokens[0].line == 1
    assert tokens[1].line == 2


def test_col_tracking():
    src = "  abc"
    tokens = tokenize(src)
    # 'abc' starts at col 3 (1-based, two spaces before it)
    assert tokens[0].col == 3


def test_multiline_col_reset():
    src = "a\nb"
    tokens = tokenize(src)
    assert tokens[1].col == 1  # 'b' should be at col 1 on line 2


# ---------------------------------------------------------------------------
# Error on bad characters
# ---------------------------------------------------------------------------

def test_bad_char_raises():
    with pytest.raises(ParseError) as exc_info:
        tokenize("5m.ema(9) @bad")
    err = exc_info.value
    assert err.line >= 1
    assert err.col >= 1
    assert "@" in err.message


def test_bad_char_position():
    with pytest.raises(ParseError) as exc_info:
        tokenize("abc $xyz")
    err = exc_info.value
    # '$' is at position 5 (1-based col after "abc ")
    assert err.col == 5


# ---------------------------------------------------------------------------
# EOF sentinel
# ---------------------------------------------------------------------------

def test_eof_always_present():
    tokens = tokenize("")
    assert tokens[-1].kind == "EOF"

    tokens = tokenize("5m.ema(9)")
    assert tokens[-1].kind == "EOF"


# ---------------------------------------------------------------------------
# Complex expression tokenization
# ---------------------------------------------------------------------------

def test_full_expression_token_count():
    src = "5m.ema(9) crosses_above 5m.ema(21) AND 5m.rsi(14) < 70"
    tokens = tokenize(src)
    non_eof = [t for t in tokens if t.kind != "EOF"]
    # Quick sanity: should have multiple tokens
    assert len(non_eof) > 10
    # All should have valid kinds
    for t in non_eof:
        assert t.kind in ("NUMBER", "IDENT", "OP", "DOT")
