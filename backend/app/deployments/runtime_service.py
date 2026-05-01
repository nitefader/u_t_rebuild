"""Composition root for DeploymentService."""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from backend.app.config.runtime_paths import get_runtime_db_path

from .persistence import DeploymentRepository
from .service import DeploymentService


def create_deployment_service_from_environment(
    *,
    runtime_reloader: Callable[[UUID], object] | None = None,
) -> DeploymentService:
    from backend.app.execution_plans.runtime_service import (
        create_execution_plan_service_from_environment,
    )
    from backend.app.strategy_controls.runtime_service import (
        create_strategy_controls_service_from_environment,
    )

    controls_svc = create_strategy_controls_service_from_environment()
    plan_svc = create_execution_plan_service_from_environment()

    return DeploymentService(
        repository=DeploymentRepository(get_runtime_db_path()),
        strategy_controls_version_resolver=controls_svc.get_version,
        execution_plan_version_resolver=plan_svc.get_version,
        runtime_reloader=runtime_reloader,
    )
