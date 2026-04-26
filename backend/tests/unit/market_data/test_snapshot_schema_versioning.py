"""Schema-version contract for the JSON-backed snapshots.

Per DE round-2 requirement: each persisted snapshot carries a
``schema_version``. ``_load`` must accept older payloads (no field, or a
lower number) silently and refuse newer payloads with an operator-readable
error rather than a Pydantic ``extra="forbid"`` traceback.
"""

from __future__ import annotations

import json

import pytest

from backend.app.ai.catalog import (
    AIProviderCatalog,
    AIProviderCatalogError,
    CURRENT_AI_PROVIDER_CATALOG_SCHEMA_VERSION,
)
from backend.app.market_data.catalog import (
    CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION,
    MarketDataCatalogError,
    MarketDataServiceCatalog,
)
from backend.app.market_data.pipeline_registry import (
    CURRENT_PIPELINE_REGISTRY_SCHEMA_VERSION,
    MarketDataPipelineRegistry,
    PipelineRegistryError,
)


def _write(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Market-data catalog
# ---------------------------------------------------------------------------


def test_market_data_catalog_loads_legacy_v0_payload(tmp_path) -> None:
    """A pre-versioning JSON file (no ``schema_version`` field) must load fine."""
    _write(tmp_path / "catalog.json", {"market_data_services": []})
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    assert catalog.list_services().services == ()


def test_market_data_catalog_save_writes_current_schema_version(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    catalog._save()
    payload = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION


def test_market_data_catalog_rejects_newer_schema_version_with_clear_error(tmp_path) -> None:
    _write(
        tmp_path / "catalog.json",
        {"schema_version": 999, "market_data_services": []},
    )
    with pytest.raises(MarketDataCatalogError) as excinfo:
        MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    assert "schema_version=999" in str(excinfo.value)
    assert "rolling back" in str(excinfo.value)


def test_market_data_catalog_ignores_unknown_top_level_fields(tmp_path) -> None:
    """A future binary writes an extra envelope field; older readers ignore it."""
    _write(
        tmp_path / "catalog.json",
        {
            "schema_version": CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION,
            "market_data_services": [],
            "future_field": {"experimental": True},
        },
    )
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    assert catalog.list_services().services == ()


# ---------------------------------------------------------------------------
# AI provider catalog
# ---------------------------------------------------------------------------


def test_ai_provider_catalog_loads_legacy_v0_payload(tmp_path) -> None:
    _write(tmp_path / "ai.json", {"ai_services": []})
    catalog = AIProviderCatalog(store_path=tmp_path / "ai.json")
    assert catalog.list_services().services == ()


def test_ai_provider_catalog_save_writes_current_schema_version(tmp_path) -> None:
    catalog = AIProviderCatalog(store_path=tmp_path / "ai.json")
    catalog._save()
    payload = json.loads((tmp_path / "ai.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == CURRENT_AI_PROVIDER_CATALOG_SCHEMA_VERSION


def test_ai_provider_catalog_rejects_newer_schema_version(tmp_path) -> None:
    _write(tmp_path / "ai.json", {"schema_version": 99, "ai_services": []})
    with pytest.raises(AIProviderCatalogError) as excinfo:
        AIProviderCatalog(store_path=tmp_path / "ai.json")
    assert "schema_version=99" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Pipeline registry
# ---------------------------------------------------------------------------


def test_pipeline_registry_loads_legacy_v0_payload(tmp_path) -> None:
    _write(tmp_path / "pipelines.json", {"pipelines": []})
    registry = MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")
    assert registry.list_pipelines().pipelines == ()


def test_pipeline_registry_save_writes_current_schema_version(tmp_path) -> None:
    registry = MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")
    registry._save()
    payload = json.loads((tmp_path / "pipelines.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == CURRENT_PIPELINE_REGISTRY_SCHEMA_VERSION


def test_pipeline_registry_rejects_newer_schema_version(tmp_path) -> None:
    _write(tmp_path / "pipelines.json", {"schema_version": 42, "pipelines": []})
    with pytest.raises(PipelineRegistryError) as excinfo:
        MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")
    assert "schema_version=42" in str(excinfo.value)
