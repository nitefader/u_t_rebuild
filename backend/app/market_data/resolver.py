"""Market data resolver — picks a market-data provider for a given DataIntent.

Per ``final_roadmap_and_arch_decisions_and_guidelines.md`` §9 and
``plan_review.md`` §I/§J, this resolver:

- Returns per-symbol resolution rows. There is no top-level "selected service"
  mirror; callers iterate ``per_symbol_rows``. The aggregate ``decision`` is
  ``selected`` only when every row succeeded, ``rejected`` only when every row
  failed, and ``partial`` otherwise.
- Returns ``selection_strategy`` (``auto`` / ``default_preferred`` /
  ``manual_override``) — banned ``mode`` wording is forbidden here.
- Returns frozen-enum reason codes — free text in audit logs is forbidden
  (§12 stop condition 7).
- Computes a deterministic ``resolver_input_hash`` for replay / audit equality.
- Carries ``pipeline_id`` per row (always ``None`` in slice 1A; populated in
  1B once ``MarketDataPipeline`` lands as first-class domain).

Trading mode (``TradingMode``) is intentionally absent from this layer —
mode is owned exclusively by ``BrokerAccount``.

Determinism contract
--------------------
Two resolver invocations are equivalent iff their ``resolver_input_hash``
values match. The hash is computed over a *stable projection* of inputs:
``{service_id, provider, status, is_default, validation_status, capabilities,
provider_reachable, service_type}`` — operator-readable prose
(``service_name``, ``validation_message``, ``credentials_ref``) is excluded
so cosmetic re-wording does not invalidate replay equality.

``decided_at`` is a wall-clock receipt and **must not** be used for equality,
replay matching, or test snapshot diffs. Audit consumers comparing full
payloads must project ``decided_at`` out before compare.

DISABLED precedence
-------------------
``service.status == DISABLED`` always maps to ``OPERATOR_VETO`` regardless of
``validation_status``. The status check runs *before* capability checks and
*before* validation-status routing.

Validation-status → rejection-code mapping
------------------------------------------
================================  =========================  ====================================
``MarketDataValidationStatus``    ``service.status``         ``ResolverRejectionCode``
================================  =========================  ====================================
``valid``                         ``valid``                  (capability checks proceed)
``invalid``                       ``invalid``                ``PROVIDER_NOT_VALIDATED``
``missing_credentials``           ``invalid``                ``CREDENTIAL_MISSING``
``provider_unreachable``          ``invalid``                ``PROVIDER_UNREACHABLE``
``unsupported_provider``          ``invalid``                ``CAPABILITY_TIER_INSUFFICIENT``
``disabled``                      ``disabled``               ``OPERATOR_VETO``
*None* (DRAFT, never validated)   ``draft``                  ``PROVIDER_NOT_VALIDATED``
================================  =========================  ====================================
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Callable

from pydantic import BaseModel, ConfigDict

from .data_intent import DataConsumer, DataIntent, DataTolerance, Timeframe


RESOLVER_VERSION = "0.11.0"

PipelineLookup = Callable[["Provider"], str | None]


class Provider(StrEnum):
    ALPACA = "alpaca"
    YAHOO = "yahoo"
    FUTURE = "future"


class ServiceType(StrEnum):
    MARKET_DATA = "market_data"


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


class SelectionStrategy(StrEnum):
    AUTO = "auto"
    DEFAULT_PREFERRED = "default_preferred"
    MANUAL_OVERRIDE = "manual_override"


class ResolverDecision(StrEnum):
    SELECTED = "selected"
    REJECTED = "rejected"
    PARTIAL = "partial"


class ResolverSelectionCode(StrEnum):
    SELECTED_AUTO_BEST_FIT = "SELECTED_AUTO_BEST_FIT"
    SELECTED_DEFAULT_PREFERRED = "SELECTED_DEFAULT_PREFERRED"
    SELECTED_MANUAL_OVERRIDE = "SELECTED_MANUAL_OVERRIDE"


class ResolverRejectionCode(StrEnum):
    """Frozen rejection-code enum. Free text in audit logs is banned (§12 stop 7)."""

    UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    STREAM_NOT_AVAILABLE = "STREAM_NOT_AVAILABLE"
    HISTORICAL_NOT_AVAILABLE = "HISTORICAL_NOT_AVAILABLE"
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"
    CAPABILITY_TIER_INSUFFICIENT = "CAPABILITY_TIER_INSUFFICIENT"
    MODE_MISMATCH = "MODE_MISMATCH"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    OPERATOR_VETO = "OPERATOR_VETO"
    PROVIDER_UNREACHABLE = "PROVIDER_UNREACHABLE"
    PROVIDER_NOT_VALIDATED = "PROVIDER_NOT_VALIDATED"
    NO_COMPATIBLE_PROVIDER = "NO_COMPATIBLE_PROVIDER"


class InvocationContext(StrEnum):
    CHART_LAB = "chart_lab"
    SIM_LAB = "sim_lab"
    BROKER_RUNTIME = "broker_runtime"
    BACKTEST = "backtest"
    OPERATIONS_PREVIEW = "operations_preview"


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
    provider: Provider | None = None
    reason_code: ResolverRejectionCode
    explanation: str


class PerSymbolResolution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    decision: ResolverDecision
    selected_service_id: str | None = None
    selected_service_name: str | None = None
    selected_provider: Provider | None = None
    pipeline_id: str | None = None
    reason: str
    explanation: str
    rejected_providers: tuple[RejectedCandidate, ...] = ()


class ResolverResult(BaseModel):
    """Resolver result.

    There is no top-level "selected service" mirror — callers must iterate
    ``per_symbol_rows``. ``decided_at`` is non-deterministic by design; use
    ``resolver_input_hash`` for equality / replay matching.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection_strategy: SelectionStrategy
    decision: ResolverDecision
    per_symbol_rows: tuple[PerSymbolResolution, ...]
    resolver_version: str = RESOLVER_VERSION
    resolver_input_hash: str
    invocation_context: InvocationContext
    decided_at: datetime


_VALIDATION_STATUS_TO_REJECTION: dict[str, ResolverRejectionCode] = {
    "valid": None,  # type: ignore[dict-item]  # sentinel; means "no rejection"
    "invalid": ResolverRejectionCode.PROVIDER_NOT_VALIDATED,
    "missing_credentials": ResolverRejectionCode.CREDENTIAL_MISSING,
    "provider_unreachable": ResolverRejectionCode.PROVIDER_UNREACHABLE,
    "unsupported_provider": ResolverRejectionCode.CAPABILITY_TIER_INSUFFICIENT,
    "disabled": ResolverRejectionCode.OPERATOR_VETO,
}


def alpaca_market_data_service(
    *,
    service_id: str = "alpaca-main-data",
    service_name: str = "Alpaca Main Data",
    status: ServiceStatus = ServiceStatus.VALID,
    is_default: bool = False,
) -> MarketDataServiceConfig:
    return MarketDataServiceConfig(
        service_id=service_id,
        service_name=service_name,
        provider=Provider.ALPACA,
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
    selection_strategy: SelectionStrategy | str,
    *,
    selected_service_id: str | None = None,
    invocation_context: InvocationContext | str = InvocationContext.OPERATIONS_PREVIEW,
    decided_at: datetime | None = None,
    pipeline_lookup: PipelineLookup | None = None,
) -> ResolverResult:
    strategy = SelectionStrategy(selection_strategy)
    context = InvocationContext(invocation_context)
    services = tuple(available_services)

    input_hash = _compute_resolver_input_hash(
        intent=intent,
        services=services,
        selection_strategy=strategy,
        selected_service_id=selected_service_id,
        invocation_context=context,
    )

    symbols = tuple(intent.symbols) if intent.symbols else ("*",)
    rows = tuple(
        _resolve_for_symbol(
            symbol=symbol,
            intent=intent,
            services=services,
            strategy=strategy,
            selected_service_id=selected_service_id,
            pipeline_lookup=pipeline_lookup,
        )
        for symbol in symbols
    )

    aggregate = _aggregate_decision(rows)
    timestamp = decided_at or datetime.now(timezone.utc)

    return ResolverResult(
        selection_strategy=strategy,
        decision=aggregate,
        per_symbol_rows=rows,
        resolver_version=RESOLVER_VERSION,
        resolver_input_hash=input_hash,
        invocation_context=context,
        decided_at=timestamp,
    )


def _resolve_for_symbol(
    *,
    symbol: str,
    intent: DataIntent,
    services: tuple[MarketDataServiceConfig, ...],
    strategy: SelectionStrategy,
    selected_service_id: str | None,
    pipeline_lookup: PipelineLookup | None,
) -> PerSymbolResolution:
    if strategy == SelectionStrategy.MANUAL_OVERRIDE:
        chosen = next((s for s in services if s.service_id == selected_service_id), None)
        if chosen is None:
            synthetic = RejectedCandidate(
                service_id=selected_service_id or "",
                service_name=None,
                provider=None,
                reason_code=ResolverRejectionCode.NO_COMPATIBLE_PROVIDER,
                explanation="Manual override targets unknown service id.",
            )
            return PerSymbolResolution(
                symbol=symbol,
                decision=ResolverDecision.REJECTED,
                reason=ResolverRejectionCode.NO_COMPATIBLE_PROVIDER.value,
                explanation="Manually selected service was not found in catalog.",
                rejected_providers=(synthetic,),
            )
        return _select_or_reject_row(symbol, intent, chosen, ResolverSelectionCode.SELECTED_MANUAL_OVERRIDE, pipeline_lookup)

    if strategy == SelectionStrategy.DEFAULT_PREFERRED:
        default = next((s for s in services if s.is_default), None)
        if default is None:
            return PerSymbolResolution(
                symbol=symbol,
                decision=ResolverDecision.REJECTED,
                reason=ResolverRejectionCode.NO_COMPATIBLE_PROVIDER.value,
                explanation="No default market data service is configured.",
            )
        return _select_or_reject_row(symbol, intent, default, ResolverSelectionCode.SELECTED_DEFAULT_PREFERRED, pipeline_lookup)

    return _auto_select_row(symbol, intent, services, pipeline_lookup)


def _resolve_pipeline_id(provider: Provider, lookup: PipelineLookup | None) -> str | None:
    if lookup is None:
        return None
    return lookup(provider)


def _select_or_reject_row(
    symbol: str,
    intent: DataIntent,
    service: MarketDataServiceConfig,
    selection_code: ResolverSelectionCode,
    pipeline_lookup: PipelineLookup | None,
) -> PerSymbolResolution:
    rejection = _rejection_for(intent, service)
    if rejection is not None:
        return PerSymbolResolution(
            symbol=symbol,
            decision=ResolverDecision.REJECTED,
            reason=rejection.reason_code.value,
            explanation=rejection.explanation,
            rejected_providers=(rejection,),
        )
    return PerSymbolResolution(
        symbol=symbol,
        decision=ResolverDecision.SELECTED,
        selected_service_id=service.service_id,
        selected_service_name=service.service_name,
        selected_provider=service.provider,
        pipeline_id=_resolve_pipeline_id(service.provider, pipeline_lookup),
        reason=selection_code.value,
        explanation=_selected_explanation(intent, service, selection_code),
    )


def _auto_select_row(
    symbol: str,
    intent: DataIntent,
    services: tuple[MarketDataServiceConfig, ...],
    pipeline_lookup: PipelineLookup | None,
) -> PerSymbolResolution:
    rejected: list[RejectedCandidate] = []
    compatible: list[MarketDataServiceConfig] = []
    for service in services:
        rejection = _rejection_for(intent, service)
        if rejection is None:
            compatible.append(service)
        else:
            rejected.append(rejection)

    if not compatible:
        return PerSymbolResolution(
            symbol=symbol,
            decision=ResolverDecision.REJECTED,
            reason=ResolverRejectionCode.NO_COMPATIBLE_PROVIDER.value,
            explanation="no_compatible_service: no configured market data service satisfies this data intent.",
            rejected_providers=tuple(rejected),
        )

    default = next((s for s in compatible if s.is_default), None)
    selected = default or min(compatible, key=lambda s: _auto_score(intent, s))
    selection_code = (
        ResolverSelectionCode.SELECTED_DEFAULT_PREFERRED
        if default is not None
        else ResolverSelectionCode.SELECTED_AUTO_BEST_FIT
    )
    return PerSymbolResolution(
        symbol=symbol,
        decision=ResolverDecision.SELECTED,
        selected_service_id=selected.service_id,
        selected_service_name=selected.service_name,
        selected_provider=selected.provider,
        pipeline_id=_resolve_pipeline_id(selected.provider, pipeline_lookup),
        reason=selection_code.value,
        explanation=_selected_explanation(intent, selected, selection_code),
        rejected_providers=tuple(rejected),
    )


def _rejection_for(intent: DataIntent, service: MarketDataServiceConfig) -> RejectedCandidate | None:
    """Decide whether a service can satisfy this intent.

    Order of operations is load-bearing:

    1. ``DISABLED`` always wins regardless of validation_status (operator-veto
       is the most authoritative state).
    2. Status-based rejection via ``_VALIDATION_STATUS_TO_REJECTION`` (lossless
       routing of invalid/draft/credential-missing/provider-unreachable/etc.).
    3. Provider reachability.
    4. Capability checks against the intent.
    """
    if service.status == ServiceStatus.DISABLED:
        return _reject(service, ResolverRejectionCode.OPERATOR_VETO, f"{service.service_name} is disabled by operator.")
    if service.status != ServiceStatus.VALID:
        return _reject_via_validation_status(service)
    if not service.provider_reachable:
        return _reject(service, ResolverRejectionCode.PROVIDER_UNREACHABLE, f"{service.service_name} provider is unreachable.")

    caps = service.capabilities
    if intent.requires_streaming and not caps.supports_streaming:
        return _reject(service, ResolverRejectionCode.STREAM_NOT_AVAILABLE, f"{service.service_name} does not support streaming market data.")
    if intent.requires_realtime and not caps.supports_realtime:
        return _reject(service, ResolverRejectionCode.STREAM_NOT_AVAILABLE, f"{service.service_name} does not support realtime market data.")
    if intent.requires_intraday and not caps.supports_intraday:
        return _reject(service, ResolverRejectionCode.UNSUPPORTED_TIMEFRAME, f"{service.service_name} does not support intraday timeframes.")
    if intent.requires_historical and not caps.supports_historical:
        return _reject(service, ResolverRejectionCode.HISTORICAL_NOT_AVAILABLE, f"{service.service_name} does not support historical bars.")
    if intent.timeframe == Timeframe.D1 and not caps.supports_daily:
        return _reject(service, ResolverRejectionCode.UNSUPPORTED_TIMEFRAME, f"{service.service_name} does not support daily bars.")
    if intent.timeframe == Timeframe.W1 and not caps.supports_weekly:
        return _reject(service, ResolverRejectionCode.UNSUPPORTED_TIMEFRAME, f"{service.service_name} does not support weekly bars.")
    if intent.timeframe == Timeframe.MO1 and not caps.supports_monthly:
        return _reject(service, ResolverRejectionCode.UNSUPPORTED_TIMEFRAME, f"{service.service_name} does not support monthly bars.")
    if intent.is_long_range_historical and not caps.supports_long_range_history:
        return _reject(service, ResolverRejectionCode.HISTORICAL_NOT_AVAILABLE, f"{service.service_name} does not support long-range historical coverage.")
    return None


def _reject_via_validation_status(service: MarketDataServiceConfig) -> RejectedCandidate:
    """Map ``service.validation_status`` losslessly to a frozen rejection code.

    Never-validated services (DRAFT with ``validation_status is None``) and
    services whose validation explicitly returned ``invalid`` both surface as
    ``PROVIDER_NOT_VALIDATED`` — operator action in both cases is "run validate".
    """
    status = service.validation_status
    if status is None:
        return _reject(
            service,
            ResolverRejectionCode.PROVIDER_NOT_VALIDATED,
            f"{service.service_name} has not been validated; run Validate before using.",
        )
    code = _VALIDATION_STATUS_TO_REJECTION.get(status)
    if code is None:
        return _reject(
            service,
            ResolverRejectionCode.PROVIDER_NOT_VALIDATED,
            f"{service.service_name} validation_status '{status}' has no rejection mapping; treating as not validated.",
        )
    return _reject(service, code, _validation_explanation(service, code))


def _validation_explanation(service: MarketDataServiceConfig, code: ResolverRejectionCode) -> str:
    if code == ResolverRejectionCode.CREDENTIAL_MISSING:
        return f"{service.service_name} is missing required credentials."
    if code == ResolverRejectionCode.PROVIDER_UNREACHABLE:
        return f"{service.service_name} provider was unreachable at last validation."
    if code == ResolverRejectionCode.CAPABILITY_TIER_INSUFFICIENT:
        return f"{service.service_name} provider is unsupported by this catalog."
    if code == ResolverRejectionCode.OPERATOR_VETO:
        return f"{service.service_name} is disabled by operator."
    if code == ResolverRejectionCode.PROVIDER_NOT_VALIDATED:
        return f"{service.service_name} did not pass validation; re-run Validate."
    return f"{service.service_name} cannot be used: {code.value}."


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


def _selected_explanation(
    intent: DataIntent,
    service: MarketDataServiceConfig,
    selection_code: ResolverSelectionCode,
) -> str:
    if selection_code == ResolverSelectionCode.SELECTED_DEFAULT_PREFERRED:
        return f"Selected {service.service_name} because it is the default Market Data Service and satisfies the detected intent."
    if selection_code == ResolverSelectionCode.SELECTED_MANUAL_OVERRIDE:
        return f"Selected {service.service_name} because it was manually chosen and satisfies the detected intent."
    if intent.consumer == DataConsumer.BROKER_RUNTIME:
        return f"Selected {service.service_name} because Broker Runtime requires realtime intraday streaming."
    if intent.is_long_range_historical and not intent.requires_streaming:
        return f"Selected {service.service_name} because the request uses long-range historical data and does not require streaming."
    return f"Selected {service.service_name} because its capabilities satisfy the detected data intent."


def _reject(
    service: MarketDataServiceConfig,
    reason_code: ResolverRejectionCode,
    explanation: str,
) -> RejectedCandidate:
    return RejectedCandidate(
        service_id=service.service_id,
        service_name=service.service_name,
        provider=service.provider,
        reason_code=reason_code,
        explanation=explanation,
    )


def _aggregate_decision(rows: tuple[PerSymbolResolution, ...]) -> ResolverDecision:
    selected = sum(1 for row in rows if row.decision == ResolverDecision.SELECTED)
    rejected = sum(1 for row in rows if row.decision == ResolverDecision.REJECTED)
    if selected == len(rows):
        return ResolverDecision.SELECTED
    if rejected == len(rows):
        return ResolverDecision.REJECTED
    return ResolverDecision.PARTIAL


def _stable_service_projection(service: MarketDataServiceConfig) -> dict:
    """Project a service to the subset that is identity-stable for the resolver.

    Excludes operator-readable prose (``service_name``, ``validation_message``,
    ``credentials_ref``) so cosmetic re-wording does not invalidate replay
    equality.
    """
    return {
        "service_id": service.service_id,
        "provider": service.provider.value,
        "service_type": service.service_type.value,
        "status": service.status.value,
        "is_default": service.is_default,
        "validation_status": service.validation_status,
        "provider_reachable": service.provider_reachable,
        "capabilities": service.capabilities.model_dump(mode="json"),
    }


def _compute_resolver_input_hash(
    *,
    intent: DataIntent,
    services: tuple[MarketDataServiceConfig, ...],
    selection_strategy: SelectionStrategy,
    selected_service_id: str | None,
    invocation_context: InvocationContext,
) -> str:
    payload = {
        "resolver_version": RESOLVER_VERSION,
        "selection_strategy": selection_strategy.value,
        "selected_service_id": selected_service_id,
        "invocation_context": invocation_context.value,
        "intent": intent.model_dump(mode="json"),
        "services": sorted(
            (_stable_service_projection(service) for service in services),
            key=lambda payload: payload["service_id"],
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()
