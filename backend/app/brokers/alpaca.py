from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import CandidateSide, OrderType
from backend.app.domain._base import utc_now
from backend.app.orders import InternalOrder

from .models import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)

try:  # pragma: no cover - exercised through monkeypatched globals in unit tests.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False


try:  # pragma: no cover - real SDK is optional in unit tests.
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide as AlpacaOrderSide
    from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
    from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
except ImportError:  # pragma: no cover
    TradingClient = None  # type: ignore[assignment]
    MarketOrderRequest = None  # type: ignore[assignment]
    LimitOrderRequest = None  # type: ignore[assignment]
    AlpacaOrderSide = None  # type: ignore[assignment]
    AlpacaTimeInForce = None  # type: ignore[assignment]


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
    supports_stop_orders: bool = False
    supports_brackets: bool = False
    supports_fractional: bool = False
    supports_shorting: bool = False
    supports_streaming_trade_updates: bool = False
    supports_paper: bool = True
    supports_live: bool = False


class AlpacaBrokerAdapter:
    """Paper-only Alpaca broker adapter.

    This adapter translates already-created internal orders and delegates to
    alpaca-py when a client is configured. It never creates internal orders.
    """

    provider = "alpaca"

    def __init__(
        self,
        *,
        mode: BrokerAccountMode = BrokerAccountMode.PAPER,
        trading_client: Any | None = None,
        load_env: bool = True,
    ) -> None:
        if mode != BrokerAccountMode.PAPER:
            raise AlpacaBrokerError("live_disabled", "AlpacaBrokerAdapter is paper-only in this implementation")
        self.mode = mode
        self.capabilities = AlpacaBrokerCapabilities()
        self._client = trading_client or self._build_trading_client(load_env=load_env)

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        self._require_internal_order(order)
        if order.order_type != OrderType.MARKET:
            raise AlpacaBrokerError(
                "submit_supports_market_only",
                "Alpaca paper execution currently submits market orders only",
                context={"order_id": str(order.order_id), "order_type": order.order_type.value},
            )
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

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        try:
            responses = self._client.get_orders()
        except Exception as exc:  # noqa: BLE001
            raise self._normalize_exception(exc) from exc
        results: list[BrokerOpenOrderSnapshot] = []
        for response in responses:
            payload = self._response_to_dict(response)
            if str(payload.get("status", "")).lower() not in {"new", "accepted", "pending_new", "partially_filled"}:
                continue
            results.append(self.open_order_response_to_snapshot(account_id=account_id, response=payload))
        return tuple(results)

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
        if order.order_type == OrderType.MARKET:
            request: dict[str, object] = {
                "symbol": order.symbol,
                "qty": order.quantity,
                "side": self._alpaca_side(order.side),
                "type": "market",
                "time_in_force": order.time_in_force.value,
                "client_order_id": order.client_order_id,
            }
        elif order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise AlpacaBrokerError(
                    "missing_limit_price",
                    "limit order translation requires limit_price",
                    context={"order_id": str(order.order_id)},
                )
            request = {
                "symbol": order.symbol,
                "qty": order.quantity,
                "side": self._alpaca_side(order.side),
                "type": "limit",
                "time_in_force": order.time_in_force.value,
                "limit_price": order.limit_price,
                "client_order_id": order.client_order_id,
            }
        else:
            raise AlpacaBrokerError(
                "unsupported_order_type",
                f"Alpaca skeleton supports market and limit orders only, got {order.order_type.value}",
                context={"order_id": str(order.order_id), "order_type": order.order_type.value},
            )
        if order.extended_hours:
            request["extended_hours"] = True
        return request

    def to_alpaca_order_request(self, order: InternalOrder) -> Any:
        request = self.translate_order_request(order)
        if order.order_type == OrderType.MARKET:
            self._require_sdk_class(MarketOrderRequest, "MarketOrderRequest")
            return MarketOrderRequest(  # type: ignore[misc,operator]
                symbol=request["symbol"],
                qty=request["qty"],
                side=self._enum_value(AlpacaOrderSide, str(request["side"])),
                time_in_force=self._enum_value(AlpacaTimeInForce, str(request["time_in_force"])),
                client_order_id=request["client_order_id"],
            )
        if order.order_type == OrderType.LIMIT:
            self._require_sdk_class(LimitOrderRequest, "LimitOrderRequest")
            return LimitOrderRequest(  # type: ignore[misc,operator]
                symbol=request["symbol"],
                qty=request["qty"],
                side=self._enum_value(AlpacaOrderSide, str(request["side"])),
                time_in_force=self._enum_value(AlpacaTimeInForce, str(request["time_in_force"])),
                limit_price=request["limit_price"],
                client_order_id=request["client_order_id"],
            )
        raise AlpacaBrokerError("unsupported_order_type", f"Unsupported Alpaca order type: {order.order_type.value}")

    def normalize_status(self, status: object) -> BrokerOrderStatus:
        normalized = self._status_token(status)
        mapping = {
            "new": BrokerOrderStatus.ACCEPTED,
            "accepted": BrokerOrderStatus.ACCEPTED,
            "pending_new": BrokerOrderStatus.ACCEPTED,
            "accepted_for_bidding": BrokerOrderStatus.ACCEPTED,
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
            "done_for_day": BrokerOrderStatus.ACCEPTED,
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
            cash=self._float(response.get("cash"), default=0),
            equity=self._float(response.get("equity"), default=0),
            trading_blocked=bool(response.get("trading_blocked", False)),
            account_blocked=bool(response.get("account_blocked", False)),
            is_pattern_day_trader=bool(response.get("pattern_day_trader", False)),
            account_status=str(response.get("status", "unknown")),
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

    def _build_trading_client(self, *, load_env: bool) -> Any:
        if load_env:
            load_dotenv()
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        base_url = os.getenv("ALPACA_BASE_URL")
        if not api_key or not secret_key:
            raise AlpacaBrokerError("missing_credentials", "ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
        if TradingClient is None:
            raise AlpacaBrokerError("missing_sdk", "alpaca-py is required for real Alpaca paper execution")
        kwargs: dict[str, object] = {"paper": True}
        if base_url:
            kwargs["url_override"] = base_url
        return TradingClient(api_key, secret_key, **kwargs)  # type: ignore[misc,operator]

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
        if value is None:
            return None
        return float(value)

    def _optional_datetime(self, value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _require_sdk_class(self, sdk_class: object, name: str) -> None:
        if sdk_class is None:
            raise AlpacaBrokerError("missing_sdk", f"alpaca-py {name} is required")

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
            "rejected_reason",
            "reject_reason",
            "reject_code",
            "buying_power",
            "cash",
            "equity",
            "daytrading_buying_power",
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

    def _synthetic_order_from_response(self, response: dict[str, Any], *, account_id: UUID) -> InternalOrder:
        now = utc_now()
        return InternalOrder(
            order_id=UUID(int=0),
            client_order_id=str(response["client_order_id"]),
            account_id=account_id,
            deployment_id=UUID(int=0),
            program_id=UUID(int=0),
            symbol=str(response.get("symbol", "UNKNOWN")).upper(),
            side=CandidateSide.LONG,
            quantity=self._float(response.get("qty"), default=self._float(response.get("filled_qty"), default=0) or 1),
            order_type=OrderType.MARKET,
            time_in_force="day",
            intent="open",
            status="created",
            created_at=now,
            updated_at=now,
        )

    def _normalize_exception(self, exc: Exception) -> AlpacaBrokerError:
        message = str(exc)
        lowered = message.lower()
        if "auth" in lowered or "unauthorized" in lowered or "forbidden" in lowered:
            return AlpacaBrokerError("auth_error", message, retryable=False)
        if "buying power" in lowered or "insufficient" in lowered:
            return AlpacaBrokerError("insufficient_buying_power", message, retryable=False)
        if "validation" in lowered or "invalid" in lowered:
            return AlpacaBrokerError("validation_error", message, retryable=False)
        return AlpacaBrokerError("network_error", message, retryable=True)
