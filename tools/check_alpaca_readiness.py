from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False

from backend.app.brokers import AlpacaBrokerAdapter, BrokerSync
from backend.app.brokers._paper_credentials import resolve_paper_credentials
from backend.app.domain import TradingMode
from backend.app.orders import OrderManager


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


def main(argv: list[str] | None = None) -> int:
    _ = argv
    load_dotenv()
    error = _validate_environment()
    if error is not None:
        print(json.dumps({"ok": False, "error": error}), file=sys.stderr)
        return 2

    account_id = _account_id()
    api_key, secret_key = resolve_paper_credentials()
    adapter = AlpacaBrokerAdapter(
        mode=TradingMode.BROKER_PAPER,
        api_key=api_key,
        secret_key=secret_key,
    )
    broker_sync = BrokerSync(ledger=OrderManager().ledger, adapter=adapter)
    account = broker_sync.sync_account(account_id)
    positions = broker_sync.sync_positions(account_id)
    open_orders = adapter.list_open_orders(account_id)

    print(
        json.dumps(
            {
                "ok": True,
                "account": {
                    "account_id": str(account.account_id),
                    "provider": account.provider,
                    "mode": account.mode.value,
                    "buying_power": account.buying_power,
                    "cash": account.cash,
                    "equity": account.equity,
                    "trading_blocked": account.trading_blocked,
                    "account_blocked": account.account_blocked,
                    "last_synced_at": account.last_synced_at.isoformat(),
                },
                "positions": [
                    {
                        "symbol": position.symbol,
                        "quantity": position.quantity,
                        "side": position.side.value,
                        "market_value": position.market_value,
                    }
                    for position in positions
                ],
                "open_orders": [
                    {
                        "client_order_id": order.client_order_id,
                        "broker_order_id": order.broker_order_id,
                        "status": order.status.value,
                        "filled_quantity": order.filled_quantity,
                    }
                    for order in open_orders
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _validate_environment() -> str | None:
    base_url = (os.getenv("ALPACA_BASE_URL") or "").rstrip("/")
    if not base_url.startswith(PAPER_BASE_URL):
        return f"ALPACA_BASE_URL must start with {PAPER_BASE_URL} (got: {base_url!r})"
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        return "ALPACA_API_KEY and ALPACA_SECRET_KEY are required"
    return None


def _account_id() -> UUID:
    raw = os.getenv("UTOS_BROKER_ACCOUNT_ID")
    if not raw:
        return DEFAULT_ACCOUNT_ID
    return UUID(raw)


if __name__ == "__main__":
    raise SystemExit(main())
