from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.decision import SignalPlanBuilder
from backend.app.domain import CandidateSide, CandidateTradeIntent, IntentType, SignalPlanIntent


def _candidate(intent_type: IntentType = IntentType.ENTRY) -> CandidateTradeIntent:
    return CandidateTradeIntent(
        timestamp=datetime.now(timezone.utc),
        symbol="spy",
        side=CandidateSide.LONG,
        intent_type=intent_type,
        signal_name="long_breakout",
        feature_values_used={"5m.close[0]": 500},
        stop_candidate=495 if intent_type == IntentType.ENTRY else None,
        target_candidate=510 if intent_type == IntentType.ENTRY else None,
    )


def test_builder_converts_entry_candidate_to_neutral_open_signal_plan() -> None:
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
    )

    assert plan.symbol == "SPY"
    assert plan.intent == SignalPlanIntent.OPEN
    assert plan.entry is not None
    assert plan.stop is not None
    assert plan.targets
    assert not hasattr(plan, "account_id")
    assert not hasattr(plan, "quantity")


def test_builder_converts_exit_candidate_to_position_management_plan_with_lineage() -> None:
    opening_signal_plan_id = uuid4()
    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(IntentType.EXIT),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        opening_signal_plan_id=opening_signal_plan_id,
    )

    assert plan.intent == SignalPlanIntent.LOGICAL_EXIT
    assert plan.opening_signal_plan_id == opening_signal_plan_id


def test_exit_candidate_requires_lineage() -> None:
    with pytest.raises(ValidationError):
        SignalPlanBuilder().build_from_candidate(
            candidate=_candidate(IntentType.EXIT),
            deployment_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
        )
