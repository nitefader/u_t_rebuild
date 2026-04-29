from __future__ import annotations

from pathlib import Path
from uuid import UUID

from backend.app.broker_accounts.credential_store import BrokerCredentialStore, CredentialStoreError
from backend.app.config.runtime_paths import get_runtime_db_path


class MarketDataCredentialStore:
    """Encrypted-at-rest credentials for market-data provider records."""

    def __init__(self, *, store_path: str | Path) -> None:
        self._store = BrokerCredentialStore(store_path=store_path)

    def put(self, service_id: UUID, *, api_key: str, api_secret: str) -> None:
        self._store.put(service_id, api_key=api_key, api_secret=api_secret)

    def get(self, service_id: UUID) -> tuple[str, str]:
        try:
            return self._store.get(service_id)
        except CredentialStoreError as exc:
            raise CredentialStoreError(f"no stored market data credentials for service {service_id}") from exc

    def has(self, service_id: UUID) -> bool:
        return self._store.has(service_id)

    def delete(self, service_id: UUID) -> None:
        self._store.delete(service_id)


def create_market_data_credential_store_from_environment() -> MarketDataCredentialStore:
    db_path = get_runtime_db_path()
    return MarketDataCredentialStore(store_path=db_path.with_name("market_data_credentials.enc"))
