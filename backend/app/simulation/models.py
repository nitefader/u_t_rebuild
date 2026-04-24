from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import SimulationSession


class SimulationError(ValueError):
    """Raised when deterministic replay cannot continue safely."""


class SimulatedOrderIntent(StrEnum):
    OPEN = "open"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    CLOSE = "close"


class SimulatedOrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class SimulatedOrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class SimulatedOrderStatus(StrEnum):
    CREATED = "created"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"


class SimulatedEventType(StrEnum):
    SIGNAL_CANDIDATE = "signal_candidate"
    SIGNAL_BLOCKED = "signal_blocked"
    ORDER_CREATED = "order_created"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_FILLED = "order_filled"
    POSITION_OPENED = "position_opened"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"
    STOP_TRIGGERED = "stop_triggered"
    TARGET_TRIGGERED = "target_triggered"
    TRAILING_STOP_UPDATED = "trailing_stop_updated"
    PNL_UPDATED = "pnl_updated"


class SimulatedFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    order_id: str
    symbol: str
    side: SimulatedOrderSide
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    timestamp: datetime


class SimulatedOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    symbol: str
    intent: SimulatedOrderIntent
    side: SimulatedOrderSide
    order_type: SimulatedOrderType
    qty: float = Field(gt=0)
    filled_qty: float = Field(default=0, ge=0)
    status: SimulatedOrderStatus = SimulatedOrderStatus.CREATED
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    parent_order_id: str | None = None
    created_at: datetime
    updated_at: datetime
    signal_name: str | None = None

    @model_validator(mode="after")
    def validate_filled_qty(self) -> "SimulatedOrder":
        if self.filled_qty > self.qty:
            raise ValueError("filled_qty cannot exceed qty")
        return self


class SimulatedPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    qty: float = 0
    avg_price: float = 0
    realized_pnl: float = 0
    open_stop: float | None = None
    open_target: float | None = None
    trailing_distance: float | None = None


class SimulatedTrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    symbol: str
    side: str
    qty: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    exit_price: float = Field(gt=0)
    entry_order_id: str
    exit_order_id: str
    opened_at: datetime
    closed_at: datetime
    realized_pnl: float
    exit_reason: SimulatedOrderIntent


class EquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    gross_exposure: float
    drawdown: float


class SimulationEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    timestamp: datetime
    event_type: SimulatedEventType
    symbol: str | None = None
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class SimulationReplayResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session: SimulationSession
    orders: tuple[SimulatedOrder, ...]
    fills: tuple[SimulatedFill, ...]
    positions: tuple[SimulatedPosition, ...]
    trades: tuple[SimulatedTrade, ...]
    events: tuple[SimulationEvent, ...]
    equity_curve: tuple[EquityPoint, ...]
    realized_pnl: float
    max_drawdown: float
    gross_exposure: float

    @model_validator(mode="before")
    @classmethod
    def reject_external_broker_artifacts(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "alpaca_order_id",
                "broker_order_id",
                "client_order_id",
                "broker_account_id",
                "deployment_id",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"simulation result cannot contain external broker artifacts: {sorted(present)}")
        return data


class ReplayClock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID
    current_timestamp: datetime
