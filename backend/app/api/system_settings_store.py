"""JSON-backed store for operator-editable runtime settings.

Anything in this store overrides the equivalent ``ALPACA_*`` env var so
the operator can flip the data feed, toggle the test stream, or change
the default symbol from the UI without hand-editing ``.env``.

Secrets (API key, secret key, base URL) **stay in .env**. The store
only persists non-sensitive runtime knobs.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path(os.getenv("UTOS_SYSTEM_SETTINGS_PATH", "data/system_settings.json"))


class SystemSettingsStore:
    """Tiny atomic JSON store. Lock-guarded so two requests can't tear writes."""

    SUPPORTED_KEYS = ("alpaca_use_test_stream", "alpaca_data_feed", "chart_lab_default_symbol")

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else _DEFAULT_PATH
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self._path.exists():
                return {}
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}

    def update(self, **changes: Any) -> dict[str, Any]:
        unknown = set(changes) - set(self.SUPPORTED_KEYS)
        if unknown:
            raise ValueError(f"unsupported settings: {sorted(unknown)}")
        from backend.app.persistence import write_json_atomic

        with self._lock:
            current = {}
            if self._path.exists():
                try:
                    current = json.loads(self._path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    current = {}
            for key, value in changes.items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
            write_json_atomic(self._path, current, sort_keys=True)
            return current


_default_store = SystemSettingsStore()


def get_store() -> SystemSettingsStore:
    return _default_store


def setting(key: str, *, fallback_env: str | None = None, default: Any = None) -> Any:
    """Resolve a runtime setting: env var → store → default.

    Env wins so ``.env`` edits always take effect after a uvicorn restart.
    The store is consulted only when the env var is unset/empty — it acts
    as the operator-overridable default for knobs nobody pinned in
    ``.env``. This avoids the trap where a single Settings-page Save
    silently locks subsequent ``.env`` edits out of effect.
    """
    if fallback_env is not None:
        env_value = os.getenv(fallback_env)
        if env_value not in (None, ""):
            return env_value
    value = _default_store.load().get(key)
    if value is not None and value != "":
        return value
    return default
