from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteSessionFactory:
    """Small SQLite connection boundary for local runtime persistence.

    T-6 (Bracket Program) sets ``journal_mode=WAL`` on every connect. WAL
    is a persistent database property — the first connection that issues
    the PRAGMA promotes the database file; subsequent issues are no-ops.
    Re-issuing on every ``connect()`` is idempotent and ensures fresh
    process boots converge to WAL even when the database file pre-exists
    in the legacy ``delete`` journal mode. WAL is required by MAP §7 D7
    (TOCTOU hardening) so reader-writer concurrency does not block:
    a writer (e.g. operator PUT to /risk-plan-map) cannot stall an
    in-flight Governor evaluation, and the evaluation reads a coherent
    snapshot inside its single-connection composite-read block.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
