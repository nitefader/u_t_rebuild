from __future__ import annotations

import os
from pathlib import Path

from backend.app.broker_accounts.service import BrokerAccountService
from backend.app.operations.runtime_service import OPERATIONS_RUNTIME_DB_PATH_ENV
from backend.app.persistence import SQLiteRuntimeStore


def create_broker_account_service_from_environment() -> BrokerAccountService:
    configured_path = os.getenv(OPERATIONS_RUNTIME_DB_PATH_ENV)
    if not configured_path:
        raise RuntimeError(f"{OPERATIONS_RUNTIME_DB_PATH_ENV} is required to create broker accounts")
    return BrokerAccountService(runtime_store=SQLiteRuntimeStore(Path(configured_path)))
