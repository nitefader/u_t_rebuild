from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

from .spec import FeatureSpec


def canonicalize_param_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else float(Decimal(str(value)).normalize())
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, list | tuple):
        return [canonicalize_param_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k).strip().lower(): canonicalize_param_value(value[k]) for k in sorted(value)}
    return value


def canonicalize_params(params: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).strip().lower(): canonicalize_param_value(params[key]) for key in sorted(params)}


def canonical_params_json(params: Mapping[str, Any]) -> str:
    return json.dumps(canonicalize_params(params), sort_keys=True, separators=(",", ":"))


def make_feature_key(spec: FeatureSpec) -> str:
    """Return the deterministic identity key for one FeatureSpec."""

    return (
        f"{spec.version}|{spec.scope.value}|{spec.timeframe}|"
        f"{spec.namespace.value}.{spec.kind}|source={spec.source}|"
        f"params={canonical_params_json(spec.params)}|lookback={spec.lookback}|shift={spec.shift}"
    )
