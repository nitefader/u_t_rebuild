from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.governor import BrokerSyncFreshness, GovernorRequest, PortfolioGovernor, PortfolioSnapshot
from backend.app.orders import OrderManager
from backend.app.runtime import ExecutionIntent, RuntimeState


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_DEPLOYMENT_ID = UUID("00000000-0000-0000-0000-000000000002")
DEFAULT_PROGRAM_ID = UUID("00000000-0000-0000-0000-000000000003")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit exactly one safe Alpaca paper market order.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--qty", type=float, default=1)
    args = parser.parse_args(argv)

    _print_step("Loading .env")
    load_dotenv()
    _print_step("Validating paper-order environment guards")
    error = _validate_environment(qty=args.qty)
    if error is not None:
        print(json.dumps({"ok": False, "error": error}), file=sys.stderr, flush=True)
        return 2

    account_id = _account_id()
    _print_step("Creating Governor-approved test ExecutionIntent")
    intent = _approved_execution_intent(
        account_id=account_id,
        symbol=args.symbol.upper(),
        qty=args.qty,
    )
    _print_step("Creating AlpacaBrokerAdapter")
    adapter = AlpacaBrokerAdapter()
    _print_step("Checking Alpaca market clock")
    if not _market_is_open(adapter):
        print("Market closed. No order submitted.", flush=True)
        return 0
    _print_step("Creating OrderManager")
    order_manager = OrderManager()
    _print_step("Creating BrokerSync")
    broker_sync = BrokerSync(ledger=order_manager.ledger, adapter=adapter)

    _print_step("Creating internal order via OrderManager")
    order = order_manager.create_order(account_id=account_id, execution_intent=intent)
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
                    "deployment_id": str(ledger_update.deployment_id),
                    "program_id": str(ledger_update.program_id),
                },
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _validate_environment(*, qty: float) -> str | None:
    if os.getenv("ALPACA_BASE_URL") != PAPER_BASE_URL:
        return "ALPACA_BASE_URL must equal https://paper-api.alpaca.markets"
    if os.getenv("CONFIRM_PAPER_ORDER") != "yes":
        return "CONFIRM_PAPER_ORDER=yes is required"
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


def _approved_execution_intent(*, account_id: UUID, symbol: str, qty: float) -> ExecutionIntent:
    intent = ExecutionIntent(
        deployment_id=DEFAULT_DEPLOYMENT_ID,
        program_version_id=DEFAULT_PROGRAM_ID,
        symbol=symbol,
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        qty=qty,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime.now(timezone.utc),
        signal_name="manual_paper_smoke",
        reason="operator_confirmed_paper_smoke",
    )
    governor = PortfolioGovernor()
    decision = governor.evaluate(
        GovernorRequest(
            account_id=account_id,
            execution_intent=intent,
            runtime_state=RuntimeState(deployment_id=intent.deployment_id),
            broker_sync=BrokerSyncFreshness(),
            portfolio=PortfolioSnapshot(),
        )
    )
    if not decision.approved:
        raise RuntimeError(f"paper smoke intent rejected by governor: {decision.reason}")
    return intent.model_copy(update={"governor_approved": True, "governor_reason": decision.reason})


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
