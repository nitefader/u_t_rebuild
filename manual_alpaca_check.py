from dotenv import load_dotenv
import os
from uuid import uuid4

# Load .env
load_dotenv()

from backend.app.brokers.alpaca import AlpacaBrokerAdapter

def main():
    print("=== Alpaca Adapter Smoke Test (NO TRADING) ===")

    # Basic env check
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_SECRET_KEY")
    base = os.getenv("ALPACA_BASE_URL")

    if not key or not secret or not base:
        raise RuntimeError("Missing Alpaca env vars. Check .env")

    print(f"Using BASE_URL: {base}")

    # Instantiate adapter
    adapter = AlpacaBrokerAdapter()
    print("Adapter instantiated")

    # Use a placeholder account_id if your interface requires it
    account_id = uuid4()

    # 1) Account snapshot
    print("\n--- Account Snapshot ---")
    acct = adapter.get_account_snapshot(account_id)
    print({
        "buying_power": acct.buying_power,
        "cash": acct.cash,
        "equity": acct.equity,
        "trading_blocked": acct.trading_blocked,
        "pattern_day_trader": acct.pattern_day_trader,
        "last_synced_at": str(acct.last_synced_at),
    })

    # 2) Positions
    print("\n--- Positions ---")
    positions = adapter.get_positions(account_id)
    for p in positions:
        print({
            "symbol": p.symbol,
            "qty": p.quantity,
            "avg_entry_price": p.avg_entry_price,
            "side": p.side,
            "last_synced_at": str(p.last_synced_at),
        })
    if not positions:
        print("No open positions")

    # 3) Open Orders
    print("\n--- Open Orders ---")
    orders = adapter.list_open_orders(account_id)
    for o in orders:
        print({
            "client_order_id": o.client_order_id,
            "broker_order_id": o.broker_order_id,
            "status": o.broker_status,
            "filled_qty": getattr(o, "filled_quantity", None),
            "remaining_qty": getattr(o, "remaining_quantity", None),
            "updated_at": str(o.updated_at),
        })
    if not orders:
        print("No open orders")

    print("\n=== DONE (no orders submitted) ===")


if __name__ == "__main__":
    main()