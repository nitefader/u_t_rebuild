from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv() -> bool:
        return False

from backend.app.brokers import AlpacaBrokerAdapter, BrokerSync
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.governor import BrokerSyncFreshness, PortfolioSnapshot, PositionSummary
from backend.app.orders import OrderManager
from backend.app.pipeline import RuntimeOrchestrator
from backend.app.runtime import DeploymentContext


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_DEPLOYMENT_ID = UUID("00000000-0000-0000-0000-000000000102")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one controlled account runtime pass.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--bars", type=int, default=5)
    parser.add_argument("--qty", type=int, default=1)
    args = parser.parse_args(argv)

    _print_step("Loading .env")
    load_dotenv()
    _print_step("Validating account runtime guards")
    error = _validate_environment(bars=args.bars, qty=args.qty)
    if error is not None:
        print(json.dumps({"ok": False, "error": error}), file=sys.stderr, flush=True)
        return 2

    symbol = args.symbol.upper()
    account_id = _account_id()
    _print_step("Creating AlpacaBrokerAdapter")
    adapter = AlpacaBrokerAdapter()
    _print_step("Checking Alpaca market clock")
    if not _market_is_open(adapter):
        print("Market closed. No runtime executed.", flush=True)
        return 0

    _print_step("Creating OrderManager")
    order_manager = OrderManager()
    _print_step("Creating BrokerSync")
    broker_sync = BrokerSync(ledger=order_manager.ledger, adapter=adapter)
    _print_step("Syncing account and positions")
    account_snapshot = broker_sync.sync_account(account_id)
    position_snapshots = broker_sync.sync_positions(account_id)

    _print_step("Creating Deployment context")
    components = _components(symbol=symbol, qty=args.qty)
    deployment = DeploymentContext(
        deployment_id=DEFAULT_DEPLOYMENT_ID,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
        mode="runtime_smoke",
    )
    broker_freshness = BrokerSyncFreshness(last_synced_at=account_snapshot.last_synced_at)
    portfolio_snapshot = _portfolio_snapshot(
        account_id=account_id,
        deployment_id=deployment.deployment_id,
        program_id=components.strategy.id,
        positions=position_snapshots,
    )
    _print_step("Creating RuntimeOrchestrator")
    orchestrator = RuntimeOrchestrator(
        account_id=account_id,
        deployment=deployment,
        components=components,
        order_manager=order_manager,
        broker_adapter=adapter,
        broker_sync=broker_sync,
        broker_freshness=broker_freshness,
        portfolio_snapshot=portfolio_snapshot,
    )

    _print_step(f"Processing up to {args.bars} completed bars for {symbol}")
    all_events: list[dict[str, object]] = []
    orders_created = 0
    for bar in _generated_completed_bars(symbol=symbol, count=args.bars):
        result = orchestrator.process_bar(bar)
        all_events = [_event_payload(event) for event in result.events]
        orders_created += len(result.orders)
        if orders_created >= 1:
            _print_step("Max one order reached; stopping runtime pass")
            break

    _print_step("Printing runtime result")
    print(
        json.dumps(
            {
                "ok": True,
                "symbol": symbol,
                "bars_requested": args.bars,
                "orders_created": orders_created,
                "events": all_events,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def _validate_environment(*, bars: int, qty: int) -> str | None:
    if os.getenv("ALPACA_BASE_URL") != PAPER_BASE_URL:
        return "ALPACA_BASE_URL must equal https://paper-api.alpaca.markets"
    if os.getenv("CONFIRM_PAPER_RUNTIME") != "yes":
        return "CONFIRM_PAPER_RUNTIME=yes is required"
    if bars <= 0:
        return "bars must be greater than 0"
    if bars > 20:
        return "bars > 20 is blocked by controlled account runtime"
    if qty <= 0:
        return "qty must be greater than 0"
    if qty > 1:
        return "qty > 1 is blocked by controlled account runtime"
    if not os.getenv("ALPACA_API_KEY") or not os.getenv("ALPACA_SECRET_KEY"):
        return "ALPACA_API_KEY and ALPACA_SECRET_KEY are required"
    return None


def _account_id() -> UUID:
    raw = os.getenv("UTOS_BROKER_ACCOUNT_ID")
    if not raw:
        return DEFAULT_ACCOUNT_ID
    return UUID(raw)


def _market_is_open(adapter: AlpacaBrokerAdapter) -> bool:
    clock = adapter.get_market_clock()
    return bool(clock.get("is_open", False))


def _components(*, symbol: str, qty: int) -> ResolvedDeploymentComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Runtime Smoke Strategy",
        entry_rules=[
            SignalRule(
                name="close_above_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
                ),
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="5m Regular Controls",
        timeframe="5m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Runtime Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=qty,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Runtime Market",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Runtime Universe",
        symbols=[UniverseSymbol(symbol=symbol)],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Runtime Strategy Version",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedDeploymentComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _portfolio_snapshot(
    *,
    account_id: UUID,
    deployment_id: UUID,
    program_id: UUID,
    positions: tuple[object, ...],
) -> PortfolioSnapshot:
    summaries = []
    for position in positions:
        summaries.append(
            PositionSummary(
                account_id=account_id,
                deployment_id=deployment_id,
                program_id=program_id,
                symbol=str(getattr(position, "symbol")),
                quantity=float(getattr(position, "quantity")),
                market_value=float(getattr(position, "market_value")),
            )
        )
    # W2-A-1b (audit P0 #2 — pre-T-7 bundle, operator decision 2026-04-30):
    # Smoke-test snapshot must carry a non-None equity so the new
    # portfolio_equity_unavailable Governor rule does not pre-empt the
    # smoke flow. Production wires real equity from BrokerSync account
    # snapshots; the smoke tool stands in with a fixed 100k baseline.
    return PortfolioSnapshot(equity=100_000, positions=tuple(summaries))


def _generated_completed_bars(*, symbol: str, count: int) -> tuple[NormalizedBar, ...]:
    start = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=5 * count)
    bars: list[NormalizedBar] = []
    for index in range(count):
        open_price = 100 + index
        close_price = open_price + 1
        bars.append(
            NormalizedBar(
                symbol=symbol,
                timeframe="5m",
                timestamp=start + timedelta(minutes=5 * index),
                open=open_price,
                high=close_price + 0.25,
                low=open_price - 0.25,
                close=close_price,
                volume=100_000 + index,
            )
        )
    return tuple(bars)


def _event_payload(event) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "sequence": event.sequence,
        "timestamp": event.timestamp.isoformat(),
        "event_type": event.event_type.value,
        "symbol": event.symbol,
        "message": event.message,
        "details": event.details,
    }


def _print_step(message: str) -> None:
    print(f"[run_runtime_smoke] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
