from __future__ import annotations

from uuid import UUID

from backend.app.api.routes import broker_accounts
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.domain import TradingMode


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


class RecordingBrokerAccountService:
    def __init__(self) -> None:
        self.calls = []

    def create_alpaca_paper_account(self, *, display_name: str, api_key: str, api_secret: str) -> BrokerAccount:
        self.calls.append((display_name, api_key, api_secret))
        return BrokerAccount(
            id=ACCOUNT_ID,
            display_name=display_name,
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref=f"alpaca-paper:{ACCOUNT_ID}:abcdef",
            validation_status=BrokerAccountValidationStatus.VALID,
        )


def test_broker_account_route_registered_with_explicit_response_model() -> None:
    registered = {(route.method, route.path): route.response_model for route in broker_accounts.router.routes}

    assert registered[("POST", "/api/v1/broker-accounts/alpaca-paper")] is broker_accounts.BrokerAccountResponse


def test_create_alpaca_paper_route_delegates_without_url_input() -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.CreateAlpacaPaperBrokerAccountRequest(
        display_name="Paper",
        api_key="key",
        api_secret="secret",
    )

    response = broker_accounts.create_alpaca_paper_broker_account(request, service=service)

    assert response.account.id == ACCOUNT_ID
    assert response.account.provider == "alpaca"
    assert response.account.mode == TradingMode.BROKER_PAPER
    assert service.calls == [("Paper", "key", "secret")]


def test_create_request_rejects_base_url() -> None:
    try:
        broker_accounts.CreateAlpacaPaperBrokerAccountRequest(
            display_name="Paper",
            api_key="key",
            api_secret="secret",
            base_url="https://example.invalid",
        )
    except Exception as exc:
        assert "Extra inputs are not permitted" in str(exc)
    else:
        raise AssertionError("base_url must not be accepted")
