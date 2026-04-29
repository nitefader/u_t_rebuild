from __future__ import annotations

import pytest
from backend.app.features import FeatureNamespace, FeatureScope, FeatureValidationError, registry


@pytest.mark.parametrize(
    "kind",
    [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "sma",
        "ema",
        "rsi",
        "atr",
        "vwap",
        "highest",
        "lowest",
        "session_state",
        "regular_session_high_so_far",
        "regular_session_low_so_far",
        "opening_range_high",
        "opening_range_low",
        "opening_range_mid",
        "opening_range_width",
        "opening_range_width_pct",
        "opening_range_complete",
        "prior_day_high",
        "prior_day_low",
        "prior_day_close",
        "gap_pct",
        "gross_exposure_pct",
        "net_exposure_pct",
        "open_risk_pct",
        "pending_open_risk_pct",
        "symbol_concentration_pct",
        "new_open_slots_remaining",
        "broker_sync_stale",
        "global_kill_active",
        "account_pause_active",
        "deployment_pause_active",
    ],
)
def test_registry_accepts_only_approved_initial_features(kind: str) -> None:
    assert registry.get(kind).kind == kind


def test_registry_rejects_unsupported_feature() -> None:
    with pytest.raises(FeatureValidationError):
        registry.get("bollinger_bands")


def test_registry_rejects_invalid_param_name() -> None:
    with pytest.raises(FeatureValidationError):
        registry.create_spec(kind="ema", timeframe="5m", params={"period": 20})


def test_registry_injects_default_params() -> None:
    spec = registry.create_spec(kind="ema", timeframe="5m")

    assert spec.params["length"] == 20


def test_registry_rejects_timeframe_alias() -> None:
    with pytest.raises(FeatureValidationError):
        registry.create_spec(kind="close", timeframe="60m")


def test_registry_creates_portfolio_feature_with_portfolio_scope() -> None:
    spec = registry.create_spec(kind="open_risk_pct", timeframe="1m")

    assert spec.namespace == FeatureNamespace.PORTFOLIO
    assert spec.scope == FeatureScope.PORTFOLIO


def test_registry_reports_consumer_support() -> None:
    registry.require_consumer_support("close", "chart_lab")
    registry.require_consumer_support("close", "sim_replay")
    registry.require_consumer_support("close", "backtest")


def test_registry_catalog_is_public_safe_metadata() -> None:
    catalog = registry.catalog()

    assert any(item["kind"] == "close" for item in catalog)
    assert all("description" in item for item in catalog)
    assert all("supported_consumers" in item for item in catalog)
