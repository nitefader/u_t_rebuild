"""Semantic validator for expression ASTs.

validate() walks the AST and:
  1. Resolves TimeframedFeature nodes against the FeatureCatalog (checks name + arity).
  2. Resolves FeatureRef nodes (session.*, orb.*, prior_day.*, bar[-N].*).
  3. Resolves VariableRef nodes against the provided variable_names set.
  4. Collects feature_requirements (deduped) and variables_used.
  5. Raises ValidationError with all discovered issues if any are level="error".
"""
from __future__ import annotations

from typing import Iterable

from .ast_nodes import (
    AstNode,
    BinaryOp,
    BoolLit,
    FeatureRef,
    FunctionCall,
    NumberLit,
    TimeframedFeature,
    TimeframeVarFeature,
    UnaryOp,
    ValidatedAst,
    VariableRef,
)
from .errors import ValidationError, ValidationIssue
from .features import FeatureCatalog
from .timeframes import CANONICAL_TIMEFRAMES_ORDER

# ---------------------------------------------------------------------------
# Allowed bar lookback fields (mirrors parser._BAR_FIELDS)
# ---------------------------------------------------------------------------
_BAR_FIELDS: frozenset[str] = frozenset({"close", "open", "high", "low", "range", "body"})

# Namespaces that are handled as FeatureRef (non-timeframed)
_NON_TF_NAMESPACES: frozenset[str] = frozenset({"session", "orb", "prior_day", "bar"})


class _Validator:
    def __init__(
        self,
        catalog: FeatureCatalog,
        variable_names: frozenset[str],
        timeframe_variable_names: frozenset[str],
    ) -> None:
        self._catalog = catalog
        self._variable_names = variable_names
        self._timeframe_variable_names = timeframe_variable_names
        self._issues: list[ValidationIssue] = []
        # Use dicts keyed by repr to deduplicate while preserving order
        self._feature_reqs: dict[str, FeatureRef | TimeframedFeature] = {}
        self._variables_used: dict[str, str] = {}

    def _err(self, message: str, location: str = "") -> None:
        self._issues.append(ValidationIssue(level="error", message=message, location=location))

    def _warn(self, message: str, location: str = "") -> None:
        self._issues.append(ValidationIssue(level="warning", message=message, location=location))

    def _add_feature(self, node: FeatureRef | TimeframedFeature) -> None:
        key = repr(node)
        self._feature_reqs.setdefault(key, node)

    def validate(self, node: AstNode) -> None:
        """Walk the AST recursively."""
        if isinstance(node, NumberLit):
            return
        if isinstance(node, BoolLit):
            return
        if isinstance(node, VariableRef):
            self._validate_variable_ref(node)
        elif isinstance(node, FeatureRef):
            self._validate_feature_ref(node)
        elif isinstance(node, TimeframedFeature):
            self._validate_timeframed_feature(node)
        elif isinstance(node, TimeframeVarFeature):
            self._validate_timeframe_var_feature(node)
        elif isinstance(node, UnaryOp):
            self.validate(node.operand)
        elif isinstance(node, BinaryOp):
            self.validate(node.left)
            self.validate(node.right)
        elif isinstance(node, FunctionCall):
            for arg in node.args:
                self.validate(arg)
        else:
            self._err(f"Unknown AST node type: {type(node).__name__}")

    def _validate_variable_ref(self, node: VariableRef) -> None:
        if node.name in self._timeframe_variable_names:
            self._err(
                f"Timeframe variable '{node.name}' must be used as a timeframe prefix "
                f"({node.name}.<feature>), not as a bare value reference",
                location=node.name,
            )
            return
        if node.name not in self._variable_names:
            # Could be an undeclared variable or a bare feature name like "volume"
            # that the parser emitted as VariableRef.  Check catalog for bare tf-features.
            spec = self._catalog.get(node.name)
            if spec is not None and spec.is_timeframed:
                self._err(
                    f"Feature '{node.name}' requires a timeframe prefix (e.g. 5m.{node.name})",
                    location=node.name,
                )
            else:
                self._err(
                    f"Unknown identifier '{node.name}' — not a variable, feature, or keyword",
                    location=node.name,
                )
        else:
            self._variables_used.setdefault(node.name, node.name)

    def _validate_feature_ref(self, node: FeatureRef) -> None:
        # bar[-N].field pattern
        if node.bar_offset is not None:
            if node.bar_field not in _BAR_FIELDS:
                self._err(
                    f"Unknown bar field '{node.bar_field}'; allowed: {sorted(_BAR_FIELDS)}",
                    location=f"bar[{node.bar_offset}].{node.bar_field}",
                )
            # Validate any args (there shouldn't be any for bar lookback)
            for arg in node.args:
                self.validate(arg)
            self._add_feature(node)
            return

        # Standard namespace feature: session.is_open, orb.high(15), etc.
        if len(node.path) < 2:
            self._err(
                f"Feature reference '{'.'.join(node.path)}' must have a namespace prefix",
                location=".".join(node.path),
            )
            return

        namespace = node.path[0]
        name = node.path[1]
        catalog_key = f"{namespace}.{name}"

        if namespace not in _NON_TF_NAMESPACES:
            self._err(
                f"Unknown namespace '{namespace}' in '{'.'.join(node.path)}'",
                location=catalog_key,
            )
            return

        spec = self._catalog.get(catalog_key)
        if spec is None:
            self._err(
                f"Unknown feature '{catalog_key}'; not in catalog",
                location=catalog_key,
            )
            return

        # Arity check
        n_args = len(node.args)
        if spec.arity >= 0 and n_args != spec.arity:
            self._err(
                f"Feature '{catalog_key}' expects {spec.arity} arg(s), got {n_args}",
                location=catalog_key,
            )

        for arg in node.args:
            self.validate(arg)

        self._add_feature(node)

    def _validate_timeframed_feature(self, node: TimeframedFeature) -> None:
        spec = self._catalog.get(node.name)
        if spec is None:
            self._err(
                f"Unknown feature '{node.name}'; not in catalog",
                location=f"{node.timeframe}.{node.name}",
            )
            return

        if not spec.is_timeframed:
            self._err(
                f"Feature '{node.name}' is not a timeframed feature "
                f"(use '{spec.namespace}.{spec.name}' instead)",
                location=f"{node.timeframe}.{node.name}",
            )
            return

        n_args = len(node.args)
        if spec.arity >= 0 and n_args != spec.arity:
            self._err(
                f"Feature '{node.timeframe}.{node.name}' expects {spec.arity} arg(s), got {n_args}",
                location=f"{node.timeframe}.{node.name}",
            )

        for arg in node.args:
            self.validate(arg)

        self._add_feature(node)

    def _validate_timeframe_var_feature(self, node: TimeframeVarFeature) -> None:
        if node.timeframe_variable not in self._timeframe_variable_names:
            self._err(
                f"Unknown timeframe variable '{node.timeframe_variable}'",
                location=node.timeframe_variable,
            )
            return

        spec = self._catalog.get(node.name)
        if spec is None:
            self._err(
                f"Unknown feature '{node.name}'; not in catalog",
                location=f"{node.timeframe_variable}.{node.name}",
            )
            return

        if not spec.is_timeframed:
            self._err(
                f"Feature '{node.name}' is not a timeframed feature "
                f"(use '{spec.namespace}.{spec.name}' instead)",
                location=f"{node.timeframe_variable}.{node.name}",
            )
            return

        n_args = len(node.args)
        if spec.arity >= 0 and n_args != spec.arity:
            self._err(
                f"Feature '{node.timeframe_variable}.{node.name}' expects "
                f"{spec.arity} arg(s), got {n_args}",
                location=f"{node.timeframe_variable}.{node.name}",
            )

        for arg in node.args:
            self.validate(arg)

        for tf in CANONICAL_TIMEFRAMES_ORDER:
            synth = TimeframedFeature(timeframe=tf, name=node.name, args=node.args)
            self._add_feature(synth)

    def build_result(self, root: AstNode) -> ValidatedAst:
        errors = [i for i in self._issues if i.level == "error"]
        if errors:
            raise ValidationError(self._issues)
        return ValidatedAst(
            root=root,
            feature_requirements=tuple(self._feature_reqs.values()),
            variables_used=tuple(self._variables_used.keys()),
        )


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def validate(
    ast: AstNode,
    catalog: FeatureCatalog,
    variable_names: Iterable[str] = (),
    *,
    timeframe_variable_names: Iterable[str] = (),
) -> ValidatedAst:
    """Validate *ast* against *catalog* and *variable_names*.

    *variable_names* are expression-valued variables (numbers / booleans).
    *timeframe_variable_names* are variables bound to canonical timeframe strings.

    Returns a :class:`ValidatedAst` with deduplicated feature_requirements
    and variables_used on success.

    Raises :class:`ValidationError` with all issues on failure.
    """
    vnames = frozenset(variable_names)
    tfnames = frozenset(timeframe_variable_names)
    overlap = vnames & tfnames
    if overlap:
        joint = ", ".join(sorted(overlap))
        raise ValidationError(
            [
                ValidationIssue(
                    level="error",
                    message=f"A name cannot be both an expression variable and timeframe variable: {joint}",
                    location=joint,
                )
            ]
        )
    v = _Validator(catalog, vnames, tfnames)
    v.validate(ast)
    return v.build_result(ast)
