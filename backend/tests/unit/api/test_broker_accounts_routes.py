"""Pin the unified broker-accounts route contract.

Per the no-fork rule: ONE create endpoint and ONE replace-credentials
endpoint, both parametrized over (provider, mode). Paper-specific URL
suffixes (e.g. ``/alpaca-paper``) are deleted, and the request shape
takes ``provider`` + ``mode`` as fields.
"""

from __future__ import annotations

from uuid import UUID

import pytest

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

    def create_account(
        self, *, display_name: str, provider: str, mode: TradingMode, api_key: str, api_secret: str
    ) -> BrokerAccountCreationResult:
        self.calls.append((display_name, provider, mode, api_key, api_secret))
        return BrokerAccountCreationResult(
            account=BrokerAccount(
                id=ACCOUNT_ID,
                display_name=display_name,
                provider=provider,
                mode=mode,
                external_account_id=f"{provider}-{mode.value.lower()}-account-1",
                credentials_ref=f"{provider}-{mode.value.lower()}:{ACCOUNT_ID}:abcdef",
                validation_status=BrokerAccountValidationStatus.VALID,
            ),
            already_exists=True,
        )

    def replace_credentials(
        self, *, account_id: UUID, api_key: str, api_secret: str
    ) -> BrokerAccountCredentialUpdateResponse:
        self.calls.append(("replace", account_id, api_key, api_secret))
        return BrokerAccountCredentialUpdateResponse(
            account=None,
            validation_status=BrokerAccountCredentialValidationStatus.VALID,
            message="ok",
        )

    def delete_or_archive_account(
        self, *, account_id: UUID, confirm_display_name: str, confirm_mode: TradingMode
    ) -> BrokerAccountDeletionResponse:
        self.calls.append(("delete", account_id, confirm_display_name, confirm_mode))
        return BrokerAccountDeletionResponse(
            account_id=account_id,
            status=BrokerAccountDeletionStatus.HARD_DELETED,
            message="deleted",
        )


def test_broker_account_routes_registered_with_unified_paths() -> None:
    registered = {(route.method, route.path): route.response_model for route in broker_accounts.router.routes}

    assert registered[("POST", "/api/v1/broker-accounts")] is broker_accounts.BrokerAccountResponse
    assert registered[("PUT", "/api/v1/broker-accounts/{account_id}/credentials")] is BrokerAccountCredentialUpdateResponse
    assert registered[("POST", "/api/v1/broker-accounts/{account_id}/delete")] is BrokerAccountDeletionResponse
    # Paper-specific URLs must not exist.
    assert ("POST", "/api/v1/broker-accounts/alpaca-paper") not in registered
    assert ("PUT", "/api/v1/broker-accounts/{account_id}/alpaca-paper/credentials") not in registered


@pytest.mark.parametrize("mode", [TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE])
def test_create_route_delegates_with_provider_and_mode(mode: TradingMode) -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.CreateBrokerAccountRequest(
        display_name=f"acct-{mode.value}",
        provider="alpaca",
        mode=mode,
        api_key="key",
        api_secret="secret",
    )

    response = broker_accounts.create_broker_account(request, service=service)

    assert response.account.id == ACCOUNT_ID
    assert response.account.provider == "alpaca"
    assert response.account.mode == mode
    assert response.already_exists is True
    assert service.calls == [(f"acct-{mode.value}", "alpaca", mode, "key", "secret")]


def test_create_request_rejects_unknown_fields() -> None:
    try:
        broker_accounts.CreateBrokerAccountRequest(
            display_name="x",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            api_key="K",
            api_secret="S",
            base_url="https://example.invalid",
        )
    except Exception as exc:
        assert "Extra inputs are not permitted" in str(exc)
    else:
        raise AssertionError("base_url must not be accepted")


def test_replace_credentials_route_delegates_without_exposing_secret() -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.ReplaceBrokerAccountCredentialsRequest(api_key="new-key", api_secret="new-secret")

    response = broker_accounts.replace_broker_account_credentials(ACCOUNT_ID, request, service=service)

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
