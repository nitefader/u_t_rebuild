from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.brokers import BrokerReconciliationReport, BrokerSyncState
from backend.app.control_plane import ControlPlane
from backend.app.domain import GovernorMode, ProgramVersion, TradingMode, ValidationEvidence
from backend.app.domain._base import utc_now


class PaperRunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    broker_account_id: UUID
    mode: TradingMode = TradingMode.BROKER_PAPER
    succeeded: bool
    started_at: datetime
    ended_at: datetime
    trade_count: int = Field(default=0, ge=0)
    submitted_order_count: int = Field(default=0, ge=0)
    rejected_order_count: int = Field(default=0, ge=0)
    max_drawdown_pct: float = Field(default=0, ge=0)
    runtime_errors: tuple[str, ...] = ()
    broker_sync_inconsistent_event_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "PaperRunEvidence":
        if self.started_at >= self.ended_at:
            raise ValueError("paper run start must be before end")
        if self.mode != TradingMode.BROKER_PAPER:
            raise ValueError(f"paper run evidence requires BROKER_PAPER mode, got {self.mode.value}")
        if self.rejected_order_count > self.submitted_order_count:
            raise ValueError("rejected_order_count cannot exceed submitted_order_count")
        return self


class SimulationPromotionEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID
    program_version_id: UUID
    mode: TradingMode
    governor_mode: GovernorMode
    succeeded: bool = True
    rejected_trades_due_to_system_issue_count: int = Field(default=0, ge=0)


class PortfolioGovernorReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    active: bool
    enforcing: bool


class PromotionEvaluationContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    program: ProgramVersion
    deployment_id: UUID | None = None
    source_broker_account_id: UUID
    target_broker_account_id: UUID
    source_mode: TradingMode
    target_mode: TradingMode
    broker_sync_state: BrokerSyncState
    control_plane: ControlPlane
    governor: PortfolioGovernorReadiness
    reconciliation_report: BrokerReconciliationReport | None = None
    paper_runs: tuple[PaperRunEvidence, ...] = ()
    simulation_evidence: tuple[SimulationPromotionEvidence, ...] = ()
    validation_evidence: tuple[ValidationEvidence, ...] = ()


class PromotionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    program_id: UUID
    deployment_id: UUID | None = None
    source_broker_account_id: UUID
    target_broker_account_id: UUID
    eligible: bool
    blocking_reasons: list[str]
    warnings: list[str]
    warning_severities: dict[str, str] = Field(default_factory=dict)
    evaluated_at: datetime = Field(default_factory=utc_now)
