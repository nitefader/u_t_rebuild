"""Hand-rolled tokenizer for the expression DSL.

Produces a flat list of Token instances.  Comments (// ...) are stripped.
Line and column numbers are 1-based.

Token kinds:
  NUMBER       numeric literal (int or float)
  IDENT        identifier or keyword
  OP           operator: > < >= <= == != + - * / ( ) , [ ]
  DOT          .
  NEWLINE      (used internally for comment stripping; not emitted)
  EOF          sentinel
"""
from __future__ import annotations

from dataclasses import dataclass

from .errors import ParseError


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    kind: str       # NUMBER | IDENT | OP | DOT | EOF
    value: str      # raw text
    line: int       # 1-based
    col: int        # 1-based


# ---------------------------------------------------------------------------
# Character classification helpers
# ---------------------------------------------------------------------------

def _is_digit(ch: str) -> bool:
    return ch.isdigit()


def _is_alpha(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_alnum(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Operators that may start a two-character sequence
_TWO_CHAR_OPS: frozenset[str] = frozenset({">=", "<=", "==", "!="})

# All known single-char operators (excluding those that combine)
_SINGLE_CHAR_OPS: frozenset[str] = frozenset({">", "<", "+", "-", "*", "/", "(", ")", ",", "[", "]"})


def tokenize(src: str) -> list[Token]:
    """Lex *src* and return a list of Tokens.

    The final token is always ``Token(kind="EOF", value="", ...)``.
    Raises :class:`ParseError` on unexpected characters.
    """
    tokens: list[Token] = []
    pos = 0
    line = 1
    col = 1
    length = len(src)

    def current_token_start() -> tuple[int, int]:
        return line, col

    def advance() -> str:
        nonlocal pos, line, col
        ch = src[pos]
        pos += 1
        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
        return ch

    def peek(offset: int = 0) -> str:
        idx = pos + offset
        if idx >= length:
            return ""
        return src[idx]

    while pos < length:
        tok_line, tok_col = line, col
        ch = peek()

        # ---- Skip whitespace (not newlines — newlines just reset col) ----
        if ch in (" ", "\t", "\r", "\n"):
            advance()
            continue

        # ---- Comments: // ... end of line ----
        if ch == "/" and peek(1) == "/":
            # consume until newline
            while pos < length and peek() != "\n":
                advance()
            continue

        # ---- Number literal OR timeframe identifier (5m, 15m, 1h, 4h, 1d, etc.) ----
        if _is_digit(ch) or (ch == "." and _is_digit(peek(1))):
            start = pos
            while pos < length and _is_digit(peek()):
                advance()
            # Check if this digit sequence is immediately followed by a timeframe suffix
            # (no dot/decimal), making it a timeframe IDENT like "5m", "1h", "15m"
            _TIMEFRAME_SUFFIXES = frozenset({"m", "h", "d"})
            if pos < length and peek() in _TIMEFRAME_SUFFIXES:
                # Consume the suffix letter to form a timeframe ident like "5m", "1h"
                advance()
                tokens.append(Token("IDENT", src[start:pos], tok_line, tok_col))
            elif pos < length and peek() == ".":
                # Could be a float like 3.14, or a timeframe like "1." — but timeframes
                # don't have a dot as suffix so this is a float
                advance()
                while pos < length and _is_digit(peek()):
                    advance()
                tokens.append(Token("NUMBER", src[start:pos], tok_line, tok_col))
            else:
                tokens.append(Token("NUMBER", src[start:pos], tok_line, tok_col))
            continue

        # ---- Dot (namespace separator / method accessor) ----
        if ch == ".":
            advance()
            tokens.append(Token("DOT", ".", tok_line, tok_col))
            continue

        # ---- Identifiers and keywords ----
        if _is_alpha(ch):
            start = pos
            while pos < length and _is_alnum(peek()):
                advance()
            value = src[start:pos]
            tokens.append(Token("IDENT", value, tok_line, tok_col))
            continue

        # ---- Two-character operators ----
        two = ch + peek(1)
        if two in _TWO_CHAR_OPS:
            advance()
            advance()
            tokens.append(Token("OP", two, tok_line, tok_col))
            continue

        # ---- Single-character operators ----
        if ch in _SINGLE_CHAR_OPS:
            advance()
            tokens.append(Token("OP", ch, tok_line, tok_col))
            continue

        # ---- Unknown character ----
        raise ParseError(
            f"Unexpected character {ch!r}",
            line=tok_line,
            col=tok_col,
        )

    tokens.append(Token("EOF", "", line, col))
    return tokens
