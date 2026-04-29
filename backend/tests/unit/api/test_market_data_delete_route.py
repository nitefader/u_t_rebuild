"""Hard-delete market data service — pipeline binding guard."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.api.routes.market_data import delete_market_data_service
from backend.app.market_data import MarketDataCatalogError, MarketDataServiceCatalog, MarketDataServiceWrite
from backend.app.market_data.models import DeleteMarketDataServiceRequest, MarketDataValidationStatus
from backend.app.market_data.validation import MarketDataValidationResult, alpaca_capabilities


class OkValidator:
    def validate(self, **kwargs):
        return MarketDataValidationResult(MarketDataValidationStatus.VALID, "ok", alpaca_capabilities())


def test_delete_market_data_route_blocks_when_pipeline_binds_service(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "cat.json", validator=OkValidator())
    svc = catalog.create_service(
        MarketDataServiceWrite(name="BoundSvc", provider="alpaca", api_key="aaaaaa", api_secret="aaaaaaaa")
    )
    pl = MagicMock(service_id=svc.id, display_name="Stream Hub", id=uuid4())
    pipelines = MagicMock()
    pipelines.list_pipelines.return_value = MagicMock(pipelines=(pl,))
    with pytest.raises(HTTPException) as exc:
        delete_market_data_service(
            svc.id,
            DeleteMarketDataServiceRequest(confirm_service_name=svc.name),
            catalog=catalog,
            pipelines=pipelines,
        )
    assert exc.value.status_code == 400
    assert "pipelines still bind" in exc.value.detail


def test_delete_market_data_route_removes_when_unbound(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(store_path=tmp_path / "cat2.json", validator=OkValidator())
    svc = catalog.create_service(
        MarketDataServiceWrite(name="Loose", provider="yahoo")
    )
    pipelines = MagicMock()
    pipelines.list_pipelines.return_value = MagicMock(pipelines=())
    resp = delete_market_data_service(
        svc.id,
        DeleteMarketDataServiceRequest(confirm_service_name=svc.name),
        catalog=catalog,
        pipelines=pipelines,
    )
    assert resp.service_id == svc.id
    assert resp.message == "market data service removed from catalog"
    with pytest.raises(MarketDataCatalogError):
        catalog.get_service(svc.id)
