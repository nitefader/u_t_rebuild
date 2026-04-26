"""Internal runtime decision loop contracts."""

from .engine import ExecutionIntentBuilder, RuntimeEngine, RuntimeEventLog, RuntimeStateStore
from .models import (
    DeploymentContext,
    ExecutionIntent,
    RuntimeDecisionBatch,
    RuntimeError,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeState,
    RuntimeStatus,
)
from .recovery_orchestrator import RecoveryResult, RuntimeRecoveryOrchestrator


def __getattr__(name: str):
    if name in {"BrokerRuntimeDeployment", "BrokerRuntimeLoopStatus", "BrokerRuntimeOrchestrator"}:
        from .broker_runtime_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeLoopStatus, BrokerRuntimeOrchestrator

        return {
            "BrokerRuntimeDeployment": BrokerRuntimeDeployment,
            "BrokerRuntimeLoopStatus": BrokerRuntimeLoopStatus,
            "BrokerRuntimeOrchestrator": BrokerRuntimeOrchestrator,
        }[name]
    if name in {"PaperRuntimeSupervisor", "PaperRuntimeSupervisorError"}:
        from .paper_runtime_supervisor import PaperRuntimeSupervisor, PaperRuntimeSupervisorError

        return {
            "PaperRuntimeSupervisor": PaperRuntimeSupervisor,
            "PaperRuntimeSupervisorError": PaperRuntimeSupervisorError,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BrokerRuntimeDeployment",
    "BrokerRuntimeLoopStatus",
    "BrokerRuntimeOrchestrator",
    "DeploymentContext",
    "ExecutionIntent",
    "ExecutionIntentBuilder",
    "PaperRuntimeSupervisor",
    "PaperRuntimeSupervisorError",
    "RecoveryResult",
    "RuntimeDecisionBatch",
    "RuntimeEngine",
    "RuntimeError",
    "RuntimeEvent",
    "RuntimeEventLog",
    "RuntimeEventType",
    "RuntimeState",
    "RuntimeStateStore",
    "RuntimeStatus",
    "RuntimeRecoveryOrchestrator",
]
