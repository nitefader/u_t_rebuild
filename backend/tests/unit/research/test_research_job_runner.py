"""Tests for the async ResearchJobRunner.

Doctrine: dispatch every backgrounded research run through the same service
the sync route uses. Persist progress + cancel state to SQLite so the
frontend can read it. Cooperative cancellation via ProgressReporter.
"""

from __future__ import annotations

import time
from uuid import uuid4

from backend.app.domain import ResearchJobKind, ResearchJobStatus
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.research.jobs import JobReporter, ResearchJobRunner, build_dispatcher
from backend.app.research.progress import RunCanceled


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_runner_dispatches_completes_and_records_result_run_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    captured_run_id = uuid4()

    def _bt(job, reporter: JobReporter):
        reporter.update(current=1, total=1, label="run", message="done")
        return captured_run_id

    runner = ResearchJobRunner(
        store=store,
        dispatchers=build_dispatcher(backtest=_bt, walk_forward=_bt, optimization=_bt),
    )
    try:
        job = runner.submit(kind=ResearchJobKind.BACKTEST, request={})
        assert _wait_until(
            lambda: store.load_research_job(job.job_id).status == ResearchJobStatus.COMPLETED
        )
        completed = store.load_research_job(job.job_id)
        assert completed.result_run_id == captured_run_id
        assert completed.error is None
        assert completed.progress.current == 1
    finally:
        runner.shutdown(wait=True)


def test_runner_records_failure_in_job_row(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")

    def _failing(job, reporter):
        raise RuntimeError("boom")

    runner = ResearchJobRunner(
        store=store,
        dispatchers=build_dispatcher(
            backtest=_failing, walk_forward=_failing, optimization=_failing
        ),
    )
    try:
        job = runner.submit(kind=ResearchJobKind.OPTIMIZATION, request={})
        assert _wait_until(
            lambda: store.load_research_job(job.job_id).status == ResearchJobStatus.FAILED
        )
        failed = store.load_research_job(job.job_id)
        assert failed.error is not None
        assert "boom" in failed.error
    finally:
        runner.shutdown(wait=True)


def test_runner_honors_cooperative_cancel(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    started = []

    def _long_running(job, reporter: JobReporter):
        started.append(True)
        for i in range(50):
            reporter.update(current=i, total=50, label="folds")
            if reporter.cancel_requested():
                raise RunCanceled("operator stopped")
            time.sleep(0.05)
        return uuid4()

    runner = ResearchJobRunner(
        store=store,
        dispatchers=build_dispatcher(
            backtest=_long_running, walk_forward=_long_running, optimization=_long_running
        ),
    )
    try:
        job = runner.submit(kind=ResearchJobKind.WALK_FORWARD, request={})
        assert _wait_until(lambda: bool(started))
        runner.request_cancel(job.job_id)
        assert _wait_until(
            lambda: store.load_research_job(job.job_id).status == ResearchJobStatus.CANCELED,
            timeout=5.0,
        )
        canceled = store.load_research_job(job.job_id)
        assert canceled.status == ResearchJobStatus.CANCELED
        assert canceled.error is not None
        assert canceled.progress.current < 50  # didn't finish
    finally:
        runner.shutdown(wait=True)


def test_runner_progress_writes_are_visible_to_other_callers(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    proceed = []

    def _stepper(job, reporter):
        for i in range(1, 6):
            reporter.update(current=i, total=5, label="folds", message=f"step {i}")
            time.sleep(0.05)
        proceed.append(True)
        return uuid4()

    runner = ResearchJobRunner(
        store=store,
        dispatchers=build_dispatcher(
            backtest=_stepper, walk_forward=_stepper, optimization=_stepper
        ),
    )
    try:
        job = runner.submit(kind=ResearchJobKind.WALK_FORWARD, request={})
        # Poll a few times mid-run; we should observe progress monotonically rising.
        seen = set()
        for _ in range(40):
            current = store.load_research_job(job.job_id).progress.current
            seen.add(current)
            if current == 5:
                break
            time.sleep(0.05)
        assert max(seen) == 5
        assert _wait_until(lambda: bool(proceed))
    finally:
        runner.shutdown(wait=True)
