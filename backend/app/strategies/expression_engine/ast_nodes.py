"""AST node dataclasses for the expression engine.

All nodes are frozen dataclasses (immutable, hashable, picklable).
The shape of every node is locked per CONTRACTS.md — do not add
fields without coordination.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Union

VariableValue = float | bool | str


@dataclass(frozen=True)
class NumberLit:
    """Numeric literal, e.g. 9, 14, 0.5."""
    value: float


@dataclass(frozen=True)
class BoolLit:
    """Boolean literal: true or false."""
    value: bool


@dataclass(frozen=True)
class VariableRef:
    """Reference to a named variable provided by the caller context."""
    name: str


@dataclass(frozen=True)
class FeatureRef:
    """Non-timeframed feature like session.is_open, orb.high(15), bar[-3].close.

    bar_offset/bar_field are set for the bar[-N].field pattern; both are None
    for ordinary session/orb/prior_day references.
    """
    path: tuple[str, ...]           # ("session", "is_open") or ("orb", "high")
    args: tuple["AstNode", ...]     # () or (NumberLit(15),)
    bar_offset: int | None = None   # for bar[-3].close; None if not used
    bar_field: str | None = None    # "close" in bar[-3].close


@dataclass(frozen=True)
class TimeframedFeature:
    """Feature bound to a timeframe like 5m.ema(9) or 1h.rsi(14)."""
    timeframe: str              # "5m"
    name: str                   # "ema"
    args: tuple["AstNode", ...]


@dataclass(frozen=True)
class TimeframeVarFeature:
    """Timeframed feature whose timeframe is a strategy variable, e.g. sig_tf.ema(9)."""
    timeframe_variable: str     # variable name (bound to a canonical TF string at eval)
    name: str                   # "ema"
    args: tuple["AstNode", ...]


@dataclass(frozen=True)
class UnaryOp:
    """Unary operator: NOT (logical) or - (arithmetic)."""
    op: str             # "NOT" or "-"
    operand: "AstNode"


@dataclass(frozen=True)
class BinaryOp:
    """Binary operator covering arithmetic, comparisons, logical, and cross operators."""
    op: str             # "AND" "OR" ">" "<" ">=" "<=" "==" "!="
                        # "+" "-" "*" "/" "crosses_above" "crosses_below"
    left: "AstNode"
    right: "AstNode"


@dataclass(frozen=True)
class FunctionCall:
    """Keyword-style function call: within(a, b, c) / any_of(...) / all_of(...)."""
    name: str
    args: tuple["AstNode", ...]


# Union type alias — every parser-produced node is one of these.
AstNode = Union[
    NumberLit,
    BoolLit,
    VariableRef,
    FeatureRef,
    TimeframedFeature,
    TimeframeVarFeature,
    UnaryOp,
    BinaryOp,
    FunctionCall,
]


# ---------------------------------------------------------------------------
# Container types produced by later pipeline stages (validator, compiler)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidatedAst:
    """AST after successful validation, with feature requirements extracted."""
    root: AstNode
    feature_requirements: tuple[Union[FeatureRef, TimeframedFeature], ...]
    variables_used: tuple[str, ...]


@dataclass(frozen=True)
class CompiledExpr:
    """Canonical, picklable, immutable compiled expression.

    feature_index maps feature key strings (e.g. "5m.ema(9)") to integer
    column indices in the FeatureSnapshot for fast evaluation.
    """
    root: AstNode
    feature_index: dict[str, int]


@dataclass(frozen=True)
class FeatureSnapshot:
    """Runtime data container passed to the evaluator.

    values    — current bar feature values: feature_key -> float | bool
    history   — recent bar values for crosses_above/crosses_below and bar[-N]:
                  feature_key -> tuple of floats, index 0 = current, index 1 = previous bar, etc.
                  For bar[-N].field the key is "bar.<field>" e.g. "bar.close".
    variables — pre-resolved variable values: name -> float | bool | str
                (strings are canonical timeframes like "5m" for timeframe variables).
    """
    timestamp: datetime
    values: dict[str, float | bool]
    history: dict[str, tuple[float, ...]]
    variables: dict[str, VariableValue]
