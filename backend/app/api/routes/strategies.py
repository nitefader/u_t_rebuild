"""Strategy CRUD routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException

from backend.app.domain import StrategyVersion
from backend.app.strategy_composer import (
    AIComposerRequest,
    ConditionParseRequest,
    ConditionParseResponse,
    FeatureCatalogItem,
    FeaturePlanPreview,
    FeaturePlanPreviewRequest,
    FeatureReferenceValidation,
    FeatureReferenceValidationRequest,
    ReuseMatchRequest,
    ReuseMatchResponse,
    StrategyDraft,
    StrategyComposerService,
    StrategyDraftSaveRequest,
    StrategyDraftSaveResponse,
)
from backend.app.strategies import (
    StrategyListResponse,
    StrategyResponse,
    StrategyService,
    StrategyServiceError,
    StrategyVersionRecord,
    StrategyWriteRequest,
)


def get_strategy_service() -> StrategyService:
    from backend.app.strategies.runtime_service import (
        create_strategy_service_from_environment,
    )

    return create_strategy_service_from_environment()


def get_strategy_v4_service() -> object:
    from backend.app.strategies_v4.runtime_service import (
        create_strategy_v4_service_from_environment,
    )

    return create_strategy_v4_service_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])

ServiceDep = Annotated[Any, _dependency(get_strategy_service)]
StrategyV4ServiceDep = Annotated[Any, _dependency(get_strategy_v4_service)]


def get_strategy_composer_service(strategy_v4_service: StrategyV4ServiceDep) -> StrategyComposerService:
    from backend.app.config.runtime_paths import get_runtime_db_path
    from backend.app.execution_plans import ExecutionPlanRepository
    from backend.app.strategy_controls import StrategyControlsRepository

    db_path = get_runtime_db_path()
    return StrategyComposerService(
        strategy_v4_service=strategy_v4_service,
        strategy_controls_repository=StrategyControlsRepository(db_path),
        execution_plan_repository=ExecutionPlanRepository(db_path),
    )


ComposerDep = Annotated[Any, _dependency(get_strategy_composer_service)]


def _err(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


@router.get("", response_model=StrategyListResponse)
def list_strategies(service: ServiceDep) -> StrategyListResponse:
    return StrategyListResponse(strategies=service.list_strategies())


@router.post("", response_model=StrategyResponse)
def create_strategy(request: StrategyWriteRequest, service: ServiceDep) -> StrategyResponse:
    strategy = service.create_strategy(request)
    return StrategyResponse(strategy=strategy, versions=())


@router.get("/builder/features", response_model=tuple[FeatureCatalogItem, ...])
def list_supported_features(composer: ComposerDep) -> tuple[FeatureCatalogItem, ...]:
    return composer.feature_catalog()


@router.get("/builder/features/aliases", response_model=dict[str, str])
def list_feature_aliases(composer: ComposerDep) -> dict[str, str]:
    return composer.feature_aliases()


@router.post("/builder/features/validate", response_model=FeatureReferenceValidation)
def validate_feature_references(
    request: FeatureReferenceValidationRequest,
    composer: ComposerDep,
) -> FeatureReferenceValidation:
    return composer.validate_feature_refs(request)


@router.post("/builder/features/plan-preview", response_model=FeaturePlanPreview)
def preview_feature_plan(
    request: FeaturePlanPreviewRequest,
    composer: ComposerDep,
) -> FeaturePlanPreview:
    return composer.feature_plan_preview(request)


@router.post("/builder/conditions/parse", response_model=ConditionParseResponse)
def parse_condition_tree(
    request: ConditionParseRequest,
    composer: ComposerDep,
) -> ConditionParseResponse:
    return composer.parse_condition(request)


@router.post("/builder/reuse-matches", response_model=ReuseMatchResponse)
def find_reuse_matches(
    request: ReuseMatchRequest,
    composer: ComposerDep,
) -> ReuseMatchResponse:
    return composer.reuse_matches(request)


@router.post("/composer/drafts", response_model=StrategyDraftSaveResponse)
def save_strategy_draft(
    request: StrategyDraftSaveRequest,
    composer: ComposerDep,
) -> StrategyDraftSaveResponse:
    try:
        return composer.save_draft(request)
    except ValueError as exc:
        raise _err(str(exc)) from exc


@router.post("/composer/preview", response_model=StrategyDraft)
def compose_strategy_draft(
    request: AIComposerRequest,
    composer: ComposerDep,
) -> StrategyDraft:
    return composer.compose(request)


@router.get("/{strategy_id}", response_model=StrategyResponse)
def get_strategy(strategy_id: UUID, service: ServiceDep) -> StrategyResponse:
    try:
        return service.get_strategy(strategy_id)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc


@router.patch("/{strategy_id}", response_model=StrategyResponse)
def update_strategy(strategy_id: UUID, request: StrategyWriteRequest, service: ServiceDep) -> StrategyResponse:
    try:
        strategy = service.update_strategy(strategy_id, request)
        versions = service.list_versions(strategy_id)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc
    return StrategyResponse(strategy=strategy, versions=versions)


@router.post("/{strategy_id}/delete", status_code=204)
def delete_strategy(strategy_id: UUID, service: ServiceDep) -> None:
    try:
        service.delete_strategy(strategy_id)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc


@router.post("/{strategy_id}/deprecate", response_model=StrategyResponse)
def deprecate_strategy(strategy_id: UUID, service: ServiceDep) -> StrategyResponse:
    try:
        strategy = service.deprecate_strategy(strategy_id)
        versions = service.list_versions(strategy_id)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc
    return StrategyResponse(strategy=strategy, versions=versions)


@router.get("/{strategy_id}/versions", response_model=tuple[StrategyVersionRecord, ...])
def list_versions(strategy_id: UUID, service: ServiceDep) -> tuple[StrategyVersionRecord, ...]:
    return service.list_versions(strategy_id)


@router.post("/{strategy_id}/versions", response_model=StrategyVersionRecord)
def add_version(strategy_id: UUID, payload: StrategyVersion, service: ServiceDep) -> StrategyVersionRecord:
    try:
        return service.add_version(strategy_id, payload)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc


@router.get("/{strategy_id}/versions/{version_id}", response_model=StrategyVersionRecord)
def get_version(strategy_id: UUID, version_id: UUID, service: ServiceDep) -> StrategyVersionRecord:
    try:
        record = service.get_version(version_id)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc
    if record.strategy_id != strategy_id:
        raise _err("strategy_version does not belong to this strategy")
    return record


@router.patch("/{strategy_id}/versions/{version_id}", response_model=StrategyVersionRecord)
def edit_version(
    strategy_id: UUID,
    version_id: UUID,
    payload: StrategyVersion,
    service: ServiceDep,
) -> StrategyVersionRecord:
    try:
        return service.edit_version(strategy_id, version_id, payload)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc


@router.post("/{strategy_id}/versions/{version_id}/freeze", response_model=StrategyVersionRecord)
def freeze_version(
    strategy_id: UUID,
    version_id: UUID,
    service: ServiceDep,
    x_operator_session_id: str | None = Header(default=None, alias="X-Operator-Session-Id"),
) -> StrategyVersionRecord:
    try:
        record = service.get_version(version_id)
        if record.strategy_id != strategy_id:
            raise _err("strategy_version does not belong to this strategy")
        return service.freeze_version(version_id, frozen_by=x_operator_session_id)
    except StrategyServiceError as exc:
        raise _err(str(exc)) from exc


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()
