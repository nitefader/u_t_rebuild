from __future__ import annotations

import json
import sqlite3
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
        strategy_version_v4_id=uuid4(),
        watchlist_ids=(uuid4(),),
        subscribed_account_ids=(uuid4(),),
    )


def test_create_requires_watchlist_and_account(service: DeploymentService) -> None:
    with pytest.raises(DeploymentServiceError):
        service.create_deployment(
            DeploymentWriteRequest(
                name="bad",
                strategy_version_v4_id=uuid4(),
                watchlist_ids=(),
                subscribed_account_ids=(uuid4(),),
            )
        )
    with pytest.raises(DeploymentServiceError):
        service.create_deployment(
            DeploymentWriteRequest(
                name="bad2",
                strategy_version_v4_id=uuid4(),
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


def test_create_persists_risk_horizon(service: DeploymentService) -> None:
    """Doctrine: Deployment chooses horizon. The field must round-trip through
    persistence — without this, every Deployment runs in the
    StrategyControls-fallback path and the per-horizon plan-required rule is
    never activated."""
    from backend.app.domain.strategy_controls import TradingHorizon

    request = DeploymentWriteRequest(
        name="With Horizon",
        strategy_version_v4_id=uuid4(),
        watchlist_ids=(uuid4(),),
        subscribed_account_ids=(uuid4(),),
        risk_horizon=TradingHorizon.SWING,
    )
    created = service.create_deployment(request)
    assert created.risk_horizon == TradingHorizon.SWING

    # Round-trip through repo.
    fetched = service.get_deployment(created.deployment_id).deployment
    assert fetched.risk_horizon == TradingHorizon.SWING


def test_create_omits_risk_horizon_by_default(service: DeploymentService) -> None:
    """Backwards-compat: Deployments without an explicit horizon stay None
    so the orchestrator routes through the StrategyControls fallback."""
    created = service.create_deployment(_request())
    assert created.risk_horizon is None


def test_update_can_change_risk_horizon(service: DeploymentService) -> None:
    from backend.app.domain.strategy_controls import TradingHorizon

    created = service.create_deployment(_request())
    assert created.risk_horizon is None

    updated = service.update_deployment(
        created.deployment_id,
        DeploymentWriteRequest(
            name=created.name,
            strategy_version_v4_id=created.strategy_version_v4_id,
            watchlist_ids=created.watchlist_ids,
            subscribed_account_ids=created.subscribed_account_ids,
            risk_horizon=TradingHorizon.INTRADAY,
        ),
    )
    assert updated.risk_horizon == TradingHorizon.INTRADAY


def test_start_requires_subscriptions(service: DeploymentService) -> None:
    d = service.create_deployment(_request())
    cleared = service.unsubscribe_account(d.deployment_id, d.subscribed_account_ids[0])
    assert cleared.subscribed_account_ids == ()
    with pytest.raises(DeploymentServiceError):
        service.start(d.deployment_id, reason="empty")


# ---------------------------------------------------------------------------
# v4 strategy FK tests
# ---------------------------------------------------------------------------

def test_create_with_v4_id_succeeds(service: DeploymentService) -> None:
    v4_id = uuid4()
    d = service.create_deployment(
        DeploymentWriteRequest(
            name="v4 only",
            strategy_version_v4_id=v4_id,
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )
    )
    assert d.strategy_version_v4_id == v4_id


def test_create_without_v4_id_raises() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DeploymentWriteRequest(
            name="neither",
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )


def test_v4_id_round_trips_through_persistence(service: DeploymentService) -> None:
    """strategy_version_v4_id must survive a save → load round-trip."""
    v4_id = uuid4()
    created = service.create_deployment(
        DeploymentWriteRequest(
            name="round trip",
            strategy_version_v4_id=v4_id,
            watchlist_ids=(uuid4(),),
            subscribed_account_ids=(uuid4(),),
        )
    )
    fetched = service.get_deployment(created.deployment_id).deployment
    assert fetched.strategy_version_v4_id == v4_id


def test_repository_schema_init_drops_legacy_strategy_version_column(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    deployment_id = uuid4()
    v4_id = uuid4()
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE deployments (
                deployment_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                strategy_version_id TEXT,
                lifecycle_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX ix_deployments_strategy_version_id "
            "ON deployments(strategy_version_id)"
        )
        payload = {
            "deployment_id": str(deployment_id),
            "name": "Legacy payload row",
            "strategy_version_id": str(uuid4()),
            "strategy_version_v4_id": str(v4_id),
        }
        conn.execute(
            """
            INSERT INTO deployments (
                deployment_id, name, strategy_version_id, lifecycle_status,
                created_at, updated_at, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(deployment_id),
                "Legacy payload row",
                str(uuid4()),
                "draft",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
                json.dumps(payload),
            ),
        )

    repo = DeploymentRepository(db)

    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(deployments)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(deployments)")}
    assert "strategy_version_id" not in columns
    assert "ix_deployments_strategy_version_id" not in indexes
    fetched = repo.get_deployment(deployment_id)
    assert fetched.strategy_version_v4_id == v4_id
