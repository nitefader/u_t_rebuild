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


class BrokerOrderResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    status: BrokerOrderStatus
    filled_quantity: float = Field(default=0, ge=0)
    reason: str | None = None
    received_at: datetime = Field(default_factory=utc_now)
    broker_reference: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "BrokerOrderResult":
        if self.status == BrokerOrderStatus.REJECTED and not self.reason:
            raise ValueError("rejected broker result requires reason")
        if self.status in {BrokerOrderStatus.PARTIAL_FILL, BrokerOrderStatus.FILLED} and self.filled_quantity <= 0:
            raise ValueError(f"{self.status.value} broker result requires filled_quantity > 0")
        return self
