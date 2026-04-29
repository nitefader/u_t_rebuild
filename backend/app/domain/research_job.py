"""Async research-run job model.

Doctrine: research POST routes that previously executed synchronously can now
enqueue a ResearchJob and return immediately. A background worker (in
``backend/app/research/jobs/``) dispatches the actual run via the same
service the sync path uses, persists the resulting evidence, and updates the
job's status + progress + result_run_id.

Operators can poll ``GET /api/v1/research/jobs/{job_id}`` for status, watch
the JobMonitor in the frontend, and request cancellation via
``POST /api/v1/research/jobs/{job_id}/cancel``. Cancellation is cooperative
— services check ``ProgressReporter.cancel_requested()`` between folds /
candidates and raise ``RunCanceled`` to abort cleanly.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from ._base import DomainSchema, JsonDict, utc_now


class ResearchJobKind(StrEnum):
    BACKTEST = "backtest"
    WALK_FORWARD = "walk_forward"
    OPTIMIZATION = "optimization"


class ResearchJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ResearchJobProgress(DomainSchema):
    current: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    label: str = ""
    message: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ResearchJob(DomainSchema):
    """A backgrounded research-run dispatch unit.

    The ``request`` JSON is the same shape the sync POST routes accept
    (so a single payload schema serves both async and sync paths). The
    ``result_run_id`` is populated on completion and points at the
    persisted ``BacktestRun`` / ``WalkForwardRun`` / ``OptimizationRun``
    evidence row.
    """

    job_id: UUID = Field(default_factory=uuid4)
    kind: ResearchJobKind
    status: ResearchJobStatus = ResearchJobStatus.QUEUED
    request: JsonDict = Field(default_factory=dict)
    progress: ResearchJobProgress = Field(default_factory=ResearchJobProgress)
    cancel_requested: bool = False
    result_run_id: UUID | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    operator_session_id: str | None = None
    metadata: JsonDict = Field(default_factory=dict)


def is_terminal(status: ResearchJobStatus) -> bool:
    return status in {
        ResearchJobStatus.COMPLETED,
        ResearchJobStatus.FAILED,
        ResearchJobStatus.CANCELED,
    }


def job_summary(job: ResearchJob) -> dict[str, Any]:
    """Compact serialization used by the JobMonitor list view."""
    return {
        "job_id": str(job.job_id),
        "kind": job.kind.value,
        "status": job.status.value,
        "progress_current": job.progress.current,
        "progress_total": job.progress.total,
        "progress_label": job.progress.label,
        "result_run_id": str(job.result_run_id) if job.result_run_id else None,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }
