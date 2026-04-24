from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, utc_now


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class BracketSpec(DomainSchema):
    enabled: bool = False
    take_profit_r_multiple: float | None = Field(default=None, gt=0)
    stop_loss_r_multiple: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_bracket_values_when_enabled(self) -> "BracketSpec":
        if self.enabled and (self.take_profit_r_multiple is None or self.stop_loss_r_multiple is None):
            raise ValueError("enabled bracket requires take_profit_r_multiple and stop_loss_r_multiple")
        return self


class ExecutionStyleVersion(DomainSchema):
    id: UUID
    execution_style_id: UUID
    version: int = Field(ge=1)
    name: str
    entry_order_type: OrderType
    exit_order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    entry_limit_offset_bps: float | None = None
    cancel_after_bars: int | None = Field(default=None, gt=0)
    bracket: BracketSpec = Field(default_factory=BracketSpec)
    trailing_stop_enabled: bool = False
    scale_out_enabled: bool = False
    created_at: datetime = Field(default_factory=utc_now)
