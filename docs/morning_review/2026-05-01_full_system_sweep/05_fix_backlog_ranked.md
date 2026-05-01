# 05 Ranked Fix Backlog

## P0 - Critical Trading Safety

### 1. Remove active Program/ExecutionIntent order path

- severity: critical
- file path: `backend/app/orders/manager.py:107`, `backend/app/orders/models.py:45`
- issue: Legacy execution intent can still create Program-origin internal orders.
- why it matters: Duplicate order path can bypass canonical SignalPlan lineage.
- recommended fix: Remove or quarantine `create_order(execution_intent)`, require explicit non-Program origin, update tests.
- suggested agent prompt: See `06_agent_ready_repair_prompts.md`, prompt A.

### 2. Seal BrokerSync truth boundary

- severity: critical
- file path: `backend/app/orders/manager.py:1063`, `backend/app/control_plane/service.py:173`
- issue: Cancellation logic reads broker positions directly through BrokerAdapter.
- why it matters: Order cancellation may use unreconciled broker truth outside BrokerSync/Operations.
- recommended fix: Use persisted BrokerSync position snapshots for backing-position checks.
- suggested agent prompt: See prompt B.

## P1 - High Runtime/User-Facing Breakage

### 3. Remove ExecutionIntent/Program from Governor request path

- severity: high
- file path: `backend/app/governor/models.py:113`, `backend/app/governor/service.py:176`
- issue: Governor accepts old intent and emits `program_id`.
- why it matters: Final safety gate still supports old runtime vocabulary.
- recommended fix: Canonical request fields only; migration-only compatibility outside Governor.
- suggested agent prompt: See prompt C.

### 4. Ship Operations SignalPlan and Governor read models

- severity: high
- file path: `frontend/src/api/timelines.ts:24`, `backend/app/api/routes/operations.py:145`
- issue: Operations has evaluations but lacks SignalPlan and GovernorDecision routes.
- why it matters: Operators cannot trace the spine end to end.
- recommended fix: Persist/read SignalPlans and Governor decisions with filters.
- suggested agent prompt: See prompt D.

### 5. Repair Position explanation backend

- severity: high
- file path: `frontend/src/routes/PositionExplainDrawer.tsx:29`, `frontend/src/api/positions.ts:17`
- issue: UI calls explanation and AI routes that backend does not register.
- why it matters: Position Truth is not explainable in Operations.
- recommended fix: Add deterministic position context endpoint and optional AI advisory endpoint.
- suggested agent prompt: See prompt E.

### 6. Make Strategy Compose v4 the only primary authoring path

- severity: high
- file path: `frontend/src/routes/Strategies.tsx:52`, `frontend/src/routes/StrategyCompose.tsx:321`
- issue: Old Composer and v4 Compose both active and linked.
- why it matters: Duplicate product paths and stale old-name concepts.
- recommended fix: Update links, redirect/quarantine old route, fix tests.
- suggested agent prompt: See prompt F.

### 7. Fix operator smoke/runtime tool tests

- severity: high
- file path: `backend/tests/unit/tools/test_account_operator_tools.py:266`, `tools/run_runtime_dry_run.py:82`
- issue: Tool tests fail after Alpaca adapter constructor change.
- why it matters: Day Zero safety tools are not protected by passing tests.
- recommended fix: Update fakes and constructor contract.
- suggested agent prompt: See prompt G.

### 8. Define Cloud Run stream/job deployment policy

- severity: high
- file path: `backend/app/api/server.py:55`, `docs/operations/RUNTIME_SHIP_GATE.md`
- issue: Always-on streams/jobs are booted in API service with no Cloud Run CPU/scale/shutdown policy.
- why it matters: Trading sync can be killed, throttled, duplicated, or timed out without clear production settings.
- recommended fix: Decide service vs worker pool, min instances, CPU allocation, SIGTERM, WebSocket reconnect.
- suggested agent prompt: See prompt H.

### 9. Tighten frontend/backend contract tests

- severity: high
- file path: `backend/tests/unit/api/test_frontend_api_contract.py:125`
- issue: Contract omits actual frontend routes.
- why it matters: Broken user-facing calls pass backend tests.
- recommended fix: Add every frontend API client path or generate contract inventory.
- suggested agent prompt: See prompt I.

### 10. Fix full Vitest order sensitivity

- severity: high
- file path: `frontend/src/routes/StrategyComposeV4.test.tsx`, `frontend/src/strategy_ide_v4/StarterStrategyPanel.test.tsx`
- issue: Full test run failed while targeted suites passed.
- why it matters: CI cannot reliably protect frontend changes.
- recommended fix: Isolate shared mocks/globals and rerun full suite.
- suggested agent prompt: See prompt J.

## P2 - Medium Production Readiness

### 11. Add versioned migration strategy

- severity: high
- file path: `backend/app/persistence/models.py`, `backend/app/strategies_v4/persistence.py`
- issue: Scattered SQLite DDL, no migration framework.
- why it matters: Postgres/cloud readiness is not real without migrations.
- recommended fix: Inventory schema and introduce migration plan.
- suggested agent prompt: See prompt K.

### 12. Add explicit Strategy v4 response models

- severity: medium
- file path: `backend/app/api/routes/strategies_v4.py:87`
- issue: New API returns bare dicts.
- why it matters: OpenAPI/contract drift risk.
- recommended fix: Attach response DTOs.
- suggested agent prompt: See prompt L.

### 13. Replace FastAPI `on_event` lifecycle

- severity: medium
- file path: `backend/app/api/server.py:55`
- issue: Deprecated startup/shutdown hooks.
- why it matters: Runtime boot/shutdown is safety-critical.
- recommended fix: Use lifespan context.
- suggested agent prompt: See prompt M.

### 14. Clean raw-ID-first operator displays

- severity: medium
- file path: `frontend/src/routes/Operations.tsx:731`, `frontend/src/routes/OperationsTimelines.tsx:206`
- issue: UUIDs are primary operator labels.
- why it matters: Violates human-readable frontend rule.
- recommended fix: Add display names/labels and move IDs to debug detail.
- suggested agent prompt: See prompt N.

### 15. Consolidate backtest namespaces

- severity: medium
- file path: `backend/app/api/routes/research_runs.py:280`
- issue: `/api/v1/backtests` and `/api/v1/research/backtests` both active.
- why it matters: Duplicate API path.
- recommended fix: Keep canonical research namespace; deprecate legacy path.
- suggested agent prompt: See prompt O.

## P3 - Lower Cleanup

### 16. Add root README

- severity: medium
- file path: `README.md`
- issue: Missing root entry point.
- why it matters: Onboarding/deployment ambiguity.
- recommended fix: Add minimal README pointing to active docs.
- suggested agent prompt: See prompt P.

### 17. Refresh active implementation log

- severity: medium
- file path: `docs/implementation/IMPLEMENTATION_LOG.md`
- issue: Log is stale after 2026-04-26 reset.
- why it matters: Docs no longer track reality.
- recommended fix: Add current implementation index.
- suggested agent prompt: See prompt Q.

### 18. Remove banned wording in historical replay

- severity: high
- file path: `backend/app/simulation/historical_replay.py:1296`
- issue: Backend lint fails on `Live Runtime`.
- why it matters: Blocks backend unit suite and violates naming contract.
- recommended fix: Replace phrase with canonical wording.
- suggested agent prompt: See prompt R.
