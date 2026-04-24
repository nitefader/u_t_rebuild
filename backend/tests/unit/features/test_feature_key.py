from __future__ import annotations

from backend.app.features import FeatureNamespace, FeatureScope, FeatureSpec, make_feature_key


def _ema_spec(params: dict[str, object], version: str = "v1") -> FeatureSpec:
    return FeatureSpec(
        kind="ema",
        namespace=FeatureNamespace.TECHNICAL,
        timeframe="5m",
        source="close",
        params=params,
        scope=FeatureScope.SYMBOL,
        version=version,
    )


def test_feature_key_is_deterministic_for_same_spec() -> None:
    spec = FeatureSpec(
        kind="close",
        namespace=FeatureNamespace.PRICE,
        timeframe="5m",
        source="close",
        scope=FeatureScope.SYMBOL,
    )

    assert make_feature_key(spec) == make_feature_key(spec)


def test_feature_key_canonicalizes_param_order() -> None:
    first = _ema_spec({"length": 20, "alpha": 0.5})
    second = _ema_spec({"alpha": 0.5, "length": 20})

    assert make_feature_key(first) == make_feature_key(second)


def test_feature_key_canonicalizes_integer_float_equivalence() -> None:
    first = _ema_spec({"length": 14})
    second = _ema_spec({"length": 14.0})

    assert make_feature_key(first) == make_feature_key(second)


def test_feature_key_changes_when_feature_version_changes() -> None:
    first = _ema_spec({"length": 20}, version="v1")
    second = _ema_spec({"length": 20}, version="v2")

    assert make_feature_key(first) != make_feature_key(second)
