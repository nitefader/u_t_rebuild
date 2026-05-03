"""Legacy simulated trade payload kept for runtime_store trade history compatibility."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SimulatedTradeExitReason(StrEnum):
    OPEN = "open"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    TRAILING_STOP = "trailing_stop"
    CLOSE = "close"


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
    exit_reason: SimulatedTradeExitReason
    risk_decision_id: UUID | None = None
    signal_plan_id: UUID | None = None
    risk_plan_version_id: UUID | None = None
