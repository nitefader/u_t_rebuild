"""Composition root for the StrategyService against the runtime DB."""

from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.deployments.persistence import DeploymentRepository

from .persistence import StrategyRepository
from .service import StrategyService


def create_strategy_service_from_environment() -> StrategyService:
    db_path = get_runtime_db_path()
    return StrategyService(
        repository=StrategyRepository(db_path),
        deployment_repository=DeploymentRepository(db_path),
    )
