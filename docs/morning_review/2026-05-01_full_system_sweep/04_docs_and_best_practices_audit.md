# 04 Docs + Best Practices Audit

Active docs reviewed:

- `docs/README.md`
- `docs/ULTIMATE_TRADER_MANDATE.md`
- `docs/architecture/NAMING_CONTRACT.md`
- `docs/architecture/CANONICAL_RUNTIME_ARCHITECTURE.md`
- `docs/architecture/SIGNALPLAN_POSITION_LIFECYCLE.md`
- `docs/architecture/BACKEND_MODULE_MAP.md`
- `docs/operations/RUNTIME_SHIP_GATE.md`
- `docs/operations/DAY_ZERO_RUNBOOK.md`
- `docs/implementation/IMPLEMENTATION_LOG.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- `Operations_Production_Readiness/OPERATION_STATUS.md`
- selected non-archived operation artifacts where current status referenced them

Archived docs were not used as authority. They only appeared in text searches and were ignored for current doctrine.

Online sources used:

- FastAPI bigger applications and APIRouter guidance: https://fastapi.tiangolo.com/tutorial/bigger-applications/
- FastAPI lifespan events: https://fastapi.tiangolo.com/advanced/events/
- FastAPI background task caveat: https://fastapi.tiangolo.com/tutorial/background-tasks/
- Cloud Run container runtime contract: https://cloud.google.com/run/docs/container-contract
- Cloud Run WebSockets: https://cloud.google.com/run/docs/triggering/websockets
- PostgreSQL `INSERT ... ON CONFLICT`: https://www.postgresql.org/docs/current/sql-insert.html
- Alpaca client order IDs: https://docs.alpaca.markets/docs/working-with-orders
- Alpaca order/bracket restrictions: https://docs.alpaca.markets/docs/orders-at-alpaca
- CodeMirror core extensions: https://codemirror.com/docs/extensions/
- Monaco completion provider API reference: https://hediet.github.io/monaco-editor/typedoc/functions/languages.registerCompletionItemProvider.html

## Findings

### D01 - Root README is missing

- severity: medium
- file path: `README.md`
- issue: The repo root has no README. `docs/README.md` exists, but a new human or deployment process landing at the root has no current entry point.
- why it matters: The user explicitly requested README review; the root README absence creates onboarding and deployment ambiguity.
- recommended fix: Add a short root README that points to `docs/README.md`, AGENTS.md, setup/test commands, and current production-readiness caveats.
- suggested agent prompt: "Create a minimal root README for Ultimate Trader. Link to active docs only, list setup/test commands, and state that archived docs are historical."

### D02 - Active implementation log is stale

- severity: medium
- file path: `docs/implementation/IMPLEMENTATION_LOG.md:1`
- issue: The active implementation log only records the 2026-04-26 docs reset and original UI pattern recommendations. Current code has many later backend/frontend slices not represented there.
- why it matters: Active docs no longer explain the implementation currently in the tree. Agents have to mine operation status logs and ledger entries instead.
- recommended fix: Add a current implementation-log index or move active status source to one canonical doc.
- suggested agent prompt: "Update active IMPLEMENTATION_LOG with a concise post-2026-04-26 index of shipped runtime/frontend/persistence slices. Do not import archived doctrine."

### D03 - Doctrine docs and code disagree on Program removal

- severity: high
- file path: `docs/ULTIMATE_TRADER_MANDATE.md:21`, `docs/architecture/NAMING_CONTRACT.md`, `backend/app/orders/manager.py:107`, `backend/app/promotion/service.py:11`
- issue: Active docs say no user-facing Program entity and no old names as active concepts, but backend runtime/order/governor/promotion still use Program and ExecutionIntent.
- why it matters: This is implementation/doc drift in a safety-critical area.
- recommended fix: Do not soften docs. Repair code and tests to match doctrine.
- suggested agent prompt: "Run a doctrine drift cleanup: Program/ExecutionIntent must be migration-only, not active runtime. Fix code/tests rather than changing doctrine."

### D04 - Operation status boards are rich but too large and not summarized for morning review

- severity: low
- file path: `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`, `Operations_Production_Readiness/OPERATION_STATUS.md`
- issue: Status files contain valuable history, but they are long enough that the current state is hard to extract quickly.
- why it matters: Morning operators need current blockers, current green checks, and next slice, not a forensic log.
- recommended fix: Add a small "Current State / Last Verified / Blocking Failures / Next Slice" block at the top of each status file and keep it current.
- suggested agent prompt: "Add a concise current-state summary block to both operation status boards, preserving history below."

### D05 - Cloud Run deployment policy is missing for always-on trading streams

- severity: high
- file path: `backend/app/api/server.py:55`, `docs/operations/RUNTIME_SHIP_GATE.md`, `Operations_Production_Readiness/CUTOVER_AND_RELEASE_PLAN.md`
- issue: The app starts market data streams, per-account trade streams, discovery polling, and in-process research jobs from the FastAPI service process. Active docs do not define Cloud Run settings needed for this shape.
- why it matters: Cloud Run services can scale to zero, idle instances can shut down, request-based CPU is allocated during request processing/startup/shutdown, and shutdown sends SIGTERM before SIGKILL. Always-on trading sync needs explicit minimum instances/CPU/worker-pool policy or a different deployment unit.
- recommended fix: Add a Cloud Run deployment decision doc before live trading: service vs worker pool, min instances, instance-based CPU, SIGTERM handling, WebSocket timeout/reconnect policy, and one-instance-vs-multi-instance stream ownership.
- suggested agent prompt: "Write the Cloud Run runtime policy for Ultimate Trader streams and jobs. Use official Cloud Run container/WebSocket docs. Decide service/worker-pool shape and list required settings."

### D06 - WebSocket docs do not cover Cloud Run timeout/reconnect behavior

- severity: medium
- file path: `frontend/src/api/ws.ts`, `backend/app/api/routes/operations_trade_stream.py`, `docs/architecture/STREAMS_AND_PROVIDERS.md`
- issue: Frontend has reconnect logic, and backend has stream routes, but active docs do not state Cloud Run WebSocket timeout behavior or reconnect expectations.
- why it matters: Cloud Run treats WebSockets as long-running HTTP requests subject to request timeout. Operators may see periodic disconnects even when the system is healthy.
- recommended fix: Document expected reconnect behavior, timeout settings, heartbeat/pulse semantics, and what counts as unhealthy.
- suggested agent prompt: "Update STREAMS_AND_PROVIDERS and Day Zero runbook with Cloud Run WebSocket timeout/reconnect expectations and operator-visible health states."

### D07 - FastAPI lifecycle best practice drift

- severity: medium
- file path: `backend/app/api/server.py:55`, `backend/app/api/server.py:97`
- issue: Code uses deprecated `@app.on_event` startup/shutdown hooks. FastAPI recommends lifespan context managers for startup/shutdown.
- why it matters: Runtime boot/shutdown is central to broker sync and stream cleanup.
- recommended fix: Move to `FastAPI(lifespan=...)` with explicit startup and cleanup ordering.
- suggested agent prompt: "Replace FastAPI on_event hooks with lifespan context. Rerun backend startup and stream route tests."

### D08 - Heavy background work needs a production worker decision

- severity: medium
- file path: `backend/app/research/jobs/runner.py:102`, `docs/operations/RUNTIME_SHIP_GATE.md`
- issue: Research jobs use a ThreadPoolExecutor in the API process. FastAPI docs note heavier background computation may need a queue/worker system.
- why it matters: In-process jobs can be interrupted by deploys, scale-down, or resource limits.
- recommended fix: Mark in-process jobs as local/dev only or move production jobs to Cloud Run jobs/worker pool with persisted state and cancellation semantics.
- suggested agent prompt: "Create production background-job policy for research runs. Define local in-process behavior and production worker/queue behavior."

### D09 - Postgres persistence practices are not reflected in implementation docs

- severity: high
- file path: `backend/app/persistence/models.py`, `backend/app/persistence/runtime_store.py`, `docs/operations/RUNTIME_SHIP_GATE.md`
- issue: Implementation is SQLite-specific. Docs mention deployment/cutover, but not a Postgres migration path, transaction model, or unique-index/idempotency policy.
- why it matters: Postgres idempotent writes rely on explicit unique constraints/indexes for `ON CONFLICT`; the current scattered SQLite DDL is not a production migration story.
- recommended fix: Document whether V1 ships SQLite-only. If Postgres is required, introduce versioned migrations, transaction boundaries, and uniqueness/index rules for orders, broker mappings, evaluations, and idempotency keys.
- suggested agent prompt: "Write the Postgres readiness plan: schema ownership, migrations, unique indexes for idempotency, transaction boundaries, and cutover tests."

### D10 - Alpaca order handling docs support lineage/client-order-id discipline, but code still has Program IDs

- severity: high
- file path: `backend/app/control_plane/client_order_id.py`, `backend/app/orders/manager.py:129`, `backend/app/orders/manager.py:455`
- issue: Alpaca supports client order IDs for organizing parallel strategies. The canonical system should encode SignalPlan/account/deployment lineage, but the legacy order path still uses Program client-order-id construction.
- why it matters: Broker reconciliation and duplicate detection depend on deterministic client order IDs. Program-based IDs can collide with or obscure SignalPlan lineage.
- recommended fix: Ensure all broker-submitted runtime orders use SignalPlan-origin client IDs and that legacy Program IDs cannot be submitted.
- suggested agent prompt: "Audit client_order_id construction. Require SignalPlan lineage for runtime orders and test uniqueness/idempotency across deployments/accounts."

### D11 - Monaco/CodeMirror best-practice gap is low risk

- severity: low
- file path: `frontend/src/strategy_ide_v4/strategyExprMonacoProviders.ts:19`
- issue: No current blocker found. Monaco provider registration returns a disposable, and the code disposes existing providers before registering.
- why it matters: Avoids duplicate completions in the Strategy v4 editor.
- recommended fix: Keep this pattern and document it in a short comment/test if more language providers appear.
- suggested agent prompt: none.
