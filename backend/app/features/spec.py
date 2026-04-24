from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeatureValidationError(ValueError):
    """Raised when a feature identity violates canonical feature rules."""


class FeatureNamespace(StrEnum):
    PRICE = "price"
    TECHNICAL = "technical"
    SESSION = "session"
    PORTFOLIO = "portfolio"


class FeatureScope(StrEnum):
    SYMBOL = "symbol"
    SESSION = "session"
    PORTFOLIO = "portfolio"


CANONICAL_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"})


class FeatureSpec(BaseModel):
    """Immutable canonical request for one feature."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    namespace: FeatureNamespace
    timeframe: str
    source: str
    params: Mapping[str, Any] = Field(default_factory=dict)
    lookback: int = Field(default=0, ge=0)
    shift: int = Field(default=0, ge=0)
    scope: FeatureScope = FeatureScope.SYMBOL
    version: str = "v1"

    @field_validator("kind", "source", "version")
    @classmethod
    def require_non_empty_lower_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise FeatureValidationError("feature string fields cannot be empty")
        return normalized.lower()

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, value: str) -> str:
        if value not in CANONICAL_TIMEFRAMES:
            raise FeatureValidationError(f"unsupported timeframe '{value}'; use one of {sorted(CANONICAL_TIMEFRAMES)}")
        return value

    @field_validator("params")
    @classmethod
    def freeze_params(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return MappingProxyType(dict(value))

    @model_validator(mode="after")
    def validate_scope_namespace(self) -> "FeatureSpec":
        if self.namespace == FeatureNamespace.PORTFOLIO and self.scope != FeatureScope.PORTFOLIO:
            raise FeatureValidationError("portfolio features must use portfolio scope")
        if self.namespace == FeatureNamespace.SESSION and self.scope not in {FeatureScope.SESSION, FeatureScope.SYMBOL}:
            raise FeatureValidationError("session features must use session or symbol scope")
        return self
