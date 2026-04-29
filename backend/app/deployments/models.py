"""Persistent shapes for Deployment definitions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import utc_now


class DeploymentLifecycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class Deployment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    strategy_version_id: UUID
    watchlist_ids: tuple[UUID, ...] = ()
    subscribed_account_ids: tuple[UUID, ...] = ()
    lifecycle_status: DeploymentLifecycleStatus = DeploymentLifecycleStatus.DRAFT
    runtime_overrides: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    stopped_at: datetime | None = None


class DeploymentResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment: Deployment


class DeploymentListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployments: tuple[Deployment, ...] = ()


class DeploymentWriteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    strategy_version_id: UUID
    watchlist_ids: tuple[UUID, ...] = ()
    subscribed_account_ids: tuple[UUID, ...] = ()
    runtime_overrides: dict[str, object] = Field(default_factory=dict)


class DeploymentSubscribeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID


class DeploymentLifecycleRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1, max_length=200)
