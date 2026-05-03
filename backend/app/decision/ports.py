"""Signal source port contracts for the S12 evaluator split.

Signature survey:
- V4 ``build_signal_plan_from_v4`` takes keyword-only strategy, snapshot,
  symbol, side, timestamp, deployment_id, optional watchlist_snapshot_id, and
  an expression loader; it returns ``SignalPlan | None``.
- Logical-exit sources take strategy, snapshot, and position contexts; they
  return candidate intents and diagnostics through this port result envelope.

The port deliberately does not import either concrete evaluator. The unified
``contexts`` payload carries the union of evaluator-specific inputs; future
adapters decide which required fields to enforce. V4-only output resolves to
``signal_plan: SignalPlan | None``. Legacy-only output resolves to
``candidate_intents``. ``source`` is the discriminator for consumers that need
to distinguish those transitional shapes.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from backend.app.domain import CandidateTradeIntent, StrategyVersion
from backend.app.domain.signal_plan import SignalPlan
from backend.app.domain.strategy_v4 import StrategyVersionV4
from backend.app.features import FeatureSnapshot


SignalSourceKind = Literal["v4_expression", "legacy_rule"]
SignalEvaluationDecision = Literal["emitted", "no_signal", "blocked", "error"]


@dataclass(frozen=True)
class PositionSignalContext:
    """Structural twin of the legacy position context, without importing it."""

    has_position: bool = False
    entry_timestamp: datetime | None = None
    entry_bar_index: int | None = None
    current_bar_index: int | None = None
    bar_timestamp: datetime | None = None
    session_open_et: time = time(9, 30)
    session_close_et: time = time(16, 0)


@dataclass(frozen=True)
class SignalEvaluationContext:
    """Union input envelope for v4 expression and legacy rule evaluators."""

    strategy: StrategyVersion | StrategyVersionV4
    evaluation_type: Literal["entry", "logical_exit"] = "entry"
    position_contexts: Mapping[str, PositionSignalContext] = field(default_factory=dict)
    symbol: str | None = None
    side: Literal["long", "short"] | None = None
    timestamp: datetime | None = None
    deployment_id: UUID | None = None
    watchlist_snapshot_id: UUID | None = None


@dataclass(frozen=True)
class SignalEvaluationResult:
    """Unified result envelope returned by future signal-source adapters."""

    decision: SignalEvaluationDecision
    source: SignalSourceKind
    signal_plan: SignalPlan | None = None
    candidate_intents: tuple[CandidateTradeIntent, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class SignalSourcePort(Protocol):
    def evaluate(
        self,
        snapshot: FeatureSnapshot,
        contexts: SignalEvaluationContext,
    ) -> SignalEvaluationResult:
        ...
