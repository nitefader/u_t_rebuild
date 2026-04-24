"""Operations Center backend runtime visibility and control contract."""

from .models import (
    AccountOperations,
    AccountSummary,
    DeploymentOperations,
    DeploymentSummary,
    FlattenRequestResponse,
    InternalOrderLedgerSummary,
    RuntimeOverview,
)

_SERVICE_EXPORTS = {"OperationsCenterService"}


def __getattr__(name: str):
    if name in _SERVICE_EXPORTS:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)

__all__ = [
    "AccountOperations",
    "AccountSummary",
    "DeploymentOperations",
    "DeploymentSummary",
    "FlattenRequestResponse",
    "InternalOrderLedgerSummary",
    "OperationsCenterService",
    "RuntimeOverview",
]
