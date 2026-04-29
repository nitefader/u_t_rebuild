from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerPositionSnapshot,
    BrokerSyncState,
)
from backend.app.broker_accounts.models import BrokerAccount
from backend.app.control_plane.service import ControlPlaneState
from backend.app.domain import (
    BacktestRun,
    ChartLabPreviewEvidence,
    OptimizationRun,
    PromotionEvidenceBundle,
    ResearchJob,
    RiskDecisionCard,
    RiskPlan,
    RiskPlanVersion,
    SimulationRunEvidence,
    WalkForwardRun,
)
from backend.app.domain._base import utc_now
from backend.app.governor import GovernorPolicy
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderLedger, OrderManagerError
from backend.app.runtime import RuntimeState
from backend.app.simulation import SimulatedTrade

from .models import RUNTIME_SCHEMA
from .session import SQLiteSessionFactory

ModelT = TypeVar("ModelT", bound=BaseModel)

ResearchEvidence = (
    ChartLabPreviewEvidence
    | BacktestRun
    | SimulationRunEvidence
    | OptimizationRun
    | WalkForwardRun
    | PromotionEvidenceBundle
)

_RESEARCH_EVIDENCE_TYPES: dict[str, type[BaseModel]] = {
    "chart_lab_preview": ChartLabPreviewEvidence,
    "backtest_run": BacktestRun,
    "simulation_run": SimulationRunEvidence,
    "optimization_run": OptimizationRun,
    "walk_forward_run": WalkForwardRun,
    "promotion_bundle": PromotionEvidenceBundle,
}

_RESEARCH_EVIDENCE_TYPE_BY_MODEL: dict[type[BaseModel], str] = {
    model: evidence_type for evidence_type, model in _RESEARCH_EVIDENCE_TYPES.items()
}


class SQLiteRuntimeStore:
    """Durable SQLite runtime repository.

    The store persists runtime facts only. It does not create orders, approve
    risk, interpret broker truth, or decide control-plane state.
    """

    def __init__(self, path: str | Path) -> None:
        self._session_factory = SQLiteSessionFactory(path)
        with self._connect() as connection:
            connection.executescript(RUNTIME_SCHEMA)
            self._migrate_legacy_tables(connection)

    def save_order(self, order: InternalOrder) -> InternalOrder:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO internal_orders
                        (
                            order_id, account_id, origin, deployment_id, program_id,
                            strategy_id, strategy_version_id, signal_plan_id,
                            opening_signal_plan_id, current_signal_plan_id,
                            position_lineage_id, account_evaluation_id,
                            governor_decision_id, leg_label, lifecycle_intent,
                            client_order_id, status, payload
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_id) DO UPDATE SET
                        account_id = excluded.account_id,
                        origin = excluded.origin,
                        deployment_id = excluded.deployment_id,
                        program_id = excluded.program_id,
                        strategy_id = excluded.strategy_id,
                        strategy_version_id = excluded.strategy_version_id,
                        signal_plan_id = excluded.signal_plan_id,
                        opening_signal_plan_id = excluded.opening_signal_plan_id,
                        current_signal_plan_id = excluded.current_signal_plan_id,
                        position_lineage_id = excluded.position_lineage_id,
                        account_evaluation_id = excluded.account_evaluation_id,
                        governor_decision_id = excluded.governor_decision_id,
                        leg_label = excluded.leg_label,
                        lifecycle_intent = excluded.lifecycle_intent,
                        client_order_id = excluded.client_order_id,
                        status = excluded.status,
                        payload = excluded.payload
                    """,
                    (
                        str(order.order_id),
                        str(order.account_id),
                        order.origin.value,
                        str(order.deployment_id) if order.deployment_id is not None else None,
                        str(order.program_id) if order.program_id is not None else None,
                        str(order.strategy_id) if order.strategy_id is not None else None,
                        str(order.strategy_version_id) if order.strategy_version_id is not None else None,
                        str(order.signal_plan_id) if order.signal_plan_id is not None else None,
                        str(order.opening_signal_plan_id) if order.opening_signal_plan_id is not None else None,
                        str(order.current_signal_plan_id) if order.current_signal_plan_id is not None else None,
                        str(order.position_lineage_id) if order.position_lineage_id is not None else None,
                        str(order.account_evaluation_id) if order.account_evaluation_id is not None else None,
                        str(order.governor_decision_id) if order.governor_decision_id is not None else None,
                        order.leg_label,
                        order.lifecycle_intent,
                        order.client_order_id,
                        order.status.value,
                        _dump_model(order),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise OrderManagerError(f"internal order already exists: {order.order_id}") from exc
        return order

    def load_order(self, order_id: UUID) -> InternalOrder:
        row = self._fetch_one("SELECT payload FROM internal_orders WHERE order_id = ?", (str(order_id),))
        if row is None:
            raise OrderManagerError(f"unknown internal order: {order_id}")
        return _load_model(InternalOrder, row["payload"])

    def list_orders_by_account(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        return self._load_orders("SELECT payload FROM internal_orders WHERE account_id = ? ORDER BY rowid", str(account_id))

    def list_orders_by_deployment(self, deployment_id: UUID) -> tuple[InternalOrder, ...]:
        return self._load_orders("SELECT payload FROM internal_orders WHERE deployment_id = ? ORDER BY rowid", str(deployment_id))

    def list_orders_by_program(self, program_id: UUID) -> tuple[InternalOrder, ...]:
        return self._load_orders("SELECT payload FROM internal_orders WHERE program_id = ? ORDER BY rowid", str(program_id))

    def list_orders_by_signal_plan(self, signal_plan_id: UUID) -> tuple[InternalOrder, ...]:
        return self._load_orders("SELECT payload FROM internal_orders WHERE signal_plan_id = ? ORDER BY rowid", str(signal_plan_id))

    def list_orders_by_position_lineage(self, position_lineage_id: UUID) -> tuple[InternalOrder, ...]:
        return self._load_orders(
            "SELECT payload FROM internal_orders WHERE position_lineage_id = ? ORDER BY rowid",
            str(position_lineage_id),
        )

    def list_orders(self) -> tuple[InternalOrder, ...]:
        rows = self._fetch_all("SELECT payload FROM internal_orders ORDER BY rowid")
        return tuple(_load_model(InternalOrder, row["payload"]) for row in rows)

    def reserve_manual_idempotency_key(
        self,
        *,
        account_id: UUID,
        idempotency_key: str,
        request_hash: str,
        operator_session_id: str,
    ) -> str | UUID:
        now = utc_now().isoformat()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO manual_order_idempotency
                        (account_id, idempotency_key, order_id, status, request_hash, operator_session_id, created_at, updated_at)
                    VALUES (?, ?, NULL, 'pending', ?, ?, ?, ?)
                    """,
                    (str(account_id), idempotency_key, request_hash, operator_session_id, now, now),
                )
                return "reserved"
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """
                    SELECT order_id, status, request_hash
                    FROM manual_order_idempotency
                    WHERE account_id = ? AND idempotency_key = ?
                    """,
                    (str(account_id), idempotency_key),
                ).fetchone()
        if row is None:
            return "in_flight"
        if row["request_hash"] != request_hash:
            return "conflict"
        if row["status"] == "committed" and row["order_id"]:
            return UUID(row["order_id"])
        return "in_flight"

    def commit_manual_idempotency_key(self, *, account_id: UUID, idempotency_key: str, order_id: UUID) -> None:
        now = utc_now().isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE manual_order_idempotency
                SET order_id = ?, status = 'committed', updated_at = ?
                WHERE account_id = ? AND idempotency_key = ? AND status = 'pending'
                """,
                (str(order_id), now, str(account_id), idempotency_key),
            )

    def release_manual_idempotency_key(self, *, account_id: UUID, idempotency_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                DELETE FROM manual_order_idempotency
                WHERE account_id = ? AND idempotency_key = ? AND status = 'pending'
                """,
                (str(account_id), idempotency_key),
            )

    def list_manual_idempotency_rows(self, account_id: UUID | None = None) -> tuple[dict[str, object], ...]:
        if account_id is None:
            rows = self._fetch_all("SELECT * FROM manual_order_idempotency ORDER BY created_at")
        else:
            rows = self._fetch_all(
                "SELECT * FROM manual_order_idempotency WHERE account_id = ? ORDER BY created_at",
                (str(account_id),),
            )
        return tuple(dict(row) for row in rows)

    def record_manual_trade_audit_event(
        self,
        *,
        event_code: str,
        account_id: UUID,
        operator_session_id: str,
        payload: dict[str, object],
        order_id: UUID | None = None,
        client_order_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        event = {
            "event_id": str(uuid4()),
            "event_code": event_code,
            "account_id": str(account_id),
            "order_id": str(order_id) if order_id is not None else None,
            "client_order_id": client_order_id,
            "idempotency_key": idempotency_key,
            "operator_session_id": operator_session_id,
            "occurred_at": utc_now().isoformat(),
            "payload": payload,
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO manual_trade_audit_events
                    (event_id, event_code, account_id, order_id, client_order_id, idempotency_key, operator_session_id, occurred_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event_code,
                    str(account_id),
                    event["order_id"],
                    client_order_id,
                    idempotency_key,
                    operator_session_id,
                    event["occurred_at"],
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )
        return event

    def list_manual_trade_audit_events(self, account_id: UUID | None = None) -> tuple[dict[str, object], ...]:
        if account_id is None:
            rows = self._fetch_all("SELECT * FROM manual_trade_audit_events ORDER BY occurred_at")
        else:
            rows = self._fetch_all(
                "SELECT * FROM manual_trade_audit_events WHERE account_id = ? ORDER BY occurred_at",
                (str(account_id),),
            )
        events = []
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(str(event["payload"]))
            events.append(event)
        return tuple(events)

    def list_deployment_runtime_states(self) -> tuple[RuntimeState, ...]:
        rows = self._fetch_all("SELECT payload FROM deployment_runtime_states ORDER BY rowid")
        return tuple(_load_model(RuntimeState, row["payload"]) for row in rows)

    def save_trade(self, trade: SimulatedTrade, *, deployment_id: UUID | None = None, account_id: UUID | None = None) -> SimulatedTrade:
        self._save_trade_payload(
            trade_id=trade.id,
            symbol=trade.symbol,
            payload_type="simulated_trade",
            payload=_dump_model(trade),
            deployment_id=deployment_id,
            account_id=account_id,
        )
        return trade

    def save_fill(self, fill: BrokerFillUpdateEvent, *, deployment_id: UUID | None = None) -> BrokerFillUpdateEvent:
        fill_id = fill.broker_execution_id or f"{fill.account_id}:{fill.client_order_id}:{fill.event_at.isoformat()}"
        self._save_trade_payload(
            trade_id=fill_id,
            symbol=fill.symbol,
            payload_type="broker_fill",
            payload=_dump_model(fill),
            deployment_id=deployment_id,
            account_id=fill.account_id,
        )
        return fill

    def load_trade(self, trade_id: str) -> SimulatedTrade | BrokerFillUpdateEvent:
        row = self._fetch_one("SELECT payload_type, payload FROM trades WHERE trade_id = ?", (trade_id,))
        if row is None:
            raise KeyError(f"unknown trade/fill: {trade_id}")
        return self._load_trade_row(row)

    def load_trades_by_deployment(self, deployment_id: UUID) -> tuple[SimulatedTrade | BrokerFillUpdateEvent, ...]:
        rows = self._fetch_all("SELECT payload_type, payload FROM trades WHERE deployment_id = ? ORDER BY rowid", (str(deployment_id),))
        return tuple(self._load_trade_row(row) for row in rows)

    def list_trades(self) -> tuple[SimulatedTrade | BrokerFillUpdateEvent, ...]:
        rows = self._fetch_all("SELECT payload_type, payload FROM trades ORDER BY rowid")
        return tuple(self._load_trade_row(row) for row in rows)

    def save_broker_order_mapping(self, mapping: BrokerOrderMapping) -> BrokerOrderMapping:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broker_order_mappings
                    (order_id, account_id, client_order_id, broker_order_id, provider, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    client_order_id = excluded.client_order_id,
                    broker_order_id = excluded.broker_order_id,
                    provider = excluded.provider,
                    payload = excluded.payload
                """,
                (
                    str(mapping.order_id),
                    str(mapping.account_id),
                    mapping.client_order_id,
                    mapping.broker_order_id,
                    mapping.provider,
                    _dump_model(mapping),
                ),
            )
        return mapping

    def lookup_broker_mapping_by_internal_order_id(self, order_id: UUID) -> BrokerOrderMapping:
        row = self._fetch_one("SELECT payload FROM broker_order_mappings WHERE order_id = ?", (str(order_id),))
        if row is None:
            raise KeyError(f"unknown broker order mapping: {order_id}")
        return _load_model(BrokerOrderMapping, row["payload"])

    def lookup_broker_mapping_by_broker_order_id(self, broker_order_id: str, *, provider: str | None = None) -> BrokerOrderMapping:
        if provider is None:
            row = self._fetch_one("SELECT payload FROM broker_order_mappings WHERE broker_order_id = ?", (broker_order_id,))
        else:
            row = self._fetch_one(
                "SELECT payload FROM broker_order_mappings WHERE provider = ? AND broker_order_id = ?",
                (provider, broker_order_id),
            )
        if row is None:
            raise KeyError(f"unknown broker order mapping: {broker_order_id}")
        return _load_model(BrokerOrderMapping, row["payload"])

    def list_broker_order_mappings(self) -> tuple[BrokerOrderMapping, ...]:
        rows = self._fetch_all("SELECT payload FROM broker_order_mappings ORDER BY rowid")
        return tuple(_load_model(BrokerOrderMapping, row["payload"]) for row in rows)

    def save_risk_plan(self, risk_plan: RiskPlan, *, account_id: UUID | None = None) -> RiskPlan:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_plans
                    (
                        risk_plan_id, name, status, risk_tier, risk_score,
                        source, account_id, created_at, updated_at, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(risk_plan_id) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    risk_tier = excluded.risk_tier,
                    risk_score = excluded.risk_score,
                    source = excluded.source,
                    account_id = excluded.account_id,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (
                    str(risk_plan.risk_plan_id),
                    risk_plan.name,
                    risk_plan.status.value,
                    risk_plan.risk_tier.value,
                    risk_plan.risk_score,
                    risk_plan.source.value,
                    str(account_id) if account_id is not None else None,
                    risk_plan.created_at.isoformat(),
                    risk_plan.updated_at.isoformat(),
                    _dump_model(risk_plan),
                ),
            )
        return risk_plan

    def load_risk_plan(self, risk_plan_id: UUID) -> RiskPlan:
        row = self._fetch_one("SELECT payload FROM risk_plans WHERE risk_plan_id = ?", (str(risk_plan_id),))
        if row is None:
            raise KeyError(f"unknown risk plan: {risk_plan_id}")
        return _load_model(RiskPlan, row["payload"])

    def list_risk_plans(
        self,
        *,
        status: str | None = None,
        risk_tier: str | None = None,
        source: str | None = None,
        account_id: UUID | None = None,
    ) -> tuple[RiskPlan, ...]:
        conditions: list[str] = []
        params: list[str] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if risk_tier is not None:
            conditions.append("risk_tier = ?")
            params.append(risk_tier)
        if source is not None:
            conditions.append("source = ?")
            params.append(source)
        if account_id is not None:
            conditions.append("account_id = ?")
            params.append(str(account_id))
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetch_all(
            f"SELECT payload FROM risk_plans{where} ORDER BY updated_at DESC, name, risk_plan_id",
            tuple(params),
        )
        return tuple(_load_model(RiskPlan, row["payload"]) for row in rows)

    def save_risk_plan_version(self, version: RiskPlanVersion) -> RiskPlanVersion:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_plan_versions
                    (
                        risk_plan_version_id, risk_plan_id, version, status,
                        config_fingerprint, created_at, activated_at,
                        archived_at, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(risk_plan_version_id) DO UPDATE SET
                    risk_plan_id = excluded.risk_plan_id,
                    version = excluded.version,
                    status = excluded.status,
                    config_fingerprint = excluded.config_fingerprint,
                    created_at = excluded.created_at,
                    activated_at = excluded.activated_at,
                    archived_at = excluded.archived_at,
                    payload = excluded.payload
                """,
                (
                    str(version.risk_plan_version_id),
                    str(version.risk_plan_id),
                    version.version,
                    version.status.value,
                    version.config_fingerprint,
                    version.created_at.isoformat(),
                    version.activated_at.isoformat() if version.activated_at is not None else None,
                    version.archived_at.isoformat() if version.archived_at is not None else None,
                    _dump_model(version),
                ),
            )
        return version

    def load_risk_plan_version(self, risk_plan_version_id: UUID) -> RiskPlanVersion:
        row = self._fetch_one(
            "SELECT payload FROM risk_plan_versions WHERE risk_plan_version_id = ?",
            (str(risk_plan_version_id),),
        )
        if row is None:
            raise KeyError(f"unknown risk plan version: {risk_plan_version_id}")
        return _load_model(RiskPlanVersion, row["payload"])

    def list_risk_plan_versions(
        self,
        risk_plan_id: UUID,
        *,
        status: str | None = None,
    ) -> tuple[RiskPlanVersion, ...]:
        conditions = ["risk_plan_id = ?"]
        params = [str(risk_plan_id)]
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        rows = self._fetch_all(
            f"SELECT payload FROM risk_plan_versions WHERE {' AND '.join(conditions)} ORDER BY version, created_at",
            tuple(params),
        )
        return tuple(_load_model(RiskPlanVersion, row["payload"]) for row in rows)

    def list_broker_accounts_by_default_risk_plan(self, risk_plan_id: UUID) -> tuple[BrokerAccount, ...]:
        rows = self._fetch_all(
            """
            SELECT payload FROM broker_accounts
            WHERE default_risk_plan_id = ?
            ORDER BY created_at, account_id
            """,
            (str(risk_plan_id),),
        )
        accounts = tuple(_load_model(BrokerAccount, row["payload"]) for row in rows)
        return tuple(account for account in accounts if not account.is_archived)

    def list_backtest_runs_for_risk_plan_versions(
        self,
        risk_plan_version_ids: tuple[UUID, ...],
        *,
        limit: int = 20,
    ) -> tuple[BacktestRun, ...]:
        if not risk_plan_version_ids:
            return ()
        version_ids = {str(version_id) for version_id in risk_plan_version_ids}
        runs = [
            evidence
            for evidence in self.list_research_evidence(evidence_type="backtest_run")
            if isinstance(evidence, BacktestRun)
            and str(evidence.metrics.get("risk_plan_version_id") or "") in version_ids
        ]
        runs.sort(key=lambda run: (run.created_at, run.run_id), reverse=True)
        return tuple(runs[:limit])

    def save_broker_account(self, account: BrokerAccount) -> BrokerAccount:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broker_accounts
                    (
                        account_id, provider, mode, external_account_id,
                        default_risk_plan_id, default_risk_plan_version_id,
                        validation_status, created_at, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    provider = excluded.provider,
                    mode = excluded.mode,
                    external_account_id = excluded.external_account_id,
                    default_risk_plan_id = excluded.default_risk_plan_id,
                    default_risk_plan_version_id = excluded.default_risk_plan_version_id,
                    validation_status = excluded.validation_status,
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (
                    str(account.id),
                    account.provider,
                    account.mode.value,
                    account.external_account_id,
                    str(account.default_risk_plan_id) if account.default_risk_plan_id is not None else None,
                    str(account.default_risk_plan_version_id)
                    if account.default_risk_plan_version_id is not None
                    else None,
                    account.validation_status.value,
                    account.created_at.isoformat(),
                    _dump_model(account),
                ),
            )
        return account

    def load_broker_account(self, account_id: UUID) -> BrokerAccount:
        row = self._fetch_one("SELECT payload FROM broker_accounts WHERE account_id = ?", (str(account_id),))
        if row is None:
            raise KeyError(f"unknown broker account: {account_id}")
        return _load_model(BrokerAccount, row["payload"])

    def load_broker_account_by_external_identity(self, *, provider: str, mode: str, external_account_id: str) -> BrokerAccount:
        row = self._fetch_one(
            """
            SELECT payload FROM broker_accounts
            WHERE provider = ? AND mode = ? AND external_account_id = ?
            """,
            (provider, mode, external_account_id),
        )
        if row is None:
            raise KeyError(f"unknown broker account external identity: {provider}:{mode}:{external_account_id}")
        return _load_model(BrokerAccount, row["payload"])

    def delete_broker_account(self, account_id: UUID) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM broker_accounts WHERE account_id = ?", (str(account_id),))
            connection.execute("DELETE FROM broker_account_snapshots WHERE account_id = ?", (str(account_id),))
            connection.execute("DELETE FROM broker_sync_freshness WHERE account_id = ?", (str(account_id),))
            connection.execute("DELETE FROM broker_position_snapshots WHERE account_id = ?", (str(account_id),))
            connection.execute("DELETE FROM broker_open_order_snapshots WHERE account_id = ?", (str(account_id),))

    def list_broker_accounts(self, *, include_archived: bool = False) -> tuple[BrokerAccount, ...]:
        rows = self._fetch_all("SELECT payload FROM broker_accounts ORDER BY created_at, account_id")
        accounts = tuple(_load_model(BrokerAccount, row["payload"]) for row in rows)
        if include_archived:
            return accounts
        return tuple(account for account in accounts if not account.is_archived)

    def save_broker_account_snapshot(self, snapshot: BrokerAccountSnapshot) -> BrokerAccountSnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broker_account_snapshots (account_id, provider, timestamp, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    provider = excluded.provider,
                    timestamp = excluded.timestamp,
                    payload = excluded.payload
                """,
                (str(snapshot.account_id), snapshot.provider, snapshot.timestamp.isoformat(), _dump_model(snapshot)),
            )
        return snapshot

    def load_broker_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        row = self._fetch_one("SELECT payload FROM broker_account_snapshots WHERE account_id = ?", (str(account_id),))
        if row is None:
            raise KeyError(f"unknown broker account snapshot: {account_id}")
        return _load_model(BrokerAccountSnapshot, row["payload"])

    def list_broker_account_snapshots(self) -> tuple[BrokerAccountSnapshot, ...]:
        rows = self._fetch_all("SELECT payload FROM broker_account_snapshots ORDER BY rowid")
        return tuple(_load_model(BrokerAccountSnapshot, row["payload"]) for row in rows)

    def save_broker_position_snapshot(self, snapshot: BrokerPositionSnapshot) -> BrokerPositionSnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broker_position_snapshots (account_id, symbol, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(account_id, symbol) DO UPDATE SET
                    payload = excluded.payload
                """,
                (str(snapshot.account_id), snapshot.symbol.upper(), _dump_model(snapshot)),
            )
        return snapshot

    def replace_broker_position_snapshots(
        self,
        account_id: UUID,
        snapshots: tuple[BrokerPositionSnapshot, ...],
    ) -> tuple[BrokerPositionSnapshot, ...]:
        with self._connect() as connection:
            connection.execute("DELETE FROM broker_position_snapshots WHERE account_id = ?", (str(account_id),))
            for snapshot in snapshots:
                connection.execute(
                    """
                    INSERT INTO broker_position_snapshots (account_id, symbol, payload)
                    VALUES (?, ?, ?)
                    """,
                    (str(snapshot.account_id), snapshot.symbol.upper(), _dump_model(snapshot)),
                )
        return snapshots

    def list_broker_position_snapshots(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        rows = self._fetch_all(
            "SELECT payload FROM broker_position_snapshots WHERE account_id = ? ORDER BY symbol",
            (str(account_id),),
        )
        return tuple(_load_model(BrokerPositionSnapshot, row["payload"]) for row in rows)

    def list_all_broker_position_snapshots(self) -> tuple[BrokerPositionSnapshot, ...]:
        rows = self._fetch_all("SELECT payload FROM broker_position_snapshots ORDER BY account_id, symbol")
        return tuple(_load_model(BrokerPositionSnapshot, row["payload"]) for row in rows)

    def list_broker_position_snapshots_by_deployment(self, deployment_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return tuple(
            snapshot
            for snapshot in self.list_all_broker_position_snapshots()
            if snapshot.deployment_id == deployment_id
        )

    def save_broker_open_order_snapshot(self, snapshot: BrokerOpenOrderSnapshot) -> BrokerOpenOrderSnapshot:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broker_open_order_snapshots
                    (broker_order_id, account_id, client_order_id, symbol, status, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(broker_order_id) DO UPDATE SET
                    account_id = excluded.account_id,
                    client_order_id = excluded.client_order_id,
                    symbol = excluded.symbol,
                    status = excluded.status,
                    payload = excluded.payload
                """,
                (
                    snapshot.broker_order_id,
                    str(snapshot.account_id),
                    snapshot.client_order_id,
                    snapshot.symbol.upper(),
                    snapshot.status.value,
                    _dump_model(snapshot),
                ),
            )
        return snapshot

    def replace_broker_open_order_snapshots(
        self,
        account_id: UUID,
        snapshots: tuple[BrokerOpenOrderSnapshot, ...],
    ) -> tuple[BrokerOpenOrderSnapshot, ...]:
        with self._connect() as connection:
            connection.execute("DELETE FROM broker_open_order_snapshots WHERE account_id = ?", (str(account_id),))
            for snapshot in snapshots:
                connection.execute(
                    """
                    INSERT INTO broker_open_order_snapshots
                        (broker_order_id, account_id, client_order_id, symbol, status, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.broker_order_id,
                        str(snapshot.account_id),
                        snapshot.client_order_id,
                        snapshot.symbol.upper(),
                        snapshot.status.value,
                        _dump_model(snapshot),
                    ),
                )
        return snapshots

    def list_broker_open_order_snapshots(self, account_id: UUID | None = None) -> tuple[BrokerOpenOrderSnapshot, ...]:
        if account_id is None:
            rows = self._fetch_all("SELECT payload FROM broker_open_order_snapshots ORDER BY rowid")
        else:
            rows = self._fetch_all(
                "SELECT payload FROM broker_open_order_snapshots WHERE account_id = ? ORDER BY rowid",
                (str(account_id),),
            )
        return tuple(_load_model(BrokerOpenOrderSnapshot, row["payload"]) for row in rows)

    def save_broker_sync_freshness(self, state: BrokerSyncState) -> BrokerSyncState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO broker_sync_freshness (account_id, last_sync_at, is_stale, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    last_sync_at = excluded.last_sync_at,
                    is_stale = excluded.is_stale,
                    payload = excluded.payload
                """,
                (str(state.account_id), state.last_sync_at.isoformat(), int(state.is_stale), _dump_model(state)),
            )
        return state

    def load_broker_sync_freshness(self, account_id: UUID) -> BrokerSyncState:
        row = self._fetch_one("SELECT payload FROM broker_sync_freshness WHERE account_id = ?", (str(account_id),))
        if row is None:
            raise KeyError(f"unknown broker sync freshness: {account_id}")
        return _load_model(BrokerSyncState, row["payload"])

    def list_broker_sync_freshness(self) -> tuple[BrokerSyncState, ...]:
        rows = self._fetch_all("SELECT payload FROM broker_sync_freshness ORDER BY rowid")
        return tuple(_load_model(BrokerSyncState, row["payload"]) for row in rows)

    def save_deployment_runtime_state(self, state: RuntimeState) -> RuntimeState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO deployment_runtime_states (deployment_id, status, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(deployment_id) DO UPDATE SET
                    status = excluded.status,
                    payload = excluded.payload
                """,
                (str(state.deployment_id), state.status.value, _dump_model(state)),
            )
        return state

    def load_deployment_runtime_state(self, deployment_id: UUID) -> RuntimeState:
        row = self._fetch_one("SELECT payload FROM deployment_runtime_states WHERE deployment_id = ?", (str(deployment_id),))
        if row is None:
            raise KeyError(f"unknown deployment state: {deployment_id}")
        return _load_model(RuntimeState, row["payload"])

    def save_portfolio_governor_state(self, governor_id: str, policy: GovernorPolicy) -> GovernorPolicy:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO portfolio_governor_states (governor_id, payload)
                VALUES (?, ?)
                ON CONFLICT(governor_id) DO UPDATE SET payload = excluded.payload
                """,
                (governor_id, _dump_model(policy)),
            )
        return policy

    def load_portfolio_governor_state(self, governor_id: str) -> GovernorPolicy:
        row = self._fetch_one("SELECT payload FROM portfolio_governor_states WHERE governor_id = ?", (governor_id,))
        if row is None:
            raise KeyError(f"unknown governor state: {governor_id}")
        return _load_model(GovernorPolicy, row["payload"])

    def save_control_plane_state(self, control_plane_id: str, state: ControlPlaneState) -> ControlPlaneState:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO control_plane_states (control_plane_id, payload)
                VALUES (?, ?)
                ON CONFLICT(control_plane_id) DO UPDATE SET payload = excluded.payload
                """,
                (control_plane_id, _dump_model(state)),
            )
        return state

    def load_control_plane_state(self, control_plane_id: str) -> ControlPlaneState:
        row = self._fetch_one("SELECT payload FROM control_plane_states WHERE control_plane_id = ?", (control_plane_id,))
        if row is None:
            raise KeyError(f"unknown control plane state: {control_plane_id}")
        return _load_model(ControlPlaneState, row["payload"])

    def save_research_evidence(self, evidence: ResearchEvidence) -> ResearchEvidence:
        evidence_type = _research_evidence_type(evidence)
        evidence_id = _research_evidence_id(evidence)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_evidence
                    (evidence_id, evidence_type, strategy_id, strategy_version_id, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    evidence_type = excluded.evidence_type,
                    strategy_id = excluded.strategy_id,
                    strategy_version_id = excluded.strategy_version_id,
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (
                    str(evidence_id),
                    evidence_type,
                    str(evidence.strategy_id),
                    str(evidence.strategy_version_id),
                    evidence.created_at.isoformat(),
                    _dump_model(evidence),
                ),
            )
        return evidence

    def load_research_evidence(self, evidence_id: UUID) -> ResearchEvidence:
        row = self._fetch_one(
            "SELECT evidence_type, payload FROM research_evidence WHERE evidence_id = ?",
            (str(evidence_id),),
        )
        if row is None:
            raise KeyError(f"unknown research evidence: {evidence_id}")
        return _load_research_evidence_row(row)

    def save_risk_decision_card(self, card: RiskDecisionCard) -> RiskDecisionCard:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_decision_cards
                    (
                        risk_decision_id, mode, run_id, session_id, account_id,
                        simulated_account_id, strategy_id, strategy_version_id,
                        deployment_id, signal_plan_id, risk_plan_id,
                        risk_plan_version_id, symbol, decision, timestamp,
                        created_at, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(risk_decision_id) DO UPDATE SET
                    mode = excluded.mode,
                    run_id = excluded.run_id,
                    session_id = excluded.session_id,
                    account_id = excluded.account_id,
                    simulated_account_id = excluded.simulated_account_id,
                    strategy_id = excluded.strategy_id,
                    strategy_version_id = excluded.strategy_version_id,
                    deployment_id = excluded.deployment_id,
                    signal_plan_id = excluded.signal_plan_id,
                    risk_plan_id = excluded.risk_plan_id,
                    risk_plan_version_id = excluded.risk_plan_version_id,
                    symbol = excluded.symbol,
                    decision = excluded.decision,
                    timestamp = excluded.timestamp,
                    created_at = excluded.created_at,
                    payload = excluded.payload
                """,
                (
                    str(card.risk_decision_id),
                    card.mode.value,
                    str(card.run_id),
                    str(card.session_id) if card.session_id is not None else None,
                    str(card.account_id) if card.account_id is not None else None,
                    str(card.simulated_account_id) if card.simulated_account_id is not None else None,
                    str(card.strategy_id),
                    str(card.strategy_version_id),
                    str(card.deployment_id) if card.deployment_id is not None else None,
                    str(card.signal_plan_id),
                    str(card.risk_plan_id),
                    str(card.risk_plan_version_id),
                    card.symbol.upper(),
                    card.decision.value,
                    card.timestamp.isoformat(),
                    card.created_at.isoformat(),
                    _dump_model(card),
                ),
            )
        return card

    def load_risk_decision_card(self, risk_decision_id: UUID) -> RiskDecisionCard:
        row = self._fetch_one(
            "SELECT payload FROM risk_decision_cards WHERE risk_decision_id = ?",
            (str(risk_decision_id),),
        )
        if row is None:
            raise KeyError(f"unknown risk decision card: {risk_decision_id}")
        return _load_model(RiskDecisionCard, row["payload"])

    def list_risk_decision_cards(
        self,
        *,
        run_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        account_id: UUID | None = None,
        strategy_version_id: UUID | None = None,
    ) -> tuple[RiskDecisionCard, ...]:
        conditions: list[str] = []
        params: list[object] = []
        if run_id is not None:
            conditions.append("run_id = ?")
            params.append(str(run_id))
        if signal_plan_id is not None:
            conditions.append("signal_plan_id = ?")
            params.append(str(signal_plan_id))
        if account_id is not None:
            conditions.append("account_id = ?")
            params.append(str(account_id))
        if strategy_version_id is not None:
            conditions.append("strategy_version_id = ?")
            params.append(str(strategy_version_id))
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetch_all(
            f"SELECT payload FROM risk_decision_cards{where} ORDER BY created_at, risk_decision_id",
            tuple(params),
        )
        return tuple(_load_model(RiskDecisionCard, row["payload"]) for row in rows)

    def list_risk_decision_cards_for_risk_plan_versions(
        self,
        risk_plan_version_ids: tuple[UUID, ...],
    ) -> tuple[RiskDecisionCard, ...]:
        if not risk_plan_version_ids:
            return ()
        placeholders = ", ".join("?" for _ in risk_plan_version_ids)
        rows = self._fetch_all(
            f"""
            SELECT payload FROM risk_decision_cards
            WHERE risk_plan_version_id IN ({placeholders})
            ORDER BY created_at DESC, risk_decision_id
            """,
            tuple(str(version_id) for version_id in risk_plan_version_ids),
        )
        return tuple(_load_model(RiskDecisionCard, row["payload"]) for row in rows)

    def save_historical_dataset(self, payload: dict[str, Any], *, dataset_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO historical_datasets
                    (
                        dataset_id, provider, symbol, timeframe, coverage_start,
                        coverage_end, adjustment_policy, timezone, ingested_at,
                        bar_count, aggregate_quality_status, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    provider = excluded.provider,
                    symbol = excluded.symbol,
                    timeframe = excluded.timeframe,
                    coverage_start = excluded.coverage_start,
                    coverage_end = excluded.coverage_end,
                    adjustment_policy = excluded.adjustment_policy,
                    timezone = excluded.timezone,
                    ingested_at = excluded.ingested_at,
                    bar_count = excluded.bar_count,
                    aggregate_quality_status = excluded.aggregate_quality_status,
                    payload = excluded.payload
                """,
                (
                    dataset_id,
                    str(payload["provider"]),
                    str(payload["symbol"]).upper(),
                    str(payload["timeframe"]),
                    str(payload["coverage_start"]),
                    str(payload["coverage_end"]),
                    str(payload["adjustment_policy"]),
                    str(payload["timezone"]),
                    str(payload["ingested_at"]),
                    int(payload["bar_count"]),
                    str(payload.get("aggregate_quality_status", "ok")),
                    json.dumps(payload, sort_keys=True, default=str),
                ),
            )

    def load_historical_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        row = self._fetch_one(
            "SELECT payload FROM historical_datasets WHERE dataset_id = ?",
            (dataset_id,),
        )
        if row is None:
            return None
        return json.loads(str(row["payload"]))

    def find_historical_dataset(
        self,
        *,
        provider: str,
        symbol: str,
        timeframe: str,
        adjustment_policy: str,
    ) -> dict[str, Any] | None:
        row = self._fetch_one(
            """
            SELECT payload FROM historical_datasets
            WHERE provider = ? AND symbol = ? AND timeframe = ? AND adjustment_policy = ?
            """,
            (provider, symbol.upper(), timeframe, adjustment_policy),
        )
        if row is None:
            return None
        return json.loads(str(row["payload"]))

    def list_historical_datasets(self) -> tuple[dict[str, Any], ...]:
        rows = self._fetch_all(
            "SELECT payload FROM historical_datasets ORDER BY ingested_at, dataset_id"
        )
        return tuple(json.loads(str(row["payload"])) for row in rows)

    def save_research_job(self, job: ResearchJob) -> ResearchJob:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_jobs
                    (
                        job_id, kind, status,
                        progress_current, progress_total, progress_label,
                        cancel_requested, result_run_id, error,
                        created_at, started_at, finished_at,
                        operator_session_id, payload
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    kind = excluded.kind,
                    status = excluded.status,
                    progress_current = excluded.progress_current,
                    progress_total = excluded.progress_total,
                    progress_label = excluded.progress_label,
                    cancel_requested = excluded.cancel_requested,
                    result_run_id = excluded.result_run_id,
                    error = excluded.error,
                    created_at = excluded.created_at,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    operator_session_id = excluded.operator_session_id,
                    payload = excluded.payload
                """,
                (
                    str(job.job_id),
                    job.kind.value,
                    job.status.value,
                    int(job.progress.current),
                    int(job.progress.total),
                    job.progress.label,
                    int(job.cancel_requested),
                    str(job.result_run_id) if job.result_run_id else None,
                    job.error,
                    job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.finished_at.isoformat() if job.finished_at else None,
                    job.operator_session_id,
                    _dump_model(job),
                ),
            )
        return job

    def load_research_job(self, job_id: UUID) -> ResearchJob:
        row = self._fetch_one(
            "SELECT payload FROM research_jobs WHERE job_id = ?",
            (str(job_id),),
        )
        if row is None:
            raise KeyError(f"unknown research job: {job_id}")
        return _load_model(ResearchJob, row["payload"])

    def list_research_jobs(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 100,
    ) -> tuple[ResearchJob, ...]:
        conditions: list[str] = []
        params: list[object] = []
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if kind is not None:
            conditions.append("kind = ?")
            params.append(kind)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetch_all(
            f"SELECT payload FROM research_jobs{where} ORDER BY created_at DESC, job_id LIMIT ?",
            (*params, int(max(1, min(limit, 500)))),
        )
        return tuple(_load_model(ResearchJob, row["payload"]) for row in rows)

    def request_research_job_cancel(self, job_id: UUID) -> ResearchJob:
        job = self.load_research_job(job_id)
        if job.status.value in {"completed", "failed", "canceled"}:
            return job
        updated = job.model_copy(update={"cancel_requested": True})
        return self.save_research_job(updated)

    def list_research_evidence(
        self,
        *,
        strategy_id: UUID | None = None,
        strategy_version_id: UUID | None = None,
        evidence_type: str | None = None,
    ) -> tuple[ResearchEvidence, ...]:
        conditions: list[str] = []
        params: list[object] = []
        if strategy_id is not None:
            conditions.append("strategy_id = ?")
            params.append(str(strategy_id))
        if strategy_version_id is not None:
            conditions.append("strategy_version_id = ?")
            params.append(str(strategy_version_id))
        if evidence_type is not None:
            conditions.append("evidence_type = ?")
            params.append(evidence_type)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetch_all(
            f"SELECT evidence_type, payload FROM research_evidence{where} ORDER BY created_at, evidence_id",
            tuple(params),
        )
        return tuple(_load_research_evidence_row(row) for row in rows)

    def _save_trade_payload(
        self,
        *,
        trade_id: str,
        symbol: str,
        payload_type: str,
        payload: str,
        deployment_id: UUID | None,
        account_id: UUID | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trades (trade_id, deployment_id, account_id, symbol, payload_type, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    deployment_id = excluded.deployment_id,
                    account_id = excluded.account_id,
                    symbol = excluded.symbol,
                    payload_type = excluded.payload_type,
                    payload = excluded.payload
                """,
                (
                    trade_id,
                    str(deployment_id) if deployment_id is not None else None,
                    str(account_id) if account_id is not None else None,
                    symbol.upper(),
                    payload_type,
                    payload,
                ),
            )

    def _load_orders(self, query: str, value: str) -> tuple[InternalOrder, ...]:
        rows = self._fetch_all(query, (value,))
        return tuple(_load_model(InternalOrder, row["payload"]) for row in rows)

    def _load_trade_row(self, row: sqlite3.Row) -> SimulatedTrade | BrokerFillUpdateEvent:
        if row["payload_type"] == "broker_fill":
            return _load_model(BrokerFillUpdateEvent, row["payload"])
        return _load_model(SimulatedTrade, row["payload"])

    def _fetch_one(self, query: str, parameters: tuple[object, ...]) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(query, parameters).fetchone()

    def _fetch_all(self, query: str, parameters: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return list(connection.execute(query, parameters).fetchall())

    def _connect(self) -> sqlite3.Connection:
        return self._session_factory.connect()

    def _migrate_legacy_tables(self, connection: sqlite3.Connection) -> None:
        legacy_orders = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'orders'"
        ).fetchone()
        if legacy_orders is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO internal_orders
                    (order_id, account_id, deployment_id, program_id, client_order_id, status, payload)
                SELECT order_id, account_id, deployment_id, program_id, client_order_id, 'created', payload
                FROM orders
                """
            )
        legacy_deployments = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'deployment_states'"
        ).fetchone()
        if legacy_deployments is not None:
            connection.execute(
                """
                INSERT OR IGNORE INTO deployment_runtime_states (deployment_id, status, payload)
                SELECT deployment_id, 'ready', payload FROM deployment_states
                """
            )
        broker_account_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(broker_accounts)").fetchall()
        }
        if "external_account_id" not in broker_account_columns:
            connection.execute("ALTER TABLE broker_accounts ADD COLUMN external_account_id TEXT")
        if "default_risk_plan_id" not in broker_account_columns:
            connection.execute("ALTER TABLE broker_accounts ADD COLUMN default_risk_plan_id TEXT")
        if "default_risk_plan_version_id" not in broker_account_columns:
            connection.execute("ALTER TABLE broker_accounts ADD COLUMN default_risk_plan_version_id TEXT")
        internal_order_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(internal_orders)").fetchall()
        }
        if "origin" not in internal_order_columns:
            connection.execute("ALTER TABLE internal_orders ADD COLUMN origin TEXT NOT NULL DEFAULT 'program'")
        lineage_columns = {
            "strategy_id",
            "strategy_version_id",
            "signal_plan_id",
            "opening_signal_plan_id",
            "current_signal_plan_id",
            "position_lineage_id",
            "account_evaluation_id",
            "governor_decision_id",
            "leg_label",
            "lifecycle_intent",
        }
        for column in sorted(lineage_columns - internal_order_columns):
            connection.execute(f"ALTER TABLE internal_orders ADD COLUMN {column} TEXT")
        internal_order_info = connection.execute("PRAGMA table_info(internal_orders)").fetchall()
        nullable_lineage = {
            row["name"]: row["notnull"]
            for row in internal_order_info
            if row["name"] in {"deployment_id", "program_id"}
        }
        if nullable_lineage.get("deployment_id") or nullable_lineage.get("program_id"):
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS internal_orders_v2 (
                    order_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    origin TEXT NOT NULL DEFAULT 'program',
                    deployment_id TEXT,
                    program_id TEXT,
                    strategy_id TEXT,
                    strategy_version_id TEXT,
                    signal_plan_id TEXT,
                    opening_signal_plan_id TEXT,
                    current_signal_plan_id TEXT,
                    position_lineage_id TEXT,
                    account_evaluation_id TEXT,
                    governor_decision_id TEXT,
                    leg_label TEXT,
                    lifecycle_intent TEXT,
                    client_order_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                INSERT OR IGNORE INTO internal_orders_v2
                    (
                        order_id, account_id, origin, deployment_id, program_id,
                        strategy_id, strategy_version_id, signal_plan_id,
                        opening_signal_plan_id, current_signal_plan_id,
                        position_lineage_id, account_evaluation_id,
                        governor_decision_id, leg_label, lifecycle_intent,
                        client_order_id, status, payload
                    )
                SELECT
                    order_id, account_id, origin, deployment_id, program_id,
                    strategy_id, strategy_version_id, signal_plan_id,
                    opening_signal_plan_id, current_signal_plan_id,
                    position_lineage_id, account_evaluation_id,
                    governor_decision_id, leg_label, lifecycle_intent,
                    client_order_id, status, payload
                FROM internal_orders;
                DROP TABLE internal_orders;
                ALTER TABLE internal_orders_v2 RENAME TO internal_orders;
                CREATE INDEX IF NOT EXISTS ix_internal_orders_account_id ON internal_orders(account_id);
                CREATE INDEX IF NOT EXISTS ix_internal_orders_origin ON internal_orders(origin);
                CREATE INDEX IF NOT EXISTS ix_internal_orders_deployment_id ON internal_orders(deployment_id);
                CREATE INDEX IF NOT EXISTS ix_internal_orders_program_id ON internal_orders(program_id);
                CREATE INDEX IF NOT EXISTS ix_internal_orders_signal_plan_id ON internal_orders(signal_plan_id);
                CREATE INDEX IF NOT EXISTS ix_internal_orders_opening_signal_plan_id ON internal_orders(opening_signal_plan_id);
                CREATE INDEX IF NOT EXISTS ix_internal_orders_position_lineage_id ON internal_orders(position_lineage_id);
                """
            )
        connection.execute("CREATE INDEX IF NOT EXISTS ix_internal_orders_signal_plan_id ON internal_orders(signal_plan_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_internal_orders_opening_signal_plan_id ON internal_orders(opening_signal_plan_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_internal_orders_position_lineage_id ON internal_orders(position_lineage_id)"
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ux_broker_accounts_external_identity
            ON broker_accounts(provider, mode, external_account_id)
            WHERE external_account_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_broker_accounts_default_risk_plan
            ON broker_accounts(default_risk_plan_id, default_risk_plan_version_id)
            """
        )


class SQLiteOrderLedger(OrderLedger):
    """SQLite-backed OrderLedger with the same public behavior."""

    def __init__(self, path: str | Path) -> None:
        self._runtime_store = SQLiteRuntimeStore(path)

    def add(self, order: InternalOrder) -> InternalOrder:
        try:
            self._runtime_store.load_order(order.order_id)
        except OrderManagerError:
            return self._runtime_store.save_order(order)
        raise OrderManagerError(f"internal order already exists: {order.order_id}")

    def get(self, order_id: UUID) -> InternalOrder:
        return self._runtime_store.load_order(order_id)

    def update_status(
        self,
        *,
        order_id: UUID,
        status: InternalOrderStatus,
        reason: str | None = None,
    ) -> InternalOrder:
        order = self.get(order_id)
        updated = order.model_copy(
            update={
                "status": status,
                "updated_at": utc_now(),
                "reason": reason if reason is not None else order.reason,
            }
        )
        return self.replace(updated)

    def replace(self, order: InternalOrder) -> InternalOrder:
        self.get(order.order_id)
        return self._runtime_store.save_order(order)

    def by_account(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        return self._runtime_store.list_orders_by_account(account_id)

    def by_deployment(self, deployment_id: UUID) -> tuple[InternalOrder, ...]:
        return self._runtime_store.list_orders_by_deployment(deployment_id)

    def by_program(self, program_id: UUID) -> tuple[InternalOrder, ...]:
        return self._runtime_store.list_orders_by_program(program_id)

    def by_client_order_id(self, client_order_id: str) -> InternalOrder | None:
        for order in self._runtime_store.list_orders():
            if order.client_order_id == client_order_id:
                return order
        return None

    def by_signal_plan(self, signal_plan_id: UUID) -> tuple[InternalOrder, ...]:
        return self._runtime_store.list_orders_by_signal_plan(signal_plan_id)

    def by_position_lineage(self, position_lineage_id: UUID) -> tuple[InternalOrder, ...]:
        return self._runtime_store.list_orders_by_position_lineage(position_lineage_id)

    def all(self) -> tuple[InternalOrder, ...]:
        return self._runtime_store.list_orders()


class SQLiteTradeLedger:
    def __init__(self, path: str | Path) -> None:
        self._runtime_store = SQLiteRuntimeStore(path)

    def add(self, trade: SimulatedTrade | BrokerFillUpdateEvent) -> SimulatedTrade | BrokerFillUpdateEvent:
        if isinstance(trade, BrokerFillUpdateEvent):
            return self._runtime_store.save_fill(trade)
        return self._runtime_store.save_trade(trade)

    def record_fill(self, event: BrokerFillUpdateEvent) -> BrokerFillUpdateEvent:
        return self._runtime_store.save_fill(event)

    def get(self, trade_id: str) -> SimulatedTrade | BrokerFillUpdateEvent:
        return self._runtime_store.load_trade(trade_id)

    def by_deployment(self, deployment_id: UUID) -> tuple[SimulatedTrade | BrokerFillUpdateEvent, ...]:
        return self._runtime_store.load_trades_by_deployment(deployment_id)

    def all(self) -> tuple[SimulatedTrade | BrokerFillUpdateEvent, ...]:
        return self._runtime_store.list_trades()


class SQLiteBrokerOrderMappingStore:
    def __init__(self, path: str | Path) -> None:
        self._runtime_store = SQLiteRuntimeStore(path)

    def save(self, mapping: BrokerOrderMapping) -> BrokerOrderMapping:
        return self._runtime_store.save_broker_order_mapping(mapping)

    def get_by_order_id(self, order_id: UUID) -> BrokerOrderMapping:
        return self._runtime_store.lookup_broker_mapping_by_internal_order_id(order_id)

    def get_by_broker_order_id(self, broker_order_id: str, *, provider: str | None = None) -> BrokerOrderMapping:
        return self._runtime_store.lookup_broker_mapping_by_broker_order_id(broker_order_id, provider=provider)


class SQLiteGovernorStateStore:
    def __init__(self, path: str | Path) -> None:
        self._runtime_store = SQLiteRuntimeStore(path)

    def save_policy(self, governor_id: str, policy: GovernorPolicy) -> GovernorPolicy:
        return self._runtime_store.save_portfolio_governor_state(governor_id, policy)

    def load_policy(self, governor_id: str) -> GovernorPolicy:
        return self._runtime_store.load_portfolio_governor_state(governor_id)


class SQLiteDeploymentStateStore:
    def __init__(self, path: str | Path) -> None:
        self._runtime_store = SQLiteRuntimeStore(path)

    def save_runtime_state(self, state: RuntimeState) -> RuntimeState:
        return self._runtime_store.save_deployment_runtime_state(state)

    def load_runtime_state(self, deployment_id: UUID) -> RuntimeState:
        return self._runtime_store.load_deployment_runtime_state(deployment_id)


def _dump_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True)


def _load_model(model_type: type[ModelT], payload: str) -> ModelT:
    return model_type.model_validate(json.loads(payload))


def _research_evidence_id(evidence: ResearchEvidence) -> UUID:
    for field_name in ("evidence_id", "run_id", "bundle_id"):
        value = getattr(evidence, field_name, None)
        if isinstance(value, UUID):
            return value
    raise KeyError("research evidence has no canonical id")


def _research_evidence_type(evidence: ResearchEvidence) -> str:
    evidence_type = _RESEARCH_EVIDENCE_TYPE_BY_MODEL.get(type(evidence))
    if evidence_type is None:
        raise KeyError(f"unsupported research evidence type: {type(evidence).__name__}")
    return evidence_type


def _load_research_evidence_row(row: sqlite3.Row) -> ResearchEvidence:
    evidence_type = str(row["evidence_type"])
    model_type = _RESEARCH_EVIDENCE_TYPES.get(evidence_type)
    if model_type is None:
        raise KeyError(f"unsupported research evidence type: {evidence_type}")
    return _load_model(model_type, row["payload"])  # type: ignore[return-value]
