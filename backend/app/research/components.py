from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from backend.app.domain import (
    ExecutionStyleVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import RiskProfileVersion
from backend.app.execution_plans.persistence import ExecutionPlanRepository
from backend.app.features import ResolvedDeploymentComponents
from backend.app.research.risk_plan_lookup import load_risk_profile_from_plan_version
from backend.app.strategy_controls.persistence import StrategyControlsRepository


def load_research_components(
    *,
    strategy_lookup: Any,
    store: Any,
    strategy_version_id: UUID,
    expected_strategy_id: UUID | None = None,
    strategy_controls_version_id: UUID,
    execution_plan_version_id: UUID,
    risk_plan_version_id: UUID | None,
    symbols: tuple[str, ...],
    timeframe: str,
    universe_name: str,
    purpose: str,
) -> ResolvedDeploymentComponents:
    """Load a Deployment-like research package from saved component versions."""

    strategy_payload = load_strategy_version(
        strategy_lookup=strategy_lookup,
        strategy_version_id=strategy_version_id,
        purpose=purpose,
    )
    if expected_strategy_id is not None and strategy_payload.strategy_id != expected_strategy_id:
        raise ValueError(
            f"{purpose} strategy_id does not match StrategyVersion "
            f"({expected_strategy_id} != {strategy_payload.strategy_id})"
        )
    strategy_controls = load_strategy_controls_version(
        store=store,
        strategy_controls_version_id=strategy_controls_version_id,
        purpose=purpose,
    )
    if strategy_controls.timeframe != timeframe:
        raise ValueError(
            f"{purpose} timeframe must match Strategy Control timeframe "
            f"({timeframe!r} != {strategy_controls.timeframe!r})"
        )
    execution_plan = load_execution_plan_version(
        store=store,
        execution_plan_version_id=execution_plan_version_id,
        purpose=purpose,
    )
    risk_profile = load_risk_profile_from_plan_version(
        store=store,
        risk_plan_version_id=risk_plan_version_id,
        purpose=purpose,
    )
    return ResolvedDeploymentComponents(
        strategy=strategy_payload,
        strategy_controls=strategy_controls,
        risk_profile=risk_profile,
        execution_style=execution_plan,
        universe=UniverseSnapshot(
            id=uuid4(),
            universe_id=uuid4(),
            version=1,
            name=universe_name,
            symbols=[UniverseSymbol(symbol=symbol) for symbol in symbols],
        ),
    )


def load_strategy_version(
    *,
    strategy_lookup: Any,
    strategy_version_id: UUID,
    purpose: str,
) -> StrategyVersion:
    if strategy_lookup is None:
        raise ValueError(f"{purpose} requires a strategy lookup; configure via runtime")
    record = strategy_lookup.get_version(strategy_version_id)
    payload = getattr(record, "payload", record)
    if not isinstance(payload, StrategyVersion):
        raise ValueError(f"strategy version {strategy_version_id} is not a StrategyVersion")
    return payload


def load_strategy_controls_version(
    *,
    store: Any,
    strategy_controls_version_id: UUID,
    purpose: str,
) -> StrategyControlsVersion:
    try:
        record = StrategyControlsRepository(_db_path_from_store(store)).load_version(
            strategy_controls_version_id
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"{purpose} requires saved Strategy Control version "
            f"{strategy_controls_version_id}"
        ) from exc
    return record.payload


def load_execution_plan_version(
    *,
    store: Any,
    execution_plan_version_id: UUID,
    purpose: str,
) -> ExecutionStyleVersion:
    try:
        record = ExecutionPlanRepository(_db_path_from_store(store)).load_version(
            execution_plan_version_id
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"{purpose} requires saved Execution Plan version "
            f"{execution_plan_version_id}"
        ) from exc
    return record.payload


def _db_path_from_store(store: Any) -> Path:
    session_factory = getattr(store, "_session_factory", None)
    path = getattr(session_factory, "path", None)
    if path is None:
        from backend.app.config.runtime_paths import get_runtime_db_path

        return Path(get_runtime_db_path())
    return Path(path)
