from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from ._base import DomainSchema, JsonDict, utc_now


class SymbolBias(StrEnum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class UniverseSymbol(DomainSchema):
    symbol: str
    bias: SymbolBias = SymbolBias.NEUTRAL
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: JsonDict = Field(default_factory=dict)


class UniverseSnapshot(DomainSchema):
    id: UUID
    universe_id: UUID
    version: int = Field(ge=1)
    name: str
    symbols: list[UniverseSymbol] = Field(min_length=1)
    source_refs: list[UUID] = Field(default_factory=list)
    resolved_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
