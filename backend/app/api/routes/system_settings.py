"""GET/PUT operator-editable runtime settings.

These knobs are persisted to ``data/system_settings.json`` and override
the equivalent ``ALPACA_*`` env vars. The endpoint deliberately covers
**non-secret** settings only — credentials stay in ``.env``.

Settings exposed:

- ``alpaca_use_test_stream``  — bool. Legacy global hint for FAKEPACA
  (used when no Chart Lab override and no catalog streaming tags).
- ``chart_lab_one_symbol_fakepaca`` — bool | omitted. When set, **Chart Lab’s
  one-symbol bar WebSocket only** uses FAKEPACA (true) or real SIP/IEX
  bars (false). Omitted = auto (catalog ``test_streaming`` / ``live_streaming``
  tags, then ``alpaca_use_test_stream``). Broker Trade Update Streams are
  **not** affected.
- ``alpaca_data_feed``        — string. ``iex`` / ``sip`` /
  ``delayed_sip`` / ``boats`` / ``overnight`` / ``otc``.
- ``chart_lab_default_symbol`` — string. Default symbol the Chart Lab
  page picks when the operator hasn't typed one.
"""

from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.system_settings_store import SystemSettingsStore, get_store


_SUPPORTED_DATA_FEEDS = {"iex", "sip", "delayed_sip", "boats", "overnight", "otc"}


class SystemSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alpaca_use_test_stream: bool = False
    alpaca_data_feed: str = "iex"
    chart_lab_default_symbol: str = Field(default="SPY", min_length=1, max_length=12)
    chart_lab_one_symbol_fakepaca: bool | None = None


class SystemSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpaca_use_test_stream: bool | None = None
    alpaca_data_feed: str | None = None
    chart_lab_default_symbol: str | None = Field(default=None, min_length=1, max_length=12)
    chart_lab_one_symbol_fakepaca: bool | None = None


def _settings_from_store(store: SystemSettingsStore) -> SystemSettings:
    raw = store.load()
    chart_override = raw["chart_lab_one_symbol_fakepaca"] if "chart_lab_one_symbol_fakepaca" in raw else None
    if chart_override is not None:
        chart_override = bool(chart_override)
    return SystemSettings(
        alpaca_use_test_stream=bool(raw.get("alpaca_use_test_stream", False)),
        alpaca_data_feed=str(raw.get("alpaca_data_feed", "iex")).lower(),
        chart_lab_default_symbol=str(raw.get("chart_lab_default_symbol", "SPY")).upper(),
        chart_lab_one_symbol_fakepaca=chart_override,
    )


def _validate_data_feed(value: str) -> str:
    normalized = value.lower()
    if normalized not in _SUPPORTED_DATA_FEEDS:
        raise HTTPException(status_code=400, detail=f"unsupported alpaca_data_feed: {value!r}")
    return normalized


def get_settings_store() -> SystemSettingsStore:
    return get_store()


def _dependency(default: object) -> object:
    return Depends(default)


def _body(default: object) -> object:
    return Body(default)


router = APIRouter(prefix="/api/v1/system", tags=["system"])


SettingsStoreDependency = Annotated[Any, _dependency(get_settings_store)]
SettingsBody = Annotated[SystemSettingsUpdate, _body(...)]


@router.get("/settings", response_model=SystemSettings)
def get_system_settings(store: SettingsStoreDependency) -> SystemSettings:
    return _settings_from_store(store)


@router.put("/settings", response_model=SystemSettings)
def put_system_settings(payload: SettingsBody, store: SettingsStoreDependency) -> SystemSettings:
    update = payload if isinstance(payload, SystemSettingsUpdate) else SystemSettingsUpdate.model_validate(payload)
    changes: dict[str, Any] = {}
    dumped = update.model_dump(exclude_unset=True)
    if update.alpaca_use_test_stream is not None:
        changes["alpaca_use_test_stream"] = bool(update.alpaca_use_test_stream)
    if update.alpaca_data_feed is not None:
        changes["alpaca_data_feed"] = _validate_data_feed(update.alpaca_data_feed)
    if update.chart_lab_default_symbol is not None:
        changes["chart_lab_default_symbol"] = update.chart_lab_default_symbol.strip().upper()
    if "chart_lab_one_symbol_fakepaca" in dumped:
        changes["chart_lab_one_symbol_fakepaca"] = dumped["chart_lab_one_symbol_fakepaca"]
    if changes:
        store.update(**changes)
    return _settings_from_store(store)
