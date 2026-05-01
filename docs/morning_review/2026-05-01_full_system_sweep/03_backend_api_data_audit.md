# 03 Backend / API / Data Audit

Scope reviewed: registered FastAPI routes, route/schema mismatches visible from frontend clients, service wiring, persistence DDL, tests, runtime tool tests, and health/status surfaces.

## Findings

### B01 - Frontend/API contract test misses actual frontend calls

- severity: high
- file path: `backend/tests/unit/api/test_frontend_api_contract.py:125`, `frontend/src/api/timelines.ts:24`, `frontend/src/api/positions.ts:17`, `frontend/src/routes/WalkForward.tsx:267`
- issue: The contract test includes many current endpoints but omits actual frontend calls for Operations SignalPlans, Governor decisions, Position explain, AI explain-position, and WalkForward detail subroutes.
- why it matters: Route tests can pass while user-facing API calls 404.
- recommended fix: Generate or maintain the contract from frontend API clients, or add explicit entries for every non-placeholder call.
- suggested agent prompt: "Expand backend frontend-api contract tests to cover every endpoint in frontend/src/api and route-level hardcoded calls. Make missing registered routes fail unless annotated as intentionally awaiting."

### B02 - Duplicate backtest API namespaces remain active

- severity: medium
- file path: `backend/app/api/routes/research_runs.py:280`, `backend/app/api/routes/research_runs.py:286`, `backend/app/api/routes/research_runs.py:357`, `backend/app/api/routes/research_runs.py:363`
- issue: Backtests are registered under both `/api/v1/backtests` and `/api/v1/research/backtests`.
- why it matters: Duplicate active routes invite inconsistent clients, tests, and docs. The frontend schema comments call the non-research path legacy.
- recommended fix: Keep one canonical namespace. Convert legacy routes to redirects/deprecation only, or remove after frontend migration.
- suggested agent prompt: "Consolidate backtest routes on `/api/v1/research/backtests`. Remove or deprecate `/api/v1/backtests` with tests proving clients use the canonical namespace."

### B03 - Strategy v4 routes lack explicit response models

- severity: medium
- file path: `backend/app/api/routes/strategies_v4.py:87`, `backend/app/api/routes/strategies_v4.py:98`, `backend/app/api/routes/strategies_v4.py:109`, `backend/app/api/routes/strategies_v4.py:117`, `backend/app/api/routes/strategies_v4.py:128`
- issue: Most Strategy v4 route decorators return bare `dict`/`list[dict]` without `response_model`.
- why it matters: This weakens API schema generation and contract testing for a new strategy authoring surface.
- recommended fix: Define Pydantic response DTOs matching `frontend/src/api/schemas/strategiesV4.ts` and attach `response_model` to every route.
- suggested agent prompt: "Add explicit response models for strategies_v4 routes and update backend route tests to require them. Keep response shape aligned with frontend strategiesV4 schemas."

### B04 - Operator smoke/runtime tools are broken against current Alpaca adapter constructor

- severity: high
- file path: `tools/paper_order_smoke.py:53`, `tools/check_alpaca_readiness.py:39`, `tools/run_runtime_dry_run.py:82`, `backend/tests/unit/tools/test_account_operator_tools.py:266`
- issue: Backend unit tests fail because fake adapters in operator-tool tests do not accept the current keyword-only Alpaca constructor (`mode`, `api_key`, `secret_key`).
- why it matters: These are Day Zero/operator safety tools. Broken tests mean paper-order smoke and dry-run safety cannot be trusted.
- recommended fix: Update fake adapter constructors and add a constructor contract test for operator tools.
- suggested agent prompt: "Repair backend/tests/unit/tools/test_account_operator_tools.py fakes to match AlpacaBrokerAdapter constructor. Rerun tool tests and full backend unit suite."

### B05 - Persistence is SQLite-first with scattered DDL and no versioned migration framework

- severity: high
- file path: `backend/app/persistence/models.py:4`, `backend/app/persistence/runtime_store.py:1623`, `backend/app/strategies_v4/persistence.py:36`, `backend/app/deployments/persistence.py:14`, `COORDINATION/PROTOCOL.md:57`
- issue: DDL lives across multiple repositories as `CREATE TABLE IF NOT EXISTS` and ad hoc `ALTER TABLE`. Coordination docs reference `backend/migrations/`, but no versioned migration system is present in the active backend tree.
- why it matters: Production Postgres/Cloud deployment cannot rely on scattered SQLite boot migrations. Schema drift becomes hard to audit and rollback.
- recommended fix: Decide whether V1 is SQLite-only or create real migrations. For Postgres readiness, add Alembic or equivalent versioned migrations and test startup against a fresh DB.
- suggested agent prompt: "Create a migration plan for current SQLite DDL. Inventory tables/indices, decide SQLite-only vs Postgres path, and introduce versioned migrations before more persistence slices."

### B06 - Runtime DB path can silently fall back to legacy SQLite file

- severity: medium
- file path: `backend/app/config/runtime_paths.py:20`, `backend/app/config/runtime_paths.py:52`
- issue: If `data/runtime.db` does not exist and `data/utos.sqlite3` does, the app uses the legacy file unless production env requires explicit path.
- why it matters: Local/dev runs can accidentally use stale legacy state, making audits and tests misleading.
- recommended fix: Keep production fail-closed behavior and add a visible startup warning/status flag when legacy fallback is used. Prefer explicit env in all runbooks.
- suggested agent prompt: "Add a system status field and test for runtime DB source: configured, default, or legacy fallback. Update runbooks to require explicit OPERATIONS_RUNTIME_DB_PATH for any shared runtime."

### B07 - SignalPlan persistence is partial: evaluations persist, SignalPlans/Governor traces do not have Operations routes

- severity: high
- file path: `backend/app/persistence/models.py:304`, `backend/app/api/routes/operations.py:145`, `frontend/src/api/timelines.ts:24`
- issue: `account_signal_plan_evaluations` exists and `/operations/evaluations` is registered, but SignalPlan and GovernorDecision trace read models are missing from Operations.
- why it matters: The operator cannot trace Deployment emission through Governor decision with persisted evidence.
- recommended fix: Persist SignalPlan events and Governor decisions with lineage, then expose list/detail routes with filters.
- suggested agent prompt: "Add persisted SignalPlan and GovernorDecisionTrace read models plus Operations routes. Include account/deployment/symbol filters and tests proving the UI endpoints are registered."

### B08 - Backend health/status exists, but production readiness status is incomplete

- severity: medium
- file path: `backend/app/api/routes/system_status.py:92`, `backend/app/api/routes/system_streams.py:147`, `backend/app/api/routes/operations_trade_stream.py:93`
- issue: Health/status endpoints exist for system status, streams, and trade-stream health, but there is no single production readiness endpoint combining DB source, migration status, stream boot state, BrokerSync freshness, and route registration.
- why it matters: Day Zero needs one operator-visible "can this trade safely" status, not scattered diagnostics.
- recommended fix: Add a read-only readiness endpoint/dashboard card composed from existing services. Do not make it start streams or mutate state.
- suggested agent prompt: "Add `/api/v1/system/readiness` as a read-only aggregator over DB source, migration version, stream state, BrokerSync freshness, and critical route availability. Add Operations card."

### B09 - Tests still prove legacy paths instead of only canonical wiring

- severity: high
- file path: `backend/tests/unit/orders/test_order_manager.py:29`, `backend/tests/unit/governor/test_portfolio_governor.py:20`, `backend/tests/unit/brokers/test_alpaca_broker_adapter.py:22`
- issue: Many tests import `LegacyExecutionIntent` and assert Program lineage behavior.
- why it matters: The suite can pass while preserving old active concepts. It also makes future cleanup harder because tests pin the wrong path.
- recommended fix: Convert safety-critical tests to SignalPlan/account-evaluation/governor-decision inputs. Keep legacy tests only under migration-specific names.
- suggested agent prompt: "Convert order/governor/broker tests from LegacyExecutionIntent to SignalPlan-origin fixtures. Move any remaining legacy fixtures under migration-only tests."

### B10 - Research job runner is in-process background work

- severity: medium
- file path: `backend/app/research/jobs/runner.py:102`, `backend/app/research/jobs/runner.py:118`, `backend/app/api/server.py:55`
- issue: Research jobs use an in-process `ThreadPoolExecutor` in the API process.
- why it matters: This may be fine locally, but Cloud Run services can scale down or throttle idle CPU depending on billing. Long research jobs need explicit production deployment semantics.
- recommended fix: Document local-only behavior or move production jobs to Cloud Run jobs/worker pool/queue. Persist job heartbeats and resume/fail closed on shutdown.
- suggested agent prompt: "Define production behavior for research jobs on Cloud Run. Either mark in-process runner local-only or move to a worker/queue with persisted heartbeats and shutdown handling."
