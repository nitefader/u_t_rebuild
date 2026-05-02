"""V4 expression signal source adapter."""
from __future__ import annotations

from backend.app.decision.ports import (
    FeatureSnapshot,
    SignalEvaluationContext,
    SignalEvaluationResult,
)
from backend.app.decision.signal_plan_builder_v4 import (
    ExpressionLoader,
    _default_expression_loader,
    build_signal_plan_from_v4,
)
from backend.app.domain.strategy_v4 import StrategyVersionV4


class V4ExpressionSignalSource:
    """Implements SignalSourcePort by delegating to build_signal_plan_from_v4.

    SignalSourcePort declares ``FeatureSnapshot`` and the v4 builder declares
    ``RuntimeFeatureSnapshot``; today both resolve to
    ``backend.app.features.frames.FeatureSnapshot``. This adapter performs no
    conversion or casting, so a future type split must be handled explicitly
    before this delegation remains valid.
    """

    def __init__(
        self,
        expression_loader: ExpressionLoader = _default_expression_loader,
    ) -> None:
        self._expression_loader = expression_loader

    def evaluate(
        self,
        snapshot: FeatureSnapshot,
        contexts: SignalEvaluationContext,
    ) -> SignalEvaluationResult:
        if not isinstance(contexts.strategy, StrategyVersionV4):
            raise TypeError("V4ExpressionSignalSource requires StrategyVersionV4")

        symbol = contexts.symbol
        side = contexts.side
        timestamp = contexts.timestamp
        deployment_id = contexts.deployment_id
        missing = [
            field_name
            for field_name, value in (
                ("symbol", symbol),
                ("side", side),
                ("timestamp", timestamp),
                ("deployment_id", deployment_id),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                "V4ExpressionSignalSource missing required context fields: "
                + ", ".join(missing)
            )

        assert symbol is not None
        assert side is not None
        assert timestamp is not None
        assert deployment_id is not None

        plan = build_signal_plan_from_v4(
            strategy=contexts.strategy,
            snapshot=snapshot,
            symbol=symbol,
            side=side,
            timestamp=timestamp,
            deployment_id=deployment_id,
            watchlist_snapshot_id=contexts.watchlist_snapshot_id,
            expression_loader=self._expression_loader,
        )

        if plan is None:
            return SignalEvaluationResult(
                decision="no_signal",
                source="v4_expression",
            )

        return SignalEvaluationResult(
            decision="emitted",
            source="v4_expression",
            signal_plan=plan,
        )
