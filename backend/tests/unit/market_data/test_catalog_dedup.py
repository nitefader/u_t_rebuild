from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.market_data import (
    MarketDataCatalogError,
    MarketDataServiceCatalog,
    MarketDataServiceWrite,
    Provider,
)


def _write(path: Path, services: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"market_data_services": services}, indent=2), encoding="utf-8")


def test_create_service_with_matching_credentials_returns_existing(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    first = catalog.create_service(
        MarketDataServiceWrite(name="Alpaca", provider=Provider.ALPACA, api_key="K", api_secret="SECRET")
    )
    # Same name + same credentials → idempotent return.
    second = catalog.create_service(
        MarketDataServiceWrite(name="Alpaca", provider=Provider.ALPACA, api_key="K", api_secret="SECRET")
    )
    assert second.id == first.id
    assert len(catalog.list_services().services) == 1


def test_create_service_with_matching_credentials_but_different_name_raises(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    catalog.create_service(
        MarketDataServiceWrite(name="Alpaca", provider=Provider.ALPACA, api_key="K", api_secret="SECRET")
    )
    with pytest.raises(MarketDataCatalogError) as excinfo:
        catalog.create_service(
            MarketDataServiceWrite(name="Alpaca (from .env)", provider=Provider.ALPACA, api_key="K", api_secret="SECRET")
        )
    assert "duplicates are not allowed" in str(excinfo.value)


def test_create_service_with_different_credentials_creates_separate_records(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    catalog.create_service(
        MarketDataServiceWrite(name="Alpaca paper-1", provider=Provider.ALPACA, api_key="K1", api_secret="S1")
    )
    catalog.create_service(
        MarketDataServiceWrite(name="Alpaca paper-2", provider=Provider.ALPACA, api_key="K2", api_secret="S2")
    )
    assert len(catalog.list_services().services) == 2


def test_load_dedupes_legacy_credentials_ref_prefix_difference(tmp_path) -> None:
    """Legacy ``service-credential:HASH`` and current ``market-data-credential:HASH``
    referring to the same secret get collapsed on load."""
    same_hash = "deadbeefcafe"
    legacy_ts = "2026-04-25T00:58:14Z"
    new_ts = "2026-04-26T00:28:00Z"
    _write(
        tmp_path / "catalog.json",
        [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Algo Trading in Alpaca",
                "provider": "alpaca",
                "credentials_ref": f"service-credential:{same_hash}",
                "is_default": True,
                "created_at": legacy_ts,
                "updated_at": legacy_ts,
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "Alpaca (from .env)",
                "provider": "alpaca",
                "credentials_ref": f"market-data-credential:{same_hash}",
                "is_default": False,
                "created_at": new_ts,
                "updated_at": new_ts,
            },
        ],
    )
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    services = catalog.list_services().services
    assert len(services) == 1
    kept = services[0]
    # Oldest (Algo Trading) wins so the operator's name + default survive.
    assert kept.name == "Algo Trading in Alpaca"
    assert kept.is_default is True


def test_load_preserves_default_when_legacy_was_not_default_but_new_was(tmp_path) -> None:
    """If only the *newer* duplicate carried is_default, propagate it onto the kept oldest record."""
    h = "abc123"
    _write(
        tmp_path / "catalog.json",
        [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Old",
                "provider": "alpaca",
                "credentials_ref": f"service-credential:{h}",
                "is_default": False,
                "created_at": "2026-04-25T00:00:00Z",
                "updated_at": "2026-04-25T00:00:00Z",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "name": "New",
                "provider": "alpaca",
                "credentials_ref": f"market-data-credential:{h}",
                "is_default": True,
                "created_at": "2026-04-26T00:00:00Z",
                "updated_at": "2026-04-26T00:00:00Z",
            },
        ],
    )
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    services = catalog.list_services().services
    assert len(services) == 1
    assert services[0].name == "Old"
    assert services[0].is_default is True


def test_find_by_credentials_returns_none_for_unknown_provider_or_creds(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "catalog.json")
    catalog.create_service(
        MarketDataServiceWrite(name="Alpaca", provider=Provider.ALPACA, api_key="K", api_secret="SECRET")
    )
    from backend.app.market_data.catalog import _credential_ref

    # Same provider, different secret.
    assert catalog.find_by_credentials(Provider.ALPACA, _credential_ref("OTHER")) is None
    # Yahoo (unknown provider in catalog).
    assert catalog.find_by_credentials(Provider.YAHOO, _credential_ref("K")) is None
    # Empty / None credentials.
    assert catalog.find_by_credentials(Provider.ALPACA, None) is None
