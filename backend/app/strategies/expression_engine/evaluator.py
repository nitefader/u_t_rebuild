"""Evaluator: walks a CompiledExpr AST and computes a bool | float result.

Feature value lookup strategy:
  - TimeframedFeature  → snapshot.values["5m.ema(9)"] etc.
  - FeatureRef         → snapshot.values["session.is_open"] etc.
  - bar[-N].field      → snapshot.history["bar.<field>"][N]
                         (index 0 = current bar, index 1 = one bar ago, etc.)
  - VariableRef        → snapshot.variables["name"]
  - crosses_above      → current value > previous value  (snapshot.history)
  - crosses_below      → current value < previous value

History keys for crosses_above/crosses_below:
  The evaluator looks for the same feature key in snapshot.history to
  retrieve the previous bar's value (index 1).  The runtime must populate
  history[key] = (current_value, prev_value, ...) for any feature used in
  a crosses expression.
"""
from __future__ import annotations

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
    VariableRef,
)
from .errors import EvalError
from .timeframes import CANONICAL_TIMEFRAMES, CANONICAL_TIMEFRAMES_ORDER


# ---------------------------------------------------------------------------
# Feature key helpers (mirrors compiler.py — kept local to avoid circular dep)
# ---------------------------------------------------------------------------

def _fmt_arg(v: object) -> str:
    if isinstance(v, NumberLit):
        f = v.value
        return str(int(f)) if f == int(f) else str(f)
    return repr(v)


def _feature_key_tf(node: TimeframedFeature) -> str:
    args_str = ",".join(_fmt_arg(a) for a in node.args)
    if args_str:
        return f"{node.timeframe}.{node.name}({args_str})"
    return f"{node.timeframe}.{node.name}"


def _feature_key_tv_resolved(node: TimeframeVarFeature, timeframe: str) -> str:
    synth = TimeframedFeature(timeframe=timeframe, name=node.name, args=node.args)
    return _feature_key_tf(synth)


def _feature_key_ref(node: FeatureRef) -> str:
    if node.bar_offset is not None:
        return f"bar.{node.bar_field}"
    namespace = node.path[0] if node.path else ""
    name = node.path[1] if len(node.path) > 1 else ""
    args_str = ",".join(_fmt_arg(a) for a in node.args)
    if args_str:
        return f"{namespace}.{name}({args_str})"
    return f"{namespace}.{name}"


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class _Evaluator:
    def __init__(self, snapshot: FeatureSnapshot) -> None:
        self._snap = snapshot

    def eval(self, node: AstNode) -> bool | float:
        if isinstance(node, NumberLit):
            return node.value

        if isinstance(node, BoolLit):
            return node.value

        if isinstance(node, VariableRef):
            try:
                val = self._snap.variables[node.name]
            except KeyError:
                raise EvalError(f"Variable '{node.name}' not found in snapshot.variables")
            if isinstance(val, str):
                raise EvalError(
                    f"Variable '{node.name}' is a timeframe binding; use it as {node.name}.<feature>"
                )
            return val

        if isinstance(node, TimeframedFeature):
            return self._lookup_tf(node)

        if isinstance(node, TimeframeVarFeature):
            return self._lookup_tv(node)

        if isinstance(node, FeatureRef):
            return self._lookup_ref(node)

        if isinstance(node, UnaryOp):
            return self._eval_unary(node)

        if isinstance(node, BinaryOp):
            return self._eval_binary(node)

        if isinstance(node, FunctionCall):
            return self._eval_function(node)

        raise EvalError(f"Unknown AST node type during evaluation: {type(node).__name__}")

    # ---- lookups ----

    def _lookup_tf(self, node: TimeframedFeature) -> bool | float:
        key = _feature_key_tf(node)
        if key in self._snap.values:
            return self._snap.values[key]
        raise EvalError(
            f"Feature '{key}' not found in snapshot.values"
        )

    def _resolve_timeframe_string(self, var_name: str) -> str:
        try:
            raw = self._snap.variables[var_name]
        except KeyError:
            raise EvalError(f"Timeframe variable '{var_name}' not found in snapshot.variables")
        if not isinstance(raw, str):
            raise EvalError(
                f"Timeframe variable '{var_name}' must be bound to a timeframe string at evaluation"
            )
        if raw not in CANONICAL_TIMEFRAMES:
            raise EvalError(
                f"Timeframe variable '{var_name}' has invalid value {raw!r}; "
                f"expected one of {list(CANONICAL_TIMEFRAMES_ORDER)}"
            )
        return raw

    def _lookup_tv(self, node: TimeframeVarFeature) -> bool | float:
        tf = self._resolve_timeframe_string(node.timeframe_variable)
        key = _feature_key_tv_resolved(node, tf)
        if key in self._snap.values:
            return self._snap.values[key]
        raise EvalError(f"Feature '{key}' not found in snapshot.values")

    def _lookup_ref(self, node: FeatureRef) -> bool | float:
        if node.bar_offset is not None:
            # bar[-N].field → history["bar.<field>"][abs(N)]
            hist_key = f"bar.{node.bar_field}"
            history = self._snap.history.get(hist_key)
            if history is None:
                raise EvalError(
                    f"Bar history '{hist_key}' not found in snapshot.history"
                )
            # offset is typically negative (bar[-1]); use abs for indexing
            idx = abs(node.bar_offset)
            if idx >= len(history):
                raise EvalError(
                    f"Bar history '{hist_key}' has only {len(history)} entries; "
                    f"requested index {idx}"
                )
            return history[idx]

        key = _feature_key_ref(node)
        if key in self._snap.values:
            return self._snap.values[key]
        raise EvalError(f"Feature '{key}' not found in snapshot.values")

    # ---- unary ----

    def _eval_unary(self, node: UnaryOp) -> bool | float:
        val = self.eval(node.operand)
        if node.op == "NOT":
            if not isinstance(val, bool):
                # Coerce: 0.0 == False
                val = bool(val)
            return not val
        if node.op == "-":
            if isinstance(val, bool):
                return -int(val)
            return -val
        raise EvalError(f"Unknown unary operator '{node.op}'")

    # ---- binary ----

    def _eval_binary(self, node: BinaryOp) -> bool | float:
        op = node.op

        # Short-circuit logical operators
        if op == "AND":
            left = self.eval(node.left)
            if not _truthy(left):
                return False
            right = self.eval(node.right)
            return _truthy(right)

        if op == "OR":
            left = self.eval(node.left)
            if _truthy(left):
                return True
            right = self.eval(node.right)
            return _truthy(right)

        # Cross operators require history
        if op == "crosses_above":
            return self._eval_cross(node, above=True)
        if op == "crosses_below":
            return self._eval_cross(node, above=False)

        # Arithmetic
        left = self.eval(node.left)
        right = self.eval(node.right)

        if op == "+":
            return _num(left, op) + _num(right, op)
        if op == "-":
            return _num(left, op) - _num(right, op)
        if op == "*":
            return _num(left, op) * _num(right, op)
        if op == "/":
            r = _num(right, op)
            if r == 0:
                raise EvalError("Division by zero")
            return _num(left, op) / r

        # Comparisons
        if op == ">":
            return _num(left, op) > _num(right, op)
        if op == "<":
            return _num(left, op) < _num(right, op)
        if op == ">=":
            return _num(left, op) >= _num(right, op)
        if op == "<=":
            return _num(left, op) <= _num(right, op)
        if op == "==":
            return left == right
        if op == "!=":
            return left != right

        raise EvalError(f"Unknown binary operator '{op}'")

    def _eval_cross(self, node: BinaryOp, above: bool) -> bool:
        """Evaluate crosses_above / crosses_below.

        For a TimeframedFeature or FeatureRef LHS:
          current  = snapshot.values[key]       (index 0 in history)
          previous = snapshot.history[key][1]

        The RHS is evaluated normally (may be a feature or constant).
        crosses_above:  prev_left <= prev_right AND curr_left > curr_right
        crosses_below:  prev_left >= prev_right AND curr_left < curr_right
        """
        # Evaluate current values
        curr_left = self.eval(node.left)
        curr_right = self.eval(node.right)

        # Retrieve previous values from history
        prev_left = self._prev_value(node.left)
        prev_right = self._prev_value(node.right)

        if above:
            return float(prev_left) <= float(prev_right) and float(curr_left) > float(curr_right)
        else:
            return float(prev_left) >= float(prev_right) and float(curr_left) < float(curr_right)

    def _prev_value(self, node: AstNode) -> float | bool:
        """Get the previous bar's value for a node (used by crosses_above/below)."""
        if isinstance(node, TimeframedFeature):
            key = _feature_key_tf(node)
            history = self._snap.history.get(key)
            if history is None or len(history) < 2:
                raise EvalError(
                    f"History for '{key}' has fewer than 2 entries; cannot evaluate cross"
                )
            return history[1]

        if isinstance(node, TimeframeVarFeature):
            tf = self._resolve_timeframe_string(node.timeframe_variable)
            key = _feature_key_tv_resolved(node, tf)
            history = self._snap.history.get(key)
            if history is None or len(history) < 2:
                raise EvalError(
                    f"History for '{key}' has fewer than 2 entries; cannot evaluate cross"
                )
            return history[1]

        if isinstance(node, FeatureRef):
            if node.bar_offset is not None:
                # bar[-N].field previous bar — look at history[abs(N)+1]
                hist_key = f"bar.{node.bar_field}"
                history = self._snap.history.get(hist_key)
                if history is None:
                    raise EvalError(f"Bar history '{hist_key}' not found")
                idx = abs(node.bar_offset) + 1
                if idx >= len(history):
                    raise EvalError(f"Insufficient bar history for cross evaluation")
                return history[idx]
            key = _feature_key_ref(node)
            history = self._snap.history.get(key)
            if history is None or len(history) < 2:
                raise EvalError(f"History for '{key}' has fewer than 2 entries")
            return history[1]

        if isinstance(node, VariableRef):
            # Variables may have history entries keyed by name
            history = self._snap.history.get(node.name)
            if history is not None and len(history) >= 2:
                return history[1]
            # Fall back to current value if no history
            return self.eval(node)

        if isinstance(node, NumberLit):
            return node.value

        if isinstance(node, BoolLit):
            return node.value

        # For complex expressions (arithmetic), re-evaluate — we can't trivially
        # get previous values.  Callers should use simple feature references in
        # crosses_above/below for meaningful semantics.
        return self.eval(node)

    # ---- function calls ----

    def _eval_function(self, node: FunctionCall) -> bool | float:
        args = [self.eval(a) for a in node.args]

        if node.name == "within":
            # within(value, low, high) → low <= value <= high
            if len(args) != 3:
                raise EvalError("within() requires exactly 3 arguments")
            return _num(args[1], "within") <= _num(args[0], "within") <= _num(args[2], "within")

        if node.name == "any_of":
            return any(_truthy(a) for a in args)

        if node.name == "all_of":
            return all(_truthy(a) for a in args)

        raise EvalError(f"Unknown function '{node.name}'")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truthy(val: bool | float) -> bool:
    if isinstance(val, bool):
        return val
    return val != 0.0


def _num(val: bool | float, ctx: str) -> float:
    if isinstance(val, bool):
        return float(val)
    return val


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def evaluate(compiled: CompiledExpr, snapshot: FeatureSnapshot) -> bool | float:
    """Evaluate *compiled* against *snapshot* and return a bool or float.

    Raises :class:`EvalError` on missing feature data or evaluation failure.
    """
    ev = _Evaluator(snapshot)
    return ev.eval(compiled.root)
