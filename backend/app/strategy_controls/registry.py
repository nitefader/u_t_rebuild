"""Sidecar SQLite repository for StrategyControls library metadata.

Owns the ``strategy_controls_registry`` table on the same DB as
``StrategyControlsRepository``. Rows are mutable — name, is_default,
and retired_at can change over the lifetime of a library.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from backend.app.persistence.session import SQLiteSessionFactory


SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_controls_registry (
    strategy_controls_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    retired_at TEXT
);
"""


class StrategyControlsRegistryNotFoundError(LookupError):
    pass


class StrategyControlsRegistryRecord:
    __slots__ = ("strategy_controls_id", "name", "is_default", "retired_at")

    def __init__(
        self,
        *,
        strategy_controls_id: UUID,
        name: str,
        is_default: bool,
        retired_at: datetime | None,
    ) -> None:
        self.strategy_controls_id = strategy_controls_id
        self.name = name
        self.is_default = is_default
        self.retired_at = retired_at


class StrategyControlsRegistry:
    """Metadata sidecar for StrategyControls libraries."""

    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._session_factory.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_name(self, strategy_controls_id: UUID, name: str) -> None:
        with self._session_factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_controls_registry(strategy_controls_id, name, is_default, retired_at)
                VALUES(?, ?, 0, NULL)
                ON CONFLICT(strategy_controls_id) DO UPDATE SET name = excluded.name
                """,
                (str(strategy_controls_id), name),
            )

    def get(self, strategy_controls_id: UUID) -> StrategyControlsRegistryRecord:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT strategy_controls_id, name, is_default, retired_at FROM strategy_controls_registry WHERE strategy_controls_id = ?",
                (str(strategy_controls_id),),
            ).fetchone()
        if row is None:
            raise StrategyControlsRegistryNotFoundError(
                f"strategy_controls_id {strategy_controls_id} not found in registry"
            )
        return self._record_from_row(row)

    def list_all(self) -> list[StrategyControlsRegistryRecord]:
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                "SELECT strategy_controls_id, name, is_default, retired_at FROM strategy_controls_registry ORDER BY name ASC"
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def set_default(self, strategy_controls_id: UUID) -> None:
        with self._session_factory.connect() as conn:
            conn.execute("UPDATE strategy_controls_registry SET is_default = 0")
            conn.execute(
                "UPDATE strategy_controls_registry SET is_default = 1 WHERE strategy_controls_id = ?",
                (str(strategy_controls_id),),
            )

    def mark_retired(self, strategy_controls_id: UUID) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._session_factory.connect() as conn:
            conn.execute(
                "UPDATE strategy_controls_registry SET retired_at = ? WHERE strategy_controls_id = ?",
                (now, str(strategy_controls_id)),
            )

    def is_retired(self, strategy_controls_id: UUID) -> bool:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT retired_at FROM strategy_controls_registry WHERE strategy_controls_id = ?",
                (str(strategy_controls_id),),
            ).fetchone()
        if row is None:
            return False
        return row[0] is not None

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> StrategyControlsRegistryRecord:
        retired_at: datetime | None = None
        if row["retired_at"] is not None:
            retired_at = datetime.fromisoformat(row["retired_at"])
        return StrategyControlsRegistryRecord(
            strategy_controls_id=UUID(row["strategy_controls_id"]),
            name=row["name"],
            is_default=bool(row["is_default"]),
            retired_at=retired_at,
        )
