"""Persistence record for ExecutionPlanVersion."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import utc_now
from backend.app.domain.execution_style import ExecutionStyleVersion


class ExecutionPlanVersionRecord(BaseModel):
    """A persisted, immutable ExecutionPlanVersion plus row-level metadata.

    Note: the Python class identity for the ExecutionPlan is
    ``ExecutionStyleVersion`` (legacy name; doctrine name is "ExecutionPlan",
    used for the table + Deployment FK). See
    ``Operations_Turtle_Shell_Artifacts/STRATEGY_TO_BROKER_BRACKET_PROGRAM.md``
    decision D3.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: ExecutionStyleVersion
    saved_at: datetime = Field(default_factory=utc_now)
