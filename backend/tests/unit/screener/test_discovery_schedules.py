from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.features import NormalizedBar
from backend.app.screener.domain import (
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerMetric,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
    ScreenerVersion,
)
from backend.app.screener.schedule_service import DiscoveryScheduleService, DiscoveryScheduleServiceError
from backend.app.screener.schedule_store import DiscoveryScheduleStore
from backend.app.screener.schedules import (
    DiscoveryScheduleApprovalPolicy,
    DiscoveryScheduleCadence,
    DiscoveryScheduleExecution,
    DiscoveryScheduleExecutionStatus,
    DiscoveryScheduleTargetKind,
    DiscoveryScheduleTrigger,
    DiscoveryScheduleWriteRequest,
)
from backend.app.screener.service import ScreenerExecutionService
from backend.app.screener.sources import HistoricalBarsLookup, MetricSource, UniverseResolver
from backend.app.screener.store import ScreenerStore
from backend.app.watchlists import WatchlistKind, WatchlistService, WatchlistWriteRequest
from backend.app.watchlists.persistence import WatchlistRepository


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class _Bars(HistoricalBarsLookup):
    def get_bars(self, *, symbol, timeframe, start, end):  # noqa: D401, ARG002
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return tuple(
            NormalizedBar(
                symbol=symbol,
                timeframe="1d",
                timestamp=base + timedelta(days=index),
                open=100 + index,
                high=101 + index,
                low=99 + index,
                close=100 + index,
                volume=3_000_000 if index == 39 else 1_000_000,
            )
            for index in range(40)
        )


@dataclass(frozen=True)
class _References:
    names: tuple[str, ...] = ()

    def active_deployment_names_for_watchlist(self, watchlist_id: UUID) -> tuple[str, ...]:  # noqa: D401, ARG002
        return self.names


def _screener_service(tmp_path: Path) -> ScreenerExecutionService:
    return ScreenerExecutionService(
        store=ScreenerStore(db_path=tmp_path / "screener.db"),
        universe_resolver=UniverseResolver(),
        metric_source=MetricSource(bars=_Bars()),
    )


def _watchlist_service(tmp_path: Path, *, refs: tuple[str, ...] = ()) -> WatchlistService:
    return WatchlistService(
        repository=WatchlistRepository(tmp_path / "runtime.db"),
        reference_lookup=_References(refs),
    )


def _schedule_service(
    tmp_path: Path,
    *,
    screeners: ScreenerExecutionService,
    watchlists: WatchlistService,
    clock: _Clock,
) -> DiscoveryScheduleService:
    return DiscoveryScheduleService(
        store=DiscoveryScheduleStore(db_path=tmp_path / "runtime.db"),
        screener_service_factory=lambda: screeners,
        watchlist_service_factory=lambda: watchlists,
        clock=clock,
    )


def test_screener_schedule_run_due_creates_immutable_scheduled_run_and_next_run(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc))
    screeners = _screener_service(tmp_path)
    watchlists = _watchlist_service(tmp_path)
    service = _schedule_service(tmp_path, screeners=screeners, watchlists=watchlists, clock=clock)
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="AAPL RVOL",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("AAPL",),
        ),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.RELATIVE_VOLUME,
                operator=ScreenerCriterionOperator.GTE,
                value=2,
            ),
        ),
    )
    screener, saved_version = screeners.create_screener(
        name="AAPL RVOL",
        description=None,
        version=version,
    )

    schedule = service.create_schedule(
        DiscoveryScheduleWriteRequest(
            name="Premarket AAPL RVOL",
            target_kind=DiscoveryScheduleTargetKind.SCREENER_RUN,
            screener_id=screener.id,
            screener_version_id=saved_version.id,
            cadence=DiscoveryScheduleCadence.DAILY,
            time_of_day="09:15",
            weekdays=(0, 1, 2, 3, 4),
        )
    )

    assert schedule.next_run_at == datetime(2026, 4, 29, 13, 15, tzinfo=timezone.utc)
    clock.now = datetime(2026, 4, 29, 13, 16, tzinfo=timezone.utc)
    executions = service.run_due(now=clock.now)

    assert len(executions) == 1
    execution = executions[0]
    assert execution.status == DiscoveryScheduleExecutionStatus.COMPLETED
    assert execution.screener_run_id is not None
    run = screeners.get_run(execution.screener_run_id)
    assert run.run_kind == "scheduled"
    assert run.matched_count == 1
    persisted = service.get_schedule(schedule.schedule_id)
    assert persisted.last_status == DiscoveryScheduleExecutionStatus.COMPLETED
    assert persisted.last_screener_run_id == execution.screener_run_id
    assert persisted.execution_count == 1
    assert persisted.next_run_at == datetime(2026, 4, 30, 13, 15, tzinfo=timezone.utc)

    restarted = _schedule_service(tmp_path, screeners=screeners, watchlists=watchlists, clock=clock)
    assert restarted.get_schedule(schedule.schedule_id).next_run_at == persisted.next_run_at


def test_watchlist_schedule_blocks_active_deployment_without_auto_snapshot(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 4, 29, 13, 16, tzinfo=timezone.utc))
    screeners = _screener_service(tmp_path)
    watchlists = _watchlist_service(tmp_path, refs=("Opening Range Deployment",))
    watchlist = watchlists.create_watchlist(
        WatchlistWriteRequest(
            name="Opening Range Entries",
            kind=WatchlistKind.STATIC,
            static_symbols=("AAPL", "MSFT"),
        )
    )
    service = _schedule_service(tmp_path, screeners=screeners, watchlists=watchlists, clock=clock)
    schedule = service.create_schedule(
        DiscoveryScheduleWriteRequest(
            name="Open-hour refresh",
            target_kind=DiscoveryScheduleTargetKind.WATCHLIST_REFRESH,
            watchlist_id=watchlist.watchlist_id,
            cadence=DiscoveryScheduleCadence.EVERY_N_MINUTES,
            interval_minutes=15,
            session_start="09:30",
            session_end="10:30",
        )
    )

    execution = service.run_schedule(schedule.schedule_id, trigger=DiscoveryScheduleTrigger.RUN_NOW)

    assert execution.status == DiscoveryScheduleExecutionStatus.BLOCKED
    assert "Opening Range Deployment" in (execution.error or "")
    assert watchlists.get_watchlist(watchlist.watchlist_id).watchlist.snapshot_count == 0


def test_watchlist_schedule_auto_snapshot_records_snapshot_diff(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 4, 29, 13, 16, tzinfo=timezone.utc))
    screeners = _screener_service(tmp_path)
    watchlists = _watchlist_service(tmp_path, refs=("Opening Range Deployment",))
    watchlist = watchlists.create_watchlist(
        WatchlistWriteRequest(
            name="Opening Range Entries",
            kind=WatchlistKind.STATIC,
            static_symbols=("AAPL", "MSFT"),
        )
    )
    service = _schedule_service(tmp_path, screeners=screeners, watchlists=watchlists, clock=clock)
    schedule = service.create_schedule(
        DiscoveryScheduleWriteRequest(
            name="Auto-approved open refresh",
            target_kind=DiscoveryScheduleTargetKind.WATCHLIST_REFRESH,
            watchlist_id=watchlist.watchlist_id,
            cadence=DiscoveryScheduleCadence.EVERY_N_MINUTES,
            interval_minutes=15,
            session_start="09:30",
            session_end="10:30",
            approval_policy=DiscoveryScheduleApprovalPolicy.AUTO_SNAPSHOT,
        )
    )

    execution = service.run_schedule(schedule.schedule_id, trigger=DiscoveryScheduleTrigger.RUN_NOW)

    assert execution.status == DiscoveryScheduleExecutionStatus.COMPLETED
    assert execution.watchlist_snapshot_id is not None
    assert execution.added_symbols == ("AAPL", "MSFT")
    response = watchlists.get_watchlist(watchlist.watchlist_id)
    assert response.watchlist.snapshot_count == 1
    assert response.snapshots[0].source_label == "Static Watchlist"


def test_schedule_overlap_and_delete_guards(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 4, 29, 13, 16, tzinfo=timezone.utc))
    screeners = _screener_service(tmp_path)
    watchlists = _watchlist_service(tmp_path)
    watchlist = watchlists.create_watchlist(
        WatchlistWriteRequest(name="Static", static_symbols=("AAPL",))
    )
    store = DiscoveryScheduleStore(db_path=tmp_path / "runtime.db")
    service = DiscoveryScheduleService(
        store=store,
        screener_service_factory=lambda: screeners,
        watchlist_service_factory=lambda: watchlists,
        clock=clock,
    )
    schedule = service.create_schedule(
        DiscoveryScheduleWriteRequest(
            name="Static snapshot",
            target_kind=DiscoveryScheduleTargetKind.WATCHLIST_REFRESH,
            watchlist_id=watchlist.watchlist_id,
            cadence=DiscoveryScheduleCadence.DAILY,
            time_of_day="09:15",
        )
    )
    store.save_execution(
        DiscoveryScheduleExecution(
            schedule_id=schedule.schedule_id,
            schedule_name=schedule.name,
            target_kind=schedule.target_kind,
            trigger=DiscoveryScheduleTrigger.DUE,
            started_at=clock.now,
            status=DiscoveryScheduleExecutionStatus.RUNNING,
        )
    )

    with pytest.raises(DiscoveryScheduleServiceError, match="running execution"):
        service.run_schedule(schedule.schedule_id)

    with pytest.raises(DiscoveryScheduleServiceError, match="execution history"):
        service.delete_schedule(schedule.schedule_id)


def test_schedule_abandons_stale_running_execution_before_retry(tmp_path: Path) -> None:
    clock = _Clock(datetime(2026, 4, 29, 13, 16, tzinfo=timezone.utc))
    screeners = _screener_service(tmp_path)
    watchlists = _watchlist_service(tmp_path)
    watchlist = watchlists.create_watchlist(
        WatchlistWriteRequest(name="Static", static_symbols=("AAPL",))
    )
    store = DiscoveryScheduleStore(db_path=tmp_path / "runtime.db")
    service = DiscoveryScheduleService(
        store=store,
        screener_service_factory=lambda: screeners,
        watchlist_service_factory=lambda: watchlists,
        clock=clock,
    )
    schedule = service.create_schedule(
        DiscoveryScheduleWriteRequest(
            name="Static snapshot",
            target_kind=DiscoveryScheduleTargetKind.WATCHLIST_REFRESH,
            watchlist_id=watchlist.watchlist_id,
            cadence=DiscoveryScheduleCadence.DAILY,
            time_of_day="09:15",
        )
    )
    stale_execution = DiscoveryScheduleExecution(
        schedule_id=schedule.schedule_id,
        schedule_name=schedule.name,
        target_kind=schedule.target_kind,
        trigger=DiscoveryScheduleTrigger.DUE,
        started_at=clock.now - timedelta(minutes=31),
        status=DiscoveryScheduleExecutionStatus.RUNNING,
    )
    store.save_execution(stale_execution)

    execution = service.run_schedule(schedule.schedule_id)

    assert execution.status == DiscoveryScheduleExecutionStatus.COMPLETED
    executions = service.list_executions(schedule_id=schedule.schedule_id)
    assert [item.status for item in executions] == [
        DiscoveryScheduleExecutionStatus.COMPLETED,
        DiscoveryScheduleExecutionStatus.FAILED,
    ]
    abandoned = executions[1]
    assert abandoned.error == "stale running execution abandoned after scheduler timeout"
    persisted = service.get_schedule(schedule.schedule_id)
    assert persisted.execution_count == 2
    assert any(
        event.get("type") == "discovery_schedule_execution_abandoned"
        for event in persisted.audit_events
    )
