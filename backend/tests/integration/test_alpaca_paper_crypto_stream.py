"""Opt-in real-network test: paper crypto order → trade-update stream → TradeLedger.

This test submits a tiny paper BTC/USD market order against Alpaca paper,
runs the alpaca-py ``TradingStream`` in a background thread, and verifies
the fill event lands in the canonical ``TradeLedger`` and updates broker
sync freshness — without depending on equity market hours.

Skipped by default. To run:

    set RUN_ALPACA_PAPER_CRYPTO_STREAM=1
    set ALPACA_API_KEY=...
    set ALPACA_SECRET_KEY=...
    set ALPACA_BASE_URL=https://paper-api.alpaca.markets
    pytest backend/tests/integration/test_alpaca_paper_crypto_stream.py -v -s

The order is sized at $1 of BTC notional to keep paper exposure trivial.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False

from backend.app.brokers import (
    AlpacaAccountStreamAdapter,
    AlpacaBrokerAdapter,
    BrokerStreamRouter,
    BrokerStreamRunner,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.orders import (
    InternalOrderIntent,
    InternalOrderStatus,
    OrderManager,
    TradeLedger,
)
from backend.tests.fixtures.legacy_intent import LegacyExecutionIntent as ExecutionIntent


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.alpaca_paper,
    pytest.mark.skipif(
        os.getenv("RUN_ALPACA_PAPER_CRYPTO_STREAM") != "1",
        reason="set RUN_ALPACA_PAPER_CRYPTO_STREAM=1 to drive the real Alpaca paper trade-update stream",
    ),
]


def test_paper_crypto_market_order_fills_through_trade_update_stream() -> None:
    load_dotenv()
    _require_paper_environment()
    account_id = _account_id()

    order_manager = OrderManager()
    trade_ledger = TradeLedger()
    adapter = AlpacaBrokerAdapter()
    broker_sync = BrokerSync(ledger=order_manager.ledger, adapter=adapter, provider="alpaca")
    sync_service = BrokerSyncService(
        adapter=adapter,
        broker_sync=broker_sync,
        order_ledger=order_manager.ledger,
        trade_ledger=trade_ledger,
    )
    order_manager.attach_broker_sync_service(sync_service)
    sync_service.record_successful_poll(account_id)

    stream_client = adapter.build_trading_stream()
    stream_adapter = AlpacaAccountStreamAdapter(
        account_id=account_id,
        stream_client=stream_client,
        normalizer=adapter,
    )
    router = BrokerStreamRouter(sync_service)
    router.attach(stream_adapter)

    runner = BrokerStreamRunner(stream_client)
    runner.start()
    try:
        # Allow the WebSocket to connect before submitting the order.
        time.sleep(2.0)

        intent = ExecutionIntent(
            deployment_id=uuid4(),
            program_version_id=uuid4(),
            symbol="BTC/USD",
            side=CandidateSide.LONG,
            intent_type=IntentType.ENTRY,
            qty=0.0001,  # ~$10 notional at $100k BTC; paper-only, low exposure.
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,  # crypto requires GTC, not DAY.
            timestamp=datetime.now(timezone.utc),
            signal_name="paper-crypto-stream-smoke",
            reason="opt-in integration test",
            governor_approved=True,
            governor_reason="opt-in integration test",
        )
        order = order_manager.create_order(account_id=account_id, execution_intent=intent)
        broker_result = adapter.submit_order(order)
        sync_service.record_successful_poll(account_id, at=broker_result.received_at)
        broker_sync.apply_result(broker_result)

        # Wait up to 15 s for at least one fill event to land via the stream.
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if trade_ledger.by_client_order_id(order.client_order_id):
                break
            time.sleep(0.25)

        trades_for_order = trade_ledger.by_client_order_id(order.client_order_id)
        assert trades_for_order, "expected at least one Trade for the BTC/USD order via stream"

        final = order_manager.ledger.get(order.order_id)
        assert final.status in {InternalOrderStatus.FILLED, InternalOrderStatus.PARTIALLY_FILLED}
        assert final.filled_quantity > 0
        assert sync_service.current_sync_state(account_id).is_stale is False
    finally:
        runner.stop(timeout=5.0)


def _require_paper_environment() -> None:
    if os.getenv("ALPACA_BASE_URL") != PAPER_BASE_URL:
        pytest.skip("ALPACA_BASE_URL must equal https://paper-api.alpaca.markets")
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        pytest.skip("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
    try:
        import alpaca  # noqa: F401
        from alpaca.trading.stream import TradingStream  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"alpaca-py is required: {exc}")


def _account_id() -> UUID:
    raw = os.getenv("UTOS_BROKER_ACCOUNT_ID")
    if not raw:
        return DEFAULT_ACCOUNT_ID
    return UUID(raw)
