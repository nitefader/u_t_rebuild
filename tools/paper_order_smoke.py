from __future__ import annotations

import argparse
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

from backend.app.brokers import AlpacaBrokerAdapter, BrokerOrderResult, BrokerSync
from backend.app.brokers._paper_credentials import resolve_paper_credentials
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.orders import OrderManager


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit exactly one safe Alpaca paper market order.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--qty", type=float, default=1)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate environment and build the order but do not submit to the broker.",
    )
    args = parser.parse_args(argv)

    _print_step("Loading .env")
    load_dotenv()
    _print_step("Validating paper-order environment guards")
    error = _validate_environment(qty=args.qty, dry_run=args.dry_run)
    if error is not None:
        print(json.dumps({"ok": False, "error": error}), file=sys.stderr, flush=True)
        return 2

    account_id = _account_id()
    _print_step("Preparing operator-confirmed paper smoke order")
    _print_step("Creating AlpacaBrokerAdapter")
    api_key, secret_key = resolve_paper_credentials()
    adapter = AlpacaBrokerAdapter(
        mode=TradingMode.BROKER_PAPER,
        api_key=api_key,
        secret_key=secret_key,
    )

    if args.dry_run:
        _print_step("Dry-run mode: broker submit skipped")
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "symbol": args.symbol.upper(),
                    "qty": args.qty,
                    "account_id": str(account_id),
                }
            ),
            flush=True,
        )
        return 0

    _print_step("Checking Alpaca market clock")
    if not _market_is_open(adapter):
        print("Market closed. No order submitted.", flush=True)
        return 0
    _print_step("Creating OrderManager")
    order_manager = OrderManager()
    _print_step("Creating BrokerSync")
    broker_sync = BrokerSync(ledger=order_manager.ledger, adapter=adapter)

    _print_step("Creating internal order via OrderManager")
    order = order_manager.create_manual_order(
        account_id=account_id,
        symbol=args.symbol.upper(),
        side=CandidateSide.LONG,
        quantity=args.qty,
        intent="open",
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        reason="operator_confirmed_paper_smoke",
    )
    _print_step("Submitting exactly one paper market order via AlpacaBrokerAdapter")
    broker_result = adapter.submit_order(order)
    _print_step("Applying broker result via BrokerSync")
    ledger_update = broker_sync.apply_result(broker_result)

    _print_step("Printing normalized result")
    print(
        json.dumps(
            {
                "ok": True,
                "order": {
                    "order_id": str(order.order_id),
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "quantity": order.quantity,
                    "status": ledger_update.status.value,
                },
                "broker_result": _broker_result_payload(broker_result),
                "ledger_update": {
                    "status": ledger_update.status.value,
                    "filled_quantity": ledger_update.filled_quantity,
                    "account_id": str(ledger_update.account_id),
                    "deployment_id": str(ledger_update.deployment_id) if ledger_update.deployment_id else None,
                },
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _validate_environment(*, qty: float, dry_run: bool = False) -> str | None:
    base_url = (os.getenv("ALPACA_BASE_URL") or "").rstrip("/")
    if not base_url.startswith(PAPER_BASE_URL):
        return f"ALPACA_BASE_URL must start with {PAPER_BASE_URL} (got: {base_url!r})"
    if not dry_run and os.getenv("CONFIRM_PAPER_ORDER") != "yes":
        return "CONFIRM_PAPER_ORDER=yes is required (or pass --dry-run to skip submit)"
    if qty <= 0:
        return "qty must be greater than 0"
    if qty > 1:
        return "qty > 1 is blocked by paper smoke command"
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        return "ALPACA_API_KEY and ALPACA_SECRET_KEY are required"
    return None


def _account_id() -> UUID:
    raw = os.getenv("UTOS_BROKER_ACCOUNT_ID")
    if not raw:
        return DEFAULT_ACCOUNT_ID
    return UUID(raw)


def _broker_result_payload(result: BrokerOrderResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "broker_order_id": result.broker_order_id,
        "broker_status": result.broker_status,
        "filled_quantity": result.filled_quantity,
        "filled_avg_price": result.filled_avg_price,
        "remaining_quantity": result.remaining_quantity,
        "reason": result.reason,
    }


def _market_is_open(adapter: AlpacaBrokerAdapter) -> bool:
    clock = adapter.get_market_clock()
    return bool(clock.get("is_open", False))


def _print_step(message: str) -> None:
    print(f"[paper_order_smoke] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
