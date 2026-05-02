from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import CandidateSide, OrderType, TradingMode
from backend.app.domain._base import utc_now
from backend.app.orders.models import InternalOrder

from .models import (
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)


try:  # pragma: no cover - real SDK is optional in unit tests.
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderClass as AlpacaOrderClass
    from alpaca.trading.enums import OrderSide as AlpacaOrderSide
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
    from alpaca.trading.requests import (
        GetOrdersRequest,
        LimitOrderRequest,
        MarketOrderRequest,
        StopLimitOrderRequest,
        StopLossRequest,
        StopOrderRequest,
        TakeProfitRequest,
    )
except ImportError:  # pragma: no cover
    TradingClient = None  # type: ignore[assignment]
    QueryOrderStatus = None  # type: ignore[assignment]
    GetOrdersRequest = None  # type: ignore[assignment]
    MarketOrderRequest = None  # type: ignore[assignment]
    LimitOrderRequest = None  # type: ignore[assignment]
    StopOrderRequest = None  # type: ignore[assignment]
    StopLimitOrderRequest = None  # type: ignore[assignment]
    StopLossRequest = None  # type: ignore[assignment]
    TakeProfitRequest = None  # type: ignore[assignment]
    AlpacaOrderClass = None  # type: ignore[assignment]
    AlpacaOrderSide = None  # type: ignore[assignment]
    AlpacaTimeInForce = None  # type: ignore[assignment]


try:  # pragma: no cover - TradingStream is part of alpaca-py too.
    from alpaca.trading.stream import TradingStream
except ImportError:  # pragma: no cover
    TradingStream = None  # type: ignore[assignment]


class AlpacaBrokerErrorDetails(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    retryable: bool = False
    context: dict[str, object] = Field(default_factory=dict)


class AlpacaBrokerError(BrokerAdapterError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        context: dict[str, object] | None = None,
    ) -> None:
        self.details = AlpacaBrokerErrorDetails(
            code=code,
            message=message,
            retryable=retryable,
            context=context or {},
        )
        super().__init__(message)


class AlpacaBrokerCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    supports_market_orders: bool = True
    supports_limit_orders: bool = True
    supports_stop_orders: bool = True
    # Bracket Program T-4: native_alpaca_bracket is supported via OrderClass.BRACKET
    # for whole-share, day/gtc, RTH, ETB-if-short orders. Operator-visible.
    supports_brackets: bool = True
    supports_fractional: bool = False
    supports_shorting: bool = False
    supports_streaming_trade_updates: bool = True
    supports_broker_paper: bool = True
    supports_broker_live: bool = False


_TERMINAL_BROKER_ORDER_STATUSES = {
    BrokerOrderStatus.FILLED,
    BrokerOrderStatus.CANCELED,
    BrokerOrderStatus.REJECTED,
    BrokerOrderStatus.EXPIRED,
}


class AlpacaBrokerAdapter:
    """Per-account Alpaca broker adapter (paper or live API host).

    ``TradingMode.BROKER_PAPER`` uses Alpaca's paper trading REST and trade-update
    stream hosts; ``TradingMode.BROKER_LIVE`` uses live trading hosts. The alpaca-py
    ``TradingClient``/``TradingStream`` ``paper=`` flag follows that mode.

    Product capabilities still mark ``supports_broker_live`` false until live
    execution is fully gated; order-type and orchestration limits may be
    stricter than the underlying SDK.

    Translates already-created internal orders and delegates to alpaca-py.
    Never creates internal orders. Mode + credentials are required; the
    adapter does not read environment variables — credentials come from
    the operator-driven ``BrokerCredentialStore`` (encrypted-at-rest)
    via the composition root.
    """

    provider = "alpaca"
    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    LIVE_BASE_URL = "https://api.alpaca.markets"

    def __init__(
        self,
        *,
        mode: TradingMode,
        api_key: str | None = None,
        secret_key: str | None = None,
        trading_client: Any | None = None,
        base_url: str | None = None,
        allow_live: bool = False,
    ) -> None:
        if base_url is not None:
            raise AlpacaBrokerError("custom_base_url_rejected", "Alpaca endpoint is derived from broker account mode")
        if mode not in (TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE):
            raise AlpacaBrokerError("unsupported_broker_mode", f"Unsupported Alpaca broker mode: {mode}")
        # M10 live-mode init guard (HARD.MD P2 tail): live trading requires
        # BOTH the env var TRADING_LIVE_ENABLED=true (system-wide) AND the
        # per-Account allow_live flag to be true. Both gates are operator-
        # owned. Default fail-closed: paper-only is always safe.
        if mode == TradingMode.BROKER_LIVE:
            env_live = os.environ.get("TRADING_LIVE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
            if not env_live:
                raise AlpacaBrokerError(
                    "live_mode_env_disabled",
                    "AlpacaBrokerAdapter cannot construct in BROKER_LIVE mode without TRADING_LIVE_ENABLED=true",
                )
            if not allow_live:
                raise AlpacaBrokerError(
                    "live_mode_account_disabled",
                    "AlpacaBrokerAdapter requires per-Account allow_live=True for BROKER_LIVE",
                )
        self.mode = mode
        self.base_url = self.endpoint_for_mode(mode)
        self.capabilities = AlpacaBrokerCapabilities()
        if trading_client is None:
            if not api_key or not secret_key:
                raise AlpacaBrokerError(
                    "missing_credentials",
                    "AlpacaBrokerAdapter requires explicit api_key and secret_key",
                )
        self._api_key = api_key
        self._secret_key = secret_key
        self._client = trading_client or self._build_trading_client()

    @classmethod
    def endpoint_for_mode(cls, mode: TradingMode) -> str:
        if mode == TradingMode.BROKER_PAPER:
            return cls.PAPER_BASE_URL
        if mode == TradingMode.BROKER_LIVE:
            return cls.LIVE_BASE_URL
        raise AlpacaBrokerError("unsupported_broker_mode", f"Unsupported Alpaca broker mode: {mode}")

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        self._require_internal_order(order)
        existing = self._get_existing_order(order)
        if existing is not None:
            return existing
        try:
            response = self._client.submit_order(order_data=self.to_alpaca_order_request(order))
        except Exception as exc:  # noqa: BLE001 - normalize external SDK errors at boundary.
            raise self._normalize_exception(exc) from exc
        return self.order_response_to_result(order=order, response=self._response_to_dict(response))

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        self._require_internal_order(order)
        try:
            response = self._client.get_order_by_client_id(order.client_order_id)
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        return self.order_response_to_result(order=order, response=self._response_to_dict(response))

    def cancel_order(self, order: InternalOrder) -> BrokerOrderResult:
        self._require_internal_order(order)
        current = self.get_order(order)
        if not current.broker_order_id:
            raise AlpacaBrokerError("missing_broker_order_id", "cancel requires broker_order_id")
        try:
            response = self._client.cancel_order_by_id(current.broker_order_id)
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        payload = self._response_to_dict(response)
        if not payload:
            payload = {
                "id": current.broker_order_id,
                "client_order_id": order.client_order_id,
                "status": "canceled",
                "filled_qty": current.filled_quantity,
                "canceled_at": utc_now(),
            }
        return self.order_response_to_result(order=order, response=payload)

    def cancel_orders(self, account_id: UUID, scope: str) -> tuple[BrokerOrderResult, ...]:
        _ = account_id, scope
        raise AlpacaBrokerError(
            "bulk_cancel_requires_internal_orders",
            "Alpaca bulk cancellation is routed through OrderManager-selected InternalOrder objects",
        )

    def replace_order(self, order: InternalOrder, new_params: Mapping[str, object]) -> BrokerOrderResult:
        self._require_internal_order(order)
        current = self.get_order(order)
        if not current.broker_order_id:
            raise AlpacaBrokerError("missing_broker_order_id", "replace requires broker_order_id")
        try:
            response = self._client.replace_order_by_id(current.broker_order_id, **dict(new_params))
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        return self.order_response_to_result(order=order, response=self._response_to_dict(response))

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        try:
            responses = self._client.get_orders(filter=self._open_orders_request())
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        results: list[BrokerOpenOrderSnapshot] = []
        for response in responses:
            payload = self._response_to_dict(response)
            status = self.normalize_status(payload.get("status", ""))
            if status in _TERMINAL_BROKER_ORDER_STATUSES:
                continue
            results.append(self.open_order_response_to_snapshot(account_id=account_id, response=payload))
        return tuple(results)

    def _open_orders_request(self) -> object | None:
        if GetOrdersRequest is None or QueryOrderStatus is None:
            return None
        return GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500, nested=False)

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        try:
            response = self._client.get_account()
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        return self.account_response_to_snapshot(account_id=account_id, response=self._response_to_dict(response))

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        try:
            responses = self._client.get_all_positions()
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        return tuple(
            self.position_response_to_snapshot(account_id=account_id, response=self._response_to_dict(response))
            for response in responses
        )

    def get_market_clock(self) -> dict[str, Any]:
        try:
            return self._response_to_dict(self._client.get_clock())
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc

    def translate_order_request(self, order: InternalOrder) -> dict[str, object]:
        self._require_internal_order(order)
        if order.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} and order.limit_price is None:
            raise AlpacaBrokerError(
                "limit_price_required",
                "limit and stop-limit Alpaca orders require limit_price",
                context={"order_id": str(order.order_id), "order_type": order.order_type.value},
            )
        if order.order_type in {OrderType.STOP, OrderType.STOP_LIMIT} and order.stop_price is None:
            raise AlpacaBrokerError(
                "stop_price_required",
                "stop and stop-limit Alpaca orders require stop_price",
                context={"order_id": str(order.order_id), "order_type": order.order_type.value},
            )
        request: dict[str, object] = {
            "symbol": order.symbol,
            "qty": order.quantity,
            "side": self._alpaca_side(order.side),
            "type": order.order_type.value,
            "time_in_force": order.time_in_force.value,
            "client_order_id": order.client_order_id,
        }
        if order.limit_price is not None:
            request["limit_price"] = order.limit_price
        if order.stop_price is not None:
            request["stop_price"] = order.stop_price
        if order.extended_hours:
            request["extended_hours"] = True
        return request

    def to_alpaca_order_request(self, order: InternalOrder) -> Any:
        if order.order_class == "oco":
            self._validate_native_oco_preflight(order)
        request = self.translate_order_request(order)
        request_class = self._request_class_for_order_type(order.order_type)
        kwargs: dict[str, Any] = {
            "symbol": request["symbol"],
            "qty": request["qty"],
            "side": self._enum_value(AlpacaOrderSide, str(request["side"])),
            "time_in_force": self._enum_value(AlpacaTimeInForce, str(request["time_in_force"])),
            "client_order_id": request["client_order_id"],
        }
        if order.extended_hours:
            kwargs["extended_hours"] = True
        if order.limit_price is not None:
            kwargs["limit_price"] = self._alpaca_price(order.limit_price)
        if order.stop_price is not None:
            kwargs["stop_price"] = self._alpaca_price(order.stop_price)
        if order.order_class == "oco":
            self._require_sdk_class(AlpacaOrderClass, "OrderClass")
            self._require_sdk_class(TakeProfitRequest, "TakeProfitRequest")
            self._require_sdk_class(StopLossRequest, "StopLossRequest")
            kwargs["order_class"] = self._enum_value(AlpacaOrderClass, "OCO")
            kwargs["take_profit"] = TakeProfitRequest(  # type: ignore[misc]
                limit_price=self._alpaca_price(order.limit_price),
            )
            kwargs["stop_loss"] = StopLossRequest(  # type: ignore[misc]
                stop_price=self._alpaca_price(order.bracket_stop_loss_stop_price),
            )
        if order.order_class == "bracket":
            self._validate_native_bracket_preflight(order)
            self._require_sdk_class(AlpacaOrderClass, "OrderClass")
            self._require_sdk_class(TakeProfitRequest, "TakeProfitRequest")
            self._require_sdk_class(StopLossRequest, "StopLossRequest")
            kwargs["order_class"] = self._enum_value(AlpacaOrderClass, "BRACKET")
            kwargs["take_profit"] = TakeProfitRequest(  # type: ignore[misc]
                limit_price=self._alpaca_price(order.bracket_take_profit_limit_price),
            )
            kwargs["stop_loss"] = StopLossRequest(  # type: ignore[misc]
                stop_price=self._alpaca_price(order.bracket_stop_loss_stop_price),
            )
        return request_class(**kwargs)  # type: ignore[misc,operator]

    @staticmethod
    def _alpaca_price(price: float | None) -> float | None:
        if price is None:
            return None
        quantum = Decimal("0.01") if price >= 1 else Decimal("0.0001")
        return float(Decimal(str(price)).quantize(quantum, rounding=ROUND_HALF_UP))

    def _validate_native_bracket_preflight(self, order: InternalOrder) -> None:
        """Refuse to submit a native Alpaca bracket that violates the constraint matrix.

        Verified 2026-04-29 against ``docs.alpaca.markets`` + alpaca-py SDK:

        - Bracket TIF must be ``day`` or ``gtc``.
        - Extended hours not supported.
        - Bracket + fractional shares not supported (whole-share only).
        - Bracket + notional not supported.
        - Bracket child prices required: take_profit limit_price + stop_loss stop_price.
        - Long+short bracket on the same symbol concurrently is forbidden by Alpaca,
          but that's an account-level constraint better caught at the OrderManager
          / RiskResolver. We don't re-check here to keep this local.

        Per operator: "fail clearly if Alpaca rejects the structure."
        """

        if order.bracket_take_profit_limit_price is None or order.bracket_stop_loss_stop_price is None:
            raise AlpacaBrokerError(
                "native_bracket_missing_child_prices",
                "Native Alpaca bracket requires both take_profit limit_price and stop_loss stop_price",
                context={
                    "take_profit": order.bracket_take_profit_limit_price,
                    "stop_loss": order.bracket_stop_loss_stop_price,
                },
            )
        tif_value = order.time_in_force.value if hasattr(order.time_in_force, "value") else str(order.time_in_force)
        if tif_value not in {"day", "gtc"}:
            raise AlpacaBrokerError(
                "native_bracket_unsupported_tif",
                f"Native Alpaca bracket requires time_in_force=day|gtc; got {tif_value}",
                context={"time_in_force": tif_value},
            )
        if order.extended_hours:
            raise AlpacaBrokerError(
                "native_bracket_unsupported_extended_hours",
                "Native Alpaca bracket does not support extended hours",
            )
        if order.quantity != int(order.quantity):
            raise AlpacaBrokerError(
                "native_bracket_unsupported_fractional",
                f"Native Alpaca bracket requires whole-share quantity; got {order.quantity}",
                context={"quantity": order.quantity},
            )

    def _validate_native_oco_preflight(self, order: InternalOrder) -> None:
        if order.limit_price is None or order.bracket_stop_loss_stop_price is None:
            raise AlpacaBrokerError(
                "native_oco_missing_prices",
                "Native Alpaca OCO requires primary limit_price and stop_loss stop_price",
                context={
                    "limit_price": order.limit_price,
                    "stop_loss": order.bracket_stop_loss_stop_price,
                },
            )
        tif_value = order.time_in_force.value if hasattr(order.time_in_force, "value") else str(order.time_in_force)
        if tif_value not in {"day", "gtc"}:
            raise AlpacaBrokerError(
                "native_oco_unsupported_tif",
                f"Native Alpaca OCO requires time_in_force=day|gtc; got {tif_value}",
                context={"time_in_force": tif_value},
            )
        if order.extended_hours:
            raise AlpacaBrokerError(
                "native_oco_unsupported_extended_hours",
                "Native Alpaca OCO does not support extended hours",
            )
        if order.quantity != int(order.quantity):
            raise AlpacaBrokerError(
                "native_oco_unsupported_fractional",
                f"Native Alpaca OCO requires whole-share quantity; got {order.quantity}",
                context={"quantity": order.quantity},
            )

    def normalize_status(self, status: object) -> BrokerOrderStatus:
        normalized = self._status_token(status)
        mapping = {
            "new": BrokerOrderStatus.ACCEPTED,
            "accepted": BrokerOrderStatus.ACCEPTED,
            "pending_new": BrokerOrderStatus.ACCEPTED,
            "accepted_for_bidding": BrokerOrderStatus.ACCEPTED,
            "held": BrokerOrderStatus.ACCEPTED,
            "stopped": BrokerOrderStatus.ACCEPTED,
            "partial_fill": BrokerOrderStatus.PARTIAL_FILL,
            "partially_filled": BrokerOrderStatus.PARTIAL_FILL,
            "filled": BrokerOrderStatus.FILLED,
            "canceled": BrokerOrderStatus.CANCELED,
            "cancelled": BrokerOrderStatus.CANCELED,
            "expired": BrokerOrderStatus.EXPIRED,
            "pending_cancel": BrokerOrderStatus.PENDING_CANCEL,
            "pending_replace": BrokerOrderStatus.REPLACED,
            "replaced": BrokerOrderStatus.REPLACED,
            "rejected": BrokerOrderStatus.REJECTED,
            "suspended": BrokerOrderStatus.SUSPENDED,
            "done_for_day": BrokerOrderStatus.DONE_FOR_DAY,
            "calculated": BrokerOrderStatus.DONE_FOR_DAY,
        }
        try:
            return mapping[normalized]
        except KeyError as exc:
            raise AlpacaBrokerError("unknown_order_status", f"Unknown Alpaca order status: {status}") from exc

    def _status_token(self, status: object) -> str:
        raw_status = getattr(status, "value", status)
        token = str(raw_status).strip()
        if "." in token:
            token = token.rsplit(".", 1)[-1]
        return token.lower()

    def order_response_to_result(self, *, order: InternalOrder, response: dict[str, Any]) -> BrokerOrderResult:
        self._require_internal_order(order)
        status_raw = str(response.get("status", ""))
        status = self.normalize_status(status_raw)
        filled_quantity = self._float(response.get("filled_qty"), default=0)
        remaining_quantity = max(order.quantity - filled_quantity, 0)
        reason = response.get("rejected_reason") or response.get("reject_reason")
        if status == BrokerOrderStatus.REJECTED and not reason:
            reason = "alpaca_rejected"
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=str(response.get("client_order_id") or order.client_order_id),
            status=status,
            broker_order_id=str(response["id"]) if response.get("id") is not None else None,
            broker_status=status_raw,
            filled_quantity=filled_quantity,
            filled_avg_price=self._optional_float(response.get("filled_avg_price")),
            remaining_quantity=remaining_quantity,
            reason=str(reason) if reason is not None else None,
            received_at=utc_now(),
            submitted_at=self._optional_datetime(response.get("submitted_at")),
            updated_at=self._optional_datetime(response.get("updated_at")),
            filled_at=self._optional_datetime(response.get("filled_at")),
            canceled_at=self._optional_datetime(response.get("canceled_at")),
            reject_code=str(response["reject_code"]) if response.get("reject_code") is not None else None,
            raw_status=status_raw,
            broker_reference=str(response["id"]) if response.get("id") is not None else None,
        )

    def account_response_to_snapshot(self, *, account_id: UUID, response: dict[str, Any]) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider=self.provider,
            mode=self.mode,
            buying_power=self._float(response.get("buying_power"), default=0),
            daytrading_buying_power=self._float(response.get("daytrading_buying_power"), default=0),
            regt_buying_power=self._optional_float(response.get("regt_buying_power")),
            non_marginable_buying_power=self._optional_float(response.get("non_marginable_buying_power")),
            multiplier=self._optional_float(response.get("multiplier")),
            portfolio_value=self._optional_float(response.get("portfolio_value")),
            long_market_value=self._optional_float(response.get("long_market_value")),
            short_market_value=self._optional_float(response.get("short_market_value")),
            initial_margin=self._optional_float(response.get("initial_margin")),
            maintenance_margin=self._optional_float(response.get("maintenance_margin")),
            last_maintenance_margin=self._optional_float(response.get("last_maintenance_margin")),
            last_equity=self._optional_float(response.get("last_equity")),
            sma=self._optional_float(response.get("sma")),
            daytrade_count=self._optional_int(response.get("daytrade_count")),
            trade_suspended_by_user=bool(response.get("trade_suspended_by_user", False)),
            transfers_blocked=bool(response.get("transfers_blocked", False)),
            crypto_status=str(response["crypto_status"]) if response.get("crypto_status") is not None else None,
            currency=str(response["currency"]) if response.get("currency") is not None else None,
            accrued_fees=self._optional_float(response.get("accrued_fees")),
            pending_transfer_in=self._optional_float(response.get("pending_transfer_in")),
            pending_transfer_out=self._optional_float(response.get("pending_transfer_out")),
            cash=self._float(response.get("cash"), default=0),
            equity=self._float(response.get("equity"), default=0),
            trading_blocked=bool(response.get("trading_blocked", False)),
            account_blocked=bool(response.get("account_blocked", False)),
            is_pattern_day_trader=bool(response.get("pattern_day_trader", False)),
            account_status=str(response.get("status", "unknown")),
            external_account_id=str(response["id"]) if response.get("id") is not None else None,
            shorting_enabled=bool(response.get("shorting_enabled", False)),
            timestamp=utc_now(),
        )

    def position_response_to_snapshot(self, *, account_id: UUID, response: dict[str, Any]) -> BrokerPositionSnapshot:
        quantity = self._float(response.get("qty"), default=0)
        side = BrokerPositionSide.LONG if quantity >= 0 else BrokerPositionSide.SHORT
        return BrokerPositionSnapshot(
            account_id=account_id,
            symbol=str(response["symbol"]).upper(),
            qty=quantity,
            market_value=self._float(response.get("market_value"), default=0),
            avg_entry_price=self._float(response.get("avg_entry_price"), default=0),
            side=side,
            unrealized_pl=self._float(response.get("unrealized_pl"), default=0),
            timestamp=utc_now(),
        )

    def open_order_response_to_snapshot(self, *, account_id: UUID, response: dict[str, Any]) -> BrokerOpenOrderSnapshot:
        return BrokerOpenOrderSnapshot(
            account_id=account_id,
            broker_order_id=str(response.get("id") or ""),
            client_order_id=str(response.get("client_order_id") or ""),
            symbol=str(response.get("symbol", "UNKNOWN")).upper(),
            side=str(response.get("side", "unknown")).lower(),
            qty=self._float(response.get("qty"), default=0),
            filled_qty=self._float(response.get("filled_qty"), default=0),
            status=self.normalize_status(response.get("status", "")),
            order_type=str(response.get("type", "unknown")).lower(),
            limit_price=self._optional_float(response.get("limit_price")),
            stop_price=self._optional_float(response.get("stop_price")),
            timestamp=self._optional_datetime(response.get("updated_at")) or utc_now(),
        )

    def _build_trading_client(self) -> Any:
        if TradingClient is None:
            raise AlpacaBrokerError("missing_sdk", "alpaca-py is required for Alpaca broker execution")
        kwargs: dict[str, object] = {"paper": self.mode == TradingMode.BROKER_PAPER}
        return TradingClient(self._api_key, self._secret_key, **kwargs)  # type: ignore[misc,operator]

    def build_trading_stream(self) -> Any:
        """Construct an alpaca-py ``TradingStream`` for this account.

        TradingStream is a 24/7 push channel that emits trade-update events
        whenever this account has order activity (accepted, fills, cancels,
        replacements). It does not depend on equity market hours — paper or
        live, order lifecycle events can arrive outside regular equity sessions.
        """
        if TradingStream is None:
            raise AlpacaBrokerError("missing_sdk", "alpaca-py is required for streaming")
        if not (self._api_key and self._secret_key):
            raise AlpacaBrokerError("missing_credentials", "API key and secret are required for TradingStream")
        return TradingStream(  # type: ignore[misc,operator]
            api_key=self._api_key,
            secret_key=self._secret_key,
            paper=self.mode == TradingMode.BROKER_PAPER,
        )

    def _get_existing_order(self, order: InternalOrder) -> BrokerOrderResult | None:
        try:
            return self.get_order(order)
        except AlpacaBrokerError as exc:
            if exc.details.code == "order_not_found":
                return None
            raise

    def _require_internal_order(self, order: InternalOrder) -> None:
        if not isinstance(order, InternalOrder):
            raise AlpacaBrokerError("invalid_order_boundary", "Alpaca adapter requires an already-created InternalOrder")

    def _alpaca_side(self, side: CandidateSide) -> str:
        if side == CandidateSide.LONG:
            return "buy"
        if side == CandidateSide.SHORT:
            return "sell"
        raise AlpacaBrokerError("unsupported_side", f"Unsupported order side: {side}")

    def _float(self, value: object, *, default: float) -> float:
        if value is None:
            return default
        return float(value)

    def _optional_float(self, value: object) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    def _optional_int(self, value: object) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    def _optional_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _require_sdk_class(self, sdk_class: object, name: str) -> None:
        if sdk_class is None:
            raise AlpacaBrokerError("missing_sdk", f"alpaca-py {name} is required")

    def _request_class_for_order_type(self, order_type: OrderType) -> object:
        mapping = {
            OrderType.MARKET: (MarketOrderRequest, "MarketOrderRequest"),
            OrderType.LIMIT: (LimitOrderRequest, "LimitOrderRequest"),
            OrderType.STOP: (StopOrderRequest, "StopOrderRequest"),
            OrderType.STOP_LIMIT: (StopLimitOrderRequest, "StopLimitOrderRequest"),
        }
        try:
            request_class, name = mapping[order_type]
        except KeyError as exc:
            raise AlpacaBrokerError("unsupported_order_type", f"Unsupported Alpaca order type: {order_type}") from exc
        self._require_sdk_class(request_class, name)
        return request_class

    def _enum_value(self, enum_class: object, value: str) -> object:
        if enum_class is None:
            return value
        try:
            return getattr(enum_class, value.upper())
        except AttributeError:
            return value

    def _response_to_dict(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return dict(response)
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        keys = [
            "id",
            "client_order_id",
            "status",
            "filled_qty",
            "filled_avg_price",
            "submitted_at",
            "updated_at",
            "filled_at",
            "canceled_at",
            "rejected_reason",
            "reject_reason",
            "reject_code",
            "buying_power",
            "cash",
            "equity",
            "daytrading_buying_power",
            "regt_buying_power",
            "non_marginable_buying_power",
            "multiplier",
            "portfolio_value",
            "long_market_value",
            "short_market_value",
            "initial_margin",
            "maintenance_margin",
            "last_maintenance_margin",
            "last_equity",
            "sma",
            "daytrade_count",
            "trade_suspended_by_user",
            "transfers_blocked",
            "crypto_status",
            "currency",
            "accrued_fees",
            "pending_transfer_in",
            "pending_transfer_out",
            "status",
            "trading_blocked",
            "account_blocked",
            "pattern_day_trader",
            "shorting_enabled",
            "symbol",
            "side",
            "qty",
            "type",
            "limit_price",
            "stop_price",
            "market_value",
            "avg_entry_price",
            "unrealized_pl",
            "is_open",
            "next_open",
            "next_close",
            "timestamp",
        ]
        return {key: getattr(response, key) for key in keys if hasattr(response, key)}

    def _normalize_exception(self, exc: Exception) -> AlpacaBrokerError:
        message = str(exc)
        lowered = message.lower()
        status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if status_code == 404 or "not found" in lowered:
            return AlpacaBrokerError("order_not_found", message, retryable=False)
        if status_code == 429 or "rate limit" in lowered or "too many requests" in lowered:
            return AlpacaBrokerError("rate_limited", message, retryable=True)
        if any(token in lowered for token in ("timeout", "temporarily unavailable", "connection", "network")):
            return AlpacaBrokerError("network_error", message, retryable=True)
        if "auth" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
            return AlpacaBrokerError("auth_error", message, retryable=False)
        if "buying power" in lowered or "insufficient" in lowered:
            return AlpacaBrokerError("insufficient_buying_power", message, retryable=False)
        if "tradable" in lowered or "not active" in lowered:
            return AlpacaBrokerError("symbol_not_tradable", message, retryable=False)
        if "validation" in lowered or "invalid" in lowered:
            return AlpacaBrokerError("validation_error", message, retryable=False)
        return AlpacaBrokerError("broker_error", message, retryable=False)
