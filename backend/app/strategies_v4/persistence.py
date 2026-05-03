"""SQLite repository for StrategyVersionV4.

Owns six tables, all ending in _v4. Idempotent DDL. Atomic transactions.
Does NOT touch legacy strategy_versions or strategies tables.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyIdentityV4,
    StrategyLegV4,
    StrategyLogicalExitV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVariableV4,
    StrategyVersionV4,
    ValidationStatusV4,
)
from backend.app.persistence.session import SQLiteSessionFactory
from backend.app.strategies.expression_api import compile_for_storage, validate_expression


# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

SCHEMA = """
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
    timeframe_aliases_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(strategy_v4_id, version)
);
CREATE INDEX IF NOT EXISTS ix_strategy_versions_v4_strategy_v4_id
    ON strategy_versions_v4(strategy_v4_id);

CREATE TABLE IF NOT EXISTS strategy_variables_v4 (
    strategy_variable_v4_id TEXT PRIMARY KEY,
    strategy_version_v4_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    expression_text TEXT NOT NULL,
    expression_ast_blob BLOB,
    feature_requirements_json TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'expression',
    UNIQUE(strategy_version_v4_id, name),
    UNIQUE(strategy_version_v4_id, position)
);

CREATE TABLE IF NOT EXISTS strategy_entries_v4 (
    strategy_entry_v4_id TEXT PRIMARY KEY,
    strategy_version_v4_id TEXT NOT NULL,
    side TEXT NOT NULL,
    expression_text TEXT NOT NULL,
    expression_ast_blob BLOB,
    feature_requirements_json TEXT NOT NULL,
    UNIQUE(strategy_version_v4_id, side)
);

CREATE TABLE IF NOT EXISTS strategy_stops_v4 (
    strategy_stop_v4_id TEXT PRIMARY KEY,
    strategy_version_v4_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    mode TEXT NOT NULL,
    scope TEXT NOT NULL,
    simple_type TEXT,
    simple_value REAL,
    expression_text TEXT,
    expression_ast_blob BLOB,
    feature_requirements_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_strategy_stops_v4_strategy_version_v4_id
    ON strategy_stops_v4(strategy_version_v4_id);

CREATE TABLE IF NOT EXISTS strategy_legs_v4 (
    strategy_leg_v4_id TEXT PRIMARY KEY,
    strategy_version_v4_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    kind TEXT NOT NULL,
    size_pct REAL NOT NULL,
    target_type TEXT NOT NULL,
    target_value REAL,
    on_fill_action_json TEXT NOT NULL,
    UNIQUE(strategy_version_v4_id, position)
);

CREATE TABLE IF NOT EXISTS strategy_logical_exits_v4 (
    strategy_logical_exit_v4_id TEXT PRIMARY KEY,
    strategy_version_v4_id TEXT NOT NULL,
    side TEXT NOT NULL,
    position INTEGER NOT NULL,
    template_id TEXT NOT NULL,
    params_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_strategy_logical_exits_v4_svv4
    ON strategy_logical_exits_v4(strategy_version_v4_id);
"""


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class StrategyV4VersionNotFoundError(LookupError):
    pass


class StrategyV4ValidationError(ValueError):
    pass


def _migrate_strategy_v4_schema(conn: sqlite3.Connection) -> None:
    var_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(strategy_variables_v4)").fetchall()
    }
    if var_cols and "kind" not in var_cols:
        conn.execute(
            "ALTER TABLE strategy_variables_v4 ADD COLUMN kind TEXT NOT NULL DEFAULT 'expression'"
        )
    ver_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(strategy_versions_v4)").fetchall()
    }
    if ver_cols and "timeframe_aliases_json" not in ver_cols:
        try:
            conn.execute(
                "ALTER TABLE strategy_versions_v4 ADD COLUMN timeframe_aliases_json TEXT NOT NULL DEFAULT '{}'"
            )
        except sqlite3.OperationalError:
            pass


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class StrategyV4Repository:

    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            _migrate_strategy_v4_schema(conn)

    def _connect(self) -> sqlite3.Connection:
        return self._session_factory.connect()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strategy_expression_bindings(
        variables: tuple[StrategyVariableV4, ...],
    ) -> tuple[list[str], frozenset[str]]:
        expr = [x.name for x in variables if x.kind == "expression"]
        tf = frozenset(x.name for x in variables if x.kind == "timeframe")
        return expr, tf

    def _compile_expression(
        self,
        text: str,
        expression_variable_names: list[str],
        timeframe_variable_names: frozenset[str],
    ) -> bytes:
        """Validate + compile; raise StrategyV4ValidationError on failure."""
        from backend.app.strategies.expression_engine import (
            compile as engine_compile,
            default_catalog,
            parse,
            validate,
        )
        from backend.app.strategies.expression_engine.errors import ParseError, ValidationError

        try:
            ast = parse(text, timeframe_variable_names=timeframe_variable_names)
        except ParseError as exc:
            raise StrategyV4ValidationError(str(exc)) from exc
        try:
            vast = validate(
                ast,
                default_catalog(),
                expression_variable_names,
                timeframe_variable_names=timeframe_variable_names,
            )
        except ValidationError as exc:
            raise StrategyV4ValidationError(str(exc)) from exc
        compiled = engine_compile(vast)
        return compile_for_storage(compiled)

    def _feature_keys_from_text(
        self,
        text: str,
        expression_variable_names: list[str],
        timeframe_variable_names: frozenset[str],
    ) -> list[str]:
        result = validate_expression(
            text,
            expression_variable_names,
            timeframe_variable_names=timeframe_variable_names,
        )
        return [f.key for f in result.feature_requirements]

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_version(self, version: StrategyVersionV4) -> None:
        """Persist all six sub-tables atomically.

        Compiles expression texts to AST blobs. Raises StrategyV4ValidationError
        if any expression fails validation.
        """
        expr_ctx, tf_ctx = self._strategy_expression_bindings(version.variables)

        with self._connect() as conn:
            conn.execute("BEGIN")
            try:
                self._save_header(conn, version)
                self._save_variables(conn, version)
                self._save_entries(conn, version, expr_ctx, tf_ctx)
                self._save_stops(conn, version, expr_ctx, tf_ctx)
                self._save_legs(conn, version)
                self._save_logical_exits(conn, version)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def _save_header(self, conn: sqlite3.Connection, v: StrategyVersionV4) -> None:
        conn.execute(
            """
            INSERT INTO strategy_versions_v4(
                strategy_version_v4_id,
                strategy_v4_id,
                version,
                name,
                description,
                direction,
                tags_json,
                default_strategy_controls_version_id,
                default_execution_plan_version_id,
                feature_requirements_json,
                validation_status_json,
                created_at,
                timeframe_aliases_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(v.id),
                str(v.strategy_v4_id),
                v.version,
                v.name,
                v.description,
                v.identity.direction,
                json.dumps(list(v.identity.tags)),
                str(v.default_strategy_controls_version_id)
                if v.default_strategy_controls_version_id
                else None,
                str(v.default_execution_plan_version_id)
                if v.default_execution_plan_version_id
                else None,
                json.dumps(list(v.feature_requirements)),
                json.dumps(
                    {
                        "valid": v.validation_status.valid,
                        "errors": list(v.validation_status.errors),
                        "warnings": list(v.validation_status.warnings),
                    }
                ),
                v.created_at.isoformat(),
                json.dumps(v.timeframe_aliases),
            ),
        )

    def _save_variables(
        self,
        conn: sqlite3.Connection,
        v: StrategyVersionV4,
    ) -> None:
        for pos, var in enumerate(v.variables, start=1):
            preceding_expr = [
                x.name
                for x in v.variables[: pos - 1]
                if x.kind == "expression"
            ]
            preceding_tf = frozenset(
                x.name for x in v.variables[: pos - 1] if x.kind == "timeframe"
            )

            blob: bytes | None
            feat_keys: list[str]

            if var.kind == "timeframe":
                blob = None
                feat_keys = []
            else:
                blob = self._compile_expression(
                    var.expression_text, preceding_expr, preceding_tf
                )
                feat_keys = self._feature_keys_from_text(
                    var.expression_text, preceding_expr, preceding_tf
                )

            conn.execute(
                """
                INSERT INTO strategy_variables_v4(
                    strategy_variable_v4_id,
                    strategy_version_v4_id,
                    position,
                    name,
                    expression_text,
                    expression_ast_blob,
                    feature_requirements_json,
                    kind
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid4()),
                    str(v.id),
                    pos,
                    var.name,
                    var.expression_text,
                    blob,
                    json.dumps(feat_keys),
                    var.kind,
                ),
            )

    def _save_entries(
        self,
        conn: sqlite3.Connection,
        v: StrategyVersionV4,
        expression_variable_names: list[str],
        timeframe_variable_names: frozenset[str],
    ) -> None:
        sides: list[tuple[str, Any]] = []
        if v.entries.long is not None:
            sides.append(("long", v.entries.long))
        if v.entries.short is not None:
            sides.append(("short", v.entries.short))
        for side, entry in sides:
            blob = self._compile_expression(
                entry.expression_text,
                expression_variable_names,
                timeframe_variable_names,
            )
            feat_keys = self._feature_keys_from_text(
                entry.expression_text,
                expression_variable_names,
                timeframe_variable_names,
            )
            conn.execute(
                """
                INSERT INTO strategy_entries_v4(
                    strategy_entry_v4_id,
                    strategy_version_v4_id,
                    side,
                    expression_text,
                    expression_ast_blob,
                    feature_requirements_json
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    str(uuid4()),
                    str(v.id),
                    side,
                    entry.expression_text,
                    blob,
                    json.dumps(feat_keys),
                ),
            )

    def _save_stops(
        self,
        conn: sqlite3.Connection,
        v: StrategyVersionV4,
        expression_variable_names: list[str],
        timeframe_variable_names: frozenset[str],
    ) -> None:
        for pos, stop in enumerate(v.stops, start=1):
            blob: bytes | None = None
            feat_keys: list[str] = []
            if stop.mode == "expression" and stop.expression_text:
                blob = self._compile_expression(
                    stop.expression_text,
                    expression_variable_names,
                    timeframe_variable_names,
                )
                feat_keys = self._feature_keys_from_text(
                    stop.expression_text,
                    expression_variable_names,
                    timeframe_variable_names,
                )
            conn.execute(
                """
                INSERT INTO strategy_stops_v4(
                    strategy_stop_v4_id,
                    strategy_version_v4_id,
                    position,
                    mode,
                    scope,
                    simple_type,
                    simple_value,
                    expression_text,
                    expression_ast_blob,
                    feature_requirements_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(stop.id),
                    str(v.id),
                    pos,
                    stop.mode,
                    stop.scope,
                    stop.simple_type,
                    stop.simple_value,
                    stop.expression_text,
                    blob,
                    json.dumps(feat_keys),
                ),
            )

    def _save_legs(self, conn: sqlite3.Connection, v: StrategyVersionV4) -> None:
        for leg in v.legs:
            conn.execute(
                """
                INSERT INTO strategy_legs_v4(
                    strategy_leg_v4_id,
                    strategy_version_v4_id,
                    position,
                    kind,
                    size_pct,
                    target_type,
                    target_value,
                    on_fill_action_json
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    str(leg.id),
                    str(v.id),
                    leg.position,
                    leg.kind,
                    leg.size_pct,
                    leg.target_type,
                    leg.target_value,
                    json.dumps(
                        {"kind": leg.on_fill_action.kind, "offset_value": leg.on_fill_action.offset_value}
                    ),
                ),
            )

    def _save_logical_exits(self, conn: sqlite3.Connection, v: StrategyVersionV4) -> None:
        sides: list[tuple[str, tuple[StrategyLogicalExitV4, ...]]] = [
            ("long", v.logical_exits.long),
            ("short", v.logical_exits.short),
        ]
        for side, exits in sides:
            for pos, exit_ in enumerate(exits, start=1):
                conn.execute(
                    """
                    INSERT INTO strategy_logical_exits_v4(
                        strategy_logical_exit_v4_id,
                        strategy_version_v4_id,
                        side,
                        position,
                        template_id,
                        params_json
                    ) VALUES (?,?,?,?,?,?)
                    """,
                    (
                        str(exit_.id),
                        str(v.id),
                        side,
                        pos,
                        exit_.template_id,
                        json.dumps(exit_.params),
                    ),
                )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_version(self, strategy_version_v4_id: UUID) -> StrategyVersionV4:
        sid = str(strategy_version_v4_id)
        with self._connect() as conn:
            header = conn.execute(
                "SELECT * FROM strategy_versions_v4 WHERE strategy_version_v4_id = ?",
                (sid,),
            ).fetchone()
            if header is None:
                raise StrategyV4VersionNotFoundError(
                    f"strategy_version_v4_id {strategy_version_v4_id} not found"
                )
            variables = conn.execute(
                "SELECT * FROM strategy_variables_v4 WHERE strategy_version_v4_id = ? ORDER BY position",
                (sid,),
            ).fetchall()
            entries = conn.execute(
                "SELECT * FROM strategy_entries_v4 WHERE strategy_version_v4_id = ?",
                (sid,),
            ).fetchall()
            stops = conn.execute(
                "SELECT * FROM strategy_stops_v4 WHERE strategy_version_v4_id = ? ORDER BY position",
                (sid,),
            ).fetchall()
            legs = conn.execute(
                "SELECT * FROM strategy_legs_v4 WHERE strategy_version_v4_id = ? ORDER BY position",
                (sid,),
            ).fetchall()
            logical_exits = conn.execute(
                "SELECT * FROM strategy_logical_exits_v4 WHERE strategy_version_v4_id = ? ORDER BY side, position",
                (sid,),
            ).fetchall()

        return self._assemble(header, variables, entries, stops, legs, logical_exits)

    def _assemble(
        self,
        header: sqlite3.Row,
        variables: list[sqlite3.Row],
        entries: list[sqlite3.Row],
        stops: list[sqlite3.Row],
        legs: list[sqlite3.Row],
        logical_exits: list[sqlite3.Row],
    ) -> StrategyVersionV4:
        from datetime import datetime, timezone

        vs_status_raw = json.loads(header["validation_status_json"])

        # entries
        long_entry: StrategyEntryV4 | None = None
        short_entry: StrategyEntryV4 | None = None
        for row in entries:
            row_keys = row.keys()
            feat = tuple(json.loads(row["feature_requirements_json"]))
            e = StrategyEntryV4(
                expression_text=row["expression_text"],
                feature_requirements=feat,
                compiled_blob=(
                    row["expression_ast_blob"]
                    if "expression_ast_blob" in row_keys
                    else None
                ),
            )
            if row["side"] == "long":
                long_entry = e
            else:
                short_entry = e

        # variables
        vars_out: list[StrategyVariableV4] = []
        for row in variables:
            rk = row.keys()
            var_kind = row["kind"] if "kind" in rk else "expression"
            vars_out.append(
                StrategyVariableV4(
                    name=row["name"],
                    expression_text=row["expression_text"],
                    kind=var_kind,
                    feature_requirements=tuple(json.loads(row["feature_requirements_json"])),
                    compiled_blob=(
                        row["expression_ast_blob"]
                        if "expression_ast_blob" in rk
                        else None
                    ),
                )
            )

        # stops
        stops_out: list[StrategyStopV4] = []
        for row in stops:
            row_keys = row.keys()
            stops_out.append(
                StrategyStopV4(
                    id=UUID(row["strategy_stop_v4_id"]),
                    mode=row["mode"],
                    scope=row["scope"],
                    simple_type=row["simple_type"],
                    simple_value=row["simple_value"],
                    expression_text=row["expression_text"],
                    feature_requirements=tuple(json.loads(row["feature_requirements_json"])),
                    compiled_blob=(
                        row["expression_ast_blob"]
                        if "expression_ast_blob" in row_keys
                        else None
                    ),
                )
            )

        # legs
        legs_out: list[StrategyLegV4] = []
        for row in legs:
            ofa_raw = json.loads(row["on_fill_action_json"])
            legs_out.append(
                StrategyLegV4(
                    id=UUID(row["strategy_leg_v4_id"]),
                    position=row["position"],
                    kind=row["kind"],
                    size_pct=row["size_pct"],
                    target_type=row["target_type"],
                    target_value=row["target_value"],
                    on_fill_action=OnFillActionV4(
                        kind=ofa_raw["kind"],
                        offset_value=ofa_raw["offset_value"],
                    ),
                )
            )

        # logical exits
        long_exits: list[StrategyLogicalExitV4] = []
        short_exits: list[StrategyLogicalExitV4] = []
        for row in logical_exits:
            ex = StrategyLogicalExitV4(
                id=UUID(row["strategy_logical_exit_v4_id"]),
                template_id=row["template_id"],
                params=json.loads(row["params_json"]),
            )
            if row["side"] == "long":
                long_exits.append(ex)
            else:
                short_exits.append(ex)

        raw_created = header["created_at"]
        if raw_created.endswith("+00:00") or raw_created.endswith("Z"):
            created_at = datetime.fromisoformat(raw_created.replace("Z", "+00:00"))
        else:
            created_at = datetime.fromisoformat(raw_created).replace(tzinfo=timezone.utc)

        header_keys = header.keys()
        raw_aliases = header["timeframe_aliases_json"] if "timeframe_aliases_json" in header_keys else "{}"
        timeframe_aliases: dict[str, str] = json.loads(raw_aliases) if raw_aliases else {}

        return StrategyVersionV4(
            id=UUID(header["strategy_version_v4_id"]),
            strategy_v4_id=UUID(header["strategy_v4_id"]),
            version=header["version"],
            name=header["name"],
            description=header["description"],
            identity=StrategyIdentityV4(
                direction=header["direction"],
                tags=tuple(json.loads(header["tags_json"])),
            ),
            default_strategy_controls_version_id=(
                UUID(header["default_strategy_controls_version_id"])
                if header["default_strategy_controls_version_id"]
                else None
            ),
            default_execution_plan_version_id=(
                UUID(header["default_execution_plan_version_id"])
                if header["default_execution_plan_version_id"]
                else None
            ),
            timeframe_aliases=timeframe_aliases,
            variables=tuple(vars_out),
            entries=StrategyEntriesV4(long=long_entry, short=short_entry),
            stops=tuple(stops_out),
            legs=tuple(legs_out),
            logical_exits=StrategyLogicalExitsV4(
                long=tuple(long_exits),
                short=tuple(short_exits),
            ),
            feature_requirements=tuple(json.loads(header["feature_requirements_json"])),
            validation_status=ValidationStatusV4(
                valid=vs_status_raw["valid"],
                errors=tuple(vs_status_raw["errors"]),
                warnings=tuple(vs_status_raw["warnings"]),
            ),
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_versions(self, strategy_v4_id: UUID) -> tuple[StrategyVersionV4, ...]:
        sid = str(strategy_v4_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT strategy_version_v4_id FROM strategy_versions_v4 WHERE strategy_v4_id = ? ORDER BY version ASC",
                (sid,),
            ).fetchall()
        return tuple(
            self.load_version(UUID(row["strategy_version_v4_id"])) for row in rows
        )

    # ------------------------------------------------------------------
    # Next version
    # ------------------------------------------------------------------

    def next_version_number(self, strategy_v4_id: UUID) -> int:
        sid = str(strategy_v4_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(version) AS max_v FROM strategy_versions_v4 WHERE strategy_v4_id = ?",
                (sid,),
            ).fetchone()
        if row is None or row["max_v"] is None:
            return 1
        return row["max_v"] + 1

    # ------------------------------------------------------------------
    # List all heads (global)
    # ------------------------------------------------------------------

    def list_all_heads(self) -> list[dict]:
        """Return one summary row per distinct strategy_v4_id (the head version).

        Each row contains:
            strategy_v4_id, name, description, head_version,
            head_version_id, total_versions, created_at, updated_at
        where created_at is the timestamp of version 1 and updated_at is the
        timestamp of the head version.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    sv.strategy_v4_id,
                    sv.name,
                    sv.description,
                    sv.version            AS head_version,
                    sv.strategy_version_v4_id AS head_version_id,
                    totals.total_versions,
                    first.created_at,
                    sv.created_at         AS updated_at
                FROM strategy_versions_v4 sv
                JOIN (
                    SELECT strategy_v4_id, MAX(version) AS max_version
                    FROM strategy_versions_v4
                    GROUP BY strategy_v4_id
                ) head ON head.strategy_v4_id = sv.strategy_v4_id
                         AND head.max_version = sv.version
                JOIN (
                    SELECT strategy_v4_id, COUNT(*) AS total_versions
                    FROM strategy_versions_v4
                    GROUP BY strategy_v4_id
                ) totals ON totals.strategy_v4_id = sv.strategy_v4_id
                JOIN (
                    SELECT strategy_v4_id, MIN(created_at) AS created_at
                    FROM strategy_versions_v4
                    GROUP BY strategy_v4_id
                ) first ON first.strategy_v4_id = sv.strategy_v4_id
                ORDER BY sv.created_at DESC
                """
            ).fetchall()
        return [
            {
                "strategy_v4_id": row["strategy_v4_id"],
                "name": row["name"],
                "description": row["description"],
                "head_version": row["head_version"],
                "head_version_id": row["head_version_id"],
                "total_versions": row["total_versions"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_strategy(self, strategy_v4_id: UUID) -> None:
        sid = str(strategy_v4_id)
        with self._connect() as conn:
            # Gather all version IDs first
            rows = conn.execute(
                "SELECT strategy_version_v4_id FROM strategy_versions_v4 WHERE strategy_v4_id = ?",
                (sid,),
            ).fetchall()
            version_ids = [row["strategy_version_v4_id"] for row in rows]

            conn.execute("BEGIN")
            try:
                for vid in version_ids:
                    conn.execute(
                        "DELETE FROM strategy_variables_v4 WHERE strategy_version_v4_id = ?",
                        (vid,),
                    )
                    conn.execute(
                        "DELETE FROM strategy_entries_v4 WHERE strategy_version_v4_id = ?",
                        (vid,),
                    )
                    conn.execute(
                        "DELETE FROM strategy_stops_v4 WHERE strategy_version_v4_id = ?",
                        (vid,),
                    )
                    conn.execute(
                        "DELETE FROM strategy_legs_v4 WHERE strategy_version_v4_id = ?",
                        (vid,),
                    )
                    conn.execute(
                        "DELETE FROM strategy_logical_exits_v4 WHERE strategy_version_v4_id = ?",
                        (vid,),
                    )
                conn.execute(
                    "DELETE FROM strategy_versions_v4 WHERE strategy_v4_id = ?",
                    (sid,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
