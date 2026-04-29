"""Composition root for DeploymentService."""

from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path

from .persistence import DeploymentRepository
from .service import DeploymentService


def create_deployment_service_from_environment() -> DeploymentService:
    return DeploymentService(repository=DeploymentRepository(get_runtime_db_path()))
