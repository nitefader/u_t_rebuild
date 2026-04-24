"""Broker account setup and validation."""

from .models import (
    BrokerAccount,
    BrokerAccountResponse,
    BrokerAccountValidationStatus,
    CreateAlpacaPaperBrokerAccountRequest,
)

_SERVICE_EXPORTS = {"BrokerAccountCreationError", "BrokerAccountService", "CredentialReferenceStore"}


def __getattr__(name: str):
    if name in _SERVICE_EXPORTS:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)


__all__ = [
    "BrokerAccount",
    "BrokerAccountCreationError",
    "BrokerAccountResponse",
    "BrokerAccountService",
    "BrokerAccountValidationStatus",
    "CreateAlpacaPaperBrokerAccountRequest",
    "CredentialReferenceStore",
]
