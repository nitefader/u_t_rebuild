"""Composition root for StrategyControlsService."""

from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.deployments.persistence import DeploymentRepository

from .persistence import StrategyControlsRepository
from .registry import StrategyControlsRegistry
from .service import StrategyControlsService


def create_strategy_controls_service_from_environment() -> StrategyControlsService:
    db_path = get_runtime_db_path()
    return StrategyControlsService(
        repository=StrategyControlsRepository(db_path),
        registry=StrategyControlsRegistry(db_path),
        deployment_repository=DeploymentRepository(db_path),
    )
