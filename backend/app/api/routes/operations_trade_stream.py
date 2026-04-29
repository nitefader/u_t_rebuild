"""Operations Center trade-update stream surface.

Each WebSocket subscription is account-scoped. The underlying runtime owns
one Broker Trade Update Stream per BrokerAccount; this route only bridges a
single account dispatcher to one browser connection.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOrderUpdateEvent,
    BrokerPositionSnapshot,
)


class OperationsTradeStreamHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    streaming_enabled: bool
    account_provider: str
    websocket_path: str
    account_ids: tuple[str, ...] = ()
    requires_account_id: bool = True


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def serialize_order_event(event: BrokerOrderUpdateEvent) -> dict[str, Any]:
    return {
        "account_id": str(event.account_id),
        "client_order_id": event.client_order_id,
        "broker_order_id": event.broker_order_id,
        "status": event.status.value,
        "broker_status": event.broker_status,
        "filled_quantity": event.filled_quantity,
        "filled_avg_price": event.filled_avg_price,
        "remaining_quantity": event.remaining_quantity,
        "reason": event.reason,
        "event_at": event.event_at.isoformat(),
    }


def serialize_fill_event(event: BrokerFillUpdateEvent) -> dict[str, Any]:
    return {
        "account_id": str(event.account_id),
        "client_order_id": event.client_order_id,
        "broker_order_id": event.broker_order_id,
        "broker_execution_id": event.broker_execution_id,
        "symbol": event.symbol,
        "side": event.side,
        "qty": event.qty,
        "price": event.price,
        "event_at": event.event_at.isoformat(),
    }


def serialize_account_snapshot(event: BrokerAccountSnapshot) -> dict[str, Any]:
    return {
        "account_id": str(event.account_id),
        "buying_power": event.buying_power,
        "cash": event.cash,
        "equity": event.equity,
        "trading_blocked": event.trading_blocked,
        "account_status": event.account_status,
        "timestamp": event.timestamp.isoformat(),
    }


def serialize_position_snapshot(event: BrokerPositionSnapshot) -> dict[str, Any]:
    return {
        "account_id": str(event.account_id),
        "symbol": event.symbol,
        "qty": event.qty,
        "side": event.side.value,
        "avg_entry_price": event.avg_entry_price,
        "market_value": event.market_value,
        "unrealized_pl": event.unrealized_pl,
        "timestamp": event.timestamp.isoformat(),
    }


@router.get("/trade-stream/health", response_model=OperationsTradeStreamHealthResponse)
def operations_trade_stream_health() -> OperationsTradeStreamHealthResponse:
    from backend.app.runtime.runtime_context import trade_dispatcher_registry

    account_ids = tuple(str(account_id) for account_id in trade_dispatcher_registry().account_ids())
    return OperationsTradeStreamHealthResponse(
        streaming_enabled=bool(account_ids),
        account_provider="broker_account",
        websocket_path="/api/v1/operations/trade-stream?account_id=<broker_account_id>&client_surface=operations|brokers",
        account_ids=account_ids,
        requires_account_id=True,
    )


@router.websocket("/trade-stream")
async def operations_trade_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    from backend.app.runtime.runtime_context import trade_dispatcher_registry

    requested_account_param = websocket.query_params.get("account_id")
    if not requested_account_param:
        await websocket.send_text(json.dumps({"type": "error", "code": "account_id_required"}))
        await websocket.close()
        return
    try:
        requested_account = UUID(requested_account_param)
    except ValueError:
        await websocket.send_text(json.dumps({"type": "error", "code": "invalid_account_id"}))
        await websocket.close()
        return

    dispatcher = trade_dispatcher_registry().get(requested_account)
    if dispatcher is None:
        await websocket.send_text(json.dumps({"type": "error", "code": "unknown_account_id"}))
        await websocket.close()
        return

    surface_raw = (websocket.query_params.get("client_surface") or "").strip().lower()
    client_surface = surface_raw if surface_raw in ("operations", "brokers") else None

    loop = asyncio.get_running_loop()
    ws_open = True

    def emit(payload: dict[str, Any]) -> None:
        if not ws_open:
            return
        future = asyncio.run_coroutine_threadsafe(websocket.send_text(json.dumps(payload)), loop)
        future.add_done_callback(lambda done: done.exception())

    def on_event(event: object) -> None:
        if isinstance(event, BrokerOrderUpdateEvent):
            emit({"type": "order_event", "data": serialize_order_event(event)})
        elif isinstance(event, BrokerFillUpdateEvent):
            emit({"type": "fill_event", "data": serialize_fill_event(event)})
        elif isinstance(event, BrokerAccountSnapshot):
            emit({"type": "account_snapshot", "data": serialize_account_snapshot(event)})
        elif isinstance(event, BrokerPositionSnapshot):
            emit({"type": "position_snapshot", "data": serialize_position_snapshot(event)})

    sub_id = dispatcher.subscribe(on_event, client_surface=client_surface)
    try:
        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "account_provider": "broker_account",
                    "account_id": str(requested_account),
                }
            )
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return
    finally:
        ws_open = False
        dispatcher.unsubscribe(sub_id)
