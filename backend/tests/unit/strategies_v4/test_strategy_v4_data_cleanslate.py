"""Tests for the strategy_v4_data_cleanslate operator tool."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from backend.tools.strategy_v4_data_cleanslate import run_cleanslate


def _setup_legacy_db(db_path: Path) -> None:
    """Create legacy tables with some rows."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_versions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            version INTEGER NOT NULL
        )
    """)
    # Insert some rows
    conn.execute("INSERT INTO strategies VALUES (?, ?)", (str(uuid4()), "Old strategy 1"))
    conn.execute("INSERT INTO strategies VALUES (?, ?)", (str(uuid4()), "Old strategy 2"))
    conn.execute("INSERT INTO strategy_versions VALUES (?, ?, ?)", (str(uuid4()), str(uuid4()), 1))
    conn.commit()
    conn.close()


def _setup_v4_tables(db_path: Path) -> None:
    """Create v4 tables with a row to verify they are untouched."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_versions_v4 (
            strategy_version_v4_id TEXT PRIMARY KEY,
            strategy_v4_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            direction TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            default_strategy_controls_version_id TEXT,
            default_execution_plan_version_id TEXT,
            feature_requirements_json TEXT NOT NULL,
            validation_status_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(strategy_v4_id, version)
        )
    """)
    conn.execute(
        "INSERT INTO strategy_versions_v4 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid4()),
            str(uuid4()),
            1,
            "V4 strategy",
            None,
            "long",
            "[]",
            None,
            None,
            "[]",
            '{"valid":true,"errors":[],"warnings":[]}',
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()


def _count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608
    conn.close()
    return row[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_cleanslate_empties_legacy_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _setup_legacy_db(db)

    assert _count(db, "strategies") == 2
    assert _count(db, "strategy_versions") == 1

    run_cleanslate(db)

    assert _count(db, "strategies") == 0
    assert _count(db, "strategy_versions") == 0


def test_cleanslate_does_not_touch_v4_tables(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _setup_legacy_db(db)
    _setup_v4_tables(db)

    run_cleanslate(db)

    assert _count(db, "strategy_versions_v4") == 1


def test_cleanslate_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    _setup_legacy_db(db)

    run_cleanslate(db)
    run_cleanslate(db)  # second run is fine

    assert _count(db, "strategies") == 0
    assert _count(db, "strategy_versions") == 0


def test_cleanslate_nonexistent_db_is_noop(tmp_path: Path) -> None:
    db = tmp_path / "does_not_exist.db"
    run_cleanslate(db)  # should not raise


def test_cleanslate_missing_table_is_noop(tmp_path: Path) -> None:
    """If legacy tables do not exist, tool skips them gracefully."""
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.close()
    run_cleanslate(db)  # should not raise
