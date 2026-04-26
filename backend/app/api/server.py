from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.routes import (
    ai,
    broker_accounts,
    chart_lab,
    market_data,
    operations,
    operations_trade_stream,
)


app = FastAPI(title="Trading OS API")

app.include_router(broker_accounts.router)
app.include_router(operations.router)
app.include_router(operations_trade_stream.router)
app.include_router(market_data.router)
app.include_router(ai.router)
app.include_router(chart_lab.router)
