"""Strategy CRUD service.

Strategies are reusable trading logic + execution-plan config. The
service exposes one ``create``/``get``/``list``/``update``/``delete``
plus version operations: ``add_version`` / ``freeze_version``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain import StrategyVersion

from .models import (
    Strategy,
    StrategyResponse,
    StrategyStatus,
    StrategyVersionRecord,
    StrategyVersionStatus,
    StrategyWriteRequest,
)
from .persistence import (
    StrategyNotFoundError,
    StrategyRepository,
    StrategyVersionNotFoundError,
    build_version_record,
    derive_strategy_aggregates,
)


class StrategyServiceError(RuntimeError):
    """Operator-readable Strategy operation failure."""


class StrategyService:
    def __init__(self, *, repository: StrategyRepository, deployment_repository: DeploymentRepository | None = None) -> None:
        self._repo = repository
        self._deployment_repo = deployment_repository

    # -- Strategies ----------------------------------------------------

    def list_strategies(self) -> tuple[Strategy, ...]:
        strategies = self._repo.list_strategies()
        return tuple(
            derive_strategy_aggregates(strategy, self._repo.list_versions(strategy.strategy_id))
            for strategy in strategies
        )

    def get_strategy(self, strategy_id: UUID) -> StrategyResponse:
        try:
            strategy = self._repo.get_strategy(strategy_id)
        except StrategyNotFoundError as exc:
            raise StrategyServiceError(str(exc)) from exc
        versions = self._repo.list_versions(strategy_id)
        return StrategyResponse(
            strategy=derive_strategy_aggregates(strategy, versions),
            versions=versions,
        )

    def create_strategy(self, request: StrategyWriteRequest) -> Strategy:
        strategy = Strategy(
            strategy_id=uuid4(),
            name=request.name.strip(),
            description=request.description,
            tags=tuple(request.tags),
        )
        return self._repo.save_strategy(strategy)

    def update_strategy(self, strategy_id: UUID, request: StrategyWriteRequest) -> Strategy:
        try:
            existing = self._repo.get_strategy(strategy_id)
        except StrategyNotFoundError as exc:
            raise StrategyServiceError(str(exc)) from exc
        updated = existing.model_copy(
            update={
                "name": request.name.strip(),
                "description": request.description,
                "tags": tuple(request.tags),
            }
        )
        self._repo.save_strategy(updated)
        return derive_strategy_aggregates(updated, self._repo.list_versions(strategy_id))

    def delete_strategy(self, strategy_id: UUID) -> None:
        # Soft-prevent deletion of strategies with frozen versions —
        # frozen versions feed Deployments and lineage.
        versions = self._repo.list_versions(strategy_id)
        if any(v.status == StrategyVersionStatus.FROZEN for v in versions):
            raise StrategyServiceError(
                "strategy has frozen versions and cannot be deleted; mark deprecated instead"
            )
        self._repo.delete_strategy(strategy_id)

    def deprecate_strategy(self, strategy_id: UUID) -> Strategy:
        try:
            existing = self._repo.get_strategy(strategy_id)
        except StrategyNotFoundError as exc:
            raise StrategyServiceError(str(exc)) from exc
        updated = existing.model_copy(update={"status": StrategyStatus.DEPRECATED})
        self._repo.save_strategy(updated)
        return derive_strategy_aggregates(updated, self._repo.list_versions(strategy_id))

    # -- Versions ------------------------------------------------------

    def list_versions(self, strategy_id: UUID) -> tuple[StrategyVersionRecord, ...]:
        return self._repo.list_versions(strategy_id)

    def get_version(self, strategy_version_id: UUID) -> StrategyVersionRecord:
        try:
            return self._repo.get_version(strategy_version_id)
        except StrategyVersionNotFoundError as exc:
            raise StrategyServiceError(str(exc)) from exc

    def add_version(self, strategy_id: UUID, payload: StrategyVersion) -> StrategyVersionRecord:
        try:
            self._repo.get_strategy(strategy_id)
        except StrategyNotFoundError as exc:
            raise StrategyServiceError(str(exc)) from exc
        if payload.strategy_id != strategy_id:
            raise StrategyServiceError("strategy_version.strategy_id does not match path id")
        next_n = self._repo.next_version_number(strategy_id)
        if payload.version != next_n:
            payload = payload.model_copy(update={"version": next_n})
        record = build_version_record(
            strategy_id=strategy_id,
            version_number=next_n,
            payload=payload,
            status=StrategyVersionStatus.DRAFT,
        )
        return self._repo.save_version(record)

    def edit_version(
        self,
        strategy_id: UUID,
        strategy_version_id: UUID,
        payload: StrategyVersion,
    ) -> StrategyVersionRecord:
        existing = self.get_version(strategy_version_id)
        if existing.strategy_id != strategy_id:
            raise StrategyServiceError("strategy_version does not belong to this strategy")
        if existing.status == StrategyVersionStatus.FROZEN:
            raise StrategyServiceError("strategy_version is frozen and cannot be edited")
        if payload.strategy_id != strategy_id:
            raise StrategyServiceError("strategy_version.strategy_id does not match path id")
        if payload.id != strategy_version_id:
            raise StrategyServiceError("strategy_version.id does not match path version id")
        updated_payload = payload.model_copy(update={"version": existing.version})
        updated = existing.model_copy(update={"payload": updated_payload})
        return self._repo.save_version(updated)

    def freeze_version(self, strategy_version_id: UUID, *, frozen_by: str | None = None) -> StrategyVersionRecord:
        existing = self.get_version(strategy_version_id)
        if existing.status == StrategyVersionStatus.FROZEN:
            return existing
        if not self._has_deployment(strategy_version_id):
            raise StrategyServiceError("strategy_version can only be frozen after it is attached to a deployment")
        frozen = existing.model_copy(
            update={
                "status": StrategyVersionStatus.FROZEN,
                "frozen_at": datetime.now(timezone.utc),
                "frozen_by": frozen_by,
            }
        )
        return self._repo.save_version(frozen)

    def _has_deployment(self, strategy_version_id: UUID) -> bool:
        if self._deployment_repo is None:
            return False
        return bool(self._deployment_repo.list_deployments_for_strategy_version(strategy_version_id))
