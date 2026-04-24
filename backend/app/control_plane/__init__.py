"""Runtime control-plane safety gates."""

from .client_order_id import (
    build_program_client_order_id,
    parse_order_deployment_id,
    parse_order_intent,
)

_SERVICE_EXPORTS = {
    "AccountControlState",
    "CancellationSweepResult",
    "ControlGateDecision",
    "ControlPlane",
    "DeploymentControlState",
    "KillSwitchEvent",
    "hydrate_control_plane",
}


def __getattr__(name: str):
    if name in _SERVICE_EXPORTS:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)

__all__ = [
    "AccountControlState",
    "CancellationSweepResult",
    "ControlGateDecision",
    "ControlPlane",
    "DeploymentControlState",
    "KillSwitchEvent",
    "build_program_client_order_id",
    "hydrate_control_plane",
    "parse_order_deployment_id",
    "parse_order_intent",
]
