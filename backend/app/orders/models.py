from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
    REDUCE = "reduce"
    TARGET = "target"
    STOP = "stop"
    TRAIL = "trail"
    BREAKEVEN = "breakeven"
    RUNNER = "runner"
    LOGICAL_EXIT = "logical_exit"
    TAKE_PROFIT = "tp"
    STOP_LOSS = "sl"
    SCALE = "scale"
    MANUAL_OPERATOR = "manual_operator"


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
    SIGNAL_PLAN = "signal_plan"
    MANUAL_OPERATOR = "manual_operator"


class InternalOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    account_id: UUID
    origin: OrderOrigin
    deployment_id: UUID | None = None
    strategy_id: UUID | None = None
    strategy_version_id: UUID | None = None
    signal_plan_id: UUID | None = None
    opening_signal_plan_id: UUID | None = None
    current_signal_plan_id: UUID | None = None
    position_lineage_id: UUID | None = None
    account_evaluation_id: UUID | None = None
    governor_decision_id: UUID | None = None
    leg_label: str | None = None
    lifecycle_intent: str | None = None
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
    # Bracket Program T-4: when ``order_class == "bracket"`` the entry order
    # carries the prices for both child legs. The AlpacaBrokerAdapter attaches
    # these to ``TakeProfitRequest`` (limit_price) + ``StopLossRequest``
    # (stop_price) on the broker submit. Native Alpaca bracket only — the
    # post_fill_bracket mode does not populate these because the prices are
    # computed *after* the entry fill by ProtectiveOrderPlacer.
    bracket_take_profit_limit_price: float | None = Field(default=None, gt=0)
    bracket_stop_loss_stop_price: float | None = Field(default=None, gt=0)
    # Trailing stop fields (M5 — HARD.MD P1-3).
    # Exactly one of trail_price XOR trail_percent must be set for TRAILING_STOP order_class.
    # Both are None for all other order classes.
    trail_price: Decimal | None = None
    trail_percent: Decimal | None = None
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
        # Trailing stop XOR constraint: trail_price and trail_percent are mutually exclusive.
        if self.trail_price is not None and self.trail_percent is not None:
            raise ValueError("trail_price and trail_percent are mutually exclusive; set exactly one for trailing stop orders")
        # If order_class is trailing_stop, exactly one trail field must be set.
        if self.order_class == "trailing_stop":
            if self.trail_price is None and self.trail_percent is None:
                raise ValueError("trailing_stop order_class requires exactly one of trail_price or trail_percent")
        if self.origin == OrderOrigin.SIGNAL_PLAN:
            required = {
                "deployment_id": self.deployment_id,
                "strategy_id": self.strategy_id,
                "signal_plan_id": self.signal_plan_id,
                "current_signal_plan_id": self.current_signal_plan_id,
                "position_lineage_id": self.position_lineage_id,
                "account_evaluation_id": self.account_evaluation_id,
                "governor_decision_id": self.governor_decision_id,
            }
            missing = sorted(name for name, value in required.items() if value is None)
            if missing:
                raise ValueError(f"signal plan orders require lineage fields: {missing}")
        if self.origin == OrderOrigin.MANUAL_OPERATOR and self.deployment_id is not None:
            raise ValueError("manual operator orders cannot carry deployment lineage")
        if self.origin == OrderOrigin.MANUAL_OPERATOR and any(
            value is not None
            for value in (
                self.strategy_id,
                self.strategy_version_id,
                self.signal_plan_id,
                self.opening_signal_plan_id,
                self.current_signal_plan_id,
                self.position_lineage_id,
                self.account_evaluation_id,
                self.governor_decision_id,
            )
        ):
            raise ValueError("manual operator orders cannot carry signal plan lineage")
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
