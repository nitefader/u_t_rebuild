from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.domain import CandidateSide, ConditionNode, ConditionOperator, IntentType, SignalRule, StrategyVersion
from backend.app.domain.execution_style import ExecutionStylePresetKind
from backend.app.domain.strategy import LogicalExitRuleKind
from backend.app.strategy_composer import (
    AIComposerRequest,
    ConditionParseRequest,
    FeaturePlanPreviewRequest,
    FeatureReferenceValidationRequest,
    StrategyComposerService,
    StrategyDraftSaveRequest,
)
from backend.app.strategies import StrategyService
from backend.app.strategies.persistence import StrategyRepository


def test_unsupported_feature_is_rejected() -> None:
    result = StrategyComposerService().validate_feature_refs(
        FeatureReferenceValidationRequest(feature_refs=("5m.bollinger_bands:length=12[0]",))
    )

    assert result.valid is False
    assert "unsupported feature" in result.errors[0]


def test_rsi_shorthand_normalizes_and_validates_after_engine_unification() -> None:
    """Slice 2 unified the feature engine — RSI is now executable by every
    consumer (no batch/stream taxonomy). The shorthand `rsi21` normalizes
    to a canonical ref and validates as a real feature."""
    result = StrategyComposerService().validate_feature_refs(
        FeatureReferenceValidationRequest(feature_refs=("rsi21",))
    )

    assert result.valid is True
    assert result.normalized_feature_refs == ("5m.rsi:length=21[0]",)
    assert result.items[0].valid is True
    assert result.items[0].feature_key is not None


def test_sma_shorthand_normalizes_and_validates() -> None:
    result = StrategyComposerService().validate_feature_refs(
        FeatureReferenceValidationRequest(feature_refs=("sma20",))
    )

    assert result.valid is True
    assert result.normalized_feature_refs == ("5m.sma:length=20[0]",)


def test_logical_exit_rule_is_validated() -> None:
    result = StrategyComposerService().parse_condition(
        ConditionParseRequest(
            logical_exit_rule={
                "kind": "time_in_position_seconds",
                "seconds": 1800,
                "label": "30 minute exit",
            }
        )
    )

    assert result.valid is True
    assert result.normalized_logical_exit_rule is not None
    assert result.normalized_logical_exit_rule["kind"] == LogicalExitRuleKind.TIME_IN_POSITION_SECONDS.value


@pytest.mark.parametrize(
    ("rule", "expected_kind"),
    [
        ({"kind": "bars_since_entry", "bars": 6}, "bars_since_entry"),
        ({"kind": "time_in_position_seconds", "seconds": 1800}, "time_in_position_seconds"),
        ({"kind": "time_of_day_et", "time_of_day_et": "15:55"}, "time_of_day_et"),
        (
            {
                "kind": "feature_condition",
                "feature_condition": {
                    "kind": "condition",
                    "left_feature": "close",
                    "operator": "lt",
                    "right_feature": "open",
                },
            },
            "feature_condition",
        ),
        (
            {
                "kind": "hybrid",
                "operator": "all",
                "children": [
                    {"kind": "bars_since_entry", "bars": 4},
                    {
                        "kind": "feature_condition",
                        "feature_condition": {
                            "kind": "condition",
                            "left_feature": "close",
                            "operator": "lt",
                            "right_feature": "open",
                        },
                    },
                ],
            },
            "hybrid",
        ),
    ],
)
def test_logical_exit_rule_supported_kinds_are_validated(rule: dict[str, object], expected_kind: str) -> None:
    result = StrategyComposerService().parse_condition(ConditionParseRequest(logical_exit_rule=rule))

    assert result.valid is True
    assert result.normalized_logical_exit_rule is not None
    assert result.normalized_logical_exit_rule["kind"] == expected_kind


def test_ai_draft_cannot_invent_features() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="Use Bollinger and Stochastic words but do not invent unsupported features")
    )

    assert draft.validation.valid is False
    assert any("unsupported prompt feature terms" in error for error in draft.validation.errors)
    assert all("bollinger" not in ref and "stochastic" not in ref for ref in draft.validation.normalized_feature_refs)


def test_rsi_prompt_yields_valid_draft_after_engine_unification() -> None:
    """Slice 2 dropped the batch/stream guardrail — RSI prompts no longer
    raise `rsi_not_batch_executable`. The composer still emits a green-bar
    placeholder; the operator revises it to actually use RSI in a condition."""
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="RSI long entry and exit after 30 minutes")
    )

    assert draft.validation.valid is True
    assert all("rsi_not_batch_executable" not in error for error in draft.validation.errors)
    assert all("rsi_not_batch_executable" not in warning for warning in draft.validation.warnings)


def test_draft_can_generate_valid_feature_plan() -> None:
    composer = StrategyComposerService()
    draft = composer.compose(AIComposerRequest(prompt="green bar long entry and exit after 30 minutes"))

    preview = composer.feature_plan_preview(
        FeaturePlanPreviewRequest(strategy=draft.strategy, symbols=("SPY", "QQQ"), consumer="backtest")
    )

    assert preview.valid is True
    assert preview.symbols == ("QQQ", "SPY")
    assert "5m" in preview.timeframes
    assert preview.feature_keys


def test_minutes_before_close_prompt_uses_session_close_exit() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="green bar entry exit 5 minutes before close")
    )

    rule = draft.strategy.exit_rules[0].logical_exit_rule
    assert rule is not None
    assert rule.kind == LogicalExitRuleKind.MINUTES_BEFORE_SESSION_CLOSE
    assert rule.minutes_before_close == 5


def test_draft_has_no_symbols_no_universe_no_risk_plan() -> None:
    """Draft no longer carries suggested_universe or suggested_risk_plan (spine doctrine)."""
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="green bar entry")
    )

    assert not hasattr(draft, "suggested_universe")
    assert not hasattr(draft, "suggested_risk_plan")
    assert draft.execution_style is not None
    assert draft.signal_plan_shape is not None


def test_request_rejects_symbols_field() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="extra_forbidden"):
        AIComposerRequest(prompt="test", symbols=("SPY",))  # type: ignore[call-arg]


def test_request_rejects_notes_field() -> None:
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="extra_forbidden"):
        AIComposerRequest(prompt="test", notes="my notes")  # type: ignore[call-arg]


def test_save_draft_persists_strategy_version_and_snapshots_component_versions(tmp_path: Path) -> None:
    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(AIComposerRequest(prompt="green bar entry with 5 minute exit"))

    response = composer.save_draft(StrategyDraftSaveRequest(draft=draft))

    assert response.strategy_version.status == "draft"
    assert response.deployment_created is False
    assert response.broker_action_created is False
    assert response.live_readiness_claimed is False
    # no risk_plan or universe in snapshots
    assert not hasattr(response.component_version_snapshots, "risk_plan")
    assert not hasattr(response.component_version_snapshots, "universe")
    assert response.component_version_snapshots.execution_style.version == 1
    assert response.component_version_snapshots.execution_style.bracket.enabled is False
    assert response.component_version_snapshots.launch_plans.backtest.route == "/api/v1/research/jobs/backtest"
    assert response.component_version_snapshots.launch_plans.backtest.ready is False
    assert response.component_version_snapshots.launch_plans.chart_lab.ready is True
    assert response.component_version_snapshots.launch_plans.walk_forward.route == "/api/v1/research/jobs/walk-forward"


def test_save_draft_persists_normalized_feature_refs(tmp_path: Path) -> None:
    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(AIComposerRequest(prompt="green bar entry"))
    bare_strategy = draft.strategy.model_copy(
        update={
            "feature_refs": ["close", "open"],
            "entry_rules": [
                draft.strategy.entry_rules[0].model_copy(
                    update={
                        "condition": ConditionNode(
                            left_feature="close",
                            operator=ConditionOperator.GT,
                            right_feature="open",
                        )
                    }
                )
            ],
        }
    )
    bare_draft = draft.model_copy(update={"strategy": bare_strategy})

    response = composer.save_draft(StrategyDraftSaveRequest(draft=bare_draft))

    saved = response.strategy_version.payload
    assert tuple(saved.feature_refs) == ("5m.close[0]", "5m.open[0]")
    condition = saved.entry_rules[0].condition
    assert isinstance(condition, ConditionNode)
    assert condition.left_feature == "5m.close[0]"
    assert condition.right_feature == "5m.open[0]"


def test_ai_draft_generates_chart_backtest_and_walk_forward_launch_plans() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="green bar entry with time exit", initial_capital=50_000)
    )

    assert draft.launch_plans.chart_lab.surface == "chart_lab"
    assert draft.launch_plans.chart_lab.method == "GET"
    # chart_lab uses the internal placeholder symbol, not operator-supplied ones
    assert draft.launch_plans.chart_lab.request["symbol"] == "SPY"
    # backtest request carries the internal placeholder symbol
    assert draft.launch_plans.backtest.request["request"]["symbols"] == ["SPY"]
    assert draft.launch_plans.backtest.request["request"]["risk_plan_version_id"] is None
    assert draft.launch_plans.backtest.missing_fields == ("risk_plan_version_id", "start", "end")
    assert draft.launch_plans.walk_forward.request["request"]["window_mode"] == "rolling"
    assert draft.launch_plans.walk_forward.request["request"]["selection_criterion"] == "max_dd_bounded_sharpe"


def test_strategy_composer_has_no_broker_runtime_or_deployment_boundary_imports() -> None:
    import backend.app.strategy_composer.service as service_module

    source = inspect.getsource(service_module)
    forbidden = (
        "backend.app.brokers",
        "backend.app.orders",
        "backend.app.deployments",
        "backend.app.runtime",
        "submit_order",
        "cancel_order",
        "start_deployment",
    )

    assert not any(token in source for token in forbidden)


def test_ai_draft_with_unsupported_manual_feature_cannot_be_saved(tmp_path: Path) -> None:
    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(AIComposerRequest(prompt="valid draft"))
    broken_strategy = StrategyVersion(
        id=draft.strategy.id,
        strategy_id=draft.strategy.strategy_id,
        version=draft.strategy.version,
        name=draft.strategy.name,
        feature_refs=["5m.notreal[0]"],
        entry_rules=[
            SignalRule(
                name="bad",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.notreal[0]",
                    operator=ConditionOperator.GT,
                    right_value=1,
                ),
            )
        ],
    )
    broken_draft = draft.model_copy(update={"strategy": broken_strategy})

    try:
        composer.save_draft(StrategyDraftSaveRequest(draft=broken_draft))
    except ValueError as exc:
        assert "unsupported feature" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsupported feature draft should not save")


def test_invalid_ai_prompt_draft_cannot_be_saved_even_if_placeholder_strategy_is_valid(tmp_path: Path) -> None:
    """Prompts that mention features the registry doesn't implement (MACD,
    Bollinger, …) still pre-block save with an unsupported-term validation
    error — the registry is the source of truth, not the prompt."""
    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(
        AIComposerRequest(prompt="MACD long entry with bollinger band exit")
    )

    assert draft.validation.valid is False
    try:
        composer.save_draft(StrategyDraftSaveRequest(draft=draft))
    except ValueError as exc:
        assert "unsupported prompt feature terms" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid AI prompt draft should not save")


# ---------------------------------------------------------------------------
# Execution-style preset round-trips (Slice 1 additions)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset",
    [
        ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT,
        ExecutionStylePresetKind.STOP_ENTRY_MARKET_EXIT,
        ExecutionStylePresetKind.BRACKET_STOP_TARGET,
        ExecutionStylePresetKind.BRACKET_RUNNER,
        ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT,
    ],
)
def test_each_preset_round_trips_through_compose(preset: ExecutionStylePresetKind) -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="green bar entry", execution_style_preset=preset)
    )

    assert draft.execution_style.preset is not None
    assert draft.execution_style.preset.kind == preset
    assert draft.signal_plan_shape is not None
    assert draft.signal_plan_shape["preset"] == preset.value


def test_market_market_preset_has_no_bracket_no_targets() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(
            prompt="green bar entry",
            execution_style_preset=ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT,
        )
    )

    assert draft.signal_plan_shape["stop"] is None
    assert draft.signal_plan_shape["targets"] == []
    assert draft.signal_plan_shape["runner"] is None


def test_bracket_stop_target_preset_has_stop_and_one_target() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(
            prompt="bracket entry",
            execution_style_preset=ExecutionStylePresetKind.BRACKET_STOP_TARGET,
            execution_style_overrides={"stop_pct": 1.5, "target_pct": 3.0},
        )
    )

    shape = draft.signal_plan_shape
    assert shape["stop"] is not None
    assert shape["stop"]["type"] == "static_pct"
    assert len(shape["targets"]) == 1
    assert shape["targets"][0]["label"] == "bracket_target"
    assert "1.5" in shape["stop"]["rule"]
    assert "3" in shape["targets"][0]["rule"]


def test_bracket_runner_preset_has_target_and_runner() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(
            prompt="bracket runner entry",
            execution_style_preset=ExecutionStylePresetKind.BRACKET_RUNNER,
        )
    )

    shape = draft.signal_plan_shape
    assert len(shape["targets"]) == 1
    assert shape["targets"][0]["label"] == "first_target"
    assert shape["runner"] is not None
    assert shape["runner"]["management"] == "trail"


def test_multi_target_scale_out_default_has_four_targets() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(
            prompt="scale out entry",
            execution_style_preset=ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT,
        )
    )

    shape = draft.signal_plan_shape
    assert len(shape["targets"]) == 4
    assert shape["targets"][0]["label"] == "target_1"
    assert shape["targets"][-1]["action"] == "close"


def test_response_has_no_suggested_universe_in_json_serialization() -> None:
    draft = StrategyComposerService().compose(
        AIComposerRequest(prompt="green bar entry")
    )
    payload = draft.model_dump(mode="json")

    assert "suggested_universe" not in payload
    assert "suggested_risk_plan" not in payload
    assert "execution_style" in payload
    assert "signal_plan_shape" in payload


# ---------------------------------------------------------------------------
# Backend defense-in-depth coherence rules (Slice 6d additions)
# These tests cover the three rules in _check_strategy_controls_coherence.
# No new backend code — these guard against bypassing the client-side rules.
# ---------------------------------------------------------------------------


def test_save_draft_blocks_on_short_enabled_no_short_entry(tmp_path: Path) -> None:
    """allowed_directions=both with only a long entry rule → ValueError naming
    short_enabled_no_short_entry."""
    from backend.app.domain.strategy_controls import AllowedDirections, StrategyControlsVersion
    from uuid import uuid4

    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(AIComposerRequest(prompt="green bar entry"))

    # Patch controls to require both directions, but keep only the long entry rule
    # that the AI generated (it never adds short entries).
    patched_controls = StrategyControlsVersion(
        id=draft.strategy_controls.id if draft.strategy_controls else uuid4(),
        strategy_controls_id=draft.strategy_controls.strategy_controls_id if draft.strategy_controls else uuid4(),
        version=1,
        name="Patched Controls",
        timeframe="5m",
        allowed_directions=AllowedDirections.BOTH,
    )
    patched_draft = draft.model_copy(update={"strategy_controls": patched_controls})

    with pytest.raises(ValueError, match="short_enabled_no_short_entry"):
        composer.save_draft(StrategyDraftSaveRequest(draft=patched_draft))


def test_save_draft_blocks_on_htf_confirmation_no_htf_feature(tmp_path: Path) -> None:
    """higher_timeframe_confirmation_required=True with all feature refs on 5m
    → ValueError naming htf_confirmation_required."""
    from backend.app.domain.strategy_controls import StrategyControlsVersion
    from uuid import uuid4

    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(AIComposerRequest(prompt="green bar entry with 5 minute exit"))

    # Ensure strategy only has 5m refs (the default composer output).
    # Patch controls to demand HTF confirmation.
    patched_controls = StrategyControlsVersion(
        id=draft.strategy_controls.id if draft.strategy_controls else uuid4(),
        strategy_controls_id=draft.strategy_controls.strategy_controls_id if draft.strategy_controls else uuid4(),
        version=1,
        name="HTF Controls",
        timeframe="5m",
        higher_timeframe_confirmation_required=True,
    )
    # Override feature_refs to be only 5m so there is guaranteed no HTF feature.
    bare_strategy = draft.strategy.model_copy(
        update={"feature_refs": ["5m.close[0]", "5m.open[0]"]}
    )
    patched_draft = draft.model_copy(
        update={"strategy": bare_strategy, "strategy_controls": patched_controls}
    )

    with pytest.raises(ValueError, match="htf_confirmation_required"):
        composer.save_draft(StrategyDraftSaveRequest(draft=patched_draft))


def test_save_draft_passes_when_htf_feature_present(tmp_path: Path) -> None:
    """Same setup as the blocking test above, but with a 1h feature_ref added →
    no coherence error, draft saves successfully."""
    from backend.app.domain.strategy_controls import StrategyControlsVersion
    from uuid import uuid4

    strategy_service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    composer = StrategyComposerService(strategy_service=strategy_service)
    draft = composer.compose(AIComposerRequest(prompt="green bar entry with 5 minute exit"))

    patched_controls = StrategyControlsVersion(
        id=draft.strategy_controls.id if draft.strategy_controls else uuid4(),
        strategy_controls_id=draft.strategy_controls.strategy_controls_id if draft.strategy_controls else uuid4(),
        version=1,
        name="HTF Controls",
        timeframe="5m",
        higher_timeframe_confirmation_required=True,
    )
    # Add a 1h feature ref so the HTF requirement is satisfied.
    bare_strategy = draft.strategy.model_copy(
        update={"feature_refs": ["5m.close[0]", "5m.open[0]", "1h.close[0]"]}
    )
    patched_draft = draft.model_copy(
        update={"strategy": bare_strategy, "strategy_controls": patched_controls}
    )

    # Should not raise — HTF feature is present.
    response = composer.save_draft(StrategyDraftSaveRequest(draft=patched_draft))
    assert response.strategy_version.status == "draft"
