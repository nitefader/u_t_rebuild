"""Service-layer tests for StrategyV4Service."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.strategies_v4.models import (
    OnFillActionV4Draft,
    StrategyEntriesV4Draft,
    StrategyEntryV4Draft,
    StrategyIdentityV4Draft,
    StrategyLegV4Draft,
    StrategyLogicalExitV4Draft,
    StrategyLogicalExitsV4Draft,
    StrategyStopV4Draft,
    StrategyVariableV4Draft,
    StrategyVersionV4Draft,
)
from backend.app.strategies_v4.persistence import (
    StrategyV4Repository,
    StrategyV4ValidationError,
)
from backend.app.strategies_v4.service import StrategyV4Service


@pytest.fixture()
def svc(tmp_path: Path) -> StrategyV4Service:
    repo = StrategyV4Repository(tmp_path / "test.db")
    return StrategyV4Service(repo)


def _simple_draft(name: str = "My Strategy") -> StrategyVersionV4Draft:
    return StrategyVersionV4Draft(
        name=name,
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="5m.ema(9) > 5m.ema(21)")
        ),
        stops=[StrategyStopV4Draft(mode="simple", scope="all", simple_type="%", simple_value=2.0)],
        legs=[
            StrategyLegV4Draft(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=3.0,
                on_fill_action=OnFillActionV4Draft(kind="leave"),
            )
        ],
    )


def _invalid_draft() -> StrategyVersionV4Draft:
    return StrategyVersionV4Draft(
        name="Bad",
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="!!! not valid !!!")
        ),
        stops=[StrategyStopV4Draft(mode="simple", scope="all", simple_type="%", simple_value=2.0)],
    )


# ---------------------------------------------------------------------------
# validate_draft
# ---------------------------------------------------------------------------

def test_validate_draft_valid(svc: StrategyV4Service) -> None:
    status = svc.validate_draft(_simple_draft())
    assert status.valid is True
    assert status.errors == ()


def test_validate_draft_invalid_expression(svc: StrategyV4Service) -> None:
    status = svc.validate_draft(_invalid_draft())
    assert status.valid is False
    assert len(status.errors) > 0


def test_validate_draft_variable_valid(svc: StrategyV4Service) -> None:
    draft = StrategyVersionV4Draft(
        name="With var",
        variables=[StrategyVariableV4Draft(name="fast", expression_text="5m.ema(9)")],
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="5m.ema(9) > 5m.ema(21)")
        ),
        stops=[StrategyStopV4Draft(mode="simple", scope="all", simple_type="%", simple_value=2.0)],
    )
    status = svc.validate_draft(draft)
    assert status.valid is True


def test_validate_draft_variable_invalid_expression(svc: StrategyV4Service) -> None:
    draft = StrategyVersionV4Draft(
        name="Bad var",
        variables=[StrategyVariableV4Draft(name="x", expression_text="@@INVALID@@")],
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="5m.ema(9) > 5m.ema(21)")
        ),
        stops=[StrategyStopV4Draft(mode="simple", scope="all", simple_type="%", simple_value=2.0)],
    )
    status = svc.validate_draft(draft)
    assert status.valid is False
    assert any("variable 'x'" in e for e in status.errors)


def test_validate_draft_timeframe_variable_invalid_literal(svc: StrategyV4Service) -> None:
    draft = StrategyVersionV4Draft(
        name="Bad tf literal",
        variables=[
            StrategyVariableV4Draft(
                name="sig_tf",
                expression_text=" bogus ",
                kind="timeframe",
            ),
        ],
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="5m.ema(9) > 5m.ema(21)")
        ),
        stops=[StrategyStopV4Draft(mode="simple", scope="all", simple_type="%", simple_value=2.0)],
    )
    status = svc.validate_draft(draft)
    assert status.valid is False


def test_validate_draft_expression_stop(svc: StrategyV4Service) -> None:
    draft = StrategyVersionV4Draft(
        name="Expr stop",
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="5m.ema(9) > 5m.ema(21)")
        ),
        stops=[
            StrategyStopV4Draft(mode="expression", scope="all", expression_text="5m.atr(14) > 0")
        ],
    )
    status = svc.validate_draft(draft)
    assert status.valid is True


# ---------------------------------------------------------------------------
# save — create
# ---------------------------------------------------------------------------

def test_save_create(svc: StrategyV4Service) -> None:
    version = svc.save(_simple_draft())
    assert version.version == 1
    assert version.name == "My Strategy"
    assert version.validation_status.valid is True


def test_save_rejects_invalid(svc: StrategyV4Service) -> None:
    with pytest.raises(StrategyV4ValidationError):
        svc.save(_invalid_draft())


def test_save_feature_requirements_aggregated(svc: StrategyV4Service) -> None:
    version = svc.save(_simple_draft())
    assert "5m.ema(9)" in version.feature_requirements
    assert "5m.ema(21)" in version.feature_requirements


def test_save_feature_requirements_include_simple_atr_stop_and_target(svc: StrategyV4Service) -> None:
    draft = StrategyVersionV4Draft(
        name="ATR protected",
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(expression_text="5m.close < 5m.open")
        ),
        stops=[
            StrategyStopV4Draft(
                mode="simple",
                scope="all",
                simple_type="ATR",
                simple_value=2.0,
            )
        ],
        legs=[
            StrategyLegV4Draft(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="ATR",
                target_value=4.0,
                on_fill_action=OnFillActionV4Draft(kind="leave"),
            )
        ],
    )

    version = svc.save(draft)

    assert "atr:length=14[0]" in version.feature_requirements
    assert version.stops[0].feature_requirements == ("atr:length=14[0]",)


def test_save_with_timeframe_variable(svc: StrategyV4Service) -> None:
    draft = StrategyVersionV4Draft(
        name="Tf strat",
        variables=[
            StrategyVariableV4Draft(
                name="sig_tf",
                expression_text="5m",
                kind="timeframe",
            ),
        ],
        entries=StrategyEntriesV4Draft(
            long=StrategyEntryV4Draft(
                expression_text="sig_tf.ema(9) crosses_above sig_tf.ema(21)"
            ),
        ),
        stops=[StrategyStopV4Draft(mode="simple", scope="all", simple_type="%", simple_value=2.0)],
    )
    saved = svc.save(draft)
    assert saved.variables[0].kind == "timeframe"
    assert saved.variables[0].expression_text == "5m"
    loaded = svc.get(saved.id)
    assert loaded.variables[0].kind == "timeframe"
    assert "5m.ema(9)" in loaded.feature_requirements


# ---------------------------------------------------------------------------
# save — edit (version+1)
# ---------------------------------------------------------------------------

def test_save_edit_increments_version(svc: StrategyV4Service) -> None:
    v1 = svc.save(_simple_draft())
    v2 = svc.save(_simple_draft("Updated"), strategy_v4_id=v1.strategy_v4_id)
    assert v2.version == 2
    assert v2.strategy_v4_id == v1.strategy_v4_id
    assert v2.name == "Updated"


def test_save_edit_preserves_old_version(svc: StrategyV4Service) -> None:
    v1 = svc.save(_simple_draft())
    svc.save(_simple_draft("V2"), strategy_v4_id=v1.strategy_v4_id)
    loaded_v1 = svc.get(v1.id)
    assert loaded_v1.version == 1


# ---------------------------------------------------------------------------
# get / list
# ---------------------------------------------------------------------------

def test_get_returns_correct_version(svc: StrategyV4Service) -> None:
    v = svc.save(_simple_draft())
    loaded = svc.get(v.id)
    assert loaded.id == v.id


def test_list_returns_versions_ordered(svc: StrategyV4Service) -> None:
    v1 = svc.save(_simple_draft())
    v2 = svc.save(_simple_draft("V2"), strategy_v4_id=v1.strategy_v4_id)
    versions = svc.list(v1.strategy_v4_id)
    assert len(versions) == 2
    assert versions[0].version == 1
    assert versions[1].version == 2


# ---------------------------------------------------------------------------
# duplicate
# ---------------------------------------------------------------------------

def test_duplicate_creates_new_strategy(svc: StrategyV4Service) -> None:
    v = svc.save(_simple_draft())
    dup = svc.duplicate(v.id, new_name="Copy")
    assert dup.strategy_v4_id != v.strategy_v4_id
    assert dup.version == 1
    assert dup.name == "Copy"


def test_duplicate_preserves_entries(svc: StrategyV4Service) -> None:
    v = svc.save(_simple_draft())
    dup = svc.duplicate(v.id, new_name="Copy")
    assert dup.entries.long is not None
    assert dup.entries.long.expression_text == "5m.ema(9) > 5m.ema(21)"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

def test_delete_removes_strategy(svc: StrategyV4Service) -> None:
    v = svc.save(_simple_draft())
    sid = v.strategy_v4_id
    svc.delete(sid)
    assert svc.list(sid) == ()


def test_delete_when_bound_raises_in_use_error(tmp_path: Path) -> None:
    """Delete of a strategy bound by a Deployment must raise StrategyV4InUseError."""
    from pathlib import Path as _Path

    from backend.app.deployments.persistence import DeploymentRepository
    from backend.app.deployments.models import DeploymentWriteRequest, Deployment
    from backend.app.domain._base import utc_now
    from backend.app.strategies_v4.service import StrategyV4InUseError
    from uuid import uuid4 as _uuid4

    db_path = tmp_path / "shared.db"
    v4_repo = StrategyV4Repository(db_path)
    dep_repo = DeploymentRepository(db_path)
    local_svc = StrategyV4Service(v4_repo)

    # Save a strategy
    version = local_svc.save(_simple_draft())
    v4_id = version.strategy_v4_id

    # Bind it in a deployment (using v4 FK)
    from backend.app.deployments.service import DeploymentService
    dep_svc = DeploymentService(repository=dep_repo)
    dep_svc.create_deployment(
        DeploymentWriteRequest(
            name="Bound Deployment",
            strategy_version_v4_id=version.id,
            watchlist_ids=(_uuid4(),),
            subscribed_account_ids=(_uuid4(),),
        )
    )

    # Attempt delete with deployment_repo guard — must fail
    with pytest.raises(StrategyV4InUseError) as exc_info:
        local_svc.delete(v4_id, deployment_repo=dep_repo)

    assert len(exc_info.value.deployment_ids) == 1


def test_delete_without_deployment_repo_skips_guard(svc: StrategyV4Service) -> None:
    """When no deployment_repo is passed, the guard is skipped (test isolation)."""
    v = svc.save(_simple_draft())
    sid = v.strategy_v4_id
    svc.delete(sid)  # no deployment_repo — should succeed
    assert svc.list(sid) == ()


# ---------------------------------------------------------------------------
# Compiled bytes round-trip
# ---------------------------------------------------------------------------

def test_compiled_ast_round_trips(svc: StrategyV4Service) -> None:
    """Verify that the compiled bytes saved to DB load back via load_compiled."""
    from backend.app.strategies.expression_api import load_compiled

    v = svc.save(_simple_draft())
    loaded = svc.get(v.id)
    assert loaded.entries.long is not None
    assert loaded.entries.long.compiled_blob is not None
    compiled = load_compiled(
        loaded.entries.long.expression_text,
        loaded.entries.long.compiled_blob,
    )
    assert compiled is not None
