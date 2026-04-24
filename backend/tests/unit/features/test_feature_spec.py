from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.features import FeatureNamespace, FeatureScope, FeatureSpec


def test_feature_spec_is_immutable() -> None:
    spec = FeatureSpec(
        kind="close",
        namespace=FeatureNamespace.PRICE,
        timeframe="5m",
        source="close",
        scope=FeatureScope.SYMBOL,
    )

    with pytest.raises(ValidationError):
        spec.timeframe = "1d"  # type: ignore[misc]


def test_feature_spec_rejects_timeframe_alias() -> None:
    with pytest.raises(ValidationError):
        FeatureSpec(
            kind="close",
            namespace=FeatureNamespace.PRICE,
            timeframe="60m",
            source="close",
            scope=FeatureScope.SYMBOL,
        )


def test_feature_spec_rejects_negative_lookback() -> None:
    with pytest.raises(ValidationError):
        FeatureSpec(
            kind="close",
            namespace=FeatureNamespace.PRICE,
            timeframe="5m",
            source="close",
            lookback=-1,
            scope=FeatureScope.SYMBOL,
        )


def test_portfolio_feature_requires_portfolio_scope() -> None:
    with pytest.raises(ValidationError):
        FeatureSpec(
            kind="open_risk_pct",
            namespace=FeatureNamespace.PORTFOLIO,
            timeframe="1m",
            source="portfolio",
            scope=FeatureScope.SYMBOL,
        )
