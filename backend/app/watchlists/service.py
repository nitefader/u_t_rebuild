"""Watchlist CRUD, archive/delete guards, and dynamic refresh snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from backend.app.domain._base import utc_now

from .models import (
    Watchlist,
    WatchlistKind,
    WatchlistResponse,
    WatchlistSnapshot,
    WatchlistWriteRequest,
)
from .persistence import WatchlistNotFoundError, WatchlistRepository


class WatchlistServiceError(RuntimeError):
    """Operator-readable Watchlist failure."""


class WatchlistReferenceLookup(Protocol):
    def active_deployment_names_for_watchlist(self, watchlist_id: UUID) -> tuple[str, ...]: ...


class DynamicWatchlistResolution(Protocol):
    symbols: tuple[str, ...]
    note: str | None
    source_run_id: UUID | None
    source_label: str | None
    evidence: dict[str, object]


class DynamicWatchlistResolver(Protocol):
    def refresh(self, watchlist: Watchlist) -> DynamicWatchlistResolution: ...


class WatchlistService:
    def __init__(
        self,
        *,
        repository: WatchlistRepository,
        dynamic_resolver: DynamicWatchlistResolver | None = None,
        reference_lookup: WatchlistReferenceLookup | None = None,
    ) -> None:
        self._repo = repository
        self._dynamic_resolver = dynamic_resolver
        self._reference_lookup = reference_lookup

    def list_watchlists(self) -> tuple[Watchlist, ...]:
        return self._repo.list_watchlists()

    def get_watchlist(self, watchlist_id: UUID) -> WatchlistResponse:
        try:
            watchlist = self._repo.get_watchlist(watchlist_id)
        except WatchlistNotFoundError as exc:
            raise WatchlistServiceError(str(exc)) from exc
        snapshots = self._repo.list_snapshots(watchlist_id)
        return WatchlistResponse(watchlist=watchlist, snapshots=snapshots)

    def create_watchlist(self, request: WatchlistWriteRequest) -> Watchlist:
        if request.kind == WatchlistKind.STATIC and not request.static_symbols:
            raise WatchlistServiceError("static watchlist requires at least one symbol")
        if request.kind == WatchlistKind.DYNAMIC and request.dynamic_rules is None:
            raise WatchlistServiceError("dynamic watchlist requires dynamic_rules")
        watchlist = Watchlist(
            watchlist_id=uuid4(),
            name=request.name.strip(),
            description=request.description,
            kind=request.kind,
            static_symbols=request.static_symbols,
            dynamic_rules=request.dynamic_rules,
        )
        return self._repo.save_watchlist(watchlist)

    def update_watchlist(self, watchlist_id: UUID, request: WatchlistWriteRequest) -> Watchlist:
        try:
            existing = self._repo.get_watchlist(watchlist_id)
        except WatchlistNotFoundError as exc:
            raise WatchlistServiceError(str(exc)) from exc
        updated = existing.model_copy(
            update={
                "name": request.name.strip(),
                "description": request.description,
                "kind": request.kind,
                "static_symbols": request.static_symbols,
                "dynamic_rules": request.dynamic_rules,
                "updated_at": utc_now(),
            }
        )
        return self._repo.save_watchlist(updated)

    def delete_watchlist(self, watchlist_id: UUID) -> None:
        try:
            watchlist = self._repo.get_watchlist(watchlist_id)
        except WatchlistNotFoundError as exc:
            raise WatchlistServiceError(str(exc)) from exc
        refs = self._active_deployment_names(watchlist_id)
        if refs:
            raise WatchlistServiceError(
                "cannot delete watchlist while active deployments reference it: "
                + ", ".join(refs)
            )
        if watchlist.snapshot_count > 0:
            raise WatchlistServiceError(
                "watchlist has snapshot history; archive it instead of deleting audit evidence"
            )
        self._repo.delete_watchlist(watchlist_id)

    def archive_watchlist(self, watchlist_id: UUID) -> Watchlist:
        try:
            watchlist = self._repo.get_watchlist(watchlist_id)
        except WatchlistNotFoundError as exc:
            raise WatchlistServiceError(str(exc)) from exc
        refs = self._active_deployment_names(watchlist_id)
        if refs:
            raise WatchlistServiceError(
                "cannot archive watchlist while active deployments reference it: "
                + ", ".join(refs)
            )
        archived = watchlist.model_copy(
            update={"status": "archived", "archived_at": utc_now(), "updated_at": utc_now()}
        )
        return self._repo.save_watchlist(archived)

    def take_snapshot(self, watchlist_id: UUID, *, note: str | None = None) -> WatchlistSnapshot:
        try:
            watchlist = self._repo.get_watchlist(watchlist_id)
        except WatchlistNotFoundError as exc:
            raise WatchlistServiceError(str(exc)) from exc

        if watchlist.kind == WatchlistKind.STATIC:
            symbols = watchlist.static_symbols
            source_run_id = None
            source_label = "Static Watchlist"
            evidence: dict[str, object] = {"source": "static_symbols"}
        else:
            if self._dynamic_resolver is None:
                raise WatchlistServiceError("dynamic watchlist resolver is not configured")
            resolved = self._dynamic_resolver.refresh(watchlist)
            symbols = tuple(dict.fromkeys(symbol.upper() for symbol in resolved.symbols if symbol))
            source_run_id = resolved.source_run_id
            source_label = resolved.source_label
            evidence = dict(resolved.evidence)
            note = " - ".join(part for part in (note, resolved.note) if part)

        previous = self._repo.latest_snapshot(watchlist_id)
        previous_symbols = set(previous.symbols) if previous is not None else set()
        current_symbols = set(symbols)
        snapshot = WatchlistSnapshot(
            watchlist_snapshot_id=uuid4(),
            watchlist_id=watchlist_id,
            taken_at=datetime.now(timezone.utc),
            symbols=symbols,
            note=note,
            source_run_id=source_run_id,
            source_label=source_label,
            added_symbols=tuple(sorted(current_symbols - previous_symbols)),
            removed_symbols=tuple(sorted(previous_symbols - current_symbols)),
            stayed_symbols=tuple(sorted(current_symbols & previous_symbols)),
            evidence=evidence,
        )
        self._repo.save_snapshot(snapshot)
        new_count = len(self._repo.list_snapshots(watchlist_id))
        self._repo.save_watchlist(
            watchlist.model_copy(
                update={
                    "latest_snapshot_id": snapshot.watchlist_snapshot_id,
                    "snapshot_count": new_count,
                    "updated_at": utc_now(),
                }
            )
        )
        return snapshot

    def latest_snapshot(self, watchlist_id: UUID) -> WatchlistSnapshot | None:
        return self._repo.latest_snapshot(watchlist_id)

    def active_deployment_names_for_watchlist(self, watchlist_id: UUID) -> tuple[str, ...]:
        return self._active_deployment_names(watchlist_id)

    def _active_deployment_names(self, watchlist_id: UUID) -> tuple[str, ...]:
        if self._reference_lookup is None:
            return ()
        return self._reference_lookup.active_deployment_names_for_watchlist(watchlist_id)
