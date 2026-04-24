from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, JsonDict, utc_now
from .trading_mode import SIM_LAB_MODES, TradingMode


class GovernorMode(StrEnum):
    OFF = "off"
    ADVISORY = "advisory"
    ENFORCED = "enforced"


class SimulationSession(DomainSchema):
    id: UUID
    mode: TradingMode
    program_version_id: UUID
    feature_plan_id: UUID | None = None
    symbol_count: int = Field(ge=1)
    start: datetime
    end: datetime
    initial_cash: float = Field(gt=0)
    governor_mode: GovernorMode = GovernorMode.OFF
    fill_model_id: str = "default"
    slippage_model_id: str = "default"
    partial_fill_model_id: str = "none"
    current_timestamp: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: JsonDict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_real_broker_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "broker_account_id",
                "alpaca_order_id",
                "client_order_id",
                "real_order_id",
                "deployment_id",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"simulation session cannot contain real broker fields: {sorted(present)}")
        return data

    @model_validator(mode="after")
    def validate_range(self) -> "SimulationSession":
        if self.start >= self.end:
            raise ValueError("simulation start must be before end")
        if self.mode not in SIM_LAB_MODES:
            raise ValueError(f"simulation session requires SIM_LAB mode, got {self.mode.value}")
        return self
