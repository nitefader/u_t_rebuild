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


class OrderOrigin(StrEnum):
    PROGRAM = "program"
    MANUAL_OPERATOR = "manual_operator"


class InternalOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    account_id: UUID
    origin: OrderOrigin = OrderOrigin.PROGRAM
    deployment_id: UUID | None = None
    program_id: UUID | None = None
    symbol: str
    side: CandidateSide
    quantity: float = Field(gt=0)
    filled_quantity: float = Field(default=0, ge=0)
    order_type: OrderType
    time_in_force: TimeInForce
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    parent_order_id: UUID | None = None
    order_class: str | None = None
    extended_hours: bool = False
    intent: InternalOrderIntent
    status: InternalOrderStatus
    created_at: datetime
    updated_at: datetime
    cancel_requested_at: datetime | None = None
    canceled_at: datetime | None = None
    replaced_by_order_id: UUID | None = None
    replaces_order_id: UUID | None = None
    signal_name: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_filled_quantity(self) -> "InternalOrder":
        if self.filled_quantity > self.quantity:
            raise ValueError("filled_quantity cannot exceed quantity")
        if self.origin == OrderOrigin.PROGRAM and (self.deployment_id is None or self.program_id is None):
            raise ValueError("program orders require deployment_id and program_id")
        if self.origin == OrderOrigin.MANUAL_OPERATOR and (self.deployment_id is not None or self.program_id is not None):
            raise ValueError("manual operator orders cannot carry deployment/program lineage")
        return self

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
