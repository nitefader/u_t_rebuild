"""SQLite repository for Deployment definitions. Owns its own DDL."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from backend.app.persistence.session import SQLiteSessionFactory

from .models import Deployment


SCHEMA = """
CREATE TABLE IF NOT EXISTS deployments (
    deployment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    strategy_version_id TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deployments_lifecycle_status ON deployments(lifecycle_status);
CREATE INDEX IF NOT EXISTS ix_deployments_strategy_version_id ON deployments(strategy_version_id);
"""


class DeploymentNotFoundError(LookupError):
    pass


class DeploymentRepository:
    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._session_factory.connect() as conn:
            conn.executescript(SCHEMA)

    def list_deployments(self) -> tuple[Deployment, ...]:
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM deployments ORDER BY created_at DESC"
            ).fetchall()
        return tuple(Deployment.model_validate_json(row[0]) for row in rows)

    def list_deployments_for_strategy_version(self, strategy_version_id: UUID) -> tuple[Deployment, ...]:
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM deployments WHERE strategy_version_id = ? ORDER BY created_at DESC",
                (str(strategy_version_id),),
            ).fetchall()
        return tuple(Deployment.model_validate_json(row[0]) for row in rows)

    def get_deployment(self, deployment_id: UUID) -> Deployment:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM deployments WHERE deployment_id = ?",
                (str(deployment_id),),
            ).fetchone()
        if row is None:
            raise DeploymentNotFoundError(f"deployment {deployment_id} not found")
        return Deployment.model_validate_json(row[0])

    def save_deployment(self, deployment: Deployment) -> Deployment:
        with self._session_factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO deployments(
                    deployment_id, name, strategy_version_id, lifecycle_status,
                    created_at, updated_at, payload
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deployment_id) DO UPDATE SET
                    name=excluded.name,
                    strategy_version_id=excluded.strategy_version_id,
                    lifecycle_status=excluded.lifecycle_status,
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    str(deployment.deployment_id),
                    deployment.name,
                    str(deployment.strategy_version_id),
                    deployment.lifecycle_status.value,
                    deployment.created_at.isoformat(),
                    deployment.updated_at.isoformat(),
                    deployment.model_dump_json(),
                ),
            )
        return deployment

    def delete_deployment(self, deployment_id: UUID) -> None:
        with self._session_factory.connect() as conn:
            conn.execute(
                "DELETE FROM deployments WHERE deployment_id = ?",
                (str(deployment_id),),
            )
