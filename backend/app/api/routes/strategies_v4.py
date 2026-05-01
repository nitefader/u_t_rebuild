"""HTTP routes for StrategyVersion v4.

Mounted at /api/v1/strategies/v4. Dual-track — does NOT touch legacy routes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.ai.llm_client import LLMClientError, resolve_default_llm_client
from backend.app.domain.strategy_v4 import StrategyVersionV4
from backend.app.strategies.expression_api import validate_expression
from backend.app.strategies_v4.ai_seedfill import (
    AISeedFillError,
    AISeedFillRequest,
    AISeedFillResponse,
    seed_fill_strategy,
)
from backend.app.strategies_v4.models import StrategyVersionV4Draft
from backend.app.strategies_v4.persistence import (
    StrategyV4ValidationError,
    StrategyV4VersionNotFoundError,
)
from backend.app.strategies_v4.runtime_service import (
    create_strategy_v4_service_from_environment,
)
from backend.app.strategies_v4.service import StrategyV4InUseError

if TYPE_CHECKING:
    from backend.app.ai.catalog import AIProviderCatalog

router = APIRouter(prefix="/api/v1/strategies/v4", tags=["strategies-v4"])


# ---------------------------------------------------------------------------
# AI catalog dependency — reuse the same factory pattern from ai.py routes
# ---------------------------------------------------------------------------

def _get_ai_provider_catalog() -> "AIProviderCatalog":
    from backend.app.ai.runtime import create_ai_provider_catalog_from_environment
    return create_ai_provider_catalog_from_environment()


AICatalogDependency = Annotated[Any, Depends(_get_ai_provider_catalog)]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SaveRequest(BaseModel):
    draft: StrategyVersionV4Draft


class DuplicateRequest(BaseModel):
    new_name: str


class ValidationStatusOut(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class ValidateDraftResponse(BaseModel):
    validation_status: ValidationStatusOut


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_service():  # noqa: ANN201
    return create_strategy_v4_service_from_environment()


def _version_to_dict(v: StrategyVersionV4) -> dict:
    return v.model_dump(mode="json")


def _validation_error_response(exc: StrategyV4ValidationError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "message": str(exc),
            "validation_status": {"valid": False, "errors": [str(exc)], "warnings": []},
        },
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class StrategyHeadSummary(BaseModel):
    strategy_v4_id: str
    name: str
    description: str | None
    head_version: int
    head_version_id: str
    total_versions: int
    created_at: str
    updated_at: str


@router.get("/", response_model=list[StrategyHeadSummary])
def list_all_strategies() -> list[StrategyHeadSummary]:
    """List all strategies (one row per strategy_v4_id, head version)."""
    svc = _get_service()
    rows = svc.list_all_heads()
    return [StrategyHeadSummary(**row) for row in rows]


@router.post("/draft", response_model=ValidateDraftResponse, status_code=200)
def validate_draft(body: SaveRequest) -> ValidateDraftResponse:
    """Validate a draft without persisting it."""
    svc = _get_service()
    status = svc.validate_draft(body.draft)
    return ValidateDraftResponse(
        validation_status=ValidationStatusOut(
            valid=status.valid,
            errors=list(status.errors),
            warnings=list(status.warnings),
        )
    )


@router.post("/", status_code=201)
def create_strategy(body: SaveRequest) -> dict:
    """Save a new strategy (version 1)."""
    svc = _get_service()
    try:
        version = svc.save(body.draft)
    except StrategyV4ValidationError as exc:
        raise _validation_error_response(exc) from exc
    return _version_to_dict(version)


@router.get("/{strategy_version_v4_id}")
def load_version(strategy_version_v4_id: UUID) -> dict:
    """Load a single StrategyVersionV4 by its row ID."""
    svc = _get_service()
    try:
        version = svc.get(strategy_version_v4_id)
    except StrategyV4VersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _version_to_dict(version)


@router.get("/by-strategy/{strategy_v4_id}")
def list_versions(strategy_v4_id: UUID) -> list[dict]:
    """List all versions for a strategy, ordered by version asc."""
    svc = _get_service()
    versions = svc.list(strategy_v4_id)
    return [_version_to_dict(v) for v in versions]


@router.put("/by-strategy/{strategy_v4_id}", status_code=201)
def edit_strategy(strategy_v4_id: UUID, body: SaveRequest) -> dict:
    """Append a new version to an existing strategy (version+1)."""
    svc = _get_service()
    try:
        version = svc.save(body.draft, strategy_v4_id=strategy_v4_id)
    except StrategyV4ValidationError as exc:
        raise _validation_error_response(exc) from exc
    return _version_to_dict(version)


@router.post("/{strategy_version_v4_id}/duplicate", status_code=201)
def duplicate_version(strategy_version_v4_id: UUID, body: DuplicateRequest) -> dict:
    """Duplicate a version into a new strategy (version=1)."""
    svc = _get_service()
    try:
        version = svc.duplicate(strategy_version_v4_id, new_name=body.new_name)
    except StrategyV4VersionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StrategyV4ValidationError as exc:
        raise _validation_error_response(exc) from exc
    return _version_to_dict(version)


@router.delete("/by-strategy/{strategy_v4_id}", status_code=204)
def delete_strategy(strategy_v4_id: UUID) -> None:
    """Delete an entire strategy (all versions).

    Returns 409 if any version is currently bound by a Deployment.
    """
    from backend.app.deployments.runtime_service import (
        create_deployment_service_from_environment,
    )

    svc = _get_service()
    deployment_svc = create_deployment_service_from_environment()
    try:
        svc.delete(strategy_v4_id, deployment_repo=deployment_svc._repo)
    except StrategyV4InUseError as exc:
        raise HTTPException(
            status_code=409,
            detail={"bound_deployment_ids": exc.deployment_ids},
        ) from exc


# ---------------------------------------------------------------------------
# AI seed-fill
# ---------------------------------------------------------------------------

@router.post("/ai-fill", response_model=AISeedFillResponse)
def ai_fill_strategy(
    request: AISeedFillRequest,
    catalog: AICatalogDependency,
) -> AISeedFillResponse:
    """Generate a StrategyVersionV4Draft from an operator prompt via the default AI provider.

    HTTP status codes:
      200 — draft returned (validation_status.valid may be False; operator fixes manually).
      412 — no default AI provider is configured.
      422 — LLM returned malformed or schema-invalid output.
      502 — LLM provider unreachable or returned an auth/network error.
    """
    try:
        llm_client = resolve_default_llm_client(catalog)
    except LLMClientError as exc:
        msg = str(exc)
        if "no default AI provider configured" in msg:
            raise HTTPException(status_code=412, detail=msg) from exc
        raise HTTPException(status_code=502, detail=msg) from exc

    try:
        return seed_fill_strategy(
            request,
            llm_client,
            validate_expression_fn=validate_expression,
        )
    except AISeedFillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
