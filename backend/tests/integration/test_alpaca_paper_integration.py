from __future__ import annotations

import os
from uuid import UUID

import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False

from backend.app.brokers import AlpacaBrokerAdapter, AlpacaBrokerError


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


pytestmark = [
    pytest.mark.integration,
    pytest.mark.alpaca_paper,
    pytest.mark.skipif(
        os.getenv("RUN_ALPACA_PAPER_INTEGRATION") != "1",
        reason="set RUN_ALPACA_PAPER_INTEGRATION=1 to run real Alpaca paper integration checks",
    ),
]


def test_alpaca_paper_read_only_polling_integration() -> None:
    """Opt-in real Alpaca paper check.

    This test intentionally performs read-only polling only. Paper order
    submission remains out of normal pytest runs and out of the default
    opt-in integration path.
    """

    load_dotenv()
    _require_paper_environment()
    account_id = _account_id()
    adapter = AlpacaBrokerAdapter()

    clock = adapter.get_market_clock()
    account = adapter.get_account_snapshot(account_id)
    positions = adapter.get_positions(account_id)
    open_orders = adapter.list_open_orders(account_id)

    assert isinstance(clock, dict)
    assert account.account_id == account_id
    assert account.provider == "alpaca"
    assert account.buying_power >= 0
    assert all(position.account_id == account_id for position in positions)
    assert all(order.account_id == account_id for order in open_orders)


def _require_paper_environment() -> None:
    if os.getenv("ALPACA_BASE_URL") != PAPER_BASE_URL:
        pytest.skip("ALPACA_BASE_URL must equal https://paper-api.alpaca.markets")
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        pytest.skip("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
    try:
        import alpaca  # noqa: F401
    except ImportError as exc:
        pytest.skip(f"alpaca-py is required for real integration checks: {exc}")


def _account_id() -> UUID:
    raw = os.getenv("UTOS_BROKER_ACCOUNT_ID")
    if not raw:
        return DEFAULT_ACCOUNT_ID
    try:
        return UUID(raw)
    except ValueError as exc:
        raise AlpacaBrokerError("invalid_account_id", "UTOS_BROKER_ACCOUNT_ID must be a UUID") from exc
