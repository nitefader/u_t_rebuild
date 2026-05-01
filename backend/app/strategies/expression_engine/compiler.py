"""Compiler: transforms a ValidatedAst into a CompiledExpr.

For v1 the compiler's main job is to build a feature_index dict that maps
every feature key string to a sequential integer column index.  This allows
the evaluator to do O(1) lookups.

The AST root is carried through unchanged (same frozen dataclass tree).
The resulting CompiledExpr is pickling-safe.
"""
from __future__ import annotations

from .ast_nodes import (
    CompiledExpr,
    FeatureRef,
    TimeframedFeature,
    ValidatedAst,
)


def _feature_key(node: FeatureRef | TimeframedFeature) -> str:
    """Return the canonical string key used in FeatureSnapshot.values.

    TimeframedFeature  → "<timeframe>.<name>(<args>)"  e.g. "5m.ema(9)"
    FeatureRef (bar)   → "bar.<field>"                 e.g. "bar.close"
    FeatureRef (other) → "<namespace>.<name>(<args>)"  e.g. "session.is_open"

    Numeric args are formatted as integers when they are whole numbers
    (e.g. 9 not 9.0) to match the natural string representation operators
    use when building snapshot keys.
    """
    def fmt_arg(v: object) -> str:
        from .ast_nodes import NumberLit
        if isinstance(v, NumberLit):
            f = v.value
            return str(int(f)) if f == int(f) else str(f)
        # For nested expressions as args (rare) fall back to repr
        return repr(v)

    if isinstance(node, TimeframedFeature):
        args_str = ",".join(fmt_arg(a) for a in node.args)
        if args_str:
            return f"{node.timeframe}.{node.name}({args_str})"
        return f"{node.timeframe}.{node.name}"

    # FeatureRef
    if node.bar_offset is not None:
        # bar lookback — key is "bar.<field>"
        return f"bar.{node.bar_field}"

    namespace = node.path[0] if node.path else ""
    name = node.path[1] if len(node.path) > 1 else ""
    args_str = ",".join(fmt_arg(a) for a in node.args)
    if args_str:
        return f"{namespace}.{name}({args_str})"
    return f"{namespace}.{name}"


def compile_expr(validated: ValidatedAst) -> CompiledExpr:
    """Compile *validated* into a picklable :class:`CompiledExpr`.

    Assigns each unique feature a sequential integer index starting at 0.
    """
    feature_index: dict[str, int] = {}
    for node in validated.feature_requirements:
        key = _feature_key(node)
        if key not in feature_index:
            feature_index[key] = len(feature_index)

    return CompiledExpr(root=validated.root, feature_index=feature_index)
