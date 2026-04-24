from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated

from backend.app.broker_accounts.models import BrokerAccountResponse, CreateAlpacaPaperBrokerAccountRequest
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
        account = service.create_alpaca_paper_account(
            display_name=request.display_name,
            api_key=request.api_key,
            api_secret=request.api_secret,
        )
    except BrokerAccountCreationError as exc:
        raise _operator_error(str(exc)) from exc
    return BrokerAccountResponse(account=account)


def _operator_error(message: str) -> Exception:
    if HTTPException is None:
        return BrokerAccountCreationError(message)
    return HTTPException(status_code=400, detail=message)
