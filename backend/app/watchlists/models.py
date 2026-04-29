"""Persistent shapes for Watchlist + WatchlistSnapshot."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain._base import utc_now


class WatchlistKind(StrEnum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class WatchlistDynamicRules(BaseModel):
    """Operator-authored dynamic-membership rules.

    V1 carries a flexible JSON map; the resolver that interprets the
    rules lives outside this package. The shape is pinned only enough
    to ensure the persisted payload round-trips.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    universe: str = "us_equities"
    filters: tuple[dict[str, object], ...] = ()
    notes: str | None = None
    source_type: Literal["manual_rules", "screener_version", "template"] = "manual_rules"
    screener_id: UUID | None = None
    screener_version_id: UUID | None = None
    template_key: str | None = None
    refresh_policy: Literal["manual", "scheduled_review", "auto_snapshot"] = "manual"
    approval_policy: Literal["operator_review", "auto_approve"] = "operator_review"


class Watchlist(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watchlist_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    kind: WatchlistKind = WatchlistKind.STATIC
    static_symbols: tuple[str, ...] = ()
    dynamic_rules: WatchlistDynamicRules | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    latest_snapshot_id: UUID | None = None
    snapshot_count: int = 0
    status: Literal["active", "archived"] = "active"
    archived_at: datetime | None = None

    @field_validator("static_symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sym.upper() for sym in value if sym.strip())


class WatchlistSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watchlist_snapshot_id: UUID
    watchlist_id: UUID
    taken_at: datetime
    symbols: tuple[str, ...]
    note: str | None = None
    source_run_id: UUID | None = None
    source_label: str | None = None
    added_symbols: tuple[str, ...] = ()
    removed_symbols: tuple[str, ...] = ()
    stayed_symbols: tuple[str, ...] = ()
    evidence: dict[str, object] = Field(default_factory=dict)


class WatchlistResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watchlist: Watchlist
    snapshots: tuple[WatchlistSnapshot, ...] = ()


class WatchlistListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    watchlists: tuple[Watchlist, ...] = ()


class WatchlistWriteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    kind: WatchlistKind = WatchlistKind.STATIC
    static_symbols: tuple[str, ...] = ()
    dynamic_rules: WatchlistDynamicRules | None = None

    @field_validator("static_symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sym.upper() for sym in value if sym.strip())
