"""Expression Engine — public API.

Usage::

    from backend.app.strategies.expression_engine import (
        parse, validate, compile, evaluate, extract_features, mirror_long_to_short,
        default_catalog, FeatureSnapshot,
    )

    ast   = parse("5m.ema(9) crosses_above 5m.ema(21)")
    vast  = validate(ast, default_catalog())
    cexpr = compile(vast)
    result = evaluate(cexpr, snapshot)

The engine is fully self-contained.  No other backend packages are imported.
"""
from __future__ import annotations

from typing import Iterable

from .ast_nodes import (
    AstNode,
    BinaryOp,
    BoolLit,
    CompiledExpr,
    FeatureRef,
    FeatureSnapshot,
    FunctionCall,
    NumberLit,
    TimeframedFeature,
    TimeframeVarFeature,
    UnaryOp,
    ValidatedAst,
    VariableRef,
)
from .compiler import compile_expr as _compile_expr
from .errors import EvalError, ExpressionError, ParseError, ValidationError, ValidationIssue
from .evaluator import evaluate as _evaluate
from .features import FeatureCatalog, FeatureSpec, default_catalog
from .mirror import mirror_long_to_short
from .parser import parse as _parse
from .timeframes import CANONICAL_TIMEFRAMES, CANONICAL_TIMEFRAMES_ORDER
from .validator import validate as _validate


# ---------------------------------------------------------------------------
# Public API functions (matching signatures in CONTRACTS.md)
# ---------------------------------------------------------------------------

def parse(src: str, timeframe_variable_names: frozenset[str] | None = None) -> AstNode:
    """Parse *src* and return the root AST node.

    Raises :class:`ParseError` with line/col on syntax errors.
    """
    return _parse(src, timeframe_variable_names=timeframe_variable_names)


def validate(
    ast: AstNode,
    catalog: FeatureCatalog,
    variable_names: Iterable[str] = (),
    *,
    timeframe_variable_names: Iterable[str] = (),
) -> ValidatedAst:
    """Validate *ast* against *catalog*.

    Returns :class:`ValidatedAst` on success.
    Raises :class:`ValidationError` on unknown features/variables or arity mismatches.
    """
    return _validate(
        ast, catalog, variable_names, timeframe_variable_names=timeframe_variable_names
    )


def compile(validated: ValidatedAst) -> CompiledExpr:
    """Compile *validated* into a picklable :class:`CompiledExpr`.

    This is our own compile function — it does NOT call Python's built-in
    compile() on user text.
    """
    return _compile_expr(validated)


def evaluate(compiled: CompiledExpr, snapshot: FeatureSnapshot) -> bool | float:
    """Evaluate *compiled* against *snapshot*.

    Raises :class:`EvalError` on missing data or evaluation failure.
    """
    return _evaluate(compiled, snapshot)


def extract_features(
    validated: ValidatedAst,
) -> list[FeatureRef | TimeframedFeature]:
    """Return the deduplicated list of feature requirements from *validated*."""
    return list(validated.feature_requirements)


__all__ = [
    # Pipeline functions
    "parse",
    "validate",
    "compile",
    "evaluate",
    "extract_features",
    "mirror_long_to_short",
    # AST nodes
    "AstNode",
    "BinaryOp",
    "BoolLit",
    "CompiledExpr",
    "FeatureRef",
    "FeatureSnapshot",
    "FunctionCall",
    "NumberLit",
    "TimeframedFeature",
    "TimeframeVarFeature",
    "UnaryOp",
    "ValidatedAst",
    "VariableRef",
    # Catalog / timeframes
    "CANONICAL_TIMEFRAMES",
    "CANONICAL_TIMEFRAMES_ORDER",
    "default_catalog",
    "FeatureCatalog",
    "FeatureSpec",
    # Errors
    "ExpressionError",
    "ParseError",
    "ValidationError",
    "ValidationIssue",
    "EvalError",
]
