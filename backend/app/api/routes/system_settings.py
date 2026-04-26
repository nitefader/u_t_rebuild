"""GET/PUT operator-editable runtime settings.

These knobs are persisted to ``data/system_settings.json`` and override
the equivalent ``ALPACA_*`` env vars. The endpoint deliberately covers
**non-secret** settings only — credentials stay in ``.env``.

Settings exposed:

- ``alpaca_use_test_stream``  — bool. Flip the market-data feed to
  Alpaca's 24/7 FAKEPACA test stream.
- ``alpaca_data_feed``        — string. ``iex`` / ``sip`` /
  ``delayed_sip`` / ``boats`` / ``overnight`` / ``otc``.
- ``chart_lab_default_symbol`` — string. Default symbol the Chart Lab
  page picks when the operator hasn't typed one.
"""

from __future__ import annotations

from typing import Any, Annotated

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.system_settings_store import SystemSettingsStore, get_store


try:  # pragma: no cover - exercised when FastAPI is installed.
    from fastapi import APIRouter, Body, Depends, HTTPException
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Body = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]


_SUPPORTED_DATA_FEEDS = {"iex", "sip", "delayed_sip", "boats", "overnight", "otc"}


class SystemSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alpaca_use_test_stream: bool = False
    alpaca_data_feed: str = "iex"
    chart_lab_default_symbol: str = Field(default="SPY", min_length=1, max_length=12)


class SystemSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpaca_use_test_stream: bool | None = None
    alpaca_data_feed: str | None = None
    chart_lab_default_symbol: str | None = Field(default=None, min_length=1, max_length=12)


def _settings_from_store(store: SystemSettingsStore) -> SystemSettings:
    raw = store.load()
    return SystemSettings(
        alpaca_use_test_stream=bool(raw.get("alpaca_use_test_stream", False)),
        alpaca_data_feed=str(raw.get("alpaca_data_feed", "iex")).lower(),
        chart_lab_default_symbol=str(raw.get("chart_lab_default_symbol", "SPY")).upper(),
    )


def _validate_data_feed(value: str) -> str:
    normalized = value.lower()
    if normalized not in _SUPPORTED_DATA_FEEDS:
        if HTTPException is None:
            raise ValueError(f"unsupported alpaca_data_feed: {value!r}")
        raise HTTPException(status_code=400, detail=f"unsupported alpaca_data_feed: {value!r}")
    return normalized


def get_settings_store() -> SystemSettingsStore:
    return get_store()


def _dependency(default: object) -> object:
    if Depends is None:
        return default
    return Depends(default)


def _body(default: object) -> object:
    if Body is None:
        return default
    return Body(default)


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/system", tags=["system"])
else:
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
    if update.alpaca_use_test_stream is not None:
        changes["alpaca_use_test_stream"] = bool(update.alpaca_use_test_stream)
    if update.alpaca_data_feed is not None:
        changes["alpaca_data_feed"] = _validate_data_feed(update.alpaca_data_feed)
    if update.chart_lab_default_symbol is not None:
        changes["chart_lab_default_symbol"] = update.chart_lab_default_symbol.strip().upper()
    if changes:
        store.update(**changes)
    return _settings_from_store(store)
