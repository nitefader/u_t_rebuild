"""Operator visibility into runtime streams.

Per the runtime architecture spec, the Operations Center must show:
- Market Data Pipeline status by asset class
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


class TradeStreamStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    account_label: str | None = None
    is_running: bool
    last_event_at: datetime | None
    last_error: str | None
    subscriber_count: int
    subscriber_summary_lines: tuple[str, ...] = ()
    is_stale: bool
    stale_reason: str | None
    idle_note: str | None = None


class HubStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    asset_class: str = "stock"
    data_feed: str
    is_running: bool
    consumer_count: int
    subscribed_symbols: tuple[str, ...]
    stream_status: str | None = None
    last_error: str | None = None
    last_message_at: datetime | None = None


class SystemStreamsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_data_hubs: tuple[HubStatus, ...]
    trade_streams: tuple[TradeStreamStatus, ...]
    snapshot_at: datetime


def _broker_account_labels() -> dict[UUID, str]:
    """Best-effort friendly names for stream rows (no raw UUID as the only label)."""
    out: dict[UUID, str] = {}
    try:
        from backend.app.broker_accounts.runtime_service import create_broker_account_service_from_environment

        service = create_broker_account_service_from_environment()
        for acct in service.list_broker_accounts():
            mode_s = getattr(acct.mode, "value", str(acct.mode))
            short = "Live" if "LIVE" in str(mode_s).upper() else "Paper"
            out[acct.id] = f"{short} · {acct.display_name}"
    except Exception:
        return out
    return out


def _trade_stream_status(dispatcher: Any, account_labels: dict[UUID, str]) -> TradeStreamStatus:
    is_running = bool(dispatcher.is_running)
    last_event_at = dispatcher.last_event_at
    last_error = dispatcher.last_error
    subscribers = len(dispatcher.subscriber_ids)
    summary_lines = dispatcher.subscriber_summary_lines()
    is_stale = False
    stale_reason: str | None = None
    idle_note: str | None = None
    if not is_running and last_error:
        is_stale = True
        stale_reason = f"not_running: {last_error}"
    elif not is_running:
        is_stale = True
        stale_reason = "not_running"
    elif last_event_at is not None:
        age = (datetime.now(timezone.utc) - last_event_at).total_seconds()
        if age > 0:
            idle_note = f"last_trade_event_{int(age)}s_ago"
    else:
        idle_note = "waiting_for_first_trade_event"
    return TradeStreamStatus(
        account_id=dispatcher.account_id,
        account_label=account_labels.get(dispatcher.account_id),
        is_running=is_running,
        last_event_at=last_event_at,
        last_error=last_error,
        subscriber_count=subscribers,
        subscriber_summary_lines=summary_lines,
        is_stale=is_stale,
        stale_reason=stale_reason,
        idle_note=idle_note,
    )


def _hub_status(key: Any, hub: Any) -> HubStatus:
    rich_status = hub.status() if hasattr(hub, "status") else None
    return HubStatus(
        provider=key.provider,
        asset_class=getattr(key, "asset_class", "stock"),
        data_feed=key.data_feed,
        is_running=bool(getattr(hub, "is_running", False)),
        consumer_count=len(getattr(hub, "consumer_ids", ()) or ()),
        subscribed_symbols=tuple(getattr(hub, "subscribed_symbols", ()) or ()),
        stream_status=getattr(getattr(rich_status, "status", None), "value", None),
        last_error=getattr(rich_status, "last_error", None),
        last_message_at=getattr(rich_status, "last_message_at", None),
    )


def system_streams_snapshot() -> SystemStreamsResponse:
    from backend.app.runtime.runtime_context import hub_registry, trade_dispatcher_registry

    hubs = hub_registry()
    hub_statuses = []
    for key in hubs.keys():
        hub = hubs.get_or_create(key)
        hub_statuses.append(_hub_status(key, hub))

    account_labels = _broker_account_labels()
    trade_statuses = [_trade_stream_status(dispatcher, account_labels) for dispatcher in trade_dispatcher_registry().all()]

    return SystemStreamsResponse(
        market_data_hubs=tuple(hub_statuses),
        trade_streams=tuple(trade_statuses),
        snapshot_at=datetime.now(timezone.utc),
    )


router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/streams", response_model=SystemStreamsResponse)
def get_system_streams() -> SystemStreamsResponse:
    return system_streams_snapshot()
