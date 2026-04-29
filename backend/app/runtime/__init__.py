"""Internal runtime contracts.

Runtime order authority lives in ``backend.app.pipeline.orchestrator``. The
legacy pre-SignalPlan decision path is intentionally not exported.
"""
from .models import (
    DeploymentContext,
    RuntimeError,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeState,
    RuntimeStatus,
)
from .recovery_orchestrator import RecoveryResult, RuntimeRecoveryOrchestrator


def __getattr__(name: str):
    if name in {"BrokerRuntimeDeployment", "BrokerRuntimeLoopStatus", "BrokerRuntimeOrchestrator"}:
        from .account_trading_orchestrator import BrokerRuntimeDeployment, BrokerRuntimeLoopStatus, BrokerRuntimeOrchestrator

        return {
            "BrokerRuntimeDeployment": BrokerRuntimeDeployment,
            "BrokerRuntimeLoopStatus": BrokerRuntimeLoopStatus,
            "BrokerRuntimeOrchestrator": BrokerRuntimeOrchestrator,
        }[name]
    if name in {"BrokerRuntimeSupervisor", "BrokerRuntimeSupervisorError"}:
        from .account_trading_supervisor import BrokerRuntimeSupervisor, BrokerRuntimeSupervisorError

        return {
            "BrokerRuntimeSupervisor": BrokerRuntimeSupervisor,
            "BrokerRuntimeSupervisorError": BrokerRuntimeSupervisorError,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BrokerRuntimeDeployment",
    "BrokerRuntimeLoopStatus",
    "BrokerRuntimeOrchestrator",
    "BrokerRuntimeSupervisor",
    "BrokerRuntimeSupervisorError",
    "DeploymentContext",
    "RecoveryResult",
    "RuntimeError",
    "RuntimeEvent",
    "RuntimeEventType",
    "RuntimeState",
    "RuntimeStatus",
    "RuntimeRecoveryOrchestrator",
]
