from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated

from uuid import UUID

from backend.app.broker_accounts.models import (
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountDeletionResponse,
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
    return BrokerAccountResponse(account=result.account, already_exists=result.already_exists)


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
