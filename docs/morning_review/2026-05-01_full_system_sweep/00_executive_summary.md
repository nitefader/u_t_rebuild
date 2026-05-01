# Executive Summary - Full System Sweep

Date: 2026-05-01
Folder: `docs/morning_review/2026-05-01_full_system_sweep/`
Mode: audit/reporting only. No production code was changed.

## Bottom Line

Ultimate Trader has a real canonical SignalPlan runtime path, but it is not clean enough to call production-safe. The worst risks are old Program/ExecutionIntent surfaces still capable of creating or shaping orders, direct broker-position reads outside BrokerSync-backed truth, missing Operations read models for the runtime spine, and frontend surfaces that route operators into old Composer paths or raw internal IDs.

The frontend build passes, but full frontend tests are order-sensitive/flaky. Backend unit tests fail. The current tree is also heavily dirty with many untracked Strategy v4 / execution-plan files, so this audit reflects the working tree as found, not a clean committed baseline.

## Top Critical/High Findings

1. critical - `backend/app/orders/manager.py:107`, `backend/app/orders/models.py:45` - legacy `create_order(execution_intent)` and `OrderOrigin.PROGRAM` remain active order creation concepts.
2. critical - `backend/app/orders/manager.py:1063`, `backend/app/control_plane/service.py:173` - OrderManager/control-plane cancellation logic reads broker positions directly through BrokerAdapter instead of BrokerSync-owned truth.
3. high - `backend/app/governor/models.py:113`, `backend/app/governor/service.py:176` - Governor still accepts ExecutionIntent and emits `program_id` in projected state.
4. high - `backend/app/promotion/service.py:11` - active promotion gate is Program-based and hard-codes paper-to-live as a workflow.
5. high - `frontend/src/api/timelines.ts:24`, `backend/app/api/routes/operations.py:145` - Operations timeline calls missing SignalPlan and GovernorDecision endpoints; only evaluations exists.
6. high - `frontend/src/api/positions.ts:17`, `frontend/src/routes/PositionExplainDrawer.tsx:29` - Position explanation and AI advisory routes are wired in UI but absent in backend.
7. high - `frontend/src/routes/Strategies.tsx:52`, `frontend/src/router.tsx`, `frontend/src/routes/StrategyCompose.tsx:321` - primary strategy links still send operators to old `/strategies/compose`, while v4 exists separately.
8. high - `backend/tests/unit/api/test_frontend_api_contract.py:125` - frontend/API contract test misses several actual frontend calls, so passing route tests do not prove wiring.
9. high - `tools/paper_order_smoke.py:53`, `tools/run_runtime_dry_run.py:82` - operator smoke/runtime tools tests fail after Alpaca adapter constructor drift.
10. high - `backend/app/api/server.py:55`, Cloud Run docs - runtime streams start in FastAPI service startup; Cloud Run CPU/idle semantics are not documented or mitigated for always-on trading sync.

## Next 5 Repair Slices

1. Kill active Program/ExecutionIntent order path: remove/retire `OrderManager.create_order(execution_intent)`, change default order origin away from Program, and tighten lint allowlists.
2. Seal BrokerSync truth boundary: replace direct `BrokerAdapter.get_positions()` reads in OrderManager/control-plane sweeps with BrokerSync/runtime-store position truth.
3. Ship Operations runtime read models: persist/list SignalPlans and GovernorDecision traces, then wire `/api/v1/operations/signal-plans` and `/api/v1/operations/governor-decisions`.
4. Unify strategy authoring route: make `/strategies/compose-v4` the primary strategy creation path, retire or redirect legacy `/strategies/compose`, and update all links/tests.
5. Fix production/tooling gates: repair Alpaca operator tool tests, remove banned `Live Runtime` text, and define Cloud Run/worker deployment policy before live runtime claims.

## Verification Snapshot

- `python -m pytest backend\tests\unit -q` -> failed: 8 failed, 2121 passed, 6 warnings.
- `python -m pytest backend\tests\unit\api\test_frontend_api_contract.py backend\tests\unit\api\test_operations_routes.py backend\tests\unit\lint -q` -> failed: 1 failed, 282 passed, 5 warnings.
- `npm.cmd run build` -> passed; Vite warned about a 1,456.04 kB chunk.
- `npm.cmd run lint:names` -> passed.
- `npm.cmd test` -> failed: full Vitest run reported 2 failed suites, 77 passed files, 594 passed tests; targeted reruns of the two failed suites passed, indicating order sensitivity/flakiness.

See `07_test_commands_and_results.md` for exact commands and raw outcomes.
