from __future__ import annotations

import re
from typing import Any

from .registry import FeatureRegistry, registry
from .spec import FeatureSpec, FeatureValidationError


_FEATURE_EXPR_RE = re.compile(
    r"^(?P<timeframe>[A-Za-z0-9]+)\."
    r"(?P<kind>[a-z][a-z0-9_]*)"
    r"(?::(?P<params>[a-z][a-z0-9_]*=[^,\[\]:]+(?:,[a-z][a-z0-9_]*=[^,\[\]:]+)*))?"
    r"(?:\[(?P<lookback>0|[1-9][0-9]*)\])?$"
)


class FeatureParseError(ValueError):
    """Raised when a feature expression does not match canonical syntax."""


def parse_param_value(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        raise FeatureParseError("feature param values cannot be empty")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if re.fullmatch(r"-?[0-9]+\.[0-9]+", value):
        return float(value)
    return value.lower()


def parse_params(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    params: dict[str, Any] = {}
    for part in raw.split(","):
        if "=" not in part:
            raise FeatureParseError(f"invalid feature param segment '{part}'")
        key, value = part.split("=", 1)
        if key in params:
            raise FeatureParseError(f"duplicate feature param '{key}'")
        params[key] = parse_param_value(value)
    return params


def parse_feature_expression(
    expression: str,
    feature_registry: FeatureRegistry = registry,
    *,
    default_timeframe: str | None = None,
) -> FeatureSpec:
    """Parse canonical feature syntax into a registry-validated FeatureSpec."""

    if expression.strip() != expression or not expression:
        raise FeatureParseError("feature expression must be non-empty and contain no surrounding whitespace")
    if default_timeframe is not None and "." not in expression:
        expression = f"{default_timeframe}.{expression}"
    match = _FEATURE_EXPR_RE.fullmatch(expression)
    if not match:
        raise FeatureParseError(f"invalid feature expression syntax '{expression}'")

    timeframe = match.group("timeframe")
    kind = match.group("kind")
    params = parse_params(match.group("params"))
    lookback = int(match.group("lookback") or 0)

    try:
        return feature_registry.create_spec(kind=kind, timeframe=timeframe, params=params, lookback=lookback)
    except FeatureValidationError:
        raise
