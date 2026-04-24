from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from backend.app.domain._base import utc_now

from .alpaca import AlpacaBrokerAdapter, AlpacaBrokerError
from .models import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)


BrokerStreamEvent = BrokerOrderUpdateEvent | BrokerFillUpdateEvent | BrokerPositionSnapshot | BrokerAccountSnapshot


class AlpacaAccountStreamAdapter:
    """Normalize Alpaca account stream payloads into broker sync events."""

    provider = "alpaca"

    def __init__(
        self,
        *,
        account_id: UUID,
        mode: BrokerAccountMode = BrokerAccountMode.PAPER,
        stream_client: Any | None = None,
        normalizer: AlpacaBrokerAdapter | None = None,
    ) -> None:
        self.account_id = account_id
        self.mode = mode
        self._stream_client = stream_client
        self._normalizer = normalizer

    def subscribe(self, emit: Callable[[BrokerStreamEvent], None]) -> None:
        if self._stream_client is None:
            raise AlpacaBrokerError("missing_stream_client", "Alpaca stream client is required for streaming")
        if hasattr(self._stream_client, "subscribe_trade_updates"):
            self._stream_client.subscribe_trade_updates(lambda payload: self._emit_normalized(payload, emit))
        if hasattr(self._stream_client, "subscribe_account_updates"):
            self._stream_client.subscribe_account_updates(lambda payload: self._emit_normalized(payload, emit))
        if hasattr(self._stream_client, "subscribe_position_updates"):
            self._stream_client.subscribe_position_updates(lambda payload: self._emit_normalized(payload, emit))

    def normalize(self, payload: object) -> tuple[BrokerStreamEvent, ...]:
        data = self._response_to_dict(payload)
        event_type = str(data.get("event") or data.get("type") or data.get("stream") or "").lower()
        if "order" in data or event_type in {"new", "fill", "partial_fill", "canceled", "rejected", "trade_updates"}:
            order_event = self._order_update(data)
            events: list[BrokerStreamEvent] = [order_event]
            if order_event.status in {BrokerOrderStatus.PARTIAL_FILL, BrokerOrderStatus.FILLED} and order_event.filled_quantity > 0:
                events.append(self._fill_update(data, order_event=order_event))
            return tuple(events)
        if "buying_power" in data or "equity" in data:
            return (self._account_update(data),)
        if "symbol" in data and ("qty" in data or "market_value" in data):
            return (self._position_update(data),)
        return ()

    def _emit_normalized(self, payload: object, emit: Callable[[BrokerStreamEvent], None]) -> None:
        for event in self.normalize(payload):
            emit(event)

    def _order_update(self, data: dict[str, Any]) -> BrokerOrderUpdateEvent:
        order = self._response_to_dict(data.get("order") or data)
        event_at = self._optional_datetime(data.get("timestamp") or data.get("event_at") or order.get("updated_at")) or utc_now()
        return BrokerOrderUpdateEvent(
            account_id=self.account_id,
            client_order_id=str(order.get("client_order_id") or ""),
            status=self._normalize_status(data.get("event") or order.get("status") or ""),
            broker_order_id=str(order["id"]) if order.get("id") is not None else None,
            broker_status=str(order.get("status") or data.get("event") or ""),
            filled_quantity=self._float(order.get("filled_qty") or data.get("filled_qty"), default=0),
            filled_avg_price=self._optional_float(order.get("filled_avg_price") or data.get("price")),
            remaining_quantity=self._optional_float(order.get("remaining_qty")),
            reason=self._optional_str(order.get("rejected_reason") or order.get("reject_reason")),
            event_at=event_at,
            submitted_at=self._optional_datetime(order.get("submitted_at")),
            updated_at=self._optional_datetime(order.get("updated_at")),
            filled_at=self._optional_datetime(order.get("filled_at")),
            canceled_at=self._optional_datetime(order.get("canceled_at")),
            reject_code=self._optional_str(order.get("reject_code")),
            raw_status=str(data.get("event") or order.get("status") or ""),
            broker_reference=str(order["id"]) if order.get("id") is not None else None,
        )

    def _fill_update(self, data: dict[str, Any], *, order_event: BrokerOrderUpdateEvent) -> BrokerFillUpdateEvent:
        order = self._response_to_dict(data.get("order") or data)
        return BrokerFillUpdateEvent(
            account_id=self.account_id,
            client_order_id=order_event.client_order_id,
            symbol=str(order.get("symbol", "UNKNOWN")).upper(),
            qty=self._float(data.get("qty") or data.get("filled_qty") or order_event.filled_quantity, default=0),
            price=self._float(data.get("price") or order.get("filled_avg_price"), default=0),
            side=str(order.get("side", "unknown")).lower(),
            broker_order_id=order_event.broker_order_id,
            broker_execution_id=self._optional_str(data.get("execution_id") or data.get("id")),
            event_at=order_event.event_at,
        )

    def _position_update(self, data: dict[str, Any]) -> BrokerPositionSnapshot:
        qty = self._float(data.get("qty"), default=0)
        return BrokerPositionSnapshot(
            account_id=self.account_id,
            symbol=str(data["symbol"]).upper(),
            qty=qty,
            side=BrokerPositionSide.LONG if qty >= 0 else BrokerPositionSide.SHORT,
            avg_entry_price=self._float(data.get("avg_entry_price"), default=0),
            market_value=self._float(data.get("market_value"), default=0),
            unrealized_pl=self._float(data.get("unrealized_pl"), default=0),
            timestamp=self._optional_datetime(data.get("timestamp") or data.get("updated_at")) or utc_now(),
        )

    def _account_update(self, data: dict[str, Any]) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id=self.account_id,
            provider=self.provider,
            mode=self.mode,
            buying_power=self._float(data.get("buying_power"), default=0),
            daytrading_buying_power=self._float(data.get("daytrading_buying_power"), default=0),
            cash=self._float(data.get("cash"), default=0),
            equity=self._float(data.get("equity"), default=0),
            trading_blocked=bool(data.get("trading_blocked", False)),
            account_blocked=bool(data.get("account_blocked", False)),
            is_pattern_day_trader=bool(data.get("pattern_day_trader", False)),
            account_status=str(data.get("status", "unknown")),
            shorting_enabled=bool(data.get("shorting_enabled", False)),
            timestamp=self._optional_datetime(data.get("timestamp") or data.get("updated_at")) or utc_now(),
        )

    def _normalize_status(self, status: object) -> BrokerOrderStatus:
        if self._normalizer is not None:
            return self._normalizer.normalize_status(status)
        token = str(getattr(status, "value", status)).lower()
        mapping = {
            "new": BrokerOrderStatus.ACCEPTED,
            "accepted": BrokerOrderStatus.ACCEPTED,
            "fill": BrokerOrderStatus.FILLED,
            "filled": BrokerOrderStatus.FILLED,
            "partial_fill": BrokerOrderStatus.PARTIAL_FILL,
            "partially_filled": BrokerOrderStatus.PARTIAL_FILL,
            "canceled": BrokerOrderStatus.CANCELED,
            "cancelled": BrokerOrderStatus.CANCELED,
            "rejected": BrokerOrderStatus.REJECTED,
            "expired": BrokerOrderStatus.EXPIRED,
        }
        try:
            return mapping[token]
        except KeyError as exc:
            raise AlpacaBrokerError("unknown_stream_order_status", f"Unknown Alpaca stream order status: {status}") from exc

    def _response_to_dict(self, response: object) -> dict[str, Any]:
        if isinstance(response, dict):
            return dict(response)
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        if isinstance(response, Iterable) and not isinstance(response, (str, bytes)):
            return dict(response)
        return {
            key: getattr(response, key)
            for key in dir(response)
            if not key.startswith("_") and not callable(getattr(response, key))
        }

    def _float(self, value: object, *, default: float) -> float:
        if value is None or value == "":
            return default
        return float(value)

    def _optional_float(self, value: object) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    def _optional_datetime(self, value: object) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)
