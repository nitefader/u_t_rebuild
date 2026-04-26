from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from backend.app.api.routes import operations_trade_stream
from backend.app.api.routes.operations_trade_stream import (
    OperationsTradeStreamHealthResponse,
    operations_trade_stream_health,
    serialize_account_snapshot,
    serialize_fill_event,
    serialize_order_event,
    serialize_position_snapshot,
)
from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.domain import TradingMode


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


def test_health_with_no_dispatchers_reports_streaming_disabled() -> None:
    from backend.app.runtime.runtime_context import shutdown_runtime_context

    shutdown_runtime_context()
    response = operations_trade_stream_health()
    assert isinstance(response, OperationsTradeStreamHealthResponse)
    assert response.streaming_enabled is False
    assert response.account_provider == "broker_account"
    assert response.requires_account_id is True
    assert "account_id" in response.websocket_path
    shutdown_runtime_context()


def test_health_with_dispatcher_reports_streaming_enabled() -> None:
    from backend.app.runtime.runtime_context import shutdown_runtime_context, trade_dispatcher_registry

    shutdown_runtime_context()
    trade_dispatcher_registry().get_or_create(ACCOUNT_ID)
    response = operations_trade_stream_health()
    assert response.streaming_enabled is True
    assert response.account_ids == (str(ACCOUNT_ID),)
    shutdown_runtime_context()


def test_serialize_order_event_emits_status_value_and_iso_timestamp() -> None:
    event = BrokerOrderUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="utos-abcd1234-open-deadbeef",
        status=BrokerOrderStatus.PARTIAL_FILL,
        broker_order_id="alp-1",
        broker_status="partially_filled",
        filled_quantity=4,
        filled_avg_price=100.5,
        remaining_quantity=6,
        event_at=datetime(2026, 4, 25, 17, 30, tzinfo=timezone.utc),
    )
    payload = serialize_order_event(event)
    assert payload["account_id"] == str(ACCOUNT_ID)
    assert payload["status"] == "partial_fill"
    assert payload["filled_quantity"] == 4
    assert payload["event_at"] == "2026-04-25T17:30:00+00:00"


def test_serialize_fill_event_includes_broker_execution_id() -> None:
    event = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="utos-abcd1234-open-deadbeef",
        symbol="SPY",
        qty=4,
        price=100.5,
        side="buy",
        broker_execution_id="exec-1",
        event_at=datetime(2026, 4, 25, 17, 30, tzinfo=timezone.utc),
    )
    payload = serialize_fill_event(event)
    assert payload["broker_execution_id"] == "exec-1"
    assert payload["qty"] == 4
    assert payload["side"] == "buy"


def test_serialize_account_snapshot_emits_equity_and_status() -> None:
    snapshot = BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        buying_power=100_000,
        cash=99_500,
        equity=100_000,
        account_status="ACTIVE",
    )
    payload = serialize_account_snapshot(snapshot)
    assert payload["equity"] == 100_000
    assert payload["account_status"] == "ACTIVE"


def test_serialize_position_snapshot_emits_side_value() -> None:
    snapshot = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=10,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=1010,
    )
    payload = serialize_position_snapshot(snapshot)
    assert payload["side"] == "long"
    assert payload["qty"] == 10


def test_router_registers_trade_stream_health_endpoint() -> None:
    paths = []
    for route in getattr(operations_trade_stream.router, "routes", []):
        path = getattr(route, "path", None) or getattr(route, "path_format", None)
        if path is not None:
            paths.append(path)
    assert any(path.endswith("/trade-stream/health") for path in paths)
