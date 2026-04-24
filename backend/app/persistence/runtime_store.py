from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerSyncState,
)
from backend.app.control_plane.service import ControlPlaneState
from backend.app.domain._base import utc_now
from backend.app.governor import GovernorPolicy
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderLedger, OrderManagerError
from backend.app.runtime import RuntimeState
from backend.app.simulation import SimulatedTrade

from .models import RUNTIME_SCHEMA
from .session import SQLiteSessionFactory

ModelT = TypeVar("ModelT", bound=BaseModel)


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
                        (order_id, account_id, deployment_id, program_id, client_order_id, status, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_id) DO UPDATE SET
                        account_id = excluded.account_id,
                        deployment_id = excluded.deployment_id,
                        program_id = excluded.program_id,
                        client_order_id = excluded.client_order_id,
                        status = excluded.status,
                        payload = excluded.payload
                    """,
                    (
                        str(order.order_id),
                        str(order.account_id),
                        str(order.deployment_id),
                        str(order.program_id),
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

    def list_orders(self) -> tuple[InternalOrder, ...]:
        rows = self._fetch_all("SELECT payload FROM internal_orders ORDER BY rowid")
        return tuple(_load_model(InternalOrder, row["payload"]) for row in rows)

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
