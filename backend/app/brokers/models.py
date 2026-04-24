from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain._base import utc_now


class BrokerAdapterError(ValueError):
    """Raised when broker adapter boundary input or output is invalid."""


class BrokerOrderStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PENDING_CANCEL = "pending_cancel"
    REPLACED = "replaced"
    SUSPENDED = "suspended"
    DONE_FOR_DAY = "done_for_day"


class BrokerAccountMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class BrokerPositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class BrokerOrderResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    status: BrokerOrderStatus
    broker_order_id: str | None = None
    broker_status: str | None = None
    filled_quantity: float = Field(default=0, ge=0)
    filled_avg_price: float | None = Field(default=None, ge=0)
    remaining_quantity: float | None = Field(default=None, ge=0)
    reason: str | None = None
    received_at: datetime = Field(default_factory=utc_now)
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    filled_at: datetime | None = None
    reject_code: str | None = None
    raw_status: str | None = None
    broker_reference: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "BrokerOrderResult":
        if self.status == BrokerOrderStatus.REJECTED and not self.reason:
            raise ValueError("rejected broker result requires reason")
        if self.status in {BrokerOrderStatus.PARTIAL_FILL, BrokerOrderStatus.FILLED} and self.filled_quantity <= 0:
            raise ValueError(f"{self.status.value} broker result requires filled_quantity > 0")
        if self.remaining_quantity is not None and self.remaining_quantity < 0:
            raise ValueError("remaining_quantity cannot be negative")
        return self


class BrokerAccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    provider: str
    mode: BrokerAccountMode
    buying_power: float = Field(ge=0)
    cash: float
    equity: float = Field(ge=0)
    trading_blocked: bool = False
    account_blocked: bool = False
    pattern_day_trader: bool = False
    shorting_enabled: bool = False
    last_synced_at: datetime = Field(default_factory=utc_now)


class BrokerPositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    symbol: str
    quantity: float
    market_value: float
    avg_entry_price: float = Field(ge=0)
    side: BrokerPositionSide
    last_synced_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def normalize_position_side(self) -> "BrokerPositionSnapshot":
        if self.quantity > 0 and self.side != BrokerPositionSide.LONG:
            raise ValueError("positive quantity requires long side")
        if self.quantity < 0 and self.side != BrokerPositionSide.SHORT:
            raise ValueError("negative quantity requires short side")
        return self


class BrokerOrderMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    broker_order_id: str
    provider: str
    account_id: UUID
    created_at: datetime = Field(default_factory=utc_now)
    last_synced_at: datetime = Field(default_factory=utc_now)
