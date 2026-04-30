from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
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
from backend.app.decision import (
    PositionContext,
    SignalEngine,
    SignalEvaluation,
    SignalEvaluationError,
    SignalPlanBuilder,
)
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    CandidateTradeIntent,
    IntentType,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
    TradingMode,
)
from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    FeatureFrame,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedDeploymentComponents,
    build_feature_plan,
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
    def __init__(
        self,
        *,
        account_id: UUID,
        account_ids: tuple[UUID, ...] | None = None,
        deployment: DeploymentContext,
        components: ResolvedDeploymentComponents,
        initial_cash: float = 100_000,
        feature_engine: IncrementalFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
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
        feature_cache: FeatureCache | None = None,
        control_plane: ControlPlane | None = None,
        runtime_store: object | None = None,
        position_reader: object | None = None,
        broker_preflight_service: AlpacaBrokerPreflightService | None = None,
        market_rule_preflight_service: MarketRulePreflightService | None = None,
        live_order_submission_enabled: bool = False,
    ) -> None:
        self._account_id = account_id
        self._account_ids = tuple(dict.fromkeys(account_ids or (account_id,)))
        self._deployment = deployment
        self._components = components
        self._initial_cash = initial_cash
        self._feature_engine = feature_engine or IncrementalFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._controls_gate = controls_gate or StrategyControlsGate()
        self._signal_plan_builder = signal_plan_builder or SignalPlanBuilder()
        self._risk_resolver = risk_resolver or RiskResolver()
        self._governor = governor or PortfolioGovernor()
        self._governor_policy_resolver = governor_policy_resolver
        # Slice A interim per GOVERNOR_WIRING_MAP §0/§G-3: try the deployment's
        # risk_horizon (added in Slice B), fall back to StrategyControls'
        # trading_horizon. Either way the resolver gets a real horizon, so
        # AccountRiskConfig limits enforce immediately while RiskPlan-by-horizon
        # remains a no-op until Slice B.
        deployment_horizon = getattr(deployment, "risk_horizon", None)
        self._deployment_risk_horizon = deployment_horizon or components.strategy_controls.trading_horizon
        # Slice B: track whether the Deployment has an EXPLICIT risk_horizon.
        # Only when True do we pass enforce_plan_required=True to the resolver,
        # activating the "Account must have a plan for this horizon" doctrine.
        # Fallback to StrategyControls.trading_horizon does NOT enforce this
        # rule — the deployment did not declare a horizon, so we can't know
        # whether the operator intends per-horizon plan enforcement.
        self._deployment_has_explicit_risk_horizon = deployment_horizon is not None
        self._broker_adapter = broker_adapter or FakeBrokerAdapter()
        self._order_manager = order_manager or OrderManager(broker_adapter=self._broker_adapter)
        self._broker_sync = broker_sync or BrokerSync(ledger=self._order_manager.ledger)
        self._trade_ledger = trade_ledger or TradeLedger()
        self._broker_sync_service = broker_sync_service or BrokerSyncService(
            adapter=self._broker_adapter,
            broker_sync=self._broker_sync,
            order_ledger=self._order_manager.ledger,
            trade_ledger=self._trade_ledger,
            runtime_store=runtime_store,
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
        self._runtime_state = self._load_runtime_state() or RuntimeState(deployment_id=deployment.deployment_id)
        self._persist_runtime_state()
        self._event_log = RuntimePipelineEventLog(deployment_id=deployment.deployment_id)
        self._entry_symbols = frozenset(symbol.symbol.upper() for symbol in components.universe.symbols)

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

    def process_bar(self, bar: NormalizedBar) -> PipelineResult:
        self._reset_positions_cache()
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
        try:
            signal_result = self._signal_engine.evaluate(
                self._components.strategy,
                self._aligned_snapshot(symbol=normalized_bar.symbol, timeframe=normalized_bar.timeframe, timestamp=normalized_bar.timestamp),
                position_contexts=self._position_contexts(bar=normalized_bar),
            )
        except SignalEvaluationError as exc:
            self._event_log.append(
                timestamp=normalized_bar.timestamp,
                event_type=PipelineEventType.SIGNAL_BLOCKED,
                symbol=normalized_bar.symbol,
                message=str(exc),
            )
            return self._result()

        candidate_intents: list[CandidateTradeIntent] = []
        signal_plans: list[SignalPlan] = []
        account_evaluations: list[AccountSignalPlanEvaluation] = []
        governor_decisions: list[GovernorDecision] = []
        orders: list[InternalOrder] = []
        broker_results: list[BrokerOrderResult] = []
        ledger_updates: list[InternalOrder] = []
        for candidate in signal_result.intents:
            candidate_intents.append(candidate)
            self._event_log.append(
                timestamp=candidate.timestamp,
                event_type=PipelineEventType.CANDIDATE_TRADE_INTENT,
                symbol=candidate.symbol,
                message="candidate trade intent emitted",
                details={"signal_name": candidate.signal_name},
            )
            if candidate.intent_type != IntentType.ENTRY or candidate.symbol.upper() not in self._entry_symbols:
                continue
            signal_plan = self._signal_plan_builder.build_from_candidate(
                candidate=candidate,
                deployment_id=self._deployment.deployment_id,
                strategy_id=self._components.strategy.strategy_id,
                strategy_version_id=self._components.strategy.id,
                watchlist_snapshot_id=self._components.universe.id,
            )
            if signal_plan.entry is not None:
                signal_plan = signal_plan.model_copy(
                    update={
                        "entry": signal_plan.entry.model_copy(
                            update={
                                "order_type": self._components.execution_style.entry_order_type,
                                "time_in_force_preference": self._components.execution_style.time_in_force,
                            }
                        )
                    }
                )
            signal_plans.append(signal_plan)
            for account_id in self._account_ids:
                lifecycle_sizing = self._risk_resolver.lifecycle_sizing_from_risk_profile(
                    AccountRiskSizingInput(
                        risk_profile=self._components.risk_profile,
                        price=normalized_bar.close,
                        initial_cash=self._initial_cash,
                        stop_candidate=candidate.stop_candidate,
                    )
                )
                risk_result = self._risk_resolver.resolve_lifecycle(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    sizing=lifecycle_sizing,
                )
                decision = self._evaluate_governor_for_signal_plan(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    order_intent=InternalOrderIntent.OPEN,
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
                account_evaluations.append(account_evaluation)
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
                result, ledger_update = self._submit_sync_order(order)
                broker_results.append(result)
                ledger_updates.append(ledger_update)
        self._process_position_management_candidates(
            signal_result=signal_result,
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
        signal_result: SignalEvaluation,
        normalized_bar: NormalizedBar,
        signal_plans: list[SignalPlan],
        account_evaluations: list[AccountSignalPlanEvaluation],
        governor_decisions: list[GovernorDecision],
        orders: list[InternalOrder],
        broker_results: list[BrokerOrderResult],
        ledger_updates: list[InternalOrder],
    ) -> None:
        exit_candidates = tuple(candidate for candidate in signal_result.intents if candidate.intent_type == IntentType.EXIT)
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
            signal_plan = self._signal_plan_builder.build_from_candidate(
                candidate=candidate,
                deployment_id=self._deployment.deployment_id,
                strategy_id=self._components.strategy.strategy_id,
                strategy_version_id=self._components.strategy.id,
                opening_signal_plan_id=opening_signal_plan_id,
                related_position_lineage_id=related_position_lineage_id,
            )
            signal_plans.append(signal_plan)
            for account_id in self._account_ids:
                account_active_positions = tuple(active_positions_by_account.get(account_id, ()))
                if len(account_active_positions) > 1:
                    account_evaluations.append(
                        self._blocked_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="multiple_active_position_lineages_for_account",
                        )
                    )
                    continue
                position = account_active_positions[0] if account_active_positions else inactive_positions_by_account.get(account_id)
                if position is None:
                    account_evaluations.append(
                        self._ignored_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="account_has_no_matching_position",
                        )
                    )
                    continue
                if not self._position_is_active(position):
                    account_evaluations.append(
                        self._ignored_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="position_already_closed",
                        )
                    )
                    continue
                if position.position_lineage_id is None:
                    account_evaluations.append(
                        self._blocked_position_management_evaluation(
                            account_id=account_id,
                            signal_plan=signal_plan,
                            timestamp=normalized_bar.timestamp,
                            reason="position_missing_lineage",
                        )
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
                account_evaluations.append(account_evaluation)
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
                result, ledger_update = self._submit_sync_order(order)
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
            broker_result, ledger_update = self._submit_sync_order(order)
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

    def _submit_sync_order(self, order: InternalOrder) -> tuple[BrokerOrderResult, InternalOrder]:
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
        return broker_result, ledger_update

    def _preflight_order_submission(self, order: InternalOrder) -> BrokerOrderResult | None:
        broker_mode = getattr(self._broker_adapter, "mode", self._deployment.mode)
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

    def _evaluate_governor_for_signal_plan(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        position_lineage_id: UUID | None = None,
        order_intent: InternalOrderIntent,
    ) -> GovernorDecision:
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

    def _position_contexts(self, *, bar: NormalizedBar) -> dict[str, PositionContext]:
        """Build per-symbol PositionContext for SignalEngine exit-rule evaluation.

        Doctrine: ``logical_exit`` is the only exit intent. Time / bar / session
        / hybrid exit rules need this context; pure feature-condition exits
        only need ``has_position`` so the engine knows there's something to
        exit.
        """
        positions = self._positions_for_deployment()
        contexts: dict[str, PositionContext] = {}
        for position in positions:
            if not DeploymentPositionManager.is_active(position):
                continue
            symbol = position.symbol.upper()
            opened_at = getattr(position, "opened_at", None) or getattr(position, "open_timestamp", None)
            contexts[symbol] = PositionContext(
                has_position=True,
                entry_timestamp=opened_at,
                entry_bar_index=None,
                current_bar_index=None,
                bar_timestamp=bar.timestamp,
            )
        # Always supply a PositionContext for the bar's symbol so the engine
        # can short-circuit "no position" cleanly when no live position exists.
        contexts.setdefault(bar.symbol.upper(), PositionContext(bar_timestamp=bar.timestamp))
        return contexts

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
