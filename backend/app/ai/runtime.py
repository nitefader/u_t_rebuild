from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path

from .catalog import AIProviderCatalog


def create_ai_provider_catalog_from_environment() -> AIProviderCatalog:
    db_path = get_runtime_db_path()
    return AIProviderCatalog(store_path=db_path.with_name("ai_provider_catalog.json"))
