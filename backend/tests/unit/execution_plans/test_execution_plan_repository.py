"""T-1 (Bracket Program) — ExecutionPlanRepository reload-survival tests."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.domain.execution_style import (
    BracketSpec,
    BracketStopTargetPreset,
    ExecutionMode,
    ExecutionStylePresetKind,
    ExecutionStyleVersion,
    OrderType,
    TimeInForce,
)
from backend.app.execution_plans import (
    ExecutionPlanRepository,
    ExecutionPlanVersionNotFoundError,
)


def _make_plan(
    *,
    version: int = 1,
    execution_style_id=None,
    execution_mode: ExecutionMode = ExecutionMode.POST_FILL_BRACKET,
    stop_pct: float = 5.0,
    target_pct: float = 10.0,
) -> ExecutionStyleVersion:
    return ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=execution_style_id or uuid4(),
        version=version,
        name=f"plan v{version}",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=execution_mode,
        bracket=BracketSpec(
            enabled=True,
            take_profit_r_multiple=target_pct / stop_pct,
            stop_loss_r_multiple=1.0,
        ),
        preset=BracketStopTargetPreset(
            kind=ExecutionStylePresetKind.BRACKET_STOP_TARGET,
            stop_pct=stop_pct,
            target_pct=target_pct,
        ),
    )


def test_save_and_load_execution_plan_version_roundtrip(tmp_path: Path) -> None:
    repo = ExecutionPlanRepository(tmp_path / "test.db")
    plan = _make_plan()

    repo.save_version(plan)
    loaded = repo.load_version(plan.id)

    assert loaded.payload.id == plan.id
    assert loaded.payload.execution_mode == ExecutionMode.POST_FILL_BRACKET
    assert isinstance(loaded.payload.preset, BracketStopTargetPreset)
    assert loaded.payload.preset.stop_pct == 5.0
    assert loaded.payload.preset.target_pct == 10.0


def test_native_alpaca_bracket_mode_round_trips(tmp_path: Path) -> None:
    repo = ExecutionPlanRepository(tmp_path / "test.db")
    plan = _make_plan(execution_mode=ExecutionMode.NATIVE_ALPACA_BRACKET)

    repo.save_version(plan)
    loaded = repo.load_version(plan.id)

    assert loaded.payload.execution_mode == ExecutionMode.NATIVE_ALPACA_BRACKET


def test_load_version_raises_when_missing(tmp_path: Path) -> None:
    repo = ExecutionPlanRepository(tmp_path / "test.db")
    with pytest.raises(ExecutionPlanVersionNotFoundError):
        repo.load_version(uuid4())


def test_versions_are_immutable_unique_per_execution_plan_id(tmp_path: Path) -> None:
    repo = ExecutionPlanRepository(tmp_path / "test.db")
    plan_id = uuid4()
    v1 = _make_plan(version=1, execution_style_id=plan_id)
    v1_collision = _make_plan(version=1, execution_style_id=plan_id)

    repo.save_version(v1)
    with pytest.raises(Exception):
        repo.save_version(v1_collision)


def test_next_version_number_increments(tmp_path: Path) -> None:
    repo = ExecutionPlanRepository(tmp_path / "test.db")
    plan_id = uuid4()
    assert repo.next_version_number(plan_id) == 1

    repo.save_version(_make_plan(version=1, execution_style_id=plan_id))
    assert repo.next_version_number(plan_id) == 2


def test_reload_survives_process_restart(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    plan_id = uuid4()
    repo1 = ExecutionPlanRepository(db)
    plan = _make_plan(version=1, execution_style_id=plan_id, stop_pct=5.0, target_pct=10.0)
    repo1.save_version(plan)

    repo2 = ExecutionPlanRepository(db)
    loaded = repo2.load_version(plan.id)

    assert isinstance(loaded.payload.preset, BracketStopTargetPreset)
    assert loaded.payload.preset.stop_pct == 5.0
    assert loaded.payload.preset.target_pct == 10.0
    assert loaded.payload.execution_style_id == plan_id
