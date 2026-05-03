"""Repository round-trip tests for StrategyV4Repository."""
from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

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
from backend.app.strategies_v4.persistence import (
    StrategyV4Repository,
    StrategyV4ValidationError,
    StrategyV4VersionNotFoundError,
)


@pytest.fixture()
def repo(tmp_path: Path) -> StrategyV4Repository:
    return StrategyV4Repository(tmp_path / "test.db")


def _make_version(
    strategy_v4_id=None,
    version=1,
    name="Test Strategy",
    with_expression_stop=False,
    with_legs=True,
    with_logical_exits=False,
) -> StrategyVersionV4:
    sid = strategy_v4_id or uuid4()
    stops = []
    if with_expression_stop:
        stops.append(
            StrategyStopV4(
                mode="expression",
                scope="all",
                expression_text="5m.atr(14) > 0",
            )
        )
    else:
        stops.append(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0))

    legs = []
    if with_legs:
        legs.append(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=3.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            )
        )

    long_exits = []
    short_exits = []
    if with_logical_exits:
        long_exits.append(
            StrategyLogicalExitV4(template_id="session_end", params={"offset_minutes": 5})
        )
        short_exits.append(
            StrategyLogicalExitV4(template_id="bars_since", params={"bars": 10})
        )

    return StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=sid,
        version=version,
        name=name,
        description="A test strategy",
        identity=StrategyIdentityV4(tags=("orb", "momentum"), direction="long"),
        variables=(
            StrategyVariableV4(
                name="fast",
                expression_text="5m.ema(9)",
                feature_requirements=("5m.ema(9)",),
            ),
        ),
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="5m.ema(9) > 5m.ema(21)",
                feature_requirements=("5m.ema(9)", "5m.ema(21)"),
            )
        ),
        stops=tuple(stops),
        legs=tuple(legs),
        logical_exits=StrategyLogicalExitsV4(
            long=tuple(long_exits), short=tuple(short_exits)
        ),
        feature_requirements=("5m.ema(9)", "5m.ema(21)"),
        validation_status=ValidationStatusV4(valid=True),
    )


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_basic(repo: StrategyV4Repository) -> None:
    v = _make_version()
    repo.save_version(v)
    loaded = repo.load_version(v.id)

    assert loaded.id == v.id
    assert loaded.strategy_v4_id == v.strategy_v4_id
    assert loaded.version == 1
    assert loaded.name == "Test Strategy"
    assert loaded.description == "A test strategy"
    assert loaded.identity.direction == "long"
    assert "orb" in loaded.identity.tags
    assert loaded.feature_requirements == ("5m.ema(9)", "5m.ema(21)")
    assert loaded.validation_status.valid is True


def test_roundtrip_variables(repo: StrategyV4Repository) -> None:
    v = _make_version()
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert len(loaded.variables) == 1
    assert loaded.variables[0].name == "fast"
    assert loaded.variables[0].expression_text == "5m.ema(9)"
    assert loaded.variables[0].compiled_blob is not None


def test_roundtrip_entries(repo: StrategyV4Repository) -> None:
    v = _make_version()
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert loaded.entries.long is not None
    assert loaded.entries.long.expression_text == "5m.ema(9) > 5m.ema(21)"
    assert loaded.entries.long.compiled_blob is not None
    assert loaded.entries.short is None


def test_roundtrip_simple_stop(repo: StrategyV4Repository) -> None:
    v = _make_version()
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert len(loaded.stops) == 1
    s = loaded.stops[0]
    assert s.mode == "simple"
    assert s.simple_type == "%"
    assert s.simple_value == 2.0


def test_roundtrip_expression_stop(repo: StrategyV4Repository) -> None:
    v = _make_version(with_expression_stop=True)
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    s = loaded.stops[0]
    assert s.mode == "expression"
    assert s.expression_text == "5m.atr(14) > 0"
    assert s.compiled_blob is not None


def test_roundtrip_legs(repo: StrategyV4Repository) -> None:
    v = _make_version()
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert len(loaded.legs) == 1
    leg = loaded.legs[0]
    assert leg.position == 1
    assert leg.kind == "target"
    assert leg.size_pct == 1.0
    assert leg.target_type == "%"
    assert leg.target_value == 3.0
    assert leg.on_fill_action.kind == "leave"
    assert leg.on_fill_action.offset_value is None


def test_roundtrip_logical_exits(repo: StrategyV4Repository) -> None:
    v = _make_version(with_logical_exits=True)
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert len(loaded.logical_exits.long) == 1
    assert loaded.logical_exits.long[0].template_id == "session_end"
    assert len(loaded.logical_exits.short) == 1
    assert loaded.logical_exits.short[0].template_id == "bars_since"


# ---------------------------------------------------------------------------
# Version uniqueness
# ---------------------------------------------------------------------------

def test_duplicate_version_rejected(repo: StrategyV4Repository) -> None:
    sid = uuid4()
    v1 = _make_version(strategy_v4_id=sid, version=1)
    v2 = _make_version(strategy_v4_id=sid, version=1, name="Same version again")
    repo.save_version(v1)
    import sqlite3
    with pytest.raises((sqlite3.IntegrityError, Exception)):
        repo.save_version(v2)


def test_multiple_versions_ok(repo: StrategyV4Repository) -> None:
    sid = uuid4()
    v1 = _make_version(strategy_v4_id=sid, version=1)
    v2 = _make_version(strategy_v4_id=sid, version=2, name="Version 2")
    repo.save_version(v1)
    repo.save_version(v2)
    versions = repo.list_versions(sid)
    assert len(versions) == 2
    assert versions[0].version == 1
    assert versions[1].version == 2


# ---------------------------------------------------------------------------
# next_version_number
# ---------------------------------------------------------------------------

def test_next_version_number_empty(repo: StrategyV4Repository) -> None:
    assert repo.next_version_number(uuid4()) == 1


def test_next_version_number_after_save(repo: StrategyV4Repository) -> None:
    sid = uuid4()
    repo.save_version(_make_version(strategy_v4_id=sid, version=1))
    assert repo.next_version_number(sid) == 2


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------

def test_load_not_found_raises(repo: StrategyV4Repository) -> None:
    with pytest.raises(StrategyV4VersionNotFoundError):
        repo.load_version(uuid4())


# ---------------------------------------------------------------------------
# delete_strategy
# ---------------------------------------------------------------------------

def test_delete_strategy_removes_all_versions(repo: StrategyV4Repository) -> None:
    sid = uuid4()
    v1 = _make_version(strategy_v4_id=sid, version=1)
    v2 = _make_version(strategy_v4_id=sid, version=2, name="V2")
    repo.save_version(v1)
    repo.save_version(v2)

    repo.delete_strategy(sid)
    assert repo.list_versions(sid) == ()
    with pytest.raises(StrategyV4VersionNotFoundError):
        repo.load_version(v1.id)


def test_delete_strategy_removes_sub_rows(repo: StrategyV4Repository, tmp_path: Path) -> None:
    import sqlite3

    sid = uuid4()
    v = _make_version(strategy_v4_id=sid, version=1, with_logical_exits=True)
    repo.save_version(v)
    repo.delete_strategy(sid)

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for table in [
        "strategy_variables_v4",
        "strategy_entries_v4",
        "strategy_stops_v4",
        "strategy_legs_v4",
        "strategy_logical_exits_v4",
    ]:
        count = conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE strategy_version_v4_id = ?", (str(v.id),)).fetchone()["n"]  # noqa: S608
        assert count == 0, f"sub-rows remain in {table}"
    conn.close()


def test_delete_nonexistent_is_noop(repo: StrategyV4Repository) -> None:
    repo.delete_strategy(uuid4())  # should not raise


# ---------------------------------------------------------------------------
# Invalid expression rejected at save
# ---------------------------------------------------------------------------

def test_save_invalid_expression_rejected(repo: StrategyV4Repository) -> None:
    v = _make_version()
    # Override entry with invalid expression by building the object directly
    bad_entry = StrategyEntryV4(expression_text="!!! not valid !!!")
    bad_v = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="bad",
        entries=StrategyEntriesV4(long=bad_entry),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0),),
        legs=(),
        validation_status=ValidationStatusV4(valid=True),
    )
    with pytest.raises(StrategyV4ValidationError):
        repo.save_version(bad_v)
