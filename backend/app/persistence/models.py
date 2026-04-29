from __future__ import annotations

RUNTIME_SCHEMA = """
CREATE TABLE IF NOT EXISTS internal_orders (
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
    default_risk_plan_id TEXT,
    default_risk_plan_version_id TEXT,
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS account_risk_configs (
    account_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS account_restrictions (
    account_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_plans (
    risk_plan_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    risk_tier TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    source TEXT NOT NULL,
    account_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_risk_plans_status
    ON risk_plans(status);
CREATE INDEX IF NOT EXISTS ix_risk_plans_tier
    ON risk_plans(risk_tier);
CREATE INDEX IF NOT EXISTS ix_risk_plans_source
    ON risk_plans(source);
CREATE INDEX IF NOT EXISTS ix_risk_plans_account_id
    ON risk_plans(account_id);

CREATE TABLE IF NOT EXISTS risk_plan_versions (
    risk_plan_version_id TEXT PRIMARY KEY,
    risk_plan_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    archived_at TEXT,
    payload TEXT NOT NULL,
    FOREIGN KEY (risk_plan_id) REFERENCES risk_plans(risk_plan_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_risk_plan_versions_plan_version
    ON risk_plan_versions(risk_plan_id, version);
CREATE INDEX IF NOT EXISTS ix_risk_plan_versions_risk_plan_id
    ON risk_plan_versions(risk_plan_id);
CREATE INDEX IF NOT EXISTS ix_risk_plan_versions_status
    ON risk_plan_versions(status);
CREATE INDEX IF NOT EXISTS ix_risk_plan_versions_config_fingerprint
    ON risk_plan_versions(config_fingerprint);

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

CREATE TABLE IF NOT EXISTS research_evidence (
    evidence_id TEXT PRIMARY KEY,
    evidence_type TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_research_evidence_strategy
    ON research_evidence(strategy_id, strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_research_evidence_type
    ON research_evidence(evidence_type);
CREATE INDEX IF NOT EXISTS ix_research_evidence_created_at
    ON research_evidence(created_at);

CREATE TABLE IF NOT EXISTS risk_decision_cards (
    risk_decision_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    run_id TEXT NOT NULL,
    session_id TEXT,
    account_id TEXT,
    simulated_account_id TEXT,
    strategy_id TEXT NOT NULL,
    strategy_version_id TEXT NOT NULL,
    deployment_id TEXT,
    signal_plan_id TEXT NOT NULL,
    risk_plan_id TEXT NOT NULL,
    risk_plan_version_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    decision TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_risk_decision_cards_run_id
    ON risk_decision_cards(run_id);
CREATE INDEX IF NOT EXISTS ix_risk_decision_cards_signal_plan_id
    ON risk_decision_cards(signal_plan_id);
CREATE INDEX IF NOT EXISTS ix_risk_decision_cards_account_id
    ON risk_decision_cards(account_id);
CREATE INDEX IF NOT EXISTS ix_risk_decision_cards_strategy_version_id
    ON risk_decision_cards(strategy_version_id);
CREATE INDEX IF NOT EXISTS ix_risk_decision_cards_risk_plan_version_id
    ON risk_decision_cards(risk_plan_version_id);
CREATE INDEX IF NOT EXISTS ix_risk_decision_cards_created_at
    ON risk_decision_cards(created_at);

CREATE TABLE IF NOT EXISTS historical_datasets (
    dataset_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    coverage_start TEXT NOT NULL,
    coverage_end TEXT NOT NULL,
    adjustment_policy TEXT NOT NULL,
    timezone TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    bar_count INTEGER NOT NULL,
    aggregate_quality_status TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_historical_datasets_identity
    ON historical_datasets(provider, symbol, timeframe, adjustment_policy);
CREATE INDEX IF NOT EXISTS ix_historical_datasets_symbol
    ON historical_datasets(symbol);

CREATE TABLE IF NOT EXISTS research_jobs (
    job_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_current INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER NOT NULL DEFAULT 0,
    progress_label TEXT NOT NULL DEFAULT '',
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    result_run_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    operator_session_id TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_research_jobs_status
    ON research_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS ix_research_jobs_kind
    ON research_jobs(kind, created_at);
CREATE INDEX IF NOT EXISTS ix_research_jobs_result_run_id
    ON research_jobs(result_run_id);
"""
