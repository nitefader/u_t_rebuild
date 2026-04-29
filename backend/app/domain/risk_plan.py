from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from ._base import DomainSchema, utc_now
from .risk_profile import PositionSizingMethod, RiskProfileVersion


class RiskPlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class RiskPlanVersionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class RiskPlanTier(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class RiskPlanSource(StrEnum):
    MANUAL = "manual"
    AI_GENERATED = "ai_generated"
    OPTIMIZATION_GENERATED = "optimization_generated"
    WALK_FORWARD_RECOMMENDED = "walk_forward_recommended"


class RiskPlanSizingMethod(StrEnum):
    FIXED_SHARES = "fixed_shares"
    FIXED_NOTIONAL = "fixed_notional"
    RISK_PERCENT = "risk_percent"
    VOLATILITY_ADJUSTED = "volatility_adjusted"
    ACCOUNT_PERCENT = "account_percent"
    CUSTOM = "custom"


class WholeShareRounding(StrEnum):
    FLOOR = "floor"
    ROUND = "round"
    CEIL = "ceil"


class RiskPlanConfig(DomainSchema):
    sizing_method: RiskPlanSizingMethod = RiskPlanSizingMethod.RISK_PERCENT

    fixed_shares: float | None = Field(default=None, gt=0)
    fixed_notional: float | None = Field(default=None, gt=0)
    risk_per_trade_pct: float | None = Field(default=None, gt=0, le=100)
    account_allocation_pct: float | None = Field(default=None, gt=0, le=100)
    max_trade_notional: float | None = Field(default=None, gt=0)
    min_trade_notional: float | None = Field(default=None, ge=0)

    max_position_notional: float | None = Field(default=None, gt=0)
    max_position_pct_of_equity: float | None = Field(default=None, gt=0, le=100)
    max_symbol_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_sector_exposure_pct: float | None = Field(default=None, gt=0, le=100)
    max_gross_exposure_pct: float | None = Field(default=None, gt=0)
    max_net_exposure_pct: float | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, gt=0)
    max_open_risk_pct: float | None = Field(default=None, gt=0, le=100)

    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    max_trades_per_day: int | None = Field(default=None, gt=0)
    cooldown_after_loss_minutes: int | None = Field(default=None, ge=0)

    fractional_quantity_allowed: bool = True
    whole_share_rounding: WholeShareRounding = WholeShareRounding.FLOOR

    min_quantity: float | None = Field(default=None, gt=0)
    max_quantity: float | None = Field(default=None, gt=0)

    stop_required: bool = True
    reject_if_no_stop: bool = True
    default_stop_policy: dict[str, Any] | None = None

    target_required: bool = False
    runner_allowed: bool = False

    allow_scale_in: bool = False
    allow_scale_out: bool = True
    allow_short: bool = False
    allow_extended_hours: bool = False

    symbol_restrictions: tuple[str, ...] = Field(default_factory=tuple)
    asset_class_restrictions: tuple[str, ...] = Field(default_factory=tuple)
    account_mode_restrictions: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_method_inputs(self) -> RiskPlanConfig:
        if self.sizing_method == RiskPlanSizingMethod.FIXED_SHARES and self.fixed_shares is None:
            raise ValueError("fixed_shares is required when sizing_method is fixed_shares")
        if self.sizing_method == RiskPlanSizingMethod.FIXED_NOTIONAL and self.fixed_notional is None:
            raise ValueError("fixed_notional is required when sizing_method is fixed_notional")
        if self.sizing_method == RiskPlanSizingMethod.RISK_PERCENT and self.risk_per_trade_pct is None:
            raise ValueError("risk_per_trade_pct is required when sizing_method is risk_percent")
        if self.sizing_method == RiskPlanSizingMethod.ACCOUNT_PERCENT and self.account_allocation_pct is None:
            raise ValueError("account_allocation_pct is required when sizing_method is account_percent")
        if (
            self.min_trade_notional is not None
            and self.max_trade_notional is not None
            and self.min_trade_notional > self.max_trade_notional
        ):
            raise ValueError("min_trade_notional cannot exceed max_trade_notional")
        if self.min_quantity is not None and self.max_quantity is not None and self.min_quantity > self.max_quantity:
            raise ValueError("min_quantity cannot exceed max_quantity")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def fingerprint(self) -> str:
        canonical = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def legacy_sizing_method(self) -> PositionSizingMethod:
        if self.sizing_method == RiskPlanSizingMethod.FIXED_SHARES:
            return PositionSizingMethod.FIXED_SHARES
        if self.sizing_method == RiskPlanSizingMethod.FIXED_NOTIONAL:
            return PositionSizingMethod.FIXED_DOLLAR
        return PositionSizingMethod.RISK_PERCENT_EQUITY


class RiskPlan(DomainSchema):
    risk_plan_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    description: str | None = None
    status: RiskPlanStatus = RiskPlanStatus.DRAFT
    risk_score: int = Field(ge=0, le=10)
    risk_tier: RiskPlanTier
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    created_by: str | None = None
    ai_generated: bool = False
    ai_summary: str | None = None
    source: RiskPlanSource = RiskPlanSource.MANUAL

    @model_validator(mode="after")
    def validate_source_flags(self) -> RiskPlan:
        if self.source == RiskPlanSource.AI_GENERATED and not self.ai_generated:
            raise ValueError("ai_generated must be true when source is ai_generated")
        return self


class RiskPlanVersion(DomainSchema):
    risk_plan_version_id: UUID = Field(default_factory=uuid4)
    risk_plan_id: UUID
    version: int = Field(ge=1)
    status: RiskPlanVersionStatus = RiskPlanVersionStatus.DRAFT
    config: RiskPlanConfig
    config_fingerprint: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    activated_at: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_config_fingerprint(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if data.get("config_fingerprint"):
            return data
        config = data.get("config")
        if config is None:
            return data
        risk_config = config if isinstance(config, RiskPlanConfig) else RiskPlanConfig.model_validate(config)
        return {**data, "config_fingerprint": risk_config.fingerprint()}

    @model_validator(mode="after")
    def validate_status_timestamps(self) -> RiskPlanVersion:
        if self.status == RiskPlanVersionStatus.ACTIVE and self.activated_at is None:
            raise ValueError("active RiskPlanVersion requires activated_at")
        if self.status == RiskPlanVersionStatus.DEPRECATED and self.archived_at is None:
            raise ValueError("deprecated RiskPlanVersion requires archived_at")
        return self

    @property
    def id(self) -> UUID:
        return self.risk_plan_version_id

    def to_risk_profile_version(self, *, name: str) -> RiskProfileVersion:
        return RiskProfileVersion(
            id=self.risk_plan_version_id,
            risk_profile_id=self.risk_plan_id,
            version=self.version,
            name=name,
            sizing_method=self.config.legacy_sizing_method(),
            risk_per_trade_pct=self.config.risk_per_trade_pct,
            fixed_notional=self.config.fixed_notional,
            fixed_shares=int(self.config.fixed_shares) if self.config.fixed_shares is not None else None,
            max_daily_loss_pct=self.config.max_daily_loss_pct,
            max_drawdown_pct=self.config.max_drawdown_pct,
            max_positions=self.config.max_open_positions,
            max_symbol_exposure_pct=self.config.max_symbol_exposure_pct,
        )
