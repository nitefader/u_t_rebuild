from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from backend.app.brokers import BrokerOrderMapping
from backend.app.domain._base import utc_now
from backend.app.governor import GovernorPolicy
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderLedger, OrderManagerError
from backend.app.runtime import RuntimeState
from backend.app.simulation import SimulatedTrade


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                deployment_id TEXT NOT NULL,
                program_id TEXT NOT NULL,
                client_order_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_orders_account_id ON orders(account_id);
            CREATE INDEX IF NOT EXISTS ix_orders_deployment_id ON orders(deployment_id);
            CREATE INDEX IF NOT EXISTS ix_orders_program_id ON orders(program_id);

            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_trades_symbol ON trades(symbol);

            CREATE TABLE IF NOT EXISTS broker_order_mappings (
                order_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                client_order_id TEXT NOT NULL,
                broker_order_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_broker_order_mappings_account_id ON broker_order_mappings(account_id);
            CREATE INDEX IF NOT EXISTS ix_broker_order_mappings_broker_order_id ON broker_order_mappings(broker_order_id);

            CREATE TABLE IF NOT EXISTS governor_states (
                governor_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deployment_states (
                deployment_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            """
        )
        self._connection.commit()


class SQLiteOrderLedger(OrderLedger):
    """SQLite-backed OrderLedger with the same public behavior."""

    def __init__(self, path: str | Path) -> None:
        self._store = SQLiteStore(path)

    def add(self, order: InternalOrder) -> InternalOrder:
        try:
            self._store.connection.execute(
                """
                INSERT INTO orders (order_id, account_id, deployment_id, program_id, client_order_id, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(order.order_id),
                    str(order.account_id),
                    str(order.deployment_id),
                    str(order.program_id),
                    order.client_order_id,
                    _dump_model(order),
                ),
            )
            self._store.connection.commit()
        except sqlite3.IntegrityError as exc:
            raise OrderManagerError(f"internal order already exists: {order.order_id}") from exc
        return order

    def get(self, order_id: UUID) -> InternalOrder:
        row = self._store.connection.execute(
            "SELECT payload FROM orders WHERE order_id = ?",
            (str(order_id),),
        ).fetchone()
        if row is None:
            raise OrderManagerError(f"unknown internal order: {order_id}")
        return _load_model(InternalOrder, row["payload"])

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
        self._store.connection.execute(
            """
            UPDATE orders
            SET account_id = ?, deployment_id = ?, program_id = ?, client_order_id = ?, payload = ?
            WHERE order_id = ?
            """,
            (
                str(order.account_id),
                str(order.deployment_id),
                str(order.program_id),
                order.client_order_id,
                _dump_model(order),
                str(order.order_id),
            ),
        )
        self._store.connection.commit()
        return order

    def by_account(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        return self._select("SELECT payload FROM orders WHERE account_id = ? ORDER BY rowid", str(account_id))

    def by_deployment(self, deployment_id: UUID) -> tuple[InternalOrder, ...]:
        return self._select("SELECT payload FROM orders WHERE deployment_id = ? ORDER BY rowid", str(deployment_id))

    def by_program(self, program_id: UUID) -> tuple[InternalOrder, ...]:
        return self._select("SELECT payload FROM orders WHERE program_id = ? ORDER BY rowid", str(program_id))

    def all(self) -> tuple[InternalOrder, ...]:
        rows = self._store.connection.execute("SELECT payload FROM orders ORDER BY rowid").fetchall()
        return tuple(_load_model(InternalOrder, row["payload"]) for row in rows)

    def _select(self, query: str, value: str) -> tuple[InternalOrder, ...]:
        rows = self._store.connection.execute(query, (value,)).fetchall()
        return tuple(_load_model(InternalOrder, row["payload"]) for row in rows)


class SQLiteTradeLedger:
    def __init__(self, path: str | Path) -> None:
        self._store = SQLiteStore(path)

    def add(self, trade: SimulatedTrade) -> SimulatedTrade:
        self._store.connection.execute(
            """
            INSERT OR REPLACE INTO trades (trade_id, symbol, payload)
            VALUES (?, ?, ?)
            """,
            (trade.id, trade.symbol.upper(), _dump_model(trade)),
        )
        self._store.connection.commit()
        return trade

    def get(self, trade_id: str) -> SimulatedTrade:
        row = self._store.connection.execute(
            "SELECT payload FROM trades WHERE trade_id = ?",
            (trade_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown trade: {trade_id}")
        return _load_model(SimulatedTrade, row["payload"])

    def all(self) -> tuple[SimulatedTrade, ...]:
        rows = self._store.connection.execute("SELECT payload FROM trades ORDER BY rowid").fetchall()
        return tuple(_load_model(SimulatedTrade, row["payload"]) for row in rows)


class SQLiteBrokerOrderMappingStore:
    def __init__(self, path: str | Path) -> None:
        self._store = SQLiteStore(path)

    def save(self, mapping: BrokerOrderMapping) -> BrokerOrderMapping:
        self._store.connection.execute(
            """
            INSERT OR REPLACE INTO broker_order_mappings
                (order_id, account_id, client_order_id, broker_order_id, provider, payload)
            VALUES (?, ?, ?, ?, ?, ?)
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
        self._store.connection.commit()
        return mapping

    def get_by_order_id(self, order_id: UUID) -> BrokerOrderMapping:
        row = self._store.connection.execute(
            "SELECT payload FROM broker_order_mappings WHERE order_id = ?",
            (str(order_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown broker order mapping: {order_id}")
        return _load_model(BrokerOrderMapping, row["payload"])


class SQLiteGovernorStateStore:
    def __init__(self, path: str | Path) -> None:
        self._store = SQLiteStore(path)

    def save_policy(self, governor_id: str, policy: GovernorPolicy) -> GovernorPolicy:
        self._store.connection.execute(
            """
            INSERT OR REPLACE INTO governor_states (governor_id, payload)
            VALUES (?, ?)
            """,
            (governor_id, _dump_model(policy)),
        )
        self._store.connection.commit()
        return policy

    def load_policy(self, governor_id: str) -> GovernorPolicy:
        row = self._store.connection.execute(
            "SELECT payload FROM governor_states WHERE governor_id = ?",
            (governor_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown governor state: {governor_id}")
        return _load_model(GovernorPolicy, row["payload"])


class SQLiteDeploymentStateStore:
    def __init__(self, path: str | Path) -> None:
        self._store = SQLiteStore(path)

    def save_runtime_state(self, state: RuntimeState) -> RuntimeState:
        self._store.connection.execute(
            """
            INSERT OR REPLACE INTO deployment_states (deployment_id, payload)
            VALUES (?, ?)
            """,
            (str(state.deployment_id), _dump_model(state)),
        )
        self._store.connection.commit()
        return state

    def load_runtime_state(self, deployment_id: UUID) -> RuntimeState:
        row = self._store.connection.execute(
            "SELECT payload FROM deployment_states WHERE deployment_id = ?",
            (str(deployment_id),),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown deployment state: {deployment_id}")
        return _load_model(RuntimeState, row["payload"])


def _dump_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), sort_keys=True)


def _load_model(model_type, payload: str):  # type: ignore[no-untyped-def]
    return model_type.model_validate(json.loads(payload))
