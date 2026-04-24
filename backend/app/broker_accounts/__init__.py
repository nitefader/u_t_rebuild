"""Broker account setup and validation."""

from .models import (
    BrokerAccount,
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountCredentialValidationStatus,
    BrokerAccountDeletionResponse,
    BrokerAccountDeletionStatus,
    BrokerAccountResponse,
    BrokerAccountValidationStatus,
    CreateAlpacaPaperBrokerAccountRequest,
    DeleteBrokerAccountRequest,
    ReplaceAlpacaPaperBrokerAccountCredentialsRequest,
)

_SERVICE_EXPORTS = {
    "BrokerAccountCreationError",
    "BrokerAccountCreationResult",
    "BrokerAccountService",
    "CredentialReferenceStore",
}


def __getattr__(name: str):
    if name in _SERVICE_EXPORTS:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)


__all__ = [
    "BrokerAccount",
    "BrokerAccountCredentialUpdateResponse",
    "BrokerAccountCredentialValidationStatus",
    "BrokerAccountDeletionResponse",
    "BrokerAccountDeletionStatus",
    "BrokerAccountCreationError",
    "BrokerAccountCreationResult",
    "BrokerAccountResponse",
    "BrokerAccountService",
    "BrokerAccountValidationStatus",
    "CreateAlpacaPaperBrokerAccountRequest",
    "DeleteBrokerAccountRequest",
    "CredentialReferenceStore",
    "ReplaceAlpacaPaperBrokerAccountCredentialsRequest",
]
