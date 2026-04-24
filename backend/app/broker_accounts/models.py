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


class BrokerAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    display_name: str = Field(min_length=1)
    provider: str = "alpaca"
    mode: TradingMode = TradingMode.BROKER_PAPER
    external_account_id: str | None = None
    credentials_ref: str
    validation_status: BrokerAccountValidationStatus
    last_account_snapshot: BrokerAccountSnapshot | None = None
    broker_sync_freshness: BrokerSyncState | None = None
    created_at: datetime = Field(default_factory=utc_now)


class CreateAlpacaPaperBrokerAccountRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class BrokerAccountResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: BrokerAccount
    already_exists: bool = False
