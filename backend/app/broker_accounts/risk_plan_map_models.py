"""Models for the account-level per-horizon RiskPlan mapping.

Risk Horizon doctrine (locked 2026-04-29 by operator):

    Deployment chooses horizon. Account chooses risk plan. Governor enforces.

Each Account owns an ``AccountRiskPlanMap``: a mapping from ``TradingHorizon``
to the UUID of the ``RiskPlanVersion`` the operator has selected for trades at
that horizon. The Governor uses this map to resolve which RiskPlanConfig to
enforce for a given Deployment's horizon.

``AccountRiskPlanMapUpdateRequest`` with ``risk_plan_version_id=None`` clears
the mapping for that horizon (operator de-assigns the plan).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain._base import utc_now
from backend.app.domain.strategy_controls import TradingHorizon


class AccountRiskPlanMapEntry(BaseModel):
    """One row in the account_risk_plan_map table.

    Maps a single ``(account_id, horizon)`` pair to a ``RiskPlanVersion``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    horizon: TradingHorizon
    risk_plan_version_id: UUID
    updated_at: datetime = utc_now()


class AccountRiskPlanMap(BaseModel):
    """Read shape for an Account's full horizon-to-plan map.

    ``entries`` contains at most one entry per horizon. Empty tuple means no
    horizons are mapped (the Governor will reject any Deployment's SignalPlan
    whose horizon is not present).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    entries: tuple[AccountRiskPlanMapEntry, ...] = ()


class AccountRiskPlanMapUpdateRequest(BaseModel):
    """Upsert or delete one row in an Account's risk-plan map.

    ``risk_plan_version_id=None`` clears the mapping for the given horizon;
    any non-None UUID upserts the mapping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    horizon: TradingHorizon
    risk_plan_version_id: UUID | None = None


__all__ = [
    "AccountRiskPlanMap",
    "AccountRiskPlanMapEntry",
    "AccountRiskPlanMapUpdateRequest",
]
