"""Mirror: invert a long-side entry expression to short-side.

Operates at the token level (re-tokenizes, swaps tokens, emits).
The inversion table is defined in CONTRACTS.md and applied here verbatim.

Inversion table:
  crosses_above  ↔  crosses_below
  >              ↔  <
  >=             ↔  <=
  bb_lower       ↔  bb_upper
  donchian_low   ↔  donchian_high
  kc_lower       ↔  kc_upper
  orb.high       ↔  orb.low
  prior_day.high ↔  prior_day.low

AND, OR, NOT, ==, !=, math operators are NOT inverted.

A header comment is prepended or replaces any existing leading // comment.
"""
from __future__ import annotations

from .lexer import Token, tokenize

# ---------------------------------------------------------------------------
# Inversion maps (both directions)
# ---------------------------------------------------------------------------

_IDENT_SWAP: dict[str, str] = {
    "crosses_above":  "crosses_below",
    "crosses_below":  "crosses_above",
    "bb_lower":       "bb_upper",
    "bb_upper":       "bb_lower",
    "donchian_low":   "donchian_high",
    "donchian_high":  "donchian_low",
    "kc_lower":       "kc_upper",
    "kc_upper":       "kc_lower",
}

_OP_SWAP: dict[str, str] = {
    ">":  "<",
    "<":  ">",
    ">=": "<=",
    "<=": ">=",
}

# Multi-token compound swaps: matched as consecutive (IDENT "." IDENT) sequences
# key: tuple of (IDENT value, ".", IDENT value) → replacement tuple
_COMPOUND_SWAP: dict[tuple[str, str, str], tuple[str, str, str]] = {
    ("orb",       ".", "high"): ("orb",       ".", "low"),
    ("orb",       ".", "low"):  ("orb",       ".", "high"),
    ("prior_day", ".", "high"): ("prior_day", ".", "low"),
    ("prior_day", ".", "low"):  ("prior_day", ".", "high"),
}

_HEADER = "// Auto-mirrored from long entry — review and adjust"


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def mirror_long_to_short(src: str) -> str:
    """Return *src* with long→short inversions applied.

    If *src* already has a leading // comment header, it is replaced.
    Otherwise the header is prepended.
    """
    tokens = tokenize(src)

    # Strip the EOF sentinel for processing
    eof = tokens[-1]
    body_tokens = tokens[:-1]

    # ---- Apply token-level substitutions ----
    result_tokens = _apply_swaps(body_tokens)

    # ---- Re-emit to text ----
    emitted = _emit(result_tokens)

    # ---- Handle header comment ----
    lines = emitted.split("\n")
    # Remove any existing leading // comment line(s)
    while lines and lines[0].strip().startswith("//"):
        lines.pop(0)
    # Remove leading blank lines introduced by header removal
    while lines and lines[0].strip() == "":
        lines.pop(0)

    header_line = _HEADER
    body = "\n".join(lines).strip()
    if body:
        result = header_line + "\n" + body
    else:
        result = header_line

    return result


def _apply_swaps(tokens: list[Token]) -> list[Token]:
    """Return a new token list with all inversion-table swaps applied."""
    out: list[Token] = []
    i = 0
    n = len(tokens)

    while i < n:
        # Check 3-token compound swap (e.g. orb . high)
        if i + 2 < n:
            t0, t1, t2 = tokens[i], tokens[i + 1], tokens[i + 2]
            triple = (t0.value, t1.value, t2.value)
            if (t0.kind == "IDENT" and t1.kind == "DOT" and t2.kind == "IDENT"
                    and triple in _COMPOUND_SWAP):
                r0, r1, r2 = _COMPOUND_SWAP[triple]
                out.append(Token(t0.kind, r0, t0.line, t0.col))
                out.append(Token(t1.kind, r1, t1.line, t1.col))
                out.append(Token(t2.kind, r2, t2.line, t2.col))
                i += 3
                continue

        t = tokens[i]

        # IDENT swap
        if t.kind == "IDENT" and t.value in _IDENT_SWAP:
            out.append(Token(t.kind, _IDENT_SWAP[t.value], t.line, t.col))
            i += 1
            continue

        # OP swap
        if t.kind == "OP" and t.value in _OP_SWAP:
            out.append(Token(t.kind, _OP_SWAP[t.value], t.line, t.col))
            i += 1
            continue

        out.append(t)
        i += 1

    return out


def _emit(tokens: list[Token]) -> str:
    """Reconstruct source text from a token list.

    Reconstruction rules (for clean, idiomatic output):
    - DOT tokens are emitted without surrounding spaces (a.b not a . b)
    - Opening paren "(" is emitted without a leading space after idents (f(x) not f (x))
    - Closing paren ")" has no trailing space before the next token
    - Opening "[" has no leading space after idents
    - Comma "," has no leading space, one trailing space
    - All other tokens separated by a single space.

    Line breaks are preserved from the original token positions.
    """
    if not tokens:
        return ""

    # Group by line
    lines: dict[int, list[Token]] = {}
    for tok in tokens:
        lines.setdefault(tok.line, []).append(tok)

    output_lines: list[str] = []
    for line_no in sorted(lines):
        toks = lines[line_no]
        parts: list[str] = []
        for i, tok in enumerate(toks):
            prev = toks[i - 1] if i > 0 else None
            # Decide whether to suppress the space before this token
            suppress_space = False
            if prev is not None:
                # No space after DOT
                if prev.kind == "DOT":
                    suppress_space = True
                # No space before DOT
                elif tok.kind == "DOT":
                    suppress_space = True
                # No space before "(" after an ident or ")"
                elif tok.kind == "OP" and tok.value == "(" and prev.kind in ("IDENT", "NUMBER"):
                    suppress_space = True
                # No space before ")" — closing paren hugs content
                elif tok.kind == "OP" and tok.value == ")":
                    suppress_space = True
                # No space before "]"
                elif tok.kind == "OP" and tok.value == "]":
                    suppress_space = True
                # No space before "[" after an ident
                elif tok.kind == "OP" and tok.value == "[" and prev.kind == "IDENT":
                    suppress_space = True
                # No space before ","
                elif tok.kind == "OP" and tok.value == ",":
                    suppress_space = True
                # No space after "("
                elif prev.kind == "OP" and prev.value == "(":
                    suppress_space = True
                # No space after "["
                elif prev.kind == "OP" and prev.value == "[":
                    suppress_space = True
                # No space after ","  — wait, we DO want space after comma
                # (handled by: don't suppress for normal tokens after comma)

            if parts and not suppress_space:
                parts.append(" ")
            parts.append(tok.value)

        output_lines.append("".join(parts))

    return "\n".join(output_lines)
