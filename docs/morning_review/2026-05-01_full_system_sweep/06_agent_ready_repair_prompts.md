# 06 Agent-Ready Repair Prompts

## Prompt A - Remove Program/ExecutionIntent Order Path

You are Codex in Ultimate Trader. Read AGENTS.md and coordination files first. Fix only backend order-path doctrine drift. Remove or quarantine active `OrderManager.create_order(execution_intent)` so production order creation is only SignalPlan-origin or manual operator-origin. Make `InternalOrder.origin` explicit instead of defaulting to Program. Update tests away from `LegacyExecutionIntent` for active order-manager behavior. Tighten lint so Program order creation is migration-only. Do not create new architecture. Verify with focused orders/governor/pipeline tests and backend lint.

## Prompt B - Seal BrokerSync Truth Boundary

You are Codex. Replace direct `BrokerAdapter.get_positions()` reads in `backend/app/orders/manager.py` and `backend/app/control_plane/service.py` with BrokerSync/runtime-store position truth. OrderManager must not decide cancellation preservation from unreconciled broker reads. Add guardrail tests that orders/control_plane do not call `get_positions()` directly. Verify no broker truth writer/reader bypass outside BrokerSync-owned paths unless explicitly documented as validation-only.

## Prompt C - Remove ExecutionIntent/Program From Governor

You are Codex. Clean `backend/app/governor/models.py` and `backend/app/governor/service.py` so GovernorRequest no longer accepts `execution_intent` or `program_id`, and projected state no longer emits Program lineage. Convert tests to canonical SignalPlan/account-evaluation/risk inputs. Any legacy persisted data compatibility must live outside Governor as migration code. Rerun governor, pipeline, and lint tests.

## Prompt D - Operations SignalPlan/Governor Read Models

You are Codex. Add persisted read models and routes for `GET /api/v1/operations/signal-plans` and `GET /api/v1/operations/governor-decisions`. Include filters for account, deployment, symbol, and limit. Keep Account evaluations route intact. Update frontend contract tests and Operations tests so these routes are real, not expected 404. Do not mutate runtime behavior beyond recording read-model evidence.

## Prompt E - Position Explanation Backend

You are Codex. Implement the deterministic position explanation endpoint expected by the frontend: `GET /api/v1/broker-accounts/{account_id}/positions/{position_lineage_id}/explain`. It must read Account-owned broker position snapshots and lineage, not broker direct calls. Add optional `POST /api/v1/ai/explain-position` only as advisory over deterministic context. Add backend tests and update frontend tests from awaiting to real data.

## Prompt F - Strategy Compose v4 Route Consolidation

You are Claude/frontend owner. Make Strategy Compose v4 the primary authoring path. Update links in Strategies, StrategyDetail, StrategyBuilder, SideNav, and tests. Redirect or quarantine legacy `/strategies/compose` without presenting it as active strategy creation. Remove stale "Composer" product terminology where it conflicts with current naming. Preserve existing v4 tests and rerun frontend build/test slice.

## Prompt G - Repair Operator Tool Tests

You are Codex. Fix backend operator-tool tests failing after `AlpacaBrokerAdapter(mode=..., api_key=..., secret_key=...)` constructor changes. Update fake adapters in `backend/tests/unit/tools/test_account_operator_tools.py` and any related fixtures. Do not weaken safety assertions. Verify `tools/paper_order_smoke.py`, `tools/check_alpaca_readiness.py`, and `tools/run_runtime_dry_run.py` tests pass.

## Prompt H - Cloud Run Runtime Policy

You are Codex/docs. Write the Cloud Run deployment policy for Ultimate Trader using official Cloud Run docs. Decide and document how always-on market data streams, per-account trade sync, WebSockets, discovery poller, and research jobs run under Cloud Run service/worker/job constraints. Include CPU allocation, min instances, request timeouts, SIGTERM cleanup, and duplicate-stream ownership. Update active docs only.

## Prompt I - Frontend/API Contract Expansion

You are Codex with Claude coordination. Expand `backend/tests/unit/api/test_frontend_api_contract.py` to include every active frontend API client route and hardcoded route call. At minimum add Operations SignalPlans/Governor, Position explain, AI explain-position, WalkForward detail panels, Strategy v4, Execution Plans, and Strategy Controls. If a route is intentionally awaiting, annotate it in one allowlist with owner and expiry.

## Prompt J - Full Vitest Order Sensitivity

You are Claude/frontend owner. Debug why `npm.cmd test` failed collection for StrategyComposeV4 and StarterStrategyPanel while targeted reruns passed. Look for shared global `crypto`, module mocks, fetch mocks, and test cleanup. Make full Vitest run deterministic. Keep build passing. Record exact command results.

## Prompt K - Migration Strategy

You are Codex. Inventory all SQLite DDL in backend/app, including runtime_store, strategies, strategies_v4, deployments, execution_plans, strategy_controls, screener, and research jobs. Decide SQLite-only V1 vs Postgres readiness. If Postgres readiness is required, introduce a versioned migration plan and tests. Do not change schemas opportunistically; produce a small, reviewed migration foundation.

## Prompt L - Strategy v4 Response Models

You are Codex. Add Pydantic response models to `backend/app/api/routes/strategies_v4.py` for create/load/list/edit/duplicate/delete responses. Align them with `frontend/src/api/schemas/strategiesV4.ts`. Add route tests that every Strategy v4 route has an explicit response model where applicable.

## Prompt M - FastAPI Lifespan

You are Codex. Convert `backend/app/api/server.py` startup/shutdown `@app.on_event` hooks to a FastAPI lifespan context. Preserve startup ordering and shutdown cleanup. Rerun server startup, system streams, operations trade stream, and backend lint tests.

## Prompt N - Human-Readable Operations UI

You are Claude/frontend owner. Audit Operations, AccountDetailDrawer, OperationsTimelines, and RiskDecisionCardDrawer for UUID-first displays. Prefer account/deployment/strategy/symbol/display labels first. Keep raw IDs as secondary copy/debug detail. Add tests for readable labels where DTOs provide them; coordinate with Codex if backend DTOs lack names.

## Prompt O - Backtest Namespace Consolidation

You are Codex. Consolidate backtest routes to `/api/v1/research/backtests`. Deprecate or remove `/api/v1/backtests` after confirming frontend uses the canonical namespace. Update tests and docs. Do not change backtest runtime behavior.

## Prompt P - Root README

You are Codex/docs. Add a minimal root `README.md` that points to AGENTS.md and `docs/README.md`, lists setup/test commands, and warns that archived docs are historical only. Keep it short and current.

## Prompt Q - Refresh Implementation Log

You are Codex/docs. Update `docs/implementation/IMPLEMENTATION_LOG.md` with a concise index of current post-cleanup implementation slices based on active operation status and ledger. Do not pull archived docs into authority. Mark uncertain entries as uncertain.

## Prompt R - Banned Wording Lint Fix

You are Codex. Fix the banned `Live Runtime` phrase in `backend/app/simulation/historical_replay.py` with canonical wording. Do not change behavior. Rerun backend lint and the targeted historical replay tests.
