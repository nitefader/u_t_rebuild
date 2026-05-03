from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.decision import SignalPlanBuilder, SignalPlanBuilderError
from backend.app.decision.signal_plan_common import (
    POST_FILL_PCT_RULE_PREFIX,
    parse_post_fill_pct,
    post_fill_pct_rule,
)
from backend.app.domain import (
    CandidateSide,
    CandidateTradeIntent,
    IntentType,
    LogicalExitRule,
    LogicalExitRuleKind,
    SignalPlanIntent,
)


def _candidate(intent_type: IntentType = IntentType.EXIT) -> CandidateTradeIntent:
    return CandidateTradeIntent(
        timestamp=datetime.now(timezone.utc),
        symbol="spy",
        side=CandidateSide.LONG,
        intent_type=intent_type,
        signal_name="logical_exit",
        reason="signal_condition_true",
        feature_values_used={"5m.close[0]": 500},
    )


def _logical_exit_rule() -> LogicalExitRule:
    return LogicalExitRule(
        kind=LogicalExitRuleKind.BARS_SINCE_ENTRY,
        bars=5,
        label="bars_since:5",
    )


def test_post_fill_pct_rule_round_trips() -> None:
    encoded = post_fill_pct_rule(7.5)
    assert encoded == f"{POST_FILL_PCT_RULE_PREFIX}:7.5"
    assert parse_post_fill_pct(encoded) == 7.5


def test_parse_post_fill_pct_rejects_garbage() -> None:
    assert parse_post_fill_pct(None) is None
    assert parse_post_fill_pct("") is None
    assert parse_post_fill_pct("fixed:5") is None
    assert parse_post_fill_pct("post_fill_pct:") is None
    assert parse_post_fill_pct("post_fill_pct:abc") is None
    assert parse_post_fill_pct("post_fill_pct:-1") is None
    assert parse_post_fill_pct("post_fill_pct:0") is None


def test_builder_converts_exit_candidate_to_logical_exit_plan_with_lineage() -> None:
    opening_signal_plan_id = uuid4()
    related_position_lineage_id = uuid4()

    plan = SignalPlanBuilder().build_from_candidate(
        candidate=_candidate(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        opening_signal_plan_id=opening_signal_plan_id,
        related_position_lineage_id=related_position_lineage_id,
        logical_exit_rule=_logical_exit_rule(),
    )

    assert plan.symbol == "SPY"
    assert plan.intent == SignalPlanIntent.LOGICAL_EXIT
    assert plan.entry is None
    assert plan.opening_signal_plan_id == opening_signal_plan_id
    assert plan.related_position_lineage_id == related_position_lineage_id
    assert plan.logical_exit is not None
    assert plan.logical_exit.rule.kind == LogicalExitRuleKind.BARS_SINCE_ENTRY
    assert not hasattr(plan, "account_id")
    assert not hasattr(plan, "quantity")


def test_exit_candidate_requires_lineage() -> None:
    with pytest.raises(ValidationError):
        SignalPlanBuilder().build_from_candidate(
            candidate=_candidate(),
            deployment_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            logical_exit_rule=_logical_exit_rule(),
        )


def test_builder_rejects_entry_candidates() -> None:
    with pytest.raises(SignalPlanBuilderError, match="unsupported candidate intent type"):
        SignalPlanBuilder().build_from_candidate(
            candidate=_candidate(IntentType.ENTRY),
            deployment_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            opening_signal_plan_id=uuid4(),
        )
