from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from ._base import DomainSchema, JsonDict, utc_now


class EvidenceKind(StrEnum):
    CHART_LAB = "chart_lab"
    SIM_LAB = "sim_lab"
    BACKTEST = "backtest"
    OPTIMIZATION = "optimization"
    WALK_FORWARD = "walk_forward"


class ValidationEvidence(DomainSchema):
    id: UUID
    program_version_id: UUID
    kind: EvidenceKind
    source_session_id: UUID | None = None
    status: str
    summary: str | None = None
    artifact_refs: list[UUID] = Field(default_factory=list)
    checks: JsonDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
