"""MarketDataPipeline — first-class shared market-data subscription.

Per ``final_roadmap_and_arch_decisions_and_guidelines.md`` §3 / plan_review §I
FINAL alignment, a ``MarketDataPipeline`` is the unit of streaming/historical
fan-out:

    One paid stream can serve many accounts.
    Do not open duplicate streams per account.

Pipelines are mediated by FeatureEngine — Deployments declare feature demand,
the resolver picks a pipeline per FeatureKey, and FeatureEngine subscribes
once per ``(pipeline, FeatureKey)``.

Trading-mode binding
--------------------
``trading_mode`` is ``TradingMode | None``:

- ``TradingMode.BROKER_PAPER`` — pipeline uses broker-paper credentials
  (e.g. Alpaca paper-environment API key for market data).
- ``TradingMode.BROKER_LIVE`` — pipeline uses broker-live credentials.
- ``None`` — vendor-data-only pipeline that requires no broker credential
  (e.g. Yahoo historical, future news vendor).

Only ``BROKER_PAPER`` / ``BROKER_LIVE`` are accepted; chart-lab and sim-lab
modes are out of scope for credential-tied pipelines (they consume snapshots
from broker- or vendor-credentialed pipelines, they don't own credentials).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain import BROKER_MODES, TradingMode
from backend.app.domain._base import utc_now

from .resolver import MarketDataCapabilities, Provider


class PipelineStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


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
    Two consumers on different feeds for the same symbol must not share
    a hub; the hub registry uses ``(provider, trading_mode, data_feed)``
    today, the matching tuple in the catalog is ``(service_id,
    trading_mode, data_feed)``.

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
    data_feed: str = DEFAULT_DATA_FEED
    trading_mode: TradingMode | None = None
    capabilities: MarketDataCapabilities = Field(default_factory=MarketDataCapabilities)
    status: PipelineStatus = PipelineStatus.DRAFT
    is_default_for_provider: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    disabled_at: datetime | None = None

    @field_validator("trading_mode")
    @classmethod
    def trading_mode_must_be_broker_or_none(cls, value: TradingMode | None) -> TradingMode | None:
        if value is None:
            return None
        if value not in BROKER_MODES:
            raise ValueError(
                f"MarketDataPipeline.trading_mode must be None or a BROKER mode "
                f"(BROKER_PAPER / BROKER_LIVE); got {value.value}"
            )
        return value

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
    data_feed: str = DEFAULT_DATA_FEED
    trading_mode: TradingMode | None = None
    capabilities: MarketDataCapabilities | None = None

    @field_validator("trading_mode")
    @classmethod
    def trading_mode_must_be_broker_or_none(cls, value: TradingMode | None) -> TradingMode | None:
        if value is None or value in BROKER_MODES:
            return value
        raise ValueError(
            f"MarketDataPipeline.trading_mode must be None or a BROKER mode "
            f"(BROKER_PAPER / BROKER_LIVE); got {value.value}"
        )

    @field_validator("data_feed")
    @classmethod
    def data_feed_normalize(cls, value: str) -> str:
        return (value or DEFAULT_DATA_FEED).lower()


class MarketDataPipelineEdit(BaseModel):
    """Operator-supplied PATCH for a Pipeline (cosmetic fields only).

    PUT /pipelines/{id} is intentionally narrowed to the two safe fields
    that don't change the stream's identity tuple
    ``(service_id, trading_mode, data_feed)``. Identity changes go
    through dedicated endpoints:

    - ``service_id`` rebind → ``POST /pipelines/{id}/attach-service``
    - ``service_id`` / ``trading_mode`` / ``data_feed`` change → disable
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
