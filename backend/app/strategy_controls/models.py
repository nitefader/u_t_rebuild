"""Persistence record for StrategyControlsVersion."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import utc_now
from backend.app.domain.strategy_controls import StrategyControlsVersion


class StrategyControlsVersionRecord(BaseModel):
    """A persisted, immutable StrategyControlsVersion plus row-level metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: StrategyControlsVersion
    saved_at: datetime = Field(default_factory=utc_now)
