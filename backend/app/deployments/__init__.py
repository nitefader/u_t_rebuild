"""Deployment CRUD package.

A Deployment is a running Strategy publisher over Watchlists, with
subscribed Accounts. This package owns ONLY the durable definition
record (CRUD) plus a thin lifecycle facade. The actual runtime
composition root lives in ``backend.app.pipeline.orchestrator``
under Operation Turtle Shell ownership; this package never
introduces a second runtime root.

Doctrine: Deployment publishes SignalPlans, never tracks positions
internally, never sizes orders, never duplicated per Account.
"""

from .models import (
    Deployment,
    DeploymentLifecycleStatus,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentWriteRequest,
)
from .service import DeploymentService, DeploymentServiceError

__all__ = [
    "Deployment",
    "DeploymentLifecycleStatus",
    "DeploymentListResponse",
    "DeploymentResponse",
    "DeploymentService",
    "DeploymentServiceError",
    "DeploymentWriteRequest",
]
