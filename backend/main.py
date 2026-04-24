from __future__ import annotations

import logging

from backend.app.runtime import RecoveryResult, RuntimeRecoveryOrchestrator

logger = logging.getLogger(__name__)


def run_startup_recovery(
    *,
    persistence_store,
    broker_adapter,
    broker_sync,
    governor_service,
    control_plane,
    runtime_state_store,
) -> RecoveryResult:
    """Startup hook to run after persistence init and before runtime starts."""

    recovery = RuntimeRecoveryOrchestrator(
        persistence_store=persistence_store,
        broker_adapter=broker_adapter,
        broker_sync=broker_sync,
        governor_service=governor_service,
        control_plane=control_plane,
        runtime_state_store=runtime_state_store,
    )
    result = recovery.run_startup_recovery()
    logger.info("runtime startup recovery result: %s", result.model_dump())
    return result
