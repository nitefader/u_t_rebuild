"""SQLite persistence for Screener / ScreenerVersion / ScreenerRun.

Lives in its own module (separate from ``backend/app/persistence/``) so this
slice does not need to mutate Codex-owned persistence schema. Tables are
created on first connection via ``ensure_schema()``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .domain import Screener, ScreenerRun, ScreenerVersion


SCREENER_SCHEMA = """
CREATE TABLE IF NOT EXISTS screeners (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_run_at TEXT,
    last_run_id TEXT,
    version_count INTEGER NOT NULL DEFAULT 1,
    latest_version_id TEXT,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_screeners_status ON screeners(status);
CREATE INDEX IF NOT EXISTS idx_screeners_last_run_at ON screeners(last_run_at);

CREATE TABLE IF NOT EXISTS screener_versions (
    id TEXT PRIMARY KEY,
    screener_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (screener_id) REFERENCES screeners(id)
);

CREATE INDEX IF NOT EXISTS idx_screener_versions_screener_id
    ON screener_versions(screener_id);

CREATE TABLE IF NOT EXISTS screener_runs (
    id TEXT PRIMARY KEY,
    screener_id TEXT NOT NULL,
    screener_version_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    universe_size INTEGER NOT NULL DEFAULT 0,
    matched_count INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL,
    FOREIGN KEY (screener_id) REFERENCES screeners(id),
    FOREIGN KEY (screener_version_id) REFERENCES screener_versions(id)
);

CREATE INDEX IF NOT EXISTS idx_screener_runs_screener_id
    ON screener_runs(screener_id);
CREATE INDEX IF NOT EXISTS idx_screener_runs_status
    ON screener_runs(status);
CREATE INDEX IF NOT EXISTS idx_screener_runs_started_at
    ON screener_runs(started_at);
"""


class ScreenerNotFoundError(LookupError):
    """Raised when a Screener / version / run id has no row."""


class ScreenerStore:
    """Thin synchronous SQLite store for Screeners.

    Threading: opens a fresh connection per call (the FastAPI server is
    single-threaded for tests but uvicorn workers may be multi-threaded;
    keeping the connection scoped per call avoids the SQLite "objects can
    only be used in the thread they were created in" trap).
    """

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCREENER_SCHEMA)

    # ---------- Screener ----------------------------------------------

    def save_screener(self, screener: Screener) -> Screener:
        payload = screener.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO screeners
                    (id, name, description, tags, status, created_at,
                     last_run_at, last_run_id, version_count,
                     latest_version_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    tags=excluded.tags,
                    status=excluded.status,
                    last_run_at=excluded.last_run_at,
                    last_run_id=excluded.last_run_id,
                    version_count=excluded.version_count,
                    latest_version_id=excluded.latest_version_id,
                    payload=excluded.payload
                """,
                (
                    str(screener.id),
                    screener.name,
                    screener.description,
                    json.dumps(list(screener.tags)),
                    screener.status,
                    screener.created_at.isoformat(),
                    screener.last_run_at.isoformat() if screener.last_run_at else None,
                    str(screener.last_run_id) if screener.last_run_id else None,
                    screener.version_count,
                    str(screener.latest_version_id) if screener.latest_version_id else None,
                    json.dumps(payload, default=str),
                ),
            )
        return screener

    def get_screener(self, screener_id: UUID) -> Screener:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM screeners WHERE id=?",
                (str(screener_id),),
            ).fetchone()
            if row is None:
                raise ScreenerNotFoundError(f"screener {screener_id} not found")
            return Screener.model_validate(json.loads(row["payload"]))

    def list_screeners(self) -> tuple[Screener, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM screeners ORDER BY created_at DESC"
            ).fetchall()
            return tuple(Screener.model_validate(json.loads(r["payload"])) for r in rows)

    def delete_screener(self, screener_id: UUID) -> None:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM screeners WHERE id=?", (str(screener_id),))
            if cur.rowcount == 0:
                raise ScreenerNotFoundError(f"screener {screener_id} not found")
            conn.execute("DELETE FROM screener_versions WHERE screener_id=?", (str(screener_id),))
            conn.execute("DELETE FROM screener_runs WHERE screener_id=?", (str(screener_id),))

    # ---------- ScreenerVersion ---------------------------------------

    def save_version(self, version: ScreenerVersion) -> ScreenerVersion:
        payload = version.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO screener_versions
                    (id, screener_id, version, name, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    version=excluded.version,
                    name=excluded.name,
                    payload=excluded.payload
                """,
                (
                    str(version.id),
                    str(version.screener_id),
                    version.version,
                    version.name,
                    version.created_at.isoformat(),
                    json.dumps(payload, default=str),
                ),
            )
        return version

    def get_version(self, version_id: UUID) -> ScreenerVersion:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM screener_versions WHERE id=?",
                (str(version_id),),
            ).fetchone()
            if row is None:
                raise ScreenerNotFoundError(f"screener_version {version_id} not found")
            return ScreenerVersion.model_validate(json.loads(row["payload"]))

    def list_versions(self, screener_id: UUID) -> tuple[ScreenerVersion, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM screener_versions WHERE screener_id=? ORDER BY version ASC",
                (str(screener_id),),
            ).fetchall()
            return tuple(ScreenerVersion.model_validate(json.loads(r["payload"])) for r in rows)

    def latest_version(self, screener_id: UUID) -> ScreenerVersion | None:
        versions = self.list_versions(screener_id)
        return versions[-1] if versions else None

    # ---------- ScreenerRun -------------------------------------------

    def save_run(self, run: ScreenerRun) -> ScreenerRun:
        payload = run.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO screener_runs
                    (id, screener_id, screener_version_id, started_at,
                     completed_at, status, universe_size, matched_count, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    completed_at=excluded.completed_at,
                    status=excluded.status,
                    universe_size=excluded.universe_size,
                    matched_count=excluded.matched_count,
                    payload=excluded.payload
                """,
                (
                    str(run.id),
                    str(run.screener_id),
                    str(run.screener_version_id),
                    run.started_at.isoformat(),
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.status.value,
                    run.universe_size,
                    run.matched_count,
                    json.dumps(payload, default=str),
                ),
            )
        return run

    def get_run(self, run_id: UUID) -> ScreenerRun:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM screener_runs WHERE id=?",
                (str(run_id),),
            ).fetchone()
            if row is None:
                raise ScreenerNotFoundError(f"screener_run {run_id} not found")
            return ScreenerRun.model_validate(json.loads(row["payload"]))

    def list_runs(self, *, screener_id: UUID | None = None, limit: int = 50) -> tuple[ScreenerRun, ...]:
        with self._connect() as conn:
            if screener_id is not None:
                rows = conn.execute(
                    "SELECT payload FROM screener_runs WHERE screener_id=? "
                    "ORDER BY started_at DESC LIMIT ?",
                    (str(screener_id), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT payload FROM screener_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return tuple(ScreenerRun.model_validate(json.loads(r["payload"])) for r in rows)

    # ---------- Convenience -------------------------------------------

    def update_last_run(self, screener_id: UUID, run: ScreenerRun, when: datetime) -> None:
        existing = self.get_screener(screener_id)
        self.save_screener(
            existing.model_copy(
                update={"last_run_id": run.id, "last_run_at": when},
            ),
        )
