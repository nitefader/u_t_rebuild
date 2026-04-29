"""Composition root for WatchlistService."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.app.config.runtime_paths import get_runtime_db_path

from .models import Watchlist, WatchlistDynamicRules
from .persistence import WatchlistRepository
from .service import WatchlistService


def create_watchlist_service_from_environment() -> WatchlistService:
    db_path = get_runtime_db_path()
    return WatchlistService(
        repository=WatchlistRepository(db_path),
        dynamic_resolver=_ScreenerDynamicWatchlistResolver(),
        reference_lookup=_DeploymentWatchlistReferenceLookup(db_path),
    )


@dataclass(frozen=True)
class _DynamicResolution:
    symbols: tuple[str, ...]
    note: str | None
    source_run_id: UUID | None
    source_label: str | None
    evidence: dict[str, object]


class _ScreenerDynamicWatchlistResolver:
    def refresh(self, watchlist: Watchlist) -> _DynamicResolution:
        rules = watchlist.dynamic_rules
        if rules is None:
            raise RuntimeError("dynamic watchlist requires dynamic_rules")
        if rules.source_type == "screener_version":
            return self._refresh_screener_version(watchlist, rules)
        if rules.source_type == "template":
            raise RuntimeError("template dynamic watchlists must first be saved as a visible Screener")
        raise RuntimeError("dynamic watchlist source_type is not backed by a resolver")

    def _refresh_screener_version(
        self,
        watchlist: Watchlist,
        rules: WatchlistDynamicRules,
    ) -> _DynamicResolution:
        if rules.screener_id is None or rules.screener_version_id is None:
            raise RuntimeError("dynamic screener watchlist requires screener_id and screener_version_id")
        from backend.app.screener.runtime import create_screener_service_from_environment

        service = create_screener_service_from_environment()
        run = service.run_screener(
            rules.screener_id,
            version_id=rules.screener_version_id,
            run_kind="refresh",
        )
        symbols = tuple(row.symbol for row in run.results if row.matched)
        return _DynamicResolution(
            symbols=symbols,
            note=f"Refreshed from Screener run {run.id}",
            source_run_id=run.id,
            source_label=f"Screener refresh: {watchlist.name}",
            evidence={
                "source_type": "screener_version",
                "screener_id": str(rules.screener_id),
                "screener_version_id": str(rules.screener_version_id),
                "matched_count": run.matched_count,
                "sources_used": run.sources_used,
            },
        )

class _DeploymentWatchlistReferenceLookup:
    def __init__(self, db_path) -> None:
        self._db_path = db_path

    def active_deployment_names_for_watchlist(self, watchlist_id: UUID) -> tuple[str, ...]:
        from backend.app.deployments import DeploymentLifecycleStatus
        from backend.app.deployments.persistence import DeploymentRepository

        repo = DeploymentRepository(self._db_path)
        names = []
        for deployment in repo.list_deployments():
            if watchlist_id not in deployment.watchlist_ids:
                continue
            if deployment.lifecycle_status in {
                DeploymentLifecycleStatus.ACTIVE,
                DeploymentLifecycleStatus.PAUSED,
            }:
                names.append(deployment.name)
        return tuple(names)
