"""Pydantic request/response models for ExecutionPlanService."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain.execution_style import (
    BracketSpec,
    ExecutionMode,
    ExecutionStylePresetSpec,
    OrderCancelPolicy,
    OrderRetryPolicy,
    OrderType,
    TimeInForce,
)
from backend.app.execution_plans.models import ExecutionPlanVersionRecord


class ExecutionPlanDraft(BaseModel):
    """All operator-editable fields of ExecutionStyleVersion.

    Excludes: id, execution_style_id, version, created_at.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    entry_order_type: OrderType = OrderType.MARKET
    exit_order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    entry_limit_offset_bps: float | None = None
    cancel_after_bars: int | None = Field(default=None, gt=0)
    bracket: BracketSpec = Field(default_factory=BracketSpec)
    execution_mode: ExecutionMode = ExecutionMode.POST_FILL_BRACKET
    trailing_stop_enabled: bool = False
    scale_out_enabled: bool = False
    order_retry_policy: OrderRetryPolicy = OrderRetryPolicy.NONE
    order_cancel_policy: OrderCancelPolicy = OrderCancelPolicy.HOLD
    order_retry_max_attempts: int | None = Field(default=None, ge=1)
    order_retry_offset_bps: float | None = Field(default=None, ge=0)
    feature_refs: list[str] = Field(default_factory=list)
    preset: ExecutionStylePresetSpec | None = None

    @model_validator(mode="after")
    def validate_retry_fields(self) -> "ExecutionPlanDraft":
        if self.order_retry_policy != OrderRetryPolicy.NONE:
            if self.order_retry_max_attempts is None:
                raise ValueError(
                    "order_retry_max_attempts is required when order_retry_policy is not NONE"
                )
            if self.order_retry_offset_bps is None:
                raise ValueError(
                    "order_retry_offset_bps is required when order_retry_policy is not NONE"
                )
        else:
            if self.order_retry_max_attempts is not None:
                raise ValueError(
                    "order_retry_max_attempts must be None when order_retry_policy is NONE"
                )
            if self.order_retry_offset_bps is not None:
                raise ValueError(
                    "order_retry_offset_bps must be None when order_retry_policy is NONE"
                )
        return self


class ExecutionPlanVersionSummary(BaseModel):
    """Compact summary entry used in history lists."""

    model_config = ConfigDict(frozen=True)

    version_id: UUID
    version: int
    saved_at: datetime


class ExecutionPlanLibrarySummary(BaseModel):
    """One row in the library list (one per execution_plan_id)."""

    model_config = ConfigDict(frozen=True)

    execution_plan_id: UUID
    name: str
    head_version_id: UUID
    head_version_number: int
    is_default: bool
    retired_at: datetime | None
    usage_count: int


class ExecutionPlanLibrary(BaseModel):
    """Full library detail: head version + version history."""

    model_config = ConfigDict(frozen=True)

    execution_plan_id: UUID
    name: str
    is_default: bool
    retired_at: datetime | None
    head: ExecutionPlanVersionRecord
    history: list[ExecutionPlanVersionSummary]


class ExecutionPlanUsedByResponse(BaseModel):
    """List of deployment ids that reference this library."""

    model_config = ConfigDict(frozen=True)

    deployment_ids: list[UUID]
