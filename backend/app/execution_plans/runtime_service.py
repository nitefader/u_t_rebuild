"""Composition root for ExecutionPlanService."""

from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.deployments.persistence import DeploymentRepository

from .persistence import ExecutionPlanRepository
from .registry import ExecutionPlanRegistry
from .service import ExecutionPlanService


def create_execution_plan_service_from_environment() -> ExecutionPlanService:
    db_path = get_runtime_db_path()
    return ExecutionPlanService(
        repository=ExecutionPlanRepository(db_path),
        registry=ExecutionPlanRegistry(db_path),
        deployment_repository=DeploymentRepository(db_path),
    )
