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


class MarketDataPipeline(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    display_name: str = Field(min_length=1)
    provider: Provider
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


class MarketDataPipelineWrite(BaseModel):
    """Operator-supplied payload for creating or updating a pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1)
    provider: Provider
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


class MarketDataPipelineList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pipelines: tuple[MarketDataPipeline, ...]
