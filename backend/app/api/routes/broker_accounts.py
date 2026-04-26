from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated

from uuid import UUID

from backend.app.broker_accounts.models import (
    BrokerAccount,
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountDeletionResponse,
    BrokerAccountListResponse,
    BrokerAccountResponse,
    CreateAlpacaPaperBrokerAccountRequest,
    DeleteBrokerAccountRequest,
    ReplaceAlpacaPaperBrokerAccountCredentialsRequest,
)
from backend.app.broker_accounts.service import BrokerAccountCreationError

if TYPE_CHECKING:
    from backend.app.broker_accounts import BrokerAccountService

try:  # pragma: no cover - exercised only when FastAPI is installed.
    from fastapi import APIRouter, Depends, HTTPException
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]


def get_broker_account_service() -> "BrokerAccountService":
    from backend.app.broker_accounts.runtime_service import create_broker_account_service_from_environment

    return create_broker_account_service_from_environment()


def _dependency(default: object) -> object:
    if Depends is None:
        return default
    return Depends(default)


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/broker-accounts", tags=["broker-accounts"])
else:
    router = APIRouter(prefix="/api/v1/broker-accounts", tags=["broker-accounts"])


BrokerAccountServiceDependency = Annotated[Any, _dependency(get_broker_account_service)]


@router.get("", response_model=BrokerAccountListResponse)
def list_broker_accounts(service: BrokerAccountServiceDependency) -> BrokerAccountListResponse:
    accounts = _list_accounts(service)
    return BrokerAccountListResponse(accounts=tuple(accounts))


@router.post("/alpaca-paper", response_model=BrokerAccountResponse)
def create_alpaca_paper_broker_account(
    request: CreateAlpacaPaperBrokerAccountRequest,
    service: BrokerAccountServiceDependency,
) -> BrokerAccountResponse:
    try:
        result = service.create_alpaca_paper_account(
            display_name=request.display_name,
            api_key=request.api_key,
            api_secret=request.api_secret,
        )
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc
    # Per the runtime architecture spec: every Account's Broker Trade
    # Update Stream starts at boot OR right after creation, regardless
    # of Deployments. Auto-start the dispatcher for the new account so
    # the system doesn't wait for an operator restart.
    _ensure_trade_stream_started(result.account.id)
    return BrokerAccountResponse(account=result.account, already_exists=result.already_exists)


def _list_accounts(service: Any) -> tuple[BrokerAccount, ...]:
    """Pull accounts from whichever surface is available on the service.

    Real BrokerAccountService delegates to ``runtime_store.list_broker_accounts``;
    test stubs may expose either method directly.
    """
    if hasattr(service, "list_broker_accounts"):
        return tuple(service.list_broker_accounts())
    runtime_store = getattr(service, "_runtime_store", None)
    if runtime_store is not None and hasattr(runtime_store, "list_broker_accounts"):
        return tuple(runtime_store.list_broker_accounts())
    return ()


def _ensure_trade_stream_started(account_id: UUID) -> None:
    """Start a per-Account trade dispatcher, if one isn't already running.

    Best-effort: failures during dispatcher construction are surfaced via
    the dispatcher's ``last_error`` (visible on /api/v1/system/streams)
    rather than crashing the create-account request.
    """
    try:
        from backend.app.runtime.runtime_context import trade_dispatcher_registry

        dispatcher = trade_dispatcher_registry().get_or_create(account_id)
        dispatcher.start()
    except Exception:  # noqa: BLE001 - best effort
        pass


@router.put("/{account_id}/alpaca-paper/credentials", response_model=BrokerAccountCredentialUpdateResponse)
def replace_alpaca_paper_broker_account_credentials(
    account_id: UUID,
    request: ReplaceAlpacaPaperBrokerAccountCredentialsRequest,
    service: BrokerAccountServiceDependency,
) -> BrokerAccountCredentialUpdateResponse:
    try:
        return service.replace_alpaca_paper_credentials(
            account_id=account_id,
            api_key=request.api_key,
            api_secret=request.api_secret,
        )
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc


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
    if HTTPException is None:
        return BrokerAccountCreationError(message)
    return HTTPException(status_code=400, detail=message)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()
