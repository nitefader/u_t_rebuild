"""SQLite repository for StrategyControlsVersion.

Owns the ``strategy_controls_versions`` table. Rows are immutable —
operator edits create a new ``version`` for the same ``strategy_controls_id``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from backend.app.domain.strategy_controls import StrategyControlsVersion
from backend.app.persistence.session import SQLiteSessionFactory

from .models import StrategyControlsVersionRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_controls_versions (
    strategy_controls_version_id TEXT PRIMARY KEY,
    strategy_controls_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    saved_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(strategy_controls_id, version)
);
CREATE INDEX IF NOT EXISTS ix_strategy_controls_versions_strategy_controls_id
    ON strategy_controls_versions(strategy_controls_id);
"""


class StrategyControlsVersionNotFoundError(LookupError):
    pass


class StrategyControlsRepository:
    """Per-account-shared repository for StrategyControlsVersion rows."""

    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def save_version(self, version: StrategyControlsVersion) -> StrategyControlsVersionRecord:
        record = StrategyControlsVersionRecord(payload=version)
        payload_json = version.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_controls_versions(
                    strategy_controls_version_id,
                    strategy_controls_id,
                    version,
                    saved_at,
                    payload
                )
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    str(version.id),
                    str(version.strategy_controls_id),
                    version.version,
                    record.saved_at.isoformat(),
                    payload_json,
                ),
            )
        return record

    def load_version(self, strategy_controls_version_id: UUID) -> StrategyControlsVersionRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload, saved_at FROM strategy_controls_versions WHERE strategy_controls_version_id = ?",
                (str(strategy_controls_version_id),),
            ).fetchone()
        if row is None:
            raise StrategyControlsVersionNotFoundError(
                f"strategy_controls_version {strategy_controls_version_id} not found"
            )
        return self._record_from_row(row)

    def list_versions(self, strategy_controls_id: UUID) -> tuple[StrategyControlsVersionRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload, saved_at
                FROM strategy_controls_versions
                WHERE strategy_controls_id = ?
                ORDER BY version ASC
                """,
                (str(strategy_controls_id),),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def next_version_number(self, strategy_controls_id: UUID) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM strategy_controls_versions WHERE strategy_controls_id = ?",
                (str(strategy_controls_id),),
            ).fetchone()
        return int(row[0]) + 1

    def _record_from_row(self, row: tuple[str, str]) -> StrategyControlsVersionRecord:
        payload = StrategyControlsVersion.model_validate_json(row[0])
        return StrategyControlsVersionRecord.model_validate(
            {"payload": payload, "saved_at": row[1]}
        )

    def _connect(self) -> sqlite3.Connection:
        return self._session_factory.connect()
