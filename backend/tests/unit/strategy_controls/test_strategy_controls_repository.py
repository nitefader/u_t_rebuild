"""T-1 (Bracket Program) — StrategyControlsRepository reload-survival tests."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.domain.strategy_controls import (
    AllowedDirections,
    StrategyControlsVersion,
)
from backend.app.strategy_controls import (
    StrategyControlsRepository,
    StrategyControlsVersionNotFoundError,
)


def _make_controls(*, version: int = 1, strategy_controls_id=None) -> StrategyControlsVersion:
    return StrategyControlsVersion(
        id=uuid4(),
        strategy_controls_id=strategy_controls_id or uuid4(),
        version=version,
        name=f"controls v{version}",
        timeframe="5m",
        allowed_directions=AllowedDirections.LONG,
        cooldown_minutes=15,
        max_trades_per_session=3,
    )


def test_save_and_load_strategy_controls_version_roundtrip(tmp_path: Path) -> None:
    repo = StrategyControlsRepository(tmp_path / "test.db")
    controls = _make_controls()

    repo.save_version(controls)

    loaded = repo.load_version(controls.id)

    assert loaded.payload.id == controls.id
    assert loaded.payload.cooldown_minutes == 15
    assert loaded.payload.max_trades_per_session == 3


def test_load_version_raises_when_missing(tmp_path: Path) -> None:
    repo = StrategyControlsRepository(tmp_path / "test.db")
    with pytest.raises(StrategyControlsVersionNotFoundError):
        repo.load_version(uuid4())


def test_versions_are_immutable_unique_per_strategy_controls_id(tmp_path: Path) -> None:
    """Two writes with same strategy_controls_id + version must collide.

    Edits create new ``version`` values; the (id, version) pair is UNIQUE.
    """

    repo = StrategyControlsRepository(tmp_path / "test.db")
    sc_id = uuid4()
    v1 = _make_controls(version=1, strategy_controls_id=sc_id)
    v1_collision = _make_controls(version=1, strategy_controls_id=sc_id)

    repo.save_version(v1)
    with pytest.raises(Exception):
        repo.save_version(v1_collision)


def test_next_version_number_increments(tmp_path: Path) -> None:
    repo = StrategyControlsRepository(tmp_path / "test.db")
    sc_id = uuid4()
    assert repo.next_version_number(sc_id) == 1

    repo.save_version(_make_controls(version=1, strategy_controls_id=sc_id))
    assert repo.next_version_number(sc_id) == 2

    repo.save_version(_make_controls(version=2, strategy_controls_id=sc_id))
    assert repo.next_version_number(sc_id) == 3


def test_list_versions_orders_by_version(tmp_path: Path) -> None:
    repo = StrategyControlsRepository(tmp_path / "test.db")
    sc_id = uuid4()
    repo.save_version(_make_controls(version=1, strategy_controls_id=sc_id))
    repo.save_version(_make_controls(version=2, strategy_controls_id=sc_id))
    repo.save_version(_make_controls(version=3, strategy_controls_id=sc_id))

    rows = repo.list_versions(sc_id)
    assert [r.payload.version for r in rows] == [1, 2, 3]


def test_reload_survives_process_restart(tmp_path: Path) -> None:
    """Persistence is durable across repository instances on the same DB."""

    db = tmp_path / "test.db"
    sc_id = uuid4()
    repo1 = StrategyControlsRepository(db)
    payload = _make_controls(version=1, strategy_controls_id=sc_id)
    repo1.save_version(payload)

    repo2 = StrategyControlsRepository(db)
    loaded = repo2.load_version(payload.id)

    assert loaded.payload.cooldown_minutes == 15
    assert loaded.payload.strategy_controls_id == sc_id
