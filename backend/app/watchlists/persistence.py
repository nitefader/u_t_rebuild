"""SQLite repository for Watchlists. Owns its own DDL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from backend.app.domain._base import utc_now
from backend.app.persistence.session import SQLiteSessionFactory

from .models import Watchlist, WatchlistDynamicRules, WatchlistKind, WatchlistSnapshot


_LEGACY_WATCHLIST_NAMESPACE = UUID("bba09b80-4d74-5d8e-82b8-73bd8e6b3a37")

WATCHLISTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""

WATCHLISTS_KIND_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlists_kind ON watchlists(kind)
"""

WATCHLIST_SNAPSHOTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS watchlist_snapshots (
    watchlist_snapshot_id TEXT PRIMARY KEY,
    watchlist_id TEXT NOT NULL,
    taken_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""

WATCHLIST_SNAPSHOTS_WATCHLIST_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_snapshots_watchlist_id
ON watchlist_snapshots(watchlist_id)
"""

WATCHLIST_SNAPSHOTS_TAKEN_AT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_watchlist_snapshots_taken_at
ON watchlist_snapshots(taken_at)
"""

CANONICAL_WATCHLIST_COLUMNS = {
    "watchlist_id",
    "name",
    "kind",
    "created_at",
    "updated_at",
    "payload",
}

CANONICAL_WATCHLIST_SNAPSHOT_COLUMNS = {
    "watchlist_snapshot_id",
    "watchlist_id",
    "taken_at",
    "payload",
}


def _table_columns(conn: Any, table: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_schema(conn: Any) -> None:
    _migrate_legacy_watchlists(conn)
    _migrate_legacy_snapshots(conn)
    conn.execute(WATCHLISTS_TABLE_SQL)
    conn.execute(WATCHLISTS_KIND_INDEX_SQL)
    conn.execute(WATCHLIST_SNAPSHOTS_TABLE_SQL)
    conn.execute(WATCHLIST_SNAPSHOTS_WATCHLIST_INDEX_SQL)
    conn.execute(WATCHLIST_SNAPSHOTS_TAKEN_AT_INDEX_SQL)


def _migrate_legacy_watchlists(conn: Any) -> None:
    columns = _table_columns(conn, "watchlists")
    if not columns or CANONICAL_WATCHLIST_COLUMNS.issubset(columns):
        return

    legacy_table = _unique_legacy_table_name(conn, "watchlists_legacy_pre_canonical")
    conn.execute(f"ALTER TABLE watchlists RENAME TO {legacy_table}")
    conn.execute(WATCHLISTS_TABLE_SQL)

    rows = conn.execute(f"SELECT * FROM {legacy_table}").fetchall()
    for row in rows:
        watchlist = _watchlist_from_legacy(dict(row))
        _insert_watchlist(conn, watchlist)


def _migrate_legacy_snapshots(conn: Any) -> None:
    columns = _table_columns(conn, "watchlist_snapshots")
    if not columns or CANONICAL_WATCHLIST_SNAPSHOT_COLUMNS.issubset(columns):
        return

    legacy_table = _unique_legacy_table_name(conn, "watchlist_snapshots_legacy_pre_canonical")
    conn.execute(f"ALTER TABLE watchlist_snapshots RENAME TO {legacy_table}")
    conn.execute(WATCHLIST_SNAPSHOTS_TABLE_SQL)


def _unique_legacy_table_name(conn: Any, base_name: str) -> str:
    candidate = base_name
    suffix = 2
    while conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (candidate,),
    ).fetchone():
        candidate = f"{base_name}_{suffix}"
        suffix += 1
    return candidate


def _watchlist_from_legacy(row: dict[str, Any]) -> Watchlist:
    payload = row.get("payload")
    if isinstance(payload, str) and payload.strip():
        try:
            return Watchlist.model_validate_json(payload)
        except ValueError:
            pass

    legacy_id = _legacy_text(row.get("watchlist_id") or row.get("id") or row.get("name"))
    config = _json_object(row.get("config_json"))
    symbols = _json_symbols(row.get("latest_symbols_json"))
    kind = _legacy_kind(row.get("kind") or row.get("type") or config.get("kind"))

    dynamic_rules = None
    if kind == WatchlistKind.DYNAMIC:
        dynamic_rules = WatchlistDynamicRules(
            universe=_legacy_text(config.get("universe")) or "us_equities",
            filters=_json_filters(config.get("filters")),
            notes=config.get("notes") if isinstance(config.get("notes"), str) else None,
        )

    description = config.get("description")
    created_at = _legacy_text(row.get("created_at")) or utc_now()
    updated_at = _legacy_text(row.get("updated_at")) or created_at

    return Watchlist.model_validate(
        {
            "watchlist_id": _legacy_uuid(legacy_id),
            "name": _legacy_text(row.get("name")) or legacy_id or "Legacy Watchlist",
            "description": description if isinstance(description, str) else None,
            "kind": kind,
            "static_symbols": tuple(symbols),
            "dynamic_rules": dynamic_rules,
            "created_at": created_at,
            "updated_at": updated_at,
        }
    )


def _legacy_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid5(_LEGACY_WATCHLIST_NAMESPACE, value or "legacy-watchlist")


def _legacy_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _legacy_kind(value: Any) -> WatchlistKind:
    text = _legacy_text(value).lower()
    return WatchlistKind.DYNAMIC if text == WatchlistKind.DYNAMIC.value else WatchlistKind.STATIC


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_symbols(value: Any) -> tuple[str, ...]:
    parsed = value
    if isinstance(value, str):
        if not value.strip():
            return ()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ()
    if not isinstance(parsed, list | tuple):
        return ()
    return tuple(str(symbol).strip().upper() for symbol in parsed if str(symbol).strip())


def _json_filters(value: Any) -> tuple[dict[str, object], ...]:
    return tuple(item for item in value if isinstance(item, dict)) if isinstance(value, list | tuple) else ()


def _insert_watchlist(conn: Any, watchlist: Watchlist) -> None:
    conn.execute(
        """
        INSERT INTO watchlists(watchlist_id, name, kind, created_at, updated_at, payload)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(watchlist_id) DO UPDATE SET
            name=excluded.name,
            kind=excluded.kind,
            updated_at=excluded.updated_at,
            payload=excluded.payload
        """,
        (
            str(watchlist.watchlist_id),
            watchlist.name,
            watchlist.kind.value,
            watchlist.created_at.isoformat(),
            watchlist.updated_at.isoformat(),
            watchlist.model_dump_json(),
        ),
    )


class WatchlistNotFoundError(LookupError):
    pass


class WatchlistRepository:
    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._session_factory.connect() as conn:
            _ensure_schema(conn)

    def list_watchlists(self) -> tuple[Watchlist, ...]:
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM watchlists ORDER BY created_at DESC"
            ).fetchall()
        return tuple(Watchlist.model_validate_json(row[0]) for row in rows)

    def get_watchlist(self, watchlist_id: UUID) -> Watchlist:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM watchlists WHERE watchlist_id = ?",
                (str(watchlist_id),),
            ).fetchone()
        if row is None:
            raise WatchlistNotFoundError(f"watchlist {watchlist_id} not found")
        return Watchlist.model_validate_json(row[0])

    def save_watchlist(self, watchlist: Watchlist) -> Watchlist:
        with self._session_factory.connect() as conn:
            _insert_watchlist(conn, watchlist)
        return watchlist

    def delete_watchlist(self, watchlist_id: UUID) -> None:
        with self._session_factory.connect() as conn:
            conn.execute(
                "DELETE FROM watchlist_snapshots WHERE watchlist_id = ?",
                (str(watchlist_id),),
            )
            conn.execute(
                "DELETE FROM watchlists WHERE watchlist_id = ?",
                (str(watchlist_id),),
            )

    def save_snapshot(self, snapshot: WatchlistSnapshot) -> WatchlistSnapshot:
        with self._session_factory.connect() as conn:
            conn.execute(
                """
                INSERT INTO watchlist_snapshots(watchlist_snapshot_id, watchlist_id, taken_at, payload)
                VALUES(?, ?, ?, ?)
                """,
                (
                    str(snapshot.watchlist_snapshot_id),
                    str(snapshot.watchlist_id),
                    snapshot.taken_at.isoformat(),
                    snapshot.model_dump_json(),
                ),
            )
        return snapshot

    def list_snapshots(self, watchlist_id: UUID) -> tuple[WatchlistSnapshot, ...]:
        with self._session_factory.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM watchlist_snapshots WHERE watchlist_id = ? ORDER BY taken_at DESC",
                (str(watchlist_id),),
            ).fetchall()
        return tuple(WatchlistSnapshot.model_validate_json(row[0]) for row in rows)

    def latest_snapshot(self, watchlist_id: UUID) -> WatchlistSnapshot | None:
        with self._session_factory.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM watchlist_snapshots WHERE watchlist_id = ? "
                "ORDER BY taken_at DESC LIMIT 1",
                (str(watchlist_id),),
            ).fetchone()
        return None if row is None else WatchlistSnapshot.model_validate_json(row[0])
