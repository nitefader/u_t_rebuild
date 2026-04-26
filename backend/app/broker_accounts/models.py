from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers import BrokerAccountSnapshot, BrokerSyncState
from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now


class BrokerAccountValidationStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class BrokerAccountCredentialValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MODE_MISMATCH = "mode_mismatch"
    MISSING_CREDENTIALS = "missing_credentials"
    PROVIDER_UNREACHABLE = "provider_unreachable"


class BrokerAccountDeletionStatus(StrEnum):
    HARD_DELETED = "hard_deleted"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class BrokerAccount(BaseModel):
    """Broker account record. Mode is required at creation and pinned for life.

    ``needs_credentials=True`` indicates the encrypted credential store
    has no entry for this account (typically a record from before
    persistent secret storage existed). The runtime gates trading on this
    flag; the operator re-enters credentials inline on the account card
    via ``PUT /{account_id}/credentials``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    display_name: str = Field(min_length=1)
    provider: str = "alpaca"
    mode: TradingMode
    external_account_id: str | None = None
    credentials_ref: str
    needs_credentials: bool = False
    validation_status: BrokerAccountValidationStatus
    last_account_snapshot: BrokerAccountSnapshot | None = None
    broker_sync_freshness: BrokerSyncState | None = None
    created_at: datetime = Field(default_factory=utc_now)
    is_archived: bool = False
    archived_at: datetime | None = None


class CreateBrokerAccountRequest(BaseModel):
    """Unified create-account request — provider + mode are operator-chosen.

    Replaces the paper-specific request. The backend derives the broker
    base URL and streaming endpoint from ``(provider, mode)``; the
    frontend never picks a URL.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1)
    provider: str = Field(min_length=1, default="alpaca")
    mode: TradingMode
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class BrokerAccountResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: BrokerAccount
    already_exists: bool = False


class BrokerAccountListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accounts: tuple[BrokerAccount, ...] = ()


class ReplaceBrokerAccountCredentialsRequest(BaseModel):
    """Unified replace-credentials request. Mode is derived from the
    existing account, never accepted from the client (the existing
    account's mode is the source of truth)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class BrokerAccountCredentialUpdateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: BrokerAccount | None = None
    validation_status: BrokerAccountCredentialValidationStatus
    message: str


class DeleteBrokerAccountRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    confirm_display_name: str = Field(min_length=1)
    confirm_mode: TradingMode


class BrokerAccountDeletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    status: BrokerAccountDeletionStatus
    message: str
    blockers: tuple[str, ...] = ()
    archived_account: BrokerAccount | None = None
