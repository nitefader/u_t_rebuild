"""Tests for new StrategyControls fields (A.2 max_consecutive_losses_halt,
A.3 skip_power_hour, A.4 day_of_week_restrictions).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.domain.strategy_controls import AllowedDirections, Weekday
from backend.app.strategy_controls.persistence import StrategyControlsRepository
from backend.app.strategy_controls.registry import StrategyControlsRegistry
from backend.app.strategy_controls.service import StrategyControlsService
from backend.app.strategy_controls.service_models import StrategyControlsDraft
from backend.app.deployments.persistence import DeploymentRepository


def _make_service(tmp_path: Path) -> StrategyControlsService:
    db = tmp_path / "test.db"
    return StrategyControlsService(
        repository=StrategyControlsRepository(db),
        registry=StrategyControlsRegistry(db),
        deployment_repository=DeploymentRepository(db),
    )


def _full_draft(**overrides) -> StrategyControlsDraft:
    defaults = dict(
        name="New Fields Test",
        timeframe="1d",
        allowed_directions=AllowedDirections.LONG,
        max_consecutive_losses_halt=3,
        skip_power_hour=True,
        day_of_week_restrictions=[Weekday.WED, Weekday.FRI],
    )
    defaults.update(overrides)
    return StrategyControlsDraft(**defaults)


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

def test_max_consecutive_losses_halt_positive() -> None:
    d = _full_draft(max_consecutive_losses_halt=5)
    assert d.max_consecutive_losses_halt == 5


def test_max_consecutive_losses_halt_none_ok() -> None:
    d = _full_draft(max_consecutive_losses_halt=None)
    assert d.max_consecutive_losses_halt is None


def test_max_consecutive_losses_halt_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        _full_draft(max_consecutive_losses_halt=0)


def test_skip_power_hour_default_false() -> None:
    d = StrategyControlsDraft(name="x", timeframe="5m")
    assert d.skip_power_hour is False


def test_skip_power_hour_true() -> None:
    d = _full_draft(skip_power_hour=True)
    assert d.skip_power_hour is True


def test_day_of_week_restrictions_sorted_mon_to_fri() -> None:
    d = _full_draft(day_of_week_restrictions=[Weekday.FRI, Weekday.MON, Weekday.WED])
    assert list(d.day_of_week_restrictions) == [Weekday.MON, Weekday.WED, Weekday.FRI]


def test_day_of_week_restrictions_deduplicates() -> None:
    d = _full_draft(day_of_week_restrictions=[Weekday.MON, Weekday.MON, Weekday.TUE])
    assert list(d.day_of_week_restrictions) == [Weekday.MON, Weekday.TUE]


def test_day_of_week_restrictions_empty_ok() -> None:
    d = _full_draft(day_of_week_restrictions=[])
    assert d.day_of_week_restrictions == []


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

def test_roundtrip_all_new_fields(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _full_draft(
        max_consecutive_losses_halt=3,
        skip_power_hour=True,
        day_of_week_restrictions=[Weekday.WED, Weekday.FRI],
    )
    record = svc.create(draft.name, draft)
    loaded_record = svc.get_library(record.payload.strategy_controls_id).head
    payload = loaded_record.payload

    assert payload.max_consecutive_losses_halt == 3
    assert payload.skip_power_hour is True
    assert Weekday.WED in payload.day_of_week_restrictions
    assert Weekday.FRI in payload.day_of_week_restrictions


def test_roundtrip_new_fields_defaults(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = StrategyControlsDraft(name="Defaults Test", timeframe="5m")
    record = svc.create(draft.name, draft)
    loaded = svc.get_library(record.payload.strategy_controls_id).head.payload

    assert loaded.max_consecutive_losses_halt is None
    assert loaded.skip_power_hour is False
    assert len(loaded.day_of_week_restrictions) == 0
