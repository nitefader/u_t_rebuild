"""SQLite repository for Deployment definitions. Owns its own DDL."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from backend.app.persistence.session import SQLiteSessionFactory

from .models import Deployment, DeploymentBindingHistoryEntry


SCHEMA = """
CREATE TABLE IF NOT EXISTS deployments (
    deployment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    strategy_version_id TEXT,
    lifecycle_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deployments_lifecycle_status ON deployments(lifecycle_status);
CREATE INDEX IF NOT EXISTS ix_deployments_strategy_version_id ON deployments(strategy_version_id);

CREATE TABLE IF NOT EXISTS deployment_binding_history (
    entry_id TEXT PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    effective TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_deployment_binding_history_deployment_id
    ON deployment_binding_history(deployment_id);
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
        # strategy_version_id column may be NULL for v4-only deployments.
        legacy_sv_id = (
            str(deployment.strategy_version_id)
            if deployment.strategy_version_id is not None
            else None
        )
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
                    legacy_sv_id,
                    deployment.lifecycle_status.value,
                    deployment.created_at.isoformat(),
                    deployment.updated_at.isoformat(),
                    deployment.model_dump_json(),
                ),
            )
        return deployment

    def list_deployments_for_strategy_controls_versions(
        self, strategy_controls_version_ids: set[UUID]
    ) -> tuple[Deployment, ...]:
        """Return deployments whose strategy_controls_version_id is in the given set.

        The strategy_controls_version_id lives in the JSON payload (not a
        deduplicated column), so this performs an in-process filter. Deployment
        volumes are small enough that a full scan is correct and safe here.
        """
        if not strategy_controls_version_ids:
            return ()
        all_deps = self.list_deployments()
        id_strings = {str(v) for v in strategy_controls_version_ids}
        return tuple(
            d
            for d in all_deps
            if d.strategy_controls_version_id is not None
            and str(d.strategy_controls_version_id) in id_strings
        )

    def list_deployments_for_execution_plan_versions(
        self, execution_plan_version_ids: set[UUID]
    ) -> tuple[Deployment, ...]:
        """Return deployments whose execution_plan_version_id is in the given set.

        The execution_plan_version_id lives in the JSON payload (not a
        deduplicated column), so this performs an in-process filter. Deployment
        volumes are small enough that a full scan is correct and safe here.
        """
        if not execution_plan_version_ids:
            return ()
        all_deps = self.list_deployments()
        id_strings = {str(v) for v in execution_plan_version_ids}
        return tuple(
            d
            for d in all_deps
            if d.execution_plan_version_id is not None
            and str(d.execution_plan_version_id) in id_strings
        )

    def list_deployments_for_strategy_v4_versions(
        self, strategy_v4_version_ids: set[UUID]
    ) -> tuple[Deployment, ...]:
        """Return deployments whose strategy_version_v4_id is in the given set.

        The strategy_version_v4_id lives in the JSON payload (not a
        deduplicated column), so this performs an in-process filter. Deployment
        volumes are small enough that a full scan is correct and safe here.
        """
        if not strategy_v4_version_ids:
            return ()
        all_deps = self.list_deployments()
        id_strings = {str(v) for v in strategy_v4_version_ids}
        return tuple(
            d
            for d in all_deps
            if d.strategy_version_v4_id is not None
            and str(d.strategy_version_v4_id) in id_strings
        )

    def delete_deployment(self, deployment_id: UUID) -> None:
        with self._session_factory.connect() as conn:
            conn.execute(
                "DELETE FROM deployments WHERE deployment_id = ?",
                (str(deployment_id),),
            )

    # ------------------------------------------------------------------
    # Binding history
    # ------------------------------------------------------------------

    def save_binding_history(self, entry: DeploymentBindingHistoryEntry) -> None:
        with self._session_factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO deployment_binding_history(
                    entry_id, deployment_id, timestamp, actor,
                    before_json, after_json, effective
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(entry.entry_id),
                    str(entry.deployment_id),
                    entry.timestamp.isoformat(),
                    entry.actor,
                    json.dumps(entry.before),
                    json.dumps(entry.after),
                    entry.effective,
                ),
            )

    def list_binding_history(
        self, deployment_id: UUID
    ) -> tuple[DeploymentBindingHistoryEntry, ...]:
        """Return history entries for a deployment, newest-first."""
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                """
                SELECT entry_id, deployment_id, timestamp, actor,
                       before_json, after_json, effective
                FROM deployment_binding_history
                WHERE deployment_id = ?
                ORDER BY timestamp DESC
                """,
                (str(deployment_id),),
            ).fetchall()
        results = []
        for row in rows:
            raw_ts = row[2]
            if raw_ts.endswith("+00:00") or raw_ts.endswith("Z"):
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            else:
                ts = datetime.fromisoformat(raw_ts).replace(tzinfo=timezone.utc)
            results.append(
                DeploymentBindingHistoryEntry(
                    entry_id=UUID(row[0]),
                    deployment_id=UUID(row[1]),
                    timestamp=ts,
                    actor=row[3],
                    before=json.loads(row[4]),
                    after=json.loads(row[5]),
                    effective=row[6],
                )
            )
        return tuple(results)
