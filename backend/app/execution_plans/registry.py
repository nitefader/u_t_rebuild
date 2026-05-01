"""Sidecar SQLite repository for ExecutionPlan library metadata.

Owns the ``execution_plan_registry`` table on the same DB as
``ExecutionPlanRepository``. Rows are mutable — name, is_default,
and retired_at can change over the lifetime of a library.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from backend.app.persistence.session import SQLiteSessionFactory


SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_plan_registry (
    execution_plan_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    retired_at TEXT
);
"""


class ExecutionPlanRegistryNotFoundError(LookupError):
    pass


class ExecutionPlanRegistryRecord:
    __slots__ = ("execution_plan_id", "name", "is_default", "retired_at")

    def __init__(
        self,
        *,
        execution_plan_id: UUID,
        name: str,
        is_default: bool,
        retired_at: datetime | None,
    ) -> None:
        self.execution_plan_id = execution_plan_id
        self.name = name
        self.is_default = is_default
        self.retired_at = retired_at


class ExecutionPlanRegistry:
    """Metadata sidecar for ExecutionPlan libraries."""

    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._session_factory.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_name(self, execution_plan_id: UUID, name: str) -> None:
        with self._session_factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_plan_registry(execution_plan_id, name, is_default, retired_at)
                VALUES(?, ?, 0, NULL)
                ON CONFLICT(execution_plan_id) DO UPDATE SET name = excluded.name
                """,
                (str(execution_plan_id), name),
            )

    def get(self, execution_plan_id: UUID) -> ExecutionPlanRegistryRecord:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT execution_plan_id, name, is_default, retired_at FROM execution_plan_registry WHERE execution_plan_id = ?",
                (str(execution_plan_id),),
            ).fetchone()
        if row is None:
            raise ExecutionPlanRegistryNotFoundError(
                f"execution_plan_id {execution_plan_id} not found in registry"
            )
        return self._record_from_row(row)

    def list_all(self) -> list[ExecutionPlanRegistryRecord]:
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                "SELECT execution_plan_id, name, is_default, retired_at FROM execution_plan_registry ORDER BY name ASC"
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def set_default(self, execution_plan_id: UUID) -> None:
        with self._session_factory.connect() as conn:
            conn.execute("UPDATE execution_plan_registry SET is_default = 0")
            conn.execute(
                "UPDATE execution_plan_registry SET is_default = 1 WHERE execution_plan_id = ?",
                (str(execution_plan_id),),
            )

    def mark_retired(self, execution_plan_id: UUID) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._session_factory.connect() as conn:
            conn.execute(
                "UPDATE execution_plan_registry SET retired_at = ? WHERE execution_plan_id = ?",
                (now, str(execution_plan_id)),
            )

    def is_retired(self, execution_plan_id: UUID) -> bool:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT retired_at FROM execution_plan_registry WHERE execution_plan_id = ?",
                (str(execution_plan_id),),
            ).fetchone()
        if row is None:
            return False
        return row[0] is not None

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> ExecutionPlanRegistryRecord:
        retired_at: datetime | None = None
        if row["retired_at"] is not None:
            retired_at = datetime.fromisoformat(row["retired_at"])
        return ExecutionPlanRegistryRecord(
            execution_plan_id=UUID(row["execution_plan_id"]),
            name=row["name"],
            is_default=bool(row["is_default"]),
            retired_at=retired_at,
        )
