from __future__ import annotations

import math
import re
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from backend.app.domain._base import JsonDict
from backend.app.domain.execution_style import (
    BracketRunnerPreset,
    BracketSpec,
    BracketStopTargetPreset,
    ExecutionStylePresetKind,
    ExecutionStyleVersion,
    MultiTargetScaleOutPreset,
    OrderType,
    TimeInForce,
)
from backend.app.domain.risk_profile import PositionSizingMethod, RiskProfileVersion
from backend.app.domain.strategy import (
    CandidateSide,
    ConditionExpression,
    ConditionGroup,
    ConditionNode,
    ConditionOperator,
    IntentType,
    LogicalExitRule,
    LogicalExitRuleKind,
    SignalRule,
    StrategyVersion,
)
from backend.app.domain.strategy_v4 import StrategyVersionV4
from backend.app.domain.strategy_controls import (
    AllowedDirections,
    SessionPreference,
    StrategyControlsVersion,
    TradingHorizon,
)
from backend.app.domain.strategy_draft import (
    StrategyDraft,
    StrategyDraftBacktestPlan,
    StrategyDraftComponentKind,
    StrategyDraftComponentMatch,
    StrategyDraftLaunchPlan,
    StrategyDraftLaunchPlans,
    StrategyDraftStep,
    StrategyDraftStepStatus,
    StrategyDraftValidation,
)
from backend.app.domain.universe import UniverseSnapshot, UniverseSymbol
from backend.app.features import (
    FeaturePlanError,
    ResolvedDeploymentComponents,
    build_feature_plan,
    make_feature_key,
    parse_feature_expression,
    registry,
)
from backend.app.features.spec import FeatureValidationError
from backend.app.execution_plans import ExecutionPlanRepository
from backend.app.strategies_v4.models import (
    OnFillActionV4Draft,
    StrategyEntriesV4Draft,
    StrategyEntryV4Draft,
    StrategyIdentityV4Draft,
    StrategyLegV4Draft,
    StrategyLogicalExitV4Draft,
    StrategyLogicalExitsV4Draft,
    StrategyStopV4Draft,
    StrategyVersionV4Draft,
)
from backend.app.strategies_v4.service import StrategyV4Service
from backend.app.strategy_composer.presets import (
    SignalPlanShapePreview,
    build_execution_style_version,
    build_preset_spec,
    build_signal_plan_shape_preview,
)
from backend.app.strategy_controls import StrategyControlsRepository


# Internal placeholder symbol used solely by the composer's feature-plan
# validation path. It is NEVER returned to the operator, NEVER persisted on
# the StrategyVersion, and NEVER surfaced in the response payload. Strategy
# is symbol-agnostic; symbols are bound at deployment via Watchlist.
_INTERNAL_PLAN_PREVIEW_SYMBOL: tuple[str, ...] = ("SPY",)


UNSUPPORTED_PROMPT_FEATURE_TERMS = frozenset({"bollinger", "bbands", "stochastic", "stoch"})
FEATURE_ALIASES: dict[str, str] = {
    "open": "5m.open[0]",
    "high": "5m.high[0]",
    "low": "5m.low[0]",
    "close": "5m.close[0]",
    "volume": "5m.volume[0]",
    "sma20": "5m.sma:length=20[0]",
    "sma_20": "5m.sma:length=20[0]",
    "ema20": "5m.ema:length=20[0]",
    "ema_20": "5m.ema:length=20[0]",
    "rsi14": "5m.rsi:length=14[0]",
    "rsi_14": "5m.rsi:length=14[0]",
    "rsi21": "5m.rsi:length=21[0]",
    "rsi_21": "5m.rsi:length=21[0]",
    "atr14": "5m.atr:length=14[0]",
    "atr_14": "5m.atr:length=14[0]",
    "vwap": "5m.vwap:session=regular[0]",
}


class FeatureCatalogItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    display_name: str
    namespace: str
    scope: str
    source: str
    description: str
    allowed_params: tuple[str, ...] = ()
    default_params: JsonDict = Field(default_factory=dict)
    supported_timeframes: tuple[str, ...] = ()
    supported_consumers: tuple[str, ...] = ()
    supported_modes: tuple[str, ...] = ()
    example_refs: tuple[str, ...] = ()


class FeatureReferenceValidationItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    input: str
    valid: bool
    normalized_ref: str | None = None
    feature_key: str | None = None
    display_name: str | None = None
    error_code: str | None = None
    message: str | None = None


class FeatureReferenceValidationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_refs: tuple[str, ...] = Field(min_length=1)
    consumer: str = "backtest"


class FeatureReferenceValidation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    normalized_feature_refs: tuple[str, ...] = ()
    feature_keys: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    items: tuple[FeatureReferenceValidationItem, ...] = ()


class FeaturePlanPreviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: StrategyVersion
    symbols: tuple[str, ...] = Field(default=("SPY",), min_length=1)
    consumer: str = "backtest"


class FeaturePlanPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    consumer: str
    symbols: tuple[str, ...] = ()
    timeframes: tuple[str, ...] = ()
    feature_refs: tuple[str, ...] = ()
    feature_keys: tuple[str, ...] = ()
    warmup_by_timeframe: dict[str, int] = Field(default_factory=dict)
    data_requirements: tuple[JsonDict, ...] = ()
    errors: tuple[str, ...] = ()


class ConditionParseRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    condition: JsonDict | None = None
    logical_exit_rule: JsonDict | None = None
    consumer: str = "backtest"


class ConditionParseResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: bool
    normalized_condition: JsonDict | None = None
    normalized_logical_exit_rule: JsonDict | None = None
    feature_refs: tuple[str, ...] = ()
    normalized_feature_refs: tuple[str, ...] = ()
    readable_summary: str | None = None
    errors: tuple[str, ...] = ()


class ReuseMatchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = ""
    strategy: StrategyVersion | None = None
    symbols: tuple[str, ...] = ()


class ReuseMatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategies: tuple[StrategyDraftComponentMatch, ...] = ()
    risk_plans: tuple[StrategyDraftComponentMatch, ...] = ()
    execution_styles: tuple[StrategyDraftComponentMatch, ...] = ()
    watchlists: tuple[StrategyDraftComponentMatch, ...] = ()
    screeners: tuple[StrategyDraftComponentMatch, ...] = ()


class WizardIntent(BaseModel):
    """Page-1 wizard checkboxes — the operator's intent envelope.

    Drives the AI compose() so the generated draft honors what the operator
    declared up front (direction, horizon, base timeframe, higher-timeframe
    confirmation, leg affordances). Maps to Strategy Controls + Strategy
    entry/exit shape on the way out.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    direction: AllowedDirections = AllowedDirections.LONG
    horizon: TradingHorizon = TradingHorizon.INTRADAY
    base_timeframe: str = "5m"
    higher_timeframe_confirmation: bool = False
    has_stop: bool = True
    has_target: bool = False
    has_multiple_targets: bool = False
    has_runner: bool = False
    has_logical_exit: bool = True
    has_time_based_exit: bool = False


class AIComposerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(min_length=1)
    timeframe: str = "5m"
    initial_capital: float = Field(default=100_000, gt=0)
    feature_refs: tuple[str, ...] = ()
    execution_style_preset: ExecutionStylePresetKind = ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT
    execution_style_overrides: dict[str, Any] | None = None
    wizard_intent: WizardIntent | None = None


class StrategyDraftSaveRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    draft: StrategyDraft


class StrategyDraftComponentSnapshots(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_style: ExecutionStyleVersion
    backtest_plan: StrategyDraftBacktestPlan
    launch_plans: StrategyDraftLaunchPlans


class StrategyDraftSaveResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_version: StrategyVersionV4
    draft: StrategyDraft
    component_version_snapshots: StrategyDraftComponentSnapshots
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    deployment_created: bool = False
    broker_action_created: bool = False
    live_readiness_claimed: bool = False


_CONDITION_ADAPTER = TypeAdapter(ConditionExpression)


class StrategyComposerService:
    def __init__(
        self,
        *,
        strategy_v4_service: StrategyV4Service | None = None,
        strategy_controls_repository: "StrategyControlsRepository | None" = None,
        execution_plan_repository: "ExecutionPlanRepository | None" = None,
    ) -> None:
        self._strategy_v4_service = strategy_v4_service
        self._strategy_controls_repository = strategy_controls_repository
        self._execution_plan_repository = execution_plan_repository

    def feature_catalog(self) -> tuple[FeatureCatalogItem, ...]:
        items: list[FeatureCatalogItem] = []
        for item in registry.catalog():
            kind = str(item["kind"])
            items.append(
                FeatureCatalogItem(
                    kind=kind,
                    display_name=self._display_name(kind),
                    namespace=str(item["namespace"]),
                    scope=str(item["scope"]),
                    source=str(item["source"]),
                    description=str(item["description"]),
                    allowed_params=tuple(item["allowed_params"]),
                    default_params=dict(item["default_params"]),
                    supported_timeframes=tuple(item["supported_timeframes"]),
                    supported_consumers=tuple(item["supported_consumers"]),
                    supported_modes=tuple(item["supported_modes"]),
                    example_refs=self._example_refs(kind, tuple(item["supported_timeframes"]), dict(item["default_params"])),
                )
            )
        return tuple(items)

    def feature_aliases(self) -> dict[str, str]:
        return dict(sorted(FEATURE_ALIASES.items()))

    def validate_feature_refs(self, request: FeatureReferenceValidationRequest) -> FeatureReferenceValidation:
        normalized: list[str] = []
        keys: list[str] = []
        errors: list[str] = []
        items: list[FeatureReferenceValidationItem] = []
        for feature_ref in request.feature_refs:
            try:
                normalized_ref = self.normalize_feature_ref(feature_ref)
                spec = parse_feature_expression(normalized_ref)
                registry.require_consumer_support(spec.kind, request.consumer)
                normalized.append(normalized_ref)
                feature_key = make_feature_key(spec)
                keys.append(feature_key)
                items.append(
                    FeatureReferenceValidationItem(
                        input=feature_ref,
                        valid=True,
                        normalized_ref=normalized_ref,
                        feature_key=feature_key,
                        display_name=self._display_name(spec.kind),
                    )
                )
            except (FeatureValidationError, ValueError) as exc:
                message = str(exc)
                errors.append(f"{feature_ref}: {message}")
                items.append(
                    FeatureReferenceValidationItem(
                        input=feature_ref,
                        valid=False,
                        error_code="unsupported_feature",
                        message=message,
                    )
                )
        return FeatureReferenceValidation(
            valid=not errors,
            normalized_feature_refs=tuple(dict.fromkeys(normalized)),
            feature_keys=tuple(dict.fromkeys(keys)),
            errors=tuple(errors),
            items=tuple(items),
        )

    def feature_plan_preview(self, request: FeaturePlanPreviewRequest) -> FeaturePlanPreview:
        strategy = self._normalize_strategy_features(request.strategy)
        components = self._components_for_preview(strategy=strategy, symbols=request.symbols)
        try:
            plan = build_feature_plan(components, consumer=request.consumer)
        except FeaturePlanError as exc:
            return FeaturePlanPreview(valid=False, consumer=request.consumer, errors=(str(exc),))
        return FeaturePlanPreview(
            valid=True,
            consumer=request.consumer,
            symbols=plan.symbols,
            timeframes=plan.timeframes,
            feature_refs=tuple(dict.fromkeys(self._strategy_feature_refs(strategy))),
            feature_keys=plan.feature_keys,
            warmup_by_timeframe=plan.warmup_by_timeframe,
            data_requirements=tuple(item.model_dump(mode="json") for item in plan.data_requirements),
        )

    def parse_condition(self, request: ConditionParseRequest) -> ConditionParseResponse:
        errors: list[str] = []
        feature_refs: list[str] = []
        condition: ConditionNode | ConditionGroup | None = None
        logical_exit: LogicalExitRule | None = None
        if request.condition is not None:
            try:
                condition = _CONDITION_ADAPTER.validate_python(request.condition)
                condition = self._normalize_condition_features(condition)
                feature_refs.extend(self._condition_feature_refs(condition))
            except ValueError as exc:
                errors.append(str(exc))
        if request.logical_exit_rule is not None:
            try:
                logical_exit = LogicalExitRule.model_validate(request.logical_exit_rule)
                logical_exit = self._normalize_logical_exit_features(logical_exit)
                feature_refs.extend(self._logical_exit_feature_refs(logical_exit))
            except ValueError as exc:
                errors.append(str(exc))
        if request.condition is None and request.logical_exit_rule is None:
            errors.append("condition or logical_exit_rule is required")

        validation = self.validate_feature_refs(
            FeatureReferenceValidationRequest(feature_refs=tuple(feature_refs or ("5m.close[0]",)), consumer=request.consumer)
        )
        if feature_refs and not validation.valid:
            errors.extend(validation.errors)
        return ConditionParseResponse(
            valid=not errors,
            normalized_condition=None if condition is None else condition.model_dump(mode="json"),
            normalized_logical_exit_rule=None if logical_exit is None else logical_exit.model_dump(mode="json"),
            feature_refs=tuple(dict.fromkeys(feature_refs)),
            normalized_feature_refs=validation.normalized_feature_refs if feature_refs else (),
            readable_summary=self._condition_summary(condition=condition, logical_exit=logical_exit),
            errors=tuple(errors),
        )

    def reuse_matches(self, request: ReuseMatchRequest) -> ReuseMatchResponse:
        prompt_tokens = self._tokens(request.prompt)
        strategy_matches: list[StrategyDraftComponentMatch] = []
        if self._strategy_v4_service is not None:
            for strategy in self._strategy_v4_service.list_all_heads():
                tokens = self._tokens(" ".join([str(strategy.get("name", "")), str(strategy.get("description") or "")]))
                overlap = len(prompt_tokens.intersection(tokens))
                score = min(1.0, 0.35 + overlap * 0.15) if overlap else 0.2
                strategy_matches.append(
                    StrategyDraftComponentMatch(
                        component_kind=StrategyDraftComponentKind.STRATEGY,
                        component_id=strategy.get("strategy_v4_id"),
                        display_name=str(strategy.get("name", "Strategy")),
                        score=score,
                        reason="name/tag overlap with composer prompt" if overlap else "available reusable Strategy",
                    )
                )
        return ReuseMatchResponse(
            strategies=tuple(sorted(strategy_matches, key=lambda item: item.score, reverse=True)[:5]),
            risk_plans=(
                StrategyDraftComponentMatch(
                    component_kind=StrategyDraftComponentKind.RISK_PLAN,
                    display_name="Fixed shares research Risk Plan",
                    score=0.82,
                    reason="safe draft default for research validation; operator can replace before deployment",
                ),
            ),
            execution_styles=(
                StrategyDraftComponentMatch(
                    component_kind=StrategyDraftComponentKind.EXECUTION_STYLE,
                    display_name="Market day bracket Execution Style",
                    score=0.8,
                    reason="matches draft research flow and keeps broker specifics outside Strategy",
                ),
            ),
            watchlists=(
                StrategyDraftComponentMatch(
                    component_kind=StrategyDraftComponentKind.WATCHLIST,
                    display_name="Prompt symbols Universe",
                    score=0.75,
                    reason="uses symbols explicitly requested by the operator" if request.symbols else "fallback research universe",
                ),
            ),
            screeners=(),
        )

    def compose(self, request: AIComposerRequest) -> StrategyDraft:
        wizard = request.wizard_intent
        timeframe = wizard.base_timeframe if wizard is not None else request.timeframe
        strategy_id = uuid4()
        strategy_version_id = uuid4()
        prompt = request.prompt.casefold()
        unsupported_terms = self._unsupported_prompt_terms(prompt)

        # Merge operator-picked feature_refs with the default close/open pair.
        picked_refs = [self.normalize_feature_ref(ref) for ref in request.feature_refs]
        default_refs = [
            self.normalize_feature_ref(f"{timeframe}.close[0]"),
            self.normalize_feature_ref(f"{timeframe}.open[0]"),
        ]
        feature_refs = list(dict.fromkeys([*picked_refs, *default_refs]))

        long_condition: ConditionExpression = ConditionNode(
            left_feature=feature_refs[0],
            operator=ConditionOperator.GT,
            right_feature=feature_refs[1] if len(feature_refs) > 1 else feature_refs[0],
            label="green bar placeholder" if unsupported_terms else "green bar",
        )
        short_condition: ConditionExpression = ConditionNode(
            left_feature=feature_refs[0],
            operator=ConditionOperator.LT,
            right_feature=feature_refs[1] if len(feature_refs) > 1 else feature_refs[0],
            label="red bar placeholder" if unsupported_terms else "red bar",
        )
        exit_rule = self._logical_exit_from_prompt(prompt)

        entry_rules: list[SignalRule] = []
        exit_rules: list[SignalRule] = []
        direction = wizard.direction if wizard is not None else AllowedDirections.LONG
        if direction in (AllowedDirections.LONG, AllowedDirections.BOTH):
            entry_rules.append(
                SignalRule(
                    name="draft_entry_long",
                    side=CandidateSide.LONG,
                    intent_type=IntentType.ENTRY,
                    condition=long_condition,
                )
            )
        if direction in (AllowedDirections.SHORT, AllowedDirections.BOTH):
            entry_rules.append(
                SignalRule(
                    name="draft_entry_short",
                    side=CandidateSide.SHORT,
                    intent_type=IntentType.ENTRY,
                    condition=short_condition,
                )
            )
        # Always emit at least one entry; default to long if direction was somehow empty.
        if not entry_rules:
            entry_rules.append(
                SignalRule(
                    name="draft_entry",
                    side=CandidateSide.LONG,
                    intent_type=IntentType.ENTRY,
                    condition=long_condition,
                )
            )

        has_logical_exit = wizard.has_logical_exit if wizard is not None else True
        if has_logical_exit:
            for rule_side in {rule.side for rule in entry_rules}:
                exit_rules.append(
                    SignalRule(
                        name=f"draft_logical_exit_{rule_side.value}",
                        side=rule_side,
                        intent_type=IntentType.EXIT,
                        logical_exit_rule=exit_rule,
                    )
                )

        strategy = StrategyVersion(
            id=strategy_version_id,
            strategy_id=strategy_id,
            version=1,
            name=self._draft_name(request.prompt),
            description=request.prompt.strip(),
            feature_refs=feature_refs,
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            tags=["ai_composer", "draft"],
        )

        preset_spec = build_preset_spec(request.execution_style_preset, request.execution_style_overrides)
        execution_style = build_execution_style_version(preset_spec)
        signal_plan_shape = build_signal_plan_shape_preview(preset_spec)

        strategy_controls = self._build_strategy_controls_from_wizard(wizard, timeframe)

        backtest_plan = StrategyDraftBacktestPlan(
            timeframe=timeframe,
            initial_capital=request.initial_capital,
            cost_model={"commission_per_trade": 0.0, "slippage_bps": 1.0},
            notes="Draft-only validation plan. No deployment or broker action.",
        )
        launch_plans = self._launch_plans(
            strategy=strategy,
            timeframe=timeframe,
            initial_capital=request.initial_capital,
        )
        validation = self._validate_draft_strategy(strategy=strategy)
        if unsupported_terms:
            validation = validation.model_copy(
                update={
                    "valid": False,
                    "errors": (
                        *validation.errors,
                        f"unsupported prompt feature terms require operator revision: {', '.join(unsupported_terms)}",
                    ),
                    "warnings": (
                        *validation.warnings,
                        "composer returned a placeholder using supported features only; revise before save",
                    ),
                }
            )
        return StrategyDraft(
            prompt=request.prompt,
            strategy=strategy,
            strategy_controls=strategy_controls,
            execution_style=execution_style,
            backtest_plan=backtest_plan,
            launch_plans=launch_plans,
            signal_plan_shape=signal_plan_shape.model_dump(mode="json"),
            steps=(
                StrategyDraftStep(
                    title="Parse operator prompt",
                    status=StrategyDraftStepStatus.VALIDATED,
                    summary="Plain English prompt converted into draft-only StrategyVersion components.",
                ),
                StrategyDraftStep(
                    title="Validate feature vocabulary",
                    status=StrategyDraftStepStatus.VALIDATED if validation.valid else StrategyDraftStepStatus.NEEDS_OPERATOR,
                    summary="All generated feature references must come from FeatureRegistry.",
                ),
                StrategyDraftStep(
                    title="Prepare backtest inputs",
                    status=StrategyDraftStepStatus.NEEDS_OPERATOR,
                    summary="Operator must confirm dates and choose a saved Risk Plan version before execution.",
                    details={"reason": "backtest route requires start, end, and persisted risk_plan_version_id"},
                ),
            ),
            component_matches=self.reuse_matches(ReuseMatchRequest(prompt=request.prompt, strategy=strategy)).strategies,
            validation=validation,
        )

    def save_draft(self, request: StrategyDraftSaveRequest) -> StrategyDraftSaveResponse:
        if self._strategy_v4_service is None:
            raise ValueError("strategy v4 service is required to save drafts")
        if not request.draft.validation.valid:
            raise ValueError(f"strategy draft failed validation: {request.draft.validation.errors}")
        normalized_strategy = self._normalize_strategy_features(request.draft.strategy)
        validation = self._validate_draft_strategy(strategy=normalized_strategy)
        if not validation.valid:
            raise ValueError(f"strategy draft failed validation: {validation.errors}")
        coherence_errors = self._check_strategy_controls_coherence(
            strategy=normalized_strategy,
            controls=request.draft.strategy_controls,
        )
        if coherence_errors:
            raise ValueError(f"strategy draft failed coherence check: {coherence_errors}")

        saved_controls, controls_version_id = self._persist_strategy_controls(
            request.draft.strategy_controls
        )
        saved_execution_plan, plan_version_id = self._persist_execution_plan(
            request.draft.execution_style
        )
        v4_draft = self._build_v4_draft(
            strategy=normalized_strategy,
            execution_style=saved_execution_plan,
            strategy_controls_version_id=controls_version_id,
            execution_plan_version_id=plan_version_id,
        )
        version = self._strategy_v4_service.save(v4_draft)

        saved_draft = request.draft.model_copy(
            update={
                "strategy": normalized_strategy,
                "validation": validation,
                "strategy_controls": saved_controls,
                "execution_style": saved_execution_plan,
            }
        )
        return StrategyDraftSaveResponse(
            strategy_version=version,
            draft=saved_draft,
            component_version_snapshots=StrategyDraftComponentSnapshots(
                execution_style=saved_execution_plan,
                backtest_plan=request.draft.backtest_plan,
                launch_plans=request.draft.launch_plans,
            ),
            strategy_controls_version_id=controls_version_id,
            execution_plan_version_id=plan_version_id,
        )

    def _build_v4_draft(
        self,
        *,
        strategy: StrategyVersion,
        execution_style: ExecutionStyleVersion,
        strategy_controls_version_id: UUID | None,
        execution_plan_version_id: UUID | None,
    ) -> StrategyVersionV4Draft:
        timeframe = self._strategy_timeframe(strategy)
        return StrategyVersionV4Draft(
            name=strategy.name,
            description=strategy.description,
            identity=StrategyIdentityV4Draft(
                tags=list(strategy.tags),
                direction=self._v4_direction(strategy),
            ),
            default_strategy_controls_version_id=strategy_controls_version_id,
            default_execution_plan_version_id=execution_plan_version_id,
            entries=StrategyEntriesV4Draft(
                long=self._v4_entry_for_side(strategy, CandidateSide.LONG),
                short=self._v4_entry_for_side(strategy, CandidateSide.SHORT),
            ),
            stops=self._v4_stops(execution_style),
            legs=self._v4_legs(execution_style),
            logical_exits=StrategyLogicalExitsV4Draft(
                long=self._v4_logical_exits_for_side(strategy, CandidateSide.LONG, timeframe),
                short=self._v4_logical_exits_for_side(strategy, CandidateSide.SHORT, timeframe),
            ),
        )

    def _v4_entry_for_side(
        self,
        strategy: StrategyVersion,
        side: CandidateSide,
    ) -> StrategyEntryV4Draft | None:
        expressions: list[str] = []
        for rule in strategy.entry_rules:
            if rule.intent_type != IntentType.ENTRY or rule.side != side:
                continue
            if rule.condition is None:
                raise ValueError(f"composer_v4_unsupported_entry_without_condition:{side.value}")
            expressions.append(self._condition_to_v4_expression(rule.condition))
        if not expressions:
            return None
        expression_text = expressions[0] if len(expressions) == 1 else " OR ".join(f"({expr})" for expr in expressions)
        return StrategyEntryV4Draft(expression_text=expression_text)

    def _condition_to_v4_expression(self, condition: ConditionExpression) -> str:
        if isinstance(condition, ConditionNode):
            left = self._feature_ref_to_v4_expression(condition.left_feature)
            op = self._condition_operator_to_v4(condition.operator)
            if condition.right_feature is not None:
                right = self._feature_ref_to_v4_expression(condition.right_feature)
            else:
                right = self._literal_to_v4_expression(condition.right_value)
            return f"{left} {op} {right}"

        joiner = " AND " if condition.operator in {"all", "and"} else " OR "
        return joiner.join(f"({self._condition_to_v4_expression(child)})" for child in condition.children)

    def _feature_ref_to_v4_expression(self, feature_ref: str) -> str:
        normalized = self.normalize_feature_ref(feature_ref)
        spec = parse_feature_expression(normalized)
        if spec.lookback != 0 or spec.shift != 0:
            raise ValueError(f"composer_v4_unsupported_feature_lookback:{normalized}")
        timeframe = spec.timeframe
        kind = spec.kind
        params = dict(spec.params)
        if kind in {"open", "high", "low", "close", "volume", "range", "body", "is_doji", "vwap"}:
            return f"{timeframe}.{kind}"
        if kind in {"sma", "ema", "rsi", "atr"}:
            length = params.get("length")
            if length is None:
                raise ValueError(f"composer_v4_missing_length_param:{normalized}")
            return f"{timeframe}.{kind}({length})"
        if not params:
            return f"{timeframe}.{kind}"
        ordered_values = ", ".join(str(value) for _, value in sorted(params.items()))
        return f"{timeframe}.{kind}({ordered_values})"

    @staticmethod
    def _condition_operator_to_v4(operator: ConditionOperator) -> str:
        mapping = {
            ConditionOperator.GT: ">",
            ConditionOperator.GREATER_THAN: ">",
            ConditionOperator.GTE: ">=",
            ConditionOperator.LT: "<",
            ConditionOperator.LESS_THAN: "<",
            ConditionOperator.LTE: "<=",
            ConditionOperator.EQ: "==",
            ConditionOperator.CROSS_ABOVE: "crosses_above",
            ConditionOperator.CROSS_BELOW: "crosses_below",
        }
        return mapping[operator]

    @staticmethod
    def _literal_to_v4_expression(value: float | int | str | bool | None) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int | float):
            return str(value)
        if isinstance(value, str):
            lowered = value.casefold()
            if lowered in {"true", "false"}:
                return lowered
            try:
                float(value)
            except ValueError as exc:
                raise ValueError(f"composer_v4_unsupported_string_literal:{value}") from exc
            return value
        raise ValueError("composer_v4_missing_literal")

    def _v4_stops(self, execution_style: ExecutionStyleVersion) -> list[StrategyStopV4Draft]:
        preset = execution_style.preset
        stop_pct = 2.0
        if isinstance(preset, BracketStopTargetPreset):
            stop_pct = preset.stop_pct
        elif isinstance(preset, BracketRunnerPreset):
            stop_pct = preset.trail_pct
        elif isinstance(preset, MultiTargetScaleOutPreset) and preset.stop_pct is not None:
            stop_pct = preset.stop_pct
        return [
            StrategyStopV4Draft(
                mode="simple",
                scope="all",
                simple_type="%",
                simple_value=float(stop_pct),
            )
        ]

    def _v4_legs(self, execution_style: ExecutionStyleVersion) -> list[StrategyLegV4Draft]:
        preset = execution_style.preset
        leave = OnFillActionV4Draft(kind="leave")
        if isinstance(preset, BracketStopTargetPreset):
            return [
                StrategyLegV4Draft(
                    position=1,
                    kind="target",
                    size_pct=1.0,
                    target_type="%",
                    target_value=float(preset.target_pct),
                    on_fill_action=leave,
                )
            ]
        if isinstance(preset, BracketRunnerPreset):
            first_slice = float(preset.first_slice_pct)
            runner_size = max(0.0, 1.0 - first_slice)
            legs = [
                StrategyLegV4Draft(
                    position=1,
                    kind="target",
                    size_pct=first_slice,
                    target_type="%",
                    target_value=float(preset.first_target_pct),
                    on_fill_action=leave,
                )
            ]
            if runner_size > 0:
                legs.append(
                    StrategyLegV4Draft(
                        position=2,
                        kind="runner",
                        size_pct=runner_size,
                        target_type="trail-%",
                        target_value=float(preset.trail_pct),
                        on_fill_action=leave,
                    )
                )
            return legs
        if isinstance(preset, MultiTargetScaleOutPreset):
            legs = [
                StrategyLegV4Draft(
                    position=index,
                    kind="target",
                    size_pct=float(target.slice_pct),
                    target_type="%",
                    target_value=float(target.target_pct),
                    on_fill_action=leave,
                )
                for index, target in enumerate(preset.targets, start=1)
            ]
            total = sum(leg.size_pct for leg in legs)
            if total < 1.0:
                legs.append(
                    StrategyLegV4Draft(
                        position=len(legs) + 1,
                        kind="runner",
                        size_pct=1.0 - total,
                        target_type="trail-%",
                        target_value=float(preset.stop_pct or 2.0),
                        on_fill_action=leave,
                    )
                )
            return legs
        return []

    def _v4_logical_exits_for_side(
        self,
        strategy: StrategyVersion,
        side: CandidateSide,
        timeframe: str,
    ) -> list[StrategyLogicalExitV4Draft]:
        exits: list[StrategyLogicalExitV4Draft] = []
        for rule in strategy.exit_rules:
            if rule.intent_type != IntentType.EXIT or rule.side != side:
                continue
            if rule.logical_exit_rule is not None:
                exits.extend(self._logical_exit_rule_to_v4(rule.logical_exit_rule, timeframe))
            elif rule.condition is not None:
                raise ValueError("composer_v4_unsupported_logical_exit:feature_condition")
        return exits

    def _logical_exit_rule_to_v4(
        self,
        rule: LogicalExitRule,
        timeframe: str,
    ) -> list[StrategyLogicalExitV4Draft]:
        if rule.kind == LogicalExitRuleKind.BARS_SINCE_ENTRY:
            return [StrategyLogicalExitV4Draft(template_id="bars_since", params={"bars": int(rule.bars or 1)})]
        if rule.kind == LogicalExitRuleKind.TIME_IN_POSITION_SECONDS:
            seconds = int(rule.seconds or 60)
            bars = max(1, math.ceil(seconds / (self._timeframe_minutes(timeframe) * 60)))
            return [StrategyLogicalExitV4Draft(template_id="bars_since", params={"bars": bars})]
        if rule.kind == LogicalExitRuleKind.MINUTES_BEFORE_SESSION_CLOSE:
            return [
                StrategyLogicalExitV4Draft(
                    template_id="session_end",
                    params={"offset_minutes": int(rule.minutes_before_close or 5)},
                )
            ]
        if rule.kind == LogicalExitRuleKind.TIME_OF_DAY_ET:
            return [
                StrategyLogicalExitV4Draft(
                    template_id="session_end",
                    params={"offset_minutes": self._minutes_before_regular_close(rule.time_of_day_et or "15:55")},
                )
            ]
        if rule.kind == LogicalExitRuleKind.SESSION_WINDOW:
            return [StrategyLogicalExitV4Draft(template_id="session_end", params={})]
        if rule.kind == LogicalExitRuleKind.HYBRID:
            raise ValueError("composer_v4_unsupported_logical_exit:hybrid")
        raise ValueError(f"composer_v4_unsupported_logical_exit:{rule.kind.value}")

    def _strategy_timeframe(self, strategy: StrategyVersion) -> str:
        refs = self._strategy_feature_refs(strategy)
        if refs:
            return refs[0].split(".", 1)[0]
        return "5m"

    @staticmethod
    def _v4_direction(strategy: StrategyVersion) -> str:
        sides = {rule.side for rule in strategy.entry_rules if rule.intent_type == IntentType.ENTRY}
        if CandidateSide.LONG in sides and CandidateSide.SHORT in sides:
            return "both"
        if CandidateSide.SHORT in sides:
            return "short"
        return "long"

    @staticmethod
    def _timeframe_minutes(timeframe: str) -> int:
        match = re.fullmatch(r"([0-9]+)([mhdw])", timeframe)
        if not match:
            return 5
        value = int(match.group(1))
        unit = match.group(2)
        multipliers = {"m": 1, "h": 60, "d": 1440, "w": 10080}
        return value * multipliers[unit]

    @staticmethod
    def _minutes_before_regular_close(time_of_day_et: str) -> int:
        try:
            hours_text, minutes_text = time_of_day_et.split(":", 1)
            minutes = int(hours_text) * 60 + int(minutes_text)
        except ValueError:
            return 5
        close = 16 * 60
        return max(1, close - minutes)

    def _persist_strategy_controls(
        self, controls: StrategyControlsVersion | None
    ) -> tuple[StrategyControlsVersion | None, UUID | None]:
        """Persist StrategyControlsVersion if a repository is wired.

        Returns ``(payload, persisted_version_id)``. When no repository is
        wired, the payload passes through unchanged and ``persisted_version_id``
        is ``None`` — signalling "not durably saved".
        """

        if controls is None:
            return None, None
        if self._strategy_controls_repository is None:
            return controls, None
        # New strategy_controls_id and version=1 for a fresh save.
        normalized = controls.model_copy(
            update={
                "id": uuid4(),
                "strategy_controls_id": uuid4(),
                "version": 1,
            }
        )
        self._strategy_controls_repository.save_version(normalized)
        return normalized, normalized.id

    def _persist_execution_plan(
        self, execution_plan: ExecutionStyleVersion
    ) -> tuple[ExecutionStyleVersion, UUID | None]:
        if self._execution_plan_repository is None:
            return execution_plan, None
        normalized = execution_plan.model_copy(
            update={
                "id": uuid4(),
                "execution_style_id": uuid4(),
                "version": 1,
            }
        )
        self._execution_plan_repository.save_version(normalized)
        return normalized, normalized.id

    def _launch_plans(
        self,
        *,
        strategy: StrategyVersion,
        timeframe: str,
        initial_capital: float,
    ) -> StrategyDraftLaunchPlans:
        strategy_id = str(strategy.strategy_id)
        strategy_version_id = str(strategy.id)
        common_request = {
            "strategy_id": strategy_id,
            "strategy_version_id": strategy_version_id,
            "symbols": list(_INTERNAL_PLAN_PREVIEW_SYMBOL),
            "timeframe": timeframe,
            "source": "yahoo",
        }
        return StrategyDraftLaunchPlans(
            backtest=StrategyDraftLaunchPlan(
                surface="backtest",
                route="/api/v1/research/jobs/backtest",
                request={
                    "request": {
                        **common_request,
                        "risk_plan_version_id": None,
                        "start": None,
                        "end": None,
                        "initial_capital": initial_capital,
                        "cost_model": {"commission_per_trade": 0.0, "slippage_bps": 1.0},
                        "adjustment_policy": "split_dividend_adjusted",
                    }
                },
                ready=False,
                missing_fields=("risk_plan_version_id", "start", "end"),
                notes="Use async research job route after the operator confirms dates and saved Risk Plan version.",
            ),
            walk_forward=StrategyDraftLaunchPlan(
                surface="walk_forward",
                route="/api/v1/research/jobs/walk-forward",
                request={
                    "request": {
                        **common_request,
                        "start": None,
                        "end": None,
                        "initial_capital": initial_capital,
                        "cost_model": {"commission_per_trade": 0.0, "slippage_bps": 1.0},
                        "adjustment_policy": "split_dividend_adjusted",
                        "window_mode": "rolling",
                        "is_length": {"unit": "days", "value": 180},
                        "oos_length": {"unit": "days", "value": 60},
                        "step": {"unit": "days", "value": 60},
                        "max_folds": 8,
                        "selection_criterion": "max_dd_bounded_sharpe",
                    }
                },
                ready=False,
                missing_fields=("start", "end"),
                notes="Use async walk-forward job route after the operator confirms the research window.",
            ),
        )

    def normalize_feature_ref(self, feature_ref: str) -> str:
        raw = feature_ref.strip()
        if not raw:
            raise ValueError("feature ref cannot be empty")
        lowered = raw.casefold()
        if lowered in FEATURE_ALIASES:
            return FEATURE_ALIASES[lowered]
        shorthand_match = re.fullmatch(r"(rsi|sma|ema|atr)[_-]?([0-9]+)", lowered)
        if shorthand_match:
            kind, length = shorthand_match.groups()
            return f"5m.{kind}:length={int(length)}[0]"
        return raw

    def _normalize_strategy_features(self, strategy: StrategyVersion) -> StrategyVersion:
        return strategy.model_copy(
            update={
                "feature_refs": [self.normalize_feature_ref(ref) for ref in strategy.feature_refs],
                "entry_rules": [self._normalize_signal_rule(rule) for rule in strategy.entry_rules],
                "exit_rules": [self._normalize_signal_rule(rule) for rule in strategy.exit_rules],
            }
        )

    def _normalize_signal_rule(self, rule: SignalRule) -> SignalRule:
        return rule.model_copy(
            update={
                "condition": None if rule.condition is None else self._normalize_condition_features(rule.condition),
                "logical_exit_rule": None if rule.logical_exit_rule is None else self._normalize_logical_exit_features(rule.logical_exit_rule),
                "stop_candidate_feature": None if rule.stop_candidate_feature is None else self.normalize_feature_ref(rule.stop_candidate_feature),
                "target_candidate_feature": None if rule.target_candidate_feature is None else self.normalize_feature_ref(rule.target_candidate_feature),
            }
        )

    def _normalize_condition_features(self, condition: ConditionExpression) -> ConditionExpression:
        if isinstance(condition, ConditionNode):
            return condition.model_copy(
                update={
                    "left_feature": self.normalize_feature_ref(condition.left_feature),
                    "right_feature": None if condition.right_feature is None else self.normalize_feature_ref(condition.right_feature),
                }
            )
        return condition.model_copy(
            update={"children": [self._normalize_condition_features(child) for child in condition.children]}
        )

    def _normalize_logical_exit_features(self, rule: LogicalExitRule) -> LogicalExitRule:
        return rule.model_copy(
            update={
                "feature_condition": None if rule.feature_condition is None else self._normalize_condition_features(rule.feature_condition),
                "children": tuple(self._normalize_logical_exit_features(child) for child in rule.children),
            }
        )

    def _validate_draft_strategy(self, *, strategy: StrategyVersion) -> StrategyDraftValidation:
        preview = self.feature_plan_preview(FeaturePlanPreviewRequest(strategy=strategy, symbols=_INTERNAL_PLAN_PREVIEW_SYMBOL, consumer="backtest"))
        errors = preview.errors
        return StrategyDraftValidation(
            valid=preview.valid,
            errors=errors,
            warnings=() if preview.valid else ("draft cannot be saved until feature plan is valid",),
            normalized_feature_refs=preview.feature_refs,
            feature_plan_preview=preview.model_dump(mode="json"),
        )

    def _components_for_preview(self, *, strategy: StrategyVersion, symbols: tuple[str, ...]) -> ResolvedDeploymentComponents:
        return ResolvedDeploymentComponents(
            strategy=strategy,
            strategy_controls=self._strategy_controls(strategy),
            risk_profile=RiskProfileVersion(
                id=uuid4(),
                risk_profile_id=uuid4(),
                version=1,
                name="Composer preview fixed shares",
                sizing_method=PositionSizingMethod.FIXED_SHARES,
                fixed_shares=10,
            ),
            execution_style=ExecutionStyleVersion(
                id=uuid4(),
                execution_style_id=uuid4(),
                version=1,
                name="Composer preview market day",
                entry_order_type=OrderType.MARKET,
                exit_order_type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
                bracket=BracketSpec(enabled=False),
                scale_out_enabled=False,
            ),
            universe=UniverseSnapshot(
                id=uuid4(),
                universe_id=uuid4(),
                version=1,
                name="Feature plan preview universe",
                symbols=[UniverseSymbol(symbol=symbol.upper()) for symbol in symbols],
            ),
        )

    def _strategy_controls(self, strategy: StrategyVersion) -> Any:
        from backend.app.domain import StrategyControlsVersion

        refs = self._strategy_feature_refs(strategy)
        timeframe = "5m"
        if refs:
            timeframe = refs[0].split(".", 1)[0]
        return StrategyControlsVersion(
            id=uuid4(),
            strategy_controls_id=uuid4(),
            version=1,
            name="Composer preview controls",
            timeframe=timeframe,
        )

    def _strategy_feature_refs(self, strategy: StrategyVersion) -> list[str]:
        refs: list[str] = [self.normalize_feature_ref(ref) for ref in strategy.feature_refs]
        for rule in [*strategy.entry_rules, *strategy.exit_rules]:
            if rule.condition is not None:
                refs.extend(self._condition_feature_refs(rule.condition))
            if rule.logical_exit_rule is not None:
                refs.extend(self._logical_exit_feature_refs(rule.logical_exit_rule))
            if rule.stop_candidate_feature is not None:
                refs.append(self.normalize_feature_ref(rule.stop_candidate_feature))
            if rule.target_candidate_feature is not None:
                refs.append(self.normalize_feature_ref(rule.target_candidate_feature))
        return list(dict.fromkeys(refs))

    def _condition_feature_refs(self, condition: ConditionExpression) -> list[str]:
        if isinstance(condition, ConditionNode):
            refs = [self.normalize_feature_ref(condition.left_feature)]
            if condition.right_feature is not None:
                refs.append(self.normalize_feature_ref(condition.right_feature))
            return refs
        refs: list[str] = []
        for child in condition.children:
            refs.extend(self._condition_feature_refs(child))
        return refs

    def _logical_exit_feature_refs(self, rule: LogicalExitRule) -> list[str]:
        refs: list[str] = []
        if rule.feature_condition is not None:
            refs.extend(self._condition_feature_refs(rule.feature_condition))
        for child in rule.children:
            refs.extend(self._logical_exit_feature_refs(child))
        return refs

    _TIMEFRAME_RANK = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440, "1w": 10080, "1mo": 43200,
    }

    def _check_strategy_controls_coherence(
        self,
        *,
        strategy: StrategyVersion,
        controls: StrategyControlsVersion | None,
    ) -> tuple[str, ...]:
        """Defense-in-depth save-time coherence rules (error severity only).

        Frontend Tier-1 surfaces these inline; backend re-validates so a
        malicious or malformed payload cannot bypass the editor.
        """
        errors: list[str] = []
        from backend.app.domain.strategy_controls import AllowedDirections as _AD

        sides_with_entry = {rule.side.value for rule in strategy.entry_rules}
        if controls is None:
            return ()

        if controls.allowed_directions in (_AD.LONG, _AD.BOTH) and "long" not in sides_with_entry:
            errors.append(
                "long_enabled_no_long_entry: allowed_directions includes long but no entry rule has side=long"
            )
        if controls.allowed_directions in (_AD.SHORT, _AD.BOTH) and "short" not in sides_with_entry:
            errors.append(
                "short_enabled_no_short_entry: allowed_directions includes short but no entry rule has side=short"
            )

        base_rank = self._TIMEFRAME_RANK.get(controls.timeframe, 0)
        feature_timeframes = {ref.split(".", 1)[0] for ref in strategy.feature_refs if "." in ref}
        if controls.higher_timeframe_confirmation_required:
            has_htf = any(self._TIMEFRAME_RANK.get(tf, 0) > base_rank for tf in feature_timeframes)
            if not has_htf:
                errors.append(
                    "htf_confirmation_required_but_no_htf_feature: strategy_controls.higher_timeframe_confirmation_required "
                    f"is true but no feature_ref uses a timeframe higher than the base ({controls.timeframe})"
                )

        for ref in strategy.feature_refs:
            if "." not in ref:
                continue
            try:
                spec = parse_feature_expression(ref)
                entry = registry.get(spec.kind)
            except (FeatureValidationError, Exception):
                continue
            if spec.timeframe not in entry.supported_timeframes:
                errors.append(
                    f"feature_not_supported_for_timeframe: '{ref}' uses timeframe '{spec.timeframe}' "
                    f"which is outside the registry's supported timeframes for kind '{spec.kind}'"
                )
        return tuple(errors)

    def _build_strategy_controls_from_wizard(
        self,
        wizard: WizardIntent | None,
        timeframe: str,
    ) -> StrategyControlsVersion | None:
        if wizard is None:
            return None
        controls_id = uuid4()
        return StrategyControlsVersion(
            id=uuid4(),
            strategy_controls_id=controls_id,
            version=1,
            name="Draft Controls (wizard)",
            timeframe=timeframe,
            allowed_directions=wizard.direction,
            higher_timeframe_confirmation_required=wizard.higher_timeframe_confirmation,
        )

    def _logical_exit_from_prompt(self, prompt: str) -> LogicalExitRule:
        minutes_before_close_match = re.search(r"([0-9]+)\s*(?:minute|minutes|min)\s+before\s+(?:session\s+)?close", prompt)
        if minutes_before_close_match:
            return LogicalExitRule(
                kind=LogicalExitRuleKind.MINUTES_BEFORE_SESSION_CLOSE,
                minutes_before_close=int(minutes_before_close_match.group(1)),
                label="minutes before session close",
            )
        time_of_day_match = re.search(r"\b(?:at|by)\s+([0-2]?[0-9]:[0-5][0-9])\s*(?:et|eastern)?\b", prompt)
        if time_of_day_match:
            return LogicalExitRule(
                kind=LogicalExitRuleKind.TIME_OF_DAY_ET,
                time_of_day_et=time_of_day_match.group(1).zfill(5),
                label="time of day exit",
            )
        minutes_match = re.search(r"(?:after|hold|holding|in position)\s+([0-9]+)\s*(?:minute|minutes|min)\b", prompt)
        if minutes_match:
            return LogicalExitRule(
                kind=LogicalExitRuleKind.TIME_IN_POSITION_SECONDS,
                seconds=int(minutes_match.group(1)) * 60,
                label="time based exit",
            )
        bars_match = re.search(r"([0-9]+)\s*bars?\b", prompt)
        if bars_match:
            return LogicalExitRule(kind=LogicalExitRuleKind.BARS_SINCE_ENTRY, bars=int(bars_match.group(1)))
        return LogicalExitRule(
            kind=LogicalExitRuleKind.FEATURE_CONDITION,
            feature_condition=ConditionNode(
                left_feature="5m.close[0]",
                operator=ConditionOperator.LT,
                right_feature="5m.open[0]",
                label="red bar exit",
            ),
        )

    @staticmethod
    def _draft_name(prompt: str) -> str:
        cleaned = " ".join(prompt.strip().split())
        return (cleaned[:80] or "AI Composer Draft").title()

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]+", text.casefold()) if len(token) > 2}

    @staticmethod
    def _display_name(kind: str) -> str:
        return kind.replace("_", " ").upper() if kind in {"rsi", "sma", "ema", "atr", "vwap"} else kind.replace("_", " ").title()

    @staticmethod
    def _example_refs(kind: str, supported_timeframes: tuple[str, ...], default_params: dict[str, Any]) -> tuple[str, ...]:
        timeframe = "5m" if "5m" in supported_timeframes else supported_timeframes[0]
        if default_params:
            params = ",".join(f"{key}={value}" for key, value in sorted(default_params.items()))
            return (f"{timeframe}.{kind}:{params}[0]",)
        return (f"{timeframe}.{kind}[0]",)

    @staticmethod
    def _unsupported_prompt_terms(prompt: str) -> tuple[str, ...]:
        return tuple(sorted(term for term in UNSUPPORTED_PROMPT_FEATURE_TERMS if term in prompt))

    @staticmethod
    def _condition_summary(*, condition: ConditionExpression | None, logical_exit: LogicalExitRule | None) -> str | None:
        parts: list[str] = []
        if condition is not None:
            parts.append("feature condition validated")
        if logical_exit is not None:
            parts.append(f"logical exit: {logical_exit.kind.value}")
        return "; ".join(parts) if parts else None
