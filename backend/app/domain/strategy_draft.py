from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field

from ._base import DomainSchema, JsonDict, utc_now
from .execution_style import ExecutionStyleVersion
from .strategy import StrategyVersion
from .strategy_controls import StrategyControlsVersion


class StrategyDraftStepStatus(StrEnum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    NEEDS_OPERATOR = "needs_operator"
    REJECTED = "rejected"


class StrategyDraftStep(DomainSchema):
    step_id: UUID = Field(default_factory=uuid4)
    title: str
    status: StrategyDraftStepStatus = StrategyDraftStepStatus.PROPOSED
    summary: str
    details: JsonDict = Field(default_factory=dict)


class StrategyDraftComponentKind(StrEnum):
    STRATEGY = "strategy"
    RISK_PLAN = "risk_plan"
    EXECUTION_STYLE = "execution_style"
    UNIVERSE = "universe"
    WATCHLIST = "watchlist"
    SCREENER = "screener"


class StrategyDraftComponentMatch(DomainSchema):
    component_kind: StrategyDraftComponentKind
    component_id: UUID | None = None
    display_name: str
    score: float = Field(ge=0, le=1)
    reason: str
    metadata: JsonDict = Field(default_factory=dict)


class StrategyDraftValidation(DomainSchema):
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    normalized_feature_refs: tuple[str, ...] = ()
    feature_plan_preview: JsonDict | None = None


class StrategyDraftBacktestPlan(DomainSchema):
    """Backtest launch defaults.

    ``symbols`` here are NOT a Strategy attribute. Per the spine doctrine
    (`feedback_strategy_symbol_agnostic_spine.md`) Strategy is symbol-agnostic
    — the operator binds the actual universe at deployment via Watchlist.
    These symbols are launch-time defaults only, used to seed the Backtest /
    Walk-Forward request body when the operator clicks "Verify in Backtest".
    They default to a single placeholder symbol; the operator overrides them
    in the launcher, not in the composer.
    """

    symbols: tuple[str, ...] = Field(default=("SPY",), min_length=1)
    timeframe: str = "5m"
    start: str | None = None
    end: str | None = None
    initial_capital: float = Field(default=100_000, gt=0)
    cost_model: JsonDict = Field(default_factory=dict)
    source: str = "yahoo"
    notes: str | None = None


class StrategyDraftLaunchPlan(DomainSchema):
    surface: Literal["backtest", "walk_forward"]
    method: Literal["GET", "POST"] = "POST"
    route: str
    request: JsonDict = Field(default_factory=dict)
    ready: bool = False
    missing_fields: tuple[str, ...] = ()
    notes: str | None = None


class StrategyDraftLaunchPlans(DomainSchema):
    backtest: StrategyDraftLaunchPlan
    walk_forward: StrategyDraftLaunchPlan


class StrategyDraft(DomainSchema):
    """Composer-time draft envelope.

    Doctrine: Strategy is symbol-agnostic. This envelope intentionally carries
    NO ``suggested_risk_plan`` and NO ``suggested_universe`` — RiskPlan is a
    separate first-class operator product, and Universe/Watchlist binding
    happens at Deployment, not Strategy. The ``execution_style`` field is
    inlined (was ``suggested_execution_style``) because the execution style
    is part of the Strategy itself, not a separate component.

    ``signal_plan_shape`` is a Tier-1 (no-AI) preview: a symbol-agnostic
    rendering of the SignalPlan intents the chosen execution preset will emit
    at runtime, with ``[symbol]`` placeholder for the operator-facing UI.
    """

    draft_id: UUID = Field(default_factory=uuid4)
    prompt: str | None = None
    strategy: StrategyVersion
    strategy_controls: StrategyControlsVersion | None = None
    execution_style: ExecutionStyleVersion
    backtest_plan: StrategyDraftBacktestPlan
    launch_plans: StrategyDraftLaunchPlans
    signal_plan_shape: dict[str, Any] | None = None
    steps: tuple[StrategyDraftStep, ...] = ()
    component_matches: tuple[StrategyDraftComponentMatch, ...] = ()
    validation: StrategyDraftValidation
    created_at: datetime = Field(default_factory=utc_now)
