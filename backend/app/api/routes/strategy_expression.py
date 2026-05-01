"""HTTP routes for the expression engine API.

Provides three endpoints:
  POST /api/v1/strategies/expression/validate
  GET  /api/v1/strategies/expression/features
  POST /api/v1/strategies/expression/mirror
"""
from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.strategies.expression_api import (
    MirrorResult,
    ValidateResult,
    list_features,
    mirror_expression,
    validate_expression,
)
from backend.app.strategies.expression_engine.errors import ParseError

router = APIRouter(prefix="/api/v1/strategies/expression", tags=["strategy-expression"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class ValidateRequest(BaseModel):
    src: str
    variables: list[str] = Field(default_factory=list)
    timeframe_variables: list[str] = Field(default_factory=list)


class ValidationIssueOut(BaseModel):
    level: str
    message: str
    line: int | None = None
    col: int | None = None


class FeatureRequirementOut(BaseModel):
    key: str
    name: str
    namespace: str | None = None
    timeframe: str | None = None
    args: list[float]


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationIssueOut]
    warnings: list[ValidationIssueOut]
    feature_requirements: list[FeatureRequirementOut]
    variables_used: list[str]


class CatalogEntryOut(BaseModel):
    key: str
    name: str
    namespace: str
    timeframe_bound: bool
    arity: int
    arg_names: list[str]
    arg_defaults: list[Any]
    return_type: str
    description: str
    category: str


class FeaturesResponse(BaseModel):
    features: list[CatalogEntryOut]


class MirrorRequest(BaseModel):
    src: str


class MirrorResponse(BaseModel):
    mirrored_text: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_result_to_response(result: ValidateResult) -> ValidateResponse:
    return ValidateResponse(
        valid=result.valid,
        errors=[
            ValidationIssueOut(level=e.level, message=e.message, line=e.line, col=e.col)
            for e in result.errors
        ],
        warnings=[
            ValidationIssueOut(level=w.level, message=w.message, line=w.line, col=w.col)
            for w in result.warnings
        ],
        feature_requirements=[
            FeatureRequirementOut(
                key=f.key,
                name=f.name,
                namespace=f.namespace,
                timeframe=f.timeframe,
                args=list(f.args),
            )
            for f in result.feature_requirements
        ],
        variables_used=list(result.variables_used),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/validate", response_model=ValidateResponse)
def validate_endpoint(request: ValidateRequest) -> ValidateResponse:
    """Validate an expression string.

    Always returns 200 — errors are in the response payload, not HTTP status.
    """
    try:
        result = validate_expression(
            request.src,
            request.variables,
            timeframe_variable_names=request.timeframe_variables,
        )
        return _validate_result_to_response(result)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"detail": str(exc)})  # type: ignore[return-value]


@router.get("/features", response_model=FeaturesResponse)
def features_endpoint() -> FeaturesResponse:
    """Return the full feature catalog."""
    try:
        entries = list_features()
        return FeaturesResponse(
            features=[
                CatalogEntryOut(
                    key=e.key,
                    name=e.name,
                    namespace=e.namespace,
                    timeframe_bound=e.timeframe_bound,
                    arity=e.arity,
                    arg_names=list(e.arg_names),
                    arg_defaults=list(e.arg_defaults),
                    return_type=e.return_type,
                    description=e.description,
                    category=e.category,
                )
                for e in entries
            ]
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"detail": str(exc)})  # type: ignore[return-value]


@router.post("/mirror", response_model=MirrorResponse)
def mirror_endpoint(request: MirrorRequest) -> MirrorResponse:
    """Mirror an expression from long to short.

    Returns 422 if the expression cannot be mirrored (parse error, etc.).
    """
    try:
        result = mirror_expression(request.src)
        return MirrorResponse(mirrored_text=result.mirrored_text)
    except ParseError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=422, content={"detail": str(exc)})  # type: ignore[return-value]
