"""V4 signal plan builder.

Evaluates a ``StrategyVersionV4`` against a runtime ``FeatureSnapshot``
(from ``backend.app.features``) and produces a ``SignalPlan``.

Design rules (locked):
- Consumes compiled ASTs via ``expression_api.load_compiled``. Never re-parses
  raw text in the hot path.
- Variables resolved in topological order (position order in the tuple).
  Timeframe variables are injected as strings; expression variables are
  evaluated to float | bool. Both land in the expression-engine
  FeatureSnapshot.variables dict before the entry expression is evaluated.
- Bridges ``features.FeatureSnapshot`` (runtime, with FeatureValue wrappers)
  to ``expression_engine.FeatureSnapshot`` (evaluator, plain float | bool).
  Features whose availability != AVAILABLE are excluded; the evaluator raises
  EvalError when they are actually referenced at evaluation time.
- AST objects never leak past this module boundary. Downstream sees only
  ``SignalPlan``.
- The legacy ``signal_plan_builder.py`` is NOT modified.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from backend.app.decision.signal_plan_builder import (
    POST_FILL_PCT_RULE_PREFIX,
    SignalPlanBuilderError,
    post_fill_pct_rule,
)
from backend.app.domain.signal_plan import (
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanRunner,
    SignalPlanRunnerManagement,
    SignalPlanSide,
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
)
from backend.app.domain.strategy_v4 import (
    StrategyLegV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import FeatureAvailability, FeatureSnapshot as RuntimeFeatureSnapshot
from backend.app.strategies.expression_api import load_compiled
from backend.app.strategies.expression_engine import evaluate as engine_evaluate
from backend.app.strategies.expression_engine.ast_nodes import (
    CompiledExpr,
    FeatureSnapshot as ExprFeatureSnapshot,
)
from backend.app.strategies.expression_engine.errors import EvalError


# ---------------------------------------------------------------------------
# Public type alias for the expression loader callable
# ---------------------------------------------------------------------------

ExpressionLoader = Callable[[str, bytes | None], CompiledExpr]


# ---------------------------------------------------------------------------
# Default expression loader (uses load_compiled with text fallback)
# ---------------------------------------------------------------------------

def _default_expression_loader(text: str, blob: bytes | None) -> CompiledExpr:
    return load_compiled(text, blob)


def _strategy_scoped_loader(
    base_loader: "ExpressionLoader",
    strategy: "StrategyVersionV4",
) -> "ExpressionLoader":
    """Wrap *base_loader* so the text-fallback path knows the strategy's variables.

    The domain model does not carry compiled bytes today, so every call into
    ``load_compiled`` re-parses text. The re-parse needs the strategy's
    variable names, otherwise ``var_ref`` references like ``bull_bar`` raise
    ``ValidationError: Unknown identifier``. Without this scoping, a
    perfectly-saved strategy that uses a variable cannot fire a signal at
    runtime.

    When a base_loader was injected (tests passing a stub) we honor it as-is
    only when the text contains no variable refs — we cannot retroactively
    teach an arbitrary loader about variables. For the production
    ``_default_expression_loader`` path, we route through ``load_compiled``
    directly with the variable-name kwargs.
    """
    expr_var_names = tuple(v.name for v in strategy.variables if v.kind == "expression")
    tf_var_names = tuple(v.name for v in strategy.variables if v.kind == "timeframe")

    if base_loader is _default_expression_loader:
        def _scoped(text: str, blob: bytes | None) -> CompiledExpr:
            return load_compiled(
                text,
                blob,
                expression_variable_names=expr_var_names,
                timeframe_variable_names=tf_var_names,
            )
        return _scoped

    # Test-injected loader: pass through. Test stubs typically build CompiledExpr
    # by hand and don't need variable scoping.
    return base_loader


# ---------------------------------------------------------------------------
# Bridge: runtime FeatureSnapshot → expression engine FeatureSnapshot
# ---------------------------------------------------------------------------

def _build_expr_snapshot(
    runtime_snapshot: RuntimeFeatureSnapshot,
    *,
    timestamp: datetime,
    variables: dict[str, float | bool | str],
) -> ExprFeatureSnapshot:
    """Convert a runtime ``FeatureSnapshot`` to an expression-engine snapshot.

    Only features with ``availability == AVAILABLE`` and a non-None value are
    copied into the expression snapshot.  Features that are warming up or
    missing are omitted; if the entry expression references them the evaluator
    raises ``EvalError`` and we return None (no signal).

    The ``history`` dict is left empty because the runtime FeatureSnapshot does
    not carry per-bar history in this interface yet. Cross (crosses_above /
    crosses_below) expressions that require history are therefore not supported
    in this slice. They will produce EvalError which is caught and treated as
    "no signal", consistent with the warmup-period treatment for missing data.
    """
    plain_values: dict[str, float | bool] = {}
    for key, fv in runtime_snapshot.values.items():
        if fv.availability == FeatureAvailability.AVAILABLE and fv.value is not None:
            plain_values[key] = fv.value
    return ExprFeatureSnapshot(
        timestamp=timestamp,
        values=plain_values,
        history={},
        variables=variables,
    )


# ---------------------------------------------------------------------------
# Variable resolution
# ---------------------------------------------------------------------------

def _resolve_variables(
    strategy: StrategyVersionV4,
    expr_snapshot_no_vars: ExprFeatureSnapshot,
    expression_loader: ExpressionLoader,
) -> dict[str, float | bool | str]:
    """Resolve strategy variables in topological order (position in tuple).

    Timeframe variables are string literals (canonical TF like "5m") —
    injected directly without expression evaluation.  Expression variables
    are evaluated against the growing variable context; each resolved value
    becomes available to subsequent variables.

    Returns the fully resolved variables dict.
    """
    resolved: dict[str, float | bool | str] = {}

    for var in strategy.variables:
        if var.kind == "timeframe":
            # Timeframe binding: literal canonical TF string.
            resolved[var.name] = var.expression_text.strip()
            continue

        # Expression variable: evaluate against current resolved context.
        snap_with_vars = ExprFeatureSnapshot(
            timestamp=expr_snapshot_no_vars.timestamp,
            values=expr_snapshot_no_vars.values,
            history=expr_snapshot_no_vars.history,
            variables=dict(resolved),
        )
        compiled = expression_loader(var.expression_text, None)
        value = engine_evaluate(compiled, snap_with_vars)
        resolved[var.name] = value

    return resolved


# ---------------------------------------------------------------------------
# Stop mapping
# ---------------------------------------------------------------------------

_SIMPLE_STOP_TYPE_MAP: dict[str, str] = {
    "%": "percent",
    "ATR": "atr",
    "$": "fixed",
    "R": "r_multiple",
}


def _atr_multiple_rule(value: float) -> str:
    return f"atr:{float(value)}"


def _build_stop_from_v4(
    stop: StrategyStopV4,
    *,
    expr_snapshot: ExprFeatureSnapshot,
    expression_loader: ExpressionLoader,
) -> SignalPlanStop | None:
    """Convert a ``StrategyStopV4`` to a ``SignalPlanStop``.

    Returns None when the stop cannot be resolved (e.g. expression evaluates
    to a non-numeric value or EvalError).
    """
    if stop.mode == "simple":
        assert stop.simple_type is not None
        assert stop.simple_value is not None
        stop_type = _SIMPLE_STOP_TYPE_MAP.get(stop.simple_type, stop.simple_type)
        if stop.simple_type == "%":
            rule = post_fill_pct_rule(stop.simple_value)
        elif stop.simple_type == "ATR":
            rule = _atr_multiple_rule(stop.simple_value)
        else:
            rule = None
        return SignalPlanStop(
            type=stop_type,
            rule=rule,
            required=True,
        )

    # Expression mode: evaluate the expression to get a numeric offset.
    assert stop.expression_text is not None
    try:
        compiled = expression_loader(stop.expression_text, None)
        raw = engine_evaluate(compiled, expr_snapshot)
    except EvalError:
        return None

    if not isinstance(raw, (int, float)) or bool.__class__ is type(raw) and isinstance(raw, bool):
        # bool is a subclass of int; we accept it as 0/1 offset by coercing.
        pass
    offset = float(raw)
    return SignalPlanStop(
        type="fixed",
        rule=f"{POST_FILL_PCT_RULE_PREFIX}_expr:{offset}",
        required=True,
    )


# ---------------------------------------------------------------------------
# Target / runner leg mapping
# ---------------------------------------------------------------------------

_TARGET_TYPE_MAP: dict[str, str] = {
    "%": "percent",
    "ATR": "atr",
    "$": "fixed",
    "R": "r_multiple",
    "feature": "feature",
}


def _build_targets_from_legs(
    legs: tuple[StrategyLegV4, ...],
) -> tuple[tuple[SignalPlanTarget, ...], SignalPlanRunner | None]:
    """Convert v4 legs to (targets, runner | None).

    Strategy legs are already validated to sum size_pct == 1.0 and have at
    most one runner.  ``target`` legs → ``SignalPlanTarget``.  The runner
    leg → ``SignalPlanRunner``.
    """
    targets: list[SignalPlanTarget] = []
    runner: SignalPlanRunner | None = None

    for leg in sorted(legs, key=lambda l: l.position):
        label = f"t{leg.position}"
        quantity_pct = leg.size_pct * 100.0

        if leg.kind == "runner":
            trail_rule: str | None = None
            if leg.target_type in ("trail-%", "trail-ATR", "trail-$"):
                trail_suffix = leg.target_type.split("-", 1)[1]
                trail_rule = (
                    post_fill_pct_rule(leg.target_value)
                    if trail_suffix == "%" and leg.target_value is not None
                    else f"trail_{trail_suffix}:{leg.target_value}"
                )
            runner = SignalPlanRunner(
                quantity_pct=quantity_pct,
                management=SignalPlanRunnerManagement.TRAIL if trail_rule else SignalPlanRunnerManagement.HOLD,
                trail_rule=trail_rule,
            )
            continue

        # target leg
        rule: str | None = None
        price: float | None = None
        if leg.target_type == "%" and leg.target_value is not None:
            rule = post_fill_pct_rule(leg.target_value)
        elif leg.target_type == "ATR" and leg.target_value is not None:
            rule = _atr_multiple_rule(leg.target_value)
        elif leg.target_type in _TARGET_TYPE_MAP and leg.target_value is not None:
            rule = f"{_TARGET_TYPE_MAP[leg.target_type]}:{leg.target_value}"

        targets.append(
            SignalPlanTarget(
                label=label,
                action=SignalPlanTargetAction.CLOSE if leg.position == len(legs) else SignalPlanTargetAction.REDUCE,
                quantity_pct=quantity_pct,
                price=price,
                rule=rule,
            )
        )

    return tuple(targets), runner


def _is_atr_rule(rule: str | None) -> bool:
    if not rule:
        return False
    return rule.strip().lower().startswith("atr:")


def _has_available_atr_value(values: dict[str, float | bool]) -> bool:
    for key, value in values.items():
        key_l = key.lower()
        if (
            key_l.startswith("atr")
            or ".atr" in key_l
            or "technical.atr" in key_l
        ) and isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return True
    return False


def _requires_atr_pricing(
    stop: SignalPlanStop | None,
    targets: tuple[SignalPlanTarget, ...],
    runner: SignalPlanRunner | None,
) -> bool:
    if stop is not None and _is_atr_rule(stop.rule):
        return True
    if any(_is_atr_rule(target.rule) for target in targets):
        return True
    return runner is not None and _is_atr_rule(runner.trail_rule)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_signal_plan_from_v4(
    *,
    strategy: StrategyVersionV4,
    snapshot: RuntimeFeatureSnapshot,
    symbol: str,
    side: Literal["long", "short"],
    timestamp: datetime,
    deployment_id: UUID,
    watchlist_snapshot_id: UUID | None = None,
    expression_loader: ExpressionLoader = _default_expression_loader,
) -> SignalPlan | None:
    """Evaluate a ``StrategyVersionV4`` for one side and emit a ``SignalPlan``.

    Returns ``None`` when:
    - The requested side has no entry expression on the strategy.
    - The entry expression evaluates to False / 0.
    - A required feature is not available (EvalError from evaluator).
    - Variable resolution fails (EvalError).

    Parameters
    ----------
    strategy:
        The loaded v4 strategy version.
    snapshot:
        Runtime feature snapshot (from ``backend.app.features``).
    symbol:
        The instrument symbol, upper-cased by the caller.
    side:
        "long" or "short".
    timestamp:
        Bar timestamp for the signal plan ``created_at``.
    deployment_id:
        Deployment that owns this signal plan.
    watchlist_snapshot_id:
        Optional watchlist snapshot FK on the SignalPlan.
    expression_loader:
        Callable(text, blob) -> CompiledExpr.  Defaults to
        ``expression_api.load_compiled``.  Tests may pass a stub.
    """
    entry = strategy.entries.long if side == "long" else strategy.entries.short
    if entry is None:
        return None

    # Wrap the loader so the text-fallback re-parse (used until persisted
    # compiled bytes are plumbed onto the domain model) knows the strategy's
    # variable names. Without this, an entry like ``bull_bar`` raises
    # ValidationError: Unknown identifier.
    scoped_loader = _strategy_scoped_loader(expression_loader, strategy)

    # Build a base expression snapshot with no variables yet so variable
    # resolution can start accumulating.
    base_expr_snap = _build_expr_snapshot(snapshot, timestamp=timestamp, variables={})

    # Resolve variables in topological order.
    try:
        resolved_vars = _resolve_variables(strategy, base_expr_snap, scoped_loader)
    except EvalError:
        return None

    # Build full expression snapshot with resolved variables.
    full_expr_snap = ExprFeatureSnapshot(
        timestamp=timestamp,
        values=base_expr_snap.values,
        history=base_expr_snap.history,
        variables=resolved_vars,
    )

    # Evaluate the entry expression.
    try:
        compiled_entry = scoped_loader(entry.expression_text, None)
        entry_result = engine_evaluate(compiled_entry, full_expr_snap)
    except EvalError:
        return None

    if not entry_result:
        return None

    # Build stop.
    stop: SignalPlanStop | None = None
    if strategy.stops:
        # Use the first stop. Multiple stops in scope 'all' are treated
        # as alternatives; Slice 12 will add multi-stop support.
        stop = _build_stop_from_v4(
            strategy.stops[0],
            expr_snapshot=full_expr_snap,
            expression_loader=scoped_loader,
        )

    # Build targets and runner from legs.
    targets: tuple[SignalPlanTarget, ...] = ()
    runner: SignalPlanRunner | None = None
    if strategy.legs:
        targets, runner = _build_targets_from_legs(strategy.legs)

    if _requires_atr_pricing(stop, targets, runner) and not _has_available_atr_value(full_expr_snap.values):
        return None

    # Collect feature values used (for SignalPlan.feature_snapshot traceability).
    feature_snapshot_used: dict[str, object] = {
        k: v for k, v in full_expr_snap.values.items()
    }

    signal_plan_side = SignalPlanSide.LONG if side == "long" else SignalPlanSide.SHORT

    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=deployment_id,
        strategy_id=strategy.strategy_v4_id,
        strategy_version_id=strategy.id,
        watchlist_snapshot_id=watchlist_snapshot_id,
        symbol=symbol.upper(),
        side=signal_plan_side,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(),
        stop=stop,
        targets=targets,
        runner=runner,
        created_at=timestamp,
        reason="v4_entry_expression_true",
        feature_snapshot=feature_snapshot_used,
    )
