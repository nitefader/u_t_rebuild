"""ProgressReporter protocol for cooperative cancellation + per-step progress.

Doctrine: research services are dispatched both synchronously (existing POST
routes) and asynchronously via the JobRunner. Both paths use the same
service.create_run(...) entry point. The async path passes a ProgressReporter
that updates job state + checks cancellation between major loop iterations.
The sync path passes ``NULL_REPORTER`` so the services see a no-op.
"""

from __future__ import annotations

from typing import Protocol


class RunCanceled(RuntimeError):
    """Raised by services when the supplied ProgressReporter signals cancel."""


class ProgressReporter(Protocol):
    def update(
        self,
        *,
        current: int,
        total: int,
        label: str,
        message: str | None = None,
    ) -> None: ...

    def cancel_requested(self) -> bool: ...


class _NullReporter:
    def update(
        self,
        *,
        current: int,
        total: int,
        label: str,
        message: str | None = None,
    ) -> None:
        return None

    def cancel_requested(self) -> bool:
        return False


NULL_REPORTER: ProgressReporter = _NullReporter()


def check_cancel(reporter: ProgressReporter | None) -> None:
    if reporter is not None and reporter.cancel_requested():
        raise RunCanceled("operator-requested cancel")
