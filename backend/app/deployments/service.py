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
from typing import Callable, Protocol
from uuid import UUID, uuid4

from backend.app.domain._base import utc_now

from .models import (
    Deployment,
    DeploymentBindingHistoryEntry,
    DeploymentBindingHistoryListResponse,
    DeploymentLifecycleStatus,
    DeploymentRebindRequest,
    DeploymentResponse,
    DeploymentWriteRequest,
)
from .persistence import DeploymentNotFoundError, DeploymentRepository


class DeploymentServiceError(RuntimeError):
    """Operator-readable Deployment failure."""


class _VersionResolver(Protocol):
    def __call__(self, version_id: UUID) -> object: ...


class _RuntimeReloader(Protocol):
    def __call__(self, deployment_id: UUID) -> None: ...


class DeploymentService:
    def __init__(
        self,
        *,
        repository: DeploymentRepository,
        strategy_controls_version_resolver: _VersionResolver | None = None,
        execution_plan_version_resolver: _VersionResolver | None = None,
        runtime_reloader: _RuntimeReloader | None = None,
    ) -> None:
        self._repo = repository
        self._resolve_controls_version = strategy_controls_version_resolver
        self._resolve_plan_version = execution_plan_version_resolver
        self._runtime_reloader = runtime_reloader

    def _notify_runtime(self, deployment_id: UUID) -> None:
        if self._runtime_reloader is None:
            return
        try:
            self._runtime_reloader(deployment_id)
        except Exception:  # noqa: BLE001
            # Persistence already committed; runtime picks up on next
            # process restart even if this notify hop fails. Don't make
            # the operator's rebind/start/stop 500 over a cache-miss.
            pass

    def _validate_controls_version_id(self, version_id: UUID | None) -> None:
        if version_id is None or self._resolve_controls_version is None:
            return
        try:
            self._resolve_controls_version(version_id)
        except LookupError as exc:
            raise DeploymentServiceError(
                f"strategy_controls_version_id {version_id} does not resolve to a saved "
                f"StrategyControls version (did you pass a strategy_controls_id instead?): {exc}"
            ) from exc

    def _validate_plan_version_id(self, version_id: UUID | None) -> None:
        if version_id is None or self._resolve_plan_version is None:
            return
        try:
            self._resolve_plan_version(version_id)
        except LookupError as exc:
            raise DeploymentServiceError(
                f"execution_plan_version_id {version_id} does not resolve to a saved "
                f"ExecutionPlan version (did you pass an execution_plan_id instead?): {exc}"
            ) from exc

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
        self._validate_controls_version_id(request.strategy_controls_version_id)
        self._validate_plan_version_id(request.execution_plan_version_id)
        deployment = Deployment(
            deployment_id=uuid4(),
            name=request.name.strip(),
            description=request.description,
            strategy_version_id=request.strategy_version_id,
            strategy_version_v4_id=request.strategy_version_v4_id,
            strategy_controls_version_id=request.strategy_controls_version_id,
            execution_plan_version_id=request.execution_plan_version_id,
            risk_plan_version_id=request.risk_plan_version_id,
            risk_horizon=request.risk_horizon,
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
        self._validate_controls_version_id(request.strategy_controls_version_id)
        self._validate_plan_version_id(request.execution_plan_version_id)
        updated = existing.model_copy(
            update={
                "name": request.name.strip(),
                "description": request.description,
                "strategy_version_id": request.strategy_version_id,
                "strategy_version_v4_id": request.strategy_version_v4_id,
                "strategy_controls_version_id": request.strategy_controls_version_id,
                "execution_plan_version_id": request.execution_plan_version_id,
                "risk_plan_version_id": request.risk_plan_version_id,
                "risk_horizon": request.risk_horizon,
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
        saved = self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.ACTIVE,
                    "started_at": deployment.started_at or datetime.now(timezone.utc),
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_start_reason": reason},
                }
            )
        )
        self._notify_runtime(deployment_id)
        return saved

    def pause(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status == DeploymentLifecycleStatus.PAUSED:
            return deployment
        saved = self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.PAUSED,
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_pause_reason": reason},
                }
            )
        )
        self._notify_runtime(deployment_id)
        return saved

    def resume(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status != DeploymentLifecycleStatus.PAUSED:
            raise DeploymentServiceError("deployment is not paused")
        saved = self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.ACTIVE,
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_resume_reason": reason},
                }
            )
        )
        self._notify_runtime(deployment_id)
        return saved

    def stop(self, deployment_id: UUID, *, reason: str) -> Deployment:
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status == DeploymentLifecycleStatus.STOPPED:
            return deployment
        saved = self._repo.save_deployment(
            deployment.model_copy(
                update={
                    "lifecycle_status": DeploymentLifecycleStatus.STOPPED,
                    "stopped_at": datetime.now(timezone.utc),
                    "updated_at": utc_now(),
                    "runtime_overrides": {**deployment.runtime_overrides, "last_stop_reason": reason},
                }
            )
        )
        self._notify_runtime(deployment_id)
        return saved

    # -- Hot-swap ----------------------------------------------------

    def rebind(
        self, deployment_id: UUID, request: DeploymentRebindRequest
    ) -> Deployment:
        """Hot-swap Controls and/or ExecutionPlan on a running deployment.

        Only ACTIVE deployments may be rebound. Open positions are unaffected;
        the next tick reads the new bindings for *new* candidate orders.
        """
        deployment = self._load(deployment_id)
        if deployment.lifecycle_status != DeploymentLifecycleStatus.ACTIVE:
            raise DeploymentServiceError(
                f"rebind requires an ACTIVE deployment; "
                f"current status is {deployment.lifecycle_status.value!r}"
            )
        self._validate_controls_version_id(request.strategy_controls_version_id)
        self._validate_plan_version_id(request.execution_plan_version_id)

        before: dict[str, str | None] = {
            "strategy_version_id": (
                str(deployment.strategy_version_id)
                if deployment.strategy_version_id is not None
                else None
            ),
            "strategy_version_v4_id": (
                str(deployment.strategy_version_v4_id)
                if deployment.strategy_version_v4_id is not None
                else None
            ),
            "strategy_controls_version_id": (
                str(deployment.strategy_controls_version_id)
                if deployment.strategy_controls_version_id is not None
                else None
            ),
            "execution_plan_version_id": (
                str(deployment.execution_plan_version_id)
                if deployment.execution_plan_version_id is not None
                else None
            ),
            "risk_plan_version_id": (
                str(deployment.risk_plan_version_id)
                if deployment.risk_plan_version_id is not None
                else None
            ),
        }

        updates: dict[str, object] = {"updated_at": utc_now()}
        if request.strategy_controls_version_id is not None:
            updates["strategy_controls_version_id"] = request.strategy_controls_version_id
        if request.execution_plan_version_id is not None:
            updates["execution_plan_version_id"] = request.execution_plan_version_id

        updated = deployment.model_copy(update=updates)
        self._repo.save_deployment(updated)

        after: dict[str, str | None] = {
            "strategy_version_id": (
                str(updated.strategy_version_id)
                if updated.strategy_version_id is not None
                else None
            ),
            "strategy_version_v4_id": (
                str(updated.strategy_version_v4_id)
                if updated.strategy_version_v4_id is not None
                else None
            ),
            "strategy_controls_version_id": (
                str(updated.strategy_controls_version_id)
                if updated.strategy_controls_version_id is not None
                else None
            ),
            "execution_plan_version_id": (
                str(updated.execution_plan_version_id)
                if updated.execution_plan_version_id is not None
                else None
            ),
            "risk_plan_version_id": (
                str(updated.risk_plan_version_id)
                if updated.risk_plan_version_id is not None
                else None
            ),
        }

        history_entry = DeploymentBindingHistoryEntry(
            deployment_id=deployment_id,
            timestamp=datetime.now(timezone.utc),
            actor="operator",
            before=before,
            after=after,
            effective=request.effective,
        )
        self._repo.save_binding_history(history_entry)
        if request.effective == "now":
            self._notify_runtime(deployment_id)
        return updated

    def get_binding_history(
        self, deployment_id: UUID
    ) -> DeploymentBindingHistoryListResponse:
        self._load(deployment_id)  # verify existence
        entries = self._repo.list_binding_history(deployment_id)
        return DeploymentBindingHistoryListResponse(entries=entries)

    def _load(self, deployment_id: UUID) -> Deployment:
        try:
            return self._repo.get_deployment(deployment_id)
        except DeploymentNotFoundError as exc:
            raise DeploymentServiceError(str(exc)) from exc
