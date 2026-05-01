"""Tests for StrategyVersionV4.timeframe_aliases field (A.1)."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyIdentityV4,
    StrategyLegV4,
    StrategyStopV4,
    StrategyVersionV4,
    ValidationStatusV4,
)
from backend.app.strategies_v4.models import StrategyVersionV4Draft
from backend.app.strategies_v4.persistence import StrategyV4Repository


# ---------------------------------------------------------------------------
# Domain validator tests
# ---------------------------------------------------------------------------

def _minimal_version(**overrides) -> StrategyVersionV4:
    defaults = dict(
        version=1,
        name="Test",
        entries=StrategyEntriesV4(long=StrategyEntryV4(expression_text="5m.ema(9) > 5m.ema(21)")),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0),),
        legs=(StrategyLegV4(
            position=1, kind="target", size_pct=1.0,
            target_type="%", target_value=3.0,
            on_fill_action=OnFillActionV4(kind="leave"),
        ),),
    )
    defaults.update(overrides)
    return StrategyVersionV4(**defaults)


def test_timeframe_aliases_default_empty() -> None:
    v = _minimal_version()
    assert v.timeframe_aliases == {}


def test_timeframe_aliases_valid() -> None:
    v = _minimal_version(timeframe_aliases={"htf": "1h", "daily": "1d"})
    assert v.timeframe_aliases == {"htf": "1h", "daily": "1d"}


def test_timeframe_aliases_valid_week() -> None:
    v = _minimal_version(timeframe_aliases={"weekly": "1w"})
    assert v.timeframe_aliases["weekly"] == "1w"


def test_timeframe_aliases_invalid_key_uppercase() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases key"):
        _minimal_version(timeframe_aliases={"HTF": "1h"})


def test_timeframe_aliases_invalid_key_starts_with_digit() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases key"):
        _minimal_version(timeframe_aliases={"1tf": "5m"})


def test_timeframe_aliases_invalid_value_no_unit() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases value"):
        _minimal_version(timeframe_aliases={"htf": "60"})


def test_timeframe_aliases_invalid_value_wrong_unit() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases value"):
        _minimal_version(timeframe_aliases={"htf": "1s"})


def test_timeframe_aliases_invalid_value_float() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases value"):
        _minimal_version(timeframe_aliases={"htf": "1.5h"})


# ---------------------------------------------------------------------------
# Draft validator tests
# ---------------------------------------------------------------------------

def _minimal_draft(**overrides) -> StrategyVersionV4Draft:
    defaults = dict(
        name="Test",
        entries={"long": {"expression_text": "5m.ema(9) > 5m.ema(21)"}},
        stops=[{"mode": "simple", "scope": "all", "simple_type": "%", "simple_value": 2.0}],
    )
    defaults.update(overrides)
    return StrategyVersionV4Draft(**defaults)


def test_draft_timeframe_aliases_default() -> None:
    d = _minimal_draft()
    assert d.timeframe_aliases == {}


def test_draft_timeframe_aliases_valid() -> None:
    d = _minimal_draft(timeframe_aliases={"htf": "4h", "ltf": "5m"})
    assert d.timeframe_aliases == {"htf": "4h", "ltf": "5m"}


def test_draft_timeframe_aliases_invalid_key() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases key"):
        _minimal_draft(timeframe_aliases={"Bad Key": "1h"})


def test_draft_timeframe_aliases_invalid_value() -> None:
    with pytest.raises(ValidationError, match="timeframe_aliases value"):
        _minimal_draft(timeframe_aliases={"htf": "1hour"})


# ---------------------------------------------------------------------------
# Repository round-trip tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path: Path) -> StrategyV4Repository:
    return StrategyV4Repository(tmp_path / "test.db")


def _make_version(aliases: dict[str, str]) -> StrategyVersionV4:
    return StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="Alias Test",
        description=None,
        identity=StrategyIdentityV4(direction="long"),
        timeframe_aliases=aliases,
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(expression_text="5m.ema(9) > 5m.ema(21)")
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0),),
        legs=(StrategyLegV4(
            position=1, kind="target", size_pct=1.0,
            target_type="%", target_value=3.0,
            on_fill_action=OnFillActionV4(kind="leave"),
        ),),
        validation_status=ValidationStatusV4(valid=True),
    )


def test_repository_roundtrip_alias_map(repo: StrategyV4Repository) -> None:
    v = _make_version({"htf": "1h", "ltf": "5m"})
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert loaded.timeframe_aliases == {"htf": "1h", "ltf": "5m"}


def test_repository_roundtrip_empty_aliases(repo: StrategyV4Repository) -> None:
    v = _make_version({})
    repo.save_version(v)
    loaded = repo.load_version(v.id)
    assert loaded.timeframe_aliases == {}
