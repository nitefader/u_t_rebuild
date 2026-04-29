from __future__ import annotations

import pytest

from backend.app.features import FeatureNamespace, FeatureParseError, FeatureScope, FeatureValidationError, parse_feature_expression


@pytest.mark.parametrize(
    ("expression", "kind", "timeframe", "lookback"),
    [
        ("5m.close[0]", "close", "5m", 0),
        ("5m.close[1]", "close", "5m", 1),
        ("1d.high[0]", "high", "1d", 0),
        ("5m.close", "close", "5m", 0),
    ],
)
def test_valid_price_feature_parsing(expression: str, kind: str, timeframe: str, lookback: int) -> None:
    spec = parse_feature_expression(expression)

    assert spec.kind == kind
    assert spec.timeframe == timeframe
    assert spec.lookback == lookback
    assert spec.namespace == FeatureNamespace.PRICE
    assert spec.scope == FeatureScope.SYMBOL


def test_valid_technical_param_parsing() -> None:
    spec = parse_feature_expression("5m.ema:length=20[0]")

    assert spec.kind == "ema"
    assert spec.timeframe == "5m"
    assert spec.params["length"] == 20
    assert spec.namespace == FeatureNamespace.TECHNICAL


def test_valid_session_param_parsing() -> None:
    spec = parse_feature_expression("15m.opening_range_high:session=regular,window_minutes=15")

    assert spec.kind == "opening_range_high"
    assert spec.timeframe == "15m"
    assert spec.params["session"] == "regular"
    assert spec.params["window_minutes"] == 15
    assert spec.namespace == FeatureNamespace.SESSION
    assert spec.scope == FeatureScope.SESSION


@pytest.mark.parametrize(
    "expression",
    [
        "",
        " 5m.close[0]",
        "5m.close[0] ",
        "5m..close[0]",
        "5m.close[]",
        "5m.close[-1]",
        "5m.close[current]",
        "5m.close[01]",
        "5m.close:length=20:",
        "5m.ema:length[0]",
        "5m.ema:length=[0]",
        "5m.ema:length=20,[0]",
        "5m.EMA:length=20[0]",
    ],
)
def test_invalid_syntax_rejection(expression: str) -> None:
    with pytest.raises(FeatureParseError):
        parse_feature_expression(expression)


def test_invalid_param_rejection() -> None:
    with pytest.raises(FeatureValidationError):
        parse_feature_expression("5m.ema:period=20[0]")


def test_unsupported_feature_rejection() -> None:
    with pytest.raises(FeatureValidationError):
        parse_feature_expression("5m.bollinger_bands:length=10[0]")


@pytest.mark.parametrize("expression", ["60m.close[0]", "5min.close[0]", "day.high[0]", "1D.high[0]"])
def test_invalid_timeframe_rejection(expression: str) -> None:
    with pytest.raises((FeatureParseError, FeatureValidationError)):
        parse_feature_expression(expression)


def test_duplicate_param_rejection() -> None:
    with pytest.raises(FeatureParseError):
        parse_feature_expression("5m.ema:length=20,length=30[0]")
