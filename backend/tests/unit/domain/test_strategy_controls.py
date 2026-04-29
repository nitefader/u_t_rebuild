from __future__ import annotations

from datetime import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain import (
    AllowedDirections,
    SessionPreference,
    StrategyControlsVersion,
    TradingHorizon,
)


def _kwargs(**overrides):
    base = {
        "id": uuid4(),
        "strategy_controls_id": uuid4(),
        "version": 1,
        "name": "Test Controls",
        "timeframe": "5m",
    }
    base.update(overrides)
    return base


def test_defaults_match_safe_baseline() -> None:
    controls = StrategyControlsVersion(**_kwargs())

    assert controls.trading_horizon == TradingHorizon.INTRADAY
    assert controls.allowed_directions == AllowedDirections.LONG
    assert controls.session_preference == SessionPreference.REGULAR_ONLY
    assert controls.higher_timeframe_confirmation_required is False
    assert controls.earnings_news_blackout_enabled is False
    assert controls.avoid_first_minutes is None
    assert controls.no_new_entries_after is None
    assert controls.force_flat_by is None
    assert controls.time_based_exit_after_bars is None
    assert controls.time_based_exit_after_minutes is None
    assert controls.time_based_exit_after_days is None


def test_all_horizons_directions_session_preferences_round_trip() -> None:
    for horizon in TradingHorizon:
        for direction in AllowedDirections:
            for session in SessionPreference:
                controls = StrategyControlsVersion(
                    **_kwargs(
                        trading_horizon=horizon,
                        allowed_directions=direction,
                        session_preference=session,
                    )
                )
                assert controls.trading_horizon == horizon
                assert controls.allowed_directions == direction
                assert controls.session_preference == session


def test_time_based_exit_units_are_mutually_exclusive() -> None:
    StrategyControlsVersion(**_kwargs(time_based_exit_after_bars=10))
    StrategyControlsVersion(**_kwargs(time_based_exit_after_minutes=30))
    StrategyControlsVersion(**_kwargs(time_based_exit_after_days=1))

    with pytest.raises(ValidationError, match="time-based exit accepts at most one"):
        StrategyControlsVersion(
            **_kwargs(time_based_exit_after_bars=10, time_based_exit_after_minutes=30)
        )

    with pytest.raises(ValidationError, match="time-based exit accepts at most one"):
        StrategyControlsVersion(
            **_kwargs(time_based_exit_after_minutes=30, time_based_exit_after_days=1)
        )


def test_time_based_exit_units_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        StrategyControlsVersion(**_kwargs(time_based_exit_after_bars=0))

    with pytest.raises(ValidationError):
        StrategyControlsVersion(**_kwargs(time_based_exit_after_minutes=-5))


def test_force_flat_must_be_at_or_after_no_new_entries() -> None:
    StrategyControlsVersion(
        **_kwargs(
            no_new_entries_after=time(15, 30),
            force_flat_by=time(15, 55),
        )
    )

    StrategyControlsVersion(
        **_kwargs(
            no_new_entries_after=time(15, 30),
            force_flat_by=time(15, 30),
        )
    )

    with pytest.raises(ValidationError, match="force_flat_by must be at or after"):
        StrategyControlsVersion(
            **_kwargs(
                no_new_entries_after=time(15, 55),
                force_flat_by=time(15, 30),
            )
        )


def test_avoid_first_minutes_must_be_non_negative() -> None:
    StrategyControlsVersion(**_kwargs(avoid_first_minutes=0))
    StrategyControlsVersion(**_kwargs(avoid_first_minutes=15))

    with pytest.raises(ValidationError):
        StrategyControlsVersion(**_kwargs(avoid_first_minutes=-1))


def test_existing_cooldown_validator_still_fires() -> None:
    with pytest.raises(ValidationError, match="cooldown_bars or cooldown_minutes"):
        StrategyControlsVersion(**_kwargs(cooldown_bars=5, cooldown_minutes=15))


def test_event_blackout_renamed_to_earnings_news_blackout() -> None:
    """Old `event_blackout_enabled` field name no longer accepted; new name is canonical."""
    controls = StrategyControlsVersion(**_kwargs(earnings_news_blackout_enabled=True))
    assert controls.earnings_news_blackout_enabled is True

    with pytest.raises(ValidationError):
        StrategyControlsVersion(**_kwargs(event_blackout_enabled=True))
