from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .data_intent import DataConsumer, DataIntent, DataTolerance, Timeframe


class Provider(StrEnum):
    ALPACA = "alpaca"
    YAHOO = "yahoo"
    FUTURE = "future"


class ServiceType(StrEnum):
    MARKET_DATA = "market_data"


class ServiceMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"
    NONE = "none"


class ServiceStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
    DISABLED = "disabled"


class CostClass(StrEnum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    UNKNOWN = "unknown"


class LatencyClass(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    DELAYED = "delayed"
    UNKNOWN = "unknown"


class SelectionMode(StrEnum):
    AUTO = "auto"
    DEFAULT = "default"
    EXPLICIT = "explicit"


class ResolverDecision(StrEnum):
    SELECTED = "selected"
    REJECTED = "rejected"


class ResolverReasonCode(StrEnum):
    SELECTED_DEFAULT = "selected_default"
    SELECTED_AUTO_BEST_FIT = "selected_auto_best_fit"
    SELECTED_EXPLICIT = "selected_explicit"
    REJECTED_INVALID_SERVICE = "rejected_invalid_service"
    REJECTED_DISABLED_SERVICE = "rejected_disabled_service"
    REJECTED_NO_STREAMING = "rejected_no_streaming"
    REJECTED_NO_INTRADAY = "rejected_no_intraday"
    REJECTED_NO_HISTORICAL = "rejected_no_historical"
    REJECTED_NO_REALTIME = "rejected_no_realtime"
    REJECTED_PROVIDER_UNREACHABLE = "rejected_provider_unreachable"
    REJECTED_NO_COMPATIBLE_SERVICE = "rejected_no_compatible_service"


class MarketDataCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supports_historical: bool = False
    supports_streaming: bool = False
    supports_intraday: bool = False
    supports_daily: bool = False
    supports_weekly: bool = False
    supports_monthly: bool = False
    supports_realtime: bool = False
    supports_long_range_history: bool = False
    requires_credentials: bool = False
    cost_class: CostClass = CostClass.UNKNOWN
    latency_class: LatencyClass = LatencyClass.UNKNOWN


class MarketDataServiceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_id: str
    service_name: str
    provider: Provider
    service_type: ServiceType = ServiceType.MARKET_DATA
    mode: ServiceMode = ServiceMode.NONE
    status: ServiceStatus = ServiceStatus.DRAFT
    is_default: bool = False
    capabilities: MarketDataCapabilities
    provider_reachable: bool = True
    credentials_ref: str | None = None
    validation_status: str | None = None
    validation_message: str | None = None


class RejectedCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_id: str
    service_name: str | None = None
    reason_code: ResolverReasonCode
    explanation: str


class ResolverResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_service_id: str | None = None
    selected_service_name: str | None = None
    provider: Provider | None = None
    selection_mode: SelectionMode
    decision: ResolverDecision
    reason_code: ResolverReasonCode
    explanation: str
    rejected_candidates: tuple[RejectedCandidate, ...] = ()


def alpaca_market_data_service(
    *,
    service_id: str = "alpaca-main-data",
    service_name: str = "Alpaca Main Data",
    status: ServiceStatus = ServiceStatus.VALID,
    is_default: bool = False,
    mode: ServiceMode = ServiceMode.PAPER,
) -> MarketDataServiceConfig:
    return MarketDataServiceConfig(
        service_id=service_id,
        service_name=service_name,
        provider=Provider.ALPACA,
        mode=mode,
        status=status,
        is_default=is_default,
        capabilities=MarketDataCapabilities(
            supports_historical=True,
            supports_streaming=True,
            supports_intraday=True,
            supports_daily=True,
            supports_weekly=False,
            supports_monthly=False,
            supports_realtime=True,
            supports_long_range_history=True,
            requires_credentials=True,
            cost_class=CostClass.STANDARD,
            latency_class=LatencyClass.LOW,
        ),
    )


def yahoo_market_data_service(
    *,
    service_id: str = "yahoo-historical",
    service_name: str = "Yahoo Historical",
    status: ServiceStatus = ServiceStatus.VALID,
    is_default: bool = False,
) -> MarketDataServiceConfig:
    return MarketDataServiceConfig(
        service_id=service_id,
        service_name=service_name,
        provider=Provider.YAHOO,
        mode=ServiceMode.NONE,
        status=status,
        is_default=is_default,
        capabilities=MarketDataCapabilities(
            supports_historical=True,
            supports_streaming=False,
            supports_intraday=False,
            supports_daily=True,
            supports_weekly=True,
            supports_monthly=True,
            supports_realtime=False,
            supports_long_range_history=True,
            requires_credentials=False,
            cost_class=CostClass.FREE,
            latency_class=LatencyClass.DELAYED,
        ),
    )


def resolve_market_data_service(
    intent: DataIntent,
    available_services: list[MarketDataServiceConfig] | tuple[MarketDataServiceConfig, ...],
    selection_mode: SelectionMode | str,
    *,
    selected_service_id: str | None = None,
) -> ResolverResult:
    mode = SelectionMode(selection_mode)
    services = tuple(available_services)
    if mode == SelectionMode.EXPLICIT:
        selected = next((service for service in services if service.service_id == selected_service_id), None)
        if selected is None:
            return _rejected_result(mode, "Selected market data service was not found.", ())
        return _select_single(intent, mode, selected, ResolverReasonCode.SELECTED_EXPLICIT)
    if mode == SelectionMode.DEFAULT:
        default = next((service for service in services if service.is_default), None)
        if default is None:
            return _rejected_result(mode, "No default market data service is configured.", ())
        return _select_single(intent, mode, default, ResolverReasonCode.SELECTED_DEFAULT)
    return _auto_select(intent, services)


def _select_single(
    intent: DataIntent,
    selection_mode: SelectionMode,
    service: MarketDataServiceConfig,
    selected_reason: ResolverReasonCode,
) -> ResolverResult:
    rejection = _rejection_for(intent, service)
    if rejection is not None:
        return ResolverResult(
            selection_mode=selection_mode,
            decision=ResolverDecision.REJECTED,
            reason_code=rejection.reason_code,
            explanation=rejection.explanation,
            rejected_candidates=(rejection,),
        )
    return ResolverResult(
        selected_service_id=service.service_id,
        selected_service_name=service.service_name,
        provider=service.provider,
        selection_mode=selection_mode,
        decision=ResolverDecision.SELECTED,
        reason_code=selected_reason,
        explanation=_selected_explanation(intent, service, selected_reason),
    )


def _auto_select(intent: DataIntent, services: tuple[MarketDataServiceConfig, ...]) -> ResolverResult:
    rejected: list[RejectedCandidate] = []
    compatible: list[MarketDataServiceConfig] = []
    for service in services:
        rejection = _rejection_for(intent, service)
        if rejection is None:
            compatible.append(service)
        else:
            rejected.append(rejection)
    if not compatible:
        return _rejected_result(
            SelectionMode.AUTO,
            "no_compatible_service: no configured market data service satisfies this data intent.",
            tuple(rejected),
        )
    default = next((service for service in compatible if service.is_default), None)
    selected = default or min(compatible, key=lambda service: _auto_score(intent, service))
    selected_reason = ResolverReasonCode.SELECTED_DEFAULT if default is not None else ResolverReasonCode.SELECTED_AUTO_BEST_FIT
    for service in compatible:
        if service.service_id != selected.service_id:
            rejected.append(
                RejectedCandidate(
                    service_id=service.service_id,
                    service_name=service.service_name,
                    reason_code=selected_reason,
                    explanation=f"{service.service_name} is compatible, but {selected.service_name} was selected for this intent.",
                )
            )
    return ResolverResult(
        selected_service_id=selected.service_id,
        selected_service_name=selected.service_name,
        provider=selected.provider,
        selection_mode=SelectionMode.AUTO,
        decision=ResolverDecision.SELECTED,
        reason_code=selected_reason,
        explanation=_selected_explanation(intent, selected, selected_reason),
        rejected_candidates=tuple(rejected),
    )


def _rejection_for(intent: DataIntent, service: MarketDataServiceConfig) -> RejectedCandidate | None:
    caps = service.capabilities
    if service.status == ServiceStatus.DISABLED:
        return _reject(service, ResolverReasonCode.REJECTED_DISABLED_SERVICE, f"{service.service_name} is disabled.")
    if service.status != ServiceStatus.VALID:
        return _reject(service, ResolverReasonCode.REJECTED_INVALID_SERVICE, f"{service.service_name} is not valid.")
    if not service.provider_reachable:
        return _reject(service, ResolverReasonCode.REJECTED_PROVIDER_UNREACHABLE, f"{service.service_name} provider is unreachable.")
    if intent.requires_streaming and not caps.supports_streaming:
        return _reject(service, ResolverReasonCode.REJECTED_NO_STREAMING, f"{service.service_name} does not support streaming market data.")
    if intent.requires_realtime and not caps.supports_realtime:
        return _reject(service, ResolverReasonCode.REJECTED_NO_REALTIME, f"{service.service_name} does not support realtime market data.")
    if intent.requires_intraday and not caps.supports_intraday:
        return _reject(service, ResolverReasonCode.REJECTED_NO_INTRADAY, f"{service.service_name} does not support intraday bars.")
    if intent.requires_historical and not caps.supports_historical:
        return _reject(service, ResolverReasonCode.REJECTED_NO_HISTORICAL, f"{service.service_name} does not support historical bars.")
    if intent.timeframe == Timeframe.D1 and not caps.supports_daily:
        return _reject(service, ResolverReasonCode.REJECTED_NO_HISTORICAL, f"{service.service_name} does not support daily bars.")
    if intent.timeframe == Timeframe.W1 and not caps.supports_weekly:
        return _reject(service, ResolverReasonCode.REJECTED_NO_HISTORICAL, f"{service.service_name} does not support weekly bars.")
    if intent.timeframe == Timeframe.MO1 and not caps.supports_monthly:
        return _reject(service, ResolverReasonCode.REJECTED_NO_HISTORICAL, f"{service.service_name} does not support monthly bars.")
    if intent.is_long_range_historical and not caps.supports_long_range_history:
        return _reject(service, ResolverReasonCode.REJECTED_NO_HISTORICAL, f"{service.service_name} does not support long-range historical coverage.")
    return None


def _auto_score(intent: DataIntent, service: MarketDataServiceConfig) -> tuple[int, str]:
    score = 100
    caps = service.capabilities
    if service.is_default:
        score -= 5
    if intent.consumer == DataConsumer.BROKER_RUNTIME or intent.purpose.value == "runtime_trading":
        if caps.supports_streaming:
            score -= 30
        if caps.latency_class == LatencyClass.LOW:
            score -= 20
    elif intent.is_long_range_historical and not intent.requires_streaming:
        score += _cost_rank(caps.cost_class)
        if caps.supports_long_range_history:
            score -= 25
        if caps.latency_class in {LatencyClass.DELAYED, LatencyClass.NORMAL}:
            score -= 4
    else:
        score += _cost_rank(caps.cost_class)
        if caps.latency_class == LatencyClass.LOW and intent.tolerance == DataTolerance.LOW_LATENCY:
            score -= 10
    return score, service.service_name


def _cost_rank(cost_class: CostClass) -> int:
    return {
        CostClass.FREE: 0,
        CostClass.STANDARD: 12,
        CostClass.UNKNOWN: 18,
        CostClass.PREMIUM: 30,
    }[cost_class]


def _selected_explanation(intent: DataIntent, service: MarketDataServiceConfig, reason_code: ResolverReasonCode) -> str:
    if reason_code == ResolverReasonCode.SELECTED_DEFAULT:
        return f"Selected {service.service_name} because it is the default Market Data Service and satisfies the detected intent."
    if reason_code == ResolverReasonCode.SELECTED_EXPLICIT:
        return f"Selected {service.service_name} because it was manually chosen and satisfies the detected intent."
    if intent.consumer == DataConsumer.BROKER_RUNTIME:
        return f"Selected {service.service_name} because Broker Runtime requires realtime intraday streaming."
    if intent.is_long_range_historical and not intent.requires_streaming:
        return f"Selected {service.service_name} because the request uses long-range historical data and does not require streaming."
    return f"Selected {service.service_name} because its capabilities satisfy the detected data intent."


def _reject(service: MarketDataServiceConfig, reason_code: ResolverReasonCode, explanation: str) -> RejectedCandidate:
    return RejectedCandidate(service_id=service.service_id, service_name=service.service_name, reason_code=reason_code, explanation=explanation)


def _rejected_result(
    selection_mode: SelectionMode,
    explanation: str,
    rejected_candidates: tuple[RejectedCandidate, ...],
) -> ResolverResult:
    return ResolverResult(
        selection_mode=selection_mode,
        decision=ResolverDecision.REJECTED,
        reason_code=ResolverReasonCode.REJECTED_NO_COMPATIBLE_SERVICE,
        explanation=explanation,
        rejected_candidates=rejected_candidates,
    )
