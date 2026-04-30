"""Account trading entrypoint — composes the broker-backed runtime stack.

This is the CLI seam that turns the in-process surfaces (broker adapter,
trade-update stream, market-data hub, account trading supervisor) into a
single ``run_account_trading`` function plus a ``__main__`` invocation
for ``python -m backend.app.runtime.account_trading_entrypoint``.

The function is intentionally thin: it composes existing services in
dependency order, registers the supervisor as a market-data hub
consumer, starts the streams, and (optionally) blocks on SIGINT.

It does not create deployments — those live elsewhere. The primary
registered Alpaca account's ``TradingMode`` selects the Alpaca REST and
trading-stream endpoints. Paper and live are Account metadata; there is
one runtime path. Live submission still requires explicit enablement and
promotion gates.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from collections.abc import Iterable
from pathlib import Path

from uuid import UUID

from backend.app.brokers import (
    AlpacaBrokerAdapter,
    BrokerSync,
)
from backend.app.control_plane import ControlPlane
from backend.app.governor import PortfolioSnapshot, PositionSummary
from backend.app.market_data import MarketDataStreamHub
from backend.app.orders import OrderManager
from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.persistence import SQLiteRuntimeStore

from .account_trading_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator
from .account_trading_supervisor import BrokerRuntimeSupervisor


logger = logging.getLogger(__name__)


class BrokerRuntimeEntrypointError(RuntimeError):
    """Raised when the runtime cannot start safely (missing env, bad store, etc.)."""


def build_portfolio_snapshot_factory(runtime_store: SQLiteRuntimeStore):
    """Build the production-grade PortfolioSnapshot factory.

    W2-A-1 (audit P0 #1 — pre-T-7 bundle, operator decision 2026-04-30):
    Closes the audit's silent-no-op where the Governor's percentage gates
    silently saw zero incremental candidate exposure. Production used to
    default to ``PortfolioSnapshot()`` (equity=None) which collapsed every
    percentage gate via ``_pct(value, None) -> 0``. This factory reads the
    BrokerSync-persisted account snapshot and returns a usable equity.

    Three exit shapes:
    1. No BrokerSync snapshot yet (``KeyError``) → ``PortfolioSnapshot()``
       so the new ``portfolio_equity_unavailable`` fail-closed rule rejects
       opens until BrokerSync seeds.
    2. Snapshot exists but equity<=0 (stale poll, blocked account, fresh
       unfunded account, post-liquidation) → ``PortfolioSnapshot()`` for
       the same reason. Operationally indistinguishable from "we don't
       know" + ``PortfolioSnapshot.equity`` is ``gt=0`` so passing 0 would
       crash construction.
    3. Snapshot exists with equity>0 → ``PortfolioSnapshot(equity=...)``.
       Positions are intentionally empty until ``BrokerPositionSnapshot``
       carries ``program_id`` (deferred to a follow-up slice); the
       Governor still enforces equity-bounded percentage gates against
       incremental candidate exposure (the core W2-A-1a fix).
    """

    def _factory(account_id: UUID) -> PortfolioSnapshot:
        try:
            account_snapshot = runtime_store.load_broker_account_snapshot(account_id)
        except KeyError:
            return PortfolioSnapshot()
        equity = float(account_snapshot.equity)
        if equity <= 0:
            return PortfolioSnapshot()
        return PortfolioSnapshot(equity=equity)

    return _factory


def run_account_trading(
    *,
    sqlite_path: str | Path,
    deployments: Iterable[BrokerRuntimeDeployment] | None = None,
    market_data_hub: MarketDataStreamHub | None = None,
    block_until_signal: bool = True,
) -> tuple[BrokerRuntimeSupervisor, MarketDataStreamHub]:
    """Build the account trading stack and return (supervisor, hub).

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
    control_plane = ControlPlane(state_store=runtime_store)
    from backend.app.api.routes.chart_lab import ChartLabConfig
    from backend.app.runtime.runtime_context import HubKey, bootstrap_manual_trade_composition, bootstrap_streams, hub_registry

    bootstrap_manual_trade_composition(broker_account_service)
    bootstrap_streams(broker_account_service)
    account_trading = BrokerRuntimeOrchestrator(
        deployments=tuple(deployments or ()),
        runtime_store=runtime_store,
        broker_adapter=broker_adapter,
        broker_sync=broker_sync,
        order_manager=order_manager,
        control_plane=control_plane,
        portfolio_snapshot_factory=build_portfolio_snapshot_factory(runtime_store),
    )

    active_entries = account_trading.load_active_account_deployments()

    hub = market_data_hub or hub_registry().get_or_create(
        HubKey(provider="alpaca", data_feed=ChartLabConfig.from_env().data_feed)
    )
    supervisor = BrokerRuntimeSupervisor(
        account_trading=account_trading,
        market_data_hub=hub,
    )
    supervisor.start(active_entries)
    if not hub.is_running:
        hub.start()

    if not block_until_signal:
        return supervisor, hub

    _block_until_signal(supervisor, hub)
    return supervisor, hub


def _block_until_signal(supervisor: BrokerRuntimeSupervisor, hub: MarketDataStreamHub) -> None:
    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.info("received signal %s; stopping account trading runtime", signum)
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
        description="Start account trading for active deployments.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=None,
        help=(
            "Path to the runtime SQLite database. When omitted, uses the same resolution as "
            "the HTTP API (OPERATIONS_RUNTIME_DB_PATH, legacy UTOS_SQLITE_PATH, then data/runtime.db "
            "or existing data/utos.sqlite3). See backend.app.config.runtime_paths.get_runtime_db_path."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=os.getenv("UTOS_LOG_LEVEL", "INFO"))
    args = _parse_args(argv)
    sqlite_path = args.sqlite_path if args.sqlite_path is not None else str(get_runtime_db_path())
    run_account_trading(sqlite_path=sqlite_path)


if __name__ == "__main__":  # pragma: no cover
    main()
