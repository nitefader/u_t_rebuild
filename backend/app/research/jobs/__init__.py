"""Async research-job runner.

Doctrine: research POST routes can enqueue a ResearchJob; this module owns
the background worker pool that dispatches jobs through the same service
layer the sync path uses (BacktestExecutionService /
WalkForwardExecutionService / OptimizationExecutionService). Per-fold and
per-candidate progress events flow back to the operator via JobRecord
updates persisted to SQLite; the frontend polls the jobs API.
"""

from .runner import (
    JobDispatcher,
    JobReporter,
    JobRunnerError,
    ResearchJobRunner,
    build_dispatcher,
)

__all__ = [
    "JobDispatcher",
    "JobReporter",
    "JobRunnerError",
    "ResearchJobRunner",
    "build_dispatcher",
]
