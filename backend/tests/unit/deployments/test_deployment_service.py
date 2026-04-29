from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.deployments import (
    DeploymentLifecycleStatus,
    DeploymentService,
    DeploymentServiceError,
    DeploymentWriteRequest,
)
from backend.app.deployments.persistence import DeploymentRepository


@pytest.fixture()
def service(tmp_path: Path) -> DeploymentService:
    return DeploymentService(repository=DeploymentRepository(tmp_path / "ut.db"))


def _request(name: str = "Test Deployment") -> DeploymentWriteRequest:
    return DeploymentWriteRequest(
        name=name,
        strategy_version_id=uuid4(),
        watchlist_ids=(uuid4(),),
        subscribed_account_ids=(uuid4(),),
    )


def test_create_requires_watchlist_and_account(service: DeploymentService) -> None:
    with pytest.raises(DeploymentServiceError):
        service.create_deployment(
            DeploymentWriteRequest(
                name="bad",
                strategy_version_id=uuid4(),
                watchlist_ids=(),
                subscribed_account_ids=(uuid4(),),
            )
        )
    with pytest.raises(DeploymentServiceError):
        service.create_deployment(
            DeploymentWriteRequest(
                name="bad2",
                strategy_version_id=uuid4(),
                watchlist_ids=(uuid4(),),
                subscribed_account_ids=(),
            )
        )


def test_create_and_lifecycle(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    assert d.lifecycle_status == DeploymentLifecycleStatus.DRAFT

    started = service.start(d.deployment_id, reason="initial start")
    assert started.lifecycle_status == DeploymentLifecycleStatus.ACTIVE
    assert started.started_at is not None

    paused = service.pause(d.deployment_id, reason="operator pause")
    assert paused.lifecycle_status == DeploymentLifecycleStatus.PAUSED

    resumed = service.resume(d.deployment_id, reason="operator resume")
    assert resumed.lifecycle_status == DeploymentLifecycleStatus.ACTIVE

    stopped = service.stop(d.deployment_id, reason="end of session")
    assert stopped.lifecycle_status == DeploymentLifecycleStatus.STOPPED
    assert stopped.stopped_at is not None


def test_resume_fails_when_not_paused(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    with pytest.raises(DeploymentServiceError):
        service.resume(d.deployment_id, reason="invalid")


def test_subscribe_unsubscribe(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    new_account = uuid4()
    after_sub = service.subscribe_account(d.deployment_id, new_account)
    assert new_account in after_sub.subscribed_account_ids

    # Idempotent
    again = service.subscribe_account(d.deployment_id, new_account)
    assert again.subscribed_account_ids.count(new_account) == 1

    after_unsub = service.unsubscribe_account(d.deployment_id, new_account)
    assert new_account not in after_unsub.subscribed_account_ids


def test_update_blocked_when_active(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    service.start(d.deployment_id, reason="active")
    with pytest.raises(DeploymentServiceError):
        service.update_deployment(
            d.deployment_id,
            _request(name="renamed-while-active"),
        )


def test_delete_requires_draft_or_stopped(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    service.start(d.deployment_id, reason="active")
    with pytest.raises(DeploymentServiceError):
        service.delete_deployment(d.deployment_id)
    service.stop(d.deployment_id, reason="end")
    service.delete_deployment(d.deployment_id)


def test_get_unknown_raises(service: DeploymentService) -> None:
    with pytest.raises(DeploymentServiceError):
        service.get_deployment(uuid4())


def test_start_requires_subscriptions(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    cleared = service.unsubscribe_account(d.deployment_id, d.subscribed_account_ids[0])
    assert cleared.subscribed_account_ids == ()
    with pytest.raises(DeploymentServiceError):
        service.start(d.deployment_id, reason="empty")
