from __future__ import annotations

import pytest

from backend.app.services import (
    AICapabilityLabel,
    AIProvider,
    AIServiceWrite,
    DataConsumer,
    DataIntent,
    DataIntentMode,
    DataPurpose,
    MarketDataServiceWrite,
    ResolveMarketDataRequest,
    SelectionMode,
    ServiceMode,
    ServiceStatus,
    ServiceValidationStatus,
    ServicesCenterError,
    ServicesCenterService,
    Timeframe,
)
from backend.app.services.validation import AIValidationResult, MarketDataValidationResult, alpaca_capabilities


class FakeMarketDataValidator:
    def __init__(self, status=ServiceValidationStatus.VALID) -> None:
        self.status = status

    def validate(self, **kwargs):
        if kwargs["provider"] == "yahoo":
            from backend.app.services.validation import yahoo_capabilities

            return MarketDataValidationResult(ServiceValidationStatus.VALID, "yahoo ok", yahoo_capabilities())
        if not kwargs["has_api_key"] or not kwargs["has_api_secret"]:
            return MarketDataValidationResult(ServiceValidationStatus.MISSING_CREDENTIALS, "missing", alpaca_capabilities())
        return MarketDataValidationResult(self.status, self.status.value, alpaca_capabilities())


class FakeAIValidator:
    def validate(self, **kwargs):
        if not kwargs["has_api_key"]:
            return AIValidationResult(ServiceValidationStatus.MISSING_CREDENTIALS, "missing")
        return AIValidationResult(ServiceValidationStatus.VALID, "ok")


def test_market_data_crud_defaults_validation_and_resolver(tmp_path) -> None:
    service = ServicesCenterService(store_path=tmp_path / "services.json", market_data_validator=FakeMarketDataValidator())

    alpaca = service.create_market_data_service(
        MarketDataServiceWrite(name="Alpaca Main", provider="alpaca", mode=ServiceMode.PAPER, api_key="abcdef", api_secret="abcdefgh")
    )
    yahoo = service.create_market_data_service(MarketDataServiceWrite(name="Yahoo Historical", provider="yahoo"))
    assert len(service.list_market_data_services().services) == 2
    assert service.get_market_data_service(alpaca.id).name == "Alpaca Main"
    assert alpaca.credentials_ref
    assert "abcdef" not in alpaca.model_dump_json()

    updated = service.update_market_data_service(
        alpaca.id,
        MarketDataServiceWrite(name="Alpaca Edited", provider="alpaca", mode=ServiceMode.LIVE, api_key="new-key", api_secret="new-secret"),
    )
    assert updated.name == "Alpaca Edited"
    assert updated.mode == ServiceMode.LIVE

    with pytest.raises(ValueError):
        MarketDataServiceWrite(name="Bad", provider="alpaca", mode=ServiceMode.PAPER, api_key="********", api_secret="********")

    alpaca = service.validate_market_data_service(alpaca.id)
    yahoo = service.validate_market_data_service(yahoo.id)
    assert alpaca.status == ServiceStatus.VALID
    assert yahoo.capabilities.supports_streaming is False

    default_alpaca = service.set_default_market_data_service(alpaca.id)
    assert default_alpaca.is_default is True
    default_yahoo = service.set_default_market_data_service(yahoo.id)
    assert default_yahoo.is_default is True
    assert service.get_market_data_service(alpaca.id).is_default is False

    disabled = service.disable_market_data_service(yahoo.id)
    assert disabled.status == ServiceStatus.DISABLED
    assert disabled.is_default is False

    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )
    result = service.resolve_market_data(ResolveMarketDataRequest(intent=intent, selection_mode=SelectionMode.AUTO))
    assert result.selected_service_id == str(alpaca.id)
    assert all(candidate.service_id != str(yahoo.id) or candidate.reason_code == "rejected_disabled_service" for candidate in result.rejected_candidates)


def test_invalid_market_data_service_cannot_be_default(tmp_path) -> None:
    service = ServicesCenterService(store_path=tmp_path / "services.json", market_data_validator=FakeMarketDataValidator(ServiceValidationStatus.INVALID))
    alpaca = service.create_market_data_service(MarketDataServiceWrite(name="Alpaca", provider="alpaca", mode=ServiceMode.PAPER, api_key="abcdef", api_secret="abcdefgh"))
    service.validate_market_data_service(alpaca.id)

    with pytest.raises(ServicesCenterError, match="invalid service"):
        service.set_default_market_data_service(alpaca.id)


def test_alpaca_missing_and_invalid_validation_statuses(tmp_path) -> None:
    service = ServicesCenterService(store_path=tmp_path / "services.json")
    missing = service.create_market_data_service(MarketDataServiceWrite(name="Alpaca", provider="alpaca", mode=ServiceMode.PAPER))
    assert service.validate_market_data_service(missing.id).validation_status == ServiceValidationStatus.MISSING_CREDENTIALS

    invalid = service.create_market_data_service(MarketDataServiceWrite(name="Bad Alpaca", provider="alpaca", mode=ServiceMode.PAPER, api_key="x", api_secret="y"))
    assert service.validate_market_data_service(invalid.id).validation_status == ServiceValidationStatus.INVALID


def test_ai_crud_validation_default_and_disable(tmp_path) -> None:
    service = ServicesCenterService(store_path=tmp_path / "services.json", ai_validator=FakeAIValidator())
    groq = service.create_ai_service(
        AIServiceWrite(name="Groq Fast", provider=AIProvider.GROQ, api_key="gsk_valid_key", capability_label=AICapabilityLabel.FAST)
    )
    assert service.list_ai_services().services == (groq,)
    edited = service.update_ai_service(groq.id, AIServiceWrite(name="Groq Reasoning", provider=AIProvider.GROQ, capability_label=AICapabilityLabel.REASONING))
    assert edited.capability_label == AICapabilityLabel.REASONING
    validated = service.validate_ai_service(groq.id)
    assert validated.status == ServiceStatus.VALID
    assert service.set_default_ai_service(groq.id).is_default is True
    assert service.disable_ai_service(groq.id).status == ServiceStatus.DISABLED
    with pytest.raises(ServicesCenterError):
        service.set_default_ai_service(groq.id)


def test_ai_missing_key_and_invalid_default(tmp_path) -> None:
    service = ServicesCenterService(store_path=tmp_path / "services.json", ai_validator=FakeAIValidator())
    groq = service.create_ai_service(AIServiceWrite(name="Groq", provider=AIProvider.GROQ))
    assert service.validate_ai_service(groq.id).validation_status == ServiceValidationStatus.MISSING_CREDENTIALS
    with pytest.raises(ServicesCenterError, match="invalid service"):
        service.set_default_ai_service(groq.id)
