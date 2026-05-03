from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import threading
from uuid import UUID, uuid4

from backend.app.brokers import (
    AlpacaBrokerPreflightService,
    BrokerAdapter,
    BrokerAdapterError,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSnapshot,
    BrokerStreamRouter,
    BrokerSync,
    BrokerSyncService,
    FakeBrokerAdapter,
    MarketRulePreflightService,
    build_broker_order_preflight_request,
    build_market_rule_preflight_request,
)
from backend.app.control_plane.service import ControlPlane
from backend.app.composition import StrategyArtifactResolver
from backend.app.decision import SignalPlanBuilder
from backend.app.decision.ports import PositionSignalContext, SignalEvaluationContext, SignalSourcePort
from backend.app.decision.signal_plan_common import parse_post_fill_pct
from backend.app.deployments.models import Deployment
from backend.app.domain._base import utc_now
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    CandidateSide,
    CandidateTradeIntent,
    IntentType,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    LogicalExitRule,
    LogicalExitRuleKind,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
    TradingMode,
)
from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    FeatureFrame,
    FeatureHydrationBarsSource,
    FeatureHydrationResult,
    FeatureHydrationService,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedDeploymentComponents,
    build_feature_plan,
    collect_feature_refs,
)
from backend.app.governor import (
    BrokerSyncFreshness,
    GovernorDecision,
    GovernorPolicyResolver,
    GovernorRequest,
    PortfolioGovernor,
    PortfolioSnapshot,
)
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, TradeLedger
from backend.app.orders.protective_placer import ProtectiveOrderPlacer
from backend.app.risk_resolver import AccountRiskSizingInput, RiskResolver, StaticSizingInput
from backend.app.runtime import DeploymentContext, RuntimeState

from .models import PipelineEvent, PipelineEventType, PipelineResult


class StrategyControlsGate:
    def allows(self, *, components: ResolvedDeploymentComponents, timestamp: datetime) -> bool:
        windows = components.strategy_controls.session_windows
        if not windows:
            return True
        current_time = timestamp.timetz().replace(tzinfo=None)
        return any(window.start <= current_time <= window.end for window in windows)


class RuntimePipelineEventLog:
    def __init__(self, *, deployment_id: UUID) -> None:
        self._deployment_id = deployment_id
        self._events: list[PipelineEvent] = []

    def append(
        self,
        *,
        timestamp: datetime,
        event_type: PipelineEventType,
        message: str,
        symbol: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._events.append(
            PipelineEvent(
                sequence=len(self._events) + 1,
                timestamp=timestamp,
                deployment_id=self._deployment_id,
                event_type=event_type,
                symbol=symbol,
                message=message,
                details=details or {},
            )
        )

    def snapshot(self) -> tuple[PipelineEvent, ...]:
        return tuple(self._events)


class DeploymentPositionManager:
    """Read-only position manager for Deployment-owned SignalPlan emission.

    It reads Account-owned Position truth scoped by Deployment. It never writes
    broker truth, mutates positions, or stores runtime state.
    """

    def __init__(self, *, deployment_id: UUID, position_reader: object | None) -> None:
        self._deployment_id = deployment_id
        self._position_reader = position_reader

    def positions_for_deployment(self) -> tuple[BrokerPositionSnapshot, ...]:
        reader = self._position_reader
        if reader is None:
            return ()
        if hasattr(reader, "list_broker_position_snapshots_by_deployment"):
            return tuple(reader.list_broker_position_snapshots_by_deployment(self._deployment_id))
        return ()

    @staticmethod
    def is_active(position: BrokerPositionSnapshot) -> bool:
        return position.qty != 0 and (position.status or "").lower() not in {"closed", "flat"}

class RuntimeOrchestrator:
    _NATIVE_BRACKET_REFERENCE_MAX_AGE_SECONDS = 5 * 60

    def __init__(
        self,
        *,
        account_id: UUID,
        account_ids: tuple[UUID, ...] | None = None,
        deployment: DeploymentContext,
        components: ResolvedDeploymentComponents,
        initial_cash: float = 100_000,
        feature_engine: IncrementalFeatureEngine | None = None,
        controls_gate: StrategyControlsGate | None = None,
        signal_plan_builder: SignalPlanBuilder | None = None,
        risk_resolver: RiskResolver | None = None,
        governor: PortfolioGovernor | None = None,
        governor_policy_resolver: GovernorPolicyResolver | None = None,
        order_manager: OrderManager | None = None,
        broker_adapter: BrokerAdapter | None = None,
        broker_sync: BrokerSync | None = None,
        broker_sync_service: BrokerSyncService | None = None,
        trade_ledger: TradeLedger | None = None,
        stream_adapter: object | None = None,
        broker_freshness: BrokerSyncFreshness | None = None,
        broker_freshness_by_account: Mapping[UUID, BrokerSyncFreshness] | None = None,
        portfolio_snapshot: PortfolioSnapshot | None = None,
        portfolio_snapshot_by_account: Mapping[UUID, PortfolioSnapshot] | None = None,
        portfolio_snapshot_factory: "Callable[[UUID], PortfolioSnapshot] | None" = None,
        feature_cache: FeatureCache | None = None,
        control_plane: ControlPlane | None = None,
        runtime_store: object | None = None,
        position_reader: object | None = None,
        broker_preflight_service: AlpacaBrokerPreflightService | None = None,
        market_rule_preflight_service: MarketRulePreflightService | None = None,
        live_order_submission_enabled: bool = False,
        protective_order_placer: ProtectiveOrderPlacer | None = None,
        daily_state_factory: "Callable[[UUID], object | None] | None" = None,
        daily_state_aggregator: object | None = None,
        daily_states: "dict[UUID, object] | None" = None,
        strategy_artifact_resolver: StrategyArtifactResolver | None = None,
    ) -> None:
        self._account_id = account_id
        self._account_ids = tuple(dict.fromkeys(account_ids or (account_id,)))
        self._deployment = deployment
        self._components = components
        # M7 null-guard (P1-6): a Deployment whose components.strategy is None
        # AND has no v4 strategy is misconfigured. Fail at construction time so
        # the error is discovered before market hours, not on the first bar.
        if components.strategy is None and components.strategy_version_v4 is None:
            raise RuntimeError(
                f"deployment_strategy_unset:{deployment.deployment_id}"
            )
        if (
            components.strategy_version_v4 is not None
            and strategy_artifact_resolver is None
        ):
            raise ValueError("v4 components require a strategy_artifact_resolver")
        self._initial_cash = initial_cash
        self._feature_engine = feature_engine or IncrementalFeatureEngine()
        self._controls_gate = controls_gate or StrategyControlsGate()
        self._signal_plan_builder = signal_plan_builder or SignalPlanBuilder()
        self._risk_resolver = risk_resolver or RiskResolver()
        self._governor = governor or PortfolioGovernor()
        self._governor_policy_resolver = governor_policy_resolver
        # Deployment is the sole source of risk_horizon (Slice 8.7 doctrine).
        # StrategyControls no longer carries a trading_horizon field.
        # When risk_horizon is None the orchestrator does not synthesize a
        # horizon — the per-horizon plan-mapping rule is simply not enforced.
        deployment_horizon = getattr(deployment, "risk_horizon", None)
        self._deployment_risk_horizon = deployment_horizon
        # Only when the Deployment has an explicit risk_horizon do we pass
        # enforce_plan_required=True to the resolver, activating the
        # "Account must have a plan for this horizon" doctrine.
        self._deployment_has_explicit_risk_horizon = deployment_horizon is not None
        self._broker_adapter = broker_adapter or FakeBrokerAdapter()
        self._order_manager = order_manager or OrderManager(broker_adapter=self._broker_adapter)
        self._broker_sync = broker_sync or BrokerSync(ledger=self._order_manager.ledger)
        self._trade_ledger = trade_ledger or TradeLedger()
        self._daily_states: dict[UUID, object] = daily_states if daily_states is not None else {}
        self._broker_sync_service = broker_sync_service or BrokerSyncService(
            adapter=self._broker_adapter,
            broker_sync=self._broker_sync,
            order_ledger=self._order_manager.ledger,
            trade_ledger=self._trade_ledger,
            runtime_store=runtime_store,
            daily_state_aggregator=daily_state_aggregator,
            daily_states=self._daily_states,
        )
        if hasattr(self._order_manager, "attach_broker_sync_service"):
            self._order_manager.attach_broker_sync_service(self._broker_sync_service)
        if hasattr(self._order_manager, "attach_broker_adapter"):
            self._order_manager.attach_broker_adapter(self._broker_adapter)
        if hasattr(self._order_manager, "attach_broker_sync"):
            self._order_manager.attach_broker_sync(self._broker_sync)
        # Seed the service with a successful poll on construction so the
        # OrderManager stale-sync gate doesn't block before the first
        # process_bar round-trip. Onboarding has already verified the
        # adapter is connected by the time the orchestrator is built.
        for synced_account_id in self._account_ids:
            self._broker_sync_service.record_successful_poll(synced_account_id)
        self._stream_router = BrokerStreamRouter(self._broker_sync_service)
        if stream_adapter is not None and hasattr(stream_adapter, "subscribe"):
            stream_adapter.subscribe(self._stream_router.route)
        self._broker_freshness = broker_freshness or BrokerSyncFreshness()
        self._broker_freshness_by_account = dict(broker_freshness_by_account or {})
        self._portfolio_snapshot = portfolio_snapshot or PortfolioSnapshot()
        self._portfolio_snapshot_by_account = dict(portfolio_snapshot_by_account or {})
        # W2-A architecture-critic fix #2: a per-call factory closes the
        # TOCTOU window where a cached snapshot ages relative to the live
        # broker-account equity. When supplied, the factory wins over
        # ``portfolio_snapshot_by_account`` (the dict still seeds the
        # initial map for back-compat with tests that supply only static
        # values). Production wires this from
        # ``backend/app/runtime/account_trading_entrypoint.build_portfolio_snapshot_factory``.
        self._portfolio_snapshot_factory: Callable[[UUID], PortfolioSnapshot] | None = portfolio_snapshot_factory
        self._feature_cache = feature_cache or FeatureCache()
        self._control_plane = control_plane or ControlPlane()
        self._runtime_store = runtime_store
        self._position_reader = position_reader or runtime_store
        self._position_manager = DeploymentPositionManager(
            deployment_id=deployment.deployment_id,
            position_reader=self._position_reader,
        )
        self._live_order_submission_enabled = live_order_submission_enabled
        self._broker_preflight_service = broker_preflight_service or (
            AlpacaBrokerPreflightService() if getattr(self._broker_adapter, "provider", None) == "alpaca" else None
        )
        self._market_rule_preflight_service = market_rule_preflight_service or (
            MarketRulePreflightService() if getattr(self._broker_adapter, "provider", None) == "alpaca" else None
        )
        self._feature_plan = build_feature_plan(components, consumer="runtime")
        # Slice 11 final-mile: build a map dotted_expression_key → runtime_key
        # so the v4 expression engine (which looks up features by their dotted
        # form, e.g. "1m.close", "1m.rsi(2)") can find values in the runtime
        # FeatureSnapshot (keyed by the long form make_feature_key produces).
        # Without this bridge every v4 expression lookup raises EvalError →
        # the legacy v4 builder returned None -> silent no-signal forever.
        self._v4_dotted_to_runtime_key: dict[str, str] = {}
        if components.strategy_version_v4 is not None:
            from backend.app.features.parser import parse_feature_expression
            from backend.app.features.key import make_feature_key
            from backend.app.features import registry as _feature_registry
            for dotted in collect_feature_refs(components):
                try:
                    spec = parse_feature_expression(
                        dotted,
                        _feature_registry,
                        default_timeframe=components.strategy_controls.timeframe,
                    )
                    self._v4_dotted_to_runtime_key[dotted] = make_feature_key(spec)
                except Exception:  # noqa: BLE001
                    # Strategy validator already screened these at save time;
                    # if anything still fails to parse, skip silently — the v4
                    # builder will return None on EvalError downstream.
                    continue
        self._runtime_state = self._load_runtime_state() or RuntimeState(deployment_id=deployment.deployment_id)
        self._persist_runtime_state()
        self._event_log = RuntimePipelineEventLog(deployment_id=deployment.deployment_id)
        self._entry_symbols = frozenset(symbol.symbol.upper() for symbol in components.universe.symbols)
        self._protective_order_placer = protective_order_placer or ProtectiveOrderPlacer()
        self._daily_state_factory = daily_state_factory
        # Wiggum P0-6: serialize post-fill protective placement per parent order.
        # Broker stream updates can arrive concurrently (partial fills on
        # different threads). Without a per-parent critical section, two
        # handlers can both read the same already_covered_qty and place
        # overlapping protective slices. A per-parent lock keeps the
        # read->compute->create->submit sequence atomic for one parent.
        self._post_fill_parent_locks: dict[UUID, threading.Lock] = {}
        self._post_fill_parent_locks_guard = threading.Lock()
        self._strategy_artifact_resolver = strategy_artifact_resolver

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def broker_sync_service(self) -> BrokerSyncService:
        return self._broker_sync_service

    @property
    def trade_ledger(self) -> TradeLedger:
        return self._trade_ledger

    @property
    def stream_router(self) -> BrokerStreamRouter:
        return self._stream_router

    @property
    def feature_cache(self) -> FeatureCache:
        return self._feature_cache

    @property
    def feature_plan(self) -> FeaturePlan:
        return self._feature_plan

    def hydrate_features(
        self,
        *,
        symbols: tuple[str, ...],
        as_of: datetime,
        bars_source: FeatureHydrationBarsSource,
        hydration_service: FeatureHydrationService | None = None,
    ) -> FeatureHydrationResult:
        normalized_symbols = tuple(sorted({symbol.upper() for symbol in (*self._feature_plan.symbols, *symbols)}))
        if normalized_symbols != self._feature_plan.symbols:
            self._feature_plan = self._feature_plan.model_copy(update={"symbols": normalized_symbols})
        return (hydration_service or FeatureHydrationService()).hydrate(
            plan=self._feature_plan,
            symbols=normalized_symbols,
            as_of=as_of,
            bars_source=bars_source,
            feature_engine=self._feature_engine,
            feature_cache=self._feature_cache,
        )

    def process_bar(self, bar: NormalizedBar) -> PipelineResult:
        self._reset_positions_cache()
        self._reset_v4_signal_source_cache()
        normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
        self._ensure_feature_plan_accepts_position_symbol(normalized_bar.symbol)
        feature_update = self._feature_engine.update(
            plan=self._feature_plan,
            bar=normalized_bar,
            cache=self._feature_cache,
        )
        self._event_log.append(
            timestamp=normalized_bar.timestamp,
            event_type=PipelineEventType.FEATURE_UPDATED,
            symbol=normalized_bar.symbol,
            message="incremental feature state updated",
            details={"feature_count": len(feature_update.snapshot.values)},
        )
        if normalized_bar.timeframe != self._components.strategy_controls.timeframe:
            return self._result()
        if not self._controls_gate.allows(components=self._components, timestamp=normalized_bar.timestamp):
            self._event_log.append(
                timestamp=normalized_bar.timestamp,
                event_type=PipelineEventType.SIGNAL_BLOCKED,
                symbol=normalized_bar.symbol,
                message="strategy controls blocked pipeline signal evaluation",
            )
            return self._result()
        runtime_snapshot = self._aligned_snapshot(
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            timestamp=normalized_bar.timestamp,
        )

        candidate_intents: list[CandidateTradeIntent] = []
        signal_plans: list[SignalPlan] = []
        account_evaluations: list[AccountSignalPlanEvaluation] = []
        governor_decisions: list[GovernorDecision] = []
        orders: list[InternalOrder] = []
        broker_results: list[BrokerOrderResult] = []
        ledger_updates: list[InternalOrder] = []

        if self._components.strategy_version_v4 is not None:
            # V4 path: evaluate entry expressions directly → SignalPlans.
            v4_plans, v4_candidates = self._evaluate_v4_entry_plans(
                normalized_bar=normalized_bar,
                runtime_snapshot=runtime_snapshot,
            )
            for v4_candidate in v4_candidates:
                candidate_intents.append(v4_candidate)
                self._event_log.append(
                    timestamp=v4_candidate.timestamp,
                    event_type=PipelineEventType.CANDIDATE_TRADE_INTENT,
                    symbol=v4_candidate.symbol,
                    message="v4 candidate trade intent emitted",
                    details={"signal_name": v4_candidate.signal_name},
                )
            for v4_plan in v4_plans:
                # Apply execution-style entry preferences (order_type, TIF).
                if v4_plan.entry is not None:
                    v4_plan = v4_plan.model_copy(
                        update={
                            "entry": v4_plan.entry.model_copy(
                                update={
                                    "order_type": self._components.execution_style.entry_order_type,
                                    "time_in_force_preference": self._components.execution_style.time_in_force,
                                }
                            )
                        }
                    )
                signal_plans.append(v4_plan)
                self._process_entry_signal_plan_for_accounts(
                    signal_plan=v4_plan,
                    normalized_bar=normalized_bar,
                    stop_candidate=None,
                    account_evaluations=account_evaluations,
                    governor_decisions=governor_decisions,
                    orders=orders,
                    broker_results=broker_results,
                    ledger_updates=ledger_updates,
                )
            # V4 logical exits use the same position-management spine once
            # translated from v4 templates to typed logical-exit rules.
            logical_exit_intents = self._evaluate_v4_logical_exit_intents(
                normalized_bar=normalized_bar,
                runtime_snapshot=runtime_snapshot,
            )
            for candidate in logical_exit_intents:
                candidate_intents.append(candidate)
                self._event_log.append(
                    timestamp=candidate.timestamp,
                    event_type=PipelineEventType.CANDIDATE_TRADE_INTENT,
                    symbol=candidate.symbol,
                    message="v4 logical-exit candidate trade intent emitted",
                    details={"signal_name": candidate.signal_name},
                )
            self._process_position_management_candidates(
                candidate_intents=logical_exit_intents,
                normalized_bar=normalized_bar,
                signal_plans=signal_plans,
                account_evaluations=account_evaluations,
                governor_decisions=governor_decisions,
                orders=orders,
                broker_results=broker_results,
                ledger_updates=ledger_updates,
            )
        return self._result(
            candidate_intents=candidate_intents,
            signal_plans=signal_plans,
            account_evaluations=account_evaluations,
            governor_decisions=governor_decisions,
            orders=orders,
            broker_results=broker_results,
            ledger_updates=ledger_updates,
        )

    def _process_entry_signal_plan_for_accounts(
        self,
        *,
        signal_plan: SignalPlan,
        normalized_bar: "NormalizedBar",
        stop_candidate: "float | None",
        account_evaluations: "list[AccountSignalPlanEvaluation]",
        governor_decisions: "list[GovernorDecision]",
        orders: "list[InternalOrder]",
        broker_results: "list[BrokerOrderResult]",
        ledger_updates: "list[InternalOrder]",
    ) -> None:
        """Run the per-account risk + governor + order fanout for one entry SignalPlan.

        Extracted so both the v4 direct-plan path and the legacy candidate
        path share the same account fanout logic.  The legacy path passes
        ``stop_candidate`` from ``CandidateTradeIntent``; the v4 path passes
        ``None`` (stop is already encoded in ``signal_plan.stop.rule``).
        """
        for account_id in self._account_ids:
            lifecycle_sizing = self._risk_resolver.lifecycle_sizing_from_risk_profile(
                AccountRiskSizingInput(
                    risk_profile=self._components.risk_profile,
                    price=normalized_bar.close,
                    initial_cash=self._initial_cash,
                    stop_candidate=stop_candidate,
                )
            )
            risk_result = self._risk_resolver.resolve_lifecycle(
                account_id=account_id,
                signal_plan=signal_plan,
                sizing=lifecycle_sizing,
            )
            # W2-A-1a: pass concrete candidate inputs so the Governor can
            # evaluate exposure / open-risk percentage gates against real
            # numbers. RiskResolver has already produced resolved_quantity
            # and stop_distance (when stop is concrete); the entry's
            # reference price is the signal-plan limit when present, else
            # the latest bar's close (same fallback the native bracket
            # placer uses). When stop is post_fill_pct, the helper proxies.
            entry_reference_price = (
                signal_plan.entry.limit_price
                if signal_plan.entry is not None and signal_plan.entry.limit_price is not None
                else normalized_bar.close
            )
            decision = self._evaluate_governor_for_signal_plan(
                account_id=account_id,
                signal_plan=signal_plan,
                order_intent=InternalOrderIntent.OPEN,
                candidate_quantity=risk_result.resolved_quantity,
                reference_price=entry_reference_price,
                risk_result_stop_distance=risk_result.stop_distance,
                timestamp=normalized_bar.timestamp,
            )
            governor_decisions.append(decision)
            self._emit_governor_decision(timestamp=signal_plan.created_at, symbol=signal_plan.symbol, decision=decision)
            governor_trace = self._governor_trace_from_decision(account_id=account_id, signal_plan=signal_plan, decision=decision)
            account_evaluation = AccountSignalPlanEvaluation(
                evaluation_id=uuid4(),
                account_id=account_id,
                signal_plan_id=signal_plan.signal_plan_id,
                deployment_id=signal_plan.deployment_id,
                strategy_id=signal_plan.strategy_id,
                status=AccountEvaluationStatus.ACCEPTED if risk_result.allowed and decision.approved else AccountEvaluationStatus.BLOCKED,
                participation_decision=AccountParticipationDecision.PARTICIPATE if risk_result.allowed and decision.approved else AccountParticipationDecision.REJECT,
                risk_resolver_result=risk_result,
                governor_decision=governor_trace,
                evaluated_at=normalized_bar.timestamp,
                rejection_reasons=() if risk_result.allowed and decision.approved else tuple(risk_result.violations) + (self._account_rejection_reason(account_id, decision),),
            )
            self._record_account_evaluation(account_evaluations, account_evaluation)
            if not risk_result.allowed:
                continue
            if not decision.approved:
                continue
            control_decision = self._control_plane.can_open_new_position(
                account_id=account_id,
                deployment_id=signal_plan.deployment_id,
                symbol=signal_plan.symbol,
                side=signal_plan.side.value,
            )
            if not control_decision.allowed:
                self._event_log.append(
                    timestamp=signal_plan.created_at,
                    event_type=PipelineEventType.GOVERNOR_DECISION,
                    symbol=signal_plan.symbol,
                    message="control plane blocked opening order",
                    details={
                        "account_id": str(account_id),
                        "approved": False,
                        "reason": control_decision.reason,
                        "rule_id": control_decision.rule_id,
                    },
                )
                continue
            order = self._order_manager.create_signal_plan_order(
                account_id=account_id,
                signal_plan=signal_plan,
                account_evaluation=account_evaluation,
                risk_result=risk_result,
                governor_decision=governor_trace,
            )
            orders.append(order)
            if order.status != InternalOrderStatus.CREATED:
                continue
            order = self._maybe_attach_native_bracket_to_entry(
                order=order,
                signal_plan=signal_plan,
                normalized_bar=normalized_bar,
            )
            result, ledger_update = self._submit_sync_order(order, signal_plan=signal_plan)
            broker_results.append(result)
            ledger_updates.append(ledger_update)

    def _ensure_feature_plan_accepts_position_symbol(self, symbol: str) -> None:
        if symbol in self._feature_plan.symbols:
            return
        if not any(position.symbol.upper() == symbol for position in self._positions_for_deployment()):
            return
        self._feature_plan = self._feature_plan.model_copy(
            update={"symbols": tuple(sorted({*self._feature_plan.symbols, symbol}))}
        )

    def _process_position_management_candidates(
        self,
        *,
        candidate_intents: tuple[CandidateTradeIntent, ...],
        normalized_bar: NormalizedBar,
        signal_plans: list[SignalPlan],
        account_evaluations: list[AccountSignalPlanEvaluation],
        governor_decisions: list[GovernorDecision],
        orders: list[InternalOrder],
        broker_results: list[BrokerOrderResult],
        ledger_updates: list[InternalOrder],
    ) -> None:
        exit_candidates = tuple(candidate for candidate in candidate_intents if candidate.intent_type == IntentType.EXIT)
        if not exit_candidates:
            return

        deployment_positions = tuple(
            position
            for position in self._positions_for_deployment()
            if position.symbol.upper() == normalized_bar.symbol
        )
        active_positions = tuple(position for position in deployment_positions if self._position_is_active(position))
        if not active_positions:
            return

        active_positions_by_account: dict[UUID, list[BrokerPositionSnapshot]] = {}
        inactive_positions_by_account: dict[UUID, BrokerPositionSnapshot] = {}
        for position in deployment_positions:
            if self._position_is_active(position):
                active_positions_by_account.setdefault(position.account_id, []).append(position)
            else:
                inactive_positions_by_account.setdefault(position.account_id, position)
        active_lineage_ids = {
            position.position_lineage_id
            for position in active_positions
            if position.position_lineage_id is not None
        }
        related_position_lineage_id = next(iter(active_lineage_ids)) if len(active_lineage_ids) == 1 else None
        opening_signal_plan_id = next(
            (position.opening_signal_plan_id for position in active_positions if position.opening_signal_plan_id is not None),
            None,
        )

        for candidate in exit_candidates:
            strategy_id, strategy_version_id = self._active_strategy_ids()
            signal_plan = self._signal_plan_builder.build_from_candidate(
                candidate=candidate,
                deployment_id=self._deployment.deployment_id,
                strategy_id=strategy_id,
                strategy_version_id=strategy_version_id,
                opening_signal_plan_id=opening_signal_plan_id,
                related_position_lineage_id=related_position_lineage_id,
                logical_exit_rule=self._logical_exit_rule_from_candidate(candidate),
            )
            signal_plans.append(signal_plan)
            for account_id in self._account_ids:
                account_active_positions = tuple(active_positions_by_account.get(account_id, ()))
                if len(account_active_positions) > 1:
                    self._record_account_evaluation(
                        account_evaluations,
                        self._blocked_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="multiple_active_position_lineages_for_account",
                        ),
                    )
                    continue
                position = account_active_positions[0] if account_active_positions else inactive_positions_by_account.get(account_id)
                if position is None:
                    self._record_account_evaluation(
                        account_evaluations,
                        self._ignored_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="account_has_no_matching_position",
                        ),
                    )
                    continue
                if not self._position_is_active(position):
                    self._record_account_evaluation(
                        account_evaluations,
                        self._ignored_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="position_already_closed",
                        ),
                    )
                    continue
                if position.position_lineage_id is None:
                    self._record_account_evaluation(
                        account_evaluations,
                        self._blocked_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="position_missing_lineage",
                        ),
                    )
                    continue

                risk_result = self._risk_resolver.resolve_static(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    sizing=StaticSizingInput(quantity=abs(position.qty)),
                    existing_position_context=self._position_context(position),
                )
                order_intent = self._order_intent_for_signal_plan(signal_plan)
                decision = self._evaluate_governor_for_signal_plan(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    position_lineage_id=position.position_lineage_id,
                    order_intent=order_intent,
                )
                governor_decisions.append(decision)
                self._emit_governor_decision(timestamp=normalized_bar.timestamp, symbol=signal_plan.symbol, decision=decision)
                governor_trace = self._governor_trace_from_decision(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    decision=decision,
                )
                accepted = risk_result.allowed and decision.approved
                account_evaluation = AccountSignalPlanEvaluation(
                    evaluation_id=uuid4(),
                    account_id=account_id,
                    signal_plan_id=signal_plan.signal_plan_id,
                    deployment_id=signal_plan.deployment_id,
                    strategy_id=signal_plan.strategy_id,
                    status=AccountEvaluationStatus.ACCEPTED if accepted else AccountEvaluationStatus.BLOCKED,
                    participation_decision=AccountParticipationDecision.PARTICIPATE if accepted else AccountParticipationDecision.REJECT,
                    risk_resolver_result=risk_result,
                    governor_decision=governor_trace,
                    evaluated_at=normalized_bar.timestamp,
                    rejection_reasons=() if accepted else tuple(risk_result.violations) + (self._account_rejection_reason(account_id, decision),),
                )
                self._record_account_evaluation(account_evaluations, account_evaluation)
                if not accepted:
                    continue

                order = self._order_manager.create_signal_plan_order(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    account_evaluation=account_evaluation,
                    risk_result=risk_result,
                    governor_decision=governor_trace,
                    order_intent=order_intent,
                    position_lineage_id=position.position_lineage_id,
                    position_side=SignalPlanSide(position.side.value),
                    opening_signal_plan_id=position.opening_signal_plan_id,
                )
                orders.append(order)
                if order.status != InternalOrderStatus.CREATED:
                    continue
                ledger_updates.extend(
                    self._cancel_superseded_position_management_orders(
                        account_id=account_id,
                        position_lineage_id=position.position_lineage_id,
                        incoming_intent=order_intent,
                        incoming_order_id=order.order_id,
                        timestamp=normalized_bar.timestamp,
                        symbol=signal_plan.symbol,
                    )
                )
                result, ledger_update = self._submit_sync_order(order, signal_plan=signal_plan)
                broker_results.append(result)
                ledger_updates.append(ledger_update)

    def _positions_for_deployment(self) -> tuple[BrokerPositionSnapshot, ...]:
        cached = getattr(self, "_positions_cache_for_bar", None)
        if cached is not None:
            return cached
        result = self._position_manager.positions_for_deployment()
        self._positions_cache_for_bar = result
        return result

    def _reset_positions_cache(self) -> None:
        if hasattr(self, "_positions_cache_for_bar"):
            self._positions_cache_for_bar = None

    def _reset_v4_signal_source_cache(self) -> None:
        if hasattr(self, "_v4_signal_source_for_bar"):
            self._v4_signal_source_for_bar = None

    def _resolve_v4_signal_source_for_bar(self, sv4: object) -> SignalSourcePort:
        cached = getattr(self, "_v4_signal_source_for_bar", None)
        if cached is not None:
            return cached
        assert self._strategy_artifact_resolver is not None
        signal_source, _metadata = self._strategy_artifact_resolver.resolve(
            Deployment(
                deployment_id=self._deployment.deployment_id,
                name=str(self._deployment.deployment_id),
                strategy_version_v4_id=getattr(sv4, "id"),
                risk_horizon=self._deployment_risk_horizon,
            )
        )
        self._v4_signal_source_for_bar = signal_source
        return signal_source

    def _cancel_superseded_position_management_orders(
        self,
        *,
        account_id: UUID,
        position_lineage_id: UUID,
        incoming_intent: InternalOrderIntent,
        incoming_order_id: UUID,
        timestamp: datetime,
        symbol: str,
    ) -> tuple[InternalOrder, ...]:
        if incoming_intent not in {InternalOrderIntent.CLOSE, InternalOrderIntent.LOGICAL_EXIT}:
            return ()
        canceled = self._order_manager.request_superseded_position_management_cancels(
            account_id=account_id,
            position_lineage_id=position_lineage_id,
            incoming_intent=incoming_intent,
            exclude_order_id=incoming_order_id,
        )
        for update in canceled:
            self._event_log.append(
                timestamp=update.updated_at or timestamp,
                event_type=PipelineEventType.LEDGER_UPDATE,
                symbol=symbol,
                message="superseded position-management order canceled before exit",
                details={
                    "order_id": str(update.order_id),
                    "client_order_id": update.client_order_id,
                    "incoming_intent": incoming_intent.value,
                    "superseded_intent": update.intent.value,
                },
            )
        return canceled

    def _position_is_active(self, position: BrokerPositionSnapshot) -> bool:
        return self._position_manager.is_active(position)

    @staticmethod
    def _position_context(position: BrokerPositionSnapshot) -> dict[str, object]:
        return {
            "account_id": str(position.account_id),
            "deployment_id": str(position.deployment_id) if position.deployment_id is not None else None,
            "strategy_id": str(position.strategy_id) if position.strategy_id is not None else None,
            "opening_signal_plan_id": str(position.opening_signal_plan_id) if position.opening_signal_plan_id is not None else None,
            "position_lineage_id": str(position.position_lineage_id) if position.position_lineage_id is not None else None,
            "symbol": position.symbol.upper(),
            "side": position.side.value,
            "current_quantity": position.qty,
            "status": position.status,
        }

    def _ignored_position_management_evaluation(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        timestamp: datetime,
        reason: str,
    ) -> AccountSignalPlanEvaluation:
        return AccountSignalPlanEvaluation(
            evaluation_id=uuid4(),
            account_id=account_id,
            signal_plan_id=signal_plan.signal_plan_id,
            deployment_id=signal_plan.deployment_id,
            strategy_id=signal_plan.strategy_id,
            status=AccountEvaluationStatus.REJECTED,
            participation_decision=AccountParticipationDecision.IGNORE,
            evaluated_at=timestamp,
            rejection_reasons=(reason,),
        )

    def _blocked_position_management_evaluation(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        timestamp: datetime,
        reason: str,
    ) -> AccountSignalPlanEvaluation:
        return AccountSignalPlanEvaluation(
            evaluation_id=uuid4(),
            account_id=account_id,
            signal_plan_id=signal_plan.signal_plan_id,
            deployment_id=signal_plan.deployment_id,
            strategy_id=signal_plan.strategy_id,
            status=AccountEvaluationStatus.BLOCKED,
            participation_decision=AccountParticipationDecision.REJECT,
            evaluated_at=timestamp,
            rejection_reasons=(reason,),
        )

    def _record_account_evaluation(
        self,
        bucket: list[AccountSignalPlanEvaluation],
        evaluation: AccountSignalPlanEvaluation,
    ) -> AccountSignalPlanEvaluation:
        """Append an evaluation to the in-memory bucket AND persist it.

        W2-A-2 (audit P0 #2 — pre-T-7 bundle): every evaluation outcome
        — PARTICIPATE / REJECT / IGNORE / DEFER — must reach the persisted
        store so Operations can render the full decision picture, not just
        the order-creating decisions. Non-order outcomes were the headline
        gap pre-W2-A.

        The store-side write is best-effort under a guarded ``hasattr`` so
        in-process / in-memory test runtimes (no SQLite store) keep working.

        W2-A adversarial-critic fix #3: persistence failures emit an
        ``EVALUATION_PERSIST_FAILED`` pipeline event and continue. They do
        NOT re-raise. Pre-fix, an IntegrityError on account #3 of a 10-
        account fanout would propagate out of ``process_bar`` while
        accounts #1 and #2 already had their evaluations in the in-memory
        bucket AND in the persisted store — the loop never reached #4..#10
        to even build their evaluations, leaving Operations with a partial
        picture that desynced from the (also partial) order ledger. By
        emitting an event and continuing, every account in the fanout gets
        a chance to evaluate; Operations sees the durable persist gap as
        an explicit event, not a silent missing row. The in-memory
        ``PipelineResult`` is still complete (bucket append happens first).
        """

        bucket.append(evaluation)
        if self._runtime_store is None or not hasattr(self._runtime_store, "save_account_signal_plan_evaluation"):
            return evaluation
        try:
            self._runtime_store.save_account_signal_plan_evaluation(evaluation)
        except Exception as exc:  # noqa: BLE001 — see docstring; structured event over re-raise
            self._event_log.append(
                timestamp=evaluation.evaluated_at or evaluation.created_at,
                event_type=PipelineEventType.EVALUATION_PERSIST_FAILED,
                symbol=None,
                message="account evaluation persisted failed; in-memory result preserved",
                details={
                    "evaluation_id": str(evaluation.evaluation_id),
                    "account_id": str(evaluation.account_id),
                    "signal_plan_id": str(evaluation.signal_plan_id),
                    "deployment_id": str(evaluation.deployment_id),
                    "participation_decision": evaluation.participation_decision.value,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        return evaluation

    def _persist_signal_plans(self, signal_plans: list[SignalPlan]) -> None:
        """Persist emitted Deployment SignalPlans for Operations timelines."""

        if self._runtime_store is None or not hasattr(self._runtime_store, "save_signal_plan"):
            return
        for signal_plan in signal_plans:
            try:
                self._runtime_store.save_signal_plan(signal_plan)
            except Exception as exc:  # noqa: BLE001 - surface the read-model gap without dropping runtime results.
                self._event_log.append(
                    timestamp=signal_plan.created_at,
                    event_type=PipelineEventType.SIGNAL_PLAN_PERSIST_FAILED,
                    symbol=signal_plan.symbol,
                    message="signal plan persist failed; in-memory result preserved",
                    details={
                        "signal_plan_id": str(signal_plan.signal_plan_id),
                        "deployment_id": str(signal_plan.deployment_id),
                        "strategy_id": str(signal_plan.strategy_id),
                        "symbol": signal_plan.symbol,
                        "intent": signal_plan.intent.value,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

    def _load_runtime_state(self) -> RuntimeState | None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_deployment_runtime_state"):
            return None
        try:
            return self._runtime_store.load_deployment_runtime_state(self._deployment.deployment_id)
        except KeyError:
            return None

    def _persist_runtime_state(self) -> None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "save_deployment_runtime_state"):
            return
        self._runtime_store.save_deployment_runtime_state(self._runtime_state)

    def process_protective_signal_plan(
        self,
        *,
        signal_plan: SignalPlan,
        order_intent: InternalOrderIntent,
    ) -> PipelineResult:
        position = self._protective_position_for_signal_plan(signal_plan)
        if position is None or position.position_lineage_id is None or position.opening_signal_plan_id is None:
            self._event_log.append(
                timestamp=signal_plan.created_at,
                event_type=PipelineEventType.SIGNAL_BLOCKED,
                symbol=signal_plan.symbol,
                message="protective position-management order blocked because no active Account-owned Position lineage was found",
                details={
                    "account_id": str(self._account_id),
                    "deployment_id": str(signal_plan.deployment_id),
                    "order_intent": order_intent.value,
                },
            )
            return self._result(signal_plans=[signal_plan])
        signal_plan = signal_plan.model_copy(
            update={
                "opening_signal_plan_id": position.opening_signal_plan_id,
                "related_position_lineage_id": position.position_lineage_id,
            }
        )
        risk_result = self._risk_resolver.resolve_static(
            account_id=self._account_id,
            signal_plan=signal_plan,
            sizing=StaticSizingInput(quantity=abs(position.qty)),
            existing_position_context=self._position_context(position),
        )
        decision = self._evaluate_governor_for_signal_plan(
            account_id=self._account_id,
            signal_plan=signal_plan,
            position_lineage_id=position.position_lineage_id,
            order_intent=order_intent,
        )
        self._emit_governor_decision(timestamp=signal_plan.created_at, symbol=signal_plan.symbol, decision=decision)
        governor_trace = self._governor_trace_from_decision(account_id=self._account_id, signal_plan=signal_plan, decision=decision)
        protective_evaluations: list[AccountSignalPlanEvaluation] = []
        account_evaluation = AccountSignalPlanEvaluation(
            evaluation_id=uuid4(),
            account_id=self._account_id,
            signal_plan_id=signal_plan.signal_plan_id,
            deployment_id=signal_plan.deployment_id,
            strategy_id=signal_plan.strategy_id,
            status=AccountEvaluationStatus.ACCEPTED if risk_result.allowed and decision.approved else AccountEvaluationStatus.BLOCKED,
            participation_decision=AccountParticipationDecision.PARTICIPATE if risk_result.allowed and decision.approved else AccountParticipationDecision.REJECT,
            risk_resolver_result=risk_result,
            governor_decision=governor_trace,
            evaluated_at=signal_plan.created_at,
            rejection_reasons=() if risk_result.allowed and decision.approved else tuple(risk_result.violations) + (decision.reason,),
        )
        # W2-A-2: persist the protective-path evaluation too. This is the
        # single-account direct entry-point used by manual ops + tests.
        self._record_account_evaluation(protective_evaluations, account_evaluation)
        if not risk_result.allowed or not decision.approved:
            return self._result(
                signal_plans=[signal_plan],
                account_evaluations=[account_evaluation],
                governor_decisions=[decision],
            )
        order = self._order_manager.create_signal_plan_order(
            account_id=self._account_id,
            signal_plan=signal_plan,
            account_evaluation=account_evaluation,
            risk_result=risk_result,
            governor_decision=governor_trace,
            order_intent=order_intent,
            position_lineage_id=position.position_lineage_id,
            position_side=SignalPlanSide(position.side.value),
            opening_signal_plan_id=position.opening_signal_plan_id,
        )
        broker_results: list[BrokerOrderResult] = []
        ledger_updates: list[InternalOrder] = []
        if order.status == InternalOrderStatus.CREATED:
            broker_result, ledger_update = self._submit_sync_order(order, signal_plan=signal_plan)
            broker_results.append(broker_result)
            ledger_updates.append(ledger_update)
        return self._result(
            signal_plans=[signal_plan],
            account_evaluations=[account_evaluation],
            governor_decisions=[decision],
            orders=[order],
            broker_results=broker_results,
            ledger_updates=ledger_updates,
        )

    def _submit_sync_order(
        self,
        order: InternalOrder,
        *,
        signal_plan: SignalPlan | None = None,
    ) -> tuple[BrokerOrderResult, InternalOrder]:
        self._event_log.append(
            timestamp=order.created_at,
            event_type=PipelineEventType.ORDER_CREATED,
            symbol=order.symbol,
            message="internal order created",
            details={"order_id": str(order.order_id), "client_order_id": order.client_order_id, "intent": order.intent.value},
        )
        try:
            preflight_result = self._preflight_order_submission(order)
            if preflight_result is not None:
                broker_result = preflight_result
                ledger_update = self._order_manager.update_status(
                    order_id=order.order_id,
                    status=InternalOrderStatus.REJECTED,
                    reason=broker_result.reason,
                )
                self._event_log.append(
                    timestamp=ledger_update.updated_at,
                    event_type=PipelineEventType.LEDGER_UPDATE,
                    symbol=ledger_update.symbol,
                    message="order ledger updated from internal preflight rejection",
                    details={"status": ledger_update.status.value, "reason": ledger_update.reason},
                )
                return broker_result, ledger_update
            else:
                broker_result = self._broker_adapter.submit_order(order)
                self._broker_sync_service.record_successful_poll(order.account_id, at=broker_result.received_at)
        except BrokerAdapterError as exc:
            broker_result = BrokerOrderResult(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status=BrokerOrderStatus.REJECTED,
                filled_quantity=0,
                remaining_quantity=order.quantity,
                reason=self._broker_error_reason(exc),
                raw_status="adapter_error",
            )
        self._event_log.append(
            timestamp=broker_result.received_at,
            event_type=PipelineEventType.BROKER_RESULT,
            symbol=order.symbol,
            message="broker adapter result received",
            details={"status": broker_result.status.value, "filled_quantity": broker_result.filled_quantity},
        )
        ledger_update = self._broker_sync.apply_result(broker_result)
        self._event_log.append(
            timestamp=ledger_update.updated_at,
            event_type=PipelineEventType.LEDGER_UPDATE,
            symbol=ledger_update.symbol,
            message="order ledger updated from broker result",
            details={"status": ledger_update.status.value, "filled_quantity": ledger_update.filled_quantity},
        )
        if signal_plan is not None and self._is_signal_plan_open_entry(ledger_update):
            self._handle_post_fill_protective_placement(
                parent_order=ledger_update,
                signal_plan=signal_plan,
                broker_result=broker_result,
            )
        return broker_result, ledger_update

    def _maybe_attach_native_bracket_to_entry(
        self,
        *,
        order: InternalOrder,
        signal_plan: SignalPlan,
        normalized_bar: NormalizedBar,
    ) -> InternalOrder:
        """Attach native broker bracket params to a SignalPlan-origin OPEN entry.

        T-5 of the Strategy-to-Broker Bracket Execution Program. When the
        deployment's ExecutionPlan declares ``execution_mode=native_alpaca_bracket``
        AND the SignalPlan carries ``post_fill_pct`` stop+target intent
        (T-3), compute concrete child prices from a reference price and
        ask OrderManager to mark the entry as ``order_class="bracket"``.

        Reference price for the bracket child computation:
        - LIMIT entry: ``signal_plan.entry.limit_price``
        - MARKET entry: latest bar close (``normalized_bar.close``)

        On any input that cannot produce both a positive stop and target
        price (missing rule, zero ref price, unsupported side) the method
        leaves the order alone — the post-fill placer remains the safety
        net for those cases. Native bracket is the *optional fast path*,
        not a replacement for post-fill.
        """

        from backend.app.decision.signal_plan_common import parse_post_fill_pct

        execution_mode = getattr(self._components.execution_style, "execution_mode", None)
        if execution_mode is None or getattr(execution_mode, "value", execution_mode) != "native_alpaca_bracket":
            return order
        if order.origin.value != "signal_plan" or order.intent != InternalOrderIntent.OPEN:
            return order
        if signal_plan.stop is None or not signal_plan.targets:
            return order
        stop_pct = parse_post_fill_pct(signal_plan.stop.rule)
        target_pct = parse_post_fill_pct(signal_plan.targets[0].rule)
        if stop_pct is None or target_pct is None:
            return order

        ref_price = self._native_bracket_reference_price(
            signal_plan=signal_plan,
            normalized_bar=normalized_bar,
        )
        if ref_price is None or ref_price <= 0:
            return order
        prices = self._protective_prices_from_reference(
            side=signal_plan.side,
            reference_price=ref_price,
            stop_pct=stop_pct,
            target_pct=target_pct,
        )
        if prices is None:
            return order
        take_profit, stop_loss = prices
        if take_profit <= 0 or stop_loss <= 0:
            return order
        return self._order_manager.attach_native_bracket_to_entry(
            order_id=order.order_id,
            take_profit_limit_price=take_profit,
            stop_loss_stop_price=stop_loss,
        )

    @staticmethod
    def _native_bracket_reference_price(
        *,
        signal_plan: SignalPlan,
        normalized_bar: NormalizedBar,
    ) -> float | None:
        bar_timestamp = getattr(normalized_bar, "timestamp", None)
        if bar_timestamp is None:
            return None
        age_seconds = (utc_now() - bar_timestamp).total_seconds()
        if age_seconds > RuntimeOrchestrator._NATIVE_BRACKET_REFERENCE_MAX_AGE_SECONDS:
            return None
        if signal_plan.entry is not None and signal_plan.entry.limit_price is not None:
            return signal_plan.entry.limit_price
        # Market entry: the latest bar's close is the operator-visible
        # reference. Real fill price lands later via BrokerSync; the
        # bracket child prices set here can drift from the actual fill.
        # That drift is acceptable because the post-fill placer is the
        # default mode — operators only opt into native bracket when
        # they accept this small slippage in exchange for atomic submit.
        return getattr(normalized_bar, "close", None)

    @staticmethod
    def _protective_prices_from_reference(
        *,
        side: SignalPlanSide,
        reference_price: float,
        stop_pct: float,
        target_pct: float,
    ) -> tuple[float, float] | None:
        if side == SignalPlanSide.LONG:
            return (
                reference_price * (1.0 + target_pct / 100.0),
                reference_price * (1.0 - stop_pct / 100.0),
            )
        if side == SignalPlanSide.SHORT:
            return (
                reference_price * (1.0 - target_pct / 100.0),
                reference_price * (1.0 + stop_pct / 100.0),
            )
        return None

    @staticmethod
    def _is_signal_plan_open_entry(order: InternalOrder) -> bool:
        # Protective placement only applies to SignalPlan-origin OPEN entries.
        # Children (STOP_LOSS / TAKE_PROFIT / etc.) are excluded by intent and
        # by parent_order_id presence — they themselves carry parent_order_id
        # and an exit-flavor intent, so this guard prevents recursive
        # protection placement on protective legs.
        from backend.app.orders.models import OrderOrigin

        return (
            order.origin == OrderOrigin.SIGNAL_PLAN
            and order.intent == InternalOrderIntent.OPEN
            and order.parent_order_id is None
        )

    def _handle_post_fill_protective_placement(
        self,
        *,
        parent_order: InternalOrder,
        signal_plan: SignalPlan,
        broker_result: BrokerOrderResult,
    ) -> None:
        """Place post-fill protective stop+target children on a SignalPlan-origin entry fill.

        T-5 of the Strategy-to-Broker Bracket Execution Program.

        - Skipped when the deployment runs in `native_alpaca_bracket` mode
          (the broker auto-attaches protective legs at entry submit time
          via T-4's AlpacaBrokerAdapter native bracket path).
        - Skipped when the broker reports zero filled quantity (rejection
          / no-fill — there is nothing to protect yet).
        - Idempotent on re-emission: ProtectiveOrderPlacer keys placement
          on `cumulative_filled_qty - already_covered_qty`, so partial
          fills extend coverage incrementally.
        - Logs `protection_placed` (with leg count) on success and
          `protection_naked` (with reason) when the SignalPlan declared
          stop/target intent but no legs could be produced — operator
          must see naked positions.
        """

        # Critic Fix #6: skip if the entry already carries a native broker
        # bracket (order_class="bracket"). The broker placed the protective
        # children atomically at submit; running post-fill on top would
        # double-bracket the position. This is more robust than reading
        # self._components.execution_style.execution_mode because the
        # orchestrator caches components at construction; switching the
        # deployment's execution_mode mid-run would leave a stale snapshot
        # behind. The order's own order_class is the ground truth.
        if parent_order.order_class == "bracket":
            return
        # Critic Fix #4: use the ledger's cumulative filled_quantity rather
        # than the broker_result's per-event filled_quantity. Some brokers
        # ship delta fills on the trade-update stream; if we treat that as
        # cumulative, the second partial fill is counted as if it equalled
        # the first, and `new_qty = cumulative - already_covered = 0` —
        # the second slice never gets a stop. The ledger is authoritative
        # because BrokerSync.apply_result accumulates fills onto the
        # InternalOrder before this method runs.
        filled_qty = parent_order.filled_quantity or 0.0
        if filled_qty <= 0:
            return
        fill_price = broker_result.filled_avg_price
        if fill_price is None or fill_price <= 0:
            self._event_log.append(
                timestamp=broker_result.received_at,
                event_type=PipelineEventType.PROTECTION_NAKED,
                symbol=parent_order.symbol,
                message="post-fill protective placement skipped — no fill price reported",
                details={
                    "parent_order_id": str(parent_order.order_id),
                    "rule_id": "protection_failed_after_fill",
                    "reason": "missing_fill_price",
                },
            )
            return

        with self._post_fill_lock_for(parent_order.order_id):
            if self._order_manager.has_operator_canceled_protective_child(
                signal_plan_id=signal_plan.signal_plan_id,
                parent_order_id=parent_order.order_id,
            ):
                self._event_log.append(
                    timestamp=broker_result.received_at,
                    event_type=PipelineEventType.PROTECTION_NAKED,
                    symbol=parent_order.symbol,
                    message="post-fill protective placement skipped — operator canceled protective child",
                    details={
                        "parent_order_id": str(parent_order.order_id),
                        "rule_id": "protection_failed_after_fill",
                        "reason": "operator_canceled_protection",
                    },
                )
                return
            already_covered = self._order_manager.cumulative_covered_qty_for_signal_plan(
                signal_plan_id=signal_plan.signal_plan_id,
                parent_order_id=parent_order.order_id,
            )
            plan = self._protective_order_placer.compute_protective_plan(
                signal_plan=signal_plan,
                parent_order_id=parent_order.order_id,
                account_id=parent_order.account_id,
                fill_price=fill_price,
                cumulative_filled_qty=filled_qty,
                already_covered_qty=already_covered,
            )
            signal_plan_has_intent = signal_plan.stop is not None or bool(signal_plan.targets)
            if not plan.legs:
                if signal_plan_has_intent:
                    self._event_log.append(
                        timestamp=broker_result.received_at,
                        event_type=PipelineEventType.PROTECTION_NAKED,
                        symbol=parent_order.symbol,
                        message="entry filled but ProtectivePlacer produced no legs",
                        details={
                            "parent_order_id": str(parent_order.order_id),
                            "rule_id": "protection_failed_after_fill",
                            "reason": "no_legs_from_intent",
                        },
                    )
                return

            children = (
                self._order_manager.create_protective_oco_order_post_fill(
                    plan=plan,
                    parent_order=parent_order,
                ),
            )
        # Critic Fix #1 + Fix #2: track per-leg success so PROTECTION_PLACED
        # only fires when at least one child reached the broker, and to
        # abort the loop on stop-leg rejection (a target-only "protection"
        # is worse than naked: it consumes margin without downside cover).
            submitted_count = 0
            aborted_due_to_stop_rejection = False
            for child in children:
                if child.status != InternalOrderStatus.CREATED:
                    # Idempotent reuse of an existing child row counts as
                    # already-submitted protection from a prior call; do not
                    # re-submit but do count as covered.
                    submitted_count += 1
                    continue
                is_stop_leg = child.intent == InternalOrderIntent.STOP_LOSS
                child_rejected = False
                child_reject_reason: str | None = None
                try:
                    child_result, child_ledger = self._submit_sync_order(child)
                    # The broker can reject a child without raising — it
                    # returns a BrokerOrderResult(status=REJECTED). The
                    # ledger update reflects the same. Both paths must land
                    # in the "rejected" branch so the operator sees the
                    # PROTECTION_NAKED alarm and we abort on stop-leg loss.
                    if child_result.status == BrokerOrderStatus.REJECTED or (
                        child_ledger.status == InternalOrderStatus.REJECTED
                    ):
                        child_rejected = True
                        child_reject_reason = (
                            child_result.reason
                            or child_ledger.reason
                            or "broker_rejected_protective_child"
                        )
                    else:
                        submitted_count += 1
                except BrokerAdapterError as exc:
                    child_rejected = True
                    child_reject_reason = self._broker_error_reason(exc)
                if child_rejected:
                    self._event_log.append(
                        timestamp=broker_result.received_at,
                        event_type=PipelineEventType.PROTECTION_NAKED,
                        symbol=child.symbol,
                        message="protective child rejected by broker adapter",
                        details={
                            "parent_order_id": str(parent_order.order_id),
                            "child_order_id": str(child.order_id),
                            "rule_id": "protection_failed_after_fill",
                            "reason": child_reject_reason or "rejected",
                        },
                    )
                    if is_stop_leg:
                        aborted_due_to_stop_rejection = True
                        break
            if submitted_count == 0:
                # All children rejected (or none submittable). Surface
                # PROTECTION_NAKED at the parent level too so the operator
                # sees a single, parent-keyed alarm in addition to per-leg
                # rejection events.
                self._event_log.append(
                    timestamp=broker_result.received_at,
                    event_type=PipelineEventType.PROTECTION_NAKED,
                    symbol=parent_order.symbol,
                    message="entry filled but no protective child reached the broker",
                    details={
                        "parent_order_id": str(parent_order.order_id),
                        "rule_id": "protection_failed_after_fill",
                        "reason": "all_children_rejected",
                        "leg_count_attempted": len(children),
                    },
                )
                return
            self._event_log.append(
                timestamp=broker_result.received_at,
                event_type=PipelineEventType.PROTECTION_PLACED,
                symbol=parent_order.symbol,
                message="post-fill protective children placed",
                details={
                    "parent_order_id": str(parent_order.order_id),
                    "leg_count": submitted_count,
                    "covered_qty": plan.covered_qty,
                    "aborted_due_to_stop_rejection": aborted_due_to_stop_rejection,
                },
            )

    def _post_fill_lock_for(self, parent_order_id: UUID) -> threading.Lock:
        with self._post_fill_parent_locks_guard:
            lock = self._post_fill_parent_locks.get(parent_order_id)
            if lock is None:
                lock = threading.Lock()
                self._post_fill_parent_locks[parent_order_id] = lock
            return lock

    def _preflight_order_submission(self, order: InternalOrder) -> BrokerOrderResult | None:
        broker_mode = self._broker_mode_for_order(order)
        if broker_mode == TradingMode.BROKER_LIVE and not self._live_order_submission_enabled:
            return self._preflight_rejection_result(order, reason="live_submission_disabled")
        if self._broker_preflight_service is None:
            return None
        provider = getattr(self._broker_adapter, "provider", "unknown")
        broker_preflight = self._broker_preflight_service.preflight_order(
            build_broker_order_preflight_request(
                order=order,
                provider=provider,
                broker_mode=broker_mode,
            )
        )
        if not broker_preflight.allowed:
            return self._preflight_rejection_result(
                order,
                reason=f"broker_preflight:{broker_preflight.violations[0].code.value}",
            )
        if self._market_rule_preflight_service is None:
            return None
        buying_power = self._buying_power_for_preflight(order.account_id)
        market_preflight = self._market_rule_preflight_service.preflight_market_rules(
            build_market_rule_preflight_request(
                order=order,
                provider=provider,
                broker_mode=broker_mode,
                buying_power=buying_power,
            )
        )
        if not market_preflight.allowed:
            return self._preflight_rejection_result(
                order,
                reason=f"market_preflight:{market_preflight.violations[0].code.value}",
            )
        return None

    def _broker_mode_for_order(self, order: InternalOrder) -> TradingMode:
        mode_for_account = getattr(self._broker_adapter, "mode_for_account", None)
        mode = mode_for_account(order.account_id) if callable(mode_for_account) else getattr(
            self._broker_adapter,
            "mode",
            self._deployment.mode,
        )
        if isinstance(mode, TradingMode):
            return mode
        try:
            return TradingMode(mode)
        except ValueError:
            return TradingMode.BROKER_PAPER

    def _buying_power_for_preflight(self, account_id: UUID) -> float:
        snapshot = self._broker_sync_service.latest_account_snapshot(account_id)
        if snapshot is None:
            return 0
        return snapshot.buying_power

    @staticmethod
    def _preflight_rejection_result(order: InternalOrder, *, reason: str) -> BrokerOrderResult:
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.REJECTED,
            filled_quantity=0,
            remaining_quantity=order.quantity,
            reason=reason,
            raw_status="preflight_rejected",
        )

    def _broker_error_reason(self, exc: BrokerAdapterError) -> str:
        details = getattr(exc, "details", None)
        code = getattr(details, "code", None)
        if code:
            return f"broker_adapter_error:{code}"
        return "broker_adapter_error"

    def _protective_position_for_signal_plan(self, signal_plan: SignalPlan) -> BrokerPositionSnapshot | None:
        for position in self._positions_for_deployment():
            if position.account_id != self._account_id:
                continue
            if position.symbol.upper() != signal_plan.symbol.upper():
                continue
            if self._position_is_active(position):
                return position
        return None

    @staticmethod
    def _signal_plan_intent_for_order_intent(order_intent: InternalOrderIntent) -> SignalPlanIntent:
        if order_intent == InternalOrderIntent.TAKE_PROFIT:
            return SignalPlanIntent.TARGET
        if order_intent == InternalOrderIntent.STOP_LOSS:
            return SignalPlanIntent.STOP
        if order_intent == InternalOrderIntent.SCALE:
            return SignalPlanIntent.REDUCE
        if order_intent in {
            InternalOrderIntent.CLOSE,
            InternalOrderIntent.REDUCE,
            InternalOrderIntent.TARGET,
            InternalOrderIntent.STOP,
            InternalOrderIntent.TRAIL,
            InternalOrderIntent.BREAKEVEN,
            InternalOrderIntent.RUNNER,
            InternalOrderIntent.LOGICAL_EXIT,
        }:
            return SignalPlanIntent(order_intent.value)
        return SignalPlanIntent.CLOSE

    def _governor_candidate_inputs(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        order_intent: InternalOrderIntent,
        candidate_quantity: float | None,
        reference_price: float | None,
        risk_result_stop_distance: float | None,
        timestamp: datetime | None,
    ) -> tuple[float, float]:
        """Resolve candidate_market_value + candidate_open_risk for the gate.

        W2-A-1a (audit P0 #1, operator decision 2026-04-30):

        - Non-OPEN intents (protective exits, position management) contribute
          zero incremental candidate exposure; ``_projected_state`` zeros these
          fields anyway. Returning (0, 0) keeps the request shape honest.
        - OPEN intents must carry non-zero candidate inputs whenever a
          quantity and a reference price are resolvable. Otherwise the
          percentage gates silently evaluate against zero incremental
          exposure, which is the audit's confirmed P0 silent-no-op.
        - When ``risk_result_stop_distance`` is concrete (RiskResolver
          computed it from a real ``candidate.stop_candidate``), use it
          directly. When it is None and the SignalPlan stop is encoded as
          ``post_fill_pct:<pct>`` (the bracket program's default mode), we
          proxy: ``proxy_stop_distance = ref_price * stop_pct/100``. The
          proxy is doctrinally honest — the gate is gating an *open*, not a
          fill, and slippage is intrinsic. A structured audit event records
          the proxy so Operations can see which evaluations ran on a proxy.
        - When neither a concrete stop_distance nor a post_fill_pct is
          available, ``candidate_open_risk`` falls back to zero with a
          structured warning event; ``candidate_market_value`` still carries
          the qty*price exposure so gross/net/concentration limits enforce.
        """

        if order_intent != InternalOrderIntent.OPEN:
            return 0.0, 0.0
        if candidate_quantity is None or candidate_quantity <= 0:
            return 0.0, 0.0
        if reference_price is None or reference_price <= 0:
            return 0.0, 0.0
        candidate_market_value = float(candidate_quantity) * float(reference_price)
        if risk_result_stop_distance is not None and risk_result_stop_distance > 0:
            candidate_open_risk = float(candidate_quantity) * float(risk_result_stop_distance)
            return candidate_market_value, candidate_open_risk
        stop_pct = parse_post_fill_pct(signal_plan.stop.rule) if signal_plan.stop is not None else None
        if stop_pct is not None and stop_pct > 0:
            # W2-A adversarial-critic fix #4: a malformed plan with
            # post_fill_pct > 100 would yield proxy_stop_distance > ref_price
            # (i.e. > 100% notional risk), which inflates candidate_open_risk
            # absurdly and may cause the open_risk_pct cap to spuriously
            # reject. Real loss can never exceed entry notional (loss = entry
            # at stop=0), so cap at 100. parse_post_fill_pct already filters
            # pct<=0; this caps the upper bound.
            stop_pct = min(stop_pct, 100.0)
            proxy_stop_distance = float(reference_price) * (stop_pct / 100.0)
            candidate_open_risk = float(candidate_quantity) * proxy_stop_distance
            event_timestamp = timestamp or signal_plan.created_at
            self._event_log.append(
                timestamp=event_timestamp,
                event_type=PipelineEventType.GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED,
                symbol=signal_plan.symbol,
                message="governor candidate_open_risk proxied from post_fill_pct",
                details={
                    "account_id": str(account_id),
                    "signal_plan_id": str(signal_plan.signal_plan_id),
                    "stop_pct": stop_pct,
                    "reference_price": float(reference_price),
                    "candidate_quantity": float(candidate_quantity),
                    "proxy_stop_distance": proxy_stop_distance,
                    "candidate_open_risk": candidate_open_risk,
                },
            )
            return candidate_market_value, candidate_open_risk
        # No concrete stop, no post_fill_pct intent — open_risk cannot be
        # computed. Market value still enforces gross/net/concentration limits.
        # Emit a structured warning so Operations can see the open_risk gate
        # ran on zero contribution.
        event_timestamp = timestamp or signal_plan.created_at
        self._event_log.append(
            timestamp=event_timestamp,
            event_type=PipelineEventType.GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED,
            symbol=signal_plan.symbol,
            message="governor candidate_open_risk unresolved; market_value populated only",
            details={
                "account_id": str(account_id),
                "signal_plan_id": str(signal_plan.signal_plan_id),
                "reason": "no_concrete_stop_and_no_post_fill_pct",
                "candidate_market_value": candidate_market_value,
                "reference_price": float(reference_price),
                "candidate_quantity": float(candidate_quantity),
            },
        )
        return candidate_market_value, 0.0

    def _evaluate_governor_for_signal_plan(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        position_lineage_id: UUID | None = None,
        order_intent: InternalOrderIntent,
        candidate_quantity: float | None = None,
        reference_price: float | None = None,
        risk_result_stop_distance: float | None = None,
        timestamp: datetime | None = None,
    ) -> GovernorDecision:
        if (
            order_intent == InternalOrderIntent.OPEN
            and self._governor.policy.requires_risk_plan
            and not self._deployment_has_explicit_risk_horizon
        ):
            return GovernorDecision.reject(
                reason="deployment_risk_horizon_missing",
                rule_id="risk_horizon_missing",
            )
        candidate_market_value, candidate_open_risk = self._governor_candidate_inputs(
            account_id=account_id,
            signal_plan=signal_plan,
            order_intent=order_intent,
            candidate_quantity=candidate_quantity,
            reference_price=reference_price,
            risk_result_stop_distance=risk_result_stop_distance,
            timestamp=timestamp,
        )
        daily_state = self._daily_state_factory(account_id) if self._daily_state_factory is not None else None
        request = GovernorRequest(
            account_id=account_id,
            deployment_id=signal_plan.deployment_id,
            symbol=signal_plan.symbol,
            signal_plan_id=signal_plan.signal_plan_id,
            position_lineage_id=position_lineage_id or signal_plan.related_position_lineage_id,
            runtime_state=self._runtime_state,
            broker_sync=self._broker_freshness_for(account_id),
            portfolio=self._portfolio_snapshot_for(account_id),
            order_intent=order_intent,
            candidate_market_value=candidate_market_value,
            candidate_open_risk=candidate_open_risk,
            daily_state=daily_state,
            evaluated_at=timestamp,
        )
        # When a resolver is wired, build a per-(account, horizon) policy from
        # AccountRiskConfig + the Account's RiskPlan-for-this-horizon, then
        # pass it as a one-call override. self._governor.policy is the floor.
        # Without a resolver, fall back to the legacy single-arg call so any
        # PortfolioGovernor subclass that doesn't yet accept policy_override
        # (e.g. test stubs) is not broken by this slice.
        if self._governor_policy_resolver is None:
            return self._governor.evaluate(request)
        policy_override = self._governor_policy_resolver.resolve(
            floor=self._governor.policy,
            account_id=account_id,
            deployment_id=signal_plan.deployment_id,
            risk_horizon=self._deployment_risk_horizon,
            enforce_plan_required=self._deployment_has_explicit_risk_horizon,
        )
        return self._governor.evaluate(request, policy_override=policy_override)

    @staticmethod
    def _order_intent_for_signal_plan(signal_plan: SignalPlan) -> InternalOrderIntent:
        try:
            return InternalOrderIntent(signal_plan.intent.value)
        except ValueError:
            return InternalOrderIntent.LOGICAL_EXIT

    def _broker_freshness_for(self, account_id: UUID) -> BrokerSyncFreshness:
        return self._broker_freshness_by_account.get(account_id, self._broker_freshness)

    def _portfolio_snapshot_for(self, account_id: UUID) -> PortfolioSnapshot:
        # W2-A architecture-critic fix #2: when a factory is wired the
        # snapshot is recomputed PER GOVERNOR EVALUATION, not cached at
        # orchestrator construction. This closes the TOCTOU window where
        # equity changes mid-loop would otherwise be invisible to the
        # gate. Static ``portfolio_snapshot_by_account`` / ``portfolio_snapshot``
        # remain as a back-compat fallback for tests that supply only a
        # static value.
        if self._portfolio_snapshot_factory is not None:
            return self._portfolio_snapshot_factory(account_id)
        return self._portfolio_snapshot_by_account.get(account_id, self._portfolio_snapshot)

    def _account_rejection_reason(self, account_id: UUID, decision: GovernorDecision) -> str:
        if decision.rule_id == "stale_broker_sync_blocks_open":
            freshness = self._broker_freshness_for(account_id)
            return freshness.reason or decision.reason
        return decision.reason

    def _emit_governor_decision(self, *, timestamp: datetime, symbol: str, decision: GovernorDecision) -> None:
        self._event_log.append(
            timestamp=timestamp,
            event_type=PipelineEventType.GOVERNOR_DECISION,
            symbol=symbol,
            message="portfolio governor decision",
            details={"approved": decision.approved, "reason": decision.reason, "rule_id": decision.rule_id},
        )

    def _governor_trace_from_decision(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        decision: GovernorDecision,
    ) -> GovernorDecisionTrace:
        return GovernorDecisionTrace(
            governor_decision_id=uuid4(),
            account_id=account_id,
            signal_plan_id=signal_plan.signal_plan_id,
            status=GovernorDecisionStatus.APPROVED if decision.approved else GovernorDecisionStatus.REJECTED,
            approved=decision.approved,
            reasons=(decision.reason,),
            violations=() if decision.approved else (decision.rule_id,),
            # Slice A finding #8: forward the projected_state so the operator
            # sees the same numeric snapshot the gate used (slots remaining,
            # gross/net exposure pct, symbol concentration pct, broker stale).
            projected_state=decision.projected_state,
        )

    def _position_contexts(self, *, bar: NormalizedBar) -> dict[str, PositionSignalContext]:
        """Build per-symbol PositionSignalContext for logical-exit evaluation.

        Doctrine: ``logical_exit`` is the only exit intent. Time / bar / session
        / hybrid exit rules need this context; pure feature-condition exits only
        need ``has_position`` so the port source knows there is something to exit.
        """
        positions = self._positions_for_deployment()
        contexts: dict[str, PositionSignalContext] = {}
        session_defaults = PositionSignalContext()
        for position in positions:
            if not DeploymentPositionManager.is_active(position):
                continue
            symbol = position.symbol.upper()
            opened_at = self._position_entry_timestamp(position)
            bars_since_entry = (
                self._bars_since_entry_timestamp(opened_at, bar_timestamp=bar.timestamp, timeframe=bar.timeframe)
                if opened_at is not None
                else None
            )
            current = contexts.get(symbol)
            if current is not None and current.current_bar_index is not None and bars_since_entry is not None:
                bars_since_entry = min(current.current_bar_index, bars_since_entry)
            if current is not None and current.current_bar_index is not None and bars_since_entry is None:
                bars_since_entry = current.current_bar_index
            contexts[symbol] = PositionSignalContext(
                has_position=True,
                entry_timestamp=opened_at,
                entry_bar_index=0 if bars_since_entry is not None else None,
                current_bar_index=bars_since_entry,
                bar_timestamp=bar.timestamp,
                session_open_et=session_defaults.session_open_et,
                session_close_et=session_defaults.session_close_et,
            )
        # Always supply a context for the bar's symbol so the source can
        # short-circuit no-position exits cleanly.
        contexts.setdefault(
            bar.symbol.upper(),
            PositionSignalContext(
                bar_timestamp=bar.timestamp,
                session_open_et=session_defaults.session_open_et,
                session_close_et=session_defaults.session_close_et,
            ),
        )
        return contexts

    def _position_entry_timestamp(self, position: BrokerPositionSnapshot) -> datetime | None:
        opened_at = getattr(position, "opened_at", None) or getattr(position, "open_timestamp", None)
        if isinstance(opened_at, datetime):
            return self._aware_timestamp(opened_at)

        account_orders = self._order_manager.ledger.by_account(position.account_id)
        matching_orders = tuple(
            order
            for order in account_orders
            if order.deployment_id == position.deployment_id
            and order.symbol.upper() == position.symbol.upper()
            and order.intent == InternalOrderIntent.OPEN
            and order.filled_quantity > 0
            and self._order_side_matches_position(order, position)
            and (
                (position.opening_signal_plan_id is not None and order.signal_plan_id == position.opening_signal_plan_id)
                or (position.opening_signal_plan_id is not None and order.opening_signal_plan_id == position.opening_signal_plan_id)
                or (position.position_lineage_id is not None and order.position_lineage_id == position.position_lineage_id)
            )
        )
        if matching_orders:
            return self._aware_timestamp(min(matching_orders, key=lambda order: order.created_at).created_at)

        if position.opening_signal_plan_id is not None and self._runtime_store is not None:
            loader = getattr(self._runtime_store, "load_signal_plan", None)
            if callable(loader):
                try:
                    plan = loader(position.opening_signal_plan_id)
                except Exception:
                    plan = None
                if plan is not None and isinstance(getattr(plan, "created_at", None), datetime):
                    return self._aware_timestamp(plan.created_at)
        return None

    @staticmethod
    def _bars_since_entry_timestamp(
        entry_timestamp: datetime,
        *,
        bar_timestamp: datetime,
        timeframe: str,
    ) -> int:
        seconds = RuntimeOrchestrator._timeframe_seconds(timeframe)
        if seconds <= 0:
            return 0
        entry = RuntimeOrchestrator._aware_timestamp(entry_timestamp)
        current = RuntimeOrchestrator._aware_timestamp(bar_timestamp)
        elapsed = max(0.0, (current - entry).total_seconds())
        return int(elapsed // seconds)

    @staticmethod
    def _timeframe_seconds(timeframe: str) -> int:
        normalized = timeframe.strip().lower()
        if len(normalized) < 2 or not normalized[:-1].isdigit():
            return 0
        count = int(normalized[:-1])
        unit = normalized[-1]
        if unit == "m":
            return count * 60
        if unit == "h":
            return count * 60 * 60
        if unit == "d":
            return count * 24 * 60 * 60
        if unit == "w":
            return count * 7 * 24 * 60 * 60
        return 0

    @staticmethod
    def _aware_timestamp(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _order_side_matches_position(order: InternalOrder, position: BrokerPositionSnapshot) -> bool:
        if position.qty > 0:
            return order.side == CandidateSide.LONG
        if position.qty < 0:
            return order.side == CandidateSide.SHORT
        return False

    def _active_strategy_ids(self) -> tuple[UUID, UUID]:
        """Return (strategy_id, strategy_version_id) for the active strategy.

        v4 deployments: (strategy_v4_id, strategy_version_v4.id).
        Legacy deployments: (strategy.strategy_id, strategy.id).
        """
        if self._components.strategy_version_v4 is not None:
            sv4 = self._components.strategy_version_v4
            return sv4.strategy_v4_id, sv4.id
        assert self._components.strategy is not None
        return self._components.strategy.strategy_id, self._components.strategy.id

    @staticmethod
    def _logical_exit_rule_from_candidate(candidate: CandidateTradeIntent) -> LogicalExitRule | None:
        payload = candidate.diagnostics.get("logical_exit_rule_payload")
        if payload is None:
            return None
        if isinstance(payload, Mapping) and "template_id" in payload:
            return RuntimeOrchestrator._logical_exit_rule_from_v4_payload(payload)
        try:
            return LogicalExitRule.model_validate(payload)
        except Exception:
            return None

    @staticmethod
    def _logical_exit_rule_from_v4_payload(payload: Mapping[str, object]) -> LogicalExitRule | None:
        template_id = payload.get("template_id")
        params_raw = payload.get("params", {})
        params = params_raw if isinstance(params_raw, Mapping) else {}
        if template_id == "bars_since":
            bars = RuntimeOrchestrator._positive_int_param(params, "bars")
            if bars is None:
                return None
            return LogicalExitRule(
                kind=LogicalExitRuleKind.BARS_SINCE_ENTRY,
                bars=bars,
                label=f"bars_since:{bars}",
            )
        if template_id == "session_end":
            minutes = RuntimeOrchestrator._positive_int_param(params, "offset_minutes") or 5
            return LogicalExitRule(
                kind=LogicalExitRuleKind.MINUTES_BEFORE_SESSION_CLOSE,
                minutes_before_close=minutes,
                label=f"session_end:{minutes}",
            )
        return None

    def _evaluate_v4_logical_exit_intents(
        self,
        *,
        normalized_bar: NormalizedBar,
        runtime_snapshot: FeatureSnapshot,
    ) -> tuple[CandidateTradeIntent, ...]:
        sv4 = self._components.strategy_version_v4
        if sv4 is None:
            return ()

        active_sides = self._active_position_sides_for_symbol(normalized_bar.symbol)
        if not active_sides:
            return ()

        sides_to_evaluate = tuple(
            side_name
            for side_name in ("long", "short")
            if side_name in active_sides
            and (sv4.logical_exits.long if side_name == "long" else sv4.logical_exits.short)
        )
        if not sides_to_evaluate:
            return ()

        from backend.app.features import FeatureSnapshot as _RtFeatureSnapshot

        translated_values = {}
        for dotted_key, runtime_key in self._v4_dotted_to_runtime_key.items():
            fv = runtime_snapshot.values.get(runtime_key)
            if fv is not None:
                translated_values[dotted_key] = fv
        translated_snapshot = _RtFeatureSnapshot(
            symbol=runtime_snapshot.symbol,
            timeframe=runtime_snapshot.timeframe,
            timestamp=runtime_snapshot.timestamp,
            values=translated_values,
        )

        signal_source = self._resolve_v4_signal_source_for_bar(sv4)
        position_contexts = self._position_contexts(bar=normalized_bar)
        symbol = normalized_bar.symbol.upper()
        position_signal_context = position_contexts.get(
            symbol,
            PositionSignalContext(bar_timestamp=normalized_bar.timestamp),
        )

        intents: list[CandidateTradeIntent] = []
        for side_str in sides_to_evaluate:
            context = SignalEvaluationContext(
                strategy=sv4,
                evaluation_type="logical_exit",
                symbol=symbol,
                side=side_str,  # type: ignore[arg-type]
                timestamp=normalized_bar.timestamp,
                deployment_id=self._deployment.deployment_id,
                watchlist_snapshot_id=self._components.universe.id,
                position_contexts={symbol: position_signal_context},
            )
            result = signal_source.evaluate(translated_snapshot, context)
            intents.extend(result.candidate_intents)
            for template_id, reason in result.diagnostics.items():
                if template_id == "reason":
                    continue
                self._event_log.append(
                    timestamp=normalized_bar.timestamp,
                    event_type=PipelineEventType.SIGNAL_BLOCKED,
                    symbol=normalized_bar.symbol,
                    message="v4 logical exit template is not runtime-supported",
                    details={
                        "template_id": template_id,
                        "reason": reason,
                        "side": side_str,
                    },
                )

        return tuple(intents)

    def _active_position_sides_for_symbol(self, symbol: str) -> set[str]:
        symbol_upper = symbol.upper()
        active_sides: set[str] = set()
        for position in self._positions_for_deployment():
            if not DeploymentPositionManager.is_active(position):
                continue
            if position.symbol.upper() != symbol_upper:
                continue
            if position.qty > 0:
                active_sides.add("long")
            elif position.qty < 0:
                active_sides.add("short")
            else:
                side = getattr(position.side, "value", str(position.side)).lower()
                if side in {"long", "short"}:
                    active_sides.add(side)
        return active_sides

    @staticmethod
    def _positive_int_param(params: Mapping[str, object], key: str) -> int | None:
        raw = params.get(key)
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _evaluate_v4_entry_plans(
        self,
        *,
        normalized_bar: "NormalizedBar",
        runtime_snapshot: "FeatureSnapshot",
    ) -> "tuple[list[SignalPlan], list[CandidateTradeIntent]]":
        """Evaluate v4 entry expressions and return pre-built SignalPlans.

        Evaluates the long and/or short entry expressions for the bound v4
        strategy against the current bar's feature snapshot.  Returns a list
        of ``SignalPlan`` objects (one per side that fired) and a matching
        list of ``CandidateTradeIntent`` objects for pipeline event logging.

        An empty list is the normal result when no expressions fire.
        """
        sv4 = self._components.strategy_version_v4
        assert sv4 is not None

        plans: list[SignalPlan] = []
        candidates: list[CandidateTradeIntent] = []

        # Translate the runtime snapshot's long-form keys to the dotted form
        # the expression engine expects (e.g. "1m.close" instead of the long
        # make_feature_key string). Without this remap every lookup misses
        # silently and no signal is ever emitted. Slice 11 final-mile fix.
        from backend.app.features import FeatureSnapshot as _RtFeatureSnapshot
        translated_values = {}
        for dotted_key, runtime_key in self._v4_dotted_to_runtime_key.items():
            fv = runtime_snapshot.values.get(runtime_key)
            if fv is not None:
                translated_values[dotted_key] = fv
        translated_snapshot = _RtFeatureSnapshot(
            symbol=runtime_snapshot.symbol,
            timeframe=runtime_snapshot.timeframe,
            timestamp=runtime_snapshot.timestamp,
            values=translated_values,
        )
        signal_source = self._resolve_v4_signal_source_for_bar(sv4)

        for side_str in ("long", "short"):
            entry = sv4.entries.long if side_str == "long" else sv4.entries.short
            if entry is None:
                continue
            if normalized_bar.symbol.upper() not in self._entry_symbols:
                continue

            context = SignalEvaluationContext(
                strategy=sv4,
                symbol=normalized_bar.symbol.upper(),
                side=side_str,  # type: ignore[arg-type]
                timestamp=normalized_bar.timestamp,
                deployment_id=self._deployment.deployment_id,
                watchlist_snapshot_id=self._components.universe.id,
                position_contexts={},
            )
            result = signal_source.evaluate(translated_snapshot, context)
            if result.decision != "emitted" or result.signal_plan is None:
                continue
            signal_plan = result.signal_plan

            plans.append(signal_plan)
            # Synthetic CandidateTradeIntent for event logging only.
            candidates.append(
                CandidateTradeIntent(
                    timestamp=normalized_bar.timestamp,
                    symbol=normalized_bar.symbol.upper(),
                    side=CandidateSide.LONG if side_str == "long" else CandidateSide.SHORT,
                    intent_type=IntentType.ENTRY,
                    signal_name="v4_entry",
                    reason="v4_entry_expression_true",
                    feature_values_used={},
                )
            )

        return plans, candidates

    def _aligned_snapshot(self, *, symbol: str, timeframe: str, timestamp: datetime) -> FeatureSnapshot:
        values: dict[str, FeatureValue] = {}
        for spec, feature_key in zip(self._feature_plan.feature_specs, self._feature_plan.feature_keys, strict=True):
            source_snapshot = self._feature_cache.latest_snapshot_at_or_before(
                symbol=symbol,
                timeframe=spec.timeframe,
                timestamp=timestamp,
            )
            if source_snapshot is None:
                values[feature_key] = FeatureValue(value=None, availability=FeatureAvailability.MISSING)
                continue
            values[feature_key] = source_snapshot.values[feature_key]
        return FeatureSnapshot(symbol=symbol.upper(), timeframe=timeframe, timestamp=timestamp, values=values)

    def _result(
        self,
        *,
        candidate_intents: list[CandidateTradeIntent] | None = None,
        signal_plans: list[SignalPlan] | None = None,
        account_evaluations: list[AccountSignalPlanEvaluation] | None = None,
        governor_decisions: list[GovernorDecision] | None = None,
        orders: list[InternalOrder] | None = None,
        broker_results: list[BrokerOrderResult] | None = None,
        ledger_updates: list[InternalOrder] | None = None,
    ) -> PipelineResult:
        self._persist_signal_plans(signal_plans or [])
        return PipelineResult(
            events=self._event_log.snapshot(),
            candidate_intents=tuple(candidate_intents or []),
            signal_plans=tuple(signal_plans or []),
            account_evaluations=tuple(account_evaluations or []),
            governor_decisions=tuple(governor_decisions or []),
            orders=tuple(orders or []),
            broker_results=tuple(broker_results or []),
            ledger_updates=tuple(ledger_updates or []),
        )
