"""Deployment CRUD + lifecycle facade.

This service does NOT introduce a runtime root. Lifecycle methods
(``start``, ``stop``, ``pause``, ``resume``) update the persisted
record's lifecycle_status and rely on the existing runtime
composition root (``backend.app.pipeline.orchestrator``) to honor
the persisted state on its next tick. Operator-initiated actions
that need control-plane gating (pause/resume/flatten across the
runtime) flow through the existing
``/api/v1/operations/deployments/{id}/...`` endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.domain._base import utc_now

from .models import (
    Deployment,
    DeploymentLifecycleStatus,
    DeploymentResponse,
    DeploymentWriteRequest,
)
from .persistence import DeploymentNotFoundError, DeploymentRepository


class DeploymentServiceError(RuntimeError):
    """Operator-readable Deployment failure."""


class DeploymentService:
    def __init__(self, *, repository: DeploymentRepository) -> None:
        self._repo = repository

    def list_deployments(self) -> tuple[Deployment, ...]:
        return self._repo.list_deployments()

    def get_deployment(self, deployment_id: UUID) -> DeploymentResponse:
        try:
            deployment = self._repo.get_deployment(deployment_id)
        except DeploymentNotFoundError as exc:
            raise DeploymentServiceError(str(exc)) from exc
        return DeploymentResponse(deployment=deployment)

    def create_deployment(self, request: DeploymentWriteRequest) -> Deployment:
        if not request.watchlist_ids:
            raise DeploymentServiceError("deployment requires at least one watchlist")
        if not request.subscribed_account_ids:
            raise DeploymentServiceError("deployment requires at least one subscribed account")
        deployment = Deployment(
            deployment_id=uuid4(),
            name=request.name.strip(),
            description=request.description,
            strategy_version_id=request.strategy_version_id,
            watchlist_ids=tuple(request.watchlist_ids),
            subscribed_account_ids=tuple(request.subscribed_account_ids),
            runtime_overrides=dict(request.runtime_overrides),
        )
        return self._repo.save_deployment(deployment)

    def update_deployment(
        self,
        deployment_id: UUID,
        request: DeploymentWriteRequest,
    ) -> Deployment:
        try:
            existing = self._repo.get_deployment(deployment_id)
        except DeploymentNotFoundError as exc:
            raise DeploymentServiceError(str(exc)) from exc
        if existing.lifecycle_status == DeploymentLifecycleStatus.ACTIVE:
            raise DeploymentServiceError(
                "cannot edit an active deployment; pause or stop it first"
            )
        updated = existing.model_copy(
            update={
                "name": request.name.strip(),
                "description": request.description,
                "strategy_version_id": request.strategy_version_id,
                "watchlist_ids": tuple(request.watchlist_ids),
                "subscribed_account_ids": tuple(request.subscribed_account_ids),
                "runtime_overrides": dict(request.runtime_overrides),
                "updated_at": utc_now(),
            }
        )
        return self._repo.save_deployment(updated)

    def delete_deployment(self, deployment_id: UUID) -> None:
        try:
            existing = self._repo.get_deployment(deployment_id)
        except DeploymentNotFoundError as exc:
            raise DeploymentServiceError(str(exc)) from exc
        if existing.lifecycle_status not in {
            DeploymentLifecycleStatus.DRAFT,
            DeploymentLifecycleStatus.STOPPED,
        }:
            raise DeploymentServiceError(
                "deployment must be DRAFT or STOPPED to delete; pause/stop it first"
            )
        self._repo.delete_deployment(deployment_id)

    # -- Lifecycle ----------------------------------------------------

    def subscribe_account(self, deployment_id: UUID, account_id: UUID) -> Deployment:
        deployment = self._load(deployment_id)
        if account_id in deployment.subscribed_account_ids:
            return deployment
        return self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "subscribed_account_ids": (*deployment.subscribed_account_ids, account_id),
                    "updated_at": utc_now(),
                }
            )
        )

    def unsubscribe_account(self, deployment_id: UUID, account_id: UUID) -> Deployment:
        deployment = self._load(deployment_id)
        next_ids = tuple(a for a in deployment.subscribed_account_ids if a != account_id)
        if next_ids == deployment.subscribed_account_ids:
            return deployment
        return self._repo.save_deployment(
            deployment.model_copy(
                update={"subscribed_account_ids": next_ids, "updated_at": utc_now()}
            )
        )

    def start(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status == DeploymentLifecycleStatus.ACTIVE:
            return deployment
        if not deployment.watchlist_ids or not deployment.subscribed_account_ids:
            raise DeploymentServiceError(
                "deployment requires watchlists and subscribed accounts before starting"
            )
        return self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.ACTIVE,
                    "started_at": deployment.started_at or datetime.now(timezone.utc),
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_start_reason": reason},
                }
            )
        )

    def pause(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status == DeploymentLifecycleStatus.PAUSED:
            return deployment
        return self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.PAUSED,
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_pause_reason": reason},
                }
            )
        )

    def resume(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status != DeploymentLifecycleStatus.PAUSED:
            raise DeploymentServiceError("deployment is not paused")
        return self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.ACTIVE,
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_resume_reason": reason},
                }
            )
        )

    def stop(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status == DeploymentLifecycleStatus.STOPPED:
            return deployment
        return self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.STOPPED,
                    "stopped_at": datetime.now(timezone.utc),
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_stop_reason": reason},
                }
            )
        )

    def _load(self, deployment_id: UUID) -> Deployment:
        try:
            return self._repo.get_deployment(deployment_id)
        except DeploymentNotFoundError as exc:
            raise DeploymentServiceError(str(exc)) from exc
