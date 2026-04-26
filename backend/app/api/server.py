from __future__ import annotations

try:  # pragma: no cover - optional dotenv support; tests don't depend on it.
    from dotenv import load_dotenv

    # override=True so edits to .env always win over stale shell-session
    # env vars. The operator UI treats .env as the source of truth — if
    # they need to inject a one-off override they can `set FOO=...` then
    # comment out the .env line.
    load_dotenv(override=True)
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
    system_status,
)


app = FastAPI(title="Trading OS API")

app.include_router(system_status.router)
app.include_router(broker_accounts.router)
app.include_router(operations.router)
app.include_router(operations_trade_stream.router)
app.include_router(market_data.router)
app.include_router(ai.router)
app.include_router(chart_lab.router)
