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

Each Account owns a per-horizon RiskPlan map (Slice B). The Deployment
declares its risk_horizon. At evaluation time the resolver looks up the
Account's mapped RiskPlanVersion FOR THAT HORIZON and combines its config
with the Account's AccountRiskConfig.

T-6 (Bracket Program, MAP §7 D7) — TOCTOU hardening:
  Both inputs are read together as a single point-in-time snapshot via
  one composite lookup. The resolver no longer owns separate account /
  plan callbacks; it owns one ``get_policy_inputs(account_id, horizon)``
  callback. The production wiring in
  ``BrokerRuntimeOrchestrator._build_governor_policy_resolver`` routes
  this callback through ``SQLiteRuntimeStore.load_governor_policy_inputs``
  which wraps both reads in a single SQLite connection. WAL mode at
  composition root keeps the writer (operator PUT to /risk-plan-map)
  non-blocking. Per D7: single-conn + WAL only, no optimistic version
  stamps, no mid-evaluation rejection.

Design constraints (locked in MAP §4 + §7 D7):
- Pure logic. The resolver does not own a runtime store; it accepts one
  lookup callable so it stays testable without DB stubs.
- ``GovernorPolicy`` is ``frozen``, so each resolution returns a new
  instance built from the floor policy + per-evaluation overrides.
- Floor ``global_kill_active`` / ``paused_account_ids`` /
  ``paused_deployment_ids`` carry through verbatim. Per-evaluation policies
  may only ADD numeric limits, never relax kill/pause state.
- The lookup callable returns ``(account_config, plan_config)``. Either
  half may be ``None`` to mean "no per-source override".
- Lookup callable that raises should NOT block trading; the resolver logs
  and falls back to the floor policy as if no override existed (graceful
  degrade per MAP D7). A misbehaving lookup is an operations problem, not
  an entire-fleet kill switch. In that case ``requires_risk_plan`` is
  NOT set even if ``enforce_plan_required=True`` — that path is the
  graceful-degrade branch and a transient DB failure must not become a
  false-positive rejection.
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
_ACCOUNT_FIELD_ALLOWLIST = frozenset(
    {
        "max_open_positions",
        "max_gross_exposure_pct",
        "max_net_exposure_pct",
        "max_symbol_concentration_pct",
        "max_daily_loss_pct",
        "max_drawdown_pct",
    }
)
_PLAN_FIELD_ALLOWLIST = frozenset(
    {
        "max_open_positions",
        "max_gross_exposure_pct",
        "max_net_exposure_pct",
        "max_symbol_exposure_pct",
        "max_open_risk_pct",
        "max_daily_loss_pct",
        "max_drawdown_pct",
        "cooldown_after_loss_minutes",
    }
)

# T-6: composite (account, horizon) → (AccountRiskConfig?, RiskPlanConfig?)
# lookup. The two halves are read as one snapshot so a concurrent operator
# PUT to /risk-plan-map cannot interleave between them.
GovernorPolicyInputsLookup = Callable[
    [UUID, "TradingHorizon | None"],
    "tuple[AccountRiskConfig | None, RiskPlanConfig | None]",
]


class GovernorPolicyResolver:
    """Resolves a per-(account, deployment-horizon) GovernorPolicy at evaluation time."""

    def __init__(
        self,
        *,
        get_policy_inputs: GovernorPolicyInputsLookup,
    ) -> None:
        self._get_policy_inputs = get_policy_inputs

    def resolve(
        self,
        *,
        floor: GovernorPolicy,
        account_id: UUID,
        deployment_id: UUID,
        risk_horizon: TradingHorizon | None,
        enforce_plan_required: bool = False,
    ) -> GovernorPolicy:
        """Resolve a per-(account, deployment-horizon) GovernorPolicy.

        ``enforce_plan_required=True`` activates the Slice B doctrine check:
        if the Account has no RiskPlanVersion mapped to this horizon (the plan
        lookup returned None and did not raise), the returned policy carries
        ``requires_risk_plan=True`` which the Governor's ``evaluate()`` turns
        into an immediate rejection.

        The orchestrator passes ``enforce_plan_required=True`` only when the
        Deployment has an explicit ``risk_horizon`` field set. Deployment is the
        sole source of horizon (Slice 8.7); StrategyControls no longer carries a
        trading_horizon field. When the Deployment has no horizon, no plan rule
        is enforced.

        ``deployment_id`` is accepted for future use (audit trails,
        per-deployment overrides) but is not consumed today — the doctrine
        resolves by horizon, not by deployment.
        """
        del deployment_id  # explicitly unused; kept in signature on purpose
        account_config, plan_config, lookup_failed = self._safe_lookup(account_id, risk_horizon)

        # Slice B: if enforce_plan_required is True AND the plan lookup returned
        # None (not because the lookup itself raised, but because no map row
        # exists), the Account has no RiskPlan for this horizon. The Governor
        # must reject entry signals via the
        # "account_missing_risk_plan_for_horizon" rule.
        #
        # If the lookup *raised* (DB error, transient failure), we do NOT set
        # requires_risk_plan — that path is graceful-degrade (MAP D7).
        requires_risk_plan = enforce_plan_required and (plan_config is None) and (not lookup_failed)

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
            # T-7 daily-state guardrails. Both AccountRiskConfig and RiskPlanConfig
            # carry max_daily_loss_pct / max_drawdown_pct; cooldown_after_loss_minutes
            # is RiskPlan-only (AccountRiskConfig has no such field). Min-of-present
            # so operator edits on either source tighten enforcement.
            max_daily_loss_pct=_min_present(
                floor.max_daily_loss_pct,
                _account_field(account_config, "max_daily_loss_pct"),
                _plan_field(plan_config, "max_daily_loss_pct"),
            ),
            max_drawdown_pct=_min_present(
                floor.max_drawdown_pct,
                _account_field(account_config, "max_drawdown_pct"),
                _plan_field(plan_config, "max_drawdown_pct"),
            ),
            cooldown_after_loss_minutes=_min_present(
                floor.cooldown_after_loss_minutes,
                None,
                _plan_field(plan_config, "cooldown_after_loss_minutes"),
            ),
            requires_risk_plan=requires_risk_plan,
        )

    def _safe_lookup(
        self, account_id: UUID, horizon: TradingHorizon | None
    ) -> "tuple[AccountRiskConfig | None, RiskPlanConfig | None, bool]":
        """Return ``(account_config, plan_config, lookup_raised)`` tuple.

        ``lookup_raised=True`` means the composite lookup itself raised an
        exception (DB error, transient failure); the caller should *not*
        set ``requires_risk_plan`` in that case — that would be a false
        positive that kills trading during a transient DB failure.

        ``lookup_raised=False, plan_config=None`` means the lookup succeeded
        but found no map row: the Account genuinely has no plan for this
        horizon. ``account_config`` may also be ``None`` independently.

        T-6: this is the single TOCTOU-safe entry point. Both halves of
        the snapshot come from one ``get_policy_inputs`` call so the
        production SQLite wiring reads them inside one connection.
        """
        try:
            account_config, plan_config = self._get_policy_inputs(account_id, horizon)
            return account_config, plan_config, False
        except Exception:
            # Adversarial-critic BUG-3 (T-6 Pass 8): silent graceful-degrade
            # is invisible to Operations. Emit a structured ``extra`` so
            # log aggregators can alarm on
            # ``event=governor_policy_inputs_lookup_failed``. D7 says the
            # resolver must graceful-degrade (no false-positive
            # rejection); it does not say the failure must be silent.
            _LOG.warning(
                "GovernorPolicyResolver: policy-inputs lookup failed for "
                "account %s horizon %s; falling back to floor policy",
                account_id,
                horizon,
                exc_info=True,
                extra={
                    "event": "governor_policy_inputs_lookup_failed",
                    "account_id": str(account_id),
                    "horizon": horizon.value if horizon is not None else None,
                },
            )
            return None, None, True


def _account_field(config: AccountRiskConfig | None, field: str) -> float | int | None:
    if config is None:
        return None
    if field not in _ACCOUNT_FIELD_ALLOWLIST:
        raise ValueError(f"unsupported account field mapping: {field}")
    return getattr(config, field)


def _plan_field(config: RiskPlanConfig | None, field: str) -> float | int | None:
    if config is None:
        return None
    if field not in _PLAN_FIELD_ALLOWLIST:
        raise ValueError(f"unsupported plan field mapping: {field}")
    return getattr(config, field)


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
    "GovernorPolicyInputsLookup",
    "GovernorPolicyResolver",
]
