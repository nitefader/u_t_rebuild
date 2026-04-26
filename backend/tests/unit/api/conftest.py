"""Per-test isolation for the JSON-backed system settings store.

Without this fixture, tests that exercise system_status / chart_lab_health
read the developer's actual ``data/system_settings.json`` (whatever the
running app has persisted), so env-var assertions become flaky.
"""

from __future__ import annotations

import pytest

import backend.app.api.system_settings_store as settings_store_module


@pytest.fixture(autouse=True)
def _isolated_system_settings_store(tmp_path, monkeypatch) -> None:
    fresh = settings_store_module.SystemSettingsStore(tmp_path / "system_settings.json")
    monkeypatch.setattr(settings_store_module, "_default_store", fresh)
