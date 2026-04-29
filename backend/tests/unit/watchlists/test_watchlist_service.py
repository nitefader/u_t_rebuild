from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.watchlists import WatchlistKind, WatchlistService, WatchlistServiceError, WatchlistWriteRequest
from backend.app.watchlists.models import WatchlistDynamicRules
from backend.app.watchlists.persistence import WatchlistRepository


@pytest.fixture()
def service(tmp_path: Path) -> WatchlistService:
    return WatchlistService(repository=WatchlistRepository(tmp_path / "ut.db"))


def test_create_static_watchlist(service: WatchlistService) -> None:
    w = service.create_watchlist(
        WatchlistWriteRequest(name="Liquid Caps", static_symbols=("aapl", "MSFT", "googl"))
    )
    assert w.kind == WatchlistKind.STATIC
    # symbols are normalized upper-case
    assert w.static_symbols == ("AAPL", "MSFT", "GOOGL")


def test_static_requires_symbols(service: WatchlistService) -> None:
    with pytest.raises(WatchlistServiceError):
        service.create_watchlist(WatchlistWriteRequest(name="empty", static_symbols=()))


def test_dynamic_requires_rules(service: WatchlistService) -> None:
    with pytest.raises(WatchlistServiceError):
        service.create_watchlist(
            WatchlistWriteRequest(name="dyn", kind=WatchlistKind.DYNAMIC, dynamic_rules=None)
        )


def test_take_snapshot_static(service: WatchlistService) -> None:
    w = service.create_watchlist(
        WatchlistWriteRequest(name="Caps", static_symbols=("AAPL", "MSFT"))
    )
    snap = service.take_snapshot(w.watchlist_id, note="initial")
    assert snap.symbols == ("AAPL", "MSFT")
    assert snap.note == "initial"
    detail = service.get_watchlist(w.watchlist_id)
    assert detail.snapshots[0].watchlist_snapshot_id == snap.watchlist_snapshot_id
    assert detail.watchlist.snapshot_count == 1
    assert detail.watchlist.latest_snapshot_id == snap.watchlist_snapshot_id


def test_take_snapshot_dynamic_requires_resolver(service: WatchlistService) -> None:
    w = service.create_watchlist(
        WatchlistWriteRequest(
            name="Dyn",
            kind=WatchlistKind.DYNAMIC,
            static_symbols=("SPY",),
            dynamic_rules=WatchlistDynamicRules(filters=()),
        )
    )
    with pytest.raises(WatchlistServiceError, match="dynamic watchlist resolver"):
        service.take_snapshot(w.watchlist_id)


def test_update_watchlist(service: WatchlistService) -> None:
    w = service.create_watchlist(
        WatchlistWriteRequest(name="A", static_symbols=("AAPL",))
    )
    updated = service.update_watchlist(
        w.watchlist_id,
        WatchlistWriteRequest(name="B", static_symbols=("MSFT", "GOOGL")),
    )
    assert updated.name == "B"
    assert updated.static_symbols == ("MSFT", "GOOGL")


def test_get_unknown_raises(service: WatchlistService) -> None:
    with pytest.raises(WatchlistServiceError):
        service.get_watchlist(uuid4())


def test_delete_watchlist_without_snapshot_history(service: WatchlistService) -> None:
    w = service.create_watchlist(
        WatchlistWriteRequest(name="Bye", static_symbols=("AAPL",))
    )
    service.delete_watchlist(w.watchlist_id)
    with pytest.raises(WatchlistServiceError):
        service.get_watchlist(w.watchlist_id)


def test_repository_migrates_legacy_watchlist_table(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE watchlists (
                id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                config_json TEXT,
                latest_symbols_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO watchlists(
                id, name, type, config_json, latest_symbols_json, created_at, updated_at
            )
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "test_watchlist",
                "Test Watchlist",
                "static",
                json.dumps({"description": "legacy row"}),
                json.dumps(["aapl", "MSFT"]),
                "2026-04-26T00:00:00Z",
                "2026-04-26T00:00:00Z",
            ),
        )
        conn.execute(
            """
            CREATE TABLE watchlist_snapshots (
                id TEXT PRIMARY KEY,
                watchlist_legacy_id TEXT,
                symbols_json TEXT
            )
            """
        )

    repository = WatchlistRepository(db_path)
    watchlists = repository.list_watchlists()

    assert len(watchlists) == 1
    migrated = watchlists[0]
    assert isinstance(migrated.watchlist_id, UUID)
    assert migrated.name == "Test Watchlist"
    assert migrated.description == "legacy row"
    assert migrated.kind == WatchlistKind.STATIC
    assert migrated.static_symbols == ("AAPL", "MSFT")

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(watchlists)")}
        assert {"watchlist_id", "kind", "payload"}.issubset(columns)
        snapshot_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(watchlist_snapshots)")
        }
        assert {"watchlist_snapshot_id", "watchlist_id", "taken_at", "payload"}.issubset(
            snapshot_columns
        )
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'watchlists_legacy_pre_canonical'"
        ).fetchone()
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' "
            "AND name = 'watchlist_snapshots_legacy_pre_canonical'"
        ).fetchone()

    assert len(WatchlistRepository(db_path).list_watchlists()) == 1
