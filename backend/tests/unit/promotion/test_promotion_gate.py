from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.brokers import (
    BrokerReconciliationIssue,
    BrokerReconciliationIssueType,
    BrokerReconciliationReport,
    BrokerSyncState,
)
from backend.app.control_plane import ControlPlane
from backend.app.domain import GovernorMode, ProgramStatus, ProgramVersion, TradingMode
from backend.app.promotion import (
    PaperRunEvidence,
    PortfolioGovernorReadiness,
    PromotionEvaluationContext,
    PromotionGateService,
    SimulationPromotionEvidence,
)
from backend.app.promotion import service as promotion_service


ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
DEPLOYMENT_ID = UUID("00000000-0000-0000-0000-000000000002")
NOW = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)


def _program(*, status: ProgramStatus = ProgramStatus.FROZEN) -> ProgramVersion:
    return ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Promotion Program",
        version=1,
        status=status,
        frozen_at=NOW if status == ProgramStatus.FROZEN else None,
        strategy_version_id=uuid4(),
        strategy_controls_version_id=uuid4(),
        risk_profile_version_id=uuid4(),
        execution_style_version_id=uuid4(),
        universe_snapshot_id=uuid4(),
    )


def _paper_run(**overrides: object) -> PaperRunEvidence:
    payload: dict[str, object] = {
        "deployment_id": DEPLOYMENT_ID,
        "succeeded": True,
        "started_at": NOW - timedelta(days=3),
        "ended_at": NOW,
        "trade_count": 12,
        "submitted_order_count": 20,
        "rejected_order_count": 1,
        "max_drawdown_pct": 2,
    }
    payload.update(overrides)
    return PaperRunEvidence(**payload)


def _simulation(program: ProgramVersion, **overrides: object) -> SimulationPromotionEvidence:
    payload: dict[str, object] = {
        "session_id": uuid4(),
        "program_version_id": program.id,
        "mode": TradingMode.SIM_LAB_HISTORICAL,
        "governor_mode": GovernorMode.ENFORCED,
        "succeeded": True,
    }
    payload.update(overrides)
    return SimulationPromotionEvidence(**payload)


def _broker_sync(*, stale: bool = False) -> BrokerSyncState:
    return BrokerSyncState(
        account_id=ACCOUNT_ID,
        last_sync_at=NOW,
        is_stale=stale,
        stale_reason="timeout" if stale else None,
    )


def _context(**overrides: object) -> PromotionEvaluationContext:
    program = overrides.pop("program", _program())
    assert isinstance(program, ProgramVersion)
    payload: dict[str, object] = {
        "program": program,
        "deployment_id": DEPLOYMENT_ID,
        "account_id": ACCOUNT_ID,
        "current_mode": TradingMode.BROKER_PAPER,
        "broker_sync_state": _broker_sync(),
        "control_plane": ControlPlane(),
        "governor": PortfolioGovernorReadiness(active=True, enforcing=True),
        "paper_runs": (_paper_run(),),
        "simulation_evidence": (_simulation(program),),
    }
    payload.update(overrides)
    return PromotionEvaluationContext(**payload)


def test_eligible_program_passes_all_checks() -> None:
    result = PromotionGateService().evaluate(_context())

    assert result.eligible is True
    assert result.blocking_reasons == []
    assert result.warnings == []
    assert result.program_id
    assert result.deployment_id == DEPLOYMENT_ID


def test_unfrozen_program_fails() -> None:
    result = PromotionGateService().evaluate(_context(program=_program(status=ProgramStatus.DRAFT)))

    assert result.eligible is False
    assert "program_not_frozen" in result.blocking_reasons


def test_stale_broker_sync_fails() -> None:
    result = PromotionGateService().evaluate(_context(broker_sync_state=_broker_sync(stale=True)))

    assert result.eligible is False
    assert "broker_sync_stale" in result.blocking_reasons


def test_global_kill_active_fails() -> None:
    result = PromotionGateService().evaluate(_context(control_plane=ControlPlane(global_kill_active=True)))

    assert result.eligible is False
    assert "global_kill_active" in result.blocking_reasons


def test_missing_simulation_fails() -> None:
    result = PromotionGateService().evaluate(_context(simulation_evidence=()))

    assert result.eligible is False
    assert "missing_required_simulation_evidence" in result.blocking_reasons


def test_missing_paper_run_fails() -> None:
    result = PromotionGateService().evaluate(_context(paper_runs=()))

    assert result.eligible is False
    assert "missing_successful_paper_run" in result.blocking_reasons


def test_warnings_generated_correctly_without_blocking() -> None:
    paper_run = _paper_run(
        started_at=NOW - timedelta(hours=2),
        trade_count=2,
        submitted_order_count=10,
        rejected_order_count=4,
        max_drawdown_pct=12,
        broker_sync_inconsistent_event_count=1,
    )
    result = PromotionGateService().evaluate(_context(paper_runs=(paper_run,)))

    assert result.eligible is True
    assert result.blocking_reasons == []
    assert result.warnings == [
        "limited_paper_trade_count",
        "short_paper_runtime_duration",
        "high_paper_rejection_rate",
        "high_paper_drawdown_observed",
        "inconsistent_broker_sync_events",
    ]


def test_required_simulation_must_use_enforced_governor_mode() -> None:
    program = _program()
    result = PromotionGateService().evaluate(
        _context(
            program=program,
            simulation_evidence=(_simulation(program, governor_mode=GovernorMode.ADVISORY),),
        )
    )

    assert result.eligible is False
    assert "missing_required_simulation_evidence" in result.blocking_reasons


def test_simulation_system_rejections_fail() -> None:
    program = _program()
    result = PromotionGateService().evaluate(
        _context(
            program=program,
            simulation_evidence=(_simulation(program, rejected_trades_due_to_system_issue_count=1),),
        )
    )

    assert result.eligible is False
    assert "simulation_system_rejections_present" in result.blocking_reasons


def test_unresolved_broker_reconciliation_mismatch_fails() -> None:
    report = BrokerReconciliationReport(
        account_id=ACCOUNT_ID,
        issues=(
            BrokerReconciliationIssue(
                issue_type=BrokerReconciliationIssueType.POSITION_MISMATCH,
                account_id=ACCOUNT_ID,
                symbol="SPY",
                message="position mismatch",
                expected=1,
                actual=2,
            ),
        ),
    )

    result = PromotionGateService().evaluate(_context(reconciliation_report=report))

    assert result.eligible is False
    assert "unresolved_broker_reconciliation_mismatch" in result.blocking_reasons


def test_promotion_gate_does_not_depend_on_feature_engine() -> None:
    source = inspect.getsource(promotion_service)

    assert "FeatureEngine" not in source
    assert "backend.app.features" not in source


def test_promotion_gate_does_not_depend_on_signal_engine() -> None:
    source = inspect.getsource(promotion_service)

    assert "SignalEngine" not in source
    assert "backend.app.decision" not in source
