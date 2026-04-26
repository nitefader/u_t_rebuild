from __future__ import annotations

import pytest

from backend.app.market_data import (
    CostClass,
    DataConsumer,
    DataIntent,
    DataIntentMode,
    DataPurpose,
    LatencyClass,
    MarketDataCapabilities,
    MarketDataCatalogError,
    MarketDataServiceCatalog,
    MarketDataServiceWrite,
    MarketDataValidationStatus,
    Provider,
    ResolveMarketDataRequest,
    SelectionStrategy,
    ServicePurpose,
    ServiceStatus,
    Timeframe,
)
from backend.app.market_data.validation import MarketDataValidationResult, alpaca_capabilities


class FakeMarketDataValidator:
    def __init__(self, status: MarketDataValidationStatus = MarketDataValidationStatus.VALID) -> None:
        self.status = status

    def validate(self, **kwargs):
        if kwargs["provider"] == "yahoo":
            from backend.app.market_data.validation import yahoo_capabilities

            return MarketDataValidationResult(MarketDataValidationStatus.VALID, "yahoo ok", yahoo_capabilities())
        if not kwargs["has_api_key"] or not kwargs["has_api_secret"]:
            return MarketDataValidationResult(MarketDataValidationStatus.MISSING_CREDENTIALS, "missing", alpaca_capabilities())
        return MarketDataValidationResult(self.status, self.status.value, alpaca_capabilities())


class LearnedIntradayLimitValidator:
    def validate(self, **kwargs):
        return MarketDataValidationResult(
            MarketDataValidationStatus.VALID,
            "provider validated with historical daily coverage only",
            MarketDataCapabilities(
                supports_historical=True,
                supports_streaming=False,
                supports_intraday=False,
                supports_daily=True,
                supports_weekly=True,
                supports_monthly=True,
                supports_long_range_history=True,
                cost_class=CostClass.FREE,
                latency_class=LatencyClass.DELAYED,
            ),
            "validation:learned-limit",
            ("Validation learned that this provider cannot satisfy intraday requests.",),
        )


def test_market_data_crud_defaults_validation_and_resolver(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json", validator=FakeMarketDataValidator())

    alpaca = catalog.create_service(
        MarketDataServiceWrite(name="Alpaca Main", provider="alpaca", api_key="abcdef", api_secret="abcdefgh")
    )
    yahoo = catalog.create_service(MarketDataServiceWrite(name="Yahoo Historical", provider="yahoo"))
    assert len(catalog.list_services().services) == 2
    assert catalog.get_service(alpaca.id).name == "Alpaca Main"
    assert alpaca.credentials_ref
    assert "abcdef" not in alpaca.model_dump_json()

    updated = catalog.update_service(
        alpaca.id,
        MarketDataServiceWrite(name="Alpaca Edited", provider="alpaca", api_key="new-key", api_secret="new-secret"),
    )
    assert updated.name == "Alpaca Edited"

    with pytest.raises(ValueError):
        MarketDataServiceWrite(name="Bad", provider="alpaca", api_key="********", api_secret="********")

    alpaca = catalog.validate_service(alpaca.id)
    yahoo = catalog.validate_service(yahoo.id)
    assert alpaca.status == ServiceStatus.VALID
    assert yahoo.capabilities.supports_streaming is False

    default_alpaca = catalog.set_default(alpaca.id)
    assert default_alpaca.is_default is True
    default_yahoo = catalog.set_default(yahoo.id)
    assert default_yahoo.is_default is True
    assert catalog.get_service(alpaca.id).is_default is False

    disabled = catalog.disable_service(yahoo.id)
    assert disabled.status == ServiceStatus.DISABLED
    assert disabled.is_default is False

    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )
    result = catalog.resolve(ResolveMarketDataRequest(intent=intent, selection_strategy=SelectionStrategy.AUTO))
    head = result.per_symbol_rows[0]
    assert head.selected_service_id == str(alpaca.id)
    assert all(
        candidate.service_id != str(yahoo.id) or candidate.reason_code == "OPERATOR_VETO"
        for candidate in head.rejected_providers
    )


def test_invalid_market_data_service_cannot_be_default(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=FakeMarketDataValidator(MarketDataValidationStatus.INVALID),
    )
    alpaca = catalog.create_service(
        MarketDataServiceWrite(name="Alpaca", provider="alpaca", api_key="abcdef", api_secret="abcdefgh")
    )
    catalog.validate_service(alpaca.id)

    with pytest.raises(MarketDataCatalogError, match="invalid service"):
        catalog.set_default(alpaca.id)


def test_alpaca_missing_and_invalid_validation_statuses(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    missing = catalog.create_service(MarketDataServiceWrite(name="Alpaca", provider="alpaca"))
    assert catalog.validate_service(missing.id).validation_status == MarketDataValidationStatus.MISSING_CREDENTIALS

    invalid = catalog.create_service(
        MarketDataServiceWrite(name="Bad Alpaca", provider="alpaca", api_key="x", api_secret="y")
    )
    assert catalog.validate_service(invalid.id).validation_status == MarketDataValidationStatus.INVALID


def test_validation_learns_capabilities_and_resolver_hard_rejects_incompatible_service(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=LearnedIntradayLimitValidator(),
    )
    learned = catalog.create_service(MarketDataServiceWrite(name="Learned Historical", provider="future"))

    validated = catalog.validate_service(learned.id)
    assert validated.capability_source == "validation:learned-limit"
    assert validated.capabilities.supports_intraday is False
    assert validated.capability_notes == ("Validation learned that this provider cannot satisfy intraday requests.",)

    intent = DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        requires_intraday=True,
        purpose=DataPurpose.BACKTEST,
    )
    result = catalog.resolve(ResolveMarketDataRequest(intent=intent, selection_strategy=SelectionStrategy.AUTO))
    assert result.decision == "rejected"
    assert result.per_symbol_rows[0].rejected_providers[0].reason_code == "UNSUPPORTED_TIMEFRAME"


def test_set_default_for_assigns_purpose_and_strips_from_other_services(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json", validator=FakeMarketDataValidator())
    a = catalog.create_service(
        MarketDataServiceWrite(name="A", provider="alpaca", api_key="aaaaaa", api_secret="aaaaaaaa")
    )
    b = catalog.create_service(
        MarketDataServiceWrite(name="B", provider="alpaca", api_key="bbbbbb", api_secret="bbbbbbbb")
    )
    catalog.validate_service(a.id)
    catalog.validate_service(b.id)

    catalog.set_default_for(a.id, (ServicePurpose.LIVE_STREAMING, ServicePurpose.RUNTIME_TRADING))
    catalog.set_default_for(b.id, (ServicePurpose.LIVE_STREAMING,))

    a_after = catalog.get_service(a.id)
    b_after = catalog.get_service(b.id)
    # B took live_streaming away from A; A keeps runtime_trading.
    assert ServicePurpose.LIVE_STREAMING not in a_after.default_for
    assert ServicePurpose.RUNTIME_TRADING in a_after.default_for
    assert b_after.default_for == (ServicePurpose.LIVE_STREAMING,)


def test_create_service_with_initial_default_for_tags(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json", validator=FakeMarketDataValidator())
    a = catalog.create_service(
        MarketDataServiceWrite(name="A", provider="alpaca", api_key="aaaaaa", api_secret="aaaaaaaa")
    )
    b = catalog.create_service(
        MarketDataServiceWrite(
            name="B",
            provider="alpaca",
            api_key="bbbbbb",
            api_secret="bbbbbbbb",
            default_for=(ServicePurpose.TEST_STREAMING,),
        )
    )
    assert ServicePurpose.TEST_STREAMING in catalog.get_service(b.id).default_for
    # A still has no tags because B claimed test_streaming on creation.
    assert ServicePurpose.TEST_STREAMING not in catalog.get_service(a.id).default_for


def test_find_default_for_returns_tagged_service_and_skips_disabled(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json", validator=FakeMarketDataValidator())
    a = catalog.create_service(
        MarketDataServiceWrite(name="A", provider="alpaca", api_key="aaaaaa", api_secret="aaaaaaaa")
    )
    catalog.validate_service(a.id)
    catalog.set_default_for(a.id, (ServicePurpose.BATCH_HISTORICAL,))

    found = catalog.find_default_for(ServicePurpose.BATCH_HISTORICAL, provider=Provider.ALPACA)
    assert found is not None and found.id == a.id
    assert catalog.find_default_for(ServicePurpose.LIVE_STREAMING) is None

    catalog.disable_service(a.id)
    assert catalog.find_default_for(ServicePurpose.BATCH_HISTORICAL) is None


def test_clear_default_for_removes_only_specified_purpose(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json", validator=FakeMarketDataValidator())
    a = catalog.create_service(
        MarketDataServiceWrite(name="A", provider="alpaca", api_key="aaaaaa", api_secret="aaaaaaaa")
    )
    catalog.validate_service(a.id)
    catalog.set_default_for(a.id, (ServicePurpose.LIVE_STREAMING, ServicePurpose.BATCH_HISTORICAL))
    catalog.clear_default_for(a.id, ServicePurpose.LIVE_STREAMING)
    after = catalog.get_service(a.id)
    assert ServicePurpose.LIVE_STREAMING not in after.default_for
    assert ServicePurpose.BATCH_HISTORICAL in after.default_for


def test_manual_capability_override_can_evolve_service_capabilities(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=LearnedIntradayLimitValidator(),
    )
    learned = catalog.create_service(MarketDataServiceWrite(name="Manual Override Provider", provider="future"))
    catalog.validate_service(learned.id)

    override = MarketDataCapabilities(
        supports_historical=True,
        supports_streaming=False,
        supports_intraday=True,
        supports_daily=True,
        supports_long_range_history=True,
        cost_class=CostClass.STANDARD,
        latency_class=LatencyClass.NORMAL,
    )
    updated = catalog.update_service(
        learned.id,
        MarketDataServiceWrite(
            name="Manual Override Provider",
            provider="future",
            capabilities=override,
            capability_notes=("Operator confirmed short-range intraday coverage.",),
        ),
    )
    assert updated.capability_manual_override is True
    assert updated.capabilities.supports_intraday is True

    validated = catalog.validate_service(learned.id)
    assert validated.capabilities.supports_intraday is True
    assert validated.capability_source == "manual_override"
