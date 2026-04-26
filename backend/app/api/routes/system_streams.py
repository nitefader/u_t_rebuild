"""Operator visibility into runtime streams.

Per the runtime architecture spec, the Operations Center must show:
- Market Data Pipeline status
- Status of every Account's Broker Trade Update Stream
- Connection issues / stale states

This endpoint reports a snapshot for the UI to render. It does not
mutate state and is safe to poll.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict


_TRADE_STREAM_STALE_SECONDS = 90


class TradeStreamStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    is_running: bool
    last_event_at: datetime | None
    last_error: str | None
    subscriber_count: int
    is_stale: bool
    stale_reason: str | None


class HubStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    trading_mode: str
    data_feed: str
    is_running: bool
    consumer_count: int
    subscribed_symbols: tuple[str, ...]


class SystemStreamsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_data_hubs: tuple[HubStatus, ...]
    trade_streams: tuple[TradeStreamStatus, ...]
    snapshot_at: datetime


def _trade_stream_status(dispatcher: Any) -> TradeStreamStatus:
    is_running = bool(dispatcher.is_running)
    last_event_at = dispatcher.last_event_at
    last_error = dispatcher.last_error
    subscribers = len(dispatcher.subscriber_ids)
    is_stale = False
    stale_reason: str | None = None
    if not is_running and last_error:
        is_stale = True
        stale_reason = f"not_running: {last_error}"
    elif not is_running:
        is_stale = True
        stale_reason = "not_running"
    elif last_event_at is not None:
        age = (datetime.now(timezone.utc) - last_event_at).total_seconds()
        if age > _TRADE_STREAM_STALE_SECONDS:
            is_stale = True
            stale_reason = f"no_event_for_{int(age)}s"
    return TradeStreamStatus(
        account_id=dispatcher.account_id,
        is_running=is_running,
        last_event_at=last_event_at,
        last_error=last_error,
        subscriber_count=subscribers,
        is_stale=is_stale,
        stale_reason=stale_reason,
    )


def _hub_status(key: Any, hub: Any) -> HubStatus:
    return HubStatus(
        provider=key.provider,
        trading_mode=key.trading_mode,
        data_feed=key.data_feed,
        is_running=bool(getattr(hub, "is_running", False)),
        consumer_count=len(getattr(hub, "consumer_ids", ()) or ()),
        subscribed_symbols=tuple(getattr(hub, "subscribed_symbols", ()) or ()),
    )


def system_streams_snapshot() -> SystemStreamsResponse:
    from backend.app.runtime.runtime_context import hub_registry, trade_dispatcher_registry

    hubs = hub_registry()
    hub_statuses = []
    for key in hubs.keys():
        hub = hubs.get_or_create(key)
        hub_statuses.append(_hub_status(key, hub))

    trade_statuses = [
        _trade_stream_status(dispatcher)
        for dispatcher in trade_dispatcher_registry().all()
    ]

    return SystemStreamsResponse(
        market_data_hubs=tuple(hub_statuses),
        trade_streams=tuple(trade_statuses),
        snapshot_at=datetime.now(timezone.utc),
    )


router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/streams", response_model=SystemStreamsResponse)
def get_system_streams() -> SystemStreamsResponse:
    return system_streams_snapshot()
