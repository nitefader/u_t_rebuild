from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.ai import AIProviderCatalogError, AIProviderStatus, AIServiceRecord
from backend.app.ai.runtime import create_ai_provider_catalog_from_environment
from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.domain import (
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSource,
    RiskPlanStatus,
    RiskPlanTier,
    RiskPlanVersion,
    RiskPlanVersionStatus,
)
from backend.app.domain._base import utc_now
from backend.app.persistence import SQLiteRuntimeStore


router = APIRouter(tags=["risk-plans"])


class RiskPlanCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str | None = None
    risk_score: int = Field(ge=0, le=10)
    risk_tier: RiskPlanTier
    config: RiskPlanConfig
    created_by: str | None = None
    ai_generated: bool = False
    ai_summary: str | None = None
    source: RiskPlanSource = RiskPlanSource.MANUAL


class RiskPlanPatchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    risk_score: int | None = Field(default=None, ge=0, le=10)
    risk_tier: RiskPlanTier | None = None
    created_by: str | None = None
    ai_summary: str | None = None


class RiskPlanVersionCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    config: RiskPlanConfig


class RiskPlanActivateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_plan_version_id: UUID | None = None


class RiskPlanAIDraftRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(min_length=1)
    created_by: str | None = None


class RiskPlanAIDraftResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_plan: RiskPlan
    risk_plan_version: RiskPlanVersion
    warnings: tuple[str, ...] = ()
    ai_provider_id: UUID
    ai_provider_name: str
    boundary_guardrails: tuple[str, ...] = (
        "AI drafts are never activated automatically.",
        "AI drafts are never assigned to an Account automatically.",
        "RiskResolver remains the only service that can produce RiskDecisionCard results.",
        "AI output cannot hide deterministic validation warnings.",
    )


class AccountRiskPlanAssignmentRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_plan_id: UUID
    risk_plan_version_id: UUID


class RiskPlanListItem(RiskPlan):
    active_version_id: UUID | None = None
    active_version: RiskPlanVersion | None = None
    linked_account_count: int = Field(default=0, ge=0)
    last_used_at: datetime | None = None


class RiskPlanLinkedAccount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    account_name: str
    account_mode: str
    is_default: bool = True
    last_risk_decision_at: datetime | None = None


class RiskPlanBacktestUsage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    started_at: datetime
    sharpe: float | None = None
    max_drawdown: float | None = None
    total_return: float | None = None
    monte_carlo_summary: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()


class RiskPlanTopRejectionReason(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str
    count: int = Field(ge=0)


class RiskPlanDecisionStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total: int = 0
    approved: int = 0
    rejected: int = 0
    reduced: int = 0
    capped: int = 0
    skipped: int = 0
    requires_operator: int = 0
    top_rejection_reasons: tuple[RiskPlanTopRejectionReason, ...] = ()


class RiskPlanListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_plans: tuple[RiskPlanListItem, ...] = ()


class RiskPlanDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_plan: RiskPlan
    versions: tuple[RiskPlanVersion, ...] = ()
    active_version_id: UUID | None = None
    active_version: RiskPlanVersion | None = None
    linked_accounts: tuple[RiskPlanLinkedAccount, ...] = ()
    backtest_usage: tuple[RiskPlanBacktestUsage, ...] = ()
    decision_stats: RiskPlanDecisionStats = Field(default_factory=RiskPlanDecisionStats)


class RiskPlanVersionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    versions: tuple[RiskPlanVersion, ...] = ()


class AccountRiskPlanAssignmentResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    risk_plan: RiskPlan | None = None
    risk_plan_version: RiskPlanVersion | None = None


def get_risk_plan_store() -> SQLiteRuntimeStore:
    return SQLiteRuntimeStore(get_runtime_db_path())


def get_risk_plan_ai_catalog():
    return create_ai_provider_catalog_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


RiskPlanStoreDependency = Annotated[Any, _dependency(get_risk_plan_store)]
RiskPlanAICatalogDependency = Annotated[Any, _dependency(get_risk_plan_ai_catalog)]


@router.get("/api/v1/risk-plans", response_model=RiskPlanListResponse)
def list_risk_plans(
    store: RiskPlanStoreDependency,
    status: RiskPlanStatus | None = Query(default=None),
    risk_tier: RiskPlanTier | None = Query(default=None),
    source: RiskPlanSource | None = Query(default=None),
    account_id: UUID | None = Query(default=None),
) -> RiskPlanListResponse:
    plans = store.list_risk_plans(
        status=status.value if status is not None else None,
        risk_tier=risk_tier.value if risk_tier is not None else None,
        source=source.value if source is not None else None,
        account_id=account_id,
    )
    return RiskPlanListResponse(
        risk_plans=tuple(_risk_plan_list_item(store, risk_plan) for risk_plan in plans)
    )


@router.post("/api/v1/risk-plans", response_model=RiskPlanDetailResponse)
def create_risk_plan(
    request: RiskPlanCreateRequest,
    store: RiskPlanStoreDependency,
) -> RiskPlanDetailResponse:
    now = utc_now()
    risk_plan = RiskPlan(
        name=request.name,
        description=request.description,
        status=RiskPlanStatus.DRAFT,
        risk_score=request.risk_score,
        risk_tier=request.risk_tier,
        version=1,
        created_at=now,
        updated_at=now,
        created_by=request.created_by,
        ai_generated=request.ai_generated,
        ai_summary=request.ai_summary,
        source=request.source,
    )
    version = RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        status=RiskPlanVersionStatus.DRAFT,
        config=request.config,
        created_at=now,
    )
    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(version)
    return _risk_plan_detail_response(store, risk_plan)


@router.post("/api/v1/risk-plans/ai-draft", response_model=RiskPlanAIDraftResponse)
def draft_risk_plan_with_ai(
    request: RiskPlanAIDraftRequest,
    catalog: RiskPlanAICatalogDependency,
) -> RiskPlanAIDraftResponse:
    provider = _default_ai_provider_or_400(catalog)
    draft = _draft_from_prompt(request.prompt, created_by=request.created_by)
    return RiskPlanAIDraftResponse(
        risk_plan=draft["risk_plan"],
        risk_plan_version=draft["risk_plan_version"],
        warnings=draft["warnings"],
        ai_provider_id=provider.id,
        ai_provider_name=provider.name,
    )


@router.get("/api/v1/risk-plans/{risk_plan_id}", response_model=RiskPlanDetailResponse)
def get_risk_plan(risk_plan_id: UUID, store: RiskPlanStoreDependency) -> RiskPlanDetailResponse:
    risk_plan = _load_risk_plan_or_404(store, risk_plan_id)
    return _risk_plan_detail_response(store, risk_plan)


@router.patch("/api/v1/risk-plans/{risk_plan_id}", response_model=RiskPlanDetailResponse)
def patch_risk_plan(
    risk_plan_id: UUID,
    request: RiskPlanPatchRequest,
    store: RiskPlanStoreDependency,
) -> RiskPlanDetailResponse:
    risk_plan = _load_risk_plan_or_404(store, risk_plan_id)
    if risk_plan.status != RiskPlanStatus.DRAFT:
        raise HTTPException(status_code=400, detail="only draft RiskPlans can be edited")
    updated = risk_plan.model_copy(
        update={
            key: value
            for key, value in {
                "name": request.name,
                "description": request.description if request.description is not None else risk_plan.description,
                "risk_score": request.risk_score,
                "risk_tier": request.risk_tier,
                "created_by": request.created_by if request.created_by is not None else risk_plan.created_by,
                "ai_summary": request.ai_summary if request.ai_summary is not None else risk_plan.ai_summary,
                "updated_at": utc_now(),
            }.items()
            if value is not None
        }
    )
    store.save_risk_plan(updated)
    return _risk_plan_detail_response(store, updated)


@router.post("/api/v1/risk-plans/{risk_plan_id}/versions", response_model=RiskPlanVersion)
def create_risk_plan_version(
    risk_plan_id: UUID,
    request: RiskPlanVersionCreateRequest,
    store: RiskPlanStoreDependency,
) -> RiskPlanVersion:
    risk_plan = _load_risk_plan_or_404(store, risk_plan_id)
    if risk_plan.status == RiskPlanStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="archived RiskPlans cannot receive new versions")
    existing = store.list_risk_plan_versions(risk_plan_id)
    version_number = max((version.version for version in existing), default=0) + 1
    version = RiskPlanVersion(
        risk_plan_id=risk_plan_id,
        version=version_number,
        status=RiskPlanVersionStatus.DRAFT,
        config=request.config,
    )
    store.save_risk_plan_version(version)
    store.save_risk_plan(risk_plan.model_copy(update={"version": version_number, "updated_at": utc_now()}))
    return version


@router.get("/api/v1/risk-plans/{risk_plan_id}/versions", response_model=RiskPlanVersionListResponse)
def list_risk_plan_versions(
    risk_plan_id: UUID,
    store: RiskPlanStoreDependency,
) -> RiskPlanVersionListResponse:
    _load_risk_plan_or_404(store, risk_plan_id)
    return RiskPlanVersionListResponse(versions=store.list_risk_plan_versions(risk_plan_id))


@router.post("/api/v1/risk-plans/{risk_plan_id}/activate", response_model=RiskPlanDetailResponse)
def activate_risk_plan(
    risk_plan_id: UUID,
    request: RiskPlanActivateRequest,
    store: RiskPlanStoreDependency,
) -> RiskPlanDetailResponse:
    risk_plan = _load_risk_plan_or_404(store, risk_plan_id)
    versions = store.list_risk_plan_versions(risk_plan_id)
    if not versions:
        raise HTTPException(status_code=400, detail="RiskPlan has no versions to activate")
    selected = _select_version(versions, request.risk_plan_version_id)
    now = utc_now()
    for version in versions:
        if version.risk_plan_version_id == selected.risk_plan_version_id:
            store.save_risk_plan_version(
                version.model_copy(update={"status": RiskPlanVersionStatus.ACTIVE, "activated_at": now})
            )
        elif version.status == RiskPlanVersionStatus.ACTIVE:
            store.save_risk_plan_version(
                version.model_copy(update={"status": RiskPlanVersionStatus.DEPRECATED, "archived_at": now})
            )
    updated_plan = risk_plan.model_copy(
        update={
            "status": RiskPlanStatus.ACTIVE,
            "version": selected.version,
            "updated_at": now,
        }
    )
    store.save_risk_plan(updated_plan)
    return _risk_plan_detail_response(store, updated_plan)


@router.post("/api/v1/risk-plans/{risk_plan_id}/archive", response_model=RiskPlanDetailResponse)
def archive_risk_plan(risk_plan_id: UUID, store: RiskPlanStoreDependency) -> RiskPlanDetailResponse:
    risk_plan = _load_risk_plan_or_404(store, risk_plan_id)
    now = utc_now()
    for version in store.list_risk_plan_versions(risk_plan_id):
        if version.status != RiskPlanVersionStatus.DEPRECATED:
            store.save_risk_plan_version(
                version.model_copy(update={"status": RiskPlanVersionStatus.DEPRECATED, "archived_at": now})
            )
    archived = risk_plan.model_copy(update={"status": RiskPlanStatus.ARCHIVED, "updated_at": now})
    store.save_risk_plan(archived)
    return _risk_plan_detail_response(store, archived)


@router.get("/api/v1/accounts/{account_id}/risk-plan", response_model=AccountRiskPlanAssignmentResponse)
def get_account_risk_plan(
    account_id: UUID,
    store: RiskPlanStoreDependency,
) -> AccountRiskPlanAssignmentResponse:
    account = _load_account_or_404(store, account_id)
    if account.default_risk_plan_id is None or account.default_risk_plan_version_id is None:
        return AccountRiskPlanAssignmentResponse(account_id=account_id)
    return AccountRiskPlanAssignmentResponse(
        account_id=account_id,
        risk_plan=_load_risk_plan_or_404(store, account.default_risk_plan_id),
        risk_plan_version=_load_risk_plan_version_or_404(store, account.default_risk_plan_version_id),
    )


@router.put("/api/v1/accounts/{account_id}/risk-plan", response_model=AccountRiskPlanAssignmentResponse)
def put_account_risk_plan(
    account_id: UUID,
    request: AccountRiskPlanAssignmentRequest,
    store: RiskPlanStoreDependency,
) -> AccountRiskPlanAssignmentResponse:
    account = _load_account_or_404(store, account_id)
    risk_plan = _load_risk_plan_or_404(store, request.risk_plan_id)
    version = _load_risk_plan_version_or_404(store, request.risk_plan_version_id)
    if version.risk_plan_id != risk_plan.risk_plan_id:
        raise HTTPException(status_code=400, detail="risk_plan_version_id does not belong to risk_plan_id")
    updated_account = account.model_copy(
        update={
            "default_risk_plan_id": risk_plan.risk_plan_id,
            "default_risk_plan_version_id": version.risk_plan_version_id,
        }
    )
    store.save_broker_account(updated_account)
    return AccountRiskPlanAssignmentResponse(
        account_id=account_id,
        risk_plan=risk_plan,
        risk_plan_version=version,
    )


def _load_risk_plan_or_404(store: SQLiteRuntimeStore, risk_plan_id: UUID) -> RiskPlan:
    try:
        return store.load_risk_plan(risk_plan_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _load_risk_plan_version_or_404(store: SQLiteRuntimeStore, risk_plan_version_id: UUID) -> RiskPlanVersion:
    try:
        return store.load_risk_plan_version(risk_plan_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _load_account_or_404(store: SQLiteRuntimeStore, account_id: UUID):
    try:
        return store.load_broker_account(account_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _select_version(versions: tuple[RiskPlanVersion, ...], risk_plan_version_id: UUID | None) -> RiskPlanVersion:
    if risk_plan_version_id is None:
        return max(versions, key=lambda version: version.version)
    for version in versions:
        if version.risk_plan_version_id == risk_plan_version_id:
            return version
    raise HTTPException(status_code=404, detail=f"unknown risk plan version: {risk_plan_version_id}")


def _risk_plan_detail_response(store: SQLiteRuntimeStore, risk_plan: RiskPlan) -> RiskPlanDetailResponse:
    versions = store.list_risk_plan_versions(risk_plan.risk_plan_id)
    active_version = _active_or_latest_draft_version(versions)
    linked_accounts = _linked_accounts_for_plan(store, risk_plan, versions)
    backtest_usage = _backtest_usage_for_plan(store, versions)
    decision_stats = _decision_stats_for_plan(store, versions)
    return RiskPlanDetailResponse(
        risk_plan=risk_plan,
        versions=versions,
        active_version_id=active_version.risk_plan_version_id if active_version is not None else None,
        active_version=active_version,
        linked_accounts=linked_accounts,
        backtest_usage=backtest_usage,
        decision_stats=decision_stats,
    )


def _risk_plan_list_item(store: SQLiteRuntimeStore, risk_plan: RiskPlan) -> RiskPlanListItem:
    versions = store.list_risk_plan_versions(risk_plan.risk_plan_id)
    active_version = _active_or_latest_draft_version(versions)
    linked_accounts = store.list_broker_accounts_by_default_risk_plan(risk_plan.risk_plan_id)
    backtest_runs = store.list_backtest_runs_for_risk_plan_versions(
        tuple(version.risk_plan_version_id for version in versions),
        limit=1,
    )
    cards = store.list_risk_decision_cards_for_risk_plan_versions(
        tuple(version.risk_plan_version_id for version in versions)
    )
    timestamps = [account.created_at for account in linked_accounts]
    timestamps.extend(run.created_at for run in backtest_runs)
    if cards:
        timestamps.append(cards[0].created_at)
    return RiskPlanListItem.model_validate(
        {
            **risk_plan.model_dump(),
            "active_version_id": active_version.risk_plan_version_id if active_version is not None else None,
            "active_version": active_version,
            "linked_account_count": len(linked_accounts),
            "last_used_at": max(timestamps) if timestamps else None,
        }
    )


def _active_or_latest_draft_version(versions: tuple[RiskPlanVersion, ...]) -> RiskPlanVersion | None:
    active_versions = [version for version in versions if version.status == RiskPlanVersionStatus.ACTIVE]
    if active_versions:
        return max(active_versions, key=lambda version: (version.version, version.created_at))
    draft_versions = [version for version in versions if version.status == RiskPlanVersionStatus.DRAFT]
    if draft_versions:
        return max(draft_versions, key=lambda version: (version.version, version.created_at))
    if versions:
        return max(versions, key=lambda version: (version.version, version.created_at))
    return None


def _linked_accounts_for_plan(
    store: SQLiteRuntimeStore,
    risk_plan: RiskPlan,
    versions: tuple[RiskPlanVersion, ...],
) -> tuple[RiskPlanLinkedAccount, ...]:
    cards = store.list_risk_decision_cards_for_risk_plan_versions(
        tuple(version.risk_plan_version_id for version in versions)
    )
    latest_by_account: dict[UUID, datetime] = {}
    for card in cards:
        if card.account_id is None:
            continue
        previous = latest_by_account.get(card.account_id)
        if previous is None or card.created_at > previous:
            latest_by_account[card.account_id] = card.created_at
    return tuple(
        RiskPlanLinkedAccount(
            account_id=account.id,
            account_name=account.display_name,
            account_mode=_readable_account_mode(account.mode.value),
            is_default=account.default_risk_plan_id == risk_plan.risk_plan_id,
            last_risk_decision_at=latest_by_account.get(account.id),
        )
        for account in store.list_broker_accounts_by_default_risk_plan(risk_plan.risk_plan_id)
    )


def _backtest_usage_for_plan(
    store: SQLiteRuntimeStore,
    versions: tuple[RiskPlanVersion, ...],
) -> tuple[RiskPlanBacktestUsage, ...]:
    runs = store.list_backtest_runs_for_risk_plan_versions(
        tuple(version.risk_plan_version_id for version in versions),
        limit=20,
    )
    return tuple(
        RiskPlanBacktestUsage(
            run_id=run.run_id,
            strategy_id=run.strategy_id,
            strategy_version_id=run.strategy_version_id,
            started_at=run.created_at,
            sharpe=_optional_float(run.metrics.get("sharpe")),
            max_drawdown=_optional_float(run.metrics.get("max_drawdown")),
            total_return=_optional_float(run.metrics.get("total_return")),
            monte_carlo_summary=_optional_dict(run.metrics.get("monte_carlo")),
            warnings=_string_tuple(run.metrics.get("warnings")),
        )
        for run in runs
    )


def _decision_stats_for_plan(
    store: SQLiteRuntimeStore,
    versions: tuple[RiskPlanVersion, ...],
) -> RiskPlanDecisionStats:
    cards = store.list_risk_decision_cards_for_risk_plan_versions(
        tuple(version.risk_plan_version_id for version in versions)
    )
    counts = Counter(card.decision.value for card in cards)
    rejected_reasons: Counter[str] = Counter()
    for card in cards:
        if card.decision.value != "rejected":
            continue
        rejected_reasons.update(reason for reason in card.reason_codes if reason)
    return RiskPlanDecisionStats(
        total=len(cards),
        approved=counts["approved"],
        rejected=counts["rejected"],
        reduced=counts["reduced"],
        capped=counts["capped"],
        skipped=counts["skipped"],
        requires_operator=counts["requires_operator"],
        top_rejection_reasons=tuple(
            RiskPlanTopRejectionReason(reason=reason, count=count)
            for reason, count in rejected_reasons.most_common(5)
        ),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _optional_dict(value: object) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _readable_account_mode(value: str) -> str:
    if value == "BROKER_PAPER":
        return "paper"
    if value == "BROKER_LIVE":
        return "live"
    return value.lower().replace("_", " ")


def _default_ai_provider_or_400(catalog: Any) -> AIServiceRecord:
    try:
        services = catalog.list_services().services
    except AIProviderCatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    valid = [service for service in services if service.status == AIProviderStatus.VALID]
    for service in valid:
        if service.is_default:
            return service
    if valid:
        return valid[0]
    raise HTTPException(status_code=400, detail="no valid AI provider is configured")


def _draft_from_prompt(prompt: str, *, created_by: str | None) -> dict[str, Any]:
    text = prompt.lower()
    warnings: list[str] = []
    if any(token in text for token in ("conservative", "small", "protect", "low risk")):
        tier = RiskPlanTier.CONSERVATIVE
        score = 3
        risk_pct = 0.5
        max_positions = 3
        max_daily_loss = 2
        max_drawdown = 6
        allow_short = False
        allow_extended = False
    elif any(token in text for token in ("aggressive", "high risk", "experimental", "growth")):
        tier = RiskPlanTier.AGGRESSIVE
        score = 8
        risk_pct = 2.0
        max_positions = 8
        max_daily_loss = 5
        max_drawdown = 15
        allow_short = "short" in text
        allow_extended = "extended" in text or "premarket" in text or "after hours" in text
        warnings.append("Aggressive AI draft: review risk_per_trade_pct, max positions, and loss limits before saving.")
    else:
        tier = RiskPlanTier.BALANCED
        score = 5
        risk_pct = 1.0
        max_positions = 5
        max_daily_loss = 3
        max_drawdown = 10
        allow_short = "short" in text
        allow_extended = "extended" in text or "premarket" in text or "after hours" in text

    if allow_short:
        warnings.append("AI draft allows short selling because the prompt requested it; deterministic validators still apply.")
    if allow_extended:
        warnings.append("AI draft allows extended-hours trading because the prompt requested it; review liquidity risk.")

    config = RiskPlanConfig(
        sizing_method="risk_percent",
        risk_per_trade_pct=risk_pct,
        max_position_pct_of_equity=20 if tier != RiskPlanTier.AGGRESSIVE else 30,
        max_symbol_exposure_pct=25 if tier != RiskPlanTier.AGGRESSIVE else 35,
        max_gross_exposure_pct=100 if tier != RiskPlanTier.AGGRESSIVE else 150,
        max_net_exposure_pct=80 if tier != RiskPlanTier.AGGRESSIVE else 120,
        max_open_positions=max_positions,
        max_open_risk_pct=risk_pct * max_positions,
        max_daily_loss_pct=max_daily_loss,
        max_drawdown_pct=max_drawdown,
        max_trades_per_day=max_positions * 2,
        cooldown_after_loss_minutes=30 if tier != RiskPlanTier.AGGRESSIVE else 15,
        fractional_quantity_allowed=True,
        whole_share_rounding="floor",
        min_quantity=1,
        stop_required=True,
        reject_if_no_stop=True,
        default_stop_policy={"kind": "operator_review_required", "source": "ai_draft"},
        target_required=False,
        runner_allowed=tier != RiskPlanTier.CONSERVATIVE,
        allow_scale_in=tier == RiskPlanTier.AGGRESSIVE,
        allow_scale_out=True,
        allow_short=allow_short,
        allow_extended_hours=allow_extended,
    )
    plan = RiskPlan(
        name=_draft_name(prompt, tier=tier),
        description=f"AI-generated draft from operator prompt: {prompt.strip()}",
        status=RiskPlanStatus.DRAFT,
        risk_score=score,
        risk_tier=tier,
        created_by=created_by,
        ai_generated=True,
        ai_summary=(
            f"Draft {tier.value} RiskPlan: risks {risk_pct}% per trade, allows up to "
            f"{max_positions} open positions, max daily loss {max_daily_loss}%."
        ),
        source=RiskPlanSource.AI_GENERATED,
    )
    version = RiskPlanVersion(
        risk_plan_id=plan.risk_plan_id,
        version=1,
        status=RiskPlanVersionStatus.DRAFT,
        config=config,
    )
    return {"risk_plan": plan, "risk_plan_version": version, "warnings": tuple(warnings)}


def _draft_name(prompt: str, *, tier: RiskPlanTier) -> str:
    compact = " ".join(prompt.strip().split())
    if not compact:
        return f"AI {tier.value.title()} Risk Draft"
    return f"AI {tier.value.title()} Risk Draft - {compact[:48]}"
