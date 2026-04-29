"""SQLite repository for Strategies.

This module owns its own DDL (idempotent CREATE-IF-NOT-EXISTS) so the
package does not modify ``backend.app.persistence.runtime_store`` —
that file is owned by the Operation Turtle Shell coordinator. Both
files share the same SQLite database so reads/writes interleave
safely.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

from backend.app.domain import StrategyVersion
from backend.app.domain._base import utc_now
from backend.app.persistence.session import SQLiteSessionFactory

from .models import Strategy, StrategyStatus, StrategyVersionRecord, StrategyVersionStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    strategy_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_strategies_status ON strategies(status);
CREATE INDEX IF NOT EXISTS ix_strategies_name ON strategies(name);

CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_version_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    frozen_at TEXT,
    payload TEXT NOT NULL,
    UNIQUE(strategy_id, version)
);
CREATE INDEX IF NOT EXISTS ix_strategy_versions_strategy_id ON strategy_versions(strategy_id);
CREATE INDEX IF NOT EXISTS ix_strategy_versions_status ON strategy_versions(status);
"""


class StrategyNotFoundError(LookupError):
    pass


class StrategyVersionNotFoundError(LookupError):
    pass


class StrategyRepository:
    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._connect() as conn:
            self._archive_incompatible_legacy_schema(conn)
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------
    # Strategy CRUD
    # ------------------------------------------------------------------

    def list_strategies(self) -> tuple[Strategy, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM strategies ORDER BY created_at DESC"
            ).fetchall()
        return tuple(self._strategy_from_row(row) for row in rows)

    def get_strategy(self, strategy_id: UUID) -> Strategy:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM strategies WHERE strategy_id = ?",
                (str(strategy_id),),
            ).fetchone()
        if row is None:
            raise StrategyNotFoundError(f"strategy {strategy_id} not found")
        return self._strategy_from_row(row)

    def save_strategy(self, strategy: Strategy) -> Strategy:
        payload = strategy.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategies(strategy_id, name, status, created_at, payload)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    name=excluded.name,
                    status=excluded.status,
                    payload=excluded.payload
                """,
                (
                    str(strategy.strategy_id),
                    strategy.name,
                    strategy.status.value,
                    strategy.created_at.isoformat(),
                    payload,
                ),
            )
        return strategy

    def delete_strategy(self, strategy_id: UUID) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM strategy_versions WHERE strategy_id = ?",
                (str(strategy_id),),
            )
            conn.execute(
                "DELETE FROM strategies WHERE strategy_id = ?",
                (str(strategy_id),),
            )

    # ------------------------------------------------------------------
    # Version CRUD
    # ------------------------------------------------------------------

    def list_versions(self, strategy_id: UUID) -> tuple[StrategyVersionRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM strategy_versions WHERE strategy_id = ? ORDER BY version ASC",
                (str(strategy_id),),
            ).fetchall()
        return tuple(self._version_from_row(row) for row in rows)

    def get_version(self, strategy_version_id: UUID) -> StrategyVersionRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM strategy_versions WHERE strategy_version_id = ?",
                (str(strategy_version_id),),
            ).fetchone()
        if row is None:
            raise StrategyVersionNotFoundError(f"strategy version {strategy_version_id} not found")
        return self._version_from_row(row)

    def save_version(self, version: StrategyVersionRecord) -> StrategyVersionRecord:
        payload = version.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_versions(
                    strategy_version_id, strategy_id, version, status, created_at, frozen_at, payload
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_version_id) DO UPDATE SET
                    status=excluded.status,
                    frozen_at=excluded.frozen_at,
                    payload=excluded.payload
                """,
                (
                    str(version.strategy_version_id),
                    str(version.strategy_id),
                    version.version,
                    version.status.value,
                    version.created_at.isoformat(),
                    version.frozen_at.isoformat() if version.frozen_at is not None else None,
                    payload,
                ),
            )
        return version

    def next_version_number(self, strategy_id: UUID) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM strategy_versions WHERE strategy_id = ?",
                (str(strategy_id),),
            ).fetchone()
        return int(row[0]) + 1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _strategy_from_row(self, row: tuple[str]) -> Strategy:
        return Strategy.model_validate_json(row[0])

    def _version_from_row(self, row: tuple[str]) -> StrategyVersionRecord:
        return StrategyVersionRecord.model_validate_json(row[0])

    def _connect(self) -> sqlite3.Connection:
        return self._session_factory.connect()

    def _archive_incompatible_legacy_schema(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'strategies'"
        ).fetchone()
        if row is None:
            return
        columns = {column[1] for column in conn.execute("PRAGMA table_info(strategies)").fetchall()}
        if {"strategy_id", "payload"}.issubset(columns):
            return
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        conn.execute(f"ALTER TABLE strategies RENAME TO strategies_legacy_{suffix}")


# ---------------------------------------------------------------------------
# Public helpers used by the service layer
# ---------------------------------------------------------------------------


def build_version_record(
    *,
    strategy_id: UUID,
    version_number: int,
    payload: StrategyVersion,
    status: StrategyVersionStatus = StrategyVersionStatus.DRAFT,
) -> StrategyVersionRecord:
    return StrategyVersionRecord(
        strategy_version_id=payload.id,
        strategy_id=strategy_id,
        version=version_number,
        status=status,
        payload=payload,
        frozen_at=None,
        created_at=utc_now(),
    )


def derive_strategy_aggregates(strategy: Strategy, versions: tuple[StrategyVersionRecord, ...]) -> Strategy:
    if not versions:
        return strategy.model_copy(
            update={
                "latest_version_id": None,
                "frozen_version_ids": (),
                "version_count": 0,
                "status": StrategyStatus.DRAFT if strategy.status == StrategyStatus.DRAFT else strategy.status,
            }
        )
    latest = max(versions, key=lambda v: v.version)
    frozen = tuple(v.strategy_version_id for v in versions if v.status == StrategyVersionStatus.FROZEN)
    new_status = strategy.status
    if frozen and strategy.status == StrategyStatus.DRAFT:
        new_status = StrategyStatus.ACTIVE
    return strategy.model_copy(
        update={
            "latest_version_id": latest.strategy_version_id,
            "frozen_version_ids": frozen,
            "version_count": len(versions),
            "status": new_status,
        }
    )


def serialize_for_audit(strategy: Strategy) -> str:
    """Compact JSON for audit / debugging — never logged with secrets."""
    return json.dumps({"strategy_id": str(strategy.strategy_id), "name": strategy.name, "status": strategy.status.value})
