from __future__ import annotations

from collections.abc import Iterable

from backend.app.domain import BROKER_MODES, CandidateSide, OrderType, TimeInForce
from backend.app.orders.models import InternalOrder, InternalOrderIntent

from .capabilities import (
    BrokerAssetClass,
    BrokerCapabilityViolation,
    BrokerErrorFamily,
    BrokerErrorSeverity,
    BrokerOperation,
    BrokerOperatorAdvisory,
    BrokerOrderClass,
    BrokerOrderPreflightRequest,
    BrokerOrderPreflightResult,
    BrokerViolationCode,
    MarketRulePreflightRequest,
    MarketRulePreflightResult,
    MarketRuleViolation,
    MarketRuleViolationCode,
    MarketSessionState,
)


def build_broker_order_preflight_request(
    *,
    order: InternalOrder,
    provider: str,
    broker_mode,
    asset_class: BrokerAssetClass = BrokerAssetClass.EQUITY,
) -> BrokerOrderPreflightRequest:
        return BrokerOrderPreflightRequest(
        account_id=order.account_id,
        provider=provider,
        broker_mode=broker_mode,
        asset_class=asset_class,
        symbol=order.symbol,
        side=order.side,
        is_position_management=order.intent != InternalOrderIntent.OPEN,
        quantity=order.quantity,
        order_type=order.order_type,
        time_in_force=order.time_in_force,
        order_class=BrokerOrderClass(order.order_class) if order.order_class is not None else BrokerOrderClass.SIMPLE,
        extended_hours=order.extended_hours,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
    )


def build_market_rule_preflight_request(
    *,
    order: InternalOrder,
    provider: str,
    broker_mode,
    buying_power: float,
    asset_class: BrokerAssetClass = BrokerAssetClass.EQUITY,
    market_session: MarketSessionState = MarketSessionState.REGULAR,
    asset_tradable: bool = True,
    asset_fractionable: bool = True,
    shortable: bool = True,
    easy_to_borrow: bool = True,
    halted: bool = False,
) -> MarketRulePreflightRequest:
    return MarketRulePreflightRequest(
        account_id=order.account_id,
        provider=provider,
        broker_mode=broker_mode,
        symbol=order.symbol,
        asset_class=asset_class,
        side=order.side,
        is_position_management=order.intent != InternalOrderIntent.OPEN,
        quantity=order.quantity,
        order_type=order.order_type,
        time_in_force=order.time_in_force,
        order_class=BrokerOrderClass.SIMPLE,
        extended_hours=order.extended_hours,
        market_session=market_session,
        asset_tradable=asset_tradable,
        asset_fractionable=asset_fractionable,
        shortable=shortable,
        easy_to_borrow=easy_to_borrow,
        halted=halted,
        buying_power=buying_power,
    )


class AlpacaBrokerPreflightService:
    """Provider-specific broker capability checks before Alpaca submission."""

    provider = "alpaca"

    def preflight_order(self, request: BrokerOrderPreflightRequest) -> BrokerOrderPreflightResult:
        violations: list[BrokerCapabilityViolation] = []
        warnings: list[str] = []

        if request.provider.lower() != self.provider:
            violations.append(
                self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
                    "broker preflight service only supports Alpaca requests",
                    field="provider",
                    operator_advisory="Route non-Alpaca accounts through their own broker preflight service.",
                )
            )

        if request.broker_mode not in BROKER_MODES:
            violations.append(
                self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
                    "broker preflight requires a broker trading mode",
                    field="broker_mode",
                    operator_advisory="Use BROKER_PAPER or BROKER_LIVE for broker order submission.",
                )
            )

        if request.operation is BrokerOperation.CANCEL:
            return self._broker_result(request, violations, warnings)

        if request.operation is BrokerOperation.REPLACE:
            violations.append(
                self._broker_violation(
                    BrokerViolationCode.REPLACE_UNSUPPORTED,
                    "order replace is not yet enabled by the Alpaca adapter boundary",
                    field="operation",
                    operator_advisory="Cancel and resubmit after the adapter exposes safe replace semantics.",
                )
            )

        violations.extend(self._native_multileg_violations(request))

        violations.extend(self._asset_shape_violations(request))
        violations.extend(self._price_shape_violations(request))

        return self._broker_result(request, violations, warnings)

    def _asset_shape_violations(
        self, request: BrokerOrderPreflightRequest
    ) -> Iterable[BrokerCapabilityViolation]:
        if request.extended_hours:
            if request.asset_class not in {BrokerAssetClass.EQUITY, BrokerAssetClass.FRACTIONAL_EQUITY}:
                yield self._broker_violation(
                    BrokerViolationCode.EXTENDED_HOURS_UNSUPPORTED,
                    "extended-hours orders are only enabled for Alpaca equity orders",
                    field="extended_hours",
                    operator_advisory="Disable extended hours for this asset class.",
                )
            if request.order_type is not OrderType.LIMIT:
                yield self._broker_violation(
                    BrokerViolationCode.EXTENDED_HOURS_UNSUPPORTED,
                    "Alpaca extended-hours equity orders must be limit orders",
                    field="order_type",
                    operator_advisory="Use a limit DAY order or submit during the regular session.",
                )
            if request.time_in_force is not TimeInForce.DAY:
                yield self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE,
                    "Alpaca extended-hours equity orders must use DAY time in force",
                    field="time_in_force",
                    operator_advisory="Set time_in_force to DAY for extended-hours equity orders.",
                )

        if request.asset_class is BrokerAssetClass.CRYPTO:
            if request.time_in_force not in {TimeInForce.GTC, TimeInForce.IOC}:
                yield self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE,
                    "Alpaca crypto orders support GTC or IOC time in force",
                    field="time_in_force",
                    operator_advisory="Use GTC or IOC for crypto orders.",
                )
            if request.order_type not in {OrderType.MARKET, OrderType.LIMIT, OrderType.STOP_LIMIT}:
                yield self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
                    "Alpaca crypto orders support market, limit, or stop-limit orders",
                    field="order_type",
                    operator_advisory="Use market, limit, or stop-limit for crypto orders.",
                )

        if request.asset_class is BrokerAssetClass.OPTION:
            if request.time_in_force is not TimeInForce.DAY:
                yield self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE,
                    "Alpaca option orders currently use DAY time in force",
                    field="time_in_force",
                    operator_advisory="Set time_in_force to DAY for option orders.",
                )
            if request.order_type not in {OrderType.MARKET, OrderType.LIMIT}:
                yield self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
                    "Alpaca option orders currently support market or limit orders",
                    field="order_type",
                    operator_advisory="Use market or limit for option orders.",
                )

        if request.asset_class is BrokerAssetClass.FRACTIONAL_EQUITY:
            if request.time_in_force is not TimeInForce.DAY:
                yield self._broker_violation(
                    BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE,
                    "Alpaca fractional equity orders must use DAY time in force",
                    field="time_in_force",
                    operator_advisory="Set time_in_force to DAY for fractional equity orders.",
                )

        if not request.is_position_management and request.side is CandidateSide.SHORT and request.asset_class in {
            BrokerAssetClass.CRYPTO,
            BrokerAssetClass.OPTION,
        }:
            yield self._broker_violation(
                BrokerViolationCode.SHORTING_UNSUPPORTED,
                "short orders are not enabled for this Alpaca asset class",
                field="side",
                operator_advisory="Use a long-only plan for this asset class.",
            )

    def _native_multileg_violations(
        self, request: BrokerOrderPreflightRequest
    ) -> Iterable[BrokerCapabilityViolation]:
        if request.order_class is BrokerOrderClass.SIMPLE and not request.native_multileg_requested:
            return
        if request.target_leg_count > 1:
            yield self._broker_violation(
                BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED,
                "Alpaca broker-native bracket orders do not support multiple take-profit targets in one broker order",
                field="target_leg_count",
                operator_advisory=(
                    "Keep the SignalPlan lifecycle intact internally and submit target legs through "
                    "ledger-managed orders until broker-native multi-target support exists."
                ),
            )
        if request.stop_leg_count > 1:
            yield self._broker_violation(
                BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED,
                "Alpaca broker-native bracket/OCO orders support one stop leg in the current capability profile",
                field="stop_leg_count",
                operator_advisory="Use one active protective stop or internal replacement logic for stop updates.",
            )
        if request.runner_leg_count > 0:
            yield self._broker_violation(
                BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED,
                "runner management is an internal lifecycle concept, not an Alpaca broker-native order class",
                field="runner_leg_count",
                operator_advisory="Manage runner state internally and submit broker orders only when a runner action is due.",
            )
        yield self._broker_violation(
            BrokerViolationCode.UNSUPPORTED_ORDER_CLASS,
            "broker-native Alpaca bracket/OCO/OTO submission is not enabled by the current adapter boundary",
            field="order_class",
            operator_advisory="Use internal SignalPlan leg allocation and ledger-managed legs as child orders.",
        )

    def _price_shape_violations(
        self, request: BrokerOrderPreflightRequest
    ) -> Iterable[BrokerCapabilityViolation]:
        if request.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} and request.limit_price is None:
            yield self._broker_violation(
                BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
                "limit and stop-limit orders require limit_price",
                field="limit_price",
                operator_advisory="Provide limit_price before submitting this order.",
            )
        if request.order_type in {OrderType.STOP, OrderType.STOP_LIMIT} and request.stop_price is None:
            yield self._broker_violation(
                BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
                "stop and stop-limit orders require stop_price",
                field="stop_price",
                operator_advisory="Provide stop_price before submitting this order.",
            )

    @staticmethod
    def _broker_violation(
        code: BrokerViolationCode,
        message: str,
        *,
        field: str,
        operator_advisory: str,
    ) -> BrokerCapabilityViolation:
        return BrokerCapabilityViolation(
            code=code,
            message=message,
            field=field,
            operator_advisory=operator_advisory,
        )

    def _broker_result(
        self,
        request: BrokerOrderPreflightRequest,
        violations: list[BrokerCapabilityViolation],
        warnings: list[str],
    ) -> BrokerOrderPreflightResult:
        if not violations:
            return BrokerOrderPreflightResult(
                allowed=True,
                warnings=tuple(warnings),
                normalized_request=request.model_dump(mode="json"),
            )

        return BrokerOrderPreflightResult(
            allowed=False,
            violations=tuple(violations),
            warnings=tuple(warnings),
            normalized_request=request.model_dump(mode="json"),
            operator_advisory=self._advisory(
                "Alpaca broker preflight rejected the order before submission.",
                violations[0].operator_advisory or "Review the broker preflight violations.",
            ),
        )

    @staticmethod
    def _advisory(message: str, operator_action: str) -> BrokerOperatorAdvisory:
        return BrokerOperatorAdvisory(
            family=BrokerErrorFamily.VALIDATION,
            severity=BrokerErrorSeverity.ERROR,
            retryable=False,
            source="alpaca_preflight",
            message=message,
            operator_action=operator_action,
        )


class MarketRulePreflightService:
    """Account, session, and asset state checks before order creation."""

    def preflight_market_rules(self, request: MarketRulePreflightRequest) -> MarketRulePreflightResult:
        violations: list[MarketRuleViolation] = []

        if request.halted:
            violations.append(
                self._market_violation(
                    MarketRuleViolationCode.ASSET_HALTED,
                    "asset is halted",
                    field="halted",
                    operator_advisory="Do not submit until the broker reports the asset is no longer halted.",
                )
            )

        if not request.asset_tradable:
            violations.append(
                self._market_violation(
                    MarketRuleViolationCode.ASSET_NOT_TRADABLE,
                    "asset is not tradable for this account",
                    field="asset_tradable",
                    operator_advisory="Remove this symbol from the deployment or choose a tradable asset.",
                )
            )

        if request.asset_class is BrokerAssetClass.FRACTIONAL_EQUITY and not request.asset_fractionable:
            violations.append(
                self._market_violation(
                    MarketRuleViolationCode.ASSET_NOT_FRACTIONABLE,
                    "asset does not support fractional trading",
                    field="asset_fractionable",
                    operator_advisory="Use whole-share sizing or choose a fractionable asset.",
                )
            )

        if request.side is CandidateSide.SHORT and not request.is_position_management:
            if not request.shortable:
                violations.append(
                    self._market_violation(
                        MarketRuleViolationCode.SHORT_NOT_ALLOWED,
                        "asset is not shortable",
                        field="shortable",
                        operator_advisory="Do not submit a short order for this symbol.",
                    )
                )
            if not request.easy_to_borrow:
                violations.append(
                    self._market_violation(
                        MarketRuleViolationCode.NOT_EASY_TO_BORROW,
                        "asset is not easy to borrow",
                        field="easy_to_borrow",
                        operator_advisory="Require operator review before shorting this symbol.",
                    )
                )

        if (
            request.market_session is MarketSessionState.CLOSED
            and request.asset_class is not BrokerAssetClass.CRYPTO
        ):
            violations.append(
                self._market_violation(
                    MarketRuleViolationCode.MARKET_CLOSED,
                    "market is closed for this asset class",
                    field="market_session",
                    operator_advisory="Wait for an eligible session or use a supported extended-hours order.",
                )
            )

        if request.notional is not None and request.notional > request.buying_power:
            violations.append(
                self._market_violation(
                    MarketRuleViolationCode.BUYING_POWER_INSUFFICIENT,
                    "order notional exceeds available buying power",
                    field="buying_power",
                    operator_advisory="Reduce order size or add buying power before submitting.",
                )
            )

        if not violations:
            return MarketRulePreflightResult(
                allowed=True,
                session_state=request.market_session,
            )

        return MarketRulePreflightResult(
            allowed=False,
            session_state=request.market_session,
            violations=tuple(violations),
            operator_advisory=AlpacaBrokerPreflightService._advisory(
                "Market rule preflight rejected the order before broker submission.",
                violations[0].operator_advisory or "Review the market rule violations.",
            ),
        )

    @staticmethod
    def _market_violation(
        code: MarketRuleViolationCode,
        message: str,
        *,
        field: str,
        operator_advisory: str,
    ) -> MarketRuleViolation:
        return MarketRuleViolation(
            code=code,
            message=message,
            field=field,
            operator_advisory=operator_advisory,
        )
