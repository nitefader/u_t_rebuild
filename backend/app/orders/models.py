from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import CandidateSide, OrderType, TimeInForce
from backend.app.domain._base import utc_now


class OrderManagerError(ValueError):
    """Raised when internal order management rejects an unsafe request."""


class InternalOrderIntent(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    TAKE_PROFIT = "tp"
    STOP_LOSS = "sl"
    SCALE = "scale"


class InternalOrderStatus(StrEnum):
    CREATED = "created"
    PENDING_SUBMISSION = "pending_submission"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    FAILED = "failed"


class InternalOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    account_id: UUID
    deployment_id: UUID
    program_id: UUID
    symbol: str
    side: CandidateSide
    quantity: float = Field(gt=0)
    order_type: OrderType
    time_in_force: TimeInForce
    intent: InternalOrderIntent
    status: InternalOrderStatus
    created_at: datetime
    updated_at: datetime
    signal_name: str | None = None
    reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_external_broker_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"alpaca_order_id", "broker_order_id", "filled_avg_price", "broker_status"}
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"internal order cannot contain broker fields: {sorted(present)}")
        return data


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    status: InternalOrderStatus
    updated_at: datetime = Field(default_factory=utc_now)
    reason: str | None = None
