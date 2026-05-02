from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain import (
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSizingMethod,
    RiskPlanSource,
    RiskPlanStatus,
    RiskPlanTier,
    RiskPlanVersion,
    RiskPlanVersionStatus,
    WholeShareRounding,
)
from backend.app.domain.risk_profile import PositionSizingMethod


def _balanced_config() -> RiskPlanConfig:
    return RiskPlanConfig(
        sizing_method=RiskPlanSizingMethod.RISK_PERCENT,
        risk_per_trade_pct=1.0,
        max_trade_notional=10_000,
        min_trade_notional=100,
        max_position_notional=20_000,
        max_position_pct_of_equity=20,
        max_symbol_exposure_pct=25,
        max_sector_exposure_pct=40,
        max_gross_exposure_pct=100,
        max_net_exposure_pct=80,
        max_open_positions=5,
        max_open_risk_pct=5,
        max_daily_loss_pct=3,
        max_drawdown_pct=10,
        max_trades_per_day=8,
        cooldown_after_loss_minutes=30,
        fractional_quantity_allowed=False,
        whole_share_rounding=WholeShareRounding.FLOOR,
        min_quantity=1,
        max_quantity=100,
        stop_required=True,
        reject_if_no_stop=True,
        default_stop_policy={"kind": "atr_multiple", "multiple": 2},
        target_required=True,
        runner_allowed=True,
        allow_scale_in=False,
        allow_scale_out=True,
        allow_short=False,
        allow_extended_hours=False,
        symbol_restrictions=("SPY", "QQQ"),
        asset_class_restrictions=("equity",),
        account_mode_restrictions=("paper", "live"),
    )


def test_risk_plan_domain_contract_and_version_fingerprint() -> None:
    risk_plan = RiskPlan(
        name="Balanced Momentum Risk",
        description="Balanced account risk for liquid ETFs.",
        status=RiskPlanStatus.DRAFT,
        risk_score=5,
        risk_tier=RiskPlanTier.BALANCED,
        created_by="operator",
        source=RiskPlanSource.MANUAL,
    )
    config = _balanced_config()
    version = RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        status=RiskPlanVersionStatus.DRAFT,
        config=config,
    )

    assert version.config_fingerprint == config.fingerprint()
    assert version.config.canonical_payload()["sizing_method"] == "risk_percent"
    assert len(version.config_fingerprint or "") == 64


def test_risk_plan_rejects_invalid_score_and_ai_source_mismatch() -> None:
    with pytest.raises(ValidationError):
        RiskPlan(
            name="Too Hot",
            risk_score=11,
            risk_tier=RiskPlanTier.AGGRESSIVE,
        )

    with pytest.raises(ValidationError, match="ai_generated must be true"):
        RiskPlan(
            name="AI Draft",
            risk_score=4,
            risk_tier=RiskPlanTier.CONSERVATIVE,
            source=RiskPlanSource.AI_GENERATED,
        )


def test_research_derived_risk_plan_requires_evidence_lineage() -> None:
    with pytest.raises(ValidationError, match="source_run_id"):
        RiskPlan(
            name="Optimization Draft",
            risk_score=5,
            risk_tier=RiskPlanTier.BALANCED,
            source=RiskPlanSource.OPTIMIZATION_GENERATED,
        )

    with pytest.raises(ValidationError, match="evidence_lineage"):
        RiskPlan(
            name="Walk Forward Draft",
            risk_score=5,
            risk_tier=RiskPlanTier.BALANCED,
            source=RiskPlanSource.WALK_FORWARD_RECOMMENDED,
            source_run_id=uuid4(),
        )

    run_id = uuid4()
    risk_plan = RiskPlan(
        name="Evidence Backed Draft",
        risk_score=5,
        risk_tier=RiskPlanTier.BALANCED,
        source=RiskPlanSource.WALK_FORWARD_RECOMMENDED,
        source_run_id=run_id,
        source_evidence_type="WalkForwardRun",
        evidence_lineage={
            "source_run_id": str(run_id),
            "source_evidence_type": "WalkForwardRun",
            "artifact_id": str(uuid4()),
            "deployment_snapshot_id": str(uuid4()),
        },
    )

    assert risk_plan.source_run_id == run_id


def test_risk_plan_config_requires_method_specific_sizing_input() -> None:
    with pytest.raises(ValidationError, match="risk_per_trade_pct is required"):
        RiskPlanConfig(sizing_method=RiskPlanSizingMethod.RISK_PERCENT)

    fixed = RiskPlanConfig(
        sizing_method=RiskPlanSizingMethod.FIXED_SHARES,
        fixed_shares=10,
        stop_required=False,
        reject_if_no_stop=False,
    )

    assert fixed.legacy_sizing_method() == PositionSizingMethod.FIXED_SHARES


def test_active_and_deprecated_versions_require_timestamps() -> None:
    config = _balanced_config()

    with pytest.raises(ValidationError, match="active RiskPlanVersion requires activated_at"):
        RiskPlanVersion(
            risk_plan_id=uuid4(),
            version=1,
            status=RiskPlanVersionStatus.ACTIVE,
            config=config,
        )

    version = RiskPlanVersion(
        risk_plan_id=uuid4(),
        version=1,
        status=RiskPlanVersionStatus.ACTIVE,
        config=config,
        activated_at=datetime.now(timezone.utc),
    )

    assert version.status == RiskPlanVersionStatus.ACTIVE


def test_risk_plan_version_can_adapt_to_legacy_risk_profile_wire_shape() -> None:
    risk_plan_id = uuid4()
    version = RiskPlanVersion(
        risk_plan_id=risk_plan_id,
        version=3,
        config=_balanced_config(),
    )

    legacy = version.to_risk_profile_version(name="Balanced Momentum Risk")

    assert legacy.id == version.risk_plan_version_id
    assert legacy.risk_profile_id == risk_plan_id
    assert legacy.version == 3
    assert legacy.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY
    assert legacy.risk_per_trade_pct == 1.0
    assert legacy.max_positions == 5
