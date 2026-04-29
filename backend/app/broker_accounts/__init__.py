"""Broker account setup and validation."""

from .credential_store import (
    BrokerCredentialStore,
    CredentialStoreError,
    create_broker_credential_store_from_environment,
)
from .models import (
    AccountRestrictions,
    AccountRestrictionsUpdateRequest,
    AccountRiskConfig,
    AccountRiskConfigUpdateRequest,
    BrokerAccount,
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountCredentialValidationStatus,
    BrokerAccountDeletionResponse,
    BrokerAccountDeletionStatus,
    BrokerAccountListResponse,
    BrokerAccountResponse,
    BrokerAccountValidationStatus,
    CreateBrokerAccountRequest,
    DeleteBrokerAccountRequest,
    ReplaceBrokerAccountCredentialsRequest,
    UpdateBrokerAccountDetailsRequest,
)

_SERVICE_EXPORTS = {
    "BrokerAccountCreationError",
    "BrokerAccountCreationResult",
    "BrokerAccountService",
}


def __getattr__(name: str):
    if name in _SERVICE_EXPORTS:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)


__all__ = [
    "AccountRestrictions",
    "AccountRestrictionsUpdateRequest",
    "AccountRiskConfig",
    "AccountRiskConfigUpdateRequest",
    "BrokerAccount",
    "BrokerAccountCredentialUpdateResponse",
    "BrokerAccountCredentialValidationStatus",
    "BrokerAccountDeletionResponse",
    "BrokerAccountDeletionStatus",
    "BrokerAccountCreationError",
    "BrokerAccountCreationResult",
    "BrokerAccountListResponse",
    "BrokerAccountResponse",
    "BrokerAccountService",
    "BrokerAccountValidationStatus",
    "BrokerCredentialStore",
    "CreateBrokerAccountRequest",
    "CredentialStoreError",
    "DeleteBrokerAccountRequest",
    "ReplaceBrokerAccountCredentialsRequest",
    "UpdateBrokerAccountDetailsRequest",
    "create_broker_credential_store_from_environment",
]
