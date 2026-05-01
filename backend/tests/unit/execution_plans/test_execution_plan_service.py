"""Unit tests for ExecutionPlanService."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.deployments.models import Deployment, DeploymentLifecycleStatus
from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain.execution_style import ExecutionMode, OrderType, TimeInForce
from backend.app.execution_plans.persistence import ExecutionPlanRepository
from backend.app.execution_plans.registry import ExecutionPlanRegistry
from backend.app.execution_plans.service import (
    ExecutionPlanBoundError,
    ExecutionPlanNotFoundError,
    ExecutionPlanService,
)
from backend.app.execution_plans.service_models import ExecutionPlanDraft


def _make_service(tmp_path: Path) -> ExecutionPlanService:
    db = tmp_path / "test.db"
    return ExecutionPlanService(
        repository=ExecutionPlanRepository(db),
        registry=ExecutionPlanRegistry(db),
        deployment_repository=DeploymentRepository(db),
    )


def _make_draft(name: str = "My Profile") -> ExecutionPlanDraft:
    return ExecutionPlanDraft(
        name=name,
        entry_order_type=OrderType.MARKET,
        exit_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
    )


def _make_deployment(execution_plan_version_id=None) -> Deployment:
    return Deployment(
        deployment_id=uuid4(),
        name="Test Deployment",
        strategy_version_id=uuid4(),
        execution_plan_version_id=execution_plan_version_id,
        lifecycle_status=DeploymentLifecycleStatus.DRAFT,
    )


# ------------------------------------------------------------------
# create
# ------------------------------------------------------------------


def test_create_returns_version_1(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _make_draft()
    record = svc.create(draft.name, draft)
    assert record.payload.version == 1
    assert record.payload.name == "My Profile"
    assert record.payload.entry_order_type == OrderType.MARKET


def test_create_appears_in_list(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _make_draft("Alpha")
    svc.create(draft.name, draft)
    libraries = svc.list_libraries()
    assert len(libraries) == 1
    assert libraries[0].name == "Alpha"
    assert libraries[0].head_version_number == 1
    assert libraries[0].is_default is False
    assert libraries[0].usage_count == 0


# ------------------------------------------------------------------
# edit bumps version
# ------------------------------------------------------------------


def test_edit_bumps_version(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _make_draft()
    record_v1 = svc.create(draft.name, draft)
    ep_id = record_v1.payload.execution_style_id

    draft2 = _make_draft("My Profile Updated")
    record_v2 = svc.edit(ep_id, draft2)

    assert record_v2.payload.version == 2
    assert record_v2.payload.name == "My Profile Updated"
    assert record_v2.payload.execution_style_id == ep_id

    library = svc.get_library(ep_id)
    assert library.head.payload.version == 2
    assert len(library.history) == 2


# ------------------------------------------------------------------
# duplicate clones fields
# ------------------------------------------------------------------


def test_duplicate_clones_fields(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _make_draft("Original")
    record = svc.create(draft.name, draft)

    dup = svc.duplicate(record.payload.id, "Copy of Original")

    assert dup.payload.version == 1
    assert dup.payload.name == "Copy of Original"
    assert dup.payload.execution_style_id != record.payload.execution_style_id
    assert dup.payload.entry_order_type == record.payload.entry_order_type
    assert dup.payload.execution_mode == record.payload.execution_mode

    libraries = svc.list_libraries()
    assert len(libraries) == 2


# ------------------------------------------------------------------
# retire
# ------------------------------------------------------------------


def test_retire_succeeds_when_unbound(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _make_draft()
    record = svc.create(draft.name, draft)
    ep_id = record.payload.execution_style_id

    svc.retire(ep_id)

    libraries = svc.list_libraries()
    assert libraries[0].retired_at is not None


def test_retire_blocks_when_bound(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    svc = ExecutionPlanService(
        repository=ExecutionPlanRepository(db),
        registry=ExecutionPlanRegistry(db),
        deployment_repository=DeploymentRepository(db),
    )
    draft = _make_draft()
    record = svc.create(draft.name, draft)
    ep_id = record.payload.execution_style_id

    dep = _make_deployment(execution_plan_version_id=record.payload.id)
    DeploymentRepository(db).save_deployment(dep)

    with pytest.raises(ExecutionPlanBoundError) as exc_info:
        svc.retire(ep_id)

    assert dep.deployment_id in exc_info.value.deployment_ids


# ------------------------------------------------------------------
# set_default is exclusive
# ------------------------------------------------------------------


def test_set_default_is_exclusive(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    d1 = _make_draft("First")
    d2 = _make_draft("Second")
    r1 = svc.create(d1.name, d1)
    r2 = svc.create(d2.name, d2)

    svc.set_default(r1.payload.execution_style_id)
    libraries = svc.list_libraries()
    defaults = [lib for lib in libraries if lib.is_default]
    assert len(defaults) == 1
    assert defaults[0].execution_plan_id == r1.payload.execution_style_id

    svc.set_default(r2.payload.execution_style_id)
    libraries2 = svc.list_libraries()
    defaults2 = [lib for lib in libraries2 if lib.is_default]
    assert len(defaults2) == 1
    assert defaults2[0].execution_plan_id == r2.payload.execution_style_id


# ------------------------------------------------------------------
# used_by returns deployment ids
# ------------------------------------------------------------------


def test_used_by_returns_deployment_ids(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    svc = ExecutionPlanService(
        repository=ExecutionPlanRepository(db),
        registry=ExecutionPlanRegistry(db),
        deployment_repository=DeploymentRepository(db),
    )
    draft = _make_draft()
    record = svc.create(draft.name, draft)
    ep_id = record.payload.execution_style_id

    dep1 = _make_deployment(execution_plan_version_id=record.payload.id)
    dep2 = _make_deployment(execution_plan_version_id=record.payload.id)
    dep_unrelated = _make_deployment(execution_plan_version_id=None)
    dep_repo = DeploymentRepository(db)
    dep_repo.save_deployment(dep1)
    dep_repo.save_deployment(dep2)
    dep_repo.save_deployment(dep_unrelated)

    response = svc.used_by(ep_id)
    assert set(response.deployment_ids) == {dep1.deployment_id, dep2.deployment_id}


# ------------------------------------------------------------------
# get_library returns head and history
# ------------------------------------------------------------------


def test_get_library_returns_head_and_history(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _make_draft()
    r1 = svc.create(draft.name, draft)
    ep_id = r1.payload.execution_style_id

    draft2 = _make_draft("Updated")
    svc.edit(ep_id, draft2)

    library = svc.get_library(ep_id)
    assert library.head.payload.version == 2
    assert len(library.history) == 2
    assert [h.version for h in library.history] == [1, 2]


def test_get_library_raises_for_unknown_id(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    with pytest.raises(ExecutionPlanNotFoundError):
        svc.get_library(uuid4())


# ------------------------------------------------------------------
# Deployment binding lookup (new persistence method)
# ------------------------------------------------------------------


def test_deployment_repo_list_for_execution_plan_versions(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    dep_repo = DeploymentRepository(db)
    epv_id = uuid4()
    epv_id2 = uuid4()

    dep1 = _make_deployment(execution_plan_version_id=epv_id)
    dep2 = _make_deployment(execution_plan_version_id=epv_id)
    dep_other = _make_deployment(execution_plan_version_id=epv_id2)
    dep_none = _make_deployment(execution_plan_version_id=None)

    for d in (dep1, dep2, dep_other, dep_none):
        dep_repo.save_deployment(d)

    result = dep_repo.list_deployments_for_execution_plan_versions({epv_id})
    assert {d.deployment_id for d in result} == {dep1.deployment_id, dep2.deployment_id}

    result2 = dep_repo.list_deployments_for_execution_plan_versions({epv_id, epv_id2})
    assert {d.deployment_id for d in result2} == {
        dep1.deployment_id,
        dep2.deployment_id,
        dep_other.deployment_id,
    }

    result_empty = dep_repo.list_deployments_for_execution_plan_versions(set())
    assert result_empty == ()
