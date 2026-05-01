"""Expression API service layer.

Thin wrappers around expression_engine.  Not FastAPI routes.
Pure Python service functions that HTTP routes delegate to.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from typing import Iterable

from backend.app.strategies.expression_engine import (
    ParseError,
    ValidationError,
    compile,
    default_catalog,
    evaluate,
    parse,
    validate,
    mirror_long_to_short,
    CompiledExpr,
    FeatureRef,
    NumberLit,
    TimeframedFeature,
)
from backend.app.strategies.expression_engine.features import FeatureSpec


# ---------------------------------------------------------------------------
# DTO types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationIssueDTO:
    level: str          # "error" | "warning"
    message: str
    line: int | None
    col: int | None


@dataclass(frozen=True)
class FeatureRequirementDTO:
    key: str            # canonical key: "5m.ema(9)" for tf, "session.is_open" for non-tf
    name: str           # "ema"
    namespace: str | None   # "" for tf, "session" / "orb" / etc.
    timeframe: str | None   # "5m" or None
    args: tuple[float, ...]


@dataclass(frozen=True)
class ValidateResult:
    valid: bool
    errors: tuple[ValidationIssueDTO, ...]
    warnings: tuple[ValidationIssueDTO, ...]
    feature_requirements: tuple[FeatureRequirementDTO, ...]
    variables_used: tuple[str, ...]


@dataclass(frozen=True)
class CatalogEntryDTO:
    key: str            # "ema" or "session.is_open"
    name: str
    namespace: str
    timeframe_bound: bool
    arity: int
    arg_names: tuple[str, ...]
    arg_defaults: tuple[float | int, ...]
    return_type: str
    description: str
    category: str       # "trend"|"momentum"|"volatility"|"volume"|"bb"|"time"|"bar"|"other"


@dataclass(frozen=True)
class MirrorResult:
    mirrored_text: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _arg_to_float(arg: object) -> float:
    """Convert a NumberLit to float.  For any other node type use 0.0 as fallback."""
    if isinstance(arg, NumberLit):
        return float(arg.value)
    # Non-literal args are unsupported in v1; use deterministic fallback.
    return 0.0


def _build_feature_key(node: FeatureRef | TimeframedFeature) -> str:
    """Build the canonical display key for a feature requirement.

    TimeframedFeature(timeframe="5m", name="ema", args=(NumberLit(9),)) -> "5m.ema(9)"
    FeatureRef(path=("session","is_open"), args=())                      -> "session.is_open"
    """
    def fmt(arg: object) -> str:
        if isinstance(arg, NumberLit):
            v = arg.value
            return str(int(v)) if v == int(v) else str(v)
        return repr(arg)

    if isinstance(node, TimeframedFeature):
        args_str = ",".join(fmt(a) for a in node.args)
        if args_str:
            return f"{node.timeframe}.{node.name}({args_str})"
        return f"{node.timeframe}.{node.name}"

    # FeatureRef
    if node.bar_offset is not None:
        return f"bar.{node.bar_field}"

    ns = node.path[0] if node.path else ""
    name = node.path[1] if len(node.path) > 1 else ""
    args_str = ",".join(fmt(a) for a in node.args)
    if args_str:
        return f"{ns}.{name}({args_str})"
    return f"{ns}.{name}"


def _to_feature_requirement_dto(node: FeatureRef | TimeframedFeature) -> FeatureRequirementDTO:
    key = _build_feature_key(node)
    if isinstance(node, TimeframedFeature):
        return FeatureRequirementDTO(
            key=key,
            name=node.name,
            namespace=None,
            timeframe=node.timeframe,
            args=tuple(_arg_to_float(a) for a in node.args),
        )
    # FeatureRef
    if node.bar_offset is not None:
        return FeatureRequirementDTO(
            key=key,
            name=node.bar_field or "",
            namespace="bar",
            timeframe=None,
            args=tuple(_arg_to_float(a) for a in node.args),
        )
    ns = node.path[0] if node.path else ""
    name = node.path[1] if len(node.path) > 1 else ""
    return FeatureRequirementDTO(
        key=key,
        name=name,
        namespace=ns,
        timeframe=None,
        args=tuple(_arg_to_float(a) for a in node.args),
    )


def _catalog_spec_to_dto(spec: FeatureSpec) -> CatalogEntryDTO:
    if spec.is_timeframed:
        key = spec.name
        namespace = ""
    elif spec.namespace:
        key = f"{spec.namespace}.{spec.name}"
        namespace = spec.namespace
    else:
        key = spec.name
        namespace = ""

    return CatalogEntryDTO(
        key=key,
        name=spec.name,
        namespace=namespace,
        timeframe_bound=spec.is_timeframed,
        arity=spec.arity,
        arg_names=spec.arg_names,
        arg_defaults=spec.arg_defaults,
        return_type=spec.return_type,
        description=spec.description,
        category=spec.category,
    )


# ---------------------------------------------------------------------------
# Internal blank-source helper
# ---------------------------------------------------------------------------

def _is_blank_source(src: str) -> bool:
    """Return True if *src* contains nothing meaningful after stripping line
    comments (``// ...``) and whitespace.

    An empty / whitespace-only / comment-only source is semantically "no
    condition", not a parse error.
    """
    import re as _re
    without_comments = _re.sub(r"//[^\n]*", "", src)
    return not without_comments.strip()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def validate_expression(
    src: str,
    variable_names: Iterable[str] = (),
    *,
    timeframe_variable_names: Iterable[str] = (),
) -> ValidateResult:
    """Parse and validate *src*.

    Always returns a ValidateResult (never raises).  Errors and warnings are
    returned as DTOs in the result.

    Empty / whitespace-only / comment-only input is treated as valid (no
    condition) rather than a parse error.
    """
    if _is_blank_source(src):
        return ValidateResult(
            valid=True,
            errors=(),
            warnings=(),
            feature_requirements=(),
            variables_used=(),
        )

    catalog = default_catalog()
    var_names = list(variable_names)
    tf_names = frozenset(timeframe_variable_names)

    try:
        ast = parse(src, timeframe_variable_names=tf_names)
    except ParseError as exc:
        issue = ValidationIssueDTO(
            level="error",
            message=exc.message,
            line=exc.line,
            col=exc.col,
        )
        return ValidateResult(
            valid=False,
            errors=(issue,),
            warnings=(),
            feature_requirements=(),
            variables_used=(),
        )

    try:
        vast = validate(ast, catalog, var_names, timeframe_variable_names=tf_names)
    except ValidationError as exc:
        errors: list[ValidationIssueDTO] = []
        warnings: list[ValidationIssueDTO] = []
        for issue in exc.issues:
            dto = ValidationIssueDTO(level=issue.level, message=issue.message, line=None, col=None)
            if issue.level == "error":
                errors.append(dto)
            else:
                warnings.append(dto)
        return ValidateResult(
            valid=False,
            errors=tuple(errors),
            warnings=tuple(warnings),
            feature_requirements=(),
            variables_used=(),
        )

    # Deduplicate feature_requirements by key, preserve insertion order.
    seen: dict[str, FeatureRequirementDTO] = {}
    for node in vast.feature_requirements:
        dto = _to_feature_requirement_dto(node)
        seen.setdefault(dto.key, dto)

    return ValidateResult(
        valid=True,
        errors=(),
        warnings=(),
        feature_requirements=tuple(seen.values()),
        variables_used=vast.variables_used,
    )


def list_features() -> tuple[CatalogEntryDTO, ...]:
    """Return all features from the default catalog as DTOs."""
    catalog = default_catalog()
    return tuple(_catalog_spec_to_dto(spec) for spec in catalog.all())


def mirror_expression(src: str) -> MirrorResult:
    """Mirror *src* from long to short.

    Raises ParseError if the expression cannot be mirrored.
    """
    mirrored = mirror_long_to_short(src)
    return MirrorResult(mirrored_text=mirrored)


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def compile_for_storage(validated: object) -> bytes:
    """Pickle a CompiledExpr to bytes using protocol 4."""
    return pickle.dumps(validated, protocol=4)


def load_compiled(
    text: str,
    blob: bytes | None,
    *,
    expression_variable_names: Iterable[str] = (),
    timeframe_variable_names: Iterable[str] = (),
) -> CompiledExpr:
    """Load a CompiledExpr from *blob*, falling back to re-parsing *text*.

    On ANY unpickling exception (schema drift, corrupt bytes, etc.) the
    function re-parses and recompiles *text* instead of raising.

    text is canonical; blob is a regenerable cache only.
    """
    if blob is not None:
        try:
            result = pickle.loads(blob)  # noqa: S301 -- controlled internal bytes
            if isinstance(result, CompiledExpr):
                return result
        except Exception:  # noqa: BLE001 -- intentional broad catch for drift/corruption
            pass

    # Fallback: parse -> validate -> compile
    catalog = default_catalog()
    tf_names = frozenset(timeframe_variable_names)
    ast = parse(text, timeframe_variable_names=tf_names)
    vast = validate(
        ast,
        catalog,
        expression_variable_names,
        timeframe_variable_names=tf_names,
    )
    return compile(vast)
