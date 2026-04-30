from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.broker_accounts.models import BrokerAccount
from backend.app.brokers import BrokerAdapter, BrokerSync
from backend.app.control_plane import ControlPlane
from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now
from backend.app.features import FeatureCache, IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.broker_accounts.models import AccountRiskConfig
from backend.app.domain.risk_plan import RiskPlanConfig
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.governor import (
    BrokerSyncFreshness,
    GovernorPolicyResolver,
    PortfolioGovernor,
    PortfolioSnapshot,
)
from backend.app.orders import OrderManager
from backend.app.pipeline import PipelineEvent, PipelineResult, RuntimeOrchestrator

from .models import DeploymentContext, RuntimeState, RuntimeStatus


class BrokerRuntimeLoopStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    state: RuntimeStatus
    running: bool = False
    last_bar_timestamp: datetime | None = None
    last_signal_timestamp: datetime | None = None
    last_governor_decision: dict[str, object] | None = None
    last_order_id: UUID | None = None
    last_broker_sync_timestamp: datetime | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class BrokerRuntimeDeployment:
    deployment: DeploymentContext
    components: ResolvedDeploymentComponents
    account_id: UUID
    active: bool = True
    initial_cash: float = 100_000
    account_ids: tuple[UUID, ...] = ()
    live_order_submission_enabled: bool = False


class BrokerRuntimeOrchestrator:
    """Account trading coordinator for broker-backed deployments.

    The service owns lifecycle gates and loop state. It delegates indicator
    updates, signal evaluation, governor checks, order creation, broker
    submission, and broker truth application to the existing production
    components.
    """

    def __init__(
        self,
        *,
        deployments: Iterable[BrokerRuntimeDeployment] = (),
        runtime_store: object | None = None,
        broker_adapter: BrokerAdapter,
        broker_sync: BrokerSync,
        order_manager: OrderManager,
        control_plane: ControlPlane,
        governor: PortfolioGovernor | None = None,
        feature_engine_factory: Callable[[], IncrementalFeatureEngine] = IncrementalFeatureEngine,
        signal_engine: object | None = None,
        portfolio_snapshot_factory: Callable[[UUID], PortfolioSnapshot] | None = None,
        bar_source: Callable[[UUID], NormalizedBar | None] | None = None,
        recovery_orchestrator: object | None = None,
    ) -> None:
        self._runtime_store = runtime_store
        self._broker_adapter = broker_adapter
        self._broker_sync = broker_sync
        self._order_manager = order_manager
        self._control_plane = control_plane
        self._governor = governor or PortfolioGovernor()
        self._feature_engine_factory = feature_engine_factory
        self._signal_engine = signal_engine
        self._portfolio_snapshot_factory = portfolio_snapshot_factory or (lambda _account_id: PortfolioSnapshot())
        self._bar_source = bar_source
        self._recovery_orchestrator = recovery_orchestrator
        self._deployments = {entry.deployment.deployment_id: entry for entry in deployments}
        self._pipelines: dict[UUID, RuntimeOrchestrator] = {}
        self._feature_caches: dict[UUID, FeatureCache] = {}
        self._latest_events: list[PipelineEvent] = []
        self._recovery_completed: set[UUID] = set()

    @property
    def latest_events(self) -> tuple[PipelineEvent, ...]:
        return tuple(self._latest_events)

    def load_active_account_deployments(self) -> tuple[BrokerRuntimeDeployment, ...]:
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_active_account_deployments"):
            loaded = tuple(self._runtime_store.list_active_account_deployments())
            self._deployments.update({entry.deployment.deployment_id: entry for entry in loaded})
        return tuple(entry for entry in self._deployments.values() if entry.active and entry.deployment.mode in {TradingMode.BROKER_PAPER.value, TradingMode.BROKER_LIVE.value})

    def start_deployment_runtime(self, deployment_id: UUID) -> BrokerRuntimeLoopStatus:
        entry = self._deployment_entry(deployment_id)
        if entry is None:
            return self._block_unknown(deployment_id, "missing_deployment")
        blocked = self._preflight(entry, require_recovery=True)
        if blocked is not None:
            return blocked
        self._pipeline_for(entry)
        state = self._save_state(deployment_id, status=RuntimeStatus.RUNNING, last_error=None)
        return self._status_from_state(state)

    def stop_deployment_runtime(self, deployment_id: UUID) -> BrokerRuntimeLoopStatus:
        self._pipelines.pop(deployment_id, None)
        state = self._save_state(deployment_id, status=RuntimeStatus.STOPPED)
        return self._status_from_state(state)

    def recover_and_resume(self, deployment_id: UUID) -> BrokerRuntimeLoopStatus:
        if self._recovery_orchestrator is not None and hasattr(self._recovery_orchestrator, "run_startup_recovery"):
            result = self._recovery_orchestrator.run_startup_recovery()
            if getattr(result, "blocked_deployments", 0):
                return self._block(deployment_id, "runtime_recovery_blocked")
        self._recovery_completed.add(deployment_id)
        return self.start_deployment_runtime(deployment_id)

    def run_once(self, deployment_id: UUID) -> PipelineResult | None:
        if self._bar_source is None:
            self._block(deployment_id, "missing_bar_source")
            return None
        bar = self._bar_source(deployment_id)
        if bar is None:
            return None
        return self.process_completed_bar(deployment_id, bar)

    def process_completed_bar(self, deployment_id: UUID, normalized_bar: NormalizedBar) -> PipelineResult | None:
        entry = self._deployment_entry(deployment_id)
        if entry is None:
            self._block_unknown(deployment_id, "missing_deployment")
            return None
        if getattr(normalized_bar, "is_complete", True) is False:
            self._block(deployment_id, "incomplete_bar")
            return None
        blocked = self._preflight(entry, require_recovery=True)
        if blocked is not None:
            return None
        if self._already_processed(entry.deployment.deployment_id, normalized_bar):
            return None

        try:
            result = self._pipeline_for(entry).process_bar(normalized_bar)
        except Exception as exc:  # noqa: BLE001 - runtime loop must fail closed.
            self._degrade(deployment_id, str(exc))
            return None

        self._latest_events.extend(result.events)
        last_decision = result.governor_decisions[-1] if result.governor_decisions else None
        last_order = result.orders[-1] if result.orders else None
        sync_state = self._freshness(entry.account_id)
        state = self._load_state(deployment_id).model_copy(
            update={
                "status": RuntimeStatus.RUNNING,
                "processed_bar_count": self._load_state(deployment_id).processed_bar_count + 1,
                "last_bar_timestamp_by_symbol_timeframe": self._updated_bar_timestamps(deployment_id, normalized_bar),
                "last_signal_timestamp": result.candidate_intents[-1].timestamp if result.candidate_intents else self._load_state(deployment_id).last_signal_timestamp,
                "signal_plan_count": self._load_state(deployment_id).signal_plan_count + len(result.signal_plans),
                "last_signal_plan_timestamp": result.signal_plans[-1].created_at if result.signal_plans else self._load_state(deployment_id).last_signal_plan_timestamp,
                "last_governor_decision": last_decision.model_dump(mode="json") if last_decision is not None else self._load_state(deployment_id).last_governor_decision,
                "last_order_id": last_order.order_id if last_order is not None else self._load_state(deployment_id).last_order_id,
                "last_broker_sync_timestamp": self._broker_sync_timestamp(sync_state),
                "last_error": None,
            }
        )
        self._persist_state(state)
        if sync_state is None or sync_state.is_stale:
            self._block(deployment_id, "broker_sync_stale_after_submit")
        return result

    def loop_status(self, deployment_id: UUID) -> BrokerRuntimeLoopStatus:
        return self._status_from_state(self._load_state(deployment_id))

    def _deployment_entry(self, deployment_id: UUID) -> BrokerRuntimeDeployment | None:
        if deployment_id not in self._deployments:
            self.load_active_account_deployments()
        return self._deployments.get(deployment_id)

    def _preflight(self, entry: BrokerRuntimeDeployment, *, require_recovery: bool) -> BrokerRuntimeLoopStatus | None:
        deployment_id = entry.deployment.deployment_id
        if not entry.active:
            return self._block(deployment_id, "deployment_not_active")
        try:
            deployment_mode = TradingMode(entry.deployment.mode)
        except ValueError:
            return self._block(deployment_id, "deployment_not_broker_active")
        if deployment_mode not in (TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE):
            return self._block(deployment_id, "deployment_not_broker_active")
        if entry.deployment.status in {RuntimeStatus.BLOCKED, RuntimeStatus.BLOCKED_RECOVERY, RuntimeStatus.ERROR, RuntimeStatus.KILLED}:
            return self._block(deployment_id, f"deployment_status_not_runnable:{entry.deployment.status.value}")
        runtime_state = self._load_state(deployment_id)
        if runtime_state.status == RuntimeStatus.DEGRADED:
            return self._status_from_state(runtime_state)
        account = self._broker_account(entry.account_id)
        if account is None:
            return self._block(deployment_id, "missing_broker_account")
        if account.mode != deployment_mode:
            return self._block(deployment_id, "broker_account_mode_mismatch")
        if require_recovery and not self._recovery_ready(deployment_id):
            return self._block(deployment_id, "runtime_recovery_not_completed")
        control = self._control_plane.can_open_new_position(
            account_id=entry.account_id,
            deployment_id=deployment_id,
            symbol="*",
            side="*",
        )
        if not control.allowed:
            return self._block(deployment_id, control.reason)
        freshness = self._freshness(entry.account_id)
        if freshness is None:
            return self._block(deployment_id, "missing_broker_sync_freshness")
        if freshness.is_stale:
            return self._block(deployment_id, freshness.stale_reason or "broker_sync_stale")
        return None

    def _pipeline_for(self, entry: BrokerRuntimeDeployment) -> RuntimeOrchestrator:
        deployment_id = entry.deployment.deployment_id
        existing = self._pipelines.get(deployment_id)
        if existing is not None:
            return existing
        cache = self._feature_caches.setdefault(deployment_id, FeatureCache())
        pipeline = RuntimeOrchestrator(
            account_id=entry.account_id,
            account_ids=entry.account_ids or (entry.account_id,),
            deployment=entry.deployment,
            components=entry.components,
            initial_cash=entry.initial_cash,
            feature_engine=self._feature_engine_factory(),
            signal_engine=self._signal_engine,
            governor=self._governor,
            governor_policy_resolver=self._build_governor_policy_resolver(),
            order_manager=self._order_manager,
            broker_adapter=self._broker_adapter,
            broker_sync=self._broker_sync,
            broker_freshness=self._governor_freshness(entry.account_id),
            broker_freshness_by_account={
                account_id: self._governor_freshness(account_id)
                for account_id in (entry.account_ids or (entry.account_id,))
            },
            portfolio_snapshot=self._portfolio_snapshot_factory(entry.account_id),
            portfolio_snapshot_by_account={
                account_id: self._portfolio_snapshot_factory(account_id)
                for account_id in (entry.account_ids or (entry.account_id,))
            },
            feature_cache=cache,
            control_plane=self._control_plane,
            runtime_store=self._runtime_store,
            live_order_submission_enabled=entry.live_order_submission_enabled,
        )
        self._pipelines[deployment_id] = pipeline
        return pipeline

    def _broker_account(self, account_id: UUID) -> BrokerAccount | None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_broker_account"):
            return None
        try:
            return self._runtime_store.load_broker_account(account_id)
        except KeyError:
            return None

    def _build_governor_policy_resolver(self) -> GovernorPolicyResolver | None:
        # Slice A finding #9: production composition root must wire the
        # resolver, otherwise operator AccountRiskConfig edits do not gate.
        # Returns None when the runtime store cannot supply lookups (test
        # fixtures, in-memory orchestrators) so the legacy single-policy
        # path stays intact.
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_governor_policy_inputs"):
            return None

        runtime_store = self._runtime_store

        # T-6 (MAP §7 D7): TOCTOU hardening. The resolver reads both
        # AccountRiskConfig and the per-horizon RiskPlanConfig in ONE
        # ``runtime_store.load_governor_policy_inputs`` call. The
        # SQLiteRuntimeStore implementation wraps both reads in a single
        # connection so a concurrent operator PUT to /risk-plan-map
        # cannot interleave between them and hand the resolver a
        # half-applied state. WAL mode at composition root
        # (SQLiteSessionFactory.connect) keeps the writer non-blocking.
        # Per D7 the doctrine choice is single-conn + WAL only — no
        # optimistic version stamps, no mid-evaluation rejection.
        # Updates apply to the next evaluation (last-writer-wins outside
        # the evaluation window).
        # Adversarial-critic BUG-5 (T-6 Pass 8): no try/except KeyError
        # wrapper here. ``SQLiteRuntimeStore.load_governor_policy_inputs``
        # never raises ``KeyError`` for missing rows — it returns
        # ``(None, None)`` natively. A blanket ``except KeyError`` would
        # only mask a real bug (e.g. malformed payload in ``_load_model``)
        # by converting it to a silent "no override" path that bypasses
        # the resolver's ``_safe_lookup`` graceful-degrade logging. Real
        # exceptions propagate into ``_safe_lookup`` which logs them and
        # falls back to floor per D7.
        return GovernorPolicyResolver(
            get_policy_inputs=runtime_store.load_governor_policy_inputs,
        )

    def _freshness(self, account_id: UUID):
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_broker_sync_freshness"):
            return None
        try:
            return self._runtime_store.load_broker_sync_freshness(account_id)
        except KeyError:
            return None

    def _governor_freshness(self, account_id: UUID) -> BrokerSyncFreshness:
        state = self._freshness(account_id)
        if state is None:
            return BrokerSyncFreshness(is_stale=True, reason="missing_broker_sync_freshness")
        return BrokerSyncFreshness(
            is_stale=state.is_stale,
            last_synced_at=self._broker_sync_timestamp(state),
            reason=state.stale_reason,
        )

    def _recovery_ready(self, deployment_id: UUID) -> bool:
        if deployment_id in self._recovery_completed:
            return True
        state = self._load_state(deployment_id)
        return state.status in {RuntimeStatus.RECOVERED_READY, RuntimeStatus.RUNNING, RuntimeStatus.STOPPED}

    def _already_processed(self, deployment_id: UUID, bar: NormalizedBar) -> bool:
        state = self._load_state(deployment_id)
        latest = state.last_bar_timestamp_by_symbol_timeframe.get(self._bar_key(bar))
        return latest is not None and latest >= bar.timestamp

    def _updated_bar_timestamps(self, deployment_id: UUID, bar: NormalizedBar) -> dict[str, datetime]:
        timestamps = dict(self._load_state(deployment_id).last_bar_timestamp_by_symbol_timeframe)
        timestamps[self._bar_key(bar)] = bar.timestamp
        return timestamps

    def _bar_key(self, bar: NormalizedBar) -> str:
        return f"{bar.symbol.upper()}:{bar.timeframe}"

    def _block_unknown(self, deployment_id: UUID, reason: str) -> BrokerRuntimeLoopStatus:
        state = RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.BLOCKED, last_error=reason)
        self._persist_state(state)
        return self._status_from_state(state)

    def _block(self, deployment_id: UUID, reason: str) -> BrokerRuntimeLoopStatus:
        state = self._save_state(deployment_id, status=RuntimeStatus.BLOCKED, last_error=reason)
        return self._status_from_state(state)

    def _degrade(self, deployment_id: UUID, reason: str) -> BrokerRuntimeLoopStatus:
        self._pipelines.pop(deployment_id, None)
        state = self._save_state(deployment_id, status=RuntimeStatus.DEGRADED, last_error=reason)
        return self._status_from_state(state)

    def _save_state(self, deployment_id: UUID, *, status: RuntimeStatus, last_error: str | None = None) -> RuntimeState:
        state = self._load_state(deployment_id).model_copy(update={"status": status, "last_error": last_error})
        self._persist_state(state)
        return state

    def _load_state(self, deployment_id: UUID) -> RuntimeState:
        if self._runtime_store is not None and hasattr(self._runtime_store, "load_deployment_runtime_state"):
            try:
                return self._runtime_store.load_deployment_runtime_state(deployment_id)
            except KeyError:
                pass
        return RuntimeState(deployment_id=deployment_id)

    def _persist_state(self, state: RuntimeState) -> RuntimeState:
        if self._runtime_store is not None and hasattr(self._runtime_store, "save_deployment_runtime_state"):
            return self._runtime_store.save_deployment_runtime_state(state)
        return state

    def _status_from_state(self, state: RuntimeState) -> BrokerRuntimeLoopStatus:
        return BrokerRuntimeLoopStatus(
            deployment_id=state.deployment_id,
            state=state.status,
            running=state.status == RuntimeStatus.RUNNING,
            last_bar_timestamp=max(state.last_bar_timestamp_by_symbol_timeframe.values(), default=None),
            last_signal_timestamp=state.last_signal_timestamp,
            last_governor_decision=state.last_governor_decision,
            last_order_id=state.last_order_id,
            last_broker_sync_timestamp=state.last_broker_sync_timestamp,
            last_error=state.last_error,
        )

    def _broker_sync_timestamp(self, state) -> datetime | None:
        if state is None:
            return None
        return max(
            (
                timestamp
                for timestamp in (
                    state.last_event_at,
                    state.last_poll_sync_at,
                    state.last_successful_sync_at,
                    state.last_sync_at,
                )
                if timestamp is not None
            ),
            default=None,
        )
