"""Strategy CRUD package.

Strategies are reusable trading logic + execution-plan config. The
runtime spine consumes ``StrategyVersion`` (in ``backend.app.domain``)
shapes; this package owns the operator-facing durable record:
multiple frozen versions per Strategy, lifecycle status, validation
state, and CRUD service.

Doctrine: this package does NOT introduce a runtime root, does NOT
mutate broker truth, and does NOT bypass the Operation Turtle Shell
runtime composition root (`backend.app.pipeline.orchestrator`).
"""

from .models import (
    Strategy,
    StrategyListResponse,
    StrategyResponse,
    StrategyStatus,
    StrategyVersionRecord,
    StrategyWriteRequest,
)
from .service import StrategyServiceError, StrategyService

__all__ = [
    "Strategy",
    "StrategyListResponse",
    "StrategyResponse",
    "StrategyService",
    "StrategyServiceError",
    "StrategyStatus",
    "StrategyVersionRecord",
    "StrategyWriteRequest",
]
