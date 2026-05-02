from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from ._base import DomainSchema, utc_now
from .execution_style import ExecutionStyleVersion
from .risk_profile import RiskProfileVersion
from .strategy import StrategyVersion
from .strategy_controls import TradingHorizon, StrategyControlsVersion
from .universe import UniverseSnapshot


class DeploymentSnapshotSource(StrEnum):
    DEPLOYMENT = "deployment"
    RESEARCH_MANUAL = "research_manual"


class ResearchRunKind(StrEnum):
    CHART_LAB = "chart_lab"
    BACKTEST = "backtest"
    SIM_LAB = "sim_lab"
    OPTIMIZATION = "optimization"
    WALK_FORWARD = "walk_forward"


class ResearchDataPolicy(DomainSchema):
    provider: str
    timeframe: str
    adjustment_policy: str = "split_dividend_adjusted"
    start: datetime
    end: datetime
    warmup_start: datetime | None = None
    timezone: str = "UTC"

    @model_validator(mode="after")
    def validate_range(self) -> "ResearchDataPolicy":
        if self.start >= self.end:
            raise ValueError("research data policy start must be before end")
        if self.warmup_start is not None and self.warmup_start > self.start:
            raise ValueError("research data policy warmup_start must be at or before start")
        return self


class SnapshotComponentPayload(DomainSchema):
    component_name: Literal["strategy", "strategy_control", "execution_plan", "risk_plan", "universe"]
    payload_json: str
    sha256: str


class DeploymentSnapshot(DomainSchema):
    """Immutable Deployment-like package used by research.

    Research may read an actual Deployment to assemble this package, but the
    snapshot is owned by the ResearchRunArtifact and research has no authority
    to mutate the source Deployment as a side effect. The source Deployment may
    still be explicitly rebound / parameter-switched by the operator through
    the proper Deployment control path. Python field names keep legacy
    component class names where needed, while operator language remains
    Strategy Control, Execution Plan, and Risk Plan.
    """

    snapshot_id: UUID = Field(default_factory=uuid4)
    source: DeploymentSnapshotSource = DeploymentSnapshotSource.RESEARCH_MANUAL
    source_deployment_id: UUID | None = None
    source_deployment_name: str | None = None
    source_deployment_description: str | None = None
    assembled_at: datetime = Field(default_factory=utc_now)

    strategy_id: UUID
    strategy_version_id: UUID
    strategy_controls_version_id: UUID
    execution_plan_version_id: UUID
    risk_plan_version_id: UUID
    risk_horizon: TradingHorizon | None = None

    watchlist_ids: tuple[UUID, ...] = ()
    watchlist_snapshot_ids: tuple[UUID, ...] = ()
    symbols: tuple[str, ...] = Field(min_length=1)

    data_policy: ResearchDataPolicy
    historical_dataset_ids: tuple[UUID, ...] = ()
    data_quality_warnings: tuple[str, ...] = ()

    strategy: StrategyVersion
    strategy_controls: StrategyControlsVersion
    execution_plan: ExecutionStyleVersion
    risk_plan: RiskProfileVersion
    universe: UniverseSnapshot
    component_payloads: tuple[SnapshotComponentPayload, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def populate_component_payloads(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("component_payloads"):
            return data
        component_values = (
            ("strategy", data.get("strategy")),
            ("strategy_control", data.get("strategy_controls")),
            ("execution_plan", data.get("execution_plan")),
            ("risk_plan", data.get("risk_plan")),
            ("universe", data.get("universe")),
        )
        if any(component is None for _, component in component_values):
            return data
        updated = dict(data)
        updated["component_payloads"] = cls._canonical_component_payloads_from_values(
            component_values
        )
        return updated

    @model_validator(mode="after")
    def validate_component_ids(self) -> "DeploymentSnapshot":
        if self.strategy.strategy_id != self.strategy_id:
            raise ValueError("deployment snapshot strategy_id does not match StrategyVersion")
        if self.strategy.id != self.strategy_version_id:
            raise ValueError("deployment snapshot strategy_version_id does not match StrategyVersion")
        if self.strategy_controls.id != self.strategy_controls_version_id:
            raise ValueError("deployment snapshot strategy_controls_version_id does not match Strategy Control")
        if self.execution_plan.id != self.execution_plan_version_id:
            raise ValueError("deployment snapshot execution_plan_version_id does not match Execution Plan")
        if self.risk_plan.id != self.risk_plan_version_id:
            raise ValueError("deployment snapshot risk_plan_version_id does not match Risk Plan")
        universe_symbols = tuple(symbol.symbol.upper() for symbol in self.universe.symbols)
        if tuple(symbol.upper() for symbol in self.symbols) != universe_symbols:
            raise ValueError("deployment snapshot symbols must match UniverseSnapshot symbols")
        payloads = self._canonical_component_payloads()
        if self.component_payloads:
            expected = {payload.component_name: payload for payload in payloads}
            actual = {payload.component_name: payload for payload in self.component_payloads}
            if actual != expected:
                raise ValueError("deployment snapshot component payload fingerprints do not match components")
        else:
            raise ValueError("deployment snapshot component payload fingerprints are required")
        return self

    def _canonical_component_payloads(self) -> tuple[SnapshotComponentPayload, ...]:
        return self._canonical_component_payloads_from_values(
            (
                ("strategy", self.strategy),
                ("strategy_control", self.strategy_controls),
                ("execution_plan", self.execution_plan),
                ("risk_plan", self.risk_plan),
                ("universe", self.universe),
            )
        )

    @staticmethod
    def _canonical_component_payloads_from_values(
        components: tuple[tuple[str, Any], ...],
    ) -> tuple[SnapshotComponentPayload, ...]:
        payloads: list[SnapshotComponentPayload] = []
        for name, component in components:
            if hasattr(component, "model_dump"):
                payload = component.model_dump(mode="json")
            else:
                payload = component
            payload_json = json.dumps(payload, sort_keys=True)
            payloads.append(
                SnapshotComponentPayload(
                    component_name=name,  # type: ignore[arg-type]
                    payload_json=payload_json,
                    sha256=hashlib.sha256(payload_json.encode("utf-8")).hexdigest(),
                )
            )
        return tuple(payloads)


class ResearchRunArtifact(DomainSchema):
    artifact_id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    run_kind: ResearchRunKind
    producer: Literal["historical_replay", "chart_lab_preview"] = "historical_replay"
    deployment_snapshot: DeploymentSnapshot
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def strategy_id(self) -> UUID:
        return self.deployment_snapshot.strategy_id

    @property
    def strategy_version_id(self) -> UUID:
        return self.deployment_snapshot.strategy_version_id
