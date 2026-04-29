from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from backend.app.domain import RiskProfileVersion


class RiskPlanVersionLookup(Protocol):
    def load_risk_plan_version(self, risk_plan_version_id: UUID) -> Any: ...

    def load_risk_plan(self, risk_plan_id: UUID) -> Any: ...


def load_risk_profile_from_plan_version(
    *,
    store: RiskPlanVersionLookup | None,
    risk_plan_version_id: UUID | None,
    purpose: str,
) -> RiskProfileVersion:
    if risk_plan_version_id is None:
        raise ValueError(f"{purpose} requires base_risk_plan_version_id")
    if store is None or not hasattr(store, "load_risk_plan_version"):
        raise ValueError(f"{purpose} requires a RiskPlanVersion store")
    try:
        version = store.load_risk_plan_version(risk_plan_version_id)
        plan = store.load_risk_plan(version.risk_plan_id)
    except KeyError as exc:
        raise ValueError(f"unknown risk_plan_version_id: {risk_plan_version_id}") from exc
    return version.to_risk_profile_version(name=plan.name)
