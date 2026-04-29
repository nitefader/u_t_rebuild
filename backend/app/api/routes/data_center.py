"""Data Center HTTP API — historical dataset inspection + on-demand ingest."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.data_center.historical_catalog import (
    HistoricalBar,
    HistoricalDatasetDetail,
    HistoricalDatasetSummary,
    configure_persistence,
    get_dataset_bars,
    get_dataset_detail,
    list_dataset_summaries,
)
from backend.app.data_center.ingest_service import (
    HistoricalBarIngestRequest,
    HistoricalBarIngestService,
    YahooBarsSource,
    alpaca_bars_source_from_runtime,
)
from backend.app.persistence import SQLiteRuntimeStore

router = APIRouter(prefix="/api/v1/data-center", tags=["data-center"])


def _store() -> SQLiteRuntimeStore:
    store = SQLiteRuntimeStore(get_runtime_db_path())
    configure_persistence(store)
    return store


def _dependency(default: object) -> object:
    return Depends(default)


DataCenterStoreDependency = Annotated[Any, _dependency(_store)]


class HistoricalDatasetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HistoricalDatasetSummary]


class HistoricalBarPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    offset: int
    limit: int
    total: int
    bars: list[HistoricalBar]


class HistoricalBarIngestApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["alpaca", "yahoo"]
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    start: datetime
    end: datetime
    adjustment_policy: Literal["split_dividend_adjusted", "split_only", "raw"] = "split_dividend_adjusted"


class HistoricalBarIngestApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: UUID
    bar_count: int
    fetched_from_provider: bool
    data_quality_warnings: tuple[str, ...] = ()


@router.get("/historical-datasets", response_model=HistoricalDatasetListResponse)
def historical_datasets_list(store: DataCenterStoreDependency) -> dict[str, Any]:
    _ = store  # touch dependency so configure_persistence runs
    return HistoricalDatasetListResponse(items=list_dataset_summaries()).model_dump()


@router.post(
    "/historical-datasets/ingest",
    response_model=HistoricalBarIngestApiResponse,
)
def historical_dataset_ingest(
    request: HistoricalBarIngestApiRequest,
    store: DataCenterStoreDependency,
) -> HistoricalBarIngestApiResponse:
    sources = {
        "yahoo": YahooBarsSource(),
        "alpaca": alpaca_bars_source_from_runtime(store),
    }
    service = HistoricalBarIngestService(store=store, sources=sources)
    try:
        result = service.ensure_bars(
            HistoricalBarIngestRequest(
                provider=request.provider,
                symbol=request.symbol,
                timeframe=request.timeframe,
                start=request.start,
                end=request.end,
                adjustment_policy=request.adjustment_policy,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return HistoricalBarIngestApiResponse(
        dataset_id=result.dataset_id,
        bar_count=len(result.bars),
        fetched_from_provider=result.fetched_from_provider,
        data_quality_warnings=result.data_quality_warnings,
    )


@router.get("/historical-datasets/{dataset_id}", response_model=HistoricalDatasetDetail)
def historical_dataset_detail(dataset_id: str, store: DataCenterStoreDependency) -> dict[str, Any]:
    _ = store
    detail = get_dataset_detail(dataset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Unknown historical dataset_id")
    return detail.model_dump()


@router.get("/historical-datasets/{dataset_id}/bars", response_model=HistoricalBarPage)
def historical_dataset_bars(
    dataset_id: str,
    store: DataCenterStoreDependency,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    _ = store
    page = get_dataset_bars(dataset_id, offset=offset, limit=limit)
    if page is None:
        raise HTTPException(status_code=404, detail="Unknown historical dataset_id")
    bars, total = page
    return HistoricalBarPage(
        dataset_id=dataset_id,
        offset=offset,
        limit=limit,
        total=total,
        bars=bars,
    ).model_dump()
