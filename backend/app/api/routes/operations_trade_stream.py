"""Operations Center — live trade-update stream surface.

Surfaces Alpaca's paper account ``TradingStream`` to the operator UI so
order submits/cancels/fills/account-equity changes flow into the
Operations Center as they happen — no waiting for poll cycles.

This route is a *viewer*: it does not feed events into
``BrokerSyncService`` or ``OrderManager``. Those updates are owned by
the broker runtime supervisor when a real deployment is running.
Operations Center just observes whatever the paper account does — even
weekends, since trade-update events fire whenever the account has
activity, regardless of equity market hours.

Account-derived routing:
- ``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY`` are the paper credentials.
- The Alpaca *trading* stream is always paper here (paper account =
  Alpaca's "test" account in their docs).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from backend.app.brokers import (
    AlpacaAccountStreamAdapter,
    AlpacaBrokerAdapter,
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOrderUpdateEvent,
    BrokerPositionSnapshot,
    BrokerStreamRunner,
)


try:  # pragma: no cover - exercised when FastAPI is installed.
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    WebSocket = None  # type: ignore[assignment]
    WebSocketDisconnect = None  # type: ignore[assignment]


class OperationsTradeStreamHealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    streaming_enabled: bool
    account_provider: str
    websocket_path: str


@dataclass(frozen=True)
class OperationsTradeStreamConfig:
    streaming_enabled: bool

    @classmethod
    def from_env(cls) -> "OperationsTradeStreamConfig":
        has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
        return cls(streaming_enabled=has_creds)


def serialize_order_event(event: BrokerOrderUpdateEvent) -> dict[str, Any]:
    return {
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
        "buying_power": event.buying_power,
        "cash": event.cash,
        "equity": event.equity,
        "trading_blocked": event.trading_blocked,
        "account_status": event.account_status,
        "timestamp": event.timestamp.isoformat(),
    }


def serialize_position_snapshot(event: BrokerPositionSnapshot) -> dict[str, Any]:
    return {
        "symbol": event.symbol,
        "qty": event.qty,
        "side": event.side.value,
        "avg_entry_price": event.avg_entry_price,
        "market_value": event.market_value,
        "unrealized_pl": event.unrealized_pl,
        "timestamp": event.timestamp.isoformat(),
    }


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/operations", tags=["operations"])
else:
    router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


@router.get("/trade-stream/health", response_model=OperationsTradeStreamHealthResponse)
def operations_trade_stream_health() -> OperationsTradeStreamHealthResponse:
    config = OperationsTradeStreamConfig.from_env()
    return OperationsTradeStreamHealthResponse(
        streaming_enabled=config.streaming_enabled,
        account_provider="alpaca_paper",
        websocket_path="/api/v1/operations/trade-stream",
    )


if APIRouter is not None:  # pragma: no cover - WebSocket only registers with real FastAPI.

    @router.websocket("/trade-stream")
    async def operations_trade_stream(websocket: WebSocket) -> None:
        await websocket.accept()
        config = OperationsTradeStreamConfig.from_env()

        if not config.streaming_enabled:
            await websocket.send_text(json.dumps({"type": "error", "code": "missing_credentials"}))
            await websocket.close()
            return

        from uuid import UUID
        from backend.app.runtime.runtime_context import trade_dispatcher_registry

        loop = asyncio.get_running_loop()
        ws_open = True

        def emit(payload: dict[str, Any]) -> None:
            if not ws_open:
                return
            try:
                asyncio.run_coroutine_threadsafe(websocket.send_text(json.dumps(payload)), loop)
            except Exception:  # noqa: BLE001 - loop closed mid-shutdown
                pass

        def make_on_event(account_id: UUID) -> Any:
            def on_event(event: object) -> None:
                envelope = {"account_id": str(account_id)}
                if isinstance(event, BrokerOrderUpdateEvent):
                    emit({"type": "order_event", "data": serialize_order_event(event), **envelope})
                elif isinstance(event, BrokerFillUpdateEvent):
                    emit({"type": "fill_event", "data": serialize_fill_event(event), **envelope})
                elif isinstance(event, BrokerAccountSnapshot):
                    emit({"type": "account_snapshot", "data": serialize_account_snapshot(event), **envelope})
                elif isinstance(event, BrokerPositionSnapshot):
                    emit({"type": "position_snapshot", "data": serialize_position_snapshot(event), **envelope})
            return on_event

        # ?account_id=... subscribes to one Account's dispatcher; omitted
        # subscribes to every running dispatcher (fan-out across accounts).
        registry = trade_dispatcher_registry()
        requested_account_param = websocket.query_params.get("account_id")
        target_dispatchers: list[tuple[UUID, Any, str]] = []
        if requested_account_param:
            try:
                requested_account = UUID(requested_account_param)
            except ValueError:
                await websocket.send_text(json.dumps({"type": "error", "code": "invalid_account_id"}))
                await websocket.close()
                return
            dispatcher = registry.get(requested_account)
            if dispatcher is None:
                await websocket.send_text(json.dumps({"type": "error", "code": "unknown_account_id"}))
                await websocket.close()
                return
            sub_id = dispatcher.subscribe(make_on_event(requested_account))
            target_dispatchers.append((requested_account, dispatcher, sub_id))
        else:
            for dispatcher in registry.all():
                sub_id = dispatcher.subscribe(make_on_event(dispatcher.account_id))
                target_dispatchers.append((dispatcher.account_id, dispatcher, sub_id))

        try:
            await websocket.send_text(json.dumps({
                "type": "ready",
                "account_provider": "alpaca_paper",
                "account_ids": [str(aid) for aid, _, _ in target_dispatchers],
            }))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            try:
                await websocket.send_text(json.dumps({"type": "error", "code": "stream_error", "message": str(exc)}))
            except Exception:  # noqa: BLE001
                pass
        finally:
            ws_open = False
            for _, dispatcher, sub_id in target_dispatchers:
                try:
                    dispatcher.unsubscribe(sub_id)
                except Exception:  # noqa: BLE001
                    pass
