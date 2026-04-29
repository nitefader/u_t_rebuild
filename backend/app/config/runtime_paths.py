from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

OPERATIONS_RUNTIME_DB_PATH_ENV = "OPERATIONS_RUNTIME_DB_PATH"
LEGACY_SQLITE_PATH_ENV = "UTOS_SQLITE_PATH"
ENVIRONMENT_ENV = "ENV"
REQUIRE_RUNTIME_DB_PATH_ENV = "OPERATIONS_REQUIRE_RUNTIME_DB_PATH"
DEFAULT_RUNTIME_DB_PATH = Path("data/runtime.db")
LEGACY_DEFAULT_SQLITE_PATH = Path("data/utos.sqlite3")

_PRODUCTION_ENV_VALUES = {"prod", "production"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


def get_runtime_db_path() -> Path:
    """Return the configured runtime DB path, with a guarded local fallback.

    Resolution order:
    1. ``OPERATIONS_RUNTIME_DB_PATH`` (canonical)
    2. ``UTOS_SQLITE_PATH`` (legacy alias used by older CLI/docs — same file as API)
    3. Default ``data/runtime.db``, or ``data/utos.sqlite3`` when the new default
       does not exist yet but the legacy file does (local migration aid only).
    """

    configured_path = os.getenv(OPERATIONS_RUNTIME_DB_PATH_ENV)
    if configured_path:
        db_path = Path(configured_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    legacy_env = os.getenv(LEGACY_SQLITE_PATH_ENV)
    if legacy_env:
        db_path = Path(legacy_env)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "%s is deprecated; set %s to the same path",
            LEGACY_SQLITE_PATH_ENV,
            OPERATIONS_RUNTIME_DB_PATH_ENV,
        )
        return db_path

    if _requires_explicit_runtime_db_path():
        raise RuntimeError(
            f"{OPERATIONS_RUNTIME_DB_PATH_ENV} is required when running in production"
        )

    db_path = DEFAULT_RUNTIME_DB_PATH
    if not db_path.exists() and LEGACY_DEFAULT_SQLITE_PATH.exists():
        logger.warning(
            "Using legacy SQLite file %s; migrate to %s or set %s",
            LEGACY_DEFAULT_SQLITE_PATH,
            DEFAULT_RUNTIME_DB_PATH,
            OPERATIONS_RUNTIME_DB_PATH_ENV,
        )
        db_path = LEGACY_DEFAULT_SQLITE_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path == DEFAULT_RUNTIME_DB_PATH:
        logger.warning("Using default runtime DB path for local development")
    return db_path


def _requires_explicit_runtime_db_path() -> bool:
    environment = os.getenv(ENVIRONMENT_ENV, "").strip().lower()
    explicit_flag = os.getenv(REQUIRE_RUNTIME_DB_PATH_ENV, "").strip().lower()
    return environment in _PRODUCTION_ENV_VALUES or explicit_flag in _TRUE_VALUES
