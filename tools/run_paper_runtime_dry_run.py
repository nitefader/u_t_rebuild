from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
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
from backend.app.features import NormalizedBar, ResolvedProgramComponents
from backend.app.governor import BrokerSyncFreshness, PortfolioSnapshot, PositionSummary
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataSubscription
from backend.app.orders import OrderManager
from backend.app.pipeline import RuntimeOrchestrator
from backend.app.runtime import DeploymentContext, RuntimeEngine


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DEFAULT_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_DEPLOYMENT_ID = UUID("00000000-0000-0000-0000-000000000202")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a controlled paper runtime dry-run from Alpaca market data.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--bars", type=int, default=5)
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    _print_step("Loading .env")
    load_dotenv()
    _print_step("Validating paper runtime dry-run guards")
    error = _validate_environment(bars=args.bars, qty=args.qty, execute=args.execute)
    if error is not None:
        print(json.dumps({"ok": False, "error": error}), file=sys.stderr, flush=True)
        return 2

    account_id = _account_id()
    symbol = args.symbol.upper()
    _print_step("Creating AlpacaBrokerAdapter")
    broker_adapter = AlpacaBrokerAdapter()
    _print_step("Checking Alpaca market clock")
    if not _market_is_open(broker_adapter):
        print("Market closed. No runtime executed.", flush=True)
        return 0

    try:
        subscription = MarketDataSubscription(symbol=symbol, timeframe=args.timeframe, limit=args.bars)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr, flush=True)
        return 2

    _print_step(f"Collecting up to {subscription.limit} normalized bars for {subscription.symbol}")
    bars = AlpacaMarketDataAdapter().collect_bars_sync(subscription=subscription, timeout_seconds=args.timeout)
    if not bars:
        print(json.dumps({"ok": True, "mode": _mode(args.execute), "bars_processed": 0, "orders_created": 0}), flush=True)
        return 0

    components = _components(symbol=subscription.symbol, timeframe=subscription.timeframe, qty=args.qty)
    deployment = DeploymentContext(
        deployment_id=DEFAULT_DEPLOYMENT_ID,
        program=components.program,
        mode="paper_runtime_execute" if args.execute else "paper_runtime_dry_run",
    )
    order_manager = OrderManager()
    broker_sync = BrokerSync(ledger=order_manager.ledger, adapter=broker_adapter)
    _print_step("Syncing account and positions")
    account_snapshot = broker_sync.sync_account(account_id)
    position_snapshots = broker_sync.sync_positions(account_id)
    broker_freshness = BrokerSyncFreshness(last_synced_at=account_snapshot.last_synced_at)
    portfolio_snapshot = _portfolio_snapshot(
        account_id=account_id,
        deployment_id=deployment.deployment_id,
        program_id=components.program.id,
        positions=position_snapshots,
    )

    if args.execute:
        result = _run_execute(
            account_id=account_id,
            deployment=deployment,
            components=components,
            bars=bars,
            broker_adapter=broker_adapter,
            broker_sync=broker_sync,
            order_manager=order_manager,
            broker_freshness=broker_freshness,
            portfolio_snapshot=portfolio_snapshot,
        )
    else:
        result = _run_dry(
            account_id=account_id,
            deployment=deployment,
            components=components,
            bars=bars,
            broker_freshness=broker_freshness,
            portfolio_snapshot=portfolio_snapshot,
        )

    _print_step("Printing runtime dry-run result")
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


def _run_dry(
    *,
    account_id: UUID,
    deployment: DeploymentContext,
    components: ResolvedProgramComponents,
    bars: tuple[NormalizedBar, ...],
    broker_freshness: BrokerSyncFreshness,
    portfolio_snapshot: PortfolioSnapshot,
) -> dict[str, object]:
    engine = RuntimeEngine(
        account_id=account_id,
        deployment=deployment,
        components=components,
        broker_sync=broker_freshness,
        portfolio_snapshot=portfolio_snapshot,
    )
    latest = None
    for bar in bars:
        latest = engine.process_bar(bar)
    events = tuple(latest.events if latest is not None else ())
    return {
        "ok": True,
        "mode": "dry_run",
        "bars_processed": len(bars),
        "orders_created": 0,
        "candidate_decisions": [
            _runtime_event_payload(event)
            for event in events
            if event.event_type.value == "signal_candidate"
        ],
        "governor_decisions": [
            _runtime_event_payload(event)
            for event in events
            if event.event_type.value in {"execution_intent_created", "execution_intent_blocked"}
        ],
    }


def _run_execute(
    *,
    account_id: UUID,
    deployment: DeploymentContext,
    components: ResolvedProgramComponents,
    bars: tuple[NormalizedBar, ...],
    broker_adapter: AlpacaBrokerAdapter,
    broker_sync: BrokerSync,
    order_manager: OrderManager,
    broker_freshness: BrokerSyncFreshness,
    portfolio_snapshot: PortfolioSnapshot,
) -> dict[str, object]:
    orchestrator = RuntimeOrchestrator(
        account_id=account_id,
        deployment=deployment,
        components=components,
        order_manager=order_manager,
        broker_adapter=broker_adapter,
        broker_sync=broker_sync,
        broker_freshness=broker_freshness,
        portfolio_snapshot=portfolio_snapshot,
    )
    latest = None
    orders_created = 0
    for bar in bars:
        latest = orchestrator.process_bar(bar)
        orders_created += len(latest.orders)
        if orders_created >= 1:
            _print_step("Max one order reached; stopping execute pass")
            break
    events = tuple(latest.events if latest is not None else ())
    return {
        "ok": True,
        "mode": "execute",
        "bars_processed": len(bars),
        "orders_created": orders_created,
        "candidate_decisions": [
            _pipeline_event_payload(event)
            for event in events
            if event.event_type.value == "candidate_trade_intent"
        ],
        "governor_decisions": [
            _pipeline_event_payload(event)
            for event in events
            if event.event_type.value == "governor_decision"
        ],
    }


def _validate_environment(*, bars: int, qty: int, execute: bool) -> str | None:
    if os.getenv("ALPACA_BASE_URL") != PAPER_BASE_URL:
        return "ALPACA_BASE_URL must equal https://paper-api.alpaca.markets"
    if execute and os.getenv("CONFIRM_PAPER_RUNTIME") != "yes":
        return "CONFIRM_PAPER_RUNTIME=yes is required when --execute is passed"
    if bars <= 0:
        return "bars must be greater than 0"
    if bars > 5:
        return "bars > 5 is blocked by paper runtime dry-run"
    if qty <= 0:
        return "qty must be greater than 0"
    if qty > 1:
        return "qty > 1 is blocked by paper runtime dry-run"
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


def _mode(execute: bool) -> str:
    return "execute" if execute else "dry_run"


def _components(*, symbol: str, timeframe: str, qty: int) -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Paper Runtime Dry Run Strategy",
        entry_rules=[
            SignalRule(
                name="close_above_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature=f"{timeframe}.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature=f"{timeframe}.open[0]",
                ),
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name=f"{timeframe} Controls",
        timeframe=timeframe,
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Paper Runtime Dry Run Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=qty,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Paper Runtime Dry Run Market",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Paper Runtime Dry Run Universe",
        symbols=[UniverseSymbol(symbol=symbol)],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Paper Runtime Dry Run Program",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedProgramComponents(
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
    return PortfolioSnapshot(positions=tuple(summaries))


def _runtime_event_payload(event) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "sequence": event.sequence,
        "timestamp": _timestamp(event.timestamp),
        "event_type": event.event_type.value,
        "symbol": event.symbol,
        "message": event.message,
        "details": event.details,
    }


def _pipeline_event_payload(event) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "sequence": event.sequence,
        "timestamp": _timestamp(event.timestamp),
        "event_type": event.event_type.value,
        "symbol": event.symbol,
        "message": event.message,
        "details": event.details,
    }


def _timestamp(value: datetime) -> str:
    return value.isoformat()


def _print_step(message: str) -> None:
    print(f"[run_paper_runtime_dry_run] {message}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
