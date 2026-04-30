from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, utc_now


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class BracketSpec(DomainSchema):
    enabled: bool = False
    take_profit_r_multiple: float | None = Field(default=None, gt=0)
    stop_loss_r_multiple: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_bracket_values_when_enabled(self) -> "BracketSpec":
        if self.enabled and (self.take_profit_r_multiple is None or self.stop_loss_r_multiple is None):
            raise ValueError("enabled bracket requires take_profit_r_multiple and stop_loss_r_multiple")
        return self


class ExecutionStylePresetKind(StrEnum):
    """Operator-grade execution-style presets for the Strategy Composer.

    Each preset maps to a strict SignalPlan shape via the deterministic
    builders in ``backend.app.strategy_composer.presets``. The preset is
    persisted on the StrategyVersion's execution_style; the runtime consults
    it to construct symbol-specific SignalPlans at deployment time.
    """

    MARKET_ENTRY_MARKET_EXIT = "market_entry_market_exit"
    STOP_ENTRY_MARKET_EXIT = "stop_entry_market_exit"
    BRACKET_STOP_TARGET = "bracket_stop_target"
    BRACKET_RUNNER = "bracket_runner"
    MULTI_TARGET_SCALE_OUT = "multi_target_scale_out"


class MarketEntryMarketExitPreset(DomainSchema):
    kind: Literal[ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT] = ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT


class StopEntryMarketExitPreset(DomainSchema):
    kind: Literal[ExecutionStylePresetKind.STOP_ENTRY_MARKET_EXIT] = ExecutionStylePresetKind.STOP_ENTRY_MARKET_EXIT
    entry_stop_offset_bps: float = Field(default=10.0, ge=0)


class BracketStopTargetPreset(DomainSchema):
    kind: Literal[ExecutionStylePresetKind.BRACKET_STOP_TARGET] = ExecutionStylePresetKind.BRACKET_STOP_TARGET
    stop_pct: float = Field(default=1.0, gt=0)
    target_pct: float = Field(default=2.0, gt=0)


class BracketRunnerPreset(DomainSchema):
    kind: Literal[ExecutionStylePresetKind.BRACKET_RUNNER] = ExecutionStylePresetKind.BRACKET_RUNNER
    first_target_pct: float = Field(default=1.0, gt=0)
    first_slice_pct: float = Field(default=0.5, gt=0, le=1)
    trail_pct: float = Field(default=1.0, gt=0)


class MultiTargetTier(DomainSchema):
    target_pct: float = Field(gt=0)
    slice_pct: float = Field(gt=0, le=1)


class MultiTargetScaleOutPreset(DomainSchema):
    kind: Literal[ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT] = ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT
    targets: tuple[MultiTargetTier, ...] = Field(min_length=1)
    stop_pct: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def slices_sum_within_one(self) -> "MultiTargetScaleOutPreset":
        total = sum(target.slice_pct for target in self.targets)
        if total > 1.0001:
            raise ValueError(f"multi-target scale-out target slice_pct must sum to <= 1.0; got {total}")
        return self


ExecutionStylePresetSpec = Annotated[
    MarketEntryMarketExitPreset
    | StopEntryMarketExitPreset
    | BracketStopTargetPreset
    | BracketRunnerPreset
    | MultiTargetScaleOutPreset,
    Field(discriminator="kind"),
]


class ExecutionMode(StrEnum):
    """Bracket execution mode owned by the ExecutionPlan.

    - ``post_fill_bracket`` (default): submit entry, wait for BrokerSync-confirmed
      fill, compute stop/target from the actual fill price, submit child OCO
      protective pair. Idempotent on re-emission of the same fill event.
    - ``native_alpaca_bracket`` (optional): submit a broker-native Alpaca
      bracket order (``OrderClass.BRACKET``) with both child legs attached at
      submit time. Pre-flight rejects fractional, notional, extended-hours, or
      same-symbol concurrent opposing-side cases (Alpaca constraints verified
      2026-04-29 against alpaca-py SDK + ``docs.alpaca.markets``).
    """

    POST_FILL_BRACKET = "post_fill_bracket"
    NATIVE_ALPACA_BRACKET = "native_alpaca_bracket"


class ExecutionStyleVersion(DomainSchema):
    """Persisted, immutable Execution Plan version.

    Doctrine name in ``MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md`` is
    "ExecutionPlan"; the table name is ``execution_plan_versions`` and the
    Deployment FK is ``execution_plan_version_id``. The Python class identity
    keeps the legacy name for now to avoid a 94-site rename in this slice.
    Renaming the class identifier is a follow-up slice with its own contract.

    The ExecutionPlan owns *how* a SignalPlan becomes broker-valid orders —
    entry order type, stop/target shape, post-fill placement policy, partial-fill
    handling, time-in-force, OCO/bracket selection. It does not create signals.

    A Deployment binds an ``execution_plan_version_id`` to a StrategyVersion
    and a StrategyControlsVersion to form the executable package. The same
    StrategyVersion can run with different ExecutionPlans across Accounts.
    """

    id: UUID
    execution_style_id: UUID
    version: int = Field(ge=1)
    name: str
    entry_order_type: OrderType
    exit_order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    entry_limit_offset_bps: float | None = None
    cancel_after_bars: int | None = Field(default=None, gt=0)
    bracket: BracketSpec = Field(default_factory=BracketSpec)
    execution_mode: ExecutionMode = ExecutionMode.POST_FILL_BRACKET
    trailing_stop_enabled: bool = False
    scale_out_enabled: bool = False
    feature_refs: list[str] = Field(default_factory=list)
    preset: ExecutionStylePresetSpec | None = None
    created_at: datetime = Field(default_factory=utc_now)
