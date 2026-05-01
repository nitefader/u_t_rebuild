"""Persistent shapes for Deployment definitions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain._base import utc_now
from backend.app.domain.strategy_controls import TradingHorizon


class DeploymentLifecycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class Deployment(BaseModel):
    """Deployment binds the executable strategy package.

    Per ``MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md``: Deployment binds
    a strategy version + ``strategy_controls_version_id`` +
    ``execution_plan_version_id`` + watchlists + subscribed accounts +
    optionally a ``risk_plan_version_id``. The same StrategyVersion can run
    with different controls / execution plans across Accounts.

    Strategy version binding (Slice 9):
    - Legacy deployments set ``strategy_version_id`` (legacy FK, kept until
      Slice 11 cutover).
    - v4 deployments set ``strategy_version_v4_id`` (points to a
      ``strategy_versions_v4`` row).
    - Transition state: both FKs may be set simultaneously.
    - At least one of the two MUST be non-None.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    # Legacy FK — kept alive until Slice 11 cutover. Optional for v4-only rows.
    strategy_version_id: UUID | None = None
    # v4 FK — set by Slice 9+ deployments that bind a StrategyVersionV4.
    strategy_version_v4_id: UUID | None = None
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    risk_plan_version_id: UUID | None = None
    # Risk Horizon doctrine (locked 2026-04-29, updated Slice 8.7): Deployment
    # is the only source of horizon. StrategyControls does not carry a
    # trading_horizon field. When set, the orchestrator passes
    # enforce_plan_required=True to the GovernorPolicyResolver, activating the
    # per-horizon plan mapping rule. When None, no horizon is synthesized and
    # the per-horizon plan rule is not enforced.
    risk_horizon: TradingHorizon | None = None
    watchlist_ids: tuple[UUID, ...] = ()
    subscribed_account_ids: tuple[UUID, ...] = ()
    lifecycle_status: DeploymentLifecycleStatus = DeploymentLifecycleStatus.DRAFT
    runtime_overrides: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    stopped_at: datetime | None = None

    @model_validator(mode="after")
    def _require_at_least_one_strategy_fk(self) -> "Deployment":
        if self.strategy_version_id is None and self.strategy_version_v4_id is None:
            raise ValueError(
                "at least one of strategy_version_id or strategy_version_v4_id must be set"
            )
        return self


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
    # Legacy FK — kept alive until Slice 11 cutover. Optional for v4-only rows.
    strategy_version_id: UUID | None = None
    # v4 FK — set by Slice 9+ deployments that bind a StrategyVersionV4.
    strategy_version_v4_id: UUID | None = None
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    risk_plan_version_id: UUID | None = None
    risk_horizon: TradingHorizon | None = None
    watchlist_ids: tuple[UUID, ...] = ()
    subscribed_account_ids: tuple[UUID, ...] = ()
    runtime_overrides: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_at_least_one_strategy_fk(self) -> "DeploymentWriteRequest":
        if self.strategy_version_id is None and self.strategy_version_v4_id is None:
            raise ValueError(
                "at least one of strategy_version_id or strategy_version_v4_id must be set"
            )
        return self


class DeploymentSubscribeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID


class DeploymentLifecycleRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1, max_length=200)


class DeploymentRebindRequest(BaseModel):
    """Hot-swap request: update Controls and/or ExecutionPlan on a running
    deployment without disrupting open positions. At least one of the two FK
    fields must be non-None. The ``effective`` field controls when the swap
    is applied: ``"now"`` (immediate, next tick), ``"next_session"`` (deferred
    to next trading session open), or an ISO 8601 datetime string."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    effective: str = "now"

    @model_validator(mode="after")
    def _require_at_least_one_fk(self) -> "DeploymentRebindRequest":
        if (
            self.strategy_controls_version_id is None
            and self.execution_plan_version_id is None
        ):
            raise ValueError(
                "at least one of strategy_controls_version_id or "
                "execution_plan_version_id must be set"
            )
        return self

    @model_validator(mode="after")
    def _validate_effective(self) -> "DeploymentRebindRequest":
        val = self.effective
        if val in ("now", "next_session"):
            return self
        try:
            datetime.fromisoformat(val)
        except ValueError as exc:
            raise ValueError(
                f"effective must be 'now', 'next_session', or a valid ISO 8601 "
                f"datetime string; got {val!r}"
            ) from exc
        return self


class DeploymentBindingHistoryEntry(BaseModel):
    """Audit record for a single hot-swap or binding change on a Deployment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_id: UUID = Field(default_factory=uuid4)
    deployment_id: UUID
    timestamp: datetime
    actor: str
    before: dict[str, str | None]
    after: dict[str, str | None]
    effective: str


class DeploymentBindingHistoryListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: tuple[DeploymentBindingHistoryEntry, ...] = ()
