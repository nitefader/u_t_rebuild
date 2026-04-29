"""Read API for RiskDecisionCard — every sized SignalPlan emits one.

RiskPlan belongs to the Account or selected research run. SignalPlan describes
the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
and current account or simulated account state to produce a RiskDecisionCard.
No simulated or real order may be created without that RiskDecisionCard.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.domain import RiskDecisionCard
from backend.app.persistence import SQLiteRuntimeStore


router = APIRouter(tags=["risk-decisions"])


class RiskDecisionCardListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cards: tuple[RiskDecisionCard, ...] = ()


def get_risk_decision_store() -> SQLiteRuntimeStore:
    return SQLiteRuntimeStore(get_runtime_db_path())


def _dependency(default: object) -> object:
    return Depends(default)


RiskDecisionStoreDependency = Annotated[Any, _dependency(get_risk_decision_store)]


@router.get("/api/v1/risk-decisions/{risk_decision_id}", response_model=RiskDecisionCard)
def get_risk_decision(risk_decision_id: UUID, store: RiskDecisionStoreDependency) -> RiskDecisionCard:
    try:
        return store.load_risk_decision_card(risk_decision_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/v1/risk-decisions", response_model=RiskDecisionCardListResponse)
def list_risk_decisions(
    store: RiskDecisionStoreDependency,
    run_id: UUID | None = Query(default=None),
    signal_plan_id: UUID | None = Query(default=None),
    account_id: UUID | None = Query(default=None),
    strategy_version_id: UUID | None = Query(default=None),
) -> RiskDecisionCardListResponse:
    cards = store.list_risk_decision_cards(
        run_id=run_id,
        signal_plan_id=signal_plan_id,
        account_id=account_id,
        strategy_version_id=strategy_version_id,
    )
    return RiskDecisionCardListResponse(cards=cards)
