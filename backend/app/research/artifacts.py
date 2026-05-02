from __future__ import annotations

from datetime import datetime
from typing import Iterable
from uuid import UUID, uuid4

from backend.app.domain import (
    DeploymentSnapshot,
    DeploymentSnapshotSource,
    ResearchDataPolicy,
    ResearchRunArtifact,
    ResearchRunKind,
)
from backend.app.domain._base import utc_now
from backend.app.features import ResolvedDeploymentComponents


def build_research_run_artifact(
    *,
    run_id: UUID,
    run_kind: ResearchRunKind | str,
    components: ResolvedDeploymentComponents,
    data_policy: ResearchDataPolicy,
    historical_dataset_ids: Iterable[UUID] = (),
    data_quality_warnings: Iterable[str] = (),
    source: DeploymentSnapshotSource = DeploymentSnapshotSource.RESEARCH_MANUAL,
    source_deployment_id: UUID | None = None,
    source_deployment_name: str | None = None,
    source_deployment_description: str | None = None,
    watchlist_ids: Iterable[UUID] = (),
    watchlist_snapshot_ids: Iterable[UUID] = (),
    producer: str = "historical_replay",
    assembled_at: datetime | None = None,
) -> ResearchRunArtifact:
    """Freeze a Deployment-like research package for one run.

    This deliberately lives in ``backend.app.research`` so research can read a
    real Deployment package without mutating the live Deployment service or
    creating a parallel research config model.
    """

    if components.strategy is None:
        raise ValueError("research artifacts currently require a resolved StrategyVersion")
    symbols = tuple(symbol.symbol.upper() for symbol in components.universe.symbols)
    snapshot = DeploymentSnapshot(
        snapshot_id=uuid4(),
        source=source,
        source_deployment_id=source_deployment_id,
        source_deployment_name=source_deployment_name,
        source_deployment_description=source_deployment_description,
        assembled_at=assembled_at or utc_now(),
        strategy_id=components.strategy.strategy_id,
        strategy_version_id=components.strategy.id,
        strategy_controls_version_id=components.strategy_controls.id,
        execution_plan_version_id=components.execution_style.id,
        risk_plan_version_id=components.risk_profile.id,
        symbols=symbols,
        watchlist_ids=tuple(watchlist_ids),
        watchlist_snapshot_ids=tuple(watchlist_snapshot_ids),
        data_policy=data_policy,
        historical_dataset_ids=tuple(historical_dataset_ids),
        data_quality_warnings=tuple(data_quality_warnings),
        strategy=components.strategy,
        strategy_controls=components.strategy_controls,
        execution_plan=components.execution_style,
        risk_plan=components.risk_profile,
        universe=components.universe,
    )
    return ResearchRunArtifact(
        run_id=run_id,
        run_kind=ResearchRunKind(run_kind),
        producer=producer,  # type: ignore[arg-type]
        deployment_snapshot=snapshot,
    )


def artifact_lineage_payload(artifact: ResearchRunArtifact) -> dict[str, object]:
    snapshot = artifact.deployment_snapshot
    return {
        "artifact_id": str(artifact.artifact_id),
        "deployment_snapshot_id": str(snapshot.snapshot_id),
        "run_kind": artifact.run_kind.value,
        "producer": artifact.producer,
        "strategy_id": str(snapshot.strategy_id),
        "strategy_version_id": str(snapshot.strategy_version_id),
        "strategy_controls_version_id": str(snapshot.strategy_controls_version_id),
        "execution_plan_version_id": str(snapshot.execution_plan_version_id),
        "risk_plan_version_id": str(snapshot.risk_plan_version_id),
        "symbols": list(snapshot.symbols),
        "data_policy": snapshot.data_policy.model_dump(mode="json"),
        "historical_dataset_ids": [str(dataset_id) for dataset_id in snapshot.historical_dataset_ids],
    }
