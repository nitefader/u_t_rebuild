"""Fail-closed registries for composition-owned adapters."""

from __future__ import annotations

from collections.abc import Callable

from backend.app.composition.types import (
    StrategyArtifactKind,
    StrategyArtifactMetadata,
)
from backend.app.decision.ports import SignalSourcePort


class SignalSourceRegistry:
    """Registry for SignalSourcePort factories.

    Re-registering the same kind raises instead of overwriting. Adapter
    registration is composition-root configuration; duplicate registration
    usually means two runtime paths are competing.
    """

    def __init__(self) -> None:
        self._factories: dict[
            StrategyArtifactKind,
            Callable[[StrategyArtifactMetadata], SignalSourcePort],
        ] = {}

    def register(
        self,
        kind: StrategyArtifactKind,
        factory: Callable[[StrategyArtifactMetadata], SignalSourcePort],
    ) -> None:
        if kind in self._factories:
            raise ValueError(f"signal source factory already registered for {kind.value}")
        self._factories[kind] = factory

    def resolve(self, metadata: StrategyArtifactMetadata) -> SignalSourcePort:
        try:
            factory = self._factories[metadata.kind]
        except KeyError as exc:
            raise KeyError(
                f"no SignalSourcePort registered for {metadata.kind.value}"
            ) from exc
        return factory(metadata)
