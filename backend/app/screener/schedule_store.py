"""SQLite persistence for discovery schedules and executions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from .schedules import (
    DiscoverySchedule,
    DiscoveryScheduleExecution,
    DiscoveryScheduleExecutionStatus,
    DiscoveryScheduleStatus,
)


DISCOVERY_SCHEDULE_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_schedules (
    schedule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    next_run_at TEXT,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_discovery_schedules_next_run
    ON discovery_schedules(status, enabled, next_run_at);
CREATE INDEX IF NOT EXISTS idx_discovery_schedules_target
    ON discovery_schedules(target_kind);

CREATE TABLE IF NOT EXISTS discovery_schedule_executions (
    execution_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES discovery_schedules(schedule_id)
);

CREATE INDEX IF NOT EXISTS idx_discovery_schedule_executions_schedule
    ON discovery_schedule_executions(schedule_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_discovery_schedule_executions_status
    ON discovery_schedule_executions(status);
"""


class DiscoveryScheduleNotFoundError(LookupError):
    pass


class DiscoveryScheduleStore:
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
            conn.executescript(DISCOVERY_SCHEDULE_SCHEMA)

    def save_schedule(self, schedule: DiscoverySchedule) -> DiscoverySchedule:
        payload = json.dumps(schedule.model_dump(mode="json"), default=str)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO discovery_schedules
                    (schedule_id, name, target_kind, status, enabled, next_run_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(schedule_id) DO UPDATE SET
                    name=excluded.name,
                    target_kind=excluded.target_kind,
                    status=excluded.status,
                    enabled=excluded.enabled,
                    next_run_at=excluded.next_run_at,
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    str(schedule.schedule_id),
                    schedule.name,
                    schedule.target_kind.value,
                    schedule.status.value,
                    1 if schedule.enabled else 0,
                    schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                    schedule.updated_at.isoformat(),
                    payload,
                ),
            )
        return schedule

    def get_schedule(self, schedule_id: UUID) -> DiscoverySchedule:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM discovery_schedules WHERE schedule_id = ?",
                (str(schedule_id),),
            ).fetchone()
        if row is None:
            raise DiscoveryScheduleNotFoundError(f"discovery schedule {schedule_id} not found")
        return DiscoverySchedule.model_validate(json.loads(row["payload"]))

    def list_schedules(self) -> tuple[DiscoverySchedule, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM discovery_schedules ORDER BY updated_at DESC"
            ).fetchall()
        return tuple(DiscoverySchedule.model_validate(json.loads(row["payload"])) for row in rows)

    def delete_schedule(self, schedule_id: UUID) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM discovery_schedules WHERE schedule_id = ?",
                (str(schedule_id),),
            )
        if cur.rowcount == 0:
            raise DiscoveryScheduleNotFoundError(f"discovery schedule {schedule_id} not found")

    def list_due_schedules(self, *, now: datetime) -> tuple[DiscoverySchedule, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM discovery_schedules
                WHERE status = ?
                  AND enabled = 1
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (DiscoveryScheduleStatus.ACTIVE.value, now.isoformat()),
            ).fetchall()
        return tuple(DiscoverySchedule.model_validate(json.loads(row["payload"])) for row in rows)

    def save_execution(self, execution: DiscoveryScheduleExecution) -> DiscoveryScheduleExecution:
        payload = json.dumps(execution.model_dump(mode="json"), default=str)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO discovery_schedule_executions
                    (execution_id, schedule_id, started_at, status, payload)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    status=excluded.status,
                    payload=excluded.payload
                """,
                (
                    str(execution.execution_id),
                    str(execution.schedule_id),
                    execution.started_at.isoformat(),
                    execution.status.value,
                    payload,
                ),
            )
        return execution

    def claim_execution(self, execution: DiscoveryScheduleExecution) -> bool:
        """Atomically insert a running execution if no fresh run is active."""

        payload = json.dumps(execution.model_dump(mode="json"), default=str)
        with self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT 1 FROM discovery_schedule_executions
                    WHERE schedule_id = ? AND status = ?
                    LIMIT 1
                    """,
                    (
                        str(execution.schedule_id),
                        DiscoveryScheduleExecutionStatus.RUNNING.value,
                    ),
                ).fetchone()
                if row is not None:
                    conn.execute("ROLLBACK")
                    return False
                conn.execute(
                    """
                    INSERT INTO discovery_schedule_executions
                        (execution_id, schedule_id, started_at, status, payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(execution.execution_id),
                        str(execution.schedule_id),
                        execution.started_at.isoformat(),
                        execution.status.value,
                        payload,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return True

    def list_executions(
        self,
        *,
        schedule_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[DiscoveryScheduleExecution, ...]:
        with self._connect() as conn:
            if schedule_id is None:
                rows = conn.execute(
                    "SELECT payload FROM discovery_schedule_executions ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT payload FROM discovery_schedule_executions
                    WHERE schedule_id = ?
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (str(schedule_id), limit),
                ).fetchall()
        return tuple(DiscoveryScheduleExecution.model_validate(json.loads(row["payload"])) for row in rows)

    def execution_count(self, schedule_id: UUID) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM discovery_schedule_executions WHERE schedule_id = ?",
                (str(schedule_id),),
            ).fetchone()
        return int(row["n"]) if row is not None else 0

    def has_running_execution(self, schedule_id: UUID) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM discovery_schedule_executions
                WHERE schedule_id = ? AND status = ?
                LIMIT 1
                """,
                (str(schedule_id), DiscoveryScheduleExecutionStatus.RUNNING.value),
            ).fetchone()
        return row is not None

    def abandon_stale_running_executions(
        self,
        schedule_id: UUID,
        *,
        stale_before: datetime,
        completed_at: datetime,
    ) -> tuple[DiscoveryScheduleExecution, ...]:
        abandoned: list[DiscoveryScheduleExecution] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT execution_id, payload FROM discovery_schedule_executions
                WHERE schedule_id = ? AND status = ? AND started_at < ?
                """,
                (
                    str(schedule_id),
                    DiscoveryScheduleExecutionStatus.RUNNING.value,
                    stale_before.isoformat(),
                ),
            ).fetchall()
            for row in rows:
                existing = DiscoveryScheduleExecution.model_validate(json.loads(row["payload"]))
                updated = existing.model_copy(
                    update={
                        "status": DiscoveryScheduleExecutionStatus.FAILED,
                        "completed_at": completed_at,
                        "error": "stale running execution abandoned after scheduler timeout",
                        "audit_events": (
                            *existing.audit_events,
                            {
                                "type": "discovery_schedule_execution_abandoned",
                                "at": completed_at.isoformat(),
                            },
                        ),
                    }
                )
                payload = json.dumps(updated.model_dump(mode="json"), default=str)
                conn.execute(
                    """
                    UPDATE discovery_schedule_executions
                    SET status = ?, payload = ?
                    WHERE execution_id = ?
                    """,
                    (
                        DiscoveryScheduleExecutionStatus.FAILED.value,
                        payload,
                        str(updated.execution_id),
                    ),
                )
                abandoned.append(updated)
        return tuple(abandoned)
