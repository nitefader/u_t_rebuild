from __future__ import annotations

RUNTIME_SCHEMA = """
CREATE TABLE IF NOT EXISTS internal_orders (
    order_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'program',
    deployment_id TEXT,
    program_id TEXT,
    client_order_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_internal_orders_account_id ON internal_orders(account_id);
CREATE INDEX IF NOT EXISTS ix_internal_orders_origin ON internal_orders(origin);
CREATE INDEX IF NOT EXISTS ix_internal_orders_deployment_id ON internal_orders(deployment_id);
CREATE INDEX IF NOT EXISTS ix_internal_orders_program_id ON internal_orders(program_id);

CREATE TABLE IF NOT EXISTS trades (
    trade_id TEXT PRIMARY KEY,
    deployment_id TEXT,
    account_id TEXT,
    symbol TEXT NOT NULL,
    payload_type TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_trades_deployment_id ON trades(deployment_id);
CREATE INDEX IF NOT EXISTS ix_trades_account_id ON trades(account_id);
CREATE INDEX IF NOT EXISTS ix_trades_symbol ON trades(symbol);

CREATE TABLE IF NOT EXISTS broker_order_mappings (
    order_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    broker_order_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_broker_order_mappings_broker_order_id
    ON broker_order_mappings(provider, broker_order_id);
CREATE INDEX IF NOT EXISTS ix_broker_order_mappings_account_id ON broker_order_mappings(account_id);

CREATE TABLE IF NOT EXISTS broker_accounts (
    account_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    mode TEXT NOT NULL,
    external_account_id TEXT,
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_account_snapshots (
    account_id TEXT PRIMARY KEY,
    provider TEXT,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS broker_position_snapshots (
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (account_id, symbol)
);

CREATE TABLE IF NOT EXISTS broker_open_order_snapshots (
    broker_order_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_broker_open_order_snapshots_account_id
    ON broker_open_order_snapshots(account_id);

CREATE TABLE IF NOT EXISTS broker_sync_freshness (
    account_id TEXT PRIMARY KEY,
    last_sync_at TEXT NOT NULL,
    is_stale INTEGER NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deployment_runtime_states (
    deployment_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_governor_states (
    governor_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS control_plane_states (
    control_plane_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS manual_order_idempotency (
    account_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    order_id TEXT,
    status TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    operator_session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS ix_manual_order_idempotency_order_id
    ON manual_order_idempotency(order_id);
CREATE INDEX IF NOT EXISTS ix_manual_order_idempotency_status
    ON manual_order_idempotency(status);

CREATE TABLE IF NOT EXISTS manual_trade_audit_events (
    event_id TEXT PRIMARY KEY,
    event_code TEXT NOT NULL,
    account_id TEXT NOT NULL,
    order_id TEXT,
    client_order_id TEXT,
    idempotency_key TEXT,
    operator_session_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_manual_trade_audit_events_account_time
    ON manual_trade_audit_events(account_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_manual_trade_audit_events_code_time
    ON manual_trade_audit_events(event_code, occurred_at);
CREATE INDEX IF NOT EXISTS ix_manual_trade_audit_events_order_id
    ON manual_trade_audit_events(order_id);
"""
