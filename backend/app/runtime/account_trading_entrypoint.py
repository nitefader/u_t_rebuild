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
from datetime import timedelta
from pathlib import Path
from typing import Any

from uuid import UUID

from backend.app.brokers import (
    AlpacaBrokerAdapter,
    AlpacaBrokerError,
    BrokerSync,
)
from backend.app.control_plane import ControlPlane
from backend.app.governor import PortfolioSnapshot, PositionSummary
from backend.app.market_data import MarketDataStreamHub
from backend.app.orders import OrderManager
from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.domain._base import utc_now
from backend.app.features import NormalizedBar
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore

from .account_trading_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator
from .account_trading_supervisor import BrokerRuntimeSupervisor


logger = logging.getLogger(__name__)


class BrokerRuntimeEntrypointError(RuntimeError):
    """Raised when the runtime cannot start safely (missing env, bad store, etc.)."""


class AccountScopedAlpacaBrokerAdapter:
    """Route broker calls to the Alpaca credentials for the target Account."""

    provider = "alpaca"

    def __init__(self, broker_account_service: Any) -> None:
        self._broker_account_service = broker_account_service
        self._adapters_by_account_id: dict[UUID, AlpacaBrokerAdapter] = {}

    def mode_for_account(self, account_id: UUID):
        return self._account_for(account_id).mode

    def submit_order(self, order):
        return self._adapter_for_account(order.account_id).submit_order(order)

    def get_order(self, order):
        return self._adapter_for_account(order.account_id).get_order(order)

    def cancel_order(self, order):
        return self._adapter_for_account(order.account_id).cancel_order(order)

    def cancel_orders(self, account_id: UUID, scope: str):
        return self._adapter_for_account(account_id).cancel_orders(account_id, scope)

    def replace_order(self, order, new_params):
        return self._adapter_for_account(order.account_id).replace_order(order, new_params)

    def list_open_orders(self, account_id: UUID):
        return self._adapter_for_account(account_id).list_open_orders(account_id)

    def get_account_snapshot(self, account_id: UUID):
        return self._adapter_for_account(account_id).get_account_snapshot(account_id)

    def get_positions(self, account_id: UUID):
        return self._adapter_for_account(account_id).get_positions(account_id)

    def get_market_clock(self) -> dict[str, Any]:
        return self._adapter_for_account(self._first_usable_account_id()).get_market_clock()

    def _adapter_for_account(self, account_id: UUID) -> AlpacaBrokerAdapter:
        existing = self._adapters_by_account_id.get(account_id)
        if existing is not None:
            return existing
        account = self._account_for(account_id)
        api_key, api_secret = self._broker_account_service.get_credentials(account_id)
        adapter = AlpacaBrokerAdapter(
            mode=account.mode,
            api_key=api_key,
            secret_key=api_secret,
        )
        self._adapters_by_account_id[account_id] = adapter
        return adapter

    def _account_for(self, account_id: UUID):
        for account in self._broker_account_service.list_broker_accounts():
            if account.id == account_id:
                if account.provider != "alpaca":
                    raise AlpacaBrokerError(
                        "unsupported_account_provider",
                        f"Account {account_id} is not an Alpaca account",
                    )
                if account.is_archived or account.needs_credentials:
                    raise AlpacaBrokerError(
                        "account_credentials_unavailable",
                        f"Account {account_id} cannot be used for broker execution",
                    )
                return account
        raise AlpacaBrokerError("missing_broker_account", f"Unknown broker account: {account_id}")

    def _first_usable_account_id(self) -> UUID:
        for account in self._broker_account_service.list_broker_accounts():
            if account.provider == "alpaca" and not account.is_archived and not account.needs_credentials:
                return account.id
        raise AlpacaBrokerError("missing_broker_account", "No usable Alpaca broker account is registered")


class RuntimeHistoricalWarmupBarsSource:
    """Fetch recent bars through Data Center for startup feature warmup."""

    def __init__(self, runtime_store: SQLiteRuntimeStore) -> None:
        self._runtime_store = runtime_store

    def __call__(
        self,
        entry: BrokerRuntimeDeployment,  # noqa: ARG002 - source is deployment-scoped for future provider routing.
        symbol: str,
        timeframe: str,
        warmup_bars: int,
    ) -> tuple[NormalizedBar, ...]:
        from backend.app.data_center.ingest_service import (
            HistoricalBarIngestRequest,
            HistoricalBarIngestService,
            alpaca_bars_source_from_runtime,
        )

        end = utc_now()
        start = end - _startup_warmup_window(timeframe=timeframe, warmup_bars=warmup_bars)
        service = HistoricalBarIngestService(
            store=self._runtime_store,
            sources={"alpaca": alpaca_bars_source_from_runtime(self._runtime_store)},
        )
        result = service.ensure_bars(
            HistoricalBarIngestRequest(
                provider="alpaca",
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
        )
        bars = tuple(
            sorted(
                (
                    bar
                    for bar in result.bars
                    if bar.symbol.upper() == symbol.upper() and bar.timeframe == timeframe
                ),
                key=lambda bar: bar.timestamp,
            )
        )
        return bars[-max(int(warmup_bars), 1):]


def _startup_warmup_window(*, timeframe: str, warmup_bars: int) -> timedelta:
    bars = max(int(warmup_bars), 1)
    if timeframe.endswith("m") and timeframe[:-1].isdigit():
        minutes = int(timeframe[:-1])
        return max(timedelta(minutes=minutes * bars * 4), timedelta(days=7))
    if timeframe.endswith("h") and timeframe[:-1].isdigit():
        hours = int(timeframe[:-1])
        return max(timedelta(hours=hours * bars * 4), timedelta(days=30))
    if timeframe == "1d":
        return timedelta(days=bars * 3 + 14)
    return timedelta(days=max(bars * 3, 14))


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
       carries SignalPlan position lineage; the
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
    broker_adapter = AccountScopedAlpacaBrokerAdapter(broker_account_service)
    order_manager = OrderManager(ledger=SQLiteOrderLedger(sqlite_path))
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
        startup_warmup_bars_source=RuntimeHistoricalWarmupBarsSource(runtime_store),
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
