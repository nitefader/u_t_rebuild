"""ExecutionPlanService — facade for the ExecutionPlan library CRUD.

Composes:
- ExecutionPlanRepository (immutable version rows)
- ExecutionPlanRegistry (mutable per-library metadata)
- DeploymentRepository (binding lookup for retire guard)
"""

from __future__ import annotations

from uuid import UUID, uuid4

from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain.execution_style import ExecutionStyleVersion

from .models import ExecutionPlanVersionRecord
from .persistence import ExecutionPlanRepository, ExecutionPlanVersionNotFoundError
from .registry import ExecutionPlanRegistry, ExecutionPlanRegistryNotFoundError
from .service_models import (
    ExecutionPlanDraft,
    ExecutionPlanLibrary,
    ExecutionPlanLibrarySummary,
    ExecutionPlanVersionSummary,
    ExecutionPlanUsedByResponse,
)


class ExecutionPlanNotFoundError(LookupError):
    pass


class ExecutionPlanBoundError(RuntimeError):
    """Raised when a retire is blocked because deployments are bound."""

    def __init__(self, deployment_ids: list[UUID]) -> None:
        super().__init__(
            f"execution_plan is bound by {len(deployment_ids)} deployment(s)"
        )
        self.deployment_ids = deployment_ids


class ExecutionPlanService:
    def __init__(
        self,
        *,
        repository: ExecutionPlanRepository,
        registry: ExecutionPlanRegistry,
        deployment_repository: DeploymentRepository,
    ) -> None:
        self._repo = repository
        self._registry = registry
        self._deployment_repo = deployment_repository

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_libraries(self) -> list[ExecutionPlanLibrarySummary]:
        registry_rows = self._registry.list_all()
        summaries: list[ExecutionPlanLibrarySummary] = []
        for reg in registry_rows:
            versions = self._repo.list_versions(reg.execution_plan_id)
            if not versions:
                continue
            head = versions[-1]
            version_ids = {v.payload.id for v in versions}
            bound = self._deployment_repo.list_deployments_for_execution_plan_versions(
                version_ids
            )
            summaries.append(
                ExecutionPlanLibrarySummary(
                    execution_plan_id=reg.execution_plan_id,
                    name=reg.name,
                    head_version_id=head.payload.id,
                    head_version_number=head.payload.version,
                    is_default=reg.is_default,
                    retired_at=reg.retired_at,
                    usage_count=len(bound),
                )
            )
        return summaries

    def get_library(self, execution_plan_id: UUID) -> ExecutionPlanLibrary:
        reg = self._get_registry_or_raise(execution_plan_id)
        versions = self._repo.list_versions(execution_plan_id)
        if not versions:
            raise ExecutionPlanNotFoundError(
                f"execution_plan_id {execution_plan_id} has no versions"
            )
        head = versions[-1]
        history = [
            ExecutionPlanVersionSummary(
                version_id=v.payload.id,
                version=v.payload.version,
                saved_at=v.saved_at,
            )
            for v in versions
        ]
        return ExecutionPlanLibrary(
            execution_plan_id=execution_plan_id,
            name=reg.name,
            is_default=reg.is_default,
            retired_at=reg.retired_at,
            head=head,
            history=history,
        )

    def get_version(self, version_id: UUID) -> ExecutionPlanVersionRecord:
        try:
            return self._repo.load_version(version_id)
        except ExecutionPlanVersionNotFoundError as exc:
            raise ExecutionPlanNotFoundError(str(exc)) from exc

    def used_by(self, execution_plan_id: UUID) -> ExecutionPlanUsedByResponse:
        self._get_registry_or_raise(execution_plan_id)
        versions = self._repo.list_versions(execution_plan_id)
        version_ids = {v.payload.id for v in versions}
        bound = self._deployment_repo.list_deployments_for_execution_plan_versions(
            version_ids
        )
        return ExecutionPlanUsedByResponse(
            deployment_ids=[d.deployment_id for d in bound]
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self, name: str, draft: ExecutionPlanDraft
    ) -> ExecutionPlanVersionRecord:
        ep_id = uuid4()
        version = self._build_version(
            execution_plan_id=ep_id, version_number=1, draft=draft, name=name
        )
        record = self._repo.save_version(version)
        self._registry.upsert_name(ep_id, name)
        return record

    def edit(
        self, execution_plan_id: UUID, draft: ExecutionPlanDraft
    ) -> ExecutionPlanVersionRecord:
        self._get_registry_or_raise(execution_plan_id)
        next_version = self._repo.next_version_number(execution_plan_id)
        version = self._build_version(
            execution_plan_id=execution_plan_id,
            version_number=next_version,
            draft=draft,
            name=draft.name,
        )
        record = self._repo.save_version(version)
        self._registry.upsert_name(execution_plan_id, draft.name)
        return record

    def duplicate(
        self, source_version_id: UUID, new_name: str
    ) -> ExecutionPlanVersionRecord:
        source_record = self.get_version(source_version_id)
        source = source_record.payload
        new_ep_id = uuid4()
        new_version = ExecutionStyleVersion(
            id=uuid4(),
            execution_style_id=new_ep_id,
            version=1,
            name=new_name,
            entry_order_type=source.entry_order_type,
            exit_order_type=source.exit_order_type,
            time_in_force=source.time_in_force,
            entry_limit_offset_bps=source.entry_limit_offset_bps,
            cancel_after_bars=source.cancel_after_bars,
            bracket=source.bracket,
            execution_mode=source.execution_mode,
            trailing_stop_enabled=source.trailing_stop_enabled,
            scale_out_enabled=source.scale_out_enabled,
            order_retry_policy=source.order_retry_policy,
            order_cancel_policy=source.order_cancel_policy,
            order_retry_max_attempts=source.order_retry_max_attempts,
            order_retry_offset_bps=source.order_retry_offset_bps,
            feature_refs=list(source.feature_refs),
            preset=source.preset,
        )
        record = self._repo.save_version(new_version)
        self._registry.upsert_name(new_ep_id, new_name)
        return record

    def retire(self, execution_plan_id: UUID) -> None:
        self._get_registry_or_raise(execution_plan_id)
        versions = self._repo.list_versions(execution_plan_id)
        version_ids = {v.payload.id for v in versions}
        bound = self._deployment_repo.list_deployments_for_execution_plan_versions(
            version_ids
        )
        if bound:
            raise ExecutionPlanBoundError(
                [d.deployment_id for d in bound]
            )
        self._registry.mark_retired(execution_plan_id)

    def set_default(self, execution_plan_id: UUID) -> None:
        self._get_registry_or_raise(execution_plan_id)
        self._registry.set_default(execution_plan_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_registry_or_raise(self, execution_plan_id: UUID):  # type: ignore[no-untyped-def]
        try:
            return self._registry.get(execution_plan_id)
        except ExecutionPlanRegistryNotFoundError as exc:
            raise ExecutionPlanNotFoundError(str(exc)) from exc

    @staticmethod
    def _build_version(
        *,
        execution_plan_id: UUID,
        version_number: int,
        draft: ExecutionPlanDraft,
        name: str,
    ) -> ExecutionStyleVersion:
        return ExecutionStyleVersion(
            id=uuid4(),
            execution_style_id=execution_plan_id,
            version=version_number,
            name=name,
            entry_order_type=draft.entry_order_type,
            exit_order_type=draft.exit_order_type,
            time_in_force=draft.time_in_force,
            entry_limit_offset_bps=draft.entry_limit_offset_bps,
            cancel_after_bars=draft.cancel_after_bars,
            bracket=draft.bracket,
            execution_mode=draft.execution_mode,
            trailing_stop_enabled=draft.trailing_stop_enabled,
            scale_out_enabled=draft.scale_out_enabled,
            order_retry_policy=draft.order_retry_policy,
            order_cancel_policy=draft.order_cancel_policy,
            order_retry_max_attempts=draft.order_retry_max_attempts,
            order_retry_offset_bps=draft.order_retry_offset_bps,
            feature_refs=draft.feature_refs,
            preset=draft.preset,
        )
