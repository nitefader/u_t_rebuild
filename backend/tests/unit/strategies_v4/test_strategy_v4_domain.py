"""Unit tests for StrategyVersionV4 pydantic validators."""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from uuid import uuid4

from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyIdentityV4,
    StrategyLegV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVariableV4,
    StrategyVersionV4,
    ValidationStatusV4,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_stop() -> StrategyStopV4:
    return StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0)


def _entry() -> StrategyEntryV4:
    return StrategyEntryV4(expression_text="5m.ema(9) > 5m.ema(21)")


def _entries_long() -> StrategyEntriesV4:
    return StrategyEntriesV4(long=_entry())


def _leg(position: int = 1, kind: str = "target", size_pct: float = 1.0) -> StrategyLegV4:
    return StrategyLegV4(
        position=position,
        kind=kind,
        size_pct=size_pct,
        target_type="%",
        target_value=3.0,
        on_fill_action=OnFillActionV4(kind="leave"),
    )


def _minimal_version(**overrides) -> StrategyVersionV4:
    defaults = dict(
        version=1,
        name="Test",
        entries=_entries_long(),
        stops=(_simple_stop(),),
        legs=(_leg(),),
    )
    defaults.update(overrides)
    return StrategyVersionV4(**defaults)


# ---------------------------------------------------------------------------
# entries validator
# ---------------------------------------------------------------------------

def test_entries_requires_at_least_one() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        StrategyEntriesV4(long=None, short=None)


def test_entries_long_only_ok() -> None:
    e = StrategyEntriesV4(long=_entry())
    assert e.long is not None
    assert e.short is None


def test_entries_both_ok() -> None:
    e = StrategyEntriesV4(long=_entry(), short=_entry())
    assert e.long is not None
    assert e.short is not None


# ---------------------------------------------------------------------------
# stops validator
# ---------------------------------------------------------------------------

def test_version_requires_at_least_one_stop() -> None:
    with pytest.raises(ValidationError, match="at least one stop"):
        _minimal_version(stops=())


def test_stop_simple_requires_type_and_value() -> None:
    with pytest.raises(ValidationError, match="simple_type required"):
        StrategyStopV4(mode="simple", scope="all")


def test_stop_expression_requires_text() -> None:
    with pytest.raises(ValidationError, match="expression_text required"):
        StrategyStopV4(mode="expression", scope="all")


def test_stop_expression_ok() -> None:
    s = StrategyStopV4(mode="expression", scope="all", expression_text="1m.atr(14) > 0")
    assert s.expression_text is not None


# ---------------------------------------------------------------------------
# legs validator
# ---------------------------------------------------------------------------

def test_legs_sum_must_be_one() -> None:
    with pytest.raises(ValidationError, match="sum of leg size_pct"):
        _minimal_version(
            legs=(
                _leg(position=1, size_pct=0.6),
                _leg(position=2, size_pct=0.5),
            )
        )


def test_legs_sum_exactly_one_ok() -> None:
    v = _minimal_version(
        legs=(
            _leg(position=1, size_pct=0.6),
            StrategyLegV4(
                position=2,
                kind="target",
                size_pct=0.4,
                target_type="%",
                target_value=6.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        )
    )
    assert len(v.legs) == 2


def test_legs_non_contiguous_positions_rejected() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        _minimal_version(
            legs=(
                _leg(position=1, size_pct=0.5),
                StrategyLegV4(
                    position=3,  # gap
                    kind="target",
                    size_pct=0.5,
                    target_type="%",
                    target_value=6.0,
                    on_fill_action=OnFillActionV4(kind="leave"),
                ),
            )
        )


def test_at_most_one_runner() -> None:
    with pytest.raises(ValidationError, match="at most one runner"):
        _minimal_version(
            legs=(
                StrategyLegV4(
                    position=1, kind="runner", size_pct=0.5,
                    target_type="trail-%", target_value=None,
                    on_fill_action=OnFillActionV4(kind="leave"),
                ),
                StrategyLegV4(
                    position=2, kind="runner", size_pct=0.5,
                    target_type="trail-%", target_value=None,
                    on_fill_action=OnFillActionV4(kind="leave"),
                ),
            )
        )


def test_empty_legs_allowed() -> None:
    v = _minimal_version(legs=())
    assert v.legs == ()


# ---------------------------------------------------------------------------
# variable uniqueness
# ---------------------------------------------------------------------------

def test_variable_names_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="variable name 'x' appears more than once"):
        _minimal_version(
            variables=(
                StrategyVariableV4(name="x", expression_text="5m.ema(9)"),
                StrategyVariableV4(name="x", expression_text="5m.ema(21)"),
            )
        )


def test_variable_names_unique_ok() -> None:
    v = _minimal_version(
        variables=(
            StrategyVariableV4(name="fast", expression_text="5m.ema(9)"),
            StrategyVariableV4(name="slow", expression_text="5m.ema(21)"),
        )
    )
    assert len(v.variables) == 2


# ---------------------------------------------------------------------------
# on_fill_action offset rules
# ---------------------------------------------------------------------------

def test_on_fill_be_exact_no_offset() -> None:
    a = OnFillActionV4(kind="be_exact", offset_value=None)
    assert a.offset_value is None


def test_on_fill_be_exact_with_offset_rejected() -> None:
    with pytest.raises(ValidationError, match="offset_value must be None"):
        OnFillActionV4(kind="be_exact", offset_value=0.5)


def test_on_fill_leave_no_offset() -> None:
    a = OnFillActionV4(kind="leave", offset_value=None)
    assert a.offset_value is None


def test_on_fill_be_plus_requires_offset() -> None:
    with pytest.raises(ValidationError, match="offset_value required"):
        OnFillActionV4(kind="be_plus", offset_value=None)


def test_on_fill_tighten_atr_requires_offset() -> None:
    with pytest.raises(ValidationError, match="offset_value required"):
        OnFillActionV4(kind="tighten_atr", offset_value=None)


def test_on_fill_be_minus_with_offset_ok() -> None:
    a = OnFillActionV4(kind="be_minus", offset_value=0.25)
    assert a.offset_value == 0.25


# ---------------------------------------------------------------------------
# validation_status default
# ---------------------------------------------------------------------------

def test_validation_status_default() -> None:
    v = _minimal_version()
    assert v.validation_status.valid is True
    assert v.validation_status.errors == ()
