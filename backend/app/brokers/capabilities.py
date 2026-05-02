from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.domain._base import DomainSchema, JsonDict


class BrokerAssetClass(StrEnum):
    EQUITY = "equity"
    FRACTIONAL_EQUITY = "fractional_equity"
    OTC = "otc"
    OPTION = "option"
    CRYPTO = "crypto"


class BrokerOrderClass(StrEnum):
    SIMPLE = "simple"
    BRACKET = "bracket"
    OCO = "oco"
    OTO = "oto"
    TRAILING_STOP = "trailing_stop"


class BrokerOperation(StrEnum):
    SUBMIT = "submit"
    CANCEL = "cancel"
    REPLACE = "replace"


class BrokerViolationCode(StrEnum):
    UNSUPPORTED_ORDER_TYPE = "unsupported_order_type"
    UNSUPPORTED_TIME_IN_FORCE = "unsupported_time_in_force"
    UNSUPPORTED_ORDER_CLASS = "unsupported_order_class"
    BROKER_NATIVE_MULTI_LEG_UNSUPPORTED = "broker_native_multi_leg_unsupported"
    EXTENDED_HOURS_UNSUPPORTED = "extended_hours_unsupported"
    EXTENDED_HOURS_TIF_UNSUPPORTED = "extended_hours_tif_unsupported"
    EXTENDED_HOURS_ORDER_TYPE_UNSUPPORTED = "extended_hours_order_type_unsupported"
    FRACTIONAL_UNSUPPORTED = "fractional_unsupported"
    FRACTIONAL_SHORT_UNSUPPORTED = "fractional_short_unsupported"
    NOTIONAL_AND_QUANTITY_BOTH_SET = "notional_and_quantity_both_set"
    NOTIONAL_OR_QUANTITY_REQUIRED = "notional_or_quantity_required"
    QTY_NOTIONAL_CONFLICT = "qty_notional_conflict"
    QTY_NOTIONAL_NEITHER = "qty_notional_neither"
    SHORTING_UNSUPPORTED = "shorting_unsupported"
    REPLACE_UNSUPPORTED = "replace_unsupported"
    OTO_REPLACE_UNSUPPORTED = "oto_replace_unsupported"
    NOTIONAL_REPLACE_UNSUPPORTED = "notional_replace_unsupported"
    CANCEL_UNSUPPORTED = "cancel_unsupported"
    STOP_DISTANCE_BELOW_THRESHOLD = "stop_distance_below_threshold"
    TRAILING_STOP_PRICE_AND_PERCENT_BOTH_SET = "trailing_stop_price_and_percent_both_set"
    TRAILING_STOP_PRICE_OR_PERCENT_REQUIRED = "trailing_stop_price_or_percent_required"
    TRAILING_STOP_AS_BRACKET_STOP_LOSS = "trailing_stop_as_bracket_stop_loss"


class BrokerErrorFamily(StrEnum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUYING_POWER = "buying_power"
    MARKET_RULE = "market_rule"
    RATE_LIMIT = "rate_limit"
    TRANSPORT = "transport"
    BROKER_REJECT = "broker_reject"
    STALE_SYNC = "stale_sync"
    UNKNOWN = "unknown"


class BrokerErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class BrokerCapabilityMatrix(DomainSchema):
    provider: str
    asset_class: BrokerAssetClass
    order_type: OrderType
    time_in_force: TimeInForce
    order_class: BrokerOrderClass = BrokerOrderClass.SIMPLE
    operation: BrokerOperation = BrokerOperation.SUBMIT
    extended_hours: bool = False
    fractional_allowed: bool = False
    short_allowed: bool = False
    replace_supported: bool = True
    cancel_supported: bool = True
    supported: bool
    reason_if_unsupported: str | None = None

    @model_validator(mode="after")
    def require_reason_when_unsupported(self) -> "BrokerCapabilityMatrix":
        if not self.supported and not self.reason_if_unsupported:
            raise ValueError("unsupported capability requires reason_if_unsupported")
        return self


class BrokerCapabilityViolation(DomainSchema):
    code: BrokerViolationCode
    message: str
    field: str | None = None
    operator_advisory: str | None = None


class BrokerOperatorAdvisory(DomainSchema):
    family: BrokerErrorFamily
    severity: BrokerErrorSeverity
    retryable: bool
    source: str
    message: str
    operator_action: str
    raw_code: str | None = None
    raw_message: str | None = None


class BrokerOrderPreflightRequest(DomainSchema):
    account_id: UUID
    provider: str
    broker_mode: TradingMode
    asset_class: BrokerAssetClass
    symbol: str
    side: CandidateSide
    is_position_management: bool = False
    operation: BrokerOperation = BrokerOperation.SUBMIT
    quantity: float | None = Field(default=None, gt=0)
    notional: float | None = Field(default=None, gt=0)
    order_type: OrderType
    time_in_force: TimeInForce
    order_class: BrokerOrderClass = BrokerOrderClass.SIMPLE
    native_multileg_requested: bool = False
    target_leg_count: int = Field(default=0, ge=0)
    stop_leg_count: int = Field(default=0, ge=0)
    runner_leg_count: int = Field(default=0, ge=0)
    extended_hours: bool = False
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_size_shape(self) -> "BrokerOrderPreflightRequest":
        if self.quantity is not None and self.notional is not None:
            raise ValueError("broker preflight may use quantity or notional, not both")
        if self.quantity is None and self.notional is None:
            raise ValueError("broker preflight requires quantity or notional")
        return self


class BrokerOrderPreflightResult(DomainSchema):
    allowed: bool
    violations: tuple[BrokerCapabilityViolation, ...] = ()
    warnings: tuple[str, ...] = ()
    normalized_request: JsonDict = Field(default_factory=dict)
    operator_advisory: BrokerOperatorAdvisory | None = None

    @model_validator(mode="after")
    def violations_match_allowed(self) -> "BrokerOrderPreflightResult":
        if self.allowed and self.violations:
            raise ValueError("allowed preflight result cannot contain violations")
        if not self.allowed and not self.violations:
            raise ValueError("rejected preflight result requires at least one violation")
        return self


class MarketSessionState(StrEnum):
    REGULAR = "regular"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"
    OVERNIGHT = "overnight"
    CLOSED = "closed"
    CRYPTO_24_7 = "crypto_24_7"


class MarketRuleViolationCode(StrEnum):
    MARKET_CLOSED = "market_closed"
    EXTENDED_HOURS_UNSUPPORTED = "extended_hours_unsupported"
    ASSET_NOT_TRADABLE = "asset_not_tradable"
    ASSET_NOT_FRACTIONABLE = "asset_not_fractionable"
    ASSET_HALTED = "asset_halted"
    SHORT_NOT_ALLOWED = "short_not_allowed"
    NOT_EASY_TO_BORROW = "not_easy_to_borrow"
    BUYING_POWER_INSUFFICIENT = "buying_power_insufficient"
    SHORT_BUYING_POWER_INSUFFICIENT = "short_buying_power_insufficient"
    INVALID_NOTIONAL_QUANTITY_COMBO = "invalid_notional_quantity_combo"
    UNSUPPORTED_ASSET_CLASS_FOR_MODE = "unsupported_asset_class_for_mode"


class MarketRuleViolation(DomainSchema):
    code: MarketRuleViolationCode
    message: str
    field: str | None = None
    operator_advisory: str | None = None


class MarketRulePreflightRequest(DomainSchema):
    account_id: UUID
    provider: str
    broker_mode: TradingMode
    symbol: str
    asset_class: BrokerAssetClass
    side: CandidateSide
    is_position_management: bool = False
    quantity: float | None = Field(default=None, gt=0)
    notional: float | None = Field(default=None, gt=0)
    order_type: OrderType
    time_in_force: TimeInForce
    order_class: BrokerOrderClass = BrokerOrderClass.SIMPLE
    extended_hours: bool = False
    market_session: MarketSessionState
    asset_tradable: bool
    asset_fractionable: bool
    shortable: bool
    easy_to_borrow: bool
    halted: bool
    buying_power: float = Field(ge=0)
    # ask_price is required for short-side buying-power estimation per Playbook §11.
    # When provided and side=SHORT, the service estimates required capital as
    # max(limit_price, 1.03 * ask_price) * quantity and checks against buying_power.
    ask_price: float | None = Field(default=None, gt=0)
    limit_price: float | None = Field(default=None, gt=0)


class MarketRulePreflightResult(DomainSchema):
    allowed: bool
    session_state: MarketSessionState
    violations: tuple[MarketRuleViolation, ...] = ()
    warnings: tuple[str, ...] = ()
    operator_advisory: BrokerOperatorAdvisory | None = None

    @model_validator(mode="after")
    def violations_match_allowed(self) -> "MarketRulePreflightResult":
        if self.allowed and self.violations:
            raise ValueError("allowed market rule result cannot contain violations")
        if not self.allowed and not self.violations:
            raise ValueError("rejected market rule result requires at least one violation")
        return self
