"""One-shot operator tool: empty legacy strategy tables.

Deletes all rows from `strategies` and `strategy_versions` (legacy tables).
DDL and all other tables are untouched. v4 tables are untouched.
Idempotent — safe to run multiple times (second run reports 0 rows deleted).

Usage:
    python -m backend.tools.strategy_v4_data_cleanslate
  or:
    python backend/tools/strategy_v4_data_cleanslate.py [--db-path PATH]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def run_cleanslate(db_path: Path) -> None:
    print(f"Database: {db_path}")

    if not db_path.exists():
        print("Database file does not exist — nothing to do.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        # Count before
        tables_to_check = ["strategies", "strategy_versions"]
        counts_before: dict[str, int] = {}
        for table in tables_to_check:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
                counts_before[table] = row["n"]
            except sqlite3.OperationalError:
                counts_before[table] = 0
                print(f"  Table '{table}' does not exist — skipping.")

        print("Row counts before clean-slate:")
        for table, count in counts_before.items():
            print(f"  {table}: {count}")

        # Delete
        with conn:
            deleted: dict[str, int] = {}
            for table in tables_to_check:
                if counts_before[table] == 0:
                    deleted[table] = 0
                    continue
                cur = conn.execute(f"DELETE FROM {table}")  # noqa: S608
                deleted[table] = cur.rowcount

        print("Rows deleted:")
        for table, count in deleted.items():
            print(f"  {table}: {count}")

        # Count after
        print("Row counts after clean-slate:")
        for table in tables_to_check:
            try:
                row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
                print(f"  {table}: {row['n']}")
            except sqlite3.OperationalError:
                print(f"  {table}: (table does not exist)")

    finally:
        conn.close()

    print("Done.")


def _resolve_db_path(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path)

    # Mirror get_runtime_db_path() resolution without importing backend packages
    # (keeps the tool usable outside the virtualenv for emergency ops).
    import os

    env_path = os.getenv("OPERATIONS_RUNTIME_DB_PATH") or os.getenv("UTOS_SQLITE_PATH")
    if env_path:
        return Path(env_path)

    default = Path("data/runtime.db")
    legacy = Path("data/utos.sqlite3")
    if not default.exists() and legacy.exists():
        return legacy
    return default


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Empty legacy strategy tables (data only).")
    parser.add_argument("--db-path", default=None, help="Path to the SQLite database.")
    args = parser.parse_args()
    db = _resolve_db_path(args.db_path)
    run_cleanslate(db)
    sys.exit(0)
