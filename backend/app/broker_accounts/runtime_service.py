from __future__ import annotations

from backend.app.broker_accounts.credential_store import (
    create_broker_credential_store_from_environment,
)
from backend.app.broker_accounts.service import BrokerAccountService
from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.persistence import SQLiteRuntimeStore


def create_broker_account_service_from_environment() -> BrokerAccountService:
    db_path = get_runtime_db_path()
    return BrokerAccountService(
        runtime_store=SQLiteRuntimeStore(db_path),
        credential_store=create_broker_credential_store_from_environment(),
    )
