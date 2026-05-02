"""Public composition surface for strategy artifact resolution."""

from backend.app.composition.registries import SignalSourceRegistry
from backend.app.composition.strategy_artifact_resolver import (
    StrategyArtifactResolutionError,
    StrategyArtifactResolver,
)
from backend.app.composition.types import (
    StrategyArtifactKind,
    StrategyArtifactMetadata,
)

__all__ = [
    "SignalSourceRegistry",
    "StrategyArtifactKind",
    "StrategyArtifactMetadata",
    "StrategyArtifactResolutionError",
    "StrategyArtifactResolver",
]
