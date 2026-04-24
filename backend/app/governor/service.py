from __future__ import annotations

from backend.app.domain import IntentType
from backend.app.orders.models import InternalOrderIntent

from .models import GovernorDecision, GovernorPolicy, GovernorRequest


class PortfolioGovernor:
    """Final internal policy gate before internal orders reach a broker adapter."""

    def __init__(self, policy: GovernorPolicy | None = None) -> None:
        self._policy = policy or GovernorPolicy()

    @property
    def policy(self) -> GovernorPolicy:
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

    def _projected_state(self, request: GovernorRequest, order_intent: InternalOrderIntent) -> dict[str, object]:
        projected_open_positions = request.portfolio.open_position_count()
        if order_intent == InternalOrderIntent.OPEN:
            projected_open_positions += 1
        symbol = request.execution_intent.symbol.upper()
        gross_value = request.portfolio.gross_market_value()
        symbol_value = request.portfolio.symbol_market_value(symbol)
        concentration_pct = (symbol_value / gross_value * 100) if gross_value > 0 else 0
        concentration_status = "not_enforced_v1"
        if self._policy.max_symbol_concentration_pct is not None:
            concentration_status = "placeholder_only_v1"
        return {
            "account_id": str(request.account_id),
            "deployment_id": str(request.execution_intent.deployment_id),
            "program_id": str(request.execution_intent.program_version_id),
            "symbol": symbol,
            "order_intent": order_intent.value,
            "open_positions": request.portfolio.open_position_count(),
            "projected_open_positions": projected_open_positions,
            "symbol_concentration_pct": concentration_pct,
            "symbol_concentration_rule": concentration_status,
        }
