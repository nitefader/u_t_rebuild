from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

OPERATIONS_RUNTIME_DB_PATH_ENV = "OPERATIONS_RUNTIME_DB_PATH"
ENVIRONMENT_ENV = "ENV"
REQUIRE_RUNTIME_DB_PATH_ENV = "OPERATIONS_REQUIRE_RUNTIME_DB_PATH"
DEFAULT_RUNTIME_DB_PATH = Path("data/runtime.db")

_PRODUCTION_ENV_VALUES = {"prod", "production"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


def get_runtime_db_path() -> Path:
    """Return the configured runtime DB path, with a guarded local fallback."""

    configured_path = os.getenv(OPERATIONS_RUNTIME_DB_PATH_ENV)
    if configured_path:
        db_path = Path(configured_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    if _requires_explicit_runtime_db_path():
        raise RuntimeError(
            f"{OPERATIONS_RUNTIME_DB_PATH_ENV} is required when running in production"
        )

    db_path = DEFAULT_RUNTIME_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.warning("Using default runtime DB path for local development")
    return db_path


def _requires_explicit_runtime_db_path() -> bool:
    environment = os.getenv(ENVIRONMENT_ENV, "").strip().lower()
    explicit_flag = os.getenv(REQUIRE_RUNTIME_DB_PATH_ENV, "").strip().lower()
    return environment in _PRODUCTION_ENV_VALUES or explicit_flag in _TRUE_VALUES
