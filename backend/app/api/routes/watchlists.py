"""Watchlist CRUD routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.watchlists import (
    WatchlistListResponse,
    WatchlistResponse,
    WatchlistService,
    WatchlistServiceError,
    WatchlistSnapshot,
    WatchlistWriteRequest,
)


def get_watchlist_service() -> WatchlistService:
    from backend.app.watchlists.runtime_service import (
        create_watchlist_service_from_environment,
    )

    return create_watchlist_service_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])

ServiceDep = Annotated[Any, _dependency(get_watchlist_service)]


def _err(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


class TakeSnapshotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    note: str | None = None


@router.get("", response_model=WatchlistListResponse)
def list_watchlists(service: ServiceDep) -> WatchlistListResponse:
    return WatchlistListResponse(watchlists=service.list_watchlists())


@router.post("", response_model=WatchlistResponse)
def create_watchlist(request: WatchlistWriteRequest, service: ServiceDep) -> WatchlistResponse:
    try:
        watchlist = service.create_watchlist(request)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc
    return WatchlistResponse(watchlist=watchlist, snapshots=())


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
def get_watchlist(watchlist_id: UUID, service: ServiceDep) -> WatchlistResponse:
    try:
        return service.get_watchlist(watchlist_id)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc


@router.patch("/{watchlist_id}", response_model=WatchlistResponse)
def update_watchlist(watchlist_id: UUID, request: WatchlistWriteRequest, service: ServiceDep) -> WatchlistResponse:
    try:
        watchlist = service.update_watchlist(watchlist_id, request)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc
    return service.get_watchlist(watchlist.watchlist_id)


@router.post("/{watchlist_id}/delete", status_code=204)
def delete_watchlist(watchlist_id: UUID, service: ServiceDep) -> None:
    try:
        service.delete_watchlist(watchlist_id)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc


@router.post("/{watchlist_id}/archive", response_model=WatchlistResponse)
def archive_watchlist(watchlist_id: UUID, service: ServiceDep) -> WatchlistResponse:
    try:
        watchlist = service.archive_watchlist(watchlist_id)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc
    return service.get_watchlist(watchlist.watchlist_id)


@router.post("/{watchlist_id}/snapshot", response_model=WatchlistSnapshot)
def take_snapshot(watchlist_id: UUID, request: TakeSnapshotRequest, service: ServiceDep) -> WatchlistSnapshot:
    try:
        return service.take_snapshot(watchlist_id, note=request.note)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc


@router.post("/{watchlist_id}/refresh", response_model=WatchlistSnapshot)
def refresh_watchlist(watchlist_id: UUID, request: TakeSnapshotRequest, service: ServiceDep) -> WatchlistSnapshot:
    try:
        return service.take_snapshot(watchlist_id, note=request.note)
    except WatchlistServiceError as exc:
        raise _err(str(exc)) from exc


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()
