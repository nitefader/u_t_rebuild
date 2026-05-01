from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.broker_accounts.models import BrokerAccount
from backend.app.brokers import BrokerAdapter, BrokerSync
from backend.app.brokers import (
    BrokerAdapterError,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.control_plane import ControlPlane
from backend.app.domain import CandidateSide, TradingMode
from backend.app.domain._base import utc_now
from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedDeploymentComponents,
    build_feature_plan,
)
from backend.app.broker_accounts.models import AccountRiskConfig
from backend.app.domain.risk_plan import RiskPlanConfig
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.governor import (
    BrokerSyncFreshness,
    GovernorPolicyResolver,
    PortfolioGovernor,
    PortfolioSnapshot,
)
from backend.app.runtime.daily_account_state import DailyAccountState, DailyAccountStateAggregator, _et_market_day as _daily_et_market_day
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.orders.protective_placer import ProtectiveOrderPlacer
from backend.app.pipeline import PipelineEvent, PipelineEventType, PipelineResult, RuntimeOrchestrator

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


StartupWarmupBarsSource = Callable[[BrokerRuntimeDeployment, str, str, int], Iterable[NormalizedBar]]


class _StartupFeatureRecoveryError(RuntimeError):
    def __init__(self, reason: str, **details: object) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = details


class BrokerRuntimeOrchestrator:
    """Account trading coordinator for broker-backed deployments.

    The service owns lifecycle gates and loop state. It delegates indicator
    updates, signal evaluation, governor checks, order creation, broker
    submission, and broker truth application to the existing production
    components.
    """

    _POSITION_QTY_TOLERANCE = 1e-6
    _PROTECTIVE_INTENTS = {
        InternalOrderIntent.STOP_LOSS,
        InternalOrderIntent.STOP,
        InternalOrderIntent.TRAIL,
        InternalOrderIntent.TAKE_PROFIT,
        InternalOrderIntent.TARGET,
        InternalOrderIntent.RUNNER,
        InternalOrderIntent.SCALE,
    }

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
        startup_warmup_bars_source: StartupWarmupBarsSource | None = None,
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
        self._startup_warmup_bars_source = startup_warmup_bars_source
        self._recovery_orchestrator = recovery_orchestrator
        self._deployments = {entry.deployment.deployment_id: entry for entry in deployments}
        self._pipelines: dict[UUID, RuntimeOrchestrator] = {}
        self._feature_caches: dict[UUID, FeatureCache] = {}
        self._latest_events: list[PipelineEvent] = []
        self._recovery_completed: set[UUID] = set()
        # T-7: daily risk state aggregator + boot-load from persisted store.
        self._daily_aggregator = DailyAccountStateAggregator()
        self._daily_states: dict[UUID, DailyAccountState] = self._boot_load_daily_states()

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
        self._recover_startup_position_protection(entry)
        state = self._save_state(deployment_id, status=RuntimeStatus.RUNNING, last_error=None)
        return self._status_from_state(state)

    def stop_deployment_runtime(self, deployment_id: UUID) -> BrokerRuntimeLoopStatus:
        self._pipelines.pop(deployment_id, None)
        state = self._save_state(deployment_id, status=RuntimeStatus.STOPPED)
        return self._status_from_state(state)

    def evict_deployment_caches(self, deployment_id: UUID) -> BrokerRuntimeDeployment | None:
        # Drop both the resolved-components entry and the compiled pipeline so
        # the next bar tick rebuilds them from persistence. Used after
        # operator rebinds (Controls / ExecutionPlan / Strategy) to force a
        # fresh load without restarting the API process.
        self._pipelines.pop(deployment_id, None)
        self._deployments.pop(deployment_id, None)
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_active_account_deployments"):
            for entry in self._runtime_store.list_active_account_deployments():
                self._deployments[entry.deployment.deployment_id] = entry
        return self._deployments.get(deployment_id)

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

    def _recover_startup_position_protection(self, entry: BrokerRuntimeDeployment) -> None:
        """Re-attach missing protective orders for Deployment-owned broker positions.

        Restart doctrine: BrokerSync owns broker truth, OrderManager owns
        internal orders, BrokerAdapter owns submit. This pass reads fresh
        broker positions through BrokerSync, matches them to filled
        SignalPlan-origin entry parents for this Deployment, and recreates
        the same post-fill OCO protection the hot fill path would have
        created. It deliberately refuses ambiguous same-account/same-symbol
        ownership instead of guessing.
        """

        account_ids = entry.account_ids or (entry.account_id,)
        for account_id in account_ids:
            positions = self._startup_positions(account_id, deployment_id=entry.deployment.deployment_id)
            if not positions:
                continue
            orders = tuple(self._order_manager.ledger.by_account(account_id))
            for symbol, parents in self._startup_parent_groups(
                orders=orders,
                deployment_id=entry.deployment.deployment_id,
            ).items():
                position = self._position_for_symbol(positions, symbol)
                if position is None or not self._broker_position_is_active(position):
                    continue
                matching_parents = tuple(parent for parent in parents if self._position_side_matches_parent(position, parent))
                if not matching_parents:
                    continue
                if self._ambiguous_position_ownership(
                    orders=orders,
                    deployment_id=entry.deployment.deployment_id,
                    symbol=symbol,
                    position=position,
                ):
                    self._record_startup_protection_event(
                        deployment_id=entry.deployment.deployment_id,
                        event_type=PipelineEventType.PROTECTION_NAKED,
                        symbol=symbol,
                        message="startup protection skipped because broker position ownership is ambiguous",
                        details={
                            "account_id": str(account_id),
                            "reason": "ambiguous_position_ownership",
                        },
                    )
                    continue
                position_qty = abs(position.qty)
                for parent in matching_parents:
                    self._submit_created_protective_children(entry=entry, parent=parent)
                covered_qty = self._active_protective_qty_for_symbol(
                    orders=tuple(self._order_manager.ledger.by_account(account_id)),
                    deployment_id=entry.deployment.deployment_id,
                    symbol=symbol,
                )
                remaining_qty = position_qty - covered_qty
                if remaining_qty <= self._POSITION_QTY_TOLERANCE:
                    continue
                for parent in self._newest_first(matching_parents):
                    parent_covered = self._order_manager.cumulative_covered_qty_for_signal_plan(
                        signal_plan_id=parent.signal_plan_id,
                        parent_order_id=parent.order_id,
                    )
                    parent_available_qty = max(parent.filled_quantity - parent_covered, 0.0)
                    if parent_available_qty <= self._POSITION_QTY_TOLERANCE:
                        continue
                    cover_qty = min(parent_available_qty, remaining_qty)
                    self._recover_parent_startup_protection(
                        entry=entry,
                        parent=parent,
                        position=position,
                        cover_quantity=cover_qty,
                    )
                    remaining_qty -= cover_qty
                    if remaining_qty <= self._POSITION_QTY_TOLERANCE:
                        break
                if remaining_qty > self._POSITION_QTY_TOLERANCE:
                    self._record_startup_protection_event(
                        deployment_id=entry.deployment.deployment_id,
                        event_type=PipelineEventType.PROTECTION_NAKED,
                        symbol=symbol,
                        message="startup protection could not fully cover broker position from filled deployment lineage",
                        details={
                            "account_id": str(account_id),
                            "reason": "position_quantity_lineage_shortfall",
                            "broker_qty": position_qty,
                            "covered_qty": position_qty - remaining_qty,
                            "remaining_qty": remaining_qty,
                        },
                    )

    def _startup_positions(
        self,
        account_id: UUID,
        *,
        deployment_id: UUID,
    ) -> tuple[BrokerPositionSnapshot, ...]:
        try:
            positions = tuple(self._broker_sync.sync_positions(account_id))
        except Exception as exc:  # noqa: BLE001 - startup recovery must fail closed per position.
            self._record_startup_protection_event(
                deployment_id=deployment_id,
                event_type=PipelineEventType.PROTECTION_NAKED,
                symbol=None,
                message="startup protection skipped because BrokerSync could not refresh positions",
                details={
                    "account_id": str(account_id),
                    "reason": "broker_sync_position_refresh_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return ()
        try:
            self._broker_sync.sync_open_orders(account_id)
        except Exception as exc:  # noqa: BLE001 - position truth is still usable; surface the gap.
            self._record_startup_protection_event(
                deployment_id=deployment_id,
                event_type=PipelineEventType.PROTECTION_NAKED,
                symbol=None,
                message="startup protection could not refresh open broker orders before reconciliation",
                details={
                    "account_id": str(account_id),
                    "reason": "broker_sync_open_order_refresh_failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        return positions

    def _recover_parent_startup_protection(
        self,
        *,
        entry: BrokerRuntimeDeployment,
        parent: InternalOrder,
        position: BrokerPositionSnapshot,
        cover_quantity: float | None = None,
    ) -> None:
        if parent.order_class == "bracket":
            return
        self._submit_created_protective_children(entry=entry, parent=parent)

        already_covered = self._order_manager.cumulative_covered_qty_for_signal_plan(
            signal_plan_id=parent.signal_plan_id,
            parent_order_id=parent.order_id,
        )
        desired_new_qty = (
            cover_quantity
            if cover_quantity is not None
            else parent.filled_quantity - already_covered
        )
        if desired_new_qty <= self._POSITION_QTY_TOLERANCE:
            return
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_signal_plan"):
            self._record_missing_startup_intent(parent, reason="missing_signal_plan_store")
            return
        try:
            signal_plan = self._runtime_store.load_signal_plan(parent.signal_plan_id)
        except Exception as exc:  # noqa: BLE001 - operator needs the naked reason, not a crash.
            self._record_missing_startup_intent(
                parent,
                reason="missing_signal_plan",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return
        signal_plan = self._startup_signal_plan_with_component_intent(entry, signal_plan)
        try:
            signal_plan = self._startup_signal_plan_with_recomputed_pricing_context(
                entry=entry,
                signal_plan=signal_plan,
            )
        except _StartupFeatureRecoveryError as exc:
            self._record_missing_startup_intent(
                parent,
                reason=exc.reason,
                extra_details=exc.details,
            )
            return
        try:
            placement = ProtectiveOrderPlacer().compute_protective_plan(
                signal_plan=signal_plan,
                parent_order_id=parent.order_id,
                account_id=parent.account_id,
                fill_price=position.avg_entry_price,
                cumulative_filled_qty=already_covered + desired_new_qty,
                already_covered_qty=already_covered,
            )
            if not placement.legs:
                if signal_plan.stop is not None or signal_plan.targets:
                    self._record_missing_startup_intent(parent, reason="no_legs_from_intent")
                return
            child = self._order_manager.create_protective_oco_order_post_fill(
                plan=placement,
                parent_order=parent,
            )
        except Exception as exc:  # noqa: BLE001 - per-position recovery should not kill other deployments.
            self._record_missing_startup_intent(
                parent,
                reason="protective_plan_create_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return
        if child.status == InternalOrderStatus.CREATED:
            self._submit_startup_protective_child(entry=entry, parent=parent, child=child)

    @staticmethod
    def _startup_signal_plan_with_component_intent(
        entry: BrokerRuntimeDeployment,
        signal_plan,
    ):
        """Recover pre-fix v4 ATR stop rules without mutating persisted truth."""

        if signal_plan.stop is None or signal_plan.stop.rule:
            return signal_plan
        if str(signal_plan.stop.type).lower() != "atr":
            return signal_plan
        strategy_v4 = getattr(entry.components, "strategy_version_v4", None)
        if strategy_v4 is None:
            return signal_plan
        for stop in getattr(strategy_v4, "stops", ()):
            if getattr(stop, "mode", None) != "simple":
                continue
            if getattr(stop, "simple_type", None) != "ATR":
                continue
            value = getattr(stop, "simple_value", None)
            if value is None:
                continue
            try:
                multiple = float(value)
            except (TypeError, ValueError):
                continue
            if multiple <= 0:
                continue
            return signal_plan.model_copy(
                update={
                    "stop": signal_plan.stop.model_copy(
                        update={"rule": f"atr:{multiple}"}
                    )
                }
            )
        return signal_plan

    def _startup_signal_plan_with_recomputed_pricing_context(
        self,
        *,
        entry: BrokerRuntimeDeployment,
        signal_plan,
    ):
        if not self._signal_plan_has_atr_pricing_intent(signal_plan):
            return signal_plan
        if self._signal_plan_has_available_atr_value(signal_plan):
            return signal_plan
        if self._startup_warmup_bars_source is None:
            raise _StartupFeatureRecoveryError(
                "startup_atr_recompute_bars_source_missing",
                symbol=signal_plan.symbol,
            )
        try:
            plan = build_feature_plan(entry.components, consumer="runtime")
        except Exception as exc:  # noqa: BLE001 - exact blocker belongs in Operations.
            raise _StartupFeatureRecoveryError(
                "startup_atr_feature_plan_failed",
                symbol=signal_plan.symbol,
                error_type=type(exc).__name__,
                error=str(exc),
            ) from exc

        symbol = signal_plan.symbol.upper()
        if symbol not in plan.symbols:
            plan = plan.model_copy(update={"symbols": tuple(sorted({*plan.symbols, symbol}))})

        atr_specs = tuple(
            (spec, feature_key)
            for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True)
            if spec.kind == "atr"
        )
        if not atr_specs:
            raise _StartupFeatureRecoveryError(
                "startup_atr_feature_requirement_missing",
                symbol=symbol,
            )

        cache = FeatureCache()
        engine = self._feature_engine_factory()
        bars_seen_by_timeframe: dict[str, int] = {}
        for timeframe in sorted({spec.timeframe for spec, _key in atr_specs}):
            warmup_bars = max(int(plan.warmup_by_timeframe.get(timeframe, 0)), 1)
            try:
                bars = tuple(
                    bar.model_copy(update={"symbol": bar.symbol.upper()})
                    for bar in self._startup_warmup_bars_source(entry, symbol, timeframe, warmup_bars)
                    if bar.symbol.upper() == symbol and bar.timeframe == timeframe
                )
            except Exception as exc:  # noqa: BLE001 - per-position recovery must fail closed.
                raise _StartupFeatureRecoveryError(
                    "startup_atr_warmup_bars_fetch_failed",
                    symbol=symbol,
                    timeframe=timeframe,
                    warmup_bars=warmup_bars,
                    error_type=type(exc).__name__,
                    error=str(exc),
                ) from exc

            deduped = self._dedupe_bars_by_timestamp(bars)
            bars_seen_by_timeframe[timeframe] = len(deduped)
            for bar in deduped:
                try:
                    engine.update(plan=plan, bar=bar, cache=cache)
                except Exception as exc:  # noqa: BLE001
                    raise _StartupFeatureRecoveryError(
                        "startup_atr_feature_replay_failed",
                        symbol=symbol,
                        timeframe=timeframe,
                        warmup_bars=warmup_bars,
                        bars_seen=len(deduped),
                        error_type=type(exc).__name__,
                        error=str(exc),
                    ) from exc

        recomputed_values: dict[str, object] = {}
        unavailable: list[dict[str, object]] = []
        for spec, feature_key in atr_specs:
            snapshot = cache.latest_snapshot_at_or_before(
                symbol=symbol,
                timeframe=spec.timeframe,
                timestamp=datetime.max.replace(tzinfo=timezone.utc),
            )
            feature_value = None if snapshot is None else snapshot.values.get(feature_key)
            if (
                feature_value is not None
                and feature_value.availability == FeatureAvailability.AVAILABLE
                and feature_value.value is not None
                and feature_value.value > 0
            ):
                recomputed_values[feature_key] = float(feature_value.value)
                continue
            unavailable.append(
                {
                    "feature_key": feature_key,
                    "timeframe": spec.timeframe,
                    "availability": None if feature_value is None else feature_value.availability.value,
                    "bars_seen": bars_seen_by_timeframe.get(spec.timeframe, 0),
                    "warmup_bars": max(int(plan.warmup_by_timeframe.get(spec.timeframe, 0)), 1),
                }
            )

        if not recomputed_values:
            raise _StartupFeatureRecoveryError(
                "startup_atr_recompute_unavailable",
                symbol=symbol,
                unavailable_atr_features=unavailable,
            )

        return signal_plan.model_copy(
            update={
                "feature_snapshot": {
                    **dict(signal_plan.feature_snapshot),
                    **recomputed_values,
                }
            }
        )

    @staticmethod
    def _dedupe_bars_by_timestamp(bars: tuple[NormalizedBar, ...]) -> tuple[NormalizedBar, ...]:
        by_timestamp: dict[datetime, NormalizedBar] = {}
        for bar in bars:
            by_timestamp[bar.timestamp] = bar
        return tuple(by_timestamp[timestamp] for timestamp in sorted(by_timestamp))

    @staticmethod
    def _signal_plan_has_atr_pricing_intent(signal_plan) -> bool:
        stop_rule = signal_plan.stop.rule if signal_plan.stop is not None else None
        if BrokerRuntimeOrchestrator._is_atr_rule(stop_rule):
            return True
        if any(BrokerRuntimeOrchestrator._is_atr_rule(target.rule) for target in signal_plan.targets):
            return True
        return signal_plan.runner is not None and BrokerRuntimeOrchestrator._is_atr_rule(signal_plan.runner.trail_rule)

    @staticmethod
    def _is_atr_rule(rule: str | None) -> bool:
        return bool(rule and rule.strip().lower().startswith("atr:"))

    @staticmethod
    def _signal_plan_has_available_atr_value(signal_plan) -> bool:
        for key, raw in signal_plan.feature_snapshot.items():
            key_l = key.lower()
            if not (
                key_l.startswith("atr")
                or ".atr" in key_l
                or "technical.atr" in key_l
            ):
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            if float(raw) > 0:
                return True
        return False

    def _submit_created_protective_children(
        self,
        *,
        entry: BrokerRuntimeDeployment,
        parent: InternalOrder,
    ) -> None:
        for child in self._order_manager.ledger.by_account(parent.account_id):
            if child.parent_order_id != parent.order_id:
                continue
            if child.intent not in self._PROTECTIVE_INTENTS:
                continue
            if child.status != InternalOrderStatus.CREATED:
                continue
            self._submit_startup_protective_child(entry=entry, parent=parent, child=child)

    def _submit_startup_protective_child(
        self,
        *,
        entry: BrokerRuntimeDeployment,
        parent: InternalOrder,
        child: InternalOrder,
    ) -> None:
        try:
            result = self._startup_protective_submit_result(entry=entry, child=child)
            ledger_update = self._broker_sync.apply_result(result)
        except Exception as exc:  # noqa: BLE001
            self._record_missing_startup_intent(
                parent,
                reason="protective_submit_sync_failed",
                child_order_id=child.order_id,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return

        if result.status == BrokerOrderStatus.REJECTED or ledger_update.status == InternalOrderStatus.REJECTED:
            self._record_missing_startup_intent(
                parent,
                reason=result.reason or ledger_update.reason or "broker_rejected_protective_child",
                child_order_id=child.order_id,
            )
            return
        self._record_startup_protection_event(
            deployment_id=entry.deployment.deployment_id,
            event_type=PipelineEventType.PROTECTION_PLACED,
            symbol=child.symbol,
            message="startup protective child placed for naked broker position",
            details={
                "account_id": str(child.account_id),
                "parent_order_id": str(parent.order_id),
                "child_order_id": str(child.order_id),
                "covered_qty": child.quantity,
            },
        )

    def _startup_protective_submit_result(
        self,
        *,
        entry: BrokerRuntimeDeployment,
        child: InternalOrder,
    ) -> BrokerOrderResult:
        account = self._broker_account(child.account_id)
        if account is not None and account.mode == TradingMode.BROKER_LIVE and not entry.live_order_submission_enabled:
            return BrokerOrderResult(
                order_id=child.order_id,
                client_order_id=child.client_order_id,
                status=BrokerOrderStatus.REJECTED,
                filled_quantity=0,
                remaining_quantity=child.quantity,
                reason="live_submission_disabled",
                raw_status="preflight_rejected",
            )
        try:
            return self._broker_adapter.submit_order(child)
        except BrokerAdapterError as exc:
            return BrokerOrderResult(
                order_id=child.order_id,
                client_order_id=child.client_order_id,
                status=BrokerOrderStatus.REJECTED,
                filled_quantity=0,
                remaining_quantity=child.quantity,
                reason=self._broker_error_reason(exc),
                raw_status="adapter_error",
            )

    def _record_missing_startup_intent(
        self,
        parent: InternalOrder,
        *,
        reason: str,
        child_order_id: UUID | None = None,
        error_type: str | None = None,
        error: str | None = None,
        extra_details: dict[str, object] | None = None,
    ) -> None:
        details: dict[str, object] = {
            "account_id": str(parent.account_id),
            "parent_order_id": str(parent.order_id),
            "signal_plan_id": str(parent.signal_plan_id),
            "reason": reason,
        }
        if extra_details:
            details.update(extra_details)
        if child_order_id is not None:
            details["child_order_id"] = str(child_order_id)
        if error_type is not None:
            details["error_type"] = error_type
        if error is not None:
            details["error"] = error
        self._record_startup_protection_event(
            deployment_id=parent.deployment_id,
            event_type=PipelineEventType.PROTECTION_NAKED,
            symbol=parent.symbol,
            message="startup protection could not place intended stop/target",
            details=details,
        )

    def _record_startup_protection_event(
        self,
        *,
        deployment_id: UUID,
        event_type: PipelineEventType,
        symbol: str | None,
        message: str,
        details: dict[str, object],
    ) -> None:
        self._latest_events.append(
            PipelineEvent(
                sequence=len(self._latest_events) + 1,
                timestamp=utc_now(),
                deployment_id=deployment_id,
                event_type=event_type,
                symbol=symbol,
                message=message,
                details=details,
            )
        )

    def _startup_parent_groups(
        self,
        *,
        orders: tuple[InternalOrder, ...],
        deployment_id: UUID,
    ) -> dict[str, tuple[InternalOrder, ...]]:
        grouped: dict[str, list[InternalOrder]] = {}
        for order in orders:
            if not self._is_filled_signal_plan_parent(order):
                continue
            if order.deployment_id != deployment_id:
                continue
            grouped.setdefault(order.symbol.upper(), []).append(order)
        return {symbol: tuple(parents) for symbol, parents in grouped.items()}

    def _active_protective_qty_for_symbol(
        self,
        *,
        orders: tuple[InternalOrder, ...],
        deployment_id: UUID,
        symbol: str,
    ) -> float:
        terminal_statuses = {
            InternalOrderStatus.CANCELED,
            InternalOrderStatus.REJECTED,
            InternalOrderStatus.FAILED,
        }
        symbol_upper = symbol.upper()
        return sum(
            order.quantity
            for order in orders
            if order.deployment_id == deployment_id
            and order.symbol.upper() == symbol_upper
            and order.parent_order_id is not None
            and order.intent in self._PROTECTIVE_INTENTS
            and order.status not in terminal_statuses
        )

    @staticmethod
    def _newest_first(orders: tuple[InternalOrder, ...]) -> tuple[InternalOrder, ...]:
        return tuple(
            sorted(
                orders,
                key=lambda order: (order.updated_at, order.created_at, order.order_id.hex),
                reverse=True,
            )
        )

    def _ambiguous_position_ownership(
        self,
        *,
        orders: tuple[InternalOrder, ...],
        deployment_id: UUID,
        symbol: str,
        position: BrokerPositionSnapshot,
    ) -> bool:
        for order in orders:
            if not self._is_filled_signal_plan_parent(order):
                continue
            if order.deployment_id == deployment_id:
                continue
            if order.symbol.upper() != symbol.upper():
                continue
            if not self._position_side_matches_parent(position, order):
                continue
            return True
        return False

    @staticmethod
    def _is_filled_signal_plan_parent(order: InternalOrder) -> bool:
        return (
            order.origin == OrderOrigin.SIGNAL_PLAN
            and order.intent == InternalOrderIntent.OPEN
            and order.parent_order_id is None
            and order.signal_plan_id is not None
            and order.filled_quantity > 0
            and order.status in {InternalOrderStatus.FILLED, InternalOrderStatus.PARTIALLY_FILLED}
        )

    @staticmethod
    def _position_for_symbol(
        positions: tuple[BrokerPositionSnapshot, ...],
        symbol: str,
    ) -> BrokerPositionSnapshot | None:
        symbol_upper = symbol.upper()
        return next((position for position in positions if position.symbol.upper() == symbol_upper), None)

    @staticmethod
    def _broker_position_is_active(position: BrokerPositionSnapshot) -> bool:
        return position.qty != 0 and (position.status or "").lower() not in {"closed", "flat"}

    @staticmethod
    def _position_side_matches_parent(position: BrokerPositionSnapshot, parent: InternalOrder) -> bool:
        if position.qty > 0 or position.side == BrokerPositionSide.LONG:
            return parent.side == CandidateSide.LONG
        if position.qty < 0 or position.side == BrokerPositionSide.SHORT:
            return parent.side == CandidateSide.SHORT
        return False

    @staticmethod
    def _broker_error_reason(exc: BrokerAdapterError) -> str:
        details = getattr(exc, "details", None)
        code = getattr(details, "code", None)
        message = getattr(details, "message", None)
        if code:
            if message:
                return f"broker_adapter_error:{code}:{message}"
            return f"broker_adapter_error:{code}"
        return "broker_adapter_error"

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
            # DEGRADED set by a transient freshness gap (post-restart WS
            # reconnect, brief network blip) must auto-clear once sync
            # recovers. DEGRADED set by a broker apply_result exception or
            # any other non-freshness fault stays sticky — those represent
            # broker-side malfunctions that the operator must resolve.
            last_error = (runtime_state.last_error or "")
            freshness_origin = (
                "broker_sync_stale" in last_error
                or "broker_truth_age_exceeded" in last_error
                or "broker_sync_freshness" in last_error
            )
            if freshness_origin:
                recheck = self._freshness(entry.account_id)
                if recheck is not None and not recheck.is_stale:
                    runtime_state = self._save_state(
                        deployment_id, status=RuntimeStatus.RUNNING, last_error=None
                    )
                else:
                    return self._status_from_state(runtime_state)
            else:
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
            # W2-A architecture-critic fix #2: thread the factory itself
            # (not a snapshot pre-resolved at construction time) so each
            # Governor evaluation gets a fresh broker-account snapshot.
            portfolio_snapshot_factory=self._portfolio_snapshot_factory,
            feature_cache=cache,
            control_plane=self._control_plane,
            runtime_store=self._runtime_store,
            live_order_submission_enabled=entry.live_order_submission_enabled,
            daily_state_factory=self._daily_state_for,
            daily_state_aggregator=self._daily_aggregator,
            daily_states=self._daily_states,
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

    # T-7 helpers

    def _boot_load_daily_states(self) -> dict[UUID, DailyAccountState]:
        if self._runtime_store is None or not hasattr(self._runtime_store, "list_daily_account_states"):
            return {}
        states: dict[UUID, DailyAccountState] = {}
        account_ids = set(entry.account_id for entry in self._deployments.values())
        today = _daily_et_market_day(datetime.now(timezone.utc))
        for account_id in account_ids:
            try:
                state = self._runtime_store.load_daily_account_state(account_id, today)
                states[account_id] = state
            except KeyError:
                pass
        return states

    def _daily_state_for(self, account_id: UUID) -> DailyAccountState | None:
        state = self._daily_states.get(account_id)
        if state is None:
            return None
        today = _daily_et_market_day(datetime.now(timezone.utc))
        if state.market_day != today:
            return None
        return state
