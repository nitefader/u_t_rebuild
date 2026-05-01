"""Recursive-descent parser for the expression DSL.

Grammar (from CONTRACTS.md):
    expression := or_expr
    or_expr    := and_expr ( "OR" and_expr )*
    and_expr   := not_expr ( "AND" not_expr )*
    not_expr   := "NOT" not_expr | comparison
    comparison := add_expr ( ( ">" | "<" | ">=" | "<=" | "==" | "!="
                               | "crosses_above" | "crosses_below" ) add_expr )?
    add_expr   := mul_expr ( ( "+" | "-" ) mul_expr )*
    mul_expr   := unary ( ( "*" | "/" ) unary )*
    unary      := "-" unary | atom
    atom       := NUMBER
                | IDENT ( "." IDENT )* ( "(" arg_list? ")" )? ( "[" INTEGER "]" "." IDENT )?
                | "(" expression ")"
    arg_list   := expression ( "," expression )*

Special IDENT values handled at parse layer:
  - true / false  → BoolLit
  - AND / OR / NOT  → logical operators
  - crosses_above / crosses_below  → comparison operators
  - within / any_of / all_of  → FunctionCall
  - Timeframes: 1m 5m 15m 30m 1h 4h 1d  → TimeframedFeature
"""
from __future__ import annotations

from .ast_nodes import (
    AstNode,
    BinaryOp,
    BoolLit,
    FeatureRef,
    FunctionCall,
    NumberLit,
    TimeframedFeature,
    UnaryOp,
    VariableRef,
)
from .errors import ParseError
from .lexer import Token, tokenize

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIMEFRAMES: frozenset[str] = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d"})

# Keywords that act as operators at the comparison level
_CROSS_OPS: frozenset[str] = frozenset({"crosses_above", "crosses_below"})

# All comparison operators
_CMP_OPS: frozenset[str] = frozenset({">", "<", ">=", "<=", "==", "!="}) | _CROSS_OPS

# Known keyword-style functions
_KEYWORD_FUNCS: frozenset[str] = frozenset({"within", "any_of", "all_of"})

# Bar lookback allowed fields
_BAR_FIELDS: frozenset[str] = frozenset({"close", "open", "high", "low", "range", "body"})


# ---------------------------------------------------------------------------
# Parser class
# ---------------------------------------------------------------------------

class _Parser:
    """Internal recursive-descent parser.  Call parse() at module level."""

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # ---- token stream helpers ----

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        if tok.kind != "EOF":
            self._pos += 1
        return tok

    def _at_end(self) -> bool:
        return self._peek().kind == "EOF"

    def _check_ident(self, value: str) -> bool:
        t = self._peek()
        return t.kind == "IDENT" and t.value == value

    def _check_op(self, value: str) -> bool:
        t = self._peek()
        return t.kind == "OP" and t.value == value

    def _expect_op(self, value: str) -> Token:
        t = self._peek()
        if t.kind != "OP" or t.value != value:
            raise ParseError(
                f"Expected '{value}', got {t.value!r}",
                line=t.line, col=t.col,
            )
        return self._advance()

    def _expect_ident(self) -> Token:
        t = self._peek()
        if t.kind != "IDENT":
            raise ParseError(
                f"Expected identifier, got {t.value!r}",
                line=t.line, col=t.col,
            )
        return self._advance()

    # ---- grammar rules ----

    def expression(self) -> AstNode:
        return self._or_expr()

    def _or_expr(self) -> AstNode:
        node = self._and_expr()
        while self._check_ident("OR"):
            self._advance()
            right = self._and_expr()
            node = BinaryOp("OR", node, right)
        return node

    def _and_expr(self) -> AstNode:
        node = self._not_expr()
        while self._check_ident("AND"):
            self._advance()
            right = self._not_expr()
            node = BinaryOp("AND", node, right)
        return node

    def _not_expr(self) -> AstNode:
        if self._check_ident("NOT"):
            tok = self._advance()
            operand = self._not_expr()
            return UnaryOp("NOT", operand)
        return self._comparison()

    def _comparison(self) -> AstNode:
        node = self._add_expr()
        t = self._peek()
        # Operator-style comparison
        if t.kind == "OP" and t.value in _CMP_OPS:
            op = self._advance().value
            right = self._add_expr()
            return BinaryOp(op, node, right)
        # Keyword-style comparison (crosses_above / crosses_below)
        if t.kind == "IDENT" and t.value in _CROSS_OPS:
            op = self._advance().value
            right = self._add_expr()
            return BinaryOp(op, node, right)
        return node

    def _add_expr(self) -> AstNode:
        node = self._mul_expr()
        while True:
            t = self._peek()
            if t.kind == "OP" and t.value in ("+", "-"):
                op = self._advance().value
                right = self._mul_expr()
                node = BinaryOp(op, node, right)
            else:
                break
        return node

    def _mul_expr(self) -> AstNode:
        node = self._unary()
        while True:
            t = self._peek()
            if t.kind == "OP" and t.value in ("*", "/"):
                op = self._advance().value
                right = self._unary()
                node = BinaryOp(op, node, right)
            else:
                break
        return node

    def _unary(self) -> AstNode:
        t = self._peek()
        if t.kind == "OP" and t.value == "-":
            self._advance()
            operand = self._unary()
            return UnaryOp("-", operand)
        return self._atom()

    def _atom(self) -> AstNode:
        t = self._peek()

        # ---- Numeric literal ----
        if t.kind == "NUMBER":
            self._advance()
            return NumberLit(float(t.value))

        # ---- Parenthesised sub-expression ----
        if t.kind == "OP" and t.value == "(":
            self._advance()
            node = self.expression()
            self._expect_op(")")
            return node

        # ---- Identifiers (timeframes, keywords, features, variables) ----
        if t.kind == "IDENT":
            return self._ident_atom()

        raise ParseError(
            f"Unexpected token {t.value!r}",
            line=t.line, col=t.col,
        )

    def _ident_atom(self) -> AstNode:
        """Parse an identifier-led atom.  Handles all 5 identifier flavours
        described in CONTRACTS.md identifier resolution section."""
        t = self._peek()
        value = t.value

        # ---- Boolean literals ----
        if value == "true":
            self._advance()
            return BoolLit(True)
        if value == "false":
            self._advance()
            return BoolLit(False)

        # ---- Keyword-style functions (within, any_of, all_of) ----
        if value in _KEYWORD_FUNCS:
            self._advance()
            self._expect_op("(")
            args = self._arg_list()
            self._expect_op(")")
            return FunctionCall(value, tuple(args))

        # ---- Timeframe-prefixed feature: 5m.ema(9) ----
        if value in _TIMEFRAMES:
            return self._timeframed_feature()

        # ---- bar[-N].field lookback ----
        if value == "bar":
            t2_pos = self._pos + 1
            # look ahead: next token should be "[" (OP)
            if t2_pos < len(self._tokens) and self._tokens[t2_pos].kind == "OP" and self._tokens[t2_pos].value == "[":
                return self._bar_lookback()

        # ---- Generic dotted path (session.is_open, orb.high(15), prior_day.close, etc.) ----
        return self._dotted_feature_or_variable()

    def _timeframed_feature(self) -> AstNode:
        """Parse 5m.ema(9), 1h.rsi(14), 5m.volume, etc."""
        tf_tok = self._advance()      # consume timeframe ident
        timeframe = tf_tok.value

        # Expect "."
        if self._peek().kind != "DOT":
            raise ParseError(
                f"Expected '.' after timeframe '{timeframe}'",
                line=self._peek().line, col=self._peek().col,
            )
        self._advance()  # consume DOT

        name_tok = self._expect_ident()
        name = name_tok.value

        # Optional argument list
        args: list[AstNode] = []
        if self._check_op("("):
            self._advance()
            if not self._check_op(")"):
                args = self._arg_list()
            self._expect_op(")")

        return TimeframedFeature(timeframe=timeframe, name=name, args=tuple(args))

    def _bar_lookback(self) -> AstNode:
        """Parse bar[-N].field where N is a positive integer (written as -N or +N)."""
        tok = self._advance()           # consume "bar"
        bar_tok = tok
        self._expect_op("[")            # consume "["

        # Expect an integer offset, possibly negative
        negative = False
        if self._check_op("-"):
            self._advance()
            negative = True
        elif self._check_op("+"):
            self._advance()

        # Expect NUMBER (integer)
        t = self._peek()
        if t.kind != "NUMBER":
            raise ParseError(
                "Expected integer offset after 'bar['",
                line=t.line, col=t.col,
            )
        offset_tok = self._advance()
        try:
            offset_val = int(float(offset_tok.value))
        except ValueError:
            raise ParseError(
                f"bar offset must be an integer, got {offset_tok.value!r}",
                line=offset_tok.line, col=offset_tok.col,
            )
        if negative:
            offset_val = -offset_val

        self._expect_op("]")

        # Expect "." then field name
        if self._peek().kind != "DOT":
            raise ParseError(
                "Expected '.' after bar[N]",
                line=self._peek().line, col=self._peek().col,
            )
        self._advance()  # consume DOT
        field_tok = self._expect_ident()
        field = field_tok.value

        if field not in _BAR_FIELDS:
            raise ParseError(
                f"Unknown bar field {field!r}; allowed: {sorted(_BAR_FIELDS)}",
                line=field_tok.line, col=field_tok.col,
            )

        return FeatureRef(
            path=("bar",),
            args=(),
            bar_offset=offset_val,
            bar_field=field,
        )

    def _dotted_feature_or_variable(self) -> AstNode:
        """Parse session.is_open, orb.high(15), prior_day.close, or bare VariableRef."""
        first_tok = self._advance()
        parts: list[str] = [first_tok.value]

        # Collect additional dot-separated parts
        while self._peek().kind == "DOT":
            self._advance()  # consume DOT
            name_tok = self._expect_ident()
            parts.append(name_tok.value)

        # Optional argument list
        args: list[AstNode] = []
        if self._check_op("("):
            self._advance()
            if not self._check_op(")"):
                args = self._arg_list()
            self._expect_op(")")

        path = tuple(parts)

        # If only one part and no args → could be variable or bare feature
        # Emit FeatureRef for single-part names that are known namespace roots
        # (session, orb, prior_day, bar) — the validator resolves unknowns.
        # Single-part with no dot chain → VariableRef if it has no args
        # (validator will reject unknown variables).
        if len(parts) == 1 and not args:
            return VariableRef(name=parts[0])

        return FeatureRef(path=path, args=tuple(args))

    def _arg_list(self) -> list[AstNode]:
        """Parse a comma-separated list of expressions."""
        args = [self.expression()]
        while self._check_op(","):
            self._advance()
            args.append(self.expression())
        return args


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def parse(src: str) -> AstNode:
    """Parse *src* and return the root :class:`AstNode`.

    Raises :class:`ParseError` with line/col on any syntax error.
    """
    tokens = tokenize(src)
    p = _Parser(tokens)
    node = p.expression()
    # Ensure we consumed everything
    trailing = p._peek()
    if trailing.kind != "EOF":
        raise ParseError(
            f"Unexpected trailing token {trailing.value!r}",
            line=trailing.line,
            col=trailing.col,
        )
    return node
