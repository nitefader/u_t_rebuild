from __future__ import annotations

from datetime import timedelta

from backend.app.brokers import BrokerReconciliationIssueType
from backend.app.domain import GovernorMode, ProgramStatus, SIM_LAB_MODES, TradingMode

from .models import PromotionEvaluationContext, PromotionResult


class PromotionGateService:
    """Deterministic pre-runtime gate for BROKER_PAPER to BROKER_LIVE promotion."""

    def __init__(
        self,
        *,
        limited_trade_count_threshold: int = 10,
        short_runtime_threshold: timedelta = timedelta(days=1),
        high_rejection_rate_threshold: float = 0.20,
        high_drawdown_pct_threshold: float = 10.0,
    ) -> None:
        self._limited_trade_count_threshold = limited_trade_count_threshold
        self._short_runtime_threshold = short_runtime_threshold
        self._high_rejection_rate_threshold = high_rejection_rate_threshold
        self._high_drawdown_pct_threshold = high_drawdown_pct_threshold

    def evaluate(self, context: PromotionEvaluationContext) -> PromotionResult:
        blocking_reasons = self._blocking_reasons(context)
        warnings = self._warnings(context)
        return PromotionResult(
            program_id=context.program.program_id,
            deployment_id=context.deployment_id,
            eligible=not blocking_reasons,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
        )

    def _blocking_reasons(self, context: PromotionEvaluationContext) -> list[str]:
        reasons: list[str] = []

        if context.program.status != ProgramStatus.FROZEN:
            reasons.append("program_not_frozen")
        if context.current_mode != TradingMode.BROKER_PAPER:
            reasons.append("current_mode_not_broker_paper")
        if not any(run.succeeded for run in context.paper_runs):
            reasons.append("missing_successful_paper_run")
        if context.broker_sync_state.is_stale:
            reasons.append("broker_sync_stale")
        if context.control_plane.global_kill_active:
            reasons.append("global_kill_active")
        if context.control_plane.is_account_paused(context.account_id):
            reasons.append("account_pause_active")
        if not context.governor.active:
            reasons.append("portfolio_governor_inactive")
        if not context.governor.enforcing:
            reasons.append("portfolio_governor_not_enforcing")
        if self._has_unresolved_reconciliation_mismatch(context):
            reasons.append("unresolved_broker_reconciliation_mismatch")
        if any(run.runtime_errors for run in context.paper_runs):
            reasons.append("paper_runtime_errors_present")
        if not self._has_required_simulation_evidence(context):
            reasons.append("missing_required_simulation_evidence")
        if any(evidence.rejected_trades_due_to_system_issue_count > 0 for evidence in context.simulation_evidence):
            reasons.append("simulation_system_rejections_present")

        return reasons

    def _warnings(self, context: PromotionEvaluationContext) -> list[str]:
        warnings: list[str] = []
        total_trade_count = sum(run.trade_count for run in context.paper_runs if run.succeeded)
        total_duration = sum(
            (run.ended_at - run.started_at for run in context.paper_runs if run.succeeded),
            timedelta(),
        )
        submitted = sum(run.submitted_order_count for run in context.paper_runs)
        rejected = sum(run.rejected_order_count for run in context.paper_runs)
        max_drawdown = max((run.max_drawdown_pct for run in context.paper_runs), default=0)
        inconsistent_sync_events = sum(run.broker_sync_inconsistent_event_count for run in context.paper_runs)

        if total_trade_count < self._limited_trade_count_threshold:
            warnings.append("limited_paper_trade_count")
        if total_duration < self._short_runtime_threshold:
            warnings.append("short_paper_runtime_duration")
        if submitted > 0 and (rejected / submitted) > self._high_rejection_rate_threshold:
            warnings.append("high_paper_rejection_rate")
        if max_drawdown > self._high_drawdown_pct_threshold:
            warnings.append("high_paper_drawdown_observed")
        if inconsistent_sync_events > 0:
            warnings.append("inconsistent_broker_sync_events")

        return warnings

    def _has_required_simulation_evidence(self, context: PromotionEvaluationContext) -> bool:
        return any(
            evidence.program_version_id == context.program.id
            and evidence.mode in SIM_LAB_MODES
            and evidence.governor_mode == GovernorMode.ENFORCED
            and evidence.succeeded
            for evidence in context.simulation_evidence
        )

    def _has_unresolved_reconciliation_mismatch(self, context: PromotionEvaluationContext) -> bool:
        report = context.reconciliation_report
        if report is None:
            return False
        mismatch_types = {
            BrokerReconciliationIssueType.MISSING_LOCAL_ORDER,
            BrokerReconciliationIssueType.MISSING_BROKER_ORDER,
            BrokerReconciliationIssueType.MISMATCHED_FILL,
            BrokerReconciliationIssueType.POSITION_MISMATCH,
        }
        return any(issue.issue_type in mismatch_types for issue in report.issues)
