"""Per-evaluation GovernorPolicy resolver.

Reads operator-edited AccountRiskConfig and the Account's per-horizon
RiskPlanConfig at runtime and produces a GovernorPolicy snapshot for a
single Governor evaluation. This closes the silent-no-op hole described
in ``Operations_Turtle_Shell_Artifacts/GOVERNOR_WIRING_MAP.md``: today
every numeric Governor check defaults to ``None`` because no code
populates the limits, so operator edits to the Risk Card or Risk Plans
never gate orders.

Risk-horizon doctrine (locked 2026-04-29 by operator):

    Deployment chooses horizon.
    Account chooses risk plan.
    Governor enforces.

Each Account owns a per-horizon RiskPlan map (Slice B — not yet built).
The Deployment declares its risk_horizon. At evaluation time the resolver
looks up the Account's mapped RiskPlanVersion FOR THAT HORIZON and
combines its config with the Account's AccountRiskConfig.

Horizon vocabulary today (Slice A): the resolver accepts every
``TradingHorizon`` enum value (currently ``SCALPING``, ``INTRADAY``,
``SWING``, ``POSITION``). Slice B will add an ``OTHER`` variant for
catch-all strategies; the resolver code already supports any enum value
because the lookup is a callable, not a switch.

Design constraints (locked in MAP §4):
- Pure logic. The resolver does not own a runtime store; it accepts two
  lookup callables so it stays testable without DB stubs.
- ``GovernorPolicy`` is ``frozen``, so each resolution returns a new
  instance built from the floor policy + per-evaluation overrides.
- Floor ``global_kill_active`` / ``paused_account_ids`` /
  ``paused_deployment_ids`` carry through verbatim. Per-evaluation policies
  may only ADD numeric limits, never relax kill/pause state.
- Lookup callables that return ``None`` mean "no per-source override".
  For RiskPlanConfig today, this is the steady-state since the per-horizon
  AccountRiskPlanMap entity does not yet exist. A future Slice B will add
  the entity AND the rejection rule for "Account has no plan for the
  Deployment's horizon" — that rejection lives in the orchestrator, not
  here, because it must produce a GovernorDecision rather than a policy.
- Lookup callables that raise should NOT block trading; the resolver logs
  and falls back to the floor policy as if no override existed (graceful
  degrade per MAP D7). A misbehaving lookup is an operations problem, not
  an entire-fleet kill switch.
- Combine rule: ``min`` of present values per field. ``None`` on either
  side means "no contribution from this source"; both ``None`` means the
  field stays at the floor's value (typically ``None`` = no gate).
"""

from __future__ import annotations

import logging
from typing import Callable
from uuid import UUID

from backend.app.broker_accounts.models import AccountRiskConfig
from backend.app.domain.risk_plan import RiskPlanConfig
from backend.app.domain.strategy_controls import TradingHorizon

from .models import GovernorPolicy

_LOG = logging.getLogger(__name__)

AccountRiskConfigLookup = Callable[[UUID], AccountRiskConfig | None]
# The (account_id, horizon) → RiskPlanConfig lookup is the per-Account,
# per-horizon resolution required by the locked Risk Horizon doctrine.
# Today this returns None for every input until AccountRiskPlanMap (Slice B)
# lands — the resolver still works, just contributes no plan-side limits.
RiskPlanConfigForHorizonLookup = Callable[
    [UUID, TradingHorizon], RiskPlanConfig | None
]


class GovernorPolicyResolver:
    """Resolves a per-(account, deployment-horizon) GovernorPolicy at evaluation time."""

    def __init__(
        self,
        *,
        get_account_risk_config: AccountRiskConfigLookup,
        get_risk_plan_config_for_horizon: RiskPlanConfigForHorizonLookup,
    ) -> None:
        self._get_account_risk_config = get_account_risk_config
        self._get_risk_plan_config_for_horizon = get_risk_plan_config_for_horizon

    def resolve(
        self,
        *,
        floor: GovernorPolicy,
        account_id: UUID,
        deployment_id: UUID,
        risk_horizon: TradingHorizon,
        enforce_plan_required: bool = False,
    ) -> GovernorPolicy:
        """Resolve a per-(account, deployment-horizon) GovernorPolicy.

        ``enforce_plan_required=True`` activates the Slice B doctrine check:
        if the Account has no RiskPlanVersion mapped to this horizon (the plan
        lookup returned None and did not raise), the returned policy carries
        ``requires_risk_plan=True`` which the Governor's ``evaluate()`` turns
        into an immediate rejection.

        The orchestrator passes ``enforce_plan_required=True`` only when the
        Deployment has an explicit ``risk_horizon`` field set (not a fallback
        from ``StrategyControls.trading_horizon``). Fallback-horizon evaluation
        is for numeric limits only; it does not enforce the must-have-plan rule,
        since the deployment did not declare a horizon.

        ``deployment_id`` is accepted for future use (audit trails,
        per-deployment overrides) but is not consumed today — the doctrine
        resolves by horizon, not by deployment.
        """
        del deployment_id  # explicitly unused; kept in signature on purpose
        account_config = self._safe_lookup_account(account_id)
        plan_config, plan_lookup_failed = self._safe_lookup_plan_with_status(account_id, risk_horizon)

        # Slice B: if enforce_plan_required is True AND the plan lookup returned
        # None (not because the lookup itself raised, but because no map row
        # exists), the Account has no RiskPlan for this horizon. The Governor
        # must reject entry signals via the
        # "account_missing_risk_plan_for_horizon" rule.
        #
        # If the lookup *raised* (DB error, transient failure), we do NOT set
        # requires_risk_plan — that path is graceful-degrade (MAP D7).
        requires_risk_plan = enforce_plan_required and (plan_config is None) and (not plan_lookup_failed)

        # Start from floor, then layer numeric limits with min-of-both.
        # Kill/pause state is preserved verbatim — see MAP D4.
        return GovernorPolicy(
            global_kill_active=floor.global_kill_active,
            paused_account_ids=floor.paused_account_ids,
            paused_deployment_ids=floor.paused_deployment_ids,
            max_open_positions=_min_present(
                floor.max_open_positions,
                _account_field(account_config, "max_open_positions"),
                _plan_field(plan_config, "max_open_positions"),
            ),
            max_gross_exposure_pct=_min_present(
                floor.max_gross_exposure_pct,
                _account_field(account_config, "max_gross_exposure_pct"),
                _plan_field(plan_config, "max_gross_exposure_pct"),
            ),
            max_net_exposure_pct=_min_present(
                floor.max_net_exposure_pct,
                _account_field(account_config, "max_net_exposure_pct"),
                _plan_field(plan_config, "max_net_exposure_pct"),
            ),
            max_symbol_concentration_pct=_min_present(
                floor.max_symbol_concentration_pct,
                _account_field(account_config, "max_symbol_concentration_pct"),
                # Name translation per MAP D5: AccountRiskConfig calls this
                # `max_symbol_concentration_pct`; RiskPlanConfig calls the same
                # concept `max_symbol_exposure_pct`. Both are operator-visible
                # labels; the resolver eats the asymmetry.
                _plan_field(plan_config, "max_symbol_exposure_pct"),
            ),
            max_open_risk_pct=_min_present(
                floor.max_open_risk_pct,
                # AccountRiskConfig has no max_open_risk_pct field; only RiskPlan
                # contributes to this one.
                None,
                _plan_field(plan_config, "max_open_risk_pct"),
            ),
            requires_risk_plan=requires_risk_plan,
        )

    def _safe_lookup_account(self, account_id: UUID) -> AccountRiskConfig | None:
        try:
            return self._get_account_risk_config(account_id)
        except Exception:
            _LOG.warning(
                "GovernorPolicyResolver: account risk config lookup failed for %s; "
                "falling back to floor policy",
                account_id,
                exc_info=True,
            )
            return None

    def _safe_lookup_plan_with_status(
        self, account_id: UUID, horizon: TradingHorizon
    ) -> "tuple[RiskPlanConfig | None, bool]":
        """Return ``(config, lookup_raised)`` tuple.

        ``lookup_raised=True`` means the lookup itself raised an exception
        (DB error, transient failure); the caller should *not* set
        ``requires_risk_plan`` in that case — that would be a false positive.

        ``lookup_raised=False, config=None`` means the lookup succeeded but
        found no map row: the Account genuinely has no plan for this horizon.
        """
        try:
            return self._get_risk_plan_config_for_horizon(account_id, horizon), False
        except Exception:
            _LOG.warning(
                "GovernorPolicyResolver: risk plan config lookup failed for "
                "account %s horizon %s; falling back to floor policy",
                account_id,
                horizon,
                exc_info=True,
            )
            return None, True


def _account_field(config: AccountRiskConfig | None, field: str) -> float | int | None:
    if config is None:
        return None
    return getattr(config, field, None)


def _plan_field(config: RiskPlanConfig | None, field: str) -> float | int | None:
    if config is None:
        return None
    return getattr(config, field, None)


def _min_present(*values: float | int | None) -> float | int | None:
    """Return min of all non-None values; return None if every value is None.

    Used to combine the floor policy with the two configuration sources for
    one numeric field. None means "no contribution" so the operator can leave
    a field unset on either source without that being interpreted as ``0``.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    return min(present)


__all__ = [
    "AccountRiskConfigLookup",
    "GovernorPolicyResolver",
    "RiskPlanConfigForHorizonLookup",
]
