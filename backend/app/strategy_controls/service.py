"""StrategyControlsService — facade for the Controls library CRUD.

Composes:
- StrategyControlsRepository (immutable version rows)
- StrategyControlsRegistry (mutable per-library metadata)
- DeploymentRepository (binding lookup for retire guard)
"""

from __future__ import annotations

from uuid import UUID, uuid4

from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain.strategy_controls import StrategyControlsVersion

from .models import StrategyControlsVersionRecord
from .persistence import StrategyControlsRepository, StrategyControlsVersionNotFoundError
from .registry import StrategyControlsRegistry, StrategyControlsRegistryNotFoundError
from .service_models import (
    StrategyControlsDraft,
    StrategyControlsLibrary,
    StrategyControlsLibrarySummary,
    StrategyControlsVersionSummary,
    StrategyControlsUsedByResponse,
)


class StrategyControlsNotFoundError(LookupError):
    pass


class StrategyControlsBoundError(RuntimeError):
    """Raised when a retire is blocked because deployments are bound."""

    def __init__(self, deployment_ids: list[UUID]) -> None:
        super().__init__(
            f"strategy_controls is bound by {len(deployment_ids)} deployment(s)"
        )
        self.deployment_ids = deployment_ids


class StrategyControlsService:
    def __init__(
        self,
        *,
        repository: StrategyControlsRepository,
        registry: StrategyControlsRegistry,
        deployment_repository: DeploymentRepository,
    ) -> None:
        self._repo = repository
        self._registry = registry
        self._deployment_repo = deployment_repository

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_libraries(self) -> list[StrategyControlsLibrarySummary]:
        registry_rows = self._registry.list_all()
        summaries: list[StrategyControlsLibrarySummary] = []
        for reg in registry_rows:
            versions = self._repo.list_versions(reg.strategy_controls_id)
            if not versions:
                continue
            head = versions[-1]
            version_ids = {v.payload.id for v in versions}
            bound = self._deployment_repo.list_deployments_for_strategy_controls_versions(
                version_ids
            )
            summaries.append(
                StrategyControlsLibrarySummary(
                    strategy_controls_id=reg.strategy_controls_id,
                    name=reg.name,
                    head_version_id=head.payload.id,
                    head_version_number=head.payload.version,
                    is_default=reg.is_default,
                    retired_at=reg.retired_at,
                    usage_count=len(bound),
                )
            )
        return summaries

    def get_library(self, strategy_controls_id: UUID) -> StrategyControlsLibrary:
        reg = self._get_registry_or_raise(strategy_controls_id)
        versions = self._repo.list_versions(strategy_controls_id)
        if not versions:
            raise StrategyControlsNotFoundError(
                f"strategy_controls_id {strategy_controls_id} has no versions"
            )
        head = versions[-1]
        history = [
            StrategyControlsVersionSummary(
                version_id=v.payload.id,
                version=v.payload.version,
                saved_at=v.saved_at,
            )
            for v in versions
        ]
        return StrategyControlsLibrary(
            strategy_controls_id=strategy_controls_id,
            name=reg.name,
            is_default=reg.is_default,
            retired_at=reg.retired_at,
            head=head,
            history=history,
        )

    def get_version(self, version_id: UUID) -> StrategyControlsVersionRecord:
        try:
            return self._repo.load_version(version_id)
        except StrategyControlsVersionNotFoundError as exc:
            raise StrategyControlsNotFoundError(str(exc)) from exc

    def used_by(self, strategy_controls_id: UUID) -> StrategyControlsUsedByResponse:
        self._get_registry_or_raise(strategy_controls_id)
        versions = self._repo.list_versions(strategy_controls_id)
        version_ids = {v.payload.id for v in versions}
        bound = self._deployment_repo.list_deployments_for_strategy_controls_versions(
            version_ids
        )
        return StrategyControlsUsedByResponse(
            deployment_ids=[d.deployment_id for d in bound]
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self, name: str, draft: StrategyControlsDraft
    ) -> StrategyControlsVersionRecord:
        sc_id = uuid4()
        version = self._build_version(
            strategy_controls_id=sc_id, version_number=1, draft=draft, name=name
        )
        record = self._repo.save_version(version)
        self._registry.upsert_name(sc_id, name)
        return record

    def edit(
        self, strategy_controls_id: UUID, draft: StrategyControlsDraft
    ) -> StrategyControlsVersionRecord:
        self._get_registry_or_raise(strategy_controls_id)
        next_version = self._repo.next_version_number(strategy_controls_id)
        version = self._build_version(
            strategy_controls_id=strategy_controls_id,
            version_number=next_version,
            draft=draft,
            name=draft.name,
        )
        record = self._repo.save_version(version)
        self._registry.upsert_name(strategy_controls_id, draft.name)
        return record

    def duplicate(
        self, source_version_id: UUID, new_name: str
    ) -> StrategyControlsVersionRecord:
        source_record = self.get_version(source_version_id)
        source = source_record.payload
        new_sc_id = uuid4()
        new_version = StrategyControlsVersion(
            id=uuid4(),
            strategy_controls_id=new_sc_id,
            version=1,
            name=new_name,
            timeframe=source.timeframe,
            allowed_directions=source.allowed_directions,
            higher_timeframe_confirmation_required=source.higher_timeframe_confirmation_required,
            session_preference=source.session_preference,
            session_windows=list(source.session_windows),
            avoid_first_minutes=source.avoid_first_minutes,
            no_new_entries_after=source.no_new_entries_after,
            force_flat_by=source.force_flat_by,
            time_based_exit_after_bars=source.time_based_exit_after_bars,
            time_based_exit_after_minutes=source.time_based_exit_after_minutes,
            time_based_exit_after_days=source.time_based_exit_after_days,
            cooldown_bars=source.cooldown_bars,
            cooldown_minutes=source.cooldown_minutes,
            max_trades_per_session=source.max_trades_per_session,
            max_trades_per_day=source.max_trades_per_day,
            earnings_news_blackout_enabled=source.earnings_news_blackout_enabled,
            max_consecutive_losses_halt=source.max_consecutive_losses_halt,
            skip_power_hour=source.skip_power_hour,
            day_of_week_restrictions=tuple(source.day_of_week_restrictions),
            feature_refs=list(source.feature_refs),
            regime_filter_refs=list(source.regime_filter_refs),
        )
        record = self._repo.save_version(new_version)
        self._registry.upsert_name(new_sc_id, new_name)
        return record

    def retire(self, strategy_controls_id: UUID) -> None:
        self._get_registry_or_raise(strategy_controls_id)
        versions = self._repo.list_versions(strategy_controls_id)
        version_ids = {v.payload.id for v in versions}
        bound = self._deployment_repo.list_deployments_for_strategy_controls_versions(
            version_ids
        )
        if bound:
            raise StrategyControlsBoundError(
                [d.deployment_id for d in bound]
            )
        self._registry.mark_retired(strategy_controls_id)

    def set_default(self, strategy_controls_id: UUID) -> None:
        self._get_registry_or_raise(strategy_controls_id)
        self._registry.set_default(strategy_controls_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_registry_or_raise(self, strategy_controls_id: UUID):  # type: ignore[no-untyped-def]
        try:
            return self._registry.get(strategy_controls_id)
        except StrategyControlsRegistryNotFoundError as exc:
            raise StrategyControlsNotFoundError(str(exc)) from exc

    @staticmethod
    def _build_version(
        *,
        strategy_controls_id: UUID,
        version_number: int,
        draft: StrategyControlsDraft,
        name: str,
    ) -> StrategyControlsVersion:
        return StrategyControlsVersion(
            id=uuid4(),
            strategy_controls_id=strategy_controls_id,
            version=version_number,
            name=name,
            timeframe=draft.timeframe,
            allowed_directions=draft.allowed_directions,
            higher_timeframe_confirmation_required=draft.higher_timeframe_confirmation_required,
            session_preference=draft.session_preference,
            session_windows=draft.session_windows,
            avoid_first_minutes=draft.avoid_first_minutes,
            no_new_entries_after=draft.no_new_entries_after,
            force_flat_by=draft.force_flat_by,
            time_based_exit_after_bars=draft.time_based_exit_after_bars,
            time_based_exit_after_minutes=draft.time_based_exit_after_minutes,
            time_based_exit_after_days=draft.time_based_exit_after_days,
            cooldown_bars=draft.cooldown_bars,
            cooldown_minutes=draft.cooldown_minutes,
            max_trades_per_session=draft.max_trades_per_session,
            max_trades_per_day=draft.max_trades_per_day,
            earnings_news_blackout_enabled=draft.earnings_news_blackout_enabled,
            max_consecutive_losses_halt=draft.max_consecutive_losses_halt,
            skip_power_hour=draft.skip_power_hour,
            day_of_week_restrictions=tuple(draft.day_of_week_restrictions),
            feature_refs=draft.feature_refs,
            regime_filter_refs=draft.regime_filter_refs,
        )
