from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.brokers import BrokerAccountSnapshot, BrokerSyncState
from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now


class BrokerAccountValidationStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class BrokerAccountCredentialValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MODE_MISMATCH = "mode_mismatch"
    MISSING_CREDENTIALS = "missing_credentials"
    PROVIDER_UNREACHABLE = "provider_unreachable"


class BrokerAccountDeletionStatus(StrEnum):
    HARD_DELETED = "hard_deleted"
    ARCHIVED = "archived"
    BLOCKED = "blocked"


class BrokerAccount(BaseModel):
    """Broker account record. Mode is required at creation and pinned for life.

    ``needs_credentials=True`` indicates the encrypted credential store
    has no entry for this account (typically a record from before
    persistent secret storage existed). The runtime gates trading on this
    flag; the operator re-enters credentials inline on the account card
    via ``PUT /{account_id}/credentials``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    display_name: str = Field(min_length=1)
    provider: str = "alpaca"
    mode: TradingMode
    external_account_id: str | None = None
    default_risk_plan_id: UUID | None = None
    default_risk_plan_version_id: UUID | None = None
    credentials_ref: str
    needs_credentials: bool = False
    validation_status: BrokerAccountValidationStatus
    last_account_snapshot: BrokerAccountSnapshot | None = None
    broker_sync_freshness: BrokerSyncState | None = None
    # M11 Guardian Assignment — Account-scoped pointer to one Deployment
    # that is pre-authorized to adopt orphaned positions or positions whose
    # owner Deployment is unhealthy AND unprotected. Account-level, NOT
    # Deployment-level: the same Deployment can be Guardian on Account B
    # while being a regular Deployment on Account A. Loose-coupled (no FK).
    guardian_deployment_id: UUID | None = None
    # M10 live-mode init guard — operator-set per-Account opt-in. Combined
    # with the env var TRADING_LIVE_ENABLED gate at AlpacaBrokerCapabilities
    # init time. Default False = paper-only safe.
    allow_live: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    is_archived: bool = False
    archived_at: datetime | None = None


class CreateBrokerAccountRequest(BaseModel):
    """Unified create-account request — provider + mode are operator-chosen.

    Replaces the paper-specific request. The backend derives the broker
    base URL and streaming endpoint from ``(provider, mode)``; the
    frontend never picks a URL.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1)
    provider: str = Field(min_length=1, default="alpaca")
    mode: TradingMode
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class BrokerAccountResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: BrokerAccount
    already_exists: bool = False


class BrokerAccountListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accounts: tuple[BrokerAccount, ...] = ()


class UpdateBrokerAccountDetailsRequest(BaseModel):
    """Operator metadata edits. Mode and provider stay pinned at creation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    display_name: str = Field(min_length=1)


class ReplaceBrokerAccountCredentialsRequest(BaseModel):
    """Unified replace-credentials request. Mode is derived from the
    existing account, never accepted from the client (the existing
    account's mode is the source of truth)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class BrokerAccountCredentialUpdateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: BrokerAccount | None = None
    validation_status: BrokerAccountCredentialValidationStatus
    message: str


class DeleteBrokerAccountRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    confirm_display_name: str = Field(min_length=1)
    confirm_mode: TradingMode


class SetAccountGuardianRequest(BaseModel):
    """Assign or clear an Account's Guardian Deployment (M11).

    Pass `guardian_deployment_id=null` to clear; pass a Deployment id to
    assign. Adoption is one-way per the operator decision (plan file
    `strategy-builder-must-only-abundant-allen.md` Q-Recovery): once a
    position is adopted by Guardian, it stays with Guardian until the
    operator explicitly transfers ownership back. There is no
    auto-revert when the original owner returns to healthy.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    guardian_deployment_id: UUID | None = None


class SetAccountAllowLiveRequest(BaseModel):
    """Toggle the per-Account live-trading allow flag (M10).

    Combined with the env ``TRADING_LIVE_ENABLED=true`` gate at
    ``AlpacaBrokerAdapter`` init time. Both must be true before a live
    broker adapter can construct.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allow_live: bool = False


class BrokerAccountDeletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    status: BrokerAccountDeletionStatus
    message: str
    blockers: tuple[str, ...] = ()
    archived_account: BrokerAccount | None = None


class AccountRiskConfig(BaseModel):
    """Account-scoped risk posture used by the operator Risk Card.

    This is persisted configuration evidence. It does not execute sizing by
    itself and does not replace the RiskResolver/Governor path.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    version: int = Field(default=1, ge=1)
    sizing_method: Literal["fixed_shares", "fixed_dollar", "risk_percent_equity"] = "risk_percent_equity"
    fixed_shares: float | None = Field(default=None, gt=0)
    fixed_notional: float | None = Field(default=None, gt=0)
    risk_per_trade_pct: float | None = Field(default=1.0, gt=0, le=100)
    max_position_notional: float | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, gt=0)  # None = no per-Account cap (Slice A: don't impose a silent default through the Governor)
    max_symbol_concentration_pct: float | None = Field(default=None, gt=0, le=100)
    max_gross_exposure_pct: float | None = Field(default=None, gt=0)
    max_net_exposure_pct: float | None = Field(default=None, gt=0)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    fractional_quantity_allowed: bool = True
    whole_share_rounding: Literal["floor", "round", "ceil"] = "floor"
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_sizing_input(self) -> "AccountRiskConfig":
        if self.sizing_method == "fixed_shares" and self.fixed_shares is None:
            raise ValueError("fixed_shares is required when sizing_method is fixed_shares")
        if self.sizing_method == "fixed_dollar" and self.fixed_notional is None:
            raise ValueError("fixed_notional is required when sizing_method is fixed_dollar")
        if self.sizing_method == "risk_percent_equity" and self.risk_per_trade_pct is None:
            raise ValueError("risk_per_trade_pct is required when sizing_method is risk_percent_equity")
        return self


class AccountRiskConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sizing_method: Literal["fixed_shares", "fixed_dollar", "risk_percent_equity"] = "risk_percent_equity"
    fixed_shares: float | None = Field(default=None, gt=0)
    fixed_notional: float | None = Field(default=None, gt=0)
    risk_per_trade_pct: float | None = Field(default=1.0, gt=0, le=100)
    max_position_notional: float | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, gt=0)  # None = no per-Account cap (Slice A: don't impose a silent default through the Governor)
    max_symbol_concentration_pct: float | None = Field(default=None, gt=0, le=100)
    max_gross_exposure_pct: float | None = Field(default=None, gt=0)
    max_net_exposure_pct: float | None = Field(default=None, gt=0)
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    fractional_quantity_allowed: bool = True
    whole_share_rounding: Literal["floor", "round", "ceil"] = "floor"

    @model_validator(mode="after")
    def validate_sizing_input(self) -> "AccountRiskConfigUpdateRequest":
        if self.sizing_method == "fixed_shares" and self.fixed_shares is None:
            raise ValueError("fixed_shares is required when sizing_method is fixed_shares")
        if self.sizing_method == "fixed_dollar" and self.fixed_notional is None:
            raise ValueError("fixed_notional is required when sizing_method is fixed_dollar")
        if self.sizing_method == "risk_percent_equity" and self.risk_per_trade_pct is None:
            raise ValueError("risk_per_trade_pct is required when sizing_method is risk_percent_equity")
        return self


class AccountRestrictions(BaseModel):
    """Account-scoped allow/block posture surfaced on the Risk Card."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    version: int = Field(default=1, ge=1)
    symbol_blocklist: tuple[str, ...] = ()
    asset_class_blocklist: tuple[str, ...] = ()
    long_only: bool = False
    short_only: bool = False
    extended_hours_allowed: bool = False
    time_of_day_windows: tuple[dict[str, object], ...] = ()
    notes: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_direction_flags(self) -> "AccountRestrictions":
        if self.long_only and self.short_only:
            raise ValueError("long_only and short_only cannot both be true")
        return self


class AccountRestrictionsUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol_blocklist: tuple[str, ...] = ()
    asset_class_blocklist: tuple[str, ...] = ()
    long_only: bool = False
    short_only: bool = False
    extended_hours_allowed: bool = False
    time_of_day_windows: tuple[dict[str, object], ...] = ()
    notes: str | None = None

    @model_validator(mode="after")
    def validate_direction_flags(self) -> "AccountRestrictionsUpdateRequest":
        if self.long_only and self.short_only:
            raise ValueError("long_only and short_only cannot both be true")
        return self
