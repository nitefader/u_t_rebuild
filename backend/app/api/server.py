from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes import operations


app = FastAPI(title="Trading OS API")

app.include_router(operations.router)
