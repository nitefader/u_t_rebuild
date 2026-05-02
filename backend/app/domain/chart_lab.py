from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, JsonDict, utc_now
from .trading_mode import CHART_LAB_MODES, TradingMode


class ChartLabSession(DomainSchema):
    id: UUID
    mode: TradingMode
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    strategy_version_id: UUID | None = None
    program_version_id: UUID | None = None
    feature_plan_id: UUID | None = None
    selected_feature_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: JsonDict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_execution_state(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "orders",
                "fills",
                "positions",
                "pnl",
                "equity",
                "drawdown",
                "cash",
                "broker_account_id",
                "deployment_id",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"chart lab session cannot contain execution state: {sorted(present)}")
        return data

    @model_validator(mode="after")
    def validate_mode_reference(self) -> "ChartLabSession":
        if self.start >= self.end:
            raise ValueError("chart lab start must be before end")
        if self.mode not in CHART_LAB_MODES:
            raise ValueError(f"chart lab session requires CHART_LAB mode, got {self.mode.value}")
        return self
