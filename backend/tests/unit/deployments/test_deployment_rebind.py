"""Tests for Deployment hot-swap (rebind) endpoint and binding history."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.deployments import (
    DeploymentLifecycleStatus,
    DeploymentService,
    DeploymentServiceError,
    DeploymentWriteRequest,
)
from backend.app.deployments.models import DeploymentRebindRequest
from backend.app.deployments.persistence import DeploymentRepository


@pytest.fixture()
def repo(tmp_path: Path) -> DeploymentRepository:
    return DeploymentRepository(tmp_path / "ut.db")


@pytest.fixture()
def service(repo: DeploymentRepository) -> DeploymentService:
    return DeploymentService(repository=repo)


def _make_active(service: DeploymentService) -> object:
    """Create a deployment and start it (status = ACTIVE)."""
    d = service.create_deployment(
        DeploymentWriteRequest(
            name="Test Deployment",
            strategy_version_v4_id=uuid4(),
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )
    )
    return service.start(d.deployment_id, reason="test start")


# ---------------------------------------------------------------------------
# Rebind success cases
# ---------------------------------------------------------------------------


def test_rebind_controls_only_succeeds(service: DeploymentService) -> None:
    d = _make_active(service)
    new_controls_id = uuid4()
    updated = service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(strategy_controls_version_id=new_controls_id),
    )
    assert updated.strategy_controls_version_id == new_controls_id
    assert updated.lifecycle_status == DeploymentLifecycleStatus.ACTIVE


def test_rebind_exec_plan_only_succeeds(service: DeploymentService) -> None:
    d = _make_active(service)
    new_ep_id = uuid4()
    updated = service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(execution_plan_version_id=new_ep_id),
    )
    assert updated.execution_plan_version_id == new_ep_id
    assert updated.lifecycle_status == DeploymentLifecycleStatus.ACTIVE


def test_rebind_both_succeeds(service: DeploymentService) -> None:
    d = _make_active(service)
    new_controls_id = uuid4()
    new_ep_id = uuid4()
    updated = service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(
            strategy_controls_version_id=new_controls_id,
            execution_plan_version_id=new_ep_id,
        ),
    )
    assert updated.strategy_controls_version_id == new_controls_id
    assert updated.execution_plan_version_id == new_ep_id


# ---------------------------------------------------------------------------
# Rebind validation error cases
# ---------------------------------------------------------------------------


def test_rebind_request_neither_field_raises_validation_error() -> None:
    """Pydantic should reject a request with neither FK set."""
    with pytest.raises(ValidationError):
        DeploymentRebindRequest(
            strategy_controls_version_id=None,
            execution_plan_version_id=None,
        )


def test_rebind_invalid_effective_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        DeploymentRebindRequest(
            strategy_controls_version_id=uuid4(),
            effective="not-a-datetime-or-keyword",
        )


def test_rebind_effective_now_is_valid() -> None:
    r = DeploymentRebindRequest(
        strategy_controls_version_id=uuid4(), effective="now"
    )
    assert r.effective == "now"


def test_rebind_effective_next_session_is_valid() -> None:
    r = DeploymentRebindRequest(
        strategy_controls_version_id=uuid4(), effective="next_session"
    )
    assert r.effective == "next_session"


def test_rebind_effective_iso_datetime_is_valid() -> None:
    r = DeploymentRebindRequest(
        strategy_controls_version_id=uuid4(),
        effective="2026-05-01T09:30:00+00:00",
    )
    assert r.effective == "2026-05-01T09:30:00+00:00"


# ---------------------------------------------------------------------------
# Rebind lifecycle guard
# ---------------------------------------------------------------------------


def test_rebind_rejects_draft_deployment(service: DeploymentService) -> None:
    d = service.create_deployment(
        DeploymentWriteRequest(
            name="Draft",
            strategy_version_v4_id=uuid4(),
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )
    )
    assert d.lifecycle_status == DeploymentLifecycleStatus.DRAFT
    with pytest.raises(DeploymentServiceError, match="ACTIVE"):
        service.rebind(
            d.deployment_id,
            DeploymentRebindRequest(strategy_controls_version_id=uuid4()),
        )


def test_rebind_rejects_stopped_deployment(service: DeploymentService) -> None:
    d = _make_active(service)
    service.stop(d.deployment_id, reason="stop")
    with pytest.raises(DeploymentServiceError, match="ACTIVE"):
        service.rebind(
            d.deployment_id,
            DeploymentRebindRequest(strategy_controls_version_id=uuid4()),
        )


def test_rebind_rejects_paused_deployment(service: DeploymentService) -> None:
    d = _make_active(service)
    service.pause(d.deployment_id, reason="pause")
    with pytest.raises(DeploymentServiceError, match="ACTIVE"):
        service.rebind(
            d.deployment_id,
            DeploymentRebindRequest(strategy_controls_version_id=uuid4()),
        )


# ---------------------------------------------------------------------------
# Binding history
# ---------------------------------------------------------------------------


def test_rebind_persists_history_entry(service: DeploymentService) -> None:
    d = _make_active(service)
    new_controls_id = uuid4()

    service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(
            strategy_controls_version_id=new_controls_id, effective="now"
        ),
    )

    history = service.get_binding_history(d.deployment_id)
    assert len(history.entries) == 1
    entry = history.entries[0]
    assert entry.deployment_id == d.deployment_id
    assert entry.effective == "now"
    assert entry.actor == "operator"
    assert entry.after["strategy_controls_version_id"] == str(new_controls_id)
    assert entry.before["strategy_controls_version_id"] is None


def test_history_is_newest_first(service: DeploymentService) -> None:
    d = _make_active(service)
    first_controls_id = uuid4()
    second_controls_id = uuid4()

    service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(strategy_controls_version_id=first_controls_id),
    )
    service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(strategy_controls_version_id=second_controls_id),
    )

    history = service.get_binding_history(d.deployment_id)
    assert len(history.entries) == 2
    # newest-first: second rebind should be at index 0
    assert history.entries[0].after["strategy_controls_version_id"] == str(
        second_controls_id
    )
    assert history.entries[1].after["strategy_controls_version_id"] == str(
        first_controls_id
    )


def test_history_before_after_snapshot_correct(service: DeploymentService) -> None:
    """before snapshot captures the state at swap time; after snapshot reflects
    the new values."""
    d = _make_active(service)
    old_ep_id = uuid4()
    # First rebind: set execution_plan_version_id
    service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(execution_plan_version_id=old_ep_id),
    )
    new_ep_id = uuid4()
    # Second rebind: swap to new execution_plan_version_id
    service.rebind(
        d.deployment_id,
        DeploymentRebindRequest(execution_plan_version_id=new_ep_id),
    )

    history = service.get_binding_history(d.deployment_id)
    # newest first — second rebind
    second = history.entries[0]
    assert second.before["execution_plan_version_id"] == str(old_ep_id)
    assert second.after["execution_plan_version_id"] == str(new_ep_id)


def test_history_unknown_deployment_raises(service: DeploymentService) -> None:
    with pytest.raises(DeploymentServiceError):
        service.get_binding_history(uuid4())
