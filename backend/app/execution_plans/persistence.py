"""SQLite repository for ExecutionPlanVersion.

Owns the ``execution_plan_versions`` table. Rows are immutable —
operator edits create a new ``version`` for the same ``execution_plan_id``.
The ``execution_plan_id`` is stored as the legacy ``execution_style_id``
column on the persisted payload (see decision D3 in the program MAP).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from backend.app.domain.execution_style import ExecutionStyleVersion
from backend.app.persistence.session import SQLiteSessionFactory

from .models import ExecutionPlanVersionRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_plan_versions (
    execution_plan_version_id TEXT PRIMARY KEY,
    execution_plan_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    saved_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(execution_plan_id, version)
);
CREATE INDEX IF NOT EXISTS ix_execution_plan_versions_execution_plan_id
    ON execution_plan_versions(execution_plan_id);
"""


class ExecutionPlanVersionNotFoundError(LookupError):
    pass


class ExecutionPlanRepository:
    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save_version(self, version: ExecutionStyleVersion) -> ExecutionPlanVersionRecord:
        record = ExecutionPlanVersionRecord(payload=version)
        payload_json = version.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_plan_versions(
                    execution_plan_version_id,
                    execution_plan_id,
                    version,
                    saved_at,
                    payload
                )
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    str(version.id),
                    str(version.execution_style_id),
                    version.version,
                    record.saved_at.isoformat(),
                    payload_json,
                ),
            )
        return record

    def load_version(self, execution_plan_version_id: UUID) -> ExecutionPlanVersionRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, saved_at FROM execution_plan_versions WHERE execution_plan_version_id = ?",
                (str(execution_plan_version_id),),
            ).fetchone()
        if row is None:
            raise ExecutionPlanVersionNotFoundError(
                f"execution_plan_version {execution_plan_version_id} not found"
            )
        return self._record_from_row(row)

    def list_versions(self, execution_plan_id: UUID) -> tuple[ExecutionPlanVersionRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload, saved_at
                FROM execution_plan_versions
                WHERE execution_plan_id = ?
                ORDER BY version ASC
                """,
                (str(execution_plan_id),),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def next_version_number(self, execution_plan_id: UUID) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM execution_plan_versions WHERE execution_plan_id = ?",
                (str(execution_plan_id),),
            ).fetchone()
        return int(row[0]) + 1

    def _record_from_row(self, row: tuple[str, str]) -> ExecutionPlanVersionRecord:
        payload = ExecutionStyleVersion.model_validate_json(row[0])
        return ExecutionPlanVersionRecord.model_validate(
            {"payload": payload, "saved_at": row[1]}
        )

    def _connect(self) -> sqlite3.Connection:
        return self._session_factory.connect()
