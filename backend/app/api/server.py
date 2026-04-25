from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes import broker_accounts, operations, services


app = FastAPI(title="Trading OS API")

app.include_router(broker_accounts.router)
app.include_router(operations.router)
app.include_router(services.router)
