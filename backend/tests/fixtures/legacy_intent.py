from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce


@dataclass(frozen=True)
class LegacyExecutionIntent:
    deployment_id: UUID
    program_version_id: UUID
    symbol: str
    side: CandidateSide
    intent_type: IntentType
    qty: float
    order_type: OrderType
    time_in_force: TimeInForce
    timestamp: datetime
    signal_name: str
    reason: str
    features_used: dict[str, object] | None = None
    stop_candidate: float | None = None
    target_candidate: float | None = None
    governor_approved: bool = False
    governor_reason: str | None = None

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError("qty must be greater than 0")
        if self.features_used is None:
            object.__setattr__(self, "features_used", {})

    def model_copy(self, *, update: dict[str, object] | None = None) -> "LegacyExecutionIntent":
        return replace(self, **(update or {}))
