from __future__ import annotations

from uuid import UUID

from backend.app.api.routes import broker_accounts
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.broker_accounts.models import (
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountCredentialValidationStatus,
    BrokerAccountDeletionResponse,
    BrokerAccountDeletionStatus,
)
from backend.app.broker_accounts.service import BrokerAccountCreationResult
from backend.app.domain import TradingMode


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


class RecordingBrokerAccountService:
    def __init__(self) -> None:
        self.calls = []

    def create_alpaca_paper_account(self, *, display_name: str, api_key: str, api_secret: str) -> BrokerAccountCreationResult:
        self.calls.append((display_name, api_key, api_secret))
        return BrokerAccountCreationResult(
            account=BrokerAccount(
                id=ACCOUNT_ID,
                display_name=display_name,
                provider="alpaca",
                mode=TradingMode.BROKER_PAPER,
                external_account_id="alpaca-paper-account-1",
                credentials_ref=f"alpaca-paper:{ACCOUNT_ID}:abcdef",
                validation_status=BrokerAccountValidationStatus.VALID,
            ),
            already_exists=True,
        )

    def replace_alpaca_paper_credentials(self, *, account_id: UUID, api_key: str, api_secret: str) -> BrokerAccountCredentialUpdateResponse:
        self.calls.append(("replace", account_id, api_key, api_secret))
        return BrokerAccountCredentialUpdateResponse(
            account=None,
            validation_status=BrokerAccountCredentialValidationStatus.VALID,
            message="ok",
        )

    def delete_or_archive_account(self, *, account_id: UUID, confirm_display_name: str, confirm_mode: TradingMode) -> BrokerAccountDeletionResponse:
        self.calls.append(("delete", account_id, confirm_display_name, confirm_mode))
        return BrokerAccountDeletionResponse(
            account_id=account_id,
            status=BrokerAccountDeletionStatus.HARD_DELETED,
            message="deleted",
        )


def test_broker_account_route_registered_with_explicit_response_model() -> None:
    registered = {(route.method, route.path): route.response_model for route in broker_accounts.router.routes}

    assert registered[("POST", "/api/v1/broker-accounts/alpaca-paper")] is broker_accounts.BrokerAccountResponse
    assert registered[("PUT", "/api/v1/broker-accounts/{account_id}/alpaca-paper/credentials")] is BrokerAccountCredentialUpdateResponse
    assert registered[("POST", "/api/v1/broker-accounts/{account_id}/delete")] is BrokerAccountDeletionResponse


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
    assert response.account.external_account_id == "alpaca-paper-account-1"
    assert response.already_exists is True
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


def test_replace_credentials_route_delegates_without_exposing_secret() -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.ReplaceAlpacaPaperBrokerAccountCredentialsRequest(api_key="new-key", api_secret="new-secret")

    response = broker_accounts.replace_alpaca_paper_broker_account_credentials(ACCOUNT_ID, request, service=service)

    assert response.validation_status == BrokerAccountCredentialValidationStatus.VALID
    assert service.calls[-1] == ("replace", ACCOUNT_ID, "new-key", "new-secret")
    assert "new-secret" not in response.model_dump_json()


def test_delete_account_route_delegates_with_explicit_confirmation() -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.DeleteBrokerAccountRequest(
        confirm_display_name="Paper",
        confirm_mode=TradingMode.BROKER_PAPER,
    )

    response = broker_accounts.delete_broker_account(ACCOUNT_ID, request, service=service)

    assert response.status == BrokerAccountDeletionStatus.HARD_DELETED
    assert service.calls[-1] == ("delete", ACCOUNT_ID, "Paper", TradingMode.BROKER_PAPER)
