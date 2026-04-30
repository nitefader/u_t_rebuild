"""ExecutionPlan persistence package.

Owns the persisted, immutable ``execution_plan_versions`` table per
``MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md``. The Deployment binds
an ``execution_plan_version_id``; the same StrategyVersion may run with
different ExecutionPlans across Accounts.
"""

from .models import ExecutionPlanVersionRecord
from .persistence import (
    ExecutionPlanRepository,
    ExecutionPlanVersionNotFoundError,
)

__all__ = [
    "ExecutionPlanVersionRecord",
    "ExecutionPlanRepository",
    "ExecutionPlanVersionNotFoundError",
]
