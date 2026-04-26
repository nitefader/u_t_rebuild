"""Paper runtime entrypoint — wires creds → supervisor → block-until-signal.

This is the CLI seam that turns the in-process surfaces (broker adapter,
streams, broker runtime, supervisor) into a single ``run_paper_runtime``
function plus a ``__main__`` invocation for ``python -m
backend.app.runtime.paper_runtime_entrypoint``.

The function is intentionally thin: it composes existing services and
hands the result to ``PaperRuntimeSupervisor.start``. It does **not**
create deployments — those are created via the broker_accounts /
deployments flow elsewhere. The entrypoint reads active paper
deployments from the runtime store (if any), starts streams, and
blocks on SIGINT.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from collections.abc import Iterable
from pathlib import Path

from backend.app.brokers import AlpacaAccountStreamAdapter, AlpacaBrokerAdapter, BrokerStreamRouter, BrokerStreamRunner, BrokerSync
from backend.app.brokers import BrokerSyncService
from backend.app.control_plane import ControlPlane
from backend.app.market_data import AlpacaMarketDataAdapter
from backend.app.orders import OrderManager, TradeLedger
from backend.app.persistence import SQLiteRuntimeStore

from .broker_runtime_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator
from .paper_runtime_supervisor import PaperRuntimeSupervisor


logger = logging.getLogger(__name__)


class PaperRuntimeEntrypointError(RuntimeError):
    """Raised when the runtime cannot start safely (missing env, bad store, etc.)."""


def run_paper_runtime(
    *,
    sqlite_path: str | Path,
    deployments: Iterable[BrokerRuntimeDeployment] | None = None,
    block_until_signal: bool = True,
) -> PaperRuntimeSupervisor:
    """Build the paper runtime stack and return a started supervisor.

    The function composes the production services in dependency order,
    starts the trade-update stream, the market-data stream, and each
    eligible deployment, then optionally blocks on SIGINT/SIGTERM. It
    returns the running supervisor so callers (tests, embedding code)
    can inspect or stop it programmatically.

    Required env (validated on construction of ``AlpacaBrokerAdapter``):
        ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL=paper URL.
    """
    runtime_store = SQLiteRuntimeStore(sqlite_path)
    broker_adapter = AlpacaBrokerAdapter()
    order_manager = OrderManager()
    broker_sync = BrokerSync(
        ledger=order_manager.ledger,
        adapter=broker_adapter,
        runtime_store=runtime_store,
        provider="alpaca",
    )
    trade_ledger = TradeLedger()
    control_plane = ControlPlane(state_store=runtime_store)
    broker_runtime = BrokerRuntimeOrchestrator(
        deployments=tuple(deployments or ()),
        runtime_store=runtime_store,
        broker_adapter=broker_adapter,
        broker_sync=broker_sync,
        order_manager=order_manager,
        control_plane=control_plane,
    )

    sync_service: BrokerSyncService | None = None
    broker_stream_runner: BrokerStreamRunner | None = None
    active_entries = broker_runtime.load_active_broker_paper_deployments()
    if active_entries:
        # One sync_service per supervisor — all active paper deployments
        # share the same broker account here. (Multi-account support is
        # deferred until the deployment model carries account_id sharding.)
        first_account_id = active_entries[0].account_id
        sync_service = BrokerSyncService(
            adapter=broker_adapter,
            broker_sync=broker_sync,
            order_ledger=order_manager.ledger,
            trade_ledger=trade_ledger,
            runtime_store=runtime_store,
        )
        sync_service.record_successful_poll(first_account_id)
        order_manager.attach_broker_sync_service(sync_service)

        stream_client = broker_adapter.build_trading_stream()
        stream_adapter = AlpacaAccountStreamAdapter(
            account_id=first_account_id,
            stream_client=stream_client,
            normalizer=broker_adapter,
        )
        BrokerStreamRouter(sync_service).attach(stream_adapter)
        broker_stream_runner = BrokerStreamRunner(stream_client)

    market_data_adapter = AlpacaMarketDataAdapter()
    supervisor = PaperRuntimeSupervisor(
        broker_runtime=broker_runtime,
        market_data_adapter=market_data_adapter,
        broker_stream_runner=broker_stream_runner,
    )
    supervisor.start(active_entries)

    if not block_until_signal:
        return supervisor

    _block_until_signal(supervisor)
    return supervisor


def _block_until_signal(supervisor: PaperRuntimeSupervisor) -> None:
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info("received signal %s; stopping paper runtime", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    try:
        stop_event.wait()
    finally:
        supervisor.stop()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the Alpaca paper trading runtime against active deployments.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("UTOS_SQLITE_PATH", "data/utos.sqlite3"),
        help="Path to the runtime SQLite database (default: data/utos.sqlite3 or $UTOS_SQLITE_PATH)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.getenv("UTOS_LOG_LEVEL", "INFO"))
    args = _parse_args(argv)
    run_paper_runtime(sqlite_path=args.sqlite_path)


if __name__ == "__main__":  # pragma: no cover
    main()
