"""Typed Screener domain — Screener / Version / Criterion / Run / Result.

All shapes are pydantic models so they round-trip through SQLite ``json1``
columns without manual serialization. ``model_config = ConfigDict(extra="forbid")``
on the request/criterion shapes catches operator typos at the API boundary
(per the production-grade-only doctrine in ``memory/MEMORY.md``).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain._base import utc_now


# ---------------------------------------------------------------- metrics


ScreenerFieldValue = bool | float | str


class ScreenerMetric(str, Enum):
    """Vocabulary of metrics a Screener criterion can pin.

    V1 ships the metrics the operator named (Alpaca + technical bar
    derivations from the existing Data Center cache). New metrics extend
    this enum as they land — never as raw strings.
    """

    PRICE = "price"
    AVG_VOLUME_20D = "avg_volume_20d"
    RELATIVE_VOLUME = "relative_volume"
    GAP_PCT = "gap_pct"
    CHANGE_PCT = "change_pct"
    RSI_14 = "rsi_14"
    ATR_14_PCT = "atr_14_pct"
    PRIOR_DAY_CLOSE = "prior_day_close"
    PRIOR_DAY_RANGE_PCT = "prior_day_range_pct"
    BROKER_TRADABLE = "broker.tradable"
    BROKER_FRACTIONABLE = "broker.fractionable"
    BROKER_SHORTABLE = "broker.shortable"
    BROKER_EASY_TO_BORROW = "broker.easy_to_borrow"
    BROKER_ACTIVE = "broker.active"
    BROKER_EXCHANGE = "broker.exchange"
    BROKER_ASSET_CLASS = "broker.asset_class"
    BROKER_NAME = "broker.name"


class ScreenerCriterionOperator(str, Enum):
    GTE = "gte"
    LTE = "lte"
    GT = "gt"
    LT = "lt"
    BETWEEN = "between"
    EQ = "eq"


class ScreenerCriterion(BaseModel):
    """One row of the Screener's criteria grid.

    For BETWEEN: ``value`` is the lower bound, ``value_max`` the upper.
    For all other operators ``value_max`` is null and ignored.
    """

    model_config = ConfigDict(extra="forbid")

    metric: ScreenerMetric
    operator: ScreenerCriterionOperator
    value: ScreenerFieldValue
    value_max: float | None = None
    label: str | None = None

    @field_validator("value_max")
    @classmethod
    def _between_requires_value_max(cls, v: float | None, info) -> float | None:
        op = info.data.get("operator")
        if op == ScreenerCriterionOperator.BETWEEN and v is None:
            raise ValueError("BETWEEN operator requires value_max")
        return v

    @field_validator("value")
    @classmethod
    def _between_requires_numeric_value(cls, v: ScreenerFieldValue, info) -> ScreenerFieldValue:
        op = info.data.get("operator")
        if op == ScreenerCriterionOperator.BETWEEN and not isinstance(v, int | float):
            raise ValueError("BETWEEN operator requires numeric value")
        return v


class ScreenerExpressionKind(str, Enum):
    ALL = "all"
    ANY = "any"
    NOT = "not"
    CRITERION = "criterion"


class ScreenerExpression(BaseModel):
    """Typed logical expression tree for Screener criteria.

    Backwards compatibility: old flat ``criteria`` rows compile to an
    ``all([...])`` expression at run time. No arbitrary eval, no raw SQL.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ScreenerExpressionKind
    criterion: ScreenerCriterion | None = None
    children: tuple["ScreenerExpression", ...] = Field(default_factory=tuple)

    @field_validator("children")
    @classmethod
    def _validate_children(
        cls,
        v: tuple["ScreenerExpression", ...],
        info,
    ) -> tuple["ScreenerExpression", ...]:
        kind = info.data.get("kind")
        if kind == ScreenerExpressionKind.NOT and len(v) != 1:
            raise ValueError("NOT expression requires exactly one child")
        return v

    @field_validator("criterion")
    @classmethod
    def _validate_criterion(cls, v: ScreenerCriterion | None, info) -> ScreenerCriterion | None:
        kind = info.data.get("kind")
        if kind == ScreenerExpressionKind.CRITERION and v is None:
            raise ValueError("criterion expression requires criterion")
        return v


# ---------------------------------------------------------------- universe source


class ScreenerUniverseSourceKind(str, Enum):
    EXPLICIT = "explicit"
    WATCHLIST = "watchlist"
    PRESET = "preset"
    MARKET_LIST = "market_list"


class ScreenerUniverseSource(BaseModel):
    """Where the Screener pulls its candidate symbols from before filtering.

    - EXPLICIT: ``symbols`` carries the operator-typed list.
    - WATCHLIST: ``watchlist_id`` references an existing Watchlist; the
      service expands it to symbols at run time. Stays decoupled — we
      never mutate the watchlist.
    - PRESET: ``preset`` is a built-in name like ``liquid_large_caps``;
      the service maps it to a hardcoded ticker list.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ScreenerUniverseSourceKind
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    watchlist_id: UUID | None = None
    preset: str | None = None
    market_list_key: str | None = None

    @field_validator("symbols", mode="before")
    @classmethod
    def _upper_strip(cls, v):  # type: ignore[no-untyped-def]
        if v is None:
            return ()
        return tuple(s.strip().upper() for s in v if isinstance(s, str) and s.strip())


# ---------------------------------------------------------------- screener


class ScreenerVersion(BaseModel):
    """Versioned Screener config. Drafts edit in place; once a run completes
    it pins a `frozen_at`/`frozen_by` lineage, but unlike Strategy we don't
    require freeze before run — research-surface doctrine: any version may
    be verified, freeze is for deployment only (which the Screener never
    does)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    screener_id: UUID
    version: int = 1
    name: str
    description: str | None = None
    universe_source: ScreenerUniverseSource
    criteria: tuple[ScreenerCriterion, ...] = Field(default_factory=tuple)
    expression: ScreenerExpression | None = None
    timeframe: Literal["1d", "1h", "5m"] = "1d"
    source_preference: Literal["auto", "alpaca", "data_center"] = "auto"
    sort_metric: ScreenerMetric | None = None
    sort_descending: bool = True
    max_results: int = Field(default=200, ge=1, le=1000)
    tags: tuple[str, ...] = Field(default_factory=tuple)
    created_at: datetime = Field(default_factory=utc_now)


class Screener(BaseModel):
    """Top-level Screener row (operator-readable name + lifecycle status)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str | None = None
    tags: tuple[str, ...] = Field(default_factory=tuple)
    status: Literal["draft", "active", "deprecated", "archived"] = "active"
    created_at: datetime = Field(default_factory=utc_now)
    last_run_at: datetime | None = None
    last_run_id: UUID | None = None
    version_count: int = 1
    latest_version_id: UUID | None = None


# ---------------------------------------------------------------- run


class ScreenerRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ScreenerResultRow(BaseModel):
    """One row of a ScreenerRun's result grid.

    `metrics` carries the actual computed metric values per criterion (so
    operators can see why a symbol passed). `matched` is true when ALL
    criteria pass; `score` is a normalized rank (0..1) used for ordering
    when ``sort_metric`` is set.
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str
    matched: bool
    metrics: dict[str, ScreenerFieldValue | None]
    failed_criteria: tuple[str, ...] = Field(default_factory=tuple)
    passed_criteria: tuple[str, ...] = Field(default_factory=tuple)
    blocked_reasons: tuple[str, ...] = Field(default_factory=tuple)
    score: float | None = None
    sparkline: tuple[float, ...] = Field(default_factory=tuple)
    evidence: dict[str, object] = Field(default_factory=dict)


class ScreenerRun(BaseModel):
    """One immutable Screener execution + its results."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    screener_id: UUID
    screener_version_id: UUID
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    status: ScreenerRunStatus = ScreenerRunStatus.QUEUED
    run_kind: Literal["run", "rerun", "refresh", "scheduled"] = "run"
    parent_run_id: UUID | None = None
    universe_size: int = 0
    matched_count: int = 0
    results: tuple[ScreenerResultRow, ...] = Field(default_factory=tuple)
    error: str | None = None
    sources_used: tuple[str, ...] = Field(default_factory=tuple)
    source_evidence: dict[str, object] = Field(default_factory=dict)
    source_freshness: dict[str, object] = Field(default_factory=dict)
    audit_events: tuple[dict[str, object], ...] = Field(default_factory=tuple)
    cache_hit_rate: float | None = None
    operator_session_id: str | None = None


ScreenerExpression.model_rebuild()
