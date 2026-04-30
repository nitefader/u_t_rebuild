"""Unit tests for GovernorPolicyResolver — the per-evaluation policy
translator that turns AccountRiskConfig + per-horizon RiskPlanConfig into
a GovernorPolicy snapshot.

Doctrine references:
- Operations_Turtle_Shell_Artifacts/GOVERNOR_WIRING_MAP.md §3 (field map)
- Operations_Turtle_Shell_Artifacts/GOVERNOR_WIRING_MAP.md §0 (locked
  Risk Horizon doctrine: Deployment chooses horizon, Account chooses plan)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts.models import AccountRiskConfig
from backend.app.domain.risk_plan import RiskPlanConfig, RiskPlanSizingMethod
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.governor import GovernorPolicy, GovernorPolicyResolver

ACCOUNT_ID = UUID("11111111-1111-1111-1111-111111111111")
DEPLOYMENT_ID = UUID("22222222-2222-2222-2222-222222222222")


def _account_config(**overrides: object) -> AccountRiskConfig:
    base: dict[str, object] = {
        "account_id": ACCOUNT_ID,
        # Wipe AccountRiskConfig defaults so tests start neutral. Operator
        # has to set fields explicitly per case.
        "max_open_positions": None,
        "risk_per_trade_pct": 1.0,
        "sizing_method": "risk_percent_equity",
        "updated_at": datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return AccountRiskConfig(**base)


def _plan_config(**overrides: object) -> RiskPlanConfig:
    base: dict[str, object] = {
        "sizing_method": RiskPlanSizingMethod.RISK_PERCENT,
        "risk_per_trade_pct": 1.0,
    }
    base.update(overrides)
    return RiskPlanConfig(**base)


def _resolver(
    account_lookup: Callable[[UUID], AccountRiskConfig | None] = lambda _aid: None,
    plan_lookup: Callable[
        [UUID, TradingHorizon], RiskPlanConfig | None
    ] = lambda _aid, _h: None,
) -> GovernorPolicyResolver:
    return GovernorPolicyResolver(
        get_account_risk_config=account_lookup,
        get_risk_plan_config_for_horizon=plan_lookup,
    )


# ---------------------------------------------------------------------------
# Floor passthrough
# ---------------------------------------------------------------------------


def test_resolve_with_no_configs_returns_floor_unchanged():
    floor = GovernorPolicy(
        max_open_positions=None,
        max_gross_exposure_pct=None,
    )
    policy = _resolver().resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert policy.max_open_positions is None
    assert policy.max_gross_exposure_pct is None
    assert policy.global_kill_active is False
    assert policy.paused_account_ids == frozenset()


# ---------------------------------------------------------------------------
# Single-source contributions
# ---------------------------------------------------------------------------


def test_account_only_contributes_max_open_positions():
    account = _account_config(max_open_positions=3)
    policy = _resolver(account_lookup=lambda _aid: account).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert policy.max_open_positions == 3


def test_plan_only_contributes_max_open_risk_pct():
    # max_open_risk_pct is RiskPlan-only by design (AccountRiskConfig
    # doesn't carry this field). Plan-only contribution must work.
    plan = _plan_config(max_open_risk_pct=10.0)
    policy = _resolver(plan_lookup=lambda _aid, _h: plan).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.POSITION,
    )
    assert policy.max_open_risk_pct == 10.0


def test_plan_only_contributes_max_gross_exposure_pct():
    plan = _plan_config(max_gross_exposure_pct=50.0)
    policy = _resolver(plan_lookup=lambda _aid, _h: plan).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert policy.max_gross_exposure_pct == 50.0


# ---------------------------------------------------------------------------
# Min-of-both rule
# ---------------------------------------------------------------------------


def test_both_set_min_wins_for_max_open_positions():
    account = _account_config(max_open_positions=5)
    plan = _plan_config(max_open_positions=2)
    policy = _resolver(
        account_lookup=lambda _aid: account,
        plan_lookup=lambda _aid, _h: plan,
    ).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert policy.max_open_positions == 2  # plan is tighter


def test_both_set_min_wins_for_max_gross_exposure_pct():
    account = _account_config(max_gross_exposure_pct=80.0)
    plan = _plan_config(max_gross_exposure_pct=50.0)
    policy = _resolver(
        account_lookup=lambda _aid: account,
        plan_lookup=lambda _aid, _h: plan,
    ).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SCALPING,
    )
    assert policy.max_gross_exposure_pct == 50.0  # plan is tighter


def test_floor_min_combines_with_per_eval_sources():
    # Floor is the persisted-singleton GovernorPolicy. It can also contribute
    # a numeric limit. The resolver must consider it alongside Account+Plan
    # so the operator cannot accidentally relax a system-wide floor.
    floor = GovernorPolicy(max_open_positions=1)
    account = _account_config(max_open_positions=10)
    plan = _plan_config(max_open_positions=8)
    policy = _resolver(
        account_lookup=lambda _aid: account,
        plan_lookup=lambda _aid, _h: plan,
    ).resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert policy.max_open_positions == 1  # floor is tightest


# ---------------------------------------------------------------------------
# Name translation: max_symbol_concentration_pct ↔ max_symbol_exposure_pct
# (MAP D5 — AccountRiskConfig and RiskPlanConfig disagree on the label)
# ---------------------------------------------------------------------------


def test_symbol_concentration_translation_account_only():
    account = _account_config(max_symbol_concentration_pct=20.0)
    policy = _resolver(account_lookup=lambda _aid: account).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert policy.max_symbol_concentration_pct == 20.0


def test_symbol_concentration_translation_plan_only():
    # RiskPlanConfig calls this max_symbol_exposure_pct, but it must land
    # on GovernorPolicy.max_symbol_concentration_pct.
    plan = _plan_config(max_symbol_exposure_pct=15.0)
    policy = _resolver(plan_lookup=lambda _aid, _h: plan).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert policy.max_symbol_concentration_pct == 15.0


def test_symbol_concentration_translation_both_min_wins():
    account = _account_config(max_symbol_concentration_pct=25.0)
    plan = _plan_config(max_symbol_exposure_pct=10.0)
    policy = _resolver(
        account_lookup=lambda _aid: account,
        plan_lookup=lambda _aid, _h: plan,
    ).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert policy.max_symbol_concentration_pct == 10.0


# ---------------------------------------------------------------------------
# Kill / pause preservation (per MAP D4)
# ---------------------------------------------------------------------------


def test_resolve_preserves_global_kill_active():
    floor = GovernorPolicy(global_kill_active=True)
    plan = _plan_config(max_open_positions=1)  # would otherwise relax nothing
    policy = _resolver(plan_lookup=lambda _aid, _h: plan).resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert policy.global_kill_active is True


def test_resolve_preserves_paused_account_ids():
    floor = GovernorPolicy(paused_account_ids=frozenset({ACCOUNT_ID}))
    policy = _resolver().resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert ACCOUNT_ID in policy.paused_account_ids


def test_resolve_preserves_paused_deployment_ids():
    floor = GovernorPolicy(paused_deployment_ids=frozenset({DEPLOYMENT_ID}))
    policy = _resolver().resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.POSITION,
    )
    assert DEPLOYMENT_ID in policy.paused_deployment_ids


# ---------------------------------------------------------------------------
# Lookup failure — graceful degrade (MAP D7)
# ---------------------------------------------------------------------------


def test_account_lookup_raising_falls_back_to_plan_only():
    def _broken_account(_aid: UUID) -> AccountRiskConfig | None:
        raise RuntimeError("simulated DB outage")

    plan = _plan_config(max_open_positions=4)
    policy = _resolver(
        account_lookup=_broken_account,
        plan_lookup=lambda _aid, _h: plan,
    ).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    # Account contributes nothing (errored); plan still applies.
    assert policy.max_open_positions == 4


def test_plan_lookup_raising_falls_back_to_account_only():
    def _broken_plan(_aid: UUID, _h: TradingHorizon) -> RiskPlanConfig | None:
        raise RuntimeError("simulated DB outage")

    account = _account_config(max_open_positions=7)
    policy = _resolver(
        account_lookup=lambda _aid: account,
        plan_lookup=_broken_plan,
    ).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert policy.max_open_positions == 7


def test_both_lookups_raising_returns_floor():
    def _broken(*_args, **_kwargs):
        raise RuntimeError("simulated DB outage")

    floor = GovernorPolicy(max_open_positions=2)
    policy = _resolver(
        account_lookup=_broken,
        plan_lookup=_broken,
    ).resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SCALPING,
    )
    assert policy.max_open_positions == 2  # floor preserved


# ---------------------------------------------------------------------------
# Horizon dispatch — every value must reach the lookup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "horizon",
    [
        TradingHorizon.SCALPING,
        TradingHorizon.INTRADAY,
        TradingHorizon.SWING,
        TradingHorizon.POSITION,
    ],
)
def test_horizon_passes_through_to_plan_lookup(horizon: TradingHorizon):
    captured: list[TradingHorizon] = []

    def _capture(_aid: UUID, h: TradingHorizon) -> RiskPlanConfig | None:
        captured.append(h)
        return None

    _resolver(plan_lookup=_capture).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=horizon,
    )
    assert captured == [horizon]


def test_account_id_passes_through_to_both_lookups():
    captured_account: list[UUID] = []
    captured_plan: list[UUID] = []

    def _account_capture(aid: UUID) -> AccountRiskConfig | None:
        captured_account.append(aid)
        return None

    def _plan_capture(aid: UUID, _h: TradingHorizon) -> RiskPlanConfig | None:
        captured_plan.append(aid)
        return None

    _resolver(
        account_lookup=_account_capture,
        plan_lookup=_plan_capture,
    ).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert captured_account == [ACCOUNT_ID]
    assert captured_plan == [ACCOUNT_ID]


# ---------------------------------------------------------------------------
# Frozen invariant — resolve never mutates floor
# ---------------------------------------------------------------------------


def test_resolve_does_not_mutate_floor():
    floor = GovernorPolicy(max_open_positions=10)
    account = _account_config(max_open_positions=2)
    resolved = _resolver(account_lookup=lambda _aid: account).resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
    )
    assert resolved.max_open_positions == 2
    # Floor unchanged; pydantic frozen would raise on mutation but we also
    # assert via a fresh read.
    assert floor.max_open_positions == 10


def test_deployment_id_does_not_affect_resolution_today():
    # Slice A doctrine: deployment_id is in the signature for future audit
    # use but does not change resolution. Two different deployment_ids with
    # identical (account, horizon) must yield identical policies.
    account = _account_config(max_open_positions=4)
    resolver = _resolver(account_lookup=lambda _aid: account)
    p1 = resolver.resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=uuid4(),
        risk_horizon=TradingHorizon.INTRADAY,
    )
    p2 = resolver.resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=uuid4(),
        risk_horizon=TradingHorizon.INTRADAY,
    )
    assert p1.max_open_positions == p2.max_open_positions == 4


# ---------------------------------------------------------------------------
# Slice B: requires_risk_plan flag — set when plan lookup returns None
# (no map row exists for this horizon); NOT set when lookup raises.
# ---------------------------------------------------------------------------


def test_requires_risk_plan_is_true_when_plan_lookup_returns_none_and_enforce_set():
    """enforce_plan_required=True + plan lookup returns None → requires_risk_plan=True."""
    policy = _resolver(plan_lookup=lambda _aid, _h: None).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
        enforce_plan_required=True,
    )
    assert policy.requires_risk_plan is True


def test_requires_risk_plan_is_false_when_enforce_not_set():
    """Without enforce_plan_required=True, missing plan does NOT set requires_risk_plan.

    This is the backwards-compat path: a Deployment without an explicit
    risk_horizon only enforces numeric limits, not the must-have-plan rule.
    """
    policy = _resolver(plan_lookup=lambda _aid, _h: None).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
        enforce_plan_required=False,
    )
    assert policy.requires_risk_plan is False


def test_requires_risk_plan_is_false_when_plan_lookup_returns_config():
    """Plan lookup returns a config → Account has a plan → flag must be False."""
    plan = _plan_config(max_open_positions=2)
    policy = _resolver(plan_lookup=lambda _aid, _h: plan).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
        enforce_plan_required=True,
    )
    assert policy.requires_risk_plan is False


def test_requires_risk_plan_is_false_when_plan_lookup_raises():
    """Lookup raises (DB outage, transient) → graceful degrade, NOT a false rejection."""
    def _broken(_aid: UUID, _h: TradingHorizon) -> RiskPlanConfig | None:
        raise RuntimeError("simulated DB error")

    policy = _resolver(plan_lookup=_broken).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.INTRADAY,
        enforce_plan_required=True,
    )
    # A lookup exception must NOT trigger the "no plan" rejection — that would
    # be a false positive that kills trading during a transient DB failure.
    assert policy.requires_risk_plan is False


def test_requires_risk_plan_false_on_default_policy():
    """GovernorPolicy default must have requires_risk_plan=False for backwards compat."""
    policy = GovernorPolicy()
    assert policy.requires_risk_plan is False


@pytest.mark.parametrize(
    "horizon",
    [
        TradingHorizon.SCALPING,
        TradingHorizon.INTRADAY,
        TradingHorizon.SWING,
        TradingHorizon.POSITION,
        TradingHorizon.OTHER,
    ],
)
def test_requires_risk_plan_set_for_all_horizons(horizon: TradingHorizon):
    """requires_risk_plan must trigger for every horizon value including OTHER."""
    policy = _resolver(plan_lookup=lambda _aid, _h: None).resolve(
        floor=GovernorPolicy(),
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=horizon,
        enforce_plan_required=True,
    )
    assert policy.requires_risk_plan is True


def test_requires_risk_plan_not_set_on_floor_when_floor_has_no_plan():
    """Floor policy's requires_risk_plan is not inherited to the resolved policy."""
    floor = GovernorPolicy(requires_risk_plan=False)
    plan = _plan_config(max_open_positions=5)
    policy = _resolver(plan_lookup=lambda _aid, _h: plan).resolve(
        floor=floor,
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        risk_horizon=TradingHorizon.SWING,
        enforce_plan_required=True,
    )
    assert policy.requires_risk_plan is False
