"""Unified broker-account REST surface.

One create endpoint, one replace-credentials endpoint, one delete
endpoint. Mode (paper/live) is operator-chosen at create time and pinned
for the life of the account; the backend derives the broker base URL
and streaming endpoint from ``(provider, mode)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.broker_accounts.models import (
    BrokerAccount,
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountDeletionResponse,
    BrokerAccountListResponse,
    BrokerAccountResponse,
    CreateBrokerAccountRequest,
    DeleteBrokerAccountRequest,
    ReplaceBrokerAccountCredentialsRequest,
    UpdateBrokerAccountDetailsRequest,
)
from backend.app.broker_accounts.service import BrokerAccountCreationError

if TYPE_CHECKING:
    from backend.app.broker_accounts import BrokerAccountService


def get_broker_account_service() -> "BrokerAccountService":
    from backend.app.broker_accounts.runtime_service import (
        create_broker_account_service_from_environment,
    )

    return create_broker_account_service_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/broker-accounts", tags=["broker-accounts"])


BrokerAccountServiceDependency = Annotated[Any, _dependency(get_broker_account_service)]


@router.get("", response_model=BrokerAccountListResponse)
def list_broker_accounts(service: BrokerAccountServiceDependency) -> BrokerAccountListResponse:
    accounts = _list_accounts(service)
    return BrokerAccountListResponse(accounts=tuple(accounts))


@router.post("", response_model=BrokerAccountResponse)
def create_broker_account(
    request: CreateBrokerAccountRequest,
    service: BrokerAccountServiceDependency,
) -> BrokerAccountResponse:
    """Unified create — operator picks provider + mode; backend derives URL."""
    try:
        result = service.create_account(
            display_name=request.display_name,
            provider=request.provider,
            mode=request.mode,
            api_key=request.api_key,
            api_secret=request.api_secret,
        )
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc
    # Build the BrokerSync / OrderManager stack before opening the stream so
    # the first broker event has a truth writer.
    _ensure_manual_trade_composition_for_account(service, result.account)
    # Per the runtime architecture spec: every Account's Broker Trade
    # Update Stream starts at boot OR right after creation.
    _ensure_trade_stream_started(service, result.account)
    return BrokerAccountResponse(account=result.account, already_exists=result.already_exists)


def _list_accounts(service: Any) -> tuple[BrokerAccount, ...]:
    """Pull accounts from whichever surface is available on the service."""
    if hasattr(service, "list_broker_accounts"):
        return tuple(service.list_broker_accounts())
    runtime_store = getattr(service, "_runtime_store", None)
    if runtime_store is not None and hasattr(runtime_store, "list_broker_accounts"):
        return tuple(runtime_store.list_broker_accounts())
    return ()


def _ensure_trade_stream_started(service: Any, account: BrokerAccount, *, restart: bool = False) -> None:
    """Start a per-Account trade dispatcher, if one isn't already running.

    Failures are surfaced via ``TradeEventDispatcher.last_error`` (visible
    on /api/v1/system/streams) rather than crashing the create-account
    request — but they are not silently ignored.
    """
    import logging

    try:
        from backend.app.runtime.runtime_context import ensure_account_trade_sync_started

        ensure_account_trade_sync_started(service, account, restart=restart)
    except Exception as exc:  # noqa: BLE001 - log loudly, do not crash route
        logging.getLogger(__name__).warning(
            "trade dispatcher start failed for account %s: %s", account.id, exc, exc_info=True
        )


def _ensure_manual_trade_composition_for_account(service: Any, account: BrokerAccount) -> None:
    """Register the per-account OrderManager + BrokerSync stack so the
    manual-trade route works without a process restart.
    """
    import logging

    try:
        from backend.app.runtime.runtime_context import (
            register_account_in_manual_trade_registry,
        )

        register_account_in_manual_trade_registry(service, account)
    except Exception as exc:  # noqa: BLE001 - log loudly, do not crash route
        logging.getLogger(__name__).warning(
            "manual-trade registry wire-up failed for account %s: %s",
            account.id,
            exc,
            exc_info=True,
        )


@router.patch("/{account_id}", response_model=BrokerAccountResponse)
def update_broker_account_details(
    account_id: UUID,
    request: UpdateBrokerAccountDetailsRequest,
    service: BrokerAccountServiceDependency,
) -> BrokerAccountResponse:
    """Rename or adjust operator-visible labels. Does not touch secrets or mode."""
    try:
        account = service.update_account_details(account_id=account_id, display_name=request.display_name)
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc
    return BrokerAccountResponse(account=account, already_exists=False)


@router.put("/{account_id}/credentials", response_model=BrokerAccountCredentialUpdateResponse)
def replace_broker_account_credentials(
    account_id: UUID,
    request: ReplaceBrokerAccountCredentialsRequest,
    service: BrokerAccountServiceDependency,
) -> BrokerAccountCredentialUpdateResponse:
    try:
        response = service.replace_credentials(
            account_id=account_id,
            api_key=request.api_key,
            api_secret=request.api_secret,
        )
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc
    # On a successful replace, refresh the per-account composition stack
    # so the new credentials are picked up without a restart.
    if response.account is not None and response.validation_status.value == "valid":
        _ensure_manual_trade_composition_for_account(service, response.account)
        _ensure_trade_stream_started(service, response.account, restart=True)
    return response


@router.post("/{account_id}/delete", response_model=BrokerAccountDeletionResponse)
def delete_broker_account(
    account_id: UUID,
    request: DeleteBrokerAccountRequest,
    service: BrokerAccountServiceDependency,
) -> BrokerAccountDeletionResponse:
    try:
        return service.delete_or_archive_account(
            account_id=account_id,
            confirm_display_name=request.confirm_display_name,
            confirm_mode=request.confirm_mode,
        )
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc


def _operator_error(message: str) -> Exception:
    return HTTPException(status_code=400, detail=message)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()
