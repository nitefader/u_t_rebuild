from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path

from .catalog import MarketDataServiceCatalog


def create_market_data_catalog_from_environment() -> MarketDataServiceCatalog:
    db_path = get_runtime_db_path()
    return MarketDataServiceCatalog(store_path=db_path.with_name("market_data_catalog.json"))
