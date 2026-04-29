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
    research_jobs,
    research_runs,
    risk_decisions,
    risk_plans,
    screener,
    strategies,
    system_migration,
    system_settings,
    system_status,
    system_streams,
    watchlists,
)


app = FastAPI(title="Ultimate Trader API")
app.add_middleware(OptionalApiKeyMiddleware)


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

    # Build per-account BrokerSync / OrderManager stacks before opening any
    # broker trade streams so the first streamed event has a truth writer.
    manual_result = bootstrap_manual_trade_composition()
    import logging
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


@app.on_event("shutdown")
def _shutdown_runtime_singletons() -> None:  # pragma: no cover
    from backend.app.runtime.runtime_context import shutdown_runtime_context
    from backend.app.screener.scheduler_runtime import stop_discovery_schedule_poller

    stop_discovery_schedule_poller()
    shutdown_runtime_context()


app.include_router(system_status.router)
app.include_router(system_settings.router)
app.include_router(system_streams.router)
app.include_router(system_migration.router)
app.include_router(broker_accounts.router)
app.include_router(manual_trade.router)
app.include_router(operations.router)
app.include_router(operations_trade_stream.router)
app.include_router(research_runs.router)
app.include_router(research_jobs.router)
app.include_router(risk_decisions.router)
app.include_router(risk_plans.router)
app.include_router(market_data.router)
app.include_router(data_center.router)
app.include_router(ai.router)
app.include_router(chart_lab.router)
app.include_router(strategies.router)
app.include_router(watchlists.router)
app.include_router(deployments.router)
app.include_router(screener.router)
app.include_router(screener.market_lists_router)
app.include_router(discovery_schedules.router)
