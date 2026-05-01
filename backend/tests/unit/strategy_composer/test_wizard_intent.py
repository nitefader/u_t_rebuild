from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.domain import CandidateSide
from backend.app.domain.strategy_controls import (
    AllowedDirections,
    SessionPreference,
    TradingHorizon,
)
from backend.app.strategy_composer import (
    AIComposerRequest,
    StrategyComposerService,
    WizardIntent,
)


def test_wizard_intent_defaults_are_intraday_long_5m_with_logical_exit() -> None:
    intent = WizardIntent()

    assert intent.direction == AllowedDirections.LONG
    assert intent.horizon == TradingHorizon.INTRADAY
    assert intent.base_timeframe == "5m"
    assert intent.higher_timeframe_confirmation is False
    assert intent.has_stop is True
    assert intent.has_target is False
    assert intent.has_multiple_targets is False
    assert intent.has_runner is False
    assert intent.has_logical_exit is True
    assert intent.has_time_based_exit is False


def test_wizard_intent_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        WizardIntent(some_unknown_field=True)  # type: ignore[call-arg]


def test_compose_without_wizard_keeps_legacy_long_only_default() -> None:
    draft = StrategyComposerService().compose(AIComposerRequest(prompt="close above sma"))

    assert draft.strategy_controls is None
    assert len(draft.strategy.entry_rules) == 1
    assert draft.strategy.entry_rules[0].side == CandidateSide.LONG


def test_compose_with_long_only_wizard_emits_long_entry_only() -> None:
    intent = WizardIntent(direction=AllowedDirections.LONG)
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="momentum long", wizard_intent=intent)
    )

    assert draft.strategy_controls is not None
    assert draft.strategy_controls.allowed_directions == AllowedDirections.LONG
    assert [rule.side for rule in draft.strategy.entry_rules] == [CandidateSide.LONG]
    assert all(rule.side == CandidateSide.LONG for rule in draft.strategy.exit_rules)


def test_compose_with_short_only_wizard_emits_short_entry_only() -> None:
    intent = WizardIntent(direction=AllowedDirections.SHORT)
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="momentum short", wizard_intent=intent)
    )

    assert draft.strategy_controls is not None
    assert draft.strategy_controls.allowed_directions == AllowedDirections.SHORT
    assert [rule.side for rule in draft.strategy.entry_rules] == [CandidateSide.SHORT]
    assert all(rule.side == CandidateSide.SHORT for rule in draft.strategy.exit_rules)


def test_compose_with_both_directions_wizard_emits_long_and_short_entries() -> None:
    intent = WizardIntent(direction=AllowedDirections.BOTH)
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="trend follower", wizard_intent=intent)
    )

    sides = sorted(rule.side.value for rule in draft.strategy.entry_rules)
    assert sides == ["long", "short"]
    exit_sides = sorted(rule.side.value for rule in draft.strategy.exit_rules)
    assert exit_sides == ["long", "short"]


def test_wizard_base_timeframe_overrides_request_timeframe() -> None:
    intent = WizardIntent(base_timeframe="1h", horizon=TradingHorizon.SWING)
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="swing trend", timeframe="5m", wizard_intent=intent)
    )

    assert draft.strategy_controls.timeframe == "1h"
    assert all(".close[0]" in ref or ".open[0]" in ref or ref.startswith("1h.") for ref in draft.strategy.feature_refs)


def test_wizard_higher_timeframe_flag_propagates_to_strategy_controls() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(
            prompt="HTF confirmation",
            wizard_intent=WizardIntent(higher_timeframe_confirmation=True),
        )
    )

    assert draft.strategy_controls.higher_timeframe_confirmation_required is True


def test_wizard_no_logical_exit_omits_exit_rules() -> None:
    intent = WizardIntent(has_logical_exit=False)
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="entry only", wizard_intent=intent)
    )

    assert draft.strategy.exit_rules == []


def test_aicomposer_request_rejects_unknown_field() -> None:
    """Slices 1-5 contract: AIComposerRequest is extra='forbid'. Adding wizard_intent
    must not relax that — still 422 on unknown fields."""
    with pytest.raises(ValidationError):
        AIComposerRequest(prompt="x", random_field="y")  # type: ignore[call-arg]


def test_aicomposer_request_rejects_old_symbols_field_post_slice1() -> None:
    """Symbols is permanently extra-forbidden per Slice 1; wizard does not bring it back."""
    with pytest.raises(ValidationError):
        AIComposerRequest(prompt="x", symbols=["SPY"])  # type: ignore[call-arg]
