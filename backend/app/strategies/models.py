"""Persistent record shapes for Strategy + StrategyVersion.

The runtime spine consumes ``backend.app.domain.StrategyVersion`` shapes;
this package owns the durable operator record (a Strategy with N
versions, each potentially frozen, and lifecycle status).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import StrategyVersion
from backend.app.domain._base import utc_now


class StrategyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class StrategyVersionStatus(StrEnum):
    DRAFT = "draft"
    FROZEN = "frozen"


class StrategyVersionRecord(BaseModel):
    """A persisted ``StrategyVersion`` plus operator lifecycle metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_version_id: UUID
    strategy_id: UUID
    version: int = Field(ge=1)
    status: StrategyVersionStatus = StrategyVersionStatus.DRAFT
    payload: StrategyVersion
    frozen_at: datetime | None = None
    frozen_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Strategy(BaseModel):
    """Operator-facing Strategy record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    tags: tuple[str, ...] = ()
    status: StrategyStatus = StrategyStatus.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    latest_version_id: UUID | None = None
    frozen_version_ids: tuple[UUID, ...] = ()
    version_count: int = 0


class StrategyResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: Strategy
    versions: tuple[StrategyVersionRecord, ...] = ()


class StrategyListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategies: tuple[Strategy, ...] = ()


class StrategyWriteRequest(BaseModel):
    """Create/update a Strategy. All fields optional on update."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    tags: tuple[str, ...] = ()
