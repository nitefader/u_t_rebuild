from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.config.runtime_paths import (
    DEFAULT_RUNTIME_DB_PATH,
    ENVIRONMENT_ENV,
    LEGACY_SQLITE_PATH_ENV,
    OPERATIONS_RUNTIME_DB_PATH_ENV,
    REQUIRE_RUNTIME_DB_PATH_ENV,
    get_runtime_db_path,
)


def test_env_var_provided_is_used(tmp_path, monkeypatch) -> None:
    configured_path = tmp_path / "nested" / "runtime.sqlite3"
    monkeypatch.setenv(OPERATIONS_RUNTIME_DB_PATH_ENV, str(configured_path))
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    monkeypatch.delenv(LEGACY_SQLITE_PATH_ENV, raising=False)

    assert get_runtime_db_path() == configured_path
    assert configured_path.parent.exists()


def test_legacy_utos_sqlite_env_is_used_when_canonical_unset(tmp_path, monkeypatch, caplog) -> None:
    legacy = tmp_path / "legacy.sqlite"
    monkeypatch.delenv(OPERATIONS_RUNTIME_DB_PATH_ENV, raising=False)
    monkeypatch.setenv(LEGACY_SQLITE_PATH_ENV, str(legacy))
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_RUNTIME_DB_PATH_ENV, raising=False)

    assert get_runtime_db_path() == legacy
    assert "deprecated" in caplog.text.lower()


def test_missing_env_in_dev_falls_back_to_default(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(OPERATIONS_RUNTIME_DB_PATH_ENV, raising=False)
    monkeypatch.delenv(LEGACY_SQLITE_PATH_ENV, raising=False)
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_RUNTIME_DB_PATH_ENV, raising=False)

    assert get_runtime_db_path() == DEFAULT_RUNTIME_DB_PATH
    assert "Using default runtime DB path for local development" in caplog.text


def test_missing_env_in_dev_creates_default_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(OPERATIONS_RUNTIME_DB_PATH_ENV, raising=False)
    monkeypatch.delenv(LEGACY_SQLITE_PATH_ENV, raising=False)
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)
    monkeypatch.delenv(REQUIRE_RUNTIME_DB_PATH_ENV, raising=False)

    db_path = get_runtime_db_path()

    assert db_path == Path("data/runtime.db")
    assert (tmp_path / "data").is_dir()


def test_production_mode_without_env_raises(monkeypatch) -> None:
    monkeypatch.delenv(OPERATIONS_RUNTIME_DB_PATH_ENV, raising=False)
    monkeypatch.setenv(ENVIRONMENT_ENV, "production")
    monkeypatch.delenv(REQUIRE_RUNTIME_DB_PATH_ENV, raising=False)

    with pytest.raises(RuntimeError, match="OPERATIONS_RUNTIME_DB_PATH is required"):
        get_runtime_db_path()


def test_explicit_runtime_db_required_flag_without_env_raises(monkeypatch) -> None:
    monkeypatch.delenv(OPERATIONS_RUNTIME_DB_PATH_ENV, raising=False)
    monkeypatch.delenv(ENVIRONMENT_ENV, raising=False)
    monkeypatch.setenv(REQUIRE_RUNTIME_DB_PATH_ENV, "true")

    with pytest.raises(RuntimeError, match="OPERATIONS_RUNTIME_DB_PATH is required"):
        get_runtime_db_path()
