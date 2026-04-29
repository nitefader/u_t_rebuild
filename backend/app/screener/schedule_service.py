"""Application service for durable discovery schedules."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from backend.app.domain._base import utc_now
from backend.app.watchlists import WatchlistService

from .schedule_store import DiscoveryScheduleStore
from .schedules import (
    DiscoverySchedule,
    DiscoveryScheduleApprovalPolicy,
    DiscoveryScheduleExecution,
    DiscoveryScheduleExecutionStatus,
    DiscoverySchedulePatchRequest,
    DiscoveryScheduleStatus,
    DiscoveryScheduleTargetKind,
    DiscoveryScheduleTrigger,
    DiscoveryScheduleWriteRequest,
    next_run_at,
    schedule_from_request,
)
from .service import ScreenerExecutionService


class DiscoveryScheduleServiceError(RuntimeError):
    """Operator-readable schedule failure."""


class DiscoveryScheduleBlockedError(DiscoveryScheduleServiceError):
    """The schedule is valid, but current state requires operator review."""


ScreenerFactory = Callable[[], ScreenerExecutionService]
WatchlistFactory = Callable[[], WatchlistService]
Clock = Callable[[], datetime]
STALE_RUNNING_EXECUTION_AFTER = timedelta(minutes=30)


class DiscoveryScheduleService:
    def __init__(
        self,
        *,
        store: DiscoveryScheduleStore,
        screener_service_factory: ScreenerFactory,
        watchlist_service_factory: WatchlistFactory,
        clock: Clock = utc_now,
    ) -> None:
        self._store = store
        self._screeners = screener_service_factory
        self._watchlists = watchlist_service_factory
        self._clock = clock

    def list_schedules(self) -> tuple[DiscoverySchedule, ...]:
        return self._store.list_schedules()

    def get_schedule(self, schedule_id: UUID) -> DiscoverySchedule:
        return self._store.get_schedule(schedule_id)

    def list_executions(
        self,
        *,
        schedule_id: UUID | None = None,
        limit: int = 50,
    ) -> tuple[DiscoveryScheduleExecution, ...]:
        return self._store.list_executions(schedule_id=schedule_id, limit=limit)

    def create_schedule(self, request: DiscoveryScheduleWriteRequest) -> DiscoverySchedule:
        self._validate_target(request)
        now = self._clock()
        schedule = schedule_from_request(request, now=now)
        schedule = schedule.model_copy(
            update={
                "audit_events": (
                    {
                        "type": "discovery_schedule_created",
                        "target_kind": request.target_kind.value,
                        "at": now.isoformat(),
                    },
                )
            }
        )
        return self._store.save_schedule(schedule)

    def patch_schedule(
        self,
        schedule_id: UUID,
        request: DiscoverySchedulePatchRequest,
    ) -> DiscoverySchedule:
        existing = self._store.get_schedule(schedule_id)
        if existing.status == DiscoveryScheduleStatus.ARCHIVED:
            raise DiscoveryScheduleServiceError("archived schedules cannot be edited")
        payload = request.model_dump(exclude_unset=True)
        if "name" in payload and isinstance(payload["name"], str):
            payload["name"] = payload["name"].strip()
        candidate = existing.model_copy(update={**payload, "updated_at": self._clock()})
        self._validate_schedule(candidate)
        next_at = next_run_at(candidate, after=self._clock())
        updated = candidate.model_copy(
            update={
                "status": DiscoveryScheduleStatus.ACTIVE if candidate.enabled else DiscoveryScheduleStatus.PAUSED,
                "next_run_at": next_at,
                "audit_events": (
                    *existing.audit_events,
                    {
                        "type": "discovery_schedule_updated",
                        "at": self._clock().isoformat(),
                    },
                ),
            }
        )
        return self._store.save_schedule(updated)

    def pause_schedule(self, schedule_id: UUID) -> DiscoverySchedule:
        schedule = self._store.get_schedule(schedule_id)
        now = self._clock()
        paused = schedule.model_copy(
            update={
                "enabled": False,
                "status": DiscoveryScheduleStatus.PAUSED,
                "next_run_at": None,
                "updated_at": now,
                "audit_events": (
                    *schedule.audit_events,
                    {"type": "discovery_schedule_paused", "at": now.isoformat()},
                ),
            }
        )
        return self._store.save_schedule(paused)

    def resume_schedule(self, schedule_id: UUID) -> DiscoverySchedule:
        schedule = self._store.get_schedule(schedule_id)
        if schedule.status == DiscoveryScheduleStatus.ARCHIVED:
            raise DiscoveryScheduleServiceError("archived schedules cannot be resumed")
        now = self._clock()
        active = schedule.model_copy(
            update={
                "enabled": True,
                "status": DiscoveryScheduleStatus.ACTIVE,
                "next_run_at": next_run_at(schedule.model_copy(update={"enabled": True, "status": DiscoveryScheduleStatus.ACTIVE}), after=now),
                "updated_at": now,
                "audit_events": (
                    *schedule.audit_events,
                    {"type": "discovery_schedule_resumed", "at": now.isoformat()},
                ),
            }
        )
        return self._store.save_schedule(active)

    def archive_schedule(self, schedule_id: UUID) -> DiscoverySchedule:
        schedule = self._store.get_schedule(schedule_id)
        now = self._clock()
        archived = schedule.model_copy(
            update={
                "enabled": False,
                "status": DiscoveryScheduleStatus.ARCHIVED,
                "next_run_at": None,
                "updated_at": now,
                "audit_events": (
                    *schedule.audit_events,
                    {"type": "discovery_schedule_archived", "at": now.isoformat()},
                ),
            }
        )
        return self._store.save_schedule(archived)

    def delete_schedule(self, schedule_id: UUID) -> None:
        if self._store.execution_count(schedule_id):
            raise DiscoveryScheduleServiceError(
                "schedule has execution history; archive it instead of deleting audit evidence"
            )
        self._store.delete_schedule(schedule_id)

    def run_due(self, *, now: datetime | None = None) -> tuple[DiscoveryScheduleExecution, ...]:
        now = now or self._clock()
        executions: list[DiscoveryScheduleExecution] = []
        for schedule in self._store.list_due_schedules(now=now):
            executions.append(self.run_schedule(schedule.schedule_id, trigger=DiscoveryScheduleTrigger.DUE))
        return tuple(executions)

    def run_schedule(
        self,
        schedule_id: UUID,
        *,
        trigger: DiscoveryScheduleTrigger = DiscoveryScheduleTrigger.RUN_NOW,
    ) -> DiscoveryScheduleExecution:
        schedule = self._store.get_schedule(schedule_id)
        if schedule.status == DiscoveryScheduleStatus.ARCHIVED:
            raise DiscoveryScheduleServiceError("archived schedules cannot run")
        started = self._clock()
        abandoned = self._store.abandon_stale_running_executions(
            schedule_id,
            stale_before=started - STALE_RUNNING_EXECUTION_AFTER,
            completed_at=started,
        )
        if abandoned:
            schedule = self._record_abandoned_executions(schedule, abandoned, at=started)
        else:
            schedule = self._store.get_schedule(schedule_id)
        execution = DiscoveryScheduleExecution(
            schedule_id=schedule.schedule_id,
            schedule_name=schedule.name,
            target_kind=schedule.target_kind,
            trigger=trigger,
            started_at=started,
            audit_events=(
                {
                    "type": "discovery_schedule_execution_started",
                    "schedule_id": str(schedule.schedule_id),
                    "target_kind": schedule.target_kind.value,
                    "trigger": trigger.value,
                    "at": started.isoformat(),
                },
            ),
        )
        if not self._store.claim_execution(execution):
            raise DiscoveryScheduleServiceError("schedule already has a running execution")
        self._store.save_schedule(
            schedule.model_copy(
                update={
                    "last_attempt_at": started,
                    "last_status": DiscoveryScheduleExecutionStatus.RUNNING,
                    "last_error": None,
                    "updated_at": started,
                }
            )
        )
        try:
            completed_execution = self._execute(schedule, execution)
        except DiscoveryScheduleBlockedError as exc:
            completed_execution = self._complete_execution(
                execution,
                status=DiscoveryScheduleExecutionStatus.BLOCKED,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            completed_execution = self._complete_execution(
                execution,
                status=DiscoveryScheduleExecutionStatus.FAILED,
                error=str(exc),
            )
        self._store.save_execution(completed_execution)
        self._finish_schedule(schedule, completed_execution)
        return completed_execution

    def _execute(
        self,
        schedule: DiscoverySchedule,
        execution: DiscoveryScheduleExecution,
    ) -> DiscoveryScheduleExecution:
        if schedule.target_kind == DiscoveryScheduleTargetKind.SCREENER_RUN:
            if schedule.screener_id is None or schedule.screener_version_id is None:
                raise DiscoveryScheduleServiceError("screener schedule is missing target ids")
            run = self._screeners().run_screener(
                schedule.screener_id,
                version_id=schedule.screener_version_id,
                run_kind="scheduled",
            )
            if run.status.value == "failed":
                return self._complete_execution(
                    execution,
                    status=DiscoveryScheduleExecutionStatus.FAILED,
                    screener_run_id=run.id,
                    error=run.error or "scheduled Screener run failed",
                )
            return self._complete_execution(
                execution,
                status=DiscoveryScheduleExecutionStatus.COMPLETED,
                screener_run_id=run.id,
            )

        if schedule.watchlist_id is None:
            raise DiscoveryScheduleServiceError("watchlist schedule is missing watchlist_id")
        watchlists = self._watchlists()
        active_refs = watchlists.active_deployment_names_for_watchlist(schedule.watchlist_id)
        if active_refs and schedule.approval_policy != DiscoveryScheduleApprovalPolicy.AUTO_SNAPSHOT:
            raise DiscoveryScheduleBlockedError(
                "active deployments reference this Watchlist; enable auto_snapshot approval "
                "or refresh manually after review: "
                + ", ".join(active_refs)
            )
        snapshot = watchlists.take_snapshot(
            schedule.watchlist_id,
            note=f"scheduled refresh: {schedule.name}",
        )
        return self._complete_execution(
            execution,
            status=DiscoveryScheduleExecutionStatus.COMPLETED,
            watchlist_snapshot_id=snapshot.watchlist_snapshot_id,
            added_symbols=snapshot.added_symbols,
            removed_symbols=snapshot.removed_symbols,
            stayed_symbols=snapshot.stayed_symbols,
        )

    def _finish_schedule(
        self,
        schedule: DiscoverySchedule,
        execution: DiscoveryScheduleExecution,
    ) -> None:
        now = execution.completed_at or self._clock()
        success = execution.status == DiscoveryScheduleExecutionStatus.COMPLETED
        next_at = next_run_at(schedule, after=now)
        updated = schedule.model_copy(
            update={
                "last_attempt_at": execution.started_at,
                "last_success_at": now if success else schedule.last_success_at,
                "next_run_at": next_at,
                "last_status": execution.status,
                "last_error": execution.error,
                "last_screener_run_id": execution.screener_run_id or schedule.last_screener_run_id,
                "last_watchlist_snapshot_id": execution.watchlist_snapshot_id or schedule.last_watchlist_snapshot_id,
                "execution_count": schedule.execution_count + 1,
                "updated_at": now,
                "audit_events": (
                    *schedule.audit_events,
                    {
                        "type": "discovery_schedule_execution_finished",
                        "execution_id": str(execution.execution_id),
                        "status": execution.status.value,
                        "at": now.isoformat(),
                    },
                ),
            }
        )
        self._store.save_schedule(updated)

    def _record_abandoned_executions(
        self,
        schedule: DiscoverySchedule,
        abandoned: tuple[DiscoveryScheduleExecution, ...],
        *,
        at: datetime,
    ) -> DiscoverySchedule:
        updated = schedule.model_copy(
            update={
                "last_status": DiscoveryScheduleExecutionStatus.FAILED,
                "last_error": "stale running execution abandoned after scheduler timeout",
                "execution_count": schedule.execution_count + len(abandoned),
                "updated_at": at,
                "audit_events": (
                    *schedule.audit_events,
                    *(
                        {
                            "type": "discovery_schedule_execution_abandoned",
                            "execution_id": str(execution.execution_id),
                            "at": at.isoformat(),
                        }
                        for execution in abandoned
                    ),
                ),
            }
        )
        return self._store.save_schedule(updated)

    def _complete_execution(
        self,
        execution: DiscoveryScheduleExecution,
        *,
        status: DiscoveryScheduleExecutionStatus,
        screener_run_id: UUID | None = None,
        watchlist_snapshot_id: UUID | None = None,
        added_symbols: tuple[str, ...] = (),
        removed_symbols: tuple[str, ...] = (),
        stayed_symbols: tuple[str, ...] = (),
        error: str | None = None,
    ) -> DiscoveryScheduleExecution:
        completed = self._clock()
        return execution.model_copy(
            update={
                "completed_at": completed,
                "status": status,
                "screener_run_id": screener_run_id,
                "watchlist_snapshot_id": watchlist_snapshot_id,
                "added_symbols": added_symbols,
                "removed_symbols": removed_symbols,
                "stayed_symbols": stayed_symbols,
                "error": error,
                "audit_events": (
                    *execution.audit_events,
                    {
                        "type": "discovery_schedule_execution_completed",
                        "status": status.value,
                        "at": completed.isoformat(),
                    },
                ),
            }
        )

    def _validate_target(self, request: DiscoveryScheduleWriteRequest) -> None:
        if request.target_kind == DiscoveryScheduleTargetKind.SCREENER_RUN:
            service = self._screeners()
            if request.screener_id is None or request.screener_version_id is None:
                raise DiscoveryScheduleServiceError("screener schedule requires target ids")
            _, versions = service.get_screener(request.screener_id)
            if request.screener_version_id not in {version.id for version in versions}:
                raise DiscoveryScheduleServiceError(
                    "screener_version_id does not belong to this Screener"
                )
            return
        if request.watchlist_id is None:
            raise DiscoveryScheduleServiceError("watchlist schedule requires watchlist_id")
        self._watchlists().get_watchlist(request.watchlist_id)

    def _validate_schedule(self, schedule: DiscoverySchedule) -> None:
        request = DiscoveryScheduleWriteRequest(
            name=schedule.name,
            target_kind=schedule.target_kind,
            screener_id=schedule.screener_id,
            screener_version_id=schedule.screener_version_id,
            watchlist_id=schedule.watchlist_id,
            cadence=schedule.cadence,
            interval_minutes=schedule.interval_minutes,
            time_of_day=schedule.time_of_day,
            weekdays=schedule.weekdays,
            timezone_name=schedule.timezone_name,
            session_start=schedule.session_start,
            session_end=schedule.session_end,
            approval_policy=schedule.approval_policy,
            enabled=schedule.enabled,
        )
        self._validate_target(request)


def create_discovery_schedule_service_from_environment() -> DiscoveryScheduleService:
    from backend.app.config.runtime_paths import get_runtime_db_path
    from backend.app.screener.runtime import create_screener_service_from_environment
    from backend.app.watchlists.runtime_service import create_watchlist_service_from_environment

    return DiscoveryScheduleService(
        store=DiscoveryScheduleStore(db_path=get_runtime_db_path()),
        screener_service_factory=create_screener_service_from_environment,
        watchlist_service_factory=create_watchlist_service_from_environment,
        clock=lambda: datetime.now(timezone.utc),
    )
