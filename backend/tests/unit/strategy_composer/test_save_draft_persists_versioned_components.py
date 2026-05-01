"""T-1 (Bracket Program) — `save_draft` persists StrategyControls + ExecutionPlan.

Acceptance test from `STRATEGY_TO_BROKER_BRACKET_PROGRAM.md` §3 T-1:

    "save a draft with strategy_controls.cooldown_after_loss_minutes=15 and
    execution_style.preset.kind='bracket_stop_target' with stop_pct=5,
    target_pct=10. Reload by id. Both values survive."
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backend.app.domain.execution_style import (
    BracketSpec,
    BracketStopTargetPreset,
    ExecutionMode,
    ExecutionStylePresetKind,
    OrderType,
    TimeInForce,
)
from backend.app.domain.strategy_controls import (
    AllowedDirections,
    StrategyControlsVersion,
)
from backend.app.execution_plans import ExecutionPlanRepository
from backend.app.strategies import StrategyService
from backend.app.strategies.persistence import StrategyRepository
from backend.app.strategy_composer import (
    AIComposerRequest,
    StrategyComposerService,
    StrategyDraftSaveRequest,
)
from backend.app.strategy_controls import StrategyControlsRepository


def _make_bracket_draft(composer: StrategyComposerService, *, stop_pct: float, target_pct: float, cooldown_minutes: int):
    draft = composer.compose(AIComposerRequest(prompt="green bar entry"))
    bracket_plan = draft.execution_style.model_copy(
        update={
            "execution_mode": ExecutionMode.POST_FILL_BRACKET,
            "bracket": BracketSpec(
                enabled=True,
                take_profit_r_multiple=target_pct / stop_pct,
                stop_loss_r_multiple=1.0,
            ),
            "preset": BracketStopTargetPreset(
                kind=ExecutionStylePresetKind.BRACKET_STOP_TARGET,
                stop_pct=stop_pct,
                target_pct=target_pct,
            ),
            "entry_order_type": OrderType.MARKET,
            "time_in_force": TimeInForce.DAY,
        }
    )
    controls = StrategyControlsVersion(
        id=uuid4(),
        strategy_controls_id=uuid4(),
        version=1,
        name="bracket controls",
        timeframe="5m",
        allowed_directions=AllowedDirections.LONG,
        cooldown_minutes=cooldown_minutes,
    )
    return draft.model_copy(update={"execution_style": bracket_plan, "strategy_controls": controls})


def test_save_draft_persists_strategy_controls_and_execution_plan(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    controls_repo = StrategyControlsRepository(db)
    plan_repo = ExecutionPlanRepository(db)
    composer = StrategyComposerService(
        strategy_service=StrategyService(repository=StrategyRepository(db)),
        strategy_controls_repository=controls_repo,
        execution_plan_repository=plan_repo,
    )

    draft = _make_bracket_draft(composer, stop_pct=5.0, target_pct=10.0, cooldown_minutes=15)

    response = composer.save_draft(StrategyDraftSaveRequest(draft=draft))

    assert response.strategy_controls_version_id is not None
    assert response.execution_plan_version_id is not None

    loaded_controls = controls_repo.load_version(response.strategy_controls_version_id)
    loaded_plan = plan_repo.load_version(response.execution_plan_version_id)

    assert loaded_controls.payload.cooldown_minutes == 15

    assert isinstance(loaded_plan.payload.preset, BracketStopTargetPreset)
    assert loaded_plan.payload.preset.stop_pct == 5.0
    assert loaded_plan.payload.preset.target_pct == 10.0
    assert loaded_plan.payload.execution_mode == ExecutionMode.POST_FILL_BRACKET


def test_save_draft_persists_native_alpaca_bracket_mode(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    plan_repo = ExecutionPlanRepository(db)
    composer = StrategyComposerService(
        strategy_service=StrategyService(repository=StrategyRepository(db)),
        execution_plan_repository=plan_repo,
    )
    draft = _make_bracket_draft(composer, stop_pct=5.0, target_pct=10.0, cooldown_minutes=0)
    draft = draft.model_copy(
        update={
            "execution_style": draft.execution_style.model_copy(
                update={"execution_mode": ExecutionMode.NATIVE_ALPACA_BRACKET}
            )
        }
    )

    response = composer.save_draft(StrategyDraftSaveRequest(draft=draft))
    assert response.execution_plan_version_id is not None

    loaded_plan = plan_repo.load_version(response.execution_plan_version_id)
    assert loaded_plan.payload.execution_mode == ExecutionMode.NATIVE_ALPACA_BRACKET


def test_save_draft_no_repos_is_noop_pass_through(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    composer = StrategyComposerService(
        strategy_service=StrategyService(repository=StrategyRepository(db)),
    )
    draft = _make_bracket_draft(composer, stop_pct=5.0, target_pct=10.0, cooldown_minutes=15)

    response = composer.save_draft(StrategyDraftSaveRequest(draft=draft))
    assert response.strategy_controls_version_id is None
    assert response.execution_plan_version_id is None
    assert response.strategy_version is not None
