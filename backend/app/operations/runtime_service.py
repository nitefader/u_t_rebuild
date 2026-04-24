from __future__ import annotations

import os
from pathlib import Path

from backend.app.control_plane.service import ControlPlane
from backend.app.persistence import SQLiteRuntimeStore

from .service import OperationsCenterService


OPERATIONS_RUNTIME_DB_PATH_ENV = "OPERATIONS_RUNTIME_DB_PATH"


def create_operations_center_service_from_environment() -> OperationsCenterService:
    """Build the Operations service for API routes from explicit local config."""

    configured_path = os.getenv(OPERATIONS_RUNTIME_DB_PATH_ENV)
    if not configured_path:
        return OperationsCenterService(control_plane=ControlPlane())

    db_path = Path(configured_path)
    store = SQLiteRuntimeStore(db_path)
    return OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
    )
