from __future__ import annotations

from uuid import uuid4

import pytest

from backend.app.composition import (
    SignalSourceRegistry,
    StrategyArtifactKind,
    StrategyArtifactMetadata,
)
from backend.app.decision.ports import (
    FeatureSnapshot,
    SignalEvaluationContext,
    SignalEvaluationResult,
)


class _TinySignalSource:
    def evaluate(
        self,
        snapshot: FeatureSnapshot,
        contexts: SignalEvaluationContext,
    ) -> SignalEvaluationResult:
        return SignalEvaluationResult(
            decision="no_signal",
            source="v4_expression",
            diagnostics={"symbol": snapshot.symbol},
        )


def _metadata() -> StrategyArtifactMetadata:
    return StrategyArtifactMetadata(
        kind=StrategyArtifactKind.EXPRESSION_V1,
        strategy_version_v4_id=uuid4(),
        strategy_id=uuid4(),
    )


def test_register_and_resolve_returns_factory_result() -> None:
    registry = SignalSourceRegistry()
    source = _TinySignalSource()
    seen_metadata: list[StrategyArtifactMetadata] = []
    metadata = _metadata()

    registry.register(
        StrategyArtifactKind.EXPRESSION_V1,
        lambda value: (seen_metadata.append(value) or source),
    )

    resolved = registry.resolve(metadata)

    assert resolved is source
    assert seen_metadata == [metadata]


def test_resolve_raises_when_kind_is_unregistered() -> None:
    registry = SignalSourceRegistry()

    with pytest.raises(KeyError, match="no SignalSourcePort registered"):
        registry.resolve(_metadata())


def test_registering_same_kind_twice_raises() -> None:
    registry = SignalSourceRegistry()
    registry.register(
        StrategyArtifactKind.EXPRESSION_V1,
        lambda _metadata: _TinySignalSource(),
    )

    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            StrategyArtifactKind.EXPRESSION_V1,
            lambda _metadata: _TinySignalSource(),
        )
