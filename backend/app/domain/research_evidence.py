from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, JsonDict, utc_now
from .research_run_artifact import DeploymentSnapshot


_FORBIDDEN_TRADING_TRUTH_FIELDS = frozenset(
    {
        "account_id",
        "broker_account_id",
        "order_id",
        "client_order_id",
        "broker_order_id",
        "position_id",
        "position_lineage_id",
        "fill_id",
        "broker_fill_id",
        "alpaca_order_id",
    }
)


class ResearchEvidenceSchema(DomainSchema):
    """Base contract for research evidence.

    Research may explain, score, and support promotion decisions. It cannot own
    live broker/order/position truth.
    """

    artifact_id: UUID | None = None
    deployment_snapshot_id: UUID | None = None
    deployment_snapshot: DeploymentSnapshot | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_trading_truth_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            present = _find_forbidden_trading_truth_fields(data)
            if present:
                raise ValueError(f"research evidence cannot contain trading truth fields: {sorted(present)}")
        return data


class ChartLabPreviewEvidence(ResearchEvidenceSchema):
    evidence_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    feature_snapshot_count: int = Field(ge=0)
    signal_marker_count: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: JsonDict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_range(self) -> "ChartLabPreviewEvidence":
        if self.start >= self.end:
            raise ValueError("chart lab preview evidence start must be before end")
        return self


class BacktestRun(ResearchEvidenceSchema):
    run_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    watchlist_snapshot_id: UUID | None = None
    universe: tuple[str, ...] = ()
    timeframe: str = "1d"
    start: datetime
    end: datetime
    initial_capital: float = Field(default=0, ge=0)
    cost_model: JsonDict = Field(default_factory=dict)
    status: str = "recorded"
    status_history: tuple[JsonDict, ...] = ()
    bar_count: int = Field(ge=0)
    signal_plan_count: int = Field(ge=0)
    simulated_trade_count: int = Field(ge=0)
    metrics: JsonDict = Field(default_factory=dict)
    results: JsonDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_range(self) -> "BacktestRun":
        if self.start >= self.end:
            raise ValueError("backtest run start must be before end")
        return self


class SimulationRunEvidence(ResearchEvidenceSchema):
    run_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    scenario_name: str
    start: datetime
    end: datetime
    signal_plan_count: int = Field(ge=0)
    simulated_order_count: int = Field(ge=0)
    simulated_fill_count: int = Field(ge=0)
    metrics: JsonDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_range(self) -> "SimulationRunEvidence":
        if self.start >= self.end:
            raise ValueError("simulation evidence start must be before end")
        return self


class OptimizationRun(ResearchEvidenceSchema):
    run_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    objective: str
    candidate_count: int = Field(gt=0)
    best_parameters: JsonDict = Field(default_factory=dict)
    best_metrics: JsonDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class WalkForwardRun(ResearchEvidenceSchema):
    run_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    window_count: int = Field(gt=0)
    passed_window_count: int = Field(ge=0)
    metrics: JsonDict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_window_count(self) -> "WalkForwardRun":
        if self.passed_window_count > self.window_count:
            raise ValueError("passed walk-forward windows cannot exceed total windows")
        return self


class PromotionEvidenceBundle(ResearchEvidenceSchema):
    bundle_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    chart_lab_evidence_ids: tuple[UUID, ...] = ()
    backtest_run_ids: tuple[UUID, ...] = ()
    simulation_run_ids: tuple[UUID, ...] = ()
    optimization_run_ids: tuple[UUID, ...] = ()
    walk_forward_run_ids: tuple[UUID, ...] = ()
    readiness_score: float = Field(default=0, ge=0, le=100)
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def ready(self) -> bool:
        return self.readiness_score >= 100 and not self.blockers


def _find_forbidden_trading_truth_fields(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(_FORBIDDEN_TRADING_TRUTH_FIELDS.intersection(str(key) for key in value))
        for child in value.values():
            found.update(_find_forbidden_trading_truth_fields(child))
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            found.update(_find_forbidden_trading_truth_fields(child))
    return found
