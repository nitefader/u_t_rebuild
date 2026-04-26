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

        loop = asyncio.get_running_loop()

        def emit(payload: dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(websocket.send_text(json.dumps(payload)), loop)

        broker_adapter = AlpacaBrokerAdapter()
        trading_stream_client = broker_adapter.build_trading_stream()
        # Operations Center tags events with a fresh viewer id; it does not
        # mutate the system's BrokerAccount registry.
        viewer_account_id = uuid4()
        stream_adapter = AlpacaAccountStreamAdapter(
            account_id=viewer_account_id,
            stream_client=trading_stream_client,
            normalizer=broker_adapter,
        )

        def on_event(event: object) -> None:
            if isinstance(event, BrokerOrderUpdateEvent):
                emit({"type": "order_event", "data": serialize_order_event(event)})
            elif isinstance(event, BrokerFillUpdateEvent):
                emit({"type": "fill_event", "data": serialize_fill_event(event)})
            elif isinstance(event, BrokerAccountSnapshot):
                emit({"type": "account_snapshot", "data": serialize_account_snapshot(event)})
            elif isinstance(event, BrokerPositionSnapshot):
                emit({"type": "position_snapshot", "data": serialize_position_snapshot(event)})

        stream_adapter.subscribe(on_event)
        runner = BrokerStreamRunner(trading_stream_client)

        try:
            runner.start()
            await websocket.send_text(json.dumps({"type": "ready", "account_provider": "alpaca_paper"}))
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
            await loop.run_in_executor(None, runner.stop)
