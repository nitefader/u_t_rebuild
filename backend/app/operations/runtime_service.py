from __future__ import annotations

import os
from pathlib import Path

from backend.app.control_plane.service import ControlPlane
from backend.app.persistence import SQLiteRuntimeStore

from .demo_seed import (
    DEMO_ACCOUNT_ID,
    DEMO_DEPLOYMENT_ID,
    DEMO_GOVERNOR_ID,
    default_operations_demo_db_path,
    demo_deployment_context,
    seed_operations_demo_store,
)
from .service import OperationsCenterService


OPERATIONS_RUNTIME_DB_PATH_ENV = "OPERATIONS_RUNTIME_DB_PATH"
SEED_OPERATIONS_DEMO_ENV = "SEED_OPERATIONS_DEMO"


def create_operations_center_service_from_environment() -> OperationsCenterService:
    """Build the Operations service for API routes from explicit local config."""

    demo_enabled = os.getenv(SEED_OPERATIONS_DEMO_ENV) == "1"
    configured_path = os.getenv(OPERATIONS_RUNTIME_DB_PATH_ENV)
    if not demo_enabled and not configured_path:
        return OperationsCenterService(control_plane=ControlPlane())

    db_path = Path(configured_path) if configured_path else default_operations_demo_db_path()
    if demo_enabled:
        seed_operations_demo_store(db_path)

    store = SQLiteRuntimeStore(db_path)
    return OperationsCenterService(
        control_plane=ControlPlane(state_store=store),
        runtime_store=store,
        deployments=(demo_deployment_context(),) if demo_enabled else (),
        governor_id=DEMO_GOVERNOR_ID if demo_enabled else "portfolio-governor",
        deployment_account_ids={DEMO_DEPLOYMENT_ID: DEMO_ACCOUNT_ID} if demo_enabled else {},
    )
