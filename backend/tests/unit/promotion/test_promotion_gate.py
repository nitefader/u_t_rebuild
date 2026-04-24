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
from backend.app.domain import EvidenceKind, GovernorMode, ProgramStatus, ProgramVersion, TradingMode, ValidationEvidence
from backend.app.promotion import (
    PaperRunEvidence,
    PortfolioGovernorReadiness,
    PromotionEvaluationContext,
    PromotionGateService,
    SimulationPromotionEvidence,
)
from backend.app.promotion import service as promotion_service


SOURCE_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")
TARGET_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000003")
OTHER_PAPER_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000004")
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
        "broker_account_id": SOURCE_ACCOUNT_ID,
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


def _validation_evidence(program: ProgramVersion, kind: EvidenceKind, **overrides: object) -> ValidationEvidence:
    payload: dict[str, object] = {
        "id": uuid4(),
        "program_version_id": program.id,
        "kind": kind,
        "status": "valid",
    }
    payload.update(overrides)
    return ValidationEvidence(**payload)


def _broker_sync(*, account_id: UUID = SOURCE_ACCOUNT_ID, stale: bool = False) -> BrokerSyncState:
    return BrokerSyncState(
        account_id=account_id,
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
        "source_broker_account_id": SOURCE_ACCOUNT_ID,
        "target_broker_account_id": TARGET_ACCOUNT_ID,
        "source_mode": TradingMode.BROKER_PAPER,
        "target_mode": TradingMode.BROKER_LIVE,
        "broker_sync_state": _broker_sync(),
        "control_plane": ControlPlane(),
        "governor": PortfolioGovernorReadiness(active=True, enforcing=True),
        "paper_runs": (_paper_run(),),
        "simulation_evidence": (_simulation(program),),
        "validation_evidence": (
            _validation_evidence(program, EvidenceKind.OPTIMIZATION),
            _validation_evidence(program, EvidenceKind.WALK_FORWARD),
        ),
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
    assert result.source_broker_account_id == SOURCE_ACCOUNT_ID
    assert result.target_broker_account_id == TARGET_ACCOUNT_ID


def test_source_mode_must_be_broker_paper_and_target_mode_must_be_broker_live() -> None:
    result = PromotionGateService().evaluate(
        _context(
            source_mode=TradingMode.BROKER_LIVE,
            target_mode=TradingMode.BROKER_PAPER,
        )
    )

    assert result.eligible is False
    assert "source_mode_not_broker_paper" in result.blocking_reasons
    assert "target_mode_not_broker_live" in result.blocking_reasons


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


def test_paper_run_evidence_is_scoped_to_source_account_and_deployment() -> None:
    other_account_run = _paper_run(broker_account_id=OTHER_PAPER_ACCOUNT_ID)
    other_deployment_run = _paper_run(deployment_id=uuid4())

    result = PromotionGateService().evaluate(_context(paper_runs=(other_account_run, other_deployment_run)))

    assert result.eligible is False
    assert "missing_successful_paper_run" in result.blocking_reasons


def test_scoped_paper_warnings_ignore_other_paper_accounts() -> None:
    noisy_other_account_run = _paper_run(
        broker_account_id=OTHER_PAPER_ACCOUNT_ID,
        started_at=NOW - timedelta(hours=2),
        trade_count=1,
        submitted_order_count=10,
        rejected_order_count=6,
        max_drawdown_pct=25,
        broker_sync_inconsistent_event_count=3,
    )

    result = PromotionGateService().evaluate(_context(paper_runs=(_paper_run(), noisy_other_account_run)))

    assert result.eligible is True
    assert result.warnings == []


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


def test_missing_walk_forward_produces_high_warning_without_blocking() -> None:
    program = _program()
    result = PromotionGateService().evaluate(
        _context(
            program=program,
            validation_evidence=(_validation_evidence(program, EvidenceKind.OPTIMIZATION),),
        )
    )

    assert result.eligible is True
    assert result.blocking_reasons == []
    assert "missing_walk_forward_evidence" in result.warnings
    assert result.warning_severities["missing_walk_forward_evidence"] == "high"


def test_missing_optimization_produces_warning_without_blocking() -> None:
    program = _program()
    result = PromotionGateService().evaluate(
        _context(
            program=program,
            validation_evidence=(_validation_evidence(program, EvidenceKind.WALK_FORWARD),),
        )
    )

    assert result.eligible is True
    assert result.blocking_reasons == []
    assert "missing_optimization_evidence" in result.warnings
    assert result.warning_severities["missing_optimization_evidence"] in {"medium", "high"}


def test_existing_recommended_validation_evidence_removes_warnings() -> None:
    result = PromotionGateService().evaluate(_context())

    assert "missing_optimization_evidence" not in result.warnings
    assert "missing_walk_forward_evidence" not in result.warnings
    assert result.warning_severities == {}


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
        account_id=SOURCE_ACCOUNT_ID,
        issues=(
            BrokerReconciliationIssue(
                issue_type=BrokerReconciliationIssueType.POSITION_MISMATCH,
                account_id=SOURCE_ACCOUNT_ID,
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


def test_gate_returns_deterministic_blockers_without_mutating_state() -> None:
    program = _program(status=ProgramStatus.DRAFT)
    control_plane = ControlPlane(global_kill_active=True)
    control_plane.pause_account(SOURCE_ACCOUNT_ID)
    control_plane.pause_account(TARGET_ACCOUNT_ID)
    context = _context(
        program=program,
        broker_sync_state=_broker_sync(stale=True),
        control_plane=control_plane,
        paper_runs=(),
        simulation_evidence=(),
    )
    before = {
        "program": program.model_dump(mode="json"),
        "broker_sync": context.broker_sync_state.model_dump(mode="json"),
        "global_kill_active": control_plane.global_kill_active,
        "source_account_paused": control_plane.is_account_paused(SOURCE_ACCOUNT_ID),
        "target_account_paused": control_plane.is_account_paused(TARGET_ACCOUNT_ID),
        "paper_runs": tuple(run.model_dump(mode="json") for run in context.paper_runs),
        "simulation_evidence": tuple(evidence.model_dump(mode="json") for evidence in context.simulation_evidence),
        "validation_evidence": tuple(evidence.model_dump(mode="json") for evidence in context.validation_evidence),
    }

    first = PromotionGateService().evaluate(context)
    second = PromotionGateService().evaluate(context)

    assert first.blocking_reasons == second.blocking_reasons
    assert first.warnings == second.warnings
    assert first.blocking_reasons == [
        "program_not_frozen",
        "missing_successful_paper_run",
        "broker_sync_stale",
        "global_kill_active",
        "source_account_pause_active",
        "target_account_pause_active",
        "missing_required_simulation_evidence",
    ]
    assert before == {
        "program": program.model_dump(mode="json"),
        "broker_sync": context.broker_sync_state.model_dump(mode="json"),
        "global_kill_active": control_plane.global_kill_active,
        "source_account_paused": control_plane.is_account_paused(SOURCE_ACCOUNT_ID),
        "target_account_paused": control_plane.is_account_paused(TARGET_ACCOUNT_ID),
        "paper_runs": tuple(run.model_dump(mode="json") for run in context.paper_runs),
        "simulation_evidence": tuple(evidence.model_dump(mode="json") for evidence in context.simulation_evidence),
        "validation_evidence": tuple(evidence.model_dump(mode="json") for evidence in context.validation_evidence),
    }


def test_promotion_gate_does_not_depend_on_feature_engine() -> None:
    source = inspect.getsource(promotion_service)

    assert "FeatureEngine" not in source
    assert "backend.app.features" not in source


def test_promotion_gate_does_not_depend_on_signal_engine() -> None:
    source = inspect.getsource(promotion_service)

    assert "SignalEngine" not in source
    assert "backend.app.decision" not in source
