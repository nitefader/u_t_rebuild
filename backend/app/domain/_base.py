from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DomainSchema(BaseModel):
    """Base for pure Pydantic domain contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        validate_assignment=True,
    )


class VersionRef(DomainSchema):
    """Reference to an immutable versioned domain object."""

    id: UUID
    version: int = Field(ge=1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


JsonDict = dict[str, Any]
