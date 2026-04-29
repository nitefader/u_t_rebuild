from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import market_data
from backend.app.market_data import (
    MarketDataServiceCatalog,
    MarketDataServiceWrite,
    MarketDataValidationStatus,
    ServiceStatus,
)
from backend.app.market_data.validation import MarketDataValidationResult, yahoo_capabilities


class _AlwaysValidValidator:
    def validate(self, **kwargs):  # type: ignore[no-untyped-def]
        return MarketDataValidationResult(
            MarketDataValidationStatus.VALID,
            "validated",
            yahoo_capabilities(),
        )


def test_market_data_enable_route_restores_disabled_service(tmp_path) -> None:  # type: ignore[no-untyped-def]
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=_AlwaysValidValidator(),
    )
    service = catalog.create_service(MarketDataServiceWrite(name="Yahoo Historical", provider="yahoo"))
    catalog.validate_service(service.id)
    catalog.disable_service(service.id)

    app = FastAPI()
    app.include_router(market_data.router)
    app.dependency_overrides[market_data.get_market_data_catalog] = lambda: catalog
    client = TestClient(app)

    response = client.post(f"/api/v1/market-data/services/{service.id}/enable")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ServiceStatus.VALID
    assert body["disabled_at"] is None
