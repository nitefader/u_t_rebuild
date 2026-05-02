from __future__ import annotations

try:  # pragma: no cover - optional dotenv support; tests don't depend on it.
    import os as _os

    from dotenv import load_dotenv

    # In dev / paper, edits to .env always win over stale shell-session
    # env vars (override=True). In production, .env (if present at all)
    # must NOT silently overwrite vars set by the deployment environment
    # — that would mask credential rotation accidents. Guard by
    # UTOS_ENVIRONMENT: production / prod / live disable override.
    _env = (_os.getenv("UTOS_ENVIRONMENT") or "").lower()
    _override = _env not in {"production", "prod", "live"}
    load_dotenv(override=_override)
except ImportError:  # pragma: no cover
    pass

from fastapi import FastAPI

from backend.app.api.api_key_middleware import OptionalApiKeyMiddleware
from backend.app.api.routes import (
    ai,
    broker_accounts,
    chart_lab,
    data_center,
    deployments,
    discovery_schedules,
    manual_trade,
    market_data,
    operations,
    operations_trade_stream,
    risk_decisions,
    risk_plans,
    screener,
    strategies,
    strategies_v4,
    execution_plans,
    strategy_controls,
    strategy_expression,
    system_migration,
    system_settings,
    system_status,
    system_streams,
    watchlists,
)


app = FastAPI(title="Ultimate Trader API")
app.add_middleware(OptionalApiKeyMiddleware)


def _kill_orphan_python_children() -> int:
    """Defense-in-depth: kill orphan multiprocessing spawn_main children
    of dead parents before opening any broker WebSocket.

    Background: ``uvicorn --reload`` and any other multiprocessing-based
    launcher can leave child workers alive when the parent dies abruptly
    (taskkill, OS crash, etc.). On Windows those children keep their TCP
    sockets open — including the Alpaca data WebSocket — which causes the
    next boot to hit ``connection limit exceeded`` because Alpaca still
    sees the orphan's session as active.

    This guard scans for ``python.exe`` processes running
    ``multiprocessing.spawn_main(parent_pid=N)`` whose parent_pid no
    longer exists, and terminates them. Safe by construction: only the
    spawn_main pattern is matched, only orphans are touched.

    Returns the number of orphans killed. No-op on non-Windows.
    """
    import logging
    import os
    import re
    import subprocess

    logger = logging.getLogger("backend.app.api.server")
    if os.name != "nt":  # POSIX child reaping handled by the kernel
        return 0

    try:
        # WMIC is deprecated but available on Win10/11; fall back to
        # PowerShell if missing.
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | Where-Object { "
                    "$_.Name -eq 'python.exe' -and $_.CommandLine -match "
                    "'multiprocessing.spawn'} | Select-Object ProcessId,CommandLine | "
                    "ConvertTo-Json -Compress"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("orphan guard: process scan failed: %s", exc)
        return 0

    raw = (result.stdout or "").strip()
    if not raw:
        return 0
    import json as _json

    try:
        items = _json.loads(raw)
    except _json.JSONDecodeError:
        return 0
    if isinstance(items, dict):
        items = [items]

    parent_pat = re.compile(r"parent_pid=(\d+)")
    killed = 0
    for item in items:
        pid = int(item.get("ProcessId") or 0)
        cmd = str(item.get("CommandLine") or "")
        m = parent_pat.search(cmd)
        if not m:
            continue
        parent_pid = int(m.group(1))
        # Is the claimed parent still alive?
        try:
            check = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 f"if (Get-Process -Id {parent_pid} -ErrorAction SilentlyContinue) {{ 'alive' }} else {{ 'dead' }}"],
                capture_output=True, text=True, timeout=5,
            )
            if "alive" in (check.stdout or ""):
                continue  # legitimate child of a live parent
        except Exception:
            continue
        # Parent is dead — this is an orphan holding sockets. Kill it.
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 f"Stop-Process -Id {pid} -Force -ErrorAction Stop"],
                capture_output=True, text=True, timeout=5,
            )
            logger.warning(
                "orphan guard: killed orphan python child PID=%d (dead parent_pid=%d)",
                pid, parent_pid,
            )
            killed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("orphan guard: failed to kill PID=%d: %s", pid, exc)
    return killed


@app.on_event("startup")
def _bootstrap_streams() -> None:  # pragma: no cover
    """Per the runtime architecture spec: streams auto-start at boot.

    - The Market Data Pipeline (hub registry) is constructed and ready.
    - One Broker Trade Update Stream is started per configured Account,
      regardless of whether any Deployments have subscribed yet.
    """
    from backend.app.runtime.runtime_context import (
        bootstrap_manual_trade_composition,
        bootstrap_streams,
    )

    # Defense-in-depth: kill any orphan multiprocessing children left
    # behind by a prior abruptly-killed launcher before opening any
    # broker WebSocket. Without this guard, Alpaca will return
    # ``connection limit exceeded`` and the runtime cannot subscribe
    # bars. See _kill_orphan_python_children docstring.
    orphans_killed = _kill_orphan_python_children()
    import logging
    if orphans_killed:
        logging.getLogger("backend.app.api.server").warning(
            "orphan guard: cleaned %d stale python children before boot",
            orphans_killed,
        )

    # Build per-account BrokerSync / OrderManager stacks before opening any
    # broker trade streams so the first streamed event has a truth writer.
    manual_result = bootstrap_manual_trade_composition()
    logging.getLogger("backend.app.api.server").info(
        "manual-trade bootstrap: registered=%d skipped=%d seen=%d",
        len(manual_result["registered_account_ids"]),
        len(manual_result["skipped"]),
        manual_result["total_accounts_seen"],
    )
    result = bootstrap_streams()
    logging.getLogger("backend.app.api.server").info(
        "stream bootstrap: started=%d skipped=%d seen=%d",
        len(result["started_account_ids"]),
        len(result["skipped"]),
        result["total_accounts_seen"],
    )
    try:
        from backend.app.screener.scheduler_runtime import start_discovery_schedule_poller

        start_discovery_schedule_poller()
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("backend.app.api.server").warning(
            "discovery schedule poller failed to start: %s",
            exc,
            exc_info=True,
        )

    # Slice 11 closer (in-process trading supervisor):
    # Start the BrokerRuntimeSupervisor in the same process as the API so
    # the single Alpaca data WebSocket is shared (Alpaca paper enforces a
    # one-connection-per-key limit). This replaces the separate
    # `python -m backend.app.runtime.account_trading_entrypoint` process.
    # Active deployments are loaded from the runtime store and subscribed
    # to the existing market-data hub.
    try:
        from pathlib import Path

        from backend.app.config.runtime_paths import get_runtime_db_path
        from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
        from backend.app.runtime.account_trading_orchestrator import (
            BrokerRuntimeOrchestrator,
        )
        from backend.app.runtime.account_trading_supervisor import (
            BrokerRuntimeSupervisor,
        )
        from backend.app.runtime.runtime_context import hub_registry, HubKey
        from backend.app.api.routes.chart_lab import ChartLabConfig
        from backend.app.brokers import BrokerSync
        from backend.app.broker_accounts.runtime_service import (
            create_broker_account_service_from_environment,
        )
        from backend.app.control_plane import ControlPlane
        from backend.app.orders import OrderManager
        from backend.app.runtime.account_trading_entrypoint import (
            AccountScopedAlpacaBrokerAdapter,
            RuntimeHistoricalWarmupBarsSource,
            build_portfolio_snapshot_factory,
        )

        runtime_log = logging.getLogger("backend.app.api.server")
        sqlite_path = get_runtime_db_path()
        runtime_store = SQLiteRuntimeStore(Path(sqlite_path))
        broker_account_service = create_broker_account_service_from_environment()
        accounts = list(broker_account_service.list_broker_accounts())
        primary = next(
            (
                a
                for a in accounts
                if a.provider == "alpaca"
                and not a.is_archived
                and not a.needs_credentials
            ),
            None,
        )
        if primary is None:
            runtime_log.warning(
                "no usable Alpaca broker account; in-process trading supervisor not started"
            )
        else:
            broker_adapter = AccountScopedAlpacaBrokerAdapter(broker_account_service)
            order_manager = OrderManager(ledger=SQLiteOrderLedger(sqlite_path))
            broker_sync = BrokerSync(
                ledger=order_manager.ledger,
                adapter=broker_adapter,
                runtime_store=runtime_store,
                provider="alpaca",
            )
            control_plane = ControlPlane(state_store=runtime_store)
            account_trading = BrokerRuntimeOrchestrator(
                deployments=(),
                runtime_store=runtime_store,
                broker_adapter=broker_adapter,
                broker_sync=broker_sync,
                order_manager=order_manager,
                control_plane=control_plane,
                portfolio_snapshot_factory=build_portfolio_snapshot_factory(
                    runtime_store
                ),
                startup_warmup_bars_source=RuntimeHistoricalWarmupBarsSource(
                    runtime_store
                ),
            )
            active_entries = account_trading.load_active_account_deployments()
            hub = hub_registry().get_or_create(
                HubKey(
                    provider="alpaca",
                    data_feed=ChartLabConfig.from_env().data_feed,
                )
            )
            supervisor = BrokerRuntimeSupervisor(
                account_trading=account_trading,
                market_data_hub=hub,
            )
            supervisor.start(active_entries)
            if not hub.is_running:
                hub.start()
            # Mark each loaded deployment as recovery-completed so the
            # supervisor's per-bar preflight does not block on
            # ``runtime_recovery_not_completed``. We pass no recovery
            # orchestrator (the production recovery rehearsal lives in a
            # separate slice), so this just promotes lifecycle to RUNNING
            # and adds the deployment to the recovery-completed set used
            # by ``_recovery_ready``.
            for entry in active_entries:
                try:
                    account_trading.recover_and_resume(entry.deployment.deployment_id)
                except Exception as exc:  # noqa: BLE001
                    runtime_log.warning(
                        "recover_and_resume failed for deployment %s: %s",
                        entry.deployment.deployment_id,
                        exc,
                        exc_info=True,
                    )
            app.state.broker_runtime_supervisor = supervisor
            app.state.broker_runtime_hub = hub
            runtime_log.info(
                "broker runtime supervisor started in-process: deployments=%d symbols=%s",
                len(active_entries),
                hub.subscribed_symbols,
            )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("backend.app.api.server").warning(
            "in-process broker runtime supervisor failed to start: %s",
            exc,
            exc_info=True,
        )


@app.on_event("shutdown")
def _shutdown_runtime_singletons() -> None:  # pragma: no cover
    """Graceful shutdown — close broker WebSockets before the process exits.

    Without explicit close, Alpaca's session table keeps our slot warm
    for ~30–120s, which causes the next boot to hit
    ``connection limit exceeded``. Closing the supervisor + hub here
    sends a proper WebSocket close frame so Alpaca releases the slot
    immediately.
    """
    import logging

    log = logging.getLogger("backend.app.api.server")
    from backend.app.runtime.runtime_context import shutdown_runtime_context
    from backend.app.screener.scheduler_runtime import stop_discovery_schedule_poller

    stop_discovery_schedule_poller()
    # Stop the in-process broker runtime supervisor first so its consumer
    # is detached from the hub before the hub closes its WebSocket.
    supervisor = getattr(app.state, "broker_runtime_supervisor", None)
    if supervisor is not None:
        try:
            supervisor.stop()
            log.info("broker runtime supervisor stopped cleanly")
        except Exception as exc:  # noqa: BLE001
            log.warning("supervisor.stop() failed: %s", exc, exc_info=True)
    hub = getattr(app.state, "broker_runtime_hub", None)
    if hub is not None:
        try:
            hub.stop()
            log.info("broker runtime hub stopped cleanly (Alpaca slot released)")
        except Exception as exc:  # noqa: BLE001
            log.warning("hub.stop() failed: %s", exc, exc_info=True)
    shutdown_runtime_context()


app.include_router(system_status.router)
app.include_router(system_settings.router)
app.include_router(system_streams.router)
app.include_router(system_migration.router)
app.include_router(broker_accounts.router)
app.include_router(manual_trade.router)
app.include_router(operations.router)
app.include_router(operations_trade_stream.router)
app.include_router(risk_decisions.router)
app.include_router(risk_plans.router)
app.include_router(market_data.router)
app.include_router(data_center.router)
app.include_router(ai.router)
app.include_router(chart_lab.router)
app.include_router(strategies.router)
app.include_router(strategies_v4.router)
app.include_router(execution_plans.router)
app.include_router(strategy_controls.router)
app.include_router(strategy_expression.router)
app.include_router(watchlists.router)
app.include_router(deployments.router)
app.include_router(screener.router)
app.include_router(screener.market_lists_router)
app.include_router(discovery_schedules.router)
