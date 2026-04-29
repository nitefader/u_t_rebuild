"""ResearchJobRunner — ThreadPoolExecutor-backed async dispatch.

Doctrine: dispatch every backgrounded research run through the same service
the sync route uses. Persist progress + cancel state to SQLite so the
frontend (and any other backend caller) can read it. Cooperative
cancellation via ProgressReporter.

Concurrency model:
- ThreadPoolExecutor (default 4 workers) runs job functions.
- Job lifecycle: queued → running → (completed | failed | canceled).
- Cancellation is cooperative — services check ``ProgressReporter.cancel_requested()``
  between folds / candidates and raise ``RunCanceled`` to abort cleanly.
- The runner persists JobRecord updates inside a per-job lock so progress
  bumps don't race the cancel-flag write.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Protocol
from uuid import UUID

from backend.app.domain import (
    ResearchJob,
    ResearchJobKind,
    ResearchJobProgress,
    ResearchJobStatus,
)
from backend.app.domain._base import utc_now
from backend.app.research.progress import RunCanceled


_LOG = logging.getLogger(__name__)


class JobRunnerError(RuntimeError):
    pass


class JobDispatcher(Protocol):
    """A function that takes a ResearchJob (with ``request`` payload) and a
    progress reporter, runs the matching service, and returns the persisted
    research-evidence run id (UUID).
    """

    def __call__(self, *, job: ResearchJob, reporter: "JobReporter") -> UUID: ...


class _JobStore(Protocol):
    def save_research_job(self, job: ResearchJob) -> ResearchJob: ...
    def load_research_job(self, job_id: UUID) -> ResearchJob: ...


class JobReporter:
    """ProgressReporter implementation backed by the SQLite job store.

    One reporter per running job. ``update`` writes a fresh JobProgress and
    persists. ``cancel_requested`` re-reads the latest job row to pick up
    cancel toggles set by other request handlers.
    """

    def __init__(self, *, job_id: UUID, store: _JobStore, lock: threading.Lock) -> None:
        self._job_id = job_id
        self._store = store
        self._lock = lock

    def update(
        self,
        *,
        current: int,
        total: int,
        label: str,
        message: str | None = None,
    ) -> None:
        with self._lock:
            job = self._store.load_research_job(self._job_id)
            updated = job.model_copy(
                update={
                    "progress": ResearchJobProgress(
                        current=current,
                        total=total,
                        label=label,
                        message=message,
                        updated_at=utc_now(),
                    ),
                }
            )
            self._store.save_research_job(updated)

    def cancel_requested(self) -> bool:
        try:
            job = self._store.load_research_job(self._job_id)
        except KeyError:
            return False
        return bool(job.cancel_requested)


class ResearchJobRunner:
    """Async runner. ``submit(...)`` enqueues a job; the worker pool dispatches it.

    The runner is process-local — for multi-process deployments switch to a
    real broker (Celery / RQ / arq). For our single-operator single-process
    setup ThreadPoolExecutor is sufficient and avoids IPC complexity.
    """

    def __init__(
        self,
        *,
        store: _JobStore,
        dispatchers: dict[ResearchJobKind, JobDispatcher],
        max_workers: int = 4,
    ) -> None:
        self._store = store
        self._dispatchers = dispatchers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research-job")
        self._futures: dict[UUID, Future[Any]] = {}
        self._locks: dict[UUID, threading.Lock] = {}
        self._mu = threading.Lock()

    def submit(
        self,
        *,
        kind: ResearchJobKind,
        request: dict[str, Any],
        operator_session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResearchJob:
        if kind not in self._dispatchers:
            raise JobRunnerError(f"no dispatcher registered for kind '{kind.value}'")
        job = ResearchJob(
            kind=kind,
            status=ResearchJobStatus.QUEUED,
            request=request,
            operator_session_id=operator_session_id,
            metadata=metadata or {},
        )
        self._store.save_research_job(job)
        lock = threading.Lock()
        with self._mu:
            self._locks[job.job_id] = lock
        future = self._executor.submit(self._run, job_id=job.job_id, lock=lock)
        with self._mu:
            self._futures[job.job_id] = future
        return job

    def request_cancel(self, job_id: UUID) -> ResearchJob:
        return self._store.request_research_job_cancel(job_id)

    def shutdown(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self, *, job_id: UUID, lock: threading.Lock) -> None:
        try:
            with lock:
                job = self._store.load_research_job(job_id)
                started = utc_now()
                job = job.model_copy(
                    update={
                        "status": ResearchJobStatus.RUNNING,
                        "started_at": started,
                    }
                )
                self._store.save_research_job(job)
            dispatcher = self._dispatchers.get(job.kind)
            if dispatcher is None:
                raise JobRunnerError(f"no dispatcher for kind '{job.kind.value}'")
            reporter = JobReporter(job_id=job_id, store=self._store, lock=lock)
            try:
                result_run_id = dispatcher(job=job, reporter=reporter)
            except RunCanceled as canceled:
                self._finalize(
                    job_id=job_id,
                    lock=lock,
                    status=ResearchJobStatus.CANCELED,
                    error=str(canceled),
                )
                _LOG.info("research-job %s canceled", job_id)
                return
            self._finalize(
                job_id=job_id,
                lock=lock,
                status=ResearchJobStatus.COMPLETED,
                result_run_id=result_run_id,
            )
        except Exception as exc:  # noqa: BLE001 — capture every failure into the job row
            self._finalize(
                job_id=job_id,
                lock=lock,
                status=ResearchJobStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )
            _LOG.exception("research-job %s failed", job_id)

    def _finalize(
        self,
        *,
        job_id: UUID,
        lock: threading.Lock,
        status: ResearchJobStatus,
        result_run_id: UUID | None = None,
        error: str | None = None,
    ) -> None:
        with lock:
            job = self._store.load_research_job(job_id)
            updated = job.model_copy(
                update={
                    "status": status,
                    "finished_at": utc_now(),
                    "result_run_id": result_run_id,
                    "error": error,
                }
            )
            self._store.save_research_job(updated)


def build_dispatcher(
    *,
    backtest: Callable[[ResearchJob, JobReporter], UUID],
    walk_forward: Callable[[ResearchJob, JobReporter], UUID],
    optimization: Callable[[ResearchJob, JobReporter], UUID],
) -> dict[ResearchJobKind, JobDispatcher]:
    """Wrap caller-supplied per-kind functions into the dispatcher map.

    Each function takes (job, reporter) and returns the persisted run id.
    The caller (route layer) builds dispatchers that close over the
    BacktestExecutionService / WalkForwardExecutionService /
    OptimizationExecutionService + their dependencies.
    """

    def _wrap(fn: Callable[[ResearchJob, JobReporter], UUID]) -> JobDispatcher:
        def _adapter(*, job: ResearchJob, reporter: JobReporter) -> UUID:
            return fn(job, reporter)
        return _adapter

    return {
        ResearchJobKind.BACKTEST: _wrap(backtest),
        ResearchJobKind.WALK_FORWARD: _wrap(walk_forward),
        ResearchJobKind.OPTIMIZATION: _wrap(optimization),
    }
