"""MarketDataPipeline — first-class shared market-data subscription.

Per ``final_roadmap_and_arch_decisions_and_guidelines.md`` §3 / plan_review §I
FINAL alignment, a ``MarketDataPipeline`` is the unit of streaming/historical
fan-out:

    One paid stream can serve many accounts.
    Do not open duplicate streams per account.

Pipelines are mediated by FeatureEngine — Deployments declare feature demand,
the resolver picks a pipeline per FeatureKey, and FeatureEngine subscribes
once per ``(pipeline, FeatureKey)``.

Asset pipeline binding
----------------------
Market-data pipelines are grouped by asset class, not broker account mode.
Paper/live are Account metadata and only influence broker API endpoints.

Examples:

- ``stock`` — equities bars/quotes/news where supported.
- ``crypto`` — crypto bars/quotes/trades where supported.
- ``option`` — option market data where supported.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain._base import utc_now

from .resolver import MarketDataCapabilities, Provider


class PipelineStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class MarketDataAssetClass(StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"
    OPTION = "option"
    FUTURE = "future"
    FOREX = "forex"


DEFAULT_DATA_FEED = "iex"


class MarketDataPipeline(BaseModel):
    """Persisted Pipeline.

    Per the DE round-2 verdict: a Pipeline is the *subscription identity*
    bound to a credentialed ``MarketDataServiceRecord``. The
    ``service_id`` foreign key is what makes "one paid stream serves
    many accounts" tractable — two Pipelines pointing at the same
    Service share authentication; two pointing at different Services
    are physically different streams.

    ``data_feed`` keys the actual stream endpoint (``iex`` / ``sip`` /
    ``delayed_sip`` / ``boats`` / ``overnight`` / ``otc`` for Alpaca).
    ``asset_class`` keys the instrument family. Two consumers on different
    feeds or asset classes for the same symbol must not share a hub; the
    live stock hub registry uses ``(provider, asset_class, data_feed)``.
    Paper/live is Account metadata, not market-data stream identity.

    ``provider`` is retained as a denormalized field for
    backward-compat reads of legacy snapshots; new code should derive
    it from the linked Service. ``capabilities`` is similarly
    deprecated — capability scoring belongs on the Service.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: UUID = Field(default_factory=uuid4)
    display_name: str = Field(min_length=1)
    provider: Provider
    service_id: UUID | None = None
    asset_class: MarketDataAssetClass = MarketDataAssetClass.STOCK
    data_feed: str = DEFAULT_DATA_FEED
    capabilities: MarketDataCapabilities = Field(default_factory=MarketDataCapabilities)
    status: PipelineStatus = PipelineStatus.DRAFT
    is_default_for_provider: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    disabled_at: datetime | None = None

    @field_validator("asset_class", mode="before")
    @classmethod
    def asset_class_normalize(cls, value: object) -> object:
        if value is None or value == "":
            return MarketDataAssetClass.STOCK
        return str(value).lower()

    @field_validator("data_feed")
    @classmethod
    def data_feed_normalize(cls, value: str) -> str:
        return (value or DEFAULT_DATA_FEED).lower()


class MarketDataPipelineWrite(BaseModel):
    """Operator-supplied payload for creating or updating a pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1)
    provider: Provider
    service_id: UUID | None = None
    asset_class: MarketDataAssetClass = MarketDataAssetClass.STOCK
    data_feed: str = DEFAULT_DATA_FEED
    capabilities: MarketDataCapabilities | None = None

    @field_validator("asset_class", mode="before")
    @classmethod
    def asset_class_normalize(cls, value: object) -> object:
        if value is None or value == "":
            return MarketDataAssetClass.STOCK
        return str(value).lower()

    @field_validator("data_feed")
    @classmethod
    def data_feed_normalize(cls, value: str) -> str:
        return (value or DEFAULT_DATA_FEED).lower()


class MarketDataPipelineEdit(BaseModel):
    """Operator-supplied PATCH for a Pipeline (cosmetic fields only).

    PUT /pipelines/{id} is intentionally narrowed to the two safe fields
    that don't change the stream's identity tuple
    ``(service_id, asset_class, data_feed)``. Identity changes go
    through dedicated endpoints:

    - ``service_id`` rebind → ``POST /pipelines/{id}/attach-service``
    - ``service_id`` / ``asset_class`` / ``data_feed`` change → disable
      this pipeline and create a new one (subscribers are bound to the
      old pipeline_id and need to migrate explicitly).

    Both fields are optional; omitted fields preserve the current value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str | None = Field(default=None, min_length=1)
    capabilities: MarketDataCapabilities | None = None


class MarketDataPipelineList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pipelines: tuple[MarketDataPipeline, ...]
