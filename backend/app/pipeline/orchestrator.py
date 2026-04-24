from __future__ import annotations

from datetime import datetime
from uuid import UUID

from backend.app.brokers import BrokerAdapter, BrokerAdapterError, BrokerOrderResult, BrokerOrderStatus, BrokerSync, FakeBrokerAdapter
from backend.app.control_plane.service import ControlPlane
from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import CandidateTradeIntent
from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    FeatureFrame,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedProgramComponents,
    build_feature_plan,
)
from backend.app.governor import (
    BrokerSyncFreshness,
    GovernorDecision,
    GovernorRequest,
    PortfolioGovernor,
    PortfolioSnapshot,
)
from backend.app.orders import InternalOrder, InternalOrderIntent, OrderManager
from backend.app.runtime import DeploymentContext, ExecutionIntent, ExecutionIntentBuilder, RuntimeState

from .models import PipelineEvent, PipelineEventType, PipelineResult


class StrategyControlsGate:
    def allows(self, *, components: ResolvedProgramComponents, timestamp: datetime) -> bool:
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


class RuntimeOrchestrator:
    def __init__(
        self,
        *,
        account_id: UUID,
        deployment: DeploymentContext,
        components: ResolvedProgramComponents,
        initial_cash: float = 100_000,
        feature_engine: IncrementalFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
        controls_gate: StrategyControlsGate | None = None,
        intent_builder: ExecutionIntentBuilder | None = None,
        governor: PortfolioGovernor | None = None,
        order_manager: OrderManager | None = None,
        broker_adapter: BrokerAdapter | None = None,
        broker_sync: BrokerSync | None = None,
        broker_freshness: BrokerSyncFreshness | None = None,
        portfolio_snapshot: PortfolioSnapshot | None = None,
        feature_cache: FeatureCache | None = None,
        control_plane: ControlPlane | None = None,
        runtime_store: object | None = None,
    ) -> None:
        self._account_id = account_id
        self._deployment = deployment
        self._components = components
        self._initial_cash = initial_cash
        self._feature_engine = feature_engine or IncrementalFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._controls_gate = controls_gate or StrategyControlsGate()
        self._intent_builder = intent_builder or ExecutionIntentBuilder()
        self._governor = governor or PortfolioGovernor()
        self._order_manager = order_manager or OrderManager()
        self._broker_adapter = broker_adapter or FakeBrokerAdapter()
        self._broker_sync = broker_sync or BrokerSync(ledger=self._order_manager.ledger)
        self._broker_freshness = broker_freshness or BrokerSyncFreshness()
        self._portfolio_snapshot = portfolio_snapshot or PortfolioSnapshot()
        self._feature_cache = feature_cache or FeatureCache()
        self._control_plane = control_plane or ControlPlane()
        self._runtime_store = runtime_store
        self._feature_plan = build_feature_plan(components, consumer="runtime")
        self._runtime_state = self._load_runtime_state() or RuntimeState(deployment_id=deployment.deployment_id)
        self._persist_runtime_state()
        self._event_log = RuntimePipelineEventLog(deployment_id=deployment.deployment_id)

    @property
    def order_manager(self) -> OrderManager:
        return self._order_manager

    @property
    def feature_cache(self) -> FeatureCache:
        return self._feature_cache

    @property
    def feature_plan(self) -> FeaturePlan:
        return self._feature_plan

    def process_bar(self, bar: NormalizedBar) -> PipelineResult:
        normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
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
        execution_intents: list[ExecutionIntent] = []
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
            intent = self._intent_builder.build_with_risk_profile(
                deployment=self._deployment,
                components=self._components,
                candidate=candidate,
                price=normalized_bar.close,
                initial_cash=self._initial_cash,
            )
            execution_intents.append(intent)
            self._event_log.append(
                timestamp=intent.timestamp,
                event_type=PipelineEventType.EXECUTION_INTENT,
                symbol=intent.symbol,
                message="execution intent built",
                details={"qty": intent.qty, "order_type": intent.order_type.value},
            )
            decision = self._evaluate_governor(intent=intent, order_intent=InternalOrderIntent.OPEN)
            governor_decisions.append(decision)
            self._emit_governor_decision(timestamp=intent.timestamp, symbol=intent.symbol, decision=decision)
            if not decision.approved:
                continue
            control_decision = self._control_plane.can_open_new_position(
                account_id=self._account_id,
                deployment_id=intent.deployment_id,
                symbol=intent.symbol,
                side=intent.side.value,
            )
            if not control_decision.allowed:
                self._event_log.append(
                    timestamp=intent.timestamp,
                    event_type=PipelineEventType.GOVERNOR_DECISION,
                    symbol=intent.symbol,
                    message="control plane blocked opening order",
                    details={
                        "approved": False,
                        "reason": control_decision.reason,
                        "rule_id": control_decision.rule_id,
                    },
                )
                continue
            approved_intent = intent.model_copy(update={"governor_approved": True, "governor_reason": decision.reason})
            order, result, ledger_update = self._create_submit_sync(
                execution_intent=approved_intent,
                order_intent=InternalOrderIntent.OPEN,
            )
            orders.append(order)
            broker_results.append(result)
            ledger_updates.append(ledger_update)
        return self._result(
            candidate_intents=candidate_intents,
            execution_intents=execution_intents,
            governor_decisions=governor_decisions,
            orders=orders,
            broker_results=broker_results,
            ledger_updates=ledger_updates,
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

    def process_protective_intent(
        self,
        *,
        execution_intent: ExecutionIntent,
        order_intent: InternalOrderIntent,
    ) -> PipelineResult:
        decision = self._evaluate_governor(intent=execution_intent, order_intent=order_intent)
        self._emit_governor_decision(timestamp=execution_intent.timestamp, symbol=execution_intent.symbol, decision=decision)
        execution_intents = [execution_intent]
        if not decision.approved:
            return self._result(execution_intents=execution_intents, governor_decisions=[decision])
        approved_intent = execution_intent.model_copy(update={"governor_approved": True, "governor_reason": decision.reason})
        order, broker_result, ledger_update = self._create_submit_sync(
            execution_intent=approved_intent,
            order_intent=order_intent,
        )
        return self._result(
            execution_intents=[approved_intent],
            governor_decisions=[decision],
            orders=[order],
            broker_results=[broker_result],
            ledger_updates=[ledger_update],
        )

    def _create_submit_sync(
        self,
        *,
        execution_intent: ExecutionIntent,
        order_intent: InternalOrderIntent,
    ) -> tuple[InternalOrder, BrokerOrderResult, InternalOrder]:
        order = self._order_manager.create_order(
            account_id=self._account_id,
            execution_intent=execution_intent,
            order_intent=order_intent,
        )
        self._event_log.append(
            timestamp=order.created_at,
            event_type=PipelineEventType.ORDER_CREATED,
            symbol=order.symbol,
            message="internal order created",
            details={"order_id": str(order.order_id), "client_order_id": order.client_order_id, "intent": order.intent.value},
        )
        try:
            broker_result = self._broker_adapter.submit_order(order)
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
        return order, broker_result, ledger_update

    def _broker_error_reason(self, exc: BrokerAdapterError) -> str:
        details = getattr(exc, "details", None)
        code = getattr(details, "code", None)
        if code:
            return f"broker_adapter_error:{code}"
        return "broker_adapter_error"

    def _evaluate_governor(self, *, intent: ExecutionIntent, order_intent: InternalOrderIntent) -> GovernorDecision:
        return self._governor.evaluate(
            GovernorRequest(
                account_id=self._account_id,
                execution_intent=intent,
                runtime_state=self._runtime_state,
                broker_sync=self._broker_freshness,
                portfolio=self._portfolio_snapshot,
                order_intent=order_intent,
            )
        )

    def _emit_governor_decision(self, *, timestamp: datetime, symbol: str, decision: GovernorDecision) -> None:
        self._event_log.append(
            timestamp=timestamp,
            event_type=PipelineEventType.GOVERNOR_DECISION,
            symbol=symbol,
            message="portfolio governor decision",
            details={"approved": decision.approved, "reason": decision.reason, "rule_id": decision.rule_id},
        )

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
        execution_intents: list[ExecutionIntent] | None = None,
        governor_decisions: list[GovernorDecision] | None = None,
        orders: list[InternalOrder] | None = None,
        broker_results: list[BrokerOrderResult] | None = None,
        ledger_updates: list[InternalOrder] | None = None,
    ) -> PipelineResult:
        return PipelineResult(
            events=self._event_log.snapshot(),
            candidate_intents=tuple(candidate_intents or []),
            execution_intents=tuple(execution_intents or []),
            governor_decisions=tuple(governor_decisions or []),
            orders=tuple(orders or []),
            broker_results=tuple(broker_results or []),
            ledger_updates=tuple(ledger_updates or []),
        )
