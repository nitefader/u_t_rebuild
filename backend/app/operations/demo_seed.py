from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import gettempdir
from uuid import UUID

from backend.app.brokers import BrokerAccountSnapshot, BrokerSyncState
from backend.app.domain import ProgramVersion, TradingMode
from backend.app.governor import GovernorPolicy
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.runtime import DeploymentContext, RuntimeState, RuntimeStatus


DEMO_ACCOUNT_ID = UUID("10000000-0000-4000-8000-000000000001")
DEMO_DEPLOYMENT_ID = UUID("20000000-0000-4000-8000-000000000001")
DEMO_PROGRAM_VERSION_ID = UUID("30000000-0000-4000-8000-000000000001")
DEMO_PROGRAM_ID = UUID("30000000-0000-4000-8000-000000000002")
DEMO_GOVERNOR_ID = "demo-portfolio-governor"
DEMO_DB_FILENAME = "utos_operations_demo.sqlite3"


@dataclass(frozen=True)
class OperationsDemoSeedResult:
    db_path: Path
    account_id: UUID
    deployment_id: UUID
    program_id: UUID
    program_version: int


def default_operations_demo_db_path() -> Path:
    return Path(gettempdir()) / DEMO_DB_FILENAME


def demo_program_version() -> ProgramVersion:
    return ProgramVersion(
        id=DEMO_PROGRAM_VERSION_ID,
        program_id=DEMO_PROGRAM_ID,
        name="Operations Center Local Demo Program",
        version=1,
        strategy_version_id=UUID("30000000-0000-4000-8000-000000000003"),
        strategy_controls_version_id=UUID("30000000-0000-4000-8000-000000000004"),
        risk_profile_version_id=UUID("30000000-0000-4000-8000-000000000005"),
        execution_style_version_id=UUID("30000000-0000-4000-8000-000000000006"),
        universe_snapshot_id=UUID("30000000-0000-4000-8000-000000000007"),
        created_at=_demo_timestamp(),
    )


def demo_deployment_context() -> DeploymentContext:
    return DeploymentContext(
        deployment_id=DEMO_DEPLOYMENT_ID,
        program=demo_program_version(),
        status=RuntimeStatus.RECOVERED_READY,
        created_at=_demo_timestamp(),
    )


def seed_operations_demo_store(path: str | Path | None = None) -> OperationsDemoSeedResult:
    """Seed a local Operations Center demo store without broker or order side effects."""

    db_path = Path(path) if path is not None else default_operations_demo_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLiteRuntimeStore(db_path)
    timestamp = _demo_timestamp()

    store.save_broker_account_snapshot(
        BrokerAccountSnapshot(
            account_id=DEMO_ACCOUNT_ID,
            equity=100_000,
            cash=100_000,
            buying_power=100_000,
            daytrading_buying_power=100_000,
            provider="operations_demo",
            mode=TradingMode.BROKER_PAPER,
            account_status="demo",
            timestamp=timestamp,
        )
    )
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=DEMO_ACCOUNT_ID,
            last_sync_at=timestamp,
            last_poll_sync_at=timestamp,
            last_successful_sync_at=timestamp,
            is_stale=False,
        )
    )
    store.save_deployment_runtime_state(
        RuntimeState(
            deployment_id=DEMO_DEPLOYMENT_ID,
            status=RuntimeStatus.RECOVERED_READY,
            last_bar_timestamp_by_symbol_timeframe={"SPY:1m": timestamp},
            last_signal_timestamp=timestamp,
            last_execution_intent_timestamp=None,
        )
    )
    store.save_portfolio_governor_state(DEMO_GOVERNOR_ID, GovernorPolicy(max_open_positions=1))

    return OperationsDemoSeedResult(
        db_path=db_path,
        account_id=DEMO_ACCOUNT_ID,
        deployment_id=DEMO_DEPLOYMENT_ID,
        program_id=DEMO_PROGRAM_VERSION_ID,
        program_version=1,
    )


def _demo_timestamp() -> datetime:
    return datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
