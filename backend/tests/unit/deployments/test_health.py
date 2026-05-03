"""Unit tests for the M11 Guardian Deployment health predicate."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.deployments.health import (
    HEALTHY_RUNTIME_STATUSES,
    is_deployment_healthy,
    is_deployment_healthy_by_id,
)
from backend.app.deployments.models import (
    Deployment,
    DeploymentLifecycleStatus,
)
from backend.app.runtime.models import RuntimeState, RuntimeStatus


# ---------------------------------------------------------------------------
# Pure predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(RuntimeStatus))
def test_pure_predicate_only_active_lifecycle_can_ever_be_healthy(status: RuntimeStatus) -> None:
    for lifecycle in DeploymentLifecycleStatus:
        result = is_deployment_healthy(lifecycle_status=lifecycle, runtime_status=status)
        if lifecycle is not DeploymentLifecycleStatus.ACTIVE:
            assert result is False, (lifecycle, status)


@pytest.mark.parametrize("status", list(RuntimeStatus))
def test_pure_predicate_active_only_healthy_for_running_or_recovered_ready(status: RuntimeStatus) -> None:
    result = is_deployment_healthy(
        lifecycle_status=DeploymentLifecycleStatus.ACTIVE,
        runtime_status=status,
    )
    assert result is (status in HEALTHY_RUNTIME_STATUSES)


def test_healthy_set_does_not_silently_widen() -> None:
    # Locked invariant: M11 plan FR11.3 says exactly RUNNING + RECOVERED_READY.
    # If somebody adds another status, this guard fires so the operator chooses.
    assert HEALTHY_RUNTIME_STATUSES == frozenset(
        {RuntimeStatus.RUNNING, RuntimeStatus.RECOVERED_READY}
    )


# ---------------------------------------------------------------------------
# Convenience by-id wrapper (fail-closed on every error path)
# ---------------------------------------------------------------------------


class _DeploymentRepoStub:
    def __init__(
        self,
        deployment: Deployment | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self._deployment = deployment
        self._raises = raises

    def get(self, deployment_id: UUID) -> Deployment | None:  # noqa: ARG002
        if self._raises is not None:
            raise self._raises
        return self._deployment


class _RuntimeStoreStub:
    def __init__(
        self,
        state: RuntimeState | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self._state = state
        self._raises = raises

    def load_deployment_runtime_state(self, deployment_id: UUID) -> RuntimeState:
        if self._raises is not None:
            raise self._raises
        if self._state is None:
            raise KeyError(deployment_id)
        return self._state


def _make_active_deployment() -> Deployment:
    return Deployment(
        deployment_id=uuid4(),
        name="Mean Reversion Protector",
        strategy_version_v4_id=uuid4(),
        watchlist_ids=(uuid4(),),
        subscribed_account_ids=(uuid4(),),
        lifecycle_status=DeploymentLifecycleStatus.ACTIVE,
    )


def test_by_id_returns_true_when_active_and_running() -> None:
    deployment = _make_active_deployment()
    state = RuntimeState(deployment_id=deployment.deployment_id, status=RuntimeStatus.RUNNING)
    assert (
        is_deployment_healthy_by_id(
            deployment.deployment_id,
            deployments_repo=_DeploymentRepoStub(deployment),
            runtime_store=_RuntimeStoreStub(state),
        )
        is True
    )


def test_by_id_returns_true_when_active_and_recovered_ready() -> None:
    deployment = _make_active_deployment()
    state = RuntimeState(
        deployment_id=deployment.deployment_id,
        status=RuntimeStatus.RECOVERED_READY,
    )
    assert (
        is_deployment_healthy_by_id(
            deployment.deployment_id,
            deployments_repo=_DeploymentRepoStub(deployment),
            runtime_store=_RuntimeStoreStub(state),
        )
        is True
    )


@pytest.mark.parametrize(
    "status",
    [
        RuntimeStatus.READY,
        RuntimeStatus.STOPPED,
        RuntimeStatus.BLOCKED,
        RuntimeStatus.DEGRADED,
        RuntimeStatus.PAUSED,
        RuntimeStatus.KILLED,
        RuntimeStatus.ERROR,
        RuntimeStatus.BLOCKED_RECOVERY,
    ],
)
def test_by_id_returns_false_when_runtime_unhealthy(status: RuntimeStatus) -> None:
    deployment = _make_active_deployment()
    state = RuntimeState(deployment_id=deployment.deployment_id, status=status)
    assert (
        is_deployment_healthy_by_id(
            deployment.deployment_id,
            deployments_repo=_DeploymentRepoStub(deployment),
            runtime_store=_RuntimeStoreStub(state),
        )
        is False
    )


@pytest.mark.parametrize(
    "lifecycle",
    [
        DeploymentLifecycleStatus.DRAFT,
        DeploymentLifecycleStatus.PAUSED,
        DeploymentLifecycleStatus.STOPPED,
    ],
)
def test_by_id_returns_false_when_lifecycle_not_active(lifecycle: DeploymentLifecycleStatus) -> None:
    deployment = _make_active_deployment().model_copy(update={"lifecycle_status": lifecycle})
    state = RuntimeState(deployment_id=deployment.deployment_id, status=RuntimeStatus.RUNNING)
    assert (
        is_deployment_healthy_by_id(
            deployment.deployment_id,
            deployments_repo=_DeploymentRepoStub(deployment),
            runtime_store=_RuntimeStoreStub(state),
        )
        is False
    )


def test_by_id_fail_closed_when_deployment_missing() -> None:
    assert (
        is_deployment_healthy_by_id(
            uuid4(),
            deployments_repo=_DeploymentRepoStub(None),
            runtime_store=_RuntimeStoreStub(
                RuntimeState(deployment_id=uuid4(), status=RuntimeStatus.RUNNING)
            ),
        )
        is False
    )


def test_by_id_fail_closed_when_deployment_lookup_raises() -> None:
    assert (
        is_deployment_healthy_by_id(
            uuid4(),
            deployments_repo=_DeploymentRepoStub(raises=RuntimeError("db_unreachable")),
            runtime_store=_RuntimeStoreStub(
                RuntimeState(deployment_id=uuid4(), status=RuntimeStatus.RUNNING)
            ),
        )
        is False
    )


def test_by_id_fail_closed_when_runtime_state_lookup_raises() -> None:
    deployment = _make_active_deployment()
    assert (
        is_deployment_healthy_by_id(
            deployment.deployment_id,
            deployments_repo=_DeploymentRepoStub(deployment),
            runtime_store=_RuntimeStoreStub(raises=RuntimeError("runtime_store_unreachable")),
        )
        is False
    )


def test_by_id_fail_closed_when_runtime_state_missing() -> None:
    deployment = _make_active_deployment()
    assert (
        is_deployment_healthy_by_id(
            deployment.deployment_id,
            deployments_repo=_DeploymentRepoStub(deployment),
            runtime_store=_RuntimeStoreStub(None),
        )
        is False
    )
