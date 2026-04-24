from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import CandidateTradeIntent
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy_controls import StrategyControlsVersion
from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedProgramComponents,
    build_feature_plan,
)

from .models import (
    DeploymentContext,
    ExecutionIntent,
    RuntimeDecisionBatch,
    RuntimeError,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeState,
    RuntimeStatus,
)


class RuntimeEventLog:
    def __init__(self, *, deployment_id) -> None:  # type: ignore[no-untyped-def]
        self._deployment_id = deployment_id
        self._events: list[RuntimeEvent] = []

    def append(
        self,
        *,
        timestamp: datetime,
        event_type: RuntimeEventType,
        message: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._events.append(
            RuntimeEvent(
                sequence=len(self._events) + 1,
                timestamp=timestamp,
                event_type=event_type,
                deployment_id=self._deployment_id,
                symbol=symbol,
                timeframe=timeframe,
                message=message,
                details=details or {},
            )
        )

    def snapshot(self) -> tuple[RuntimeEvent, ...]:
        return tuple(self._events)


class RuntimeStateStore:
    def __init__(self, state: RuntimeState) -> None:
        self._state = state

    @property
    def state(self) -> RuntimeState:
        return self._state

    def record_bar(self, *, symbol: str, timeframe: str, timestamp: datetime) -> None:
        key = f"{symbol.upper()}:{timeframe}"
        timestamps = dict(self._state.last_bar_timestamp_by_symbol_timeframe)
        timestamps[key] = timestamp
        self._state = self._state.model_copy(
            update={
                "status": RuntimeStatus.RUNNING,
                "processed_bar_count": self._state.processed_bar_count + 1,
                "last_bar_timestamp_by_symbol_timeframe": timestamps,
                "last_error": None,
            }
        )

    def record_candidate(self, timestamp: datetime) -> None:
        self._state = self._state.model_copy(
            update={
                "candidate_intent_count": self._state.candidate_intent_count + 1,
                "last_signal_timestamp": timestamp,
            }
        )

    def record_execution_intent(self, timestamp: datetime) -> None:
        self._state = self._state.model_copy(
            update={
                "execution_intent_count": self._state.execution_intent_count + 1,
                "last_execution_intent_timestamp": timestamp,
            }
        )

    def record_error(self, message: str) -> None:
        self._state = self._state.model_copy(update={"status": RuntimeStatus.ERROR, "last_error": message})


class PortfolioGovernor:
    """Minimal internal authority for runtime decisions before broker work exists."""

    def approve(self, *, state: RuntimeState, intent: ExecutionIntent) -> tuple[bool, str]:
        if state.status in {RuntimeStatus.PAUSED, RuntimeStatus.KILLED, RuntimeStatus.ERROR}:
            return False, f"runtime_state_{state.status.value}"
        if intent.qty <= 0:
            return False, "invalid_qty"
        return True, "approved"


class ExecutionIntentBuilder:
    def build_with_risk_profile(
        self,
        *,
        deployment: DeploymentContext,
        components: ResolvedProgramComponents,
        candidate: CandidateTradeIntent,
        price: float,
        initial_cash: float,
    ) -> ExecutionIntent:
        qty = self._size_from_components(components=components, candidate=candidate, price=price, initial_cash=initial_cash)
        return ExecutionIntent(
            deployment_id=deployment.deployment_id,
            program_version_id=deployment.program.id,
            symbol=candidate.symbol,
            side=candidate.side,
            intent_type=candidate.intent_type,
            qty=qty,
            order_type=components.execution_style.entry_order_type,
            time_in_force=components.execution_style.time_in_force,
            timestamp=candidate.timestamp,
            signal_name=candidate.signal_name,
            reason=candidate.reason,
            features_used=candidate.feature_values_used,
            stop_candidate=candidate.stop_candidate,
            target_candidate=candidate.target_candidate,
        )

    def _size_from_components(
        self,
        *,
        components: ResolvedProgramComponents,
        candidate: CandidateTradeIntent,
        price: float,
        initial_cash: float,
    ) -> float:
        risk = components.risk_profile
        if risk.sizing_method == PositionSizingMethod.FIXED_SHARES:
            if risk.fixed_shares is None:
                raise RuntimeError("fixed_shares sizing requires fixed_shares")
            return float(risk.fixed_shares)
        if risk.sizing_method == PositionSizingMethod.FIXED_DOLLAR:
            if risk.fixed_notional is None:
                raise RuntimeError("fixed_dollar sizing requires fixed_notional")
            return max(risk.fixed_notional / price, 0.000001)
        if risk.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY:
            if risk.risk_per_trade_pct is None:
                raise RuntimeError("risk_percent_equity sizing requires risk_per_trade_pct")
            risk_amount = initial_cash * (risk.risk_per_trade_pct / 100)
            if candidate.stop_candidate is not None:
                per_share_risk = max(price - candidate.stop_candidate, 0)
                if per_share_risk > 0:
                    return max(risk_amount / per_share_risk, 0.000001)
            return max(risk_amount / price, 0.000001)
        raise RuntimeError(f"unsupported sizing method '{risk.sizing_method}'")


class RuntimeEngine:
    def __init__(
        self,
        *,
        deployment: DeploymentContext,
        components: ResolvedProgramComponents,
        initial_cash: float = 100_000,
        feature_engine: IncrementalFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
        governor: PortfolioGovernor | None = None,
        intent_builder: ExecutionIntentBuilder | None = None,
        feature_cache: FeatureCache | None = None,
    ) -> None:
        self._deployment = deployment
        self._components = components
        self._initial_cash = initial_cash
        self._feature_engine = feature_engine or IncrementalFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._governor = governor or PortfolioGovernor()
        self._intent_builder = intent_builder or ExecutionIntentBuilder()
        self._feature_cache = feature_cache or FeatureCache()
        self._feature_plan = build_feature_plan(components, consumer="runtime")
        self._state_store = RuntimeStateStore(
            RuntimeState(deployment_id=deployment.deployment_id, status=deployment.status)
        )
        self._event_log = RuntimeEventLog(deployment_id=deployment.deployment_id)

    @property
    def state(self) -> RuntimeState:
        return self._state_store.state

    @property
    def feature_cache(self) -> FeatureCache:
        return self._feature_cache

    @property
    def feature_plan(self) -> FeaturePlan:
        return self._feature_plan

    def process_bar(self, bar: NormalizedBar) -> RuntimeDecisionBatch:
        normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
        self._event_log.append(
            timestamp=normalized_bar.timestamp,
            event_type=RuntimeEventType.BAR_RECEIVED,
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            message="runtime received completed bar",
        )
        feature_update = self._feature_engine.update(
            plan=self._feature_plan,
            bar=normalized_bar,
            cache=self._feature_cache,
        )
        self._state_store.record_bar(
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            timestamp=normalized_bar.timestamp,
        )
        self._event_log.append(
            timestamp=normalized_bar.timestamp,
            event_type=RuntimeEventType.FEATURE_UPDATED,
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            message="incremental features updated",
            details={"feature_count": len(feature_update.snapshot.values)},
        )

        execution_intents: list[ExecutionIntent] = []
        if normalized_bar.timeframe == self._components.strategy_controls.timeframe:
            execution_intents.extend(self._evaluate_runtime_decisions(normalized_bar))

        self._event_log.append(
            timestamp=normalized_bar.timestamp,
            event_type=RuntimeEventType.RUNTIME_STATE_UPDATED,
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            message="runtime state updated",
            details={"processed_bar_count": self._state_store.state.processed_bar_count},
        )
        return RuntimeDecisionBatch(
            state=self._state_store.state,
            events=self._event_log.snapshot(),
            execution_intents=tuple(execution_intents),
        )

    def process_bars(self, bars: Iterable[NormalizedBar]) -> RuntimeDecisionBatch:
        latest: RuntimeDecisionBatch | None = None
        for bar in bars:
            latest = self.process_bar(bar)
        if latest is None:
            return RuntimeDecisionBatch(state=self._state_store.state, events=self._event_log.snapshot(), execution_intents=())
        return latest

    def _evaluate_runtime_decisions(self, bar: NormalizedBar) -> list[ExecutionIntent]:
        if not self._controls_allow(self._components.strategy_controls, bar.timestamp):
            self._event_log.append(
                timestamp=bar.timestamp,
                event_type=RuntimeEventType.SIGNAL_BLOCKED,
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                message="strategy controls blocked runtime signal evaluation",
            )
            return []

        aligned_snapshot = self._aligned_snapshot(symbol=bar.symbol, timeframe=bar.timeframe, timestamp=bar.timestamp)
        try:
            signal_evaluation = self._signal_engine.evaluate(self._components.strategy, aligned_snapshot)
        except SignalEvaluationError as exc:
            self._state_store.record_error(str(exc))
            self._event_log.append(
                timestamp=bar.timestamp,
                event_type=RuntimeEventType.SIGNAL_BLOCKED,
                symbol=bar.symbol,
                timeframe=bar.timeframe,
                message=str(exc),
            )
            return []

        execution_intents: list[ExecutionIntent] = []
        for candidate in signal_evaluation.intents:
            self._state_store.record_candidate(candidate.timestamp)
            self._event_log.append(
                timestamp=candidate.timestamp,
                event_type=RuntimeEventType.SIGNAL_CANDIDATE,
                symbol=candidate.symbol,
                timeframe=bar.timeframe,
                message="candidate trade intent emitted",
                details={"signal_name": candidate.signal_name, "intent_type": candidate.intent_type.value},
            )
            intent = self._intent_builder.build_with_risk_profile(
                deployment=self._deployment,
                components=self._components,
                candidate=candidate,
                price=bar.close,
                initial_cash=self._initial_cash,
            )
            approved, reason = self._governor.approve(state=self._state_store.state, intent=intent)
            intent = intent.model_copy(update={"governor_approved": approved, "governor_reason": reason})
            if approved:
                self._state_store.record_execution_intent(intent.timestamp)
                execution_intents.append(intent)
                self._event_log.append(
                    timestamp=intent.timestamp,
                    event_type=RuntimeEventType.EXECUTION_INTENT_CREATED,
                    symbol=intent.symbol,
                    timeframe=bar.timeframe,
                    message="execution intent created",
                    details={"qty": intent.qty, "order_type": intent.order_type.value, "governor_reason": reason},
                )
            else:
                self._event_log.append(
                    timestamp=intent.timestamp,
                    event_type=RuntimeEventType.EXECUTION_INTENT_BLOCKED,
                    symbol=intent.symbol,
                    timeframe=bar.timeframe,
                    message="execution intent blocked by portfolio governor",
                    details={"governor_reason": reason},
                )
        return execution_intents

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

    def _controls_allow(self, controls: StrategyControlsVersion, timestamp: datetime) -> bool:
        if not controls.session_windows:
            return True
        current_time = timestamp.timetz().replace(tzinfo=None)
        return any(window.start <= current_time <= window.end for window in controls.session_windows)
