from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.features import FeatureNamespace, FeatureScope, FeatureSpec, FeatureValidationError, make_feature_key, registry


def test_feature_key_determinism_contract() -> None:
    first = FeatureSpec(
        kind="ema",
        namespace=FeatureNamespace.TECHNICAL,
        timeframe="5m",
        source="close",
        params={"length": 20, "alpha": 0.5},
        scope=FeatureScope.SYMBOL,
    )
    second = FeatureSpec(
        kind="ema",
        namespace=FeatureNamespace.TECHNICAL,
        timeframe="5m",
        source="close",
        params={"alpha": 0.5, "length": 20.0},
        scope=FeatureScope.SYMBOL,
    )

    assert make_feature_key(first) == make_feature_key(second)
    assert make_feature_key(first) == make_feature_key(first)


def test_invalid_feature_rejection_contract() -> None:
    with pytest.raises(FeatureValidationError, match="unsupported feature"):
        registry.create_spec(kind="supertrend", timeframe="5m")


@pytest.mark.parametrize("timeframe", ["60m", "5min", "day", "1D"])
def test_timeframe_validation_rejects_aliases_contract(timeframe: str) -> None:
    with pytest.raises((FeatureValidationError, ValidationError)):
        registry.create_spec(kind="close", timeframe=timeframe)
