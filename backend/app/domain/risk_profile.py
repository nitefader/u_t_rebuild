from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from ._base import DomainSchema, utc_now


class PositionSizingMethod(StrEnum):
    FIXED_DOLLAR = "fixed_dollar"
    FIXED_SHARES = "fixed_shares"
    RISK_PERCENT_EQUITY = "risk_percent_equity"


class RiskProfileVersion(DomainSchema):
    id: UUID
    risk_profile_id: UUID
    version: int = Field(ge=1)
    name: str
    sizing_method: PositionSizingMethod
    risk_per_trade_pct: float | None = Field(default=None, gt=0, le=100)
    fixed_notional: float | None = Field(default=None, gt=0)
    fixed_shares: int | None = Field(default=None, gt=0)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    max_positions: int | None = Field(default=None, gt=0)
    max_symbol_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    feature_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
