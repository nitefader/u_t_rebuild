from __future__ import annotations

from backend.app.config.runtime_paths import OPERATIONS_RUNTIME_DB_PATH_ENV, get_runtime_db_path
from backend.app.control_plane.service import ControlPlane
from backend.app.persistence import SQLiteRuntimeStore

from .service import OperationsCenterService


def create_operations_center_service_from_environment() -> OperationsCenterService:
    """Build the Operations service for API routes from shared runtime config."""

    db_path = get_runtime_db_path()
    store = SQLiteRuntimeStore(db_path)
    return OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
    )
