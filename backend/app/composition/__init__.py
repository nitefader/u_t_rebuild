"""Public composition surface for strategy artifact resolution."""

from uuid import UUID

from backend.app.composition.registries import SignalSourceRegistry
from backend.app.composition.strategy_artifact_resolver import (
    StrategyArtifactResolutionError,
    StrategyArtifactResolver,
)
from backend.app.composition.types import (
    StrategyArtifactKind,
    StrategyArtifactMetadata,
)
from backend.app.decision.ports import SignalSourcePort
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.domain.strategy_v4 import StrategyVersionV4


def build_strategy_artifact_resolver() -> tuple[
    SignalSourceRegistry,
    StrategyArtifactResolver,
]:
    registry = SignalSourceRegistry()

    def v4_expression_factory(
        _metadata: StrategyArtifactMetadata,
    ) -> SignalSourcePort:
        return V4ExpressionSignalSource()

    def strategy_v4_lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        from backend.app.strategies_v4.runtime_service import (
            create_strategy_v4_service_from_environment,
        )

        return create_strategy_v4_service_from_environment().get(
            strategy_version_v4_id
        )

    registry.register(StrategyArtifactKind.EXPRESSION_V1, v4_expression_factory)
    resolver = StrategyArtifactResolver(
        registry=registry,
        strategy_v4_lookup=strategy_v4_lookup,
    )
    return registry, resolver

__all__ = [
    "SignalSourceRegistry",
    "StrategyArtifactKind",
    "StrategyArtifactMetadata",
    "StrategyArtifactResolutionError",
    "StrategyArtifactResolver",
    "build_strategy_artifact_resolver",
]
