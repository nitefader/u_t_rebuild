"""Resolve a Deployment's strategy artifact to its SignalSourcePort."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from backend.app.composition.registries import SignalSourceRegistry
from backend.app.composition.types import (
    StrategyArtifactKind,
    StrategyArtifactMetadata,
)
from backend.app.decision.ports import SignalSourcePort
from backend.app.deployments.models import Deployment
from backend.app.domain.strategy_v4 import StrategyVersionV4


class StrategyArtifactResolutionError(ValueError):
    pass


class StrategyArtifactResolver:
    def __init__(
        self,
        *,
        registry: SignalSourceRegistry,
        strategy_v4_lookup: Callable[[UUID], StrategyVersionV4],
    ) -> None:
        self._registry = registry
        self._strategy_v4_lookup = strategy_v4_lookup

    def resolve(
        self,
        deployment: Deployment,
    ) -> tuple[SignalSourcePort, StrategyArtifactMetadata]:
        if deployment.strategy_version_v4_id is None:
            raise StrategyArtifactResolutionError(
                "deployment strategy_version_v4_id is missing"
            )

        strategy = self._strategy_v4_lookup(deployment.strategy_version_v4_id)
        metadata = StrategyArtifactMetadata(
            kind=StrategyArtifactKind.EXPRESSION_V1,
            strategy_version_v4_id=deployment.strategy_version_v4_id,
            strategy_id=strategy.strategy_v4_id,
        )
        return self._registry.resolve(metadata), metadata
