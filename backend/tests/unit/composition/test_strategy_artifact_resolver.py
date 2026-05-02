from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import Request
from starlette.testclient import TestClient

from backend.app.api import server
from backend.app.composition import (
    SignalSourceRegistry,
    StrategyArtifactKind,
    StrategyArtifactResolutionError,
    StrategyArtifactResolver,
)
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.deployments.models import Deployment
from backend.app.domain.strategy_v4 import (
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyStopV4,
    StrategyVersionV4,
)


def _strategy(
    *,
    strategy_version_v4_id: UUID,
    strategy_id: UUID,
) -> StrategyVersionV4:
    return StrategyVersionV4(
        id=strategy_version_v4_id,
        strategy_v4_id=strategy_id,
        version=1,
        name="Resolver Test Strategy",
        entries=StrategyEntriesV4(long=StrategyEntryV4(expression_text="true")),
        stops=(
            StrategyStopV4(
                mode="simple",
                simple_type="$",
                simple_value=1.0,
            ),
        ),
        legs=(),
    )


def _deployment(
    *,
    strategy_version_id: UUID | None = None,
    strategy_version_v4_id: UUID | None = None,
) -> Deployment:
    return Deployment.model_construct(
        deployment_id=uuid4(),
        name="Resolver Test Deployment",
        strategy_version_id=strategy_version_id,
        strategy_version_v4_id=strategy_version_v4_id,
    )


def _resolver(
    *,
    strategy: StrategyVersionV4,
    lookup_calls: list[UUID],
) -> StrategyArtifactResolver:
    registry = SignalSourceRegistry()
    registry.register(
        StrategyArtifactKind.EXPRESSION_V1,
        lambda _metadata: V4ExpressionSignalSource(),
    )

    def lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        lookup_calls.append(strategy_version_v4_id)
        return strategy

    return StrategyArtifactResolver(
        registry=registry,
        strategy_v4_lookup=lookup,
    )


def test_v4_deployment_returns_v4_expression_source_and_metadata() -> None:
    strategy_version_v4_id = uuid4()
    strategy_id = uuid4()
    calls: list[UUID] = []
    resolver = _resolver(
        strategy=_strategy(
            strategy_version_v4_id=strategy_version_v4_id,
            strategy_id=strategy_id,
        ),
        lookup_calls=calls,
    )

    source, metadata = resolver.resolve(
        _deployment(strategy_version_v4_id=strategy_version_v4_id)
    )

    assert isinstance(source, V4ExpressionSignalSource)
    assert metadata.kind is StrategyArtifactKind.EXPRESSION_V1
    assert metadata.strategy_version_v4_id == strategy_version_v4_id
    assert metadata.strategy_id == strategy_id
    assert calls == [strategy_version_v4_id]


def test_dual_set_deployment_prefers_v4() -> None:
    strategy_version_v4_id = uuid4()
    strategy_id = uuid4()
    calls: list[UUID] = []
    resolver = _resolver(
        strategy=_strategy(
            strategy_version_v4_id=strategy_version_v4_id,
            strategy_id=strategy_id,
        ),
        lookup_calls=calls,
    )

    source, metadata = resolver.resolve(
        _deployment(
            strategy_version_id=uuid4(),
            strategy_version_v4_id=strategy_version_v4_id,
        )
    )

    assert isinstance(source, V4ExpressionSignalSource)
    assert metadata.strategy_version_v4_id == strategy_version_v4_id
    assert metadata.strategy_id == strategy_id
    assert calls == [strategy_version_v4_id]


def test_v1_only_deployment_raises_v4_required() -> None:
    calls: list[UUID] = []
    resolver = _resolver(
        strategy=_strategy(strategy_version_v4_id=uuid4(), strategy_id=uuid4()),
        lookup_calls=calls,
    )

    with pytest.raises(StrategyArtifactResolutionError, match="V4 path required"):
        resolver.resolve(_deployment(strategy_version_id=uuid4()))

    assert calls == []


def test_deployment_without_strategy_reference_raises() -> None:
    calls: list[UUID] = []
    resolver = _resolver(
        strategy=_strategy(strategy_version_v4_id=uuid4(), strategy_id=uuid4()),
        lookup_calls=calls,
    )

    with pytest.raises(StrategyArtifactResolutionError, match="no strategy reference"):
        resolver.resolve(_deployment())

    assert calls == []


def test_server_exposes_resolver_on_app_state_dependency_surface() -> None:
    client = TestClient(server.app)

    assert client.get("/docs").status_code == 200

    request = Request({"type": "http", "app": server.app})
    assert isinstance(
        server.get_signal_source_registry(request),
        SignalSourceRegistry,
    )
    assert isinstance(
        server.get_strategy_artifact_resolver(request),
        StrategyArtifactResolver,
    )
