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

from backend.app.api.routes import (
    ai,
    broker_accounts,
    chart_lab,
    market_data,
    operations,
    operations_trade_stream,
    system_migration,
    system_settings,
    system_status,
)


app = FastAPI(title="Trading OS API")


@app.on_event("shutdown")
def _shutdown_runtime_singletons() -> None:  # pragma: no cover
    from backend.app.runtime.runtime_context import shutdown_runtime_context

    shutdown_runtime_context()


app.include_router(system_status.router)
app.include_router(system_settings.router)
app.include_router(system_migration.router)
app.include_router(broker_accounts.router)
app.include_router(operations.router)
app.include_router(operations_trade_stream.router)
app.include_router(market_data.router)
app.include_router(ai.router)
app.include_router(chart_lab.router)
