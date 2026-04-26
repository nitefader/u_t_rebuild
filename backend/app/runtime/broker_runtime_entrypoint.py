"""Broker-runtime entrypoint — composes the full broker-runtime stack.

This is the CLI seam that turns the in-process surfaces (broker adapter,
trade-update stream, market-data hub, broker runtime, supervisor) into a
single ``run_broker_runtime`` function plus a ``__main__`` invocation
for ``python -m backend.app.runtime.broker_runtime_entrypoint``.

The function is intentionally thin: it composes existing services in
dependency order, registers the supervisor as a market-data hub
consumer, starts the streams, and (optionally) blocks on SIGINT.

It does not create deployments — those live elsewhere. It also does not
know whether the broker adapter is BROKER_PAPER or BROKER_LIVE; today
``AlpacaBrokerAdapter`` only supports paper, so paper is what runs. When
the adapter gains live support and the promotion gate is wired in, the
same entrypoint runs live.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from collections.abc import Iterable
from pathlib import Path

from backend.app.brokers import (
    AlpacaAccountStreamAdapter,
    AlpacaBrokerAdapter,
    BrokerStreamRouter,
    BrokerStreamRunner,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.control_plane import ControlPlane
from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataStreamHub
from backend.app.orders import OrderManager, TradeLedger
from backend.app.persistence import SQLiteRuntimeStore

from .broker_runtime_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator
from .broker_runtime_supervisor import BrokerRuntimeSupervisor


logger = logging.getLogger(__name__)


class BrokerRuntimeEntrypointError(RuntimeError):
    """Raised when the runtime cannot start safely (missing env, bad store, etc.)."""


def run_broker_runtime(
    *,
    sqlite_path: str | Path,
    deployments: Iterable[BrokerRuntimeDeployment] | None = None,
    market_data_hub: MarketDataStreamHub | None = None,
    block_until_signal: bool = True,
) -> tuple[BrokerRuntimeSupervisor, MarketDataStreamHub]:
    """Build the broker runtime stack and return (supervisor, hub).

    The hub is exposed so callers can register additional consumers
    (sim-lab live simulation, chart-lab live preview) against the same
    market-data subscription before the hub starts.

    Per the operator-driven credential model: this entrypoint pulls the
    per-account credentials from the encrypted ``BrokerCredentialStore``
    via ``BrokerAccountService``. There is no env-var fallback; accounts
    without stored credentials fail-closed and the operator must
    re-enter via the inline credentials surface on the Brokers page.
    """
    from backend.app.broker_accounts.runtime_service import (
        create_broker_account_service_from_environment,
    )

    runtime_store = SQLiteRuntimeStore(sqlite_path)
    broker_account_service = create_broker_account_service_from_environment()
    accounts = list(broker_account_service.list_broker_accounts())
    primary = next(
        (a for a in accounts if a.provider == "alpaca" and not a.is_archived and not a.needs_credentials),
        None,
    )
    if primary is None:
        raise BrokerRuntimeEntrypointError(
            "no usable Alpaca broker account is registered. "
            "Add one (or re-enter credentials) on the Brokers page before starting the runtime."
        )
    api_key, api_secret = broker_account_service.get_credentials(primary.id)
    broker_adapter = AlpacaBrokerAdapter(
        mode=primary.mode,
        api_key=api_key,
        secret_key=api_secret,
    )
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

    broker_stream_runner: BrokerStreamRunner | None = None
    active_entries = broker_runtime.load_active_broker_paper_deployments()
    if active_entries:
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

    hub = market_data_hub or MarketDataStreamHub(market_data_adapter=AlpacaMarketDataAdapter())
    supervisor = BrokerRuntimeSupervisor(
        broker_runtime=broker_runtime,
        market_data_hub=hub,
        broker_stream_runner=broker_stream_runner,
    )
    supervisor.start(active_entries)
    hub.start()

    if not block_until_signal:
        return supervisor, hub

    _block_until_signal(supervisor, hub)
    return supervisor, hub


def _block_until_signal(supervisor: BrokerRuntimeSupervisor, hub: MarketDataStreamHub) -> None:
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info("received signal %s; stopping broker runtime", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    try:
        stop_event.wait()
    finally:
        supervisor.stop()
        hub.stop()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the broker runtime against active deployments.",
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
    run_broker_runtime(sqlite_path=args.sqlite_path)


if __name__ == "__main__":  # pragma: no cover
    main()
