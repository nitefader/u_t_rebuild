from __future__ import annotations

from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    IntentType,
    SignalRule,
    StrategyVersion,
)
from backend.app.deployments.models import Deployment
from backend.app.deployments.persistence import DeploymentRepository
from backend.app.strategies import StrategyService, StrategyServiceError, StrategyWriteRequest
from backend.app.strategies.models import StrategyStatus, StrategyVersionStatus
from backend.app.strategies.persistence import StrategyRepository


@pytest.fixture()
def service(tmp_path: Path) -> StrategyService:
    db_path = tmp_path / "ut.db"
    return StrategyService(
        repository=StrategyRepository(db_path),
        deployment_repository=DeploymentRepository(db_path),
    )


def _attach_deployment(tmp_path: Path, strategy_version_id) -> Deployment:
    repo = DeploymentRepository(tmp_path / "ut.db")
    return repo.save_deployment(
        Deployment(
            name="Verification Deployment",
            strategy_version_id=strategy_version_id,
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )
    )


def _payload(strategy_id, version: int = 1) -> StrategyVersion:
    rule = SignalRule(
        name="entry-rule",
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        condition=ConditionNode(
            left_feature="close",
            operator=ConditionOperator.GT,
            right_value=10.0,
        ),
    )
    return StrategyVersion(
        id=uuid4(),
        strategy_id=strategy_id,
        version=version,
        name="Test Strategy",
        feature_refs=["close"],
        entry_rules=[rule],
    )


def test_create_lists_and_gets_strategy(service: StrategyService) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Mean Reversion"))
    assert s.status == StrategyStatus.DRAFT
    listing = service.list_strategies()
    assert any(item.strategy_id == s.strategy_id for item in listing)
    detail = service.get_strategy(s.strategy_id)
    assert detail.strategy.strategy_id == s.strategy_id
    assert detail.versions == ()


def test_repository_archives_incompatible_legacy_strategy_table(tmp_path: Path) -> None:
    db_path = tmp_path / "ut.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE strategies (
                id TEXT PRIMARY KEY,
                name TEXT,
                version TEXT,
                status TEXT,
                config_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO strategies(id, name, version, status, config_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
            ("legacy-1", "Legacy", "1", "draft", "{}", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )

    service = StrategyService(repository=StrategyRepository(db_path))
    strategy = service.create_strategy(StrategyWriteRequest(name="Validated Strategy"))

    assert service.get_strategy(strategy.strategy_id).strategy.name == "Validated Strategy"


def test_freeze_version_requires_deployment(service: StrategyService, tmp_path: Path) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Trend"))
    version = service.add_version(s.strategy_id, _payload(s.strategy_id))
    assert version.version == 1
    assert version.status == StrategyVersionStatus.DRAFT

    with pytest.raises(StrategyServiceError, match="only be frozen after it is attached to a deployment"):
        service.freeze_version(version.strategy_version_id, frozen_by="operator-session-1")

    _attach_deployment(tmp_path, version.strategy_version_id)
    frozen = service.freeze_version(version.strategy_version_id, frozen_by="operator-session-1")
    assert frozen.status == StrategyVersionStatus.FROZEN
    assert frozen.frozen_at is not None
    assert frozen.frozen_by == "operator-session-1"

    detail = service.get_strategy(s.strategy_id)
    assert detail.strategy.frozen_version_ids == (version.strategy_version_id,)
    assert detail.strategy.status == StrategyStatus.ACTIVE
    assert detail.strategy.latest_version_id == version.strategy_version_id


def test_versions_increment(service: StrategyService) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Layered"))
    v1 = service.add_version(s.strategy_id, _payload(s.strategy_id, version=1))
    v2 = service.add_version(s.strategy_id, _payload(s.strategy_id, version=42))
    assert v1.version == 1
    assert v2.version == 2  # service forces sequential versioning


def test_edit_draft_version_preserves_identity_and_rejects_frozen_versions(
    service: StrategyService,
    tmp_path: Path,
) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Editable"))
    version = service.add_version(s.strategy_id, _payload(s.strategy_id))
    edited_payload = version.payload.model_copy(update={"name": "Edited Draft", "version": 99})

    edited = service.edit_version(s.strategy_id, version.strategy_version_id, edited_payload)

    assert edited.strategy_version_id == version.strategy_version_id
    assert edited.version == version.version
    assert edited.payload.name == "Edited Draft"
    assert edited.payload.version == version.version

    _attach_deployment(tmp_path, version.strategy_version_id)
    service.freeze_version(version.strategy_version_id)
    with pytest.raises(StrategyServiceError, match="frozen and cannot be edited"):
        service.edit_version(s.strategy_id, version.strategy_version_id, edited_payload)


def test_delete_blocked_when_frozen(service: StrategyService, tmp_path: Path) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Blocker"))
    v1 = service.add_version(s.strategy_id, _payload(s.strategy_id))
    _attach_deployment(tmp_path, v1.strategy_version_id)
    service.freeze_version(v1.strategy_version_id)
    with pytest.raises(StrategyServiceError):
        service.delete_strategy(s.strategy_id)


def test_delete_allowed_when_no_frozen(service: StrategyService) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Free"))
    service.add_version(s.strategy_id, _payload(s.strategy_id))
    service.delete_strategy(s.strategy_id)
    assert all(item.strategy_id != s.strategy_id for item in service.list_strategies())


def test_update_strategy_metadata(service: StrategyService) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Old"))
    updated = service.update_strategy(
        s.strategy_id,
        StrategyWriteRequest(name="New", description="renamed", tags=("alpha",)),
    )
    assert updated.name == "New"
    assert updated.description == "renamed"
    assert updated.tags == ("alpha",)


def test_get_unknown_raises(service: StrategyService) -> None:
    with pytest.raises(StrategyServiceError):
        service.get_strategy(uuid4())


def test_add_version_strategy_id_mismatch(service: StrategyService) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="One"))
    other = uuid4()
    with pytest.raises(StrategyServiceError):
        service.add_version(s.strategy_id, _payload(other))


def test_deprecate_strategy(service: StrategyService) -> None:
    s = service.create_strategy(StrategyWriteRequest(name="Stale"))
    deprecated = service.deprecate_strategy(s.strategy_id)
    assert deprecated.status == StrategyStatus.DEPRECATED
