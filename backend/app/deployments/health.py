"""Deployment health predicate (M11 Guardian Assignment).

`is_deployment_healthy` is the single source of truth for "can this
Deployment safely manage its positions right now?" — used by the
Guardian adoption pathway in `backend/app/brokers/sync.py` to decide
whether the original owner is alive or whether Guardian should adopt.

Two layers of state combine into healthy:
- `DeploymentLifecycleStatus.ACTIVE` — operator lever (operator
  intentionally enabled this Deployment).
- `RuntimeStatus in {RUNNING, RECOVERED_READY}` — system lever (the
  runtime is actually executing; not BLOCKED, ERROR, KILLED, PAUSED,
  STOPPED, DEGRADED, etc.).

Per operator decision (plan file
`strategy-builder-must-only-abundant-allen.md` plan-review #3+#4):
PAUSED/STOPPED/BLOCKED/ERROR/KILLED/DEGRADED all return False. Pausing
a Deployment with self-protected positions does NOT trigger Guardian
adoption — that's enforced separately by
`BrokerSync.position_has_active_protective_orders` (FR11.4 case 4).
This predicate is purely about the Deployment, not the position.

The `*_by_id` convenience does the lookup; the bare predicate stays
pure for trivial unit testing and call-site reuse.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from backend.app.deployments.models import Deployment, DeploymentLifecycleStatus
from backend.app.runtime.models import RuntimeState, RuntimeStatus


HEALTHY_RUNTIME_STATUSES: frozenset[RuntimeStatus] = frozenset(
    {RuntimeStatus.RUNNING, RuntimeStatus.RECOVERED_READY}
)


class _DeploymentRepo(Protocol):
    def get(self, deployment_id: UUID) -> Deployment | None: ...


class _RuntimeStateRepo(Protocol):
    def load_deployment_runtime_state(self, deployment_id: UUID) -> RuntimeState: ...


def is_deployment_healthy(
    *,
    lifecycle_status: DeploymentLifecycleStatus,
    runtime_status: RuntimeStatus,
) -> bool:
    """Pure predicate — both arguments required, no I/O."""
    return (
        lifecycle_status == DeploymentLifecycleStatus.ACTIVE
        and runtime_status in HEALTHY_RUNTIME_STATUSES
    )


def is_deployment_healthy_by_id(
    deployment_id: UUID,
    *,
    deployments_repo: _DeploymentRepo,
    runtime_store: _RuntimeStateRepo,
) -> bool:
    """Convenience that fetches deployment + runtime state and combines.

    Returns False fail-closed when either lookup raises or returns None.
    Callers in the Guardian adoption path expect a single bool — they
    do not care to distinguish "missing record" from "explicitly
    unhealthy"; both should suppress adoption.
    """
    try:
        deployment = deployments_repo.get(deployment_id)
    except Exception:  # noqa: BLE001 - fail-closed
        return False
    if deployment is None:
        return False
    try:
        runtime_state = runtime_store.load_deployment_runtime_state(deployment_id)
    except Exception:  # noqa: BLE001 - fail-closed
        return False
    return is_deployment_healthy(
        lifecycle_status=deployment.lifecycle_status,
        runtime_status=runtime_state.status,
    )
