from __future__ import annotations

from backend.app.domain import IntentType
from backend.app.orders.models import InternalOrderIntent

from .models import GovernorDecision, GovernorPolicy, GovernorRequest


class PortfolioGovernor:
    """Final internal policy gate before internal orders reach a broker adapter."""

    def __init__(self, policy: GovernorPolicy | None = None, *, state_store: object | None = None, governor_id: str = "portfolio-governor") -> None:
        self._state_store = state_store
        self._governor_id = governor_id
        loaded_policy = self._load_policy()
        self._policy = loaded_policy or policy or GovernorPolicy()
        self._persist_policy()

    @property
    def policy(self) -> GovernorPolicy:
        return self._policy

    def save_state(self) -> GovernorPolicy:
        self._persist_policy()
        return self._policy

    def evaluate(self, request: GovernorRequest) -> GovernorDecision:
        order_intent = self._resolve_order_intent(request)
        projected_state = self._projected_state(request, order_intent)
        if self._is_protective_exit(order_intent):
            return GovernorDecision.approve(
                reason="protective_exit_allowed",
                rule_id="protective_exit_bypass",
                projected_state=projected_state,
            )
        if self._policy.global_kill_active:
            return GovernorDecision.reject(
                reason="global_kill_active",
                rule_id="global_kill_blocks_open",
                projected_state=projected_state,
            )
        if request.account_id in self._policy.paused_account_ids:
            return GovernorDecision.reject(
                reason="account_pause_active",
                rule_id="account_pause_blocks_open",
                projected_state=projected_state,
            )
        if request.execution_intent.deployment_id in self._policy.paused_deployment_ids:
            return GovernorDecision.reject(
                reason="deployment_pause_active",
                rule_id="deployment_pause_blocks_open",
                projected_state=projected_state,
            )
        if request.broker_sync.is_stale:
            return GovernorDecision.reject(
                reason="broker_sync_stale",
                rule_id="stale_broker_sync_blocks_open",
                projected_state=projected_state,
            )
        if self._policy.max_open_positions is not None and request.portfolio.open_position_count() >= self._policy.max_open_positions:
            return GovernorDecision.reject(
                reason="max_open_positions_exceeded",
                rule_id="max_open_positions",
                projected_state=projected_state,
            )
        if self._exceeds_limit(projected_state, "gross_exposure_pct", self._policy.max_gross_exposure_pct):
            return GovernorDecision.reject(
                reason="projected_gross_exposure_exceeded",
                rule_id="max_gross_exposure_pct",
                projected_state=projected_state,
            )
        if self._exceeds_limit(projected_state, "net_exposure_pct", self._policy.max_net_exposure_pct):
            return GovernorDecision.reject(
                reason="projected_net_exposure_exceeded",
                rule_id="max_net_exposure_pct",
                projected_state=projected_state,
            )
        if self._exceeds_limit(projected_state, "symbol_concentration_pct", self._policy.max_symbol_concentration_pct):
            return GovernorDecision.reject(
                reason="symbol_concentration_exceeded",
                rule_id="max_symbol_concentration_pct",
                projected_state=projected_state,
            )
        if self._exceeds_limit(projected_state, "open_risk_pct", self._policy.max_open_risk_pct):
            return GovernorDecision.reject(
                reason="open_risk_exceeded",
                rule_id="max_open_risk_pct",
                projected_state=projected_state,
            )
        return GovernorDecision.approve(projected_state=projected_state)

    def approve(self, *, request: GovernorRequest) -> tuple[bool, str]:
        decision = self.evaluate(request)
        return decision.approved, decision.reason

    def _resolve_order_intent(self, request: GovernorRequest) -> InternalOrderIntent:
        if request.order_intent is not None:
            return request.order_intent
        if request.execution_intent.intent_type == IntentType.ENTRY:
            return InternalOrderIntent.OPEN
        return InternalOrderIntent.CLOSE

    def _is_protective_exit(self, order_intent: InternalOrderIntent) -> bool:
        return order_intent in {
            InternalOrderIntent.CLOSE,
            InternalOrderIntent.TAKE_PROFIT,
            InternalOrderIntent.STOP_LOSS,
        }

    def _exceeds_limit(self, projected_state: dict[str, object], key: str, limit: float | None) -> bool:
        return limit is not None and float(projected_state[key]) > limit

    def _projected_state(self, request: GovernorRequest, order_intent: InternalOrderIntent) -> dict[str, object]:
        projected_open_positions = request.portfolio.open_position_count()
        if order_intent == InternalOrderIntent.OPEN:
            projected_open_positions += 1
        symbol = request.execution_intent.symbol.upper()
        candidate_market_value = request.candidate_market_value if order_intent == InternalOrderIntent.OPEN else 0
        candidate_open_risk = request.candidate_open_risk if order_intent == InternalOrderIntent.OPEN else 0
        gross_value = request.portfolio.gross_market_value()
        projected_gross_value = gross_value + request.portfolio.pending_market_value() + candidate_market_value
        projected_net_value = request.portfolio.net_market_value() + request.portfolio.pending_market_value() + candidate_market_value
        projected_symbol_value = (
            request.portfolio.symbol_market_value(symbol)
            + request.portfolio.pending_symbol_market_value(symbol)
            + candidate_market_value
        )
        equity = request.portfolio.equity
        gross_exposure_pct = self._pct(projected_gross_value, equity)
        net_exposure_pct = self._pct(abs(projected_net_value), equity)
        open_risk_pct = self._pct(request.portfolio.open_risk() + request.portfolio.pending_open_risk() + candidate_open_risk, equity)
        pending_open_risk_pct = self._pct(request.portfolio.pending_open_risk() + candidate_open_risk, equity)
        concentration_pct = (projected_symbol_value / projected_gross_value * 100) if projected_gross_value > 0 else 0
        new_open_slots_remaining = None
        if self._policy.max_open_positions is not None:
            new_open_slots_remaining = max(self._policy.max_open_positions - projected_open_positions, 0)
        return {
            "account_id": str(request.account_id),
            "deployment_id": str(request.execution_intent.deployment_id),
            "program_id": str(request.execution_intent.program_version_id),
            "symbol": symbol,
            "order_intent": order_intent.value,
            "open_positions": request.portfolio.open_position_count(),
            "projected_open_positions": projected_open_positions,
            "gross_exposure_pct": gross_exposure_pct,
            "net_exposure_pct": net_exposure_pct,
            "open_risk_pct": open_risk_pct,
            "pending_open_risk_pct": pending_open_risk_pct,
            "symbol_concentration_pct": concentration_pct,
            "new_open_slots_remaining": new_open_slots_remaining,
            "broker_sync_stale": request.broker_sync.is_stale,
        }

    def _pct(self, value: float, equity: float | None) -> float:
        return (value / equity * 100) if equity else 0

    def _load_policy(self) -> GovernorPolicy | None:
        if self._state_store is None:
            return None
        try:
            if hasattr(self._state_store, "load_portfolio_governor_state"):
                return self._state_store.load_portfolio_governor_state(self._governor_id)
            if hasattr(self._state_store, "load_policy"):
                return self._state_store.load_policy(self._governor_id)
        except KeyError:
            return None
        return None

    def _persist_policy(self) -> None:
        if self._state_store is None:
            return
        if hasattr(self._state_store, "save_portfolio_governor_state"):
            self._state_store.save_portfolio_governor_state(self._governor_id, self._policy)
            return
        if hasattr(self._state_store, "save_policy"):
            self._state_store.save_policy(self._governor_id, self._policy)
