"""Slice 6a-i save-time coherence checks (defense-in-depth).

Frontend Tier-1 surfaces these inline; backend re-validates on save so a
malicious or malformed payload cannot bypass the editor.

Rules covered (error severity only):
- long_enabled_no_long_entry
- short_enabled_no_short_entry
- htf_confirmation_required_but_no_htf_feature
- feature_not_supported_for_timeframe
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.domain import (
    AllowedDirections,
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    IntentType,
    SignalRule,
    StrategyControlsVersion,
    StrategyVersion,
    TradingHorizon,
)
from backend.app.strategies import StrategyService
from backend.app.strategies.persistence import StrategyRepository
from backend.app.strategy_composer import (
    AIComposerRequest,
    StrategyComposerService,
    StrategyDraftSaveRequest,
    WizardIntent,
)


def _service(tmp_path: Path) -> StrategyComposerService:
    repo = StrategyRepository(tmp_path / "strategies.db")
    return StrategyComposerService(strategy_service=StrategyService(repository=repo))


def _draft(service: StrategyComposerService, **wizard_overrides):
    intent_kwargs = {"direction": AllowedDirections.LONG}
    intent_kwargs.update(wizard_overrides)
    return service.compose(
        AIComposerRequest(prompt="test draft", wizard_intent=WizardIntent(**intent_kwargs))
    )


def test_save_succeeds_when_long_only_strategy_has_long_entry(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = _draft(service, direction=AllowedDirections.LONG)

    # Smoke: should not raise
    response = service.save_draft(StrategyDraftSaveRequest(draft=draft))
    assert response.strategy_version is not None


def test_save_blocks_short_enabled_with_no_short_entry(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = _draft(service, direction=AllowedDirections.SHORT)

    # Manually mutate the strategy to remove the short entry while keeping controls saying SHORT.
    # (This simulates a malformed/malicious payload — the editor would not let this through.)
    long_only_strategy = draft.strategy.model_copy(
        update={
            "entry_rules": [
                rule.model_copy(update={"side": CandidateSide.LONG, "name": "draft_entry_long"})
                for rule in draft.strategy.entry_rules
            ]
        }
    )
    tampered_draft = draft.model_copy(update={"strategy": long_only_strategy})

    with pytest.raises(ValueError, match="short_enabled_no_short_entry"):
        service.save_draft(StrategyDraftSaveRequest(draft=tampered_draft))


def test_save_blocks_long_enabled_with_no_long_entry(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = _draft(service, direction=AllowedDirections.LONG)

    short_only_strategy = draft.strategy.model_copy(
        update={
            "entry_rules": [
                rule.model_copy(update={"side": CandidateSide.SHORT, "name": "draft_entry_short"})
                for rule in draft.strategy.entry_rules
            ]
        }
    )
    tampered_draft = draft.model_copy(update={"strategy": short_only_strategy})

    with pytest.raises(ValueError, match="long_enabled_no_long_entry"):
        service.save_draft(StrategyDraftSaveRequest(draft=tampered_draft))


def test_save_blocks_htf_required_but_no_htf_feature(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = _draft(service, higher_timeframe_confirmation=True, base_timeframe="5m")

    # Strategy uses only 5m features — fails HTF check.
    with pytest.raises(ValueError, match="htf_confirmation_required_but_no_htf_feature"):
        service.save_draft(StrategyDraftSaveRequest(draft=draft))


def test_save_succeeds_when_htf_required_and_htf_feature_present(tmp_path: Path) -> None:
    service = _service(tmp_path)
    draft = _draft(service, higher_timeframe_confirmation=True, base_timeframe="5m")

    # Inject a 1h feature_ref to satisfy HTF requirement.
    augmented_strategy = draft.strategy.model_copy(
        update={"feature_refs": list(draft.strategy.feature_refs) + ["1h.close[0]"]}
    )
    augmented_draft = draft.model_copy(update={"strategy": augmented_strategy})

    response = service.save_draft(StrategyDraftSaveRequest(draft=augmented_draft))
    assert response.strategy_version is not None


def test_coherence_check_no_op_when_strategy_controls_absent(tmp_path: Path) -> None:
    """Drafts composed without a wizard intent have no Strategy Controls;
    save must not impose coherence rules that depend on Controls."""
    service = _service(tmp_path)
    draft = service.compose(AIComposerRequest(prompt="legacy draft no wizard"))
    assert draft.strategy_controls is None

    response = service.save_draft(StrategyDraftSaveRequest(draft=draft))
    assert response.strategy_version is not None


def test_coherence_check_directly_returns_no_errors_when_controls_none() -> None:
    service = StrategyComposerService()
    strategy = StrategyVersion(
        id=__import__("uuid").uuid4(),
        strategy_id=__import__("uuid").uuid4(),
        version=1,
        name="Direct test",
        feature_refs=["5m.close[0]"],
        entry_rules=[
            SignalRule(
                name="entry",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GT,
                    right_feature="5m.open[0]",
                ),
            )
        ],
    )
    assert service._check_strategy_controls_coherence(strategy=strategy, controls=None) == ()
