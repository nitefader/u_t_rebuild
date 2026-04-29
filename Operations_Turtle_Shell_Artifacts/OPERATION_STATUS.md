# Operation Turtle Shell Status

Last updated: 2026-04-29 13:43:29 -04:00

## Date And Time Syntax

All Operation Turtle Shell timestamps use:

```text
YYYY-MM-DD HH:mm:ss -04:00
```

Date-only approvals use:

```text
YYYY-MM-DD
```

## Current Mode

Backend doctrine spine lockdown remains primary.

Exception (2026-04-26): **Data Center · Historical Datasets** is an approved
read-only operator surface (inventory + bar grid + dataset chart + side
drawer). It does not add trading, broker submit, or a second runtime root.

## Executive Briefing

Work session status: release_cleanup_commit_push_in_progress

Agent role: Codex - Operation Turtle Shell backend doctrine spine

Started at: 2026-04-27 22:28:16 -04:00

Last heartbeat: 2026-04-29 13:43:29 -04:00

Ended at: pending git push

Expected next checkpoint: Push `master` to `origin`, then confirm the working tree is clean.

Operator urgency:

```text
2026-04-26 night work is critical. The operator intends to trade, backtest,
use Chart Lab, run Sim Lab, and run optimization on 2026-04-27.
```

Continuity instruction:

```text
No agent may begin silently. No agent may end silently. Update this executive
briefing at start, heartbeat, and handoff.
```

## Current Phase

Account Detail Risk Card backend route and bulk delete UX slice shipped; local backend/frontend restarted and verified live; release cleanup underway.

## Current Task

Operator-requested Account Detail Risk Card route gap and easier bulk deletion for Deployments/Watchlists completed; local dev servers refreshed; verification clean; release commit/push requested by operator.

## Current Owner

Codex

## Reviewers

- UX/front-end engineer
- Nanyel/product owner
- User/test mapper
- Codex doctrine reviewer

## Latest Completed Action

Release cleanup before commit:

- Started at: 2026-04-29 13:36:00 -04:00
- Completed verification at: 2026-04-29 13:43:29 -04:00
- Verification:
  - `git diff --check` -> clean, CRLF warnings only.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - Initial full `npm.cmd test` hit two 5-second timeout-only frontend tests under whole-suite load; both failed tests passed focused.
  - `npx.cmd vitest run --testTimeout=15000` in `frontend/` -> 48 files / 336 tests passed.
  - `npm.cmd run lint:names` in `frontend/` -> clean.
  - `python -m pytest backend/tests/unit -q` -> 1395 passed, 6 warnings.
- Next action:
  - Stage all dirty/untracked work, commit, and push to `origin/master`.

Local dev server refresh:

- Started at: 2026-04-29 13:20:00 -04:00
- Completed at: 2026-04-29 13:31:19 -04:00
- Completed:
  - Stopped stale duplicate uvicorn/Vite processes.
  - Restarted backend on `127.0.0.1:8000`.
  - Restarted frontend Vite on `127.0.0.1:5173`.
  - Verified direct backend HTTP 200 for Account Risk Card routes on account `e43733eb-4d90-473b-af46-6aaac06e85f7`.
  - Verified Vite-proxied HTTP 200 for the same Risk Card routes through `127.0.0.1:5173/api/...`.
- Active listeners:
  - Backend: `python.exe` uvicorn on `127.0.0.1:8000`
  - Frontend: Vite on `127.0.0.1:5173`
- Blockers:
  - None. Browser may need a hard refresh if it still has the old failed query cached.

Account Risk Card routes and bulk delete UX:

- Started at: 2026-04-29 12:50:17 -04:00
- Completed at: 2026-04-29 13:00:42 -04:00
- Completed:
  - Added durable `AccountRiskConfig` and `AccountRestrictions` models plus SQLite persistence on the runtime store.
  - Added `GET/PUT /api/v1/broker-accounts/{account_id}/risk-config`.
  - Added `GET/PUT /api/v1/broker-accounts/{account_id}/restrictions`.
  - Account Detail Risk Card now consumes live routes and no longer says Operation Turtle Shell route/persistence work is pending.
  - Deployment list now supports select-all and bulk delete through the existing guarded delete route.
  - Watchlist list now supports select-all, bulk archive, and guarded bulk hard delete; archive remains the safer history-preserving path.
  - Per-row failure reporting keeps blocked rows understandable by readable name.
- Files touched:
  - `backend/app/api/routes/broker_accounts.py`
  - `backend/app/broker_accounts/{__init__.py,models.py}`
  - `backend/app/persistence/{models.py,runtime_store.py}`
  - `backend/tests/unit/api/{test_broker_accounts_routes.py,test_frontend_api_contract.py}`
  - `backend/tests/unit/persistence/test_sqlite_persistence.py`
  - `frontend/src/api/schemas/risk.ts`
  - `frontend/src/routes/{RiskCardPanel,Deployments,Watchlists}.tsx`
  - `frontend/src/routes/{RiskCardPanel,Deployments,Watchlists}.test.tsx`
  - `frontend/src/routes/explainerContent.ts`
  - `COORDINATION/{LOCKS.md,LEDGER.md,INBOX_CLAUDE.md}`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_broker_accounts_routes.py backend/tests/unit/persistence/test_sqlite_persistence.py backend/tests/unit/api/test_frontend_api_contract.py -q` -> 41 passed, 5 warnings.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npx.cmd vitest run src/routes/Deployments.test.tsx src/routes/Watchlists.test.tsx src/routes/RiskCardPanel.test.tsx` in `frontend/` -> 12 passed.
- Blockers:
  - None for this slice.
  - Existing unrelated Strategy Builder/roadmap dirty files remain outside this slice and were not reverted.
- Nanyel approval:
  - Approved. The Account Risk Card is account-owned policy data, not broker truth; Deployment bulk delete still uses the existing lifecycle guard; Watchlist delete/archive keeps Watchlists entry-only and preserves audit/deployment protections. No SignalPlan, Governor, BrokerAdapter, BrokerSync, order, or position-truth path changed.

Screener/Watchlist UX clarity slice:

- Started at: 2026-04-29 07:47:00 -04:00
- Completed at: 2026-04-29 08:06:58 -04:00
- Completed:
  - Added `Operations_Turtle_Shell_Artifacts/SCREENER_WATCHLIST_UX_FIX_PLAN.md` with MAP understanding, system areas, current behavior, problem/gap, proposed solution, implementation plan, validation checklist, and expert findings.
  - Scoped Screener detail actions so operators can distinguish latest-version actions from selected-run actions: `Run latest version`, `Rerun selected run`, `Compare with previous run`, and `Save selected matches`.
  - Added readable criterion/result formatting, including boolean Yes/No labels, readable metric labels, ResultsTable presets, and `Decision reason`.
  - Added template search/show-all and collapsed advanced Screener run settings.
  - Replaced schedule weekday numeric text entry with weekday chips and made schedule execution labels human-readable, with raw IDs relegated to debug title text.
  - Synced `UniverseSourcePicker` explicit-symbol draft state from the controlled value.
  - Added Watchlist deep-link open-after-save behavior.
  - Updated Deployment and explainer copy: entries come from Watchlists; exits come from Account-owned Positions scoped to the Deployment.
  - Final UX/front-end engineer, Nanyel/product owner, and test-mapper reviews all approved.
- Files touched:
  - `Operations_Turtle_Shell_Artifacts/SCREENER_WATCHLIST_UX_FIX_PLAN.md`
  - `frontend/src/components/screener/{CriteriaEditor.tsx,DiscoveryScheduleControls.tsx,ExpressionPreview.tsx,ResultsTable.tsx,UniverseSourcePicker.tsx,criterionFormat.ts}`
  - `frontend/src/components/screener/{DiscoveryScheduleControls.test.tsx,ExpressionPreview.test.tsx,ResultsTable.test.tsx,UniverseSourcePicker.test.tsx}`
  - `frontend/src/routes/{Screeners.tsx,ScreenerDetail.tsx,Watchlists.tsx,Deployments.tsx,explainerContent.ts}`
  - `frontend/src/routes/{Screeners.test.tsx,ScreenerDetail.test.tsx}`
  - `frontend/scripts/headless-screener-watchlist.mjs`
  - `COORDINATION/{LOCKS.md,LEDGER.md,INBOX_CLAUDE.md}`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npx.cmd vitest run src/routes/Screeners.test.tsx src/routes/ScreenerDetail.test.tsx src/routes/Watchlists.test.tsx src/routes/Deployments.test.tsx src/components/screener/DiscoveryScheduleControls.test.tsx src/components/screener/ResultsTable.test.tsx src/components/screener/UniverseSourcePicker.test.tsx src/components/screener/ExpressionPreview.test.tsx` in `frontend/` -> 24 passed.
  - `npm.cmd test` in `frontend/` -> 44 files / 308 tests passed plus banned-name lint clean.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `node --check scripts/headless-screener-watchlist.mjs` in `frontend/` -> passed.
  - `git diff --check` -> passed with CRLF warnings only.
- Blockers:
  - None for this slice.
  - Existing unrelated Strategy Builder/roadmap dirty files remain outside this slice and were not reverted.
- Nanyel approval:
  - Approved. Screeners remain discovery-only, Watchlists remain entry-only, Strategy remains symbol-agnostic, Deployment remains a SignalPlan publisher, exits remain Account/Position scoped, BrokerSync remains the only broker truth writer, and raw IDs are not primary operator-facing labels.

Local Git hygiene cleanup:

- Started at: 2026-04-29 07:25:00 -04:00
- Completed at: 2026-04-29 07:28:47 -04:00
- Completed:
  - Stopped tracking local `.env`.
  - Stopped tracking Python bytecode caches under `__pycache__` and `*.pyc`.
  - Added `.claude/` to `.gitignore`.
  - Left local files on disk but ignored by Git.
- Tests run:
  - Not rerun; Git index hygiene only.
- Blockers:
  - None.
- Nanyel approval:
  - Approved. No runtime source behavior or trading doctrine path changed.

Chart Lab source checkpoint:

- Started at: 2026-04-29 06:30:00 -04:00
- Completed at: 2026-04-29 06:38:57 -04:00
- Completed:
  - Status audit found imported Chart Lab preview files still uncommitted after the large checkpoint.
  - Committed `c3a83ce`: `Add strategy preview chart component`.
  - Included `frontend/src/components/charts/StrategyPreviewChart.tsx`, `frontend/src/routes/ChartLab.tsx`, and `frontend/src/routes/ChartLab.test.tsx`.
  - Kept visible Chart Lab preview source Alpaca-only; no Yahoo option is exposed.
  - Fixed `lightweight-charts` RGB parsing by emitting comma-separated RGB strings.
- Tests run:
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npx.cmd vitest run src/routes/ChartLab.test.tsx` in `frontend/` -> 7 passed.
- Blockers:
  - GitHub push blocked: `git remote -v` returns no configured remote.
- Nanyel approval:
  - Approved. Chart Lab remains research-only and cannot submit broker orders; Alpaca remains provider pack; no trading spine ownership changed.

Local Git checkpoint:

- Started at: 2026-04-29 06:19:00 -04:00
- Completed at: 2026-04-29 06:28:40 -04:00
- Completed:
  - Created local commit `9e1d3d2` on `master`: `Checkpoint production rebuild and screener journey`.
  - Captured the verified rebuild, Alpaca-first Screener/Watchlist journey, frontend migration, backend services, tests, operation docs, and coordination artifacts.
  - Added `.runtime_logs/` and `*.tsbuildinfo` to `.gitignore`.
  - Confirmed staged checkpoint excluded `.env`, `.claude/`, `.runtime_logs/`, `__pycache__`, `.pyc`, and `*.tsbuildinfo`.
  - Ran `git diff --cached --check`; fixed whitespace hygiene findings before commit.
- Tests run:
  - No full suite rerun after commit-only hygiene cleanup. Prior verified gate remains: `npm.cmd run headless:screener` -> 43 checks; frontend suite -> 288 passed; backend unit suite -> 1392 passed.
- Blockers:
  - GitHub push blocked: `git remote -v` returns no configured remote.
- Nanyel approval:
  - Approved for local checkpoint. No trading doctrine path changed by the commit operation.

Screener/Watchlist full user journey and persona headless verification:

- Started at: 2026-04-29 04:05:53 -04:00
- Completed at: 2026-04-29 04:35:37 -04:00
- Completed:
  - Drafted `SCREENER_WATCHLIST_USER_JOURNEY.md` for Nanyel/operator, expert day trader, and swing/quant user.
  - Added explicit headless persona gates for `operator`, `day_trader`, and `swing_quant`.
  - Added headless AAPL capability regression: AAPL must return `broker.tradable=true` and must not show a false "asset is not tradable at Alpaca" reason.
  - Converted Watchlist schedule creation and schedule run/pause/resume/archive exercise to visible schedule controls in the headless browser flow.
  - Added schedule execution history UI with readable run/snapshot labels, diff counts, status, trigger, and timezone visibility.
  - Hardened schedule execution claim/recovery: atomic running-execution claim and stale-running abandonment after deterministic timeout.
  - Fixed schedule drawer form state so rapid visible control edits cannot overwrite cadence/interval/session fields with stale state.
  - Restarted backend on `127.0.0.1:8000` before the final headless run.
- Files touched:
  - `Operations_Turtle_Shell_Artifacts/SCREENER_WATCHLIST_USER_JOURNEY.md`
  - `backend/app/screener/{schedule_store.py,schedule_service.py}`
  - `backend/tests/unit/screener/test_discovery_schedules.py`
  - `frontend/src/components/screener/{DiscoveryScheduleControls.tsx,DiscoveryScheduleControls.test.tsx}`
  - `frontend/scripts/headless-screener-watchlist.mjs`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npm.cmd run headless:screener` in `frontend/` -> 43 checks passed.
  - `npm.cmd test` in `frontend/` -> 288 passed plus banned-name lint clean.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npm.cmd run lint:names` in `frontend/` -> clean.
  - `node --check scripts/headless-screener-watchlist.mjs` in `frontend/` -> passed.
  - `npx.cmd vitest run src/components/screener/DiscoveryScheduleControls.test.tsx` in `frontend/` -> 3 passed.
  - `python -m pytest backend/tests/unit/screener/test_discovery_schedules.py -q` -> 5 passed, 1 warning.
  - `python -m pytest backend/tests/unit -q` -> 1392 passed, 6 warnings.
- Blockers:
  - None.
- Nanyel approval:
  - Approved. The journey remains discovery/entry-only, schedules never submit broker orders or mutate Account truth, Watchlists do not drive exits, Deployment emits SignalPlans only, and BrokerSync remains the only broker truth writer.

Screener/Watchlist scheduling and Alpaca capability evidence fix:

- Started at: 2026-04-29 03:05:06 -04:00
- Completed at: 2026-04-29 04:01:30 -04:00
- Completed:
  - Verified live Alpaca asset evidence for AAPL returns active/tradable/fractionable/shortable/easy-to-borrow.
  - Fixed Screener metric collection so Alpaca asset capabilities are attached even when bar metrics are unavailable.
  - Changed blocked wording so unavailable Alpaca evidence is not reported as a false "not tradable" capability.
  - Added durable discovery schedules for exact ScreenerVersion runs and Watchlist refreshes with next/last run, execution records, pause/resume/archive/delete, non-overlap guard, startup poller, and active-Deployment approval protection for scheduled Watchlist refresh.
  - Added visible schedule controls on Screener detail and Watchlist detail; Watchlist schedules default to operator review and require explicit auto-snapshot when active deployments are involved.
  - Restarted local backend so `/api/v1/discovery-schedules` and the poller are loaded.
  - Updated headless walkthrough to cover scheduling; final pass is 23 checks.
- Files touched:
  - `backend/app/screener/{domain.py,sources.py,service.py,schedules.py,schedule_store.py,schedule_service.py,scheduler_runtime.py}`
  - `backend/app/watchlists/service.py`
  - `backend/app/api/routes/discovery_schedules.py`
  - `backend/app/api/server.py`
  - `backend/tests/unit/screener/{test_discovery_schedules.py,test_screener_alpaca_first.py}`
  - `backend/tests/unit/api/test_frontend_api_contract.py`
  - `frontend/src/api/{discoverySchedules.ts,schemas/discoverySchedules.ts}`
  - `frontend/src/components/screener/{DiscoveryScheduleControls.tsx,ResultsTable.tsx,ResultsTable.test.tsx}`
  - `frontend/src/routes/{ScreenerDetail.tsx,Watchlists.tsx}`
  - `frontend/scripts/headless-screener-watchlist.mjs`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npm.cmd run headless:screener` in `frontend/` -> 23 checks passed.
  - `python -m pytest backend/tests/unit -q` -> 1391 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/screener backend/tests/unit/watchlists backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py -q` -> 58 passed, 5 warnings.
  - `npm.cmd test` in `frontend/` -> 285 passed plus banned-name lint clean.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npm.cmd run lint:names` in `frontend/` -> clean.
  - `node --check scripts/headless-screener-watchlist.mjs` in `frontend/` -> passed.
- Blockers:
  - None.
- Nanyel approval:
  - Approved. Schedules are discovery/entry-universe automation only; Screener remains discovery-only; Watchlists remain entry-only; Strategy remains symbol-agnostic; Deployment still emits SignalPlans only; exits remain Account/Position scoped by `deployment_id`; BrokerSync remains the only broker truth writer; Alpaca remains provider pack, not core architecture.

Headless verifier hardening and final retrospective closeout:

- Started at: 2026-04-29 01:46:25 -04:00
- Completed at: 2026-04-29 02:54:40 -04:00
- Completed:
  - Addressed Enemy Agent's objection that the first verifier leaned too much on browser-side API calls for operator controls.
  - Hardened `npm.cmd run headless:screener` to pass 21 checks, including UI drawer/control coverage for:
    - AI Composer advisory controls.
    - Day Losers and Most Active Alpaca market-list variants.
    - Typed criteria metric/operator/value controls.
    - Deployment Strategy version selection.
    - Full Screener -> Watchlist -> Deployment verification path.
  - Fixed Deployment UI doctrine mismatch: current Strategy versions can now be selected for Deployment attachment; freezing remains the post-attachment commit boundary.
  - Added a Deployment UI regression test proving draft/current Strategy versions are selectable.
  - Reran requested final retrospectives: Alpaca Expert, UX reviewer, and Enemy Agent all passed with no blockers.
  - Released verifier-hardening leases and notified Claude.
- Files touched:
  - `frontend/scripts/headless-screener-watchlist.mjs`
  - `frontend/package.json`
  - `frontend/src/routes/Deployments.tsx`
  - `frontend/src/routes/Deployments.test.tsx`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npm.cmd run headless:screener` in `frontend/` -> 21 checks passed.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npx.cmd vitest run src/routes/Deployments.test.tsx` in `frontend/` -> 4 passed.
  - `npm.cmd run lint:names` in `frontend/` -> clean.
  - `node --check scripts/headless-screener-watchlist.mjs` in `frontend/` -> passed.
  - `python -m pytest backend/tests/unit/screener/test_screener_runtime.py backend/tests/unit/screener/test_screener_alpaca_first.py backend/tests/unit/screener/test_screener_service.py backend/tests/unit/screener/test_screener_routes.py -q` -> 30 passed, 5 warnings.
- Blockers:
  - None.
- Nanyel approval:
  - Approved. The final verifier is auditable and doctrine-aligned: Screener is discovery-only, Watchlist is entry-only, Deployment attaches entry universe and emits SignalPlans only, exits remain Account/Position scoped by `deployment_id`, BrokerSync remains the only broker truth writer, AI remains advisory and visible, and no duplicate runtime or broker order path was introduced.

Headless Screener/Watchlist browser release verification:

- Started at: 2026-04-29 00:51:39 -04:00
- Completed at: 2026-04-29 01:44:20 -04:00
- Completed:
  - Ran the operator-requested npm headless browser walkthrough against the live local backend and frontend.
  - Fixed live provider release gaps found by the walkthrough:
    - Removed stale Screener runtime dependency on `DataCenterStore`.
    - Resolved saved Alpaca credentials through the runtime SQLite store.
    - Reused the same runtime store for Screener historical bar lookup.
    - Capped Alpaca market-list provider requests at Alpaca's `top <= 50` limit.
  - Added repeatable script `npm.cmd run headless:screener`.
  - Verified the browser flow end-to-end: Screeners page, Alpaca market lists, templates, AI advisory composer, create/edit/run/rerun/compare, static Watchlist save, dynamic Watchlist create/refresh with source run, Deployment entry-universe attachment, archive/delete guard, readable UI labels, and audit/source visibility.
  - Captured a headless screenshot under `.runtime_logs/headless-screener-2026-04-29T05-39-07-818Z.png`.
  - Confirmed both local servers are still listening: backend `127.0.0.1:8000`, frontend `127.0.0.1:5173`.
- Files touched:
  - `backend/app/screener/runtime.py`
  - `backend/app/screener/sources.py`
  - `backend/tests/unit/screener/test_screener_runtime.py`
  - `frontend/scripts/headless-screener-watchlist.mjs`
  - `frontend/package.json`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npm.cmd run headless:screener` in `frontend/` -> passed 17 checks.
  - `python -m pytest backend/tests/unit/screener/test_screener_runtime.py backend/tests/unit/screener/test_screener_alpaca_first.py backend/tests/unit/screener/test_screener_service.py backend/tests/unit/screener/test_screener_routes.py -q` -> 30 passed, 5 warnings.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `node --check scripts/headless-screener-watchlist.mjs` in `frontend/` -> passed.
  - `npm.cmd run lint:names` in `frontend/` -> clean.
- Blockers:
  - None.
- Nanyel approval:
  - Approved. Screener remains discovery-only; Watchlists remain entry-only; Strategy remains symbol-agnostic; Deployment attaches Watchlists as entry universe and emits SignalPlans only; exits remain Account/Position scoped by `deployment_id`; BrokerSync remains the only broker truth writer; AI remains advisory and visible; no duplicate runtime or broker order path was introduced.

Screeners 500 operational recovery:

- Started at: 2026-04-29 00:40:00 -04:00
- Completed at: 2026-04-29 00:45:14 -04:00
- Completed:
  - Reproduced the operator-reported Screeners 500 against the live backend process.
  - Verified current source code returns 200 for `/api/v1/screeners` and `/api/v1/watchlists` under `TestClient`.
  - Identified the live backend process as stale from before the current Watchlist/Screener schema migration code was loaded.
  - Restarted only the backend server on `127.0.0.1:8000`.
  - Verified real HTTP 200 responses for `/api/v1/screeners`, `/api/v1/watchlists`, `/api/v1/screeners/templates`, `/api/v1/screeners/market-lists`, and `/api/v1/screeners/fields`.
- Files touched:
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `TestClient(app).get("/api/v1/screeners")` -> 200.
  - `TestClient(app).get("/api/v1/watchlists")` -> 200.
  - Real HTTP checks on `127.0.0.1:8000` -> 200 for Screeners/Watchlists core endpoints.
- Blockers:
  - None.
- Nanyel approval:
  - Operational fix only. No doctrine surface changed; Screener remains discovery-only and Watchlists remain entry-only.

Operator override Alpaca-first Screener/Watchlist completion:

- Started at: 2026-04-28 23:50:30 -04:00
- Completed at: 2026-04-29 00:39:19 -04:00
- Completed:
  - Completed the 10-step Alpaca-first Screener/Watchlist plan front-to-back under the operator override.
  - Added Alpaca market-list UI entry points, Screener templates, advisory-only AI composer, visible typed expression preview, run/rerun/compare, archive/delete confirmation, static/dynamic save-as-watchlist, dynamic refresh evidence/diff, and Deployment labels that prefer strategy/watchlist names over raw ids.
  - Preserved expression-backed Screener versions instead of flattening grouped `all` / `any` / `not` logic.
  - Made manual Watchlist creation static-only in the UI; dynamic Watchlists come from Screener run lineage.
  - Hardened backend release findings: `source_preference` now exposes `auto|alpaca|data_center`, and run-by-version rejects versions from another Screener.
  - Ran requested retrospectives with Alpaca Expert, UX reviewer, and Enemy Agent; fixed the rejection findings before closing the slice.
  - Released Codex frontend/shared leases and notified Claude.
- Files touched:
  - `frontend/src/api/schemas/screener.ts`
  - `frontend/src/api/schemas/watchlists.ts`
  - `frontend/src/api/screener.ts`
  - `frontend/src/api/watchlists.ts`
  - `frontend/src/components/screener/`
  - `frontend/src/routes/Screeners.tsx`
  - `frontend/src/routes/ScreenerDetail.tsx`
  - `frontend/src/routes/Watchlists.tsx`
  - `frontend/src/routes/Deployments.tsx`
  - `frontend/src/routes/*Screener*.test.tsx`
  - `frontend/src/routes/Watchlists.test.tsx`
  - `frontend/src/routes/Deployments.test.tsx`
  - `backend/app/screener/domain.py`
  - `backend/app/screener/service.py`
  - `backend/app/api/routes/screener.py`
  - `backend/tests/unit/screener/test_screener_service.py`
  - `backend/tests/unit/screener/test_screener_routes.py`
  - `backend/tests/unit/api/test_frontend_api_contract.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npm.cmd run typecheck` -> passed.
  - `npx.cmd vitest run src/routes/ScreenerDetail.test.tsx src/routes/Screeners.test.tsx src/routes/Watchlists.test.tsx src/routes/Deployments.test.tsx` -> 14 passed.
  - `python -m pytest backend/tests/unit/screener/test_screener_service.py backend/tests/unit/screener/test_screener_routes.py backend/tests/unit/screener/test_screener_alpaca_first.py backend/tests/unit/watchlists/test_watchlist_refresh.py backend/tests/unit/api/test_frontend_api_contract.py` -> 39 passed, 5 warnings.
  - `npm.cmd test` -> 282 passed; banned-name lint clean.
  - `npm.cmd run build` -> passed; Vite chunk-size warning only.
  - `python -m pytest backend/tests/unit` -> 1376 passed, 6 warnings.
- Blockers:
  - No code blocker remains.
  - No opt-in live Alpaca credential test was run; no credential-dependent live provider call was attempted.
- Nanyel approval:
  - Approved under doctrine: Screener remains discovery-only, Watchlist remains entry-only, Strategy remains symbol-agnostic, Deployment emits SignalPlans only, exits remain Account/Position scoped by `deployment_id`, BrokerSync remains the only broker truth writer, AI remains advisory and visible, and no duplicate runtime path was introduced.

Alpaca-first Step 10 backend release gate:

- Started at: 2026-04-28 22:59:07 -04:00
- Completed at: 2026-04-28 23:03:46 -04:00
- Completed:
  - Re-read `MAP__MASTER_AGENT_PROMPT.md`, `COORDINATION/PROTOCOL.md`, locks, inbox, ledger, operation status, and the Alpaca-first plan before continuing.
  - Confirmed no Claude ack for frontend-owned Step 9 UI/schema work was present in `COORDINATION/INBOX_CODEX.md`.
  - Added a backend release-gate test covering:
    - Alpaca Day Gainers market-list run.
    - Edited ScreenerVersion with broker fractionable filter.
    - Run, rerun, and diff showing added/stayed symbols.
    - Static Watchlist snapshot from matched symbols.
    - Dynamic Watchlist refresh snapshots from a ScreenerVersion, with source run id and added/stayed diff.
    - Deployment attachment using Watchlist as entry universe while Strategy remains symbol-agnostic.
    - Active Deployment reference guard blocking Watchlist archive.
    - Logical exit rule requiring `PositionContext`, proving exits remain Account/Position scoped rather than Watchlist scoped.
  - Released Codex test-path leases and notified Claude.
- Files touched:
  - `backend/tests/unit/screener/test_screener_alpaca_first.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/screener/test_screener_alpaca_first.py -q -vv` -> 6 passed, 1 warning.
  - `python -m pytest backend/tests/unit/screener backend/tests/unit/watchlists backend/tests/unit/deployments backend/tests/unit/domain/test_domain_boundaries.py backend/tests/unit/simulation/test_logical_exit_spine.py -q` -> 102 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1369 passed, 6 warnings.
- Blockers:
  - Step 9 frontend/UI integration remains blocked by AGENTS/PROTOCOL ownership until Claude acks the 2026-04-28 22:24:00 frontend/shared lease request, or the operator explicitly redirects frontend ownership.
  - No opt-in live Alpaca test was run; no credential-dependent live provider call was attempted.
- Nanyel approval:
  - Backend release gate approved. Screener remains discovery-only, Watchlist remains entry-only, Deployment only owns the entry universe and lifecycle, SignalPlan/Account/Position exit doctrine remains intact, and no duplicate runtime path was introduced.

Alpaca-first Screener/Watchlist backend contract:

- Started at: 2026-04-28 22:22:31 -04:00
- Completed at: 2026-04-28 22:52:37 -04:00
- Completed:
  - Read `AGENTS.md`, `MAP__MASTER_AGENT_PROMPT.md`, coordination state, operation status, and the Alpaca-first plan before editing.
  - Used requested subagents: Alpaca Expert, UX reviewer, Enemy Agent, lower-cost inventory, and lower-cost test mapping.
  - Added typed Screener field registry for existing bar-backed metrics plus Alpaca broker-capability fields:
    `broker.tradable`, `broker.fractionable`, `broker.shortable`, `broker.easy_to_borrow`, `broker.active`, `broker.exchange`, `broker.asset_class`, and `broker.name`.
  - Added typed `ScreenerExpression` AST with `all` / `any` / `not` / `criterion`; old flat criteria rows still compile to an `all(...)` expression.
  - Added Alpaca market-list and asset-capability adapters behind the Screener provider boundary; Alpaca stays provider pack, not core architecture.
  - Removed Screener production Yahoo fallback so the Screener path does not silently use Yahoo scraping as its provider backbone.
  - Added Screener templates and top-level Market Lists contract.
  - Added advisory-only Screener AI interpretation endpoint; it returns typed rules, assumptions, unsupported clauses, and audit preview without writes.
  - Added run/rerun/diff lifecycle, Screener archive, delete guard for run history, and dynamic save-as-watchlist option.
  - Replaced placeholder dynamic Watchlist snapshots with resolver-backed refresh snapshots containing source run id, evidence, added/removed/stayed diff, and readable source labels.
  - Added Watchlist archive and refresh endpoints; delete now blocks snapshot history and active Deployment references.
  - Filed Claude frontend/shared lease request and backend contract heads-up; no frontend-owned files edited.
- Files touched:
  - `backend/app/screener/domain.py`
  - `backend/app/screener/fields.py`
  - `backend/app/screener/sources.py`
  - `backend/app/screener/templates.py`
  - `backend/app/screener/ai.py`
  - `backend/app/screener/service.py`
  - `backend/app/screener/runtime.py`
  - `backend/app/screener/__init__.py`
  - `backend/app/watchlists/models.py`
  - `backend/app/watchlists/service.py`
  - `backend/app/watchlists/runtime_service.py`
  - `backend/app/api/routes/screener.py`
  - `backend/app/api/routes/watchlists.py`
  - `backend/app/api/server.py`
  - `backend/tests/unit/screener/test_screener_alpaca_first.py`
  - `backend/tests/unit/screener/test_screener_routes.py`
  - `backend/tests/unit/watchlists/test_watchlist_refresh.py`
  - `backend/tests/unit/watchlists/test_watchlist_service.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/screener/test_screener_alpaca_first.py -q -vv` -> 5 passed.
  - `python -m pytest backend/tests/unit/screener/test_screener_service.py -q` -> 10 passed.
  - `python -m pytest backend/tests/unit/watchlists -q -vv` -> 12 passed.
  - `python -m pytest backend/tests/unit/screener/test_screener_routes.py -q` -> 10 passed.
  - `python -m pytest backend/tests/unit/screener backend/tests/unit/watchlists -q` -> 37 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 8 passed.
  - `python -m pytest backend/tests/unit/screener backend/tests/unit/watchlists backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py -q` -> 47 passed.
  - `python -m pytest backend/tests/unit -q` -> 1368 passed, 6 warnings.
- Blockers:
  - Step 9 frontend/UI integration is blocked by AGENTS/PROTOCOL ownership until Claude acks the 2026-04-28 22:24:00 frontend/shared lease request, or the operator explicitly redirects frontend ownership.
  - No opt-in live Alpaca test was run; no credential-dependent live provider call was attempted.
- Nanyel approval:
  - Backend slice approved. Screener remains discovery-only, Watchlist remains entry-only, AI is advisory-only, runs/snapshots are immutable audit evidence, Strategy remains symbol-agnostic, Deployment/SignalPlan/Account/BrokerSync trading spine is untouched.

Alpaca-first Screener/Watchlist execution plan:

- Started at: 2026-04-28 22:06:35 -04:00
- Completed at: 2026-04-28 22:12:29 -04:00
- Completed:
  - Created `Operations_Turtle_Shell_Artifacts/ALPACA_FIRST_SCREENER_WATCHLIST_PLAN.md`.
  - Broke the build into 10 steps from current-state audit through end-to-end release gate.
  - Incorporated three user reviewers: Nanyel/operator, expert day trader, swing/quant user.
  - Added Alpaca Expert and Enemy Agent review roles.
  - Captured provider decision: Alpaca-first, Yahoo as product inspiration only unless licensed/stable.
  - Added explicit boundaries: Screener discovery-only, Watchlist entry-only, Deployment SignalPlan-only, BrokerSync only broker truth writer.
  - Added template, AI advisory, run/rerun/compare, archive/delete, refresh, and dynamic Watchlist snapshot plans.
  - Added restart prompt for a new Codex window.
- Files touched:
  - `Operations_Turtle_Shell_Artifacts/ALPACA_FIRST_SCREENER_WATCHLIST_PLAN.md`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - Not run; planning artifact only.
- Blockers:
  - None for planning. Implementation must coordinate with Claude before frontend/shared edits.
- Nanyel approval:
  - Pending operator approval to start the new execution window.

Watchlist list 500 fix:

- Started at: 2026-04-28 18:53:05 -04:00
- Completed at: 2026-04-28 18:58:26 -04:00
- Completed:
  - Reproduced `GET /api/v1/watchlists` returning 500 against `data/runtime.db`.
  - Identified root cause: legacy SQLite table shape `watchlists(id, type, config_json, latest_symbols_json, created_at, updated_at)` was missing canonical `kind` / `payload`, so repository schema initialization failed while creating the `kind` index.
  - Updated `WatchlistRepository` initialization to migrate legacy `watchlists` rows into canonical payload-backed `Watchlist` rows before creating indexes.
  - Added a guard for legacy `watchlist_snapshots` tables so old snapshot schemas cannot trigger the same init-time failure.
  - Preserved the `/api/v1/watchlists` response shape; no frontend contract changes.
  - Migrated the local `data/runtime.db` by exercising the route; the route now returns 200.
  - Notified Claude and logged the route-changed ledger entry.
- Files touched:
  - `backend/app/watchlists/persistence.py`
  - `backend/tests/unit/watchlists/test_watchlist_service.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/watchlists backend/tests/unit/api/test_frontend_api_contract.py -q` -> 17 passed.
  - `npx.cmd vitest run src/routes/Watchlists.test.tsx` in `frontend/` -> 3 passed.
  - Direct `TestClient` call to `GET /api/v1/watchlists` against `data/runtime.db` -> 200.
  - `npm.cmd --prefix frontend run test -- Watchlists.test.tsx` -> failed because the package script runs the full frontend suite; failures were in current Strategy Builder tests, unrelated to Watchlists.
- Blockers:
  - Running backend process must reload/restart to pick up the repository migration code if hot reload is not active.
- Nanyel approval:
  - Approved. Watchlists remain the Deployment entry universe only; exits still come from Account-owned Positions. No Strategy symbols, SignalPlan behavior, Account truth, RiskResolver, Governor, BrokerAdapter, or BrokerSync flow changed.

Backtest cache gap fix and Market Data enable route:

- Started at: 2026-04-28 12:34:43 -04:00
- Completed at: 2026-04-28 13:01:27 -04:00
- Completed:
  - Investigated Claude's report that Backtest appeared to download bars and read `historical_datasets` for the same window.
  - Confirmed the source of the operator-visible duplicate behavior: Backtest asks Data Center for a 14-day warmup window, so a dataset seeded for the exact run window was treated as a partial miss and the old ingest code fetched the full warmup+run window again.
  - Updated `HistoricalBarIngestService.ensure_bars` to fetch only missing cache gaps, merge provider rows with the existing dataset, and dedupe inclusive provider boundary bars by `(symbol, timeframe, timestamp)`.
  - Preserved the exact cache-hit invariant: matching stored coverage still returns from Data Center with zero provider calls.
  - Added `POST /api/v1/market-data/services/{service_id}/enable`.
  - `enable_service` clears `disabled_at`; previously validated services return to `status=valid`, while unvalidated/invalid services return to `status=draft` so credentials are never silently trusted.
  - Notified Claude and logged cross-boundary route/cache entries.
- Files touched:
  - `backend/app/data_center/ingest_service.py`
  - `backend/app/api/routes/market_data.py`
  - `backend/app/market_data/catalog.py`
  - `backend/tests/unit/api/test_data_center_routes.py`
  - `backend/tests/unit/api/test_market_data_routes.py`
  - `backend/tests/unit/market_data/test_market_data_catalog.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_market_data_routes.py backend/tests/unit/api/test_data_center_routes.py backend/tests/unit/market_data/test_market_data_catalog.py -q` -> 22 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 8 passed.
  - `python -m pytest backend/tests/unit -q` -> 1288 passed, 30 warnings.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npm.cmd test` in `frontend/` -> 93 passed; banned-name lint clean.
- Blockers:
  - None.
- Nanyel approval:
  - Approved. The change keeps Data Center as the single historical-data cache path, adds no alternate runtime, performs no Watchlist mutation, and restores provider availability through an explicit operator route without hidden credential validation.

Operations overview phantom Deployment fix:

- Started at: 2026-04-28 11:57:54 -04:00
- Completed at: 2026-04-28 12:08:19 -04:00
- Completed:
  - Traced Dashboard Deployments KPI source to `GET /api/v1/operations/overview.deployments.length`.
  - Confirmed `OperationsCenterService._deployment_ids()` was promoting old internal-order and pipeline-event `deployment_id` lineage into overview Deployment summaries.
  - Updated overview discovery to count only real Deployment records, persisted deployment runtime states, and current in-memory deployment contexts.
  - Wired the Operations API composition root to the Deployment repository so Dashboard and Deployments page reality stay aligned.
  - Preserved Account/deployment detail behavior so old orders can still expose lineage without creating phantom Dashboard Deployments.
  - Added a regression test for historical SignalPlan order lineage plus recent pipeline-event lineage.
  - Notified Claude and logged the route-changed entry because Dashboard consumes this route.
- Files touched:
  - `backend/app/operations/service.py`
  - `backend/app/operations/runtime_service.py`
  - `backend/tests/unit/operations/test_operations_center_service.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/operations/test_operations_center_service.py -q` -> 22 passed.
  - `python -m pytest backend/tests/unit/operations/test_operations_center_service.py backend/tests/unit/api/test_operations_routes.py -q` -> 37 passed.
  - `python -m pytest backend/tests/unit/api/test_server_startup.py backend/tests/unit/operations/test_operations_center_service.py backend/tests/unit/api/test_operations_routes.py -q` -> 38 passed.
  - `python -m pytest backend/tests/unit -q` -> timed out before reporting.
- Blockers:
  - Running backend must be restarted or reloaded before the live `/api/v1/operations/overview` payload reflects this code change.
- Approval status:
  - Backend read-model fix shipped under Nanyel doctrine: Deployment count is current operator state, not inferred from stale order lineage.

Dashboard Operations overview KPI wiring:

- Started at: 2026-04-28 11:49:05 -04:00
- Completed at: 2026-04-28 11:53:54 -04:00
- Completed:
  - Wired Dashboard to call existing `GET /api/v1/operations/overview`.
  - Replaced placeholder Deployments KPI with live count plus running/blocked context.
  - Replaced placeholder Open Positions KPI with `open_positions_count` plus open-order context.
  - Preserved explicit degraded state: overview failure shows `unavailable`, not false zero.
  - Notified Claude and logged the frontend-consumed entry.
- Files touched:
  - `frontend/src/routes/Dashboard.tsx`
  - `frontend/src/routes/Dashboard.test.tsx`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `npx.cmd vitest run src/routes/Dashboard.test.tsx` in `frontend/` -> 4 passed.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npm.cmd run lint:names` in `frontend/` -> clean.
- Blockers:
  - None.
- Approval status:
  - Dashboard KPI read-model wiring shipped.

Operations AccountSignalPlanEvaluation read-model:

- Started at: 2026-04-28 02:04:00 -04:00
- Completed at: 2026-04-28 02:18:00 -04:00
- Completed:
  - Added `GET /api/v1/operations/evaluations`.
  - Response is `{evaluations: AccountSignalPlanEvaluation[]}` using the
    existing domain contract consumed by the frontend timeline.
  - Supports `account_id`, `deployment_id`, `signal_plan_id`, and `limit`
    filters.
  - Projects durable accepted Account evaluations from SignalPlan-origin
    internal orders carrying `account_evaluation_id` and optional
    `governor_decision_id`.
  - Manual orders and legacy orders without SignalPlan lineage are excluded
    so Operations stays a read model and does not fabricate trading facts.
  - Notified Claude and logged the route-added entry.
- Files touched:
  - `backend/app/operations/models.py`
  - `backend/app/operations/__init__.py`
  - `backend/app/operations/service.py`
  - `backend/app/api/routes/operations.py`
  - `backend/tests/unit/operations/test_operations_center_service.py`
  - `backend/tests/unit/api/test_operations_routes.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/operations/test_operations_center_service.py backend/tests/unit/api/test_operations_routes.py -q` -> 35 passed.
  - `python -m pytest backend/tests/unit -q` -> 1255 passed, 6 warnings.
- Blockers:
  - None.
- Approval status:
  - Backend Operations evaluation timeline route shipped.

Backtest operator-test gap closure:

- Started at: 2026-04-28 01:32:00 -04:00
- Completed at: 2026-04-28 01:48:00 -04:00
- Completed:
  - Strategy Composer save path now persists normalized feature refs instead
    of validating a normalized copy and saving the original draft payload.
  - FeatureParser / FeaturePlanner now support legacy bare bar refs by
    defaulting `close`, `open`, etc. to `StrategyControlsVersion.timeframe`.
  - Alpaca historical bars source now supports alpaca-py
    `StockHistoricalDataClient.get_stock_bars`.
  - Research sync routes, async job routes, and Data Center ingest now build
    AlpacaBarsSource from a validated saved Alpaca Account's encrypted
    credentials.
  - Answered Claude's 01:25 inbox request and logged the route-changed entry.
- Files touched:
  - `backend/app/features/parser.py`
  - `backend/app/features/planner.py`
  - `backend/app/strategy_composer/service.py`
  - `backend/app/data_center/ingest_service.py`
  - `backend/app/api/routes/research_runs.py`
  - `backend/app/api/routes/research_jobs.py`
  - `backend/app/api/routes/data_center.py`
  - `backend/tests/unit/features/test_feature_planner.py`
  - `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`
  - `backend/tests/unit/api/test_data_center_routes.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/strategy_composer/test_strategy_composer_service.py backend/tests/unit/features/test_feature_planner.py backend/tests/unit/api/test_data_center_routes.py backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/research/test_research_job_runner.py -q` -> 61 passed.
  - `python -m pytest backend/tests/unit -q` -> 1252 passed, 6 warnings.
- Blockers:
  - None.
- Approval status:
  - Backend operator gaps closed; ready for end-to-end retry.

Risk Plan list/detail enrichment follow-up:

- Started at: 2026-04-28 00:45:00 -04:00
- Completed at: 2026-04-28 01:08:00 -04:00
- Completed:
  - Added `active_version_id`, `active_version`, `linked_account_count`, and
    `last_used_at` to `GET /api/v1/risk-plans` rows.
  - Added `active_version_id`, `active_version`, `linked_accounts`,
    `backtest_usage`, and `decision_stats` to
    `GET /api/v1/risk-plans/{risk_plan_id}` envelopes.
  - Derived linked accounts, backtest usage, and decision stats from persisted
    Account, BacktestRun, and RiskDecisionCard rows.
  - Added a SQLite index for RiskDecisionCard lookup by
    `risk_plan_version_id`.
  - Answered Claude's inbox request and logged the route-changed entry.
- Files touched:
  - `backend/app/api/routes/risk_plans.py`
  - `backend/app/persistence/models.py`
  - `backend/app/persistence/runtime_store.py`
  - `backend/tests/unit/api/test_risk_plan_routes.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_risk_plan_routes.py -q` -> 7 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/api/test_risk_plan_routes.py -q` -> 15 passed.
  - `python -m pytest backend/tests/unit -q` -> 1249 passed, 6 warnings.
- Blockers:
  - None.
- Approval status:
  - Backend enrichment shipped; frontend helper can be removed.

Risk Plan slice B8 final acceptance and closure:

- Started at: 2026-04-27 23:55:00 -04:00
- Completed at: 2026-04-27 23:55:00 -04:00
- Completed:
  - Ran focused backend acceptance/guardrail suite.
  - Ran full backend unit suite.
  - Ran frontend typecheck.
  - Ran frontend test suite and banned-name lint.
  - Marked B8 complete.
  - Updated cross-cutting status notes.
  - Added closing LEDGER entry:
    `Risk Plan slice complete — full contract shipped, no MVP`.
- Files touched:
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/api/test_risk_plan_routes.py backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/research/test_walk_forward_spine_integration.py backend/tests/unit/research/test_optimization_spine_integration.py backend/tests/unit/simulation/test_historical_replay_engine.py backend/tests/unit/simulation/test_logical_exit_spine.py backend/tests/unit/risk_resolver -q` -> 44 passed.
  - `python -m pytest backend/tests/unit -q` -> 1239 passed, 6 warnings.
  - `npm.cmd run typecheck` in `frontend/` -> passed.
  - `npm.cmd test` in `frontend/` -> 71 passed; banned-name lint clean.
- Blockers:
  - None.
- Approval status:
  - Risk Plan slice complete, full contract shipped, no MVP.

Risk Plan slice B7 save-as-draft RiskPlan endpoints:

- Started at: 2026-04-27 23:45:00 -04:00
- Completed at: 2026-04-27 23:45:00 -04:00
- Completed:
  - Added `POST /api/v1/walk-forward/runs/{run_id}/save-risk-plan`.
  - Added `POST /api/v1/optimization/runs/{run_id}/save-risk-plan`.
  - Endpoints create draft-only RiskPlans from recommendation/winner
    parameters.
  - Sources are `walk_forward_recommended` and `optimization_generated`.
  - No activation and no Account assignment occurs.
- Files touched:
  - `backend/app/api/routes/research_runs.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py -q` -> 13 passed.
  - `python -m pytest backend/tests/unit -q` -> 1239 passed, 6 warnings.
- Blockers:
  - None for B7.
- Approval status:
  - Ready for B8 acceptance/guardrail sweep.

Risk Plan slice B6 real risk evidence persistence:

- Started at: 2026-04-27 23:30:00 -04:00
- Completed at: 2026-04-27 23:30:00 -04:00
- Completed:
  - Backtest evidence asserts real selected `risk_plan_version_id`.
  - Walk-Forward evidence includes `risk_plan_id`, `risk_plan_version_id`,
    `base_risk_plan_version_id`, and recommendation base version lineage.
  - Optimization evidence includes `risk_plan_id`, `risk_plan_version_id`,
    and `base_risk_plan_version_id`.
  - Optimization candidate replays now persist RiskDecisionCards through the
    configured sink.
  - Tests verify persisted RiskDecisionCards point to real RiskPlan rows.
- Files touched:
  - `backend/app/research/walk_forward/service.py`
  - `backend/app/research/optimization/service.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `backend/tests/unit/research/test_walk_forward_spine_integration.py`
  - `backend/tests/unit/research/test_optimization_spine_integration.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/research/test_walk_forward_spine_integration.py backend/tests/unit/research/test_optimization_spine_integration.py -q` -> 14 passed.
  - `python -m pytest backend/tests/unit -q` -> 1237 passed, 6 warnings.
- Blockers:
  - None for B6.
- Approval status:
  - Ready for B7 save-as-draft RiskPlan endpoint.

Risk Plan slice B5 real RiskPlanVersion lookups:

- Started at: 2026-04-27 23:15:00 -04:00
- Completed at: 2026-04-27 23:15:00 -04:00
- Completed:
  - Added `backend/app/research/risk_plan_lookup.py`.
  - Backtest, Walk-Forward, and Optimization services now load saved
    `RiskPlanVersion` rows instead of minting synthetic RiskProfileVersion
    defaults.
  - RiskPlanVersion adapts to the legacy `RiskProfileVersion` wire shape for
    RiskResolver until the resolver signature is fully product-facing.
  - Updated Backtest/WF/Optimization tests to create real RiskPlans.
- Files touched:
  - `backend/app/research/risk_plan_lookup.py`
  - `backend/app/research/backtests/service.py`
  - `backend/app/research/walk_forward/service.py`
  - `backend/app/research/optimization/service.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `backend/tests/unit/research/test_walk_forward_spine_integration.py`
  - `backend/tests/unit/research/test_optimization_spine_integration.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/research/test_walk_forward_spine_integration.py backend/tests/unit/research/test_optimization_spine_integration.py -q` -> 14 passed.
  - `python -m pytest backend/tests/unit -q` -> 1237 passed, 6 warnings.
- Blockers:
  - None for B5.
- Approval status:
  - Ready for B6 evidence persistence verification.

Risk Plan slice B4 AI-draft route:

- Started at: 2026-04-27 23:05:00 -04:00
- Completed at: 2026-04-27 23:05:00 -04:00
- Completed:
  - Added `POST /api/v1/risk-plans/ai-draft`.
  - Consults existing AI provider catalog and requires a valid provider.
  - Returns unsaved draft `RiskPlan` plus draft `RiskPlanVersion`.
  - Forces `status=draft`, `source=ai_generated`, `ai_generated=true`,
    and populated `ai_summary`.
  - Includes warnings and boundary guardrails.
  - Does not persist, activate, or assign the draft to any Account.
- Files touched:
  - `backend/app/api/routes/risk_plans.py`
  - `backend/tests/unit/api/test_risk_plan_routes.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_risk_plan_routes.py -q` -> 5 passed.
  - `python -m pytest backend/tests/unit -q` -> 1236 passed, 6 warnings.
- Blockers:
  - None for B4.
- Approval status:
  - Ready for B5 fabrication-path removal.

Risk Plan slice B3 RiskPlan and Account default routes:

- Started at: 2026-04-27 22:50:00 -04:00
- Completed at: 2026-04-27 22:50:00 -04:00
- Completed:
  - Added `backend/app/api/routes/risk_plans.py`.
  - Registered RiskPlan routes in the FastAPI server.
  - Implemented list/create/get/patch/versions/activate/archive.
  - Implemented account default RiskPlan `GET/PUT`.
  - Enforced draft-only plan edits and explicit activation.
  - Sent Claude the route list for their leased frontend contract test.
- Files touched:
  - `backend/app/api/routes/risk_plans.py`
  - `backend/app/api/server.py`
  - `backend/tests/unit/api/test_risk_plan_routes.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_risk_plan_routes.py -q` -> 3 passed.
  - `python -m pytest backend/tests/unit -q` -> 1234 passed, 6 warnings.
- Blockers:
  - Claude currently leases `backend/tests/unit/api/test_frontend_api_contract.py`;
    Codex requested the new route entries there.
- Approval status:
  - Ready for B4 AI-draft route.

Risk Plan slice B2 SQLite persistence and Account default mapping:

- Started at: 2026-04-27 22:35:00 -04:00
- Completed at: 2026-04-27 22:35:00 -04:00
- Completed:
  - Added `risk_plans` and `risk_plan_versions` SQLite tables.
  - Added indexes for plan status, tier, source, account lookup, version
    status, fingerprint, and plan/version uniqueness.
  - Added `SQLiteRuntimeStore` save/load/list methods for RiskPlans and
    RiskPlanVersions.
  - Added `BrokerAccount.default_risk_plan_id` and
    `BrokerAccount.default_risk_plan_version_id`.
  - Added broker account migration columns and migration-safe index creation.
  - Marked B2 complete in the shared status board and notified Claude.
- Files touched:
  - `backend/app/persistence/models.py`
  - `backend/app/persistence/runtime_store.py`
  - `backend/app/broker_accounts/models.py`
  - `backend/tests/unit/persistence/test_sqlite_persistence.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/persistence/test_sqlite_persistence.py -q` -> 22 passed.
  - `python -m pytest backend/tests/unit/broker_accounts -q` -> 38 passed.
  - `python -m pytest backend/tests/unit -q` -> 1230 passed, 6 warnings.
- Blockers:
  - None for B2.
- Approval status:
  - Ready for B3 route implementation.

Risk Plan slice B1 domain contract:

- Started at: 2026-04-27 22:28:16 -04:00
- Completed at: 2026-04-27 22:28:16 -04:00
- Completed:
  - Created shared slice board at `Operations_Risk_Plan_Slice/STATUS.md`.
  - Added product-facing `RiskPlan`, `RiskPlanVersion`, and `RiskPlanConfig`
    domain models.
  - Added status, tier, source, sizing-method, and whole-share-rounding enums.
  - Added deterministic canonical config fingerprinting.
  - Added compatibility adapter from `RiskPlanVersion` to legacy
    `RiskProfileVersion` for later RiskResolver migration.
  - Marked B1 complete in the shared status board and notified Claude.
- Files touched:
  - `backend/app/domain/risk_plan.py`
  - `backend/app/domain/__init__.py`
  - `backend/tests/unit/domain/test_risk_plan_domain.py`
  - `Operations_Risk_Plan_Slice/STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/domain/test_risk_plan_domain.py backend/tests/unit/domain/test_domain_boundaries.py -q` -> 56 passed.
  - `python -m pytest backend/tests/unit -q` -> 1227 passed, 6 warnings.
- Blockers:
  - None for B1.
- Approval status:
  - Ready for B2 persistence implementation.

AI Strategy Composer review recursion and Nanyel approval:

- Started at: 2026-04-27 21:33:33 -04:00
- Completed at: 2026-04-27 21:49:31 -04:00
- Reviewers:
  - AI Architect
  - Quant Strategist
  - Fullstack Developer
  - Alpaca Engineer
  - Nanyel final approval gate
- Fixes applied:
  - Composer no longer treats RSI as a valid backtest-ready draft until the
    batch research engine can execute RSI.
  - Unsupported prompt concepts such as MACD/Bollinger now mark the draft
    `NEEDS_OPERATOR` / invalid instead of silently converting to a green-bar
    strategy.
  - Invalid preview drafts cannot be saved even if the placeholder
    StrategyVersion itself is structurally valid.
  - `minutes before close` prompts now map to
    `MINUTES_BEFORE_SESSION_CLOSE`, not generic time-in-position exits.
  - Blank explicit symbols safely fall back to `SPY` instead of producing a
    route 500.
  - Indicator tokens such as `RSI` are not inferred as tradeable symbols.
  - Composer default ExecutionStyle is broker-neutral: no default bracket and
    no default scale-out flag.
  - Feature catalog and component snapshots now use typed response contracts.
  - Added boundary guard proving Strategy Composer does not import broker,
    order, deployment, or runtime boundaries.
- Files touched:
  - `backend/app/strategy_composer/service.py`
  - `backend/app/strategy_composer/__init__.py`
  - `backend/app/api/routes/strategies.py`
  - `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`
  - `backend/tests/unit/api/test_strategy_composer_api.py`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/strategy_composer backend/tests/unit/api/test_strategy_composer_api.py backend/tests/unit/api/test_strategy_routes.py backend/tests/unit/api/test_frontend_api_contract.py -q` -> 19 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1214 passed, 6 warnings.
- Blockers:
  - None.
- Approval status:
  - Nanyel final approval: APPROVED.

## Previous Completed Action

AI Strategy Composer and Strategy Builder backend support:

- Started at: 2026-04-27 21:17:26 -04:00
- Completed at: 2026-04-27 21:28:11 -04:00
- Operator directive:
  - Backend only. Do not build frontend UI.
  - Claude should reference only `file:///C:/Users/potij/OneDrive/AI_things/mockup_review.html`
    for the desired UI after backend completion.
- Completed:
  - Added draft contracts: `StrategyDraft`, `StrategyDraftStep`,
    `StrategyDraftComponentMatch`, `StrategyDraftValidation`, and
    `StrategyDraftBacktestPlan`.
  - Added feature catalog APIs for supported features, shorthand aliases,
    feature reference validation, and `FeaturePlanPreview`.
  - Added condition builder API that validates condition trees and typed
    `LogicalExitRule` payloads.
  - Added reuse matching API for strategies, risk plans, execution styles,
    watchlists, and screeners.
  - Added AI Composer preview endpoint that turns plain English into a
    draft-only Strategy, suggested Risk Plan, Execution Style, Universe, and
    Backtest Plan.
  - Added draft save endpoint that persists only a draft StrategyVersion,
    snapshots component versions, creates no Deployment, performs no broker
    action, and makes no live-readiness claim.
  - AI Composer output is deterministic and validated against FeatureRegistry
    vocabulary before save.
- Files touched:
  - `backend/app/domain/strategy_draft.py`
  - `backend/app/domain/__init__.py`
  - `backend/app/strategy_composer/__init__.py`
  - `backend/app/strategy_composer/service.py`
  - `backend/app/api/routes/strategies.py`
  - `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`
  - `backend/tests/unit/api/test_strategy_composer_api.py`
  - `backend/tests/unit/api/test_frontend_api_contract.py`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/strategy_composer backend/tests/unit/api/test_strategy_composer_api.py backend/tests/unit/api/test_strategy_routes.py backend/tests/unit/api/test_frontend_api_contract.py -q` -> 11 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1206 passed, 6 warnings.
- Blockers:
  - None.
- Approval status:
  - Backend contracts verified. Ready for Claude UI integration.

## Previous Completed Action

Sim Lab stream visualization contract stabilization:

- Started at: 2026-04-27 15:26:01 -04:00
- Completed at: 2026-04-27 15:33:08 -04:00
- Operator directive:
  - Sim Lab streaming is for visually seeing what is happening on charts,
    not filling the screen with session rows/tables.
- Completed:
  - `WS /api/v1/research/sim_lab/stream` no longer persists
    `SimulationRunEvidence`; `POST /api/v1/research/sim_lab/runs`
    remains the durable batch/history path.
  - WebSocket no longer self-closes after `session_completed`; it stays open
    until the browser closes it, preventing reconnect loops.
  - `virtual_fill` payload now exposes flat `fill_id`, `order_id`, `symbol`,
    `side`, `qty`, and `price`.
  - `position` payload now exposes flat `symbol`, `qty`, `avg_price`,
    `realized_pnl`, `unrealized_pnl`, `open_stop`, and `open_target`.
  - `equity` payload exposes equity fields directly.
  - Notified Claude that the UI should render chart/timeline overlays from
    stream events and keep Sessions as durable batch/history only.
- Live verification:
  - Sessions before stream: 157.
  - Sessions after stream: 157.
  - Stream included bars, signal plans, virtual fills, positions, and equity.
  - First virtual fill had `side=buy`, `qty=10`, `price=101`.
  - First virtual position had `qty=10`, `avg_price=101`.
- Files touched:
  - `backend/app/research/sim_lab/service.py`
  - `backend/app/api/routes/research_runs.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py -q` -> 11 passed, 1 warning.
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/simulation/test_historical_replay_engine.py -q` -> 21 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 179 passed.
  - `python -m pytest backend/tests/unit -q` -> 1131 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
- Blockers:
  - None for C2 stream telemetry. C5 pause/step/resume backend control plane
    remains open.
- Approval status:
  - Ready for Nanyel review for C2 refinement.

Strategy freeze deployment prerequisite:

- Started at: 2026-04-27 15:17:50 -04:00
- Completed at: 2026-04-27 15:23:00 -04:00
- Operator directive:
  - Research verification may use draft StrategyVersions.
  - A StrategyVersion can only be frozen after it is attached to a Deployment.
- Completed:
  - `StrategyService.freeze_version(...)` now checks Deployment attachment
    before transitioning a draft StrategyVersion to frozen.
  - Added `DeploymentRepository.list_deployments_for_strategy_version(...)`.
  - Runtime StrategyService composition now shares the runtime DB with
    DeploymentRepository for this check.
  - Freeze route now returns 400 with
    `strategy_version can only be frozen after it is attached to a deployment`
    when the version is verification-only and undeployed.
  - Notified Claude so frontend copy/button logic does not treat Sim Lab or
    Backtest verification as a freeze trigger.
- Files touched:
  - `backend/app/deployments/persistence.py`
  - `backend/app/strategies/runtime_service.py`
  - `backend/app/strategies/service.py`
  - `backend/tests/unit/strategies/test_strategy_service.py`
  - `backend/tests/unit/api/test_strategy_routes.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/strategies/test_strategy_service.py backend/tests/unit/api/test_strategy_routes.py backend/tests/unit/deployments/test_deployment_service.py -q` -> 20 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 179 passed.
  - `python -m pytest backend/tests/unit -q` -> 1131 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
- Blockers:
  - None.
- Approval status:
  - Ready for Nanyel review for the A4 doctrine correction.

Sim Lab C2 stream mode backend:

- Started at: 2026-04-27 15:07:44 -04:00
- Completed at: 2026-04-27 15:13:00 -04:00
- Scope: add a backend WebSocket stream that emits simulator progress as
  ordered research evidence messages.
- Completed:
  - Added `SimLabStreamMessage` and
    `SimLabBatchRunService.stream_messages(...)`.
  - Added `WS /api/v1/research/sim_lab/stream`.
  - Stream emits `session_started`, `bar`, `signal_plan`,
    `virtual_fill`, `position`, `equity`, and `session_completed`.
  - SignalPlan stream payloads are explicitly `simulation_only: true` and
    retain Strategy/StrategyVersion/scenario lineage without writing broker
    truth or inventing Account state.
  - Recorded Nanyel gate C2 evidence.
- Files touched:
  - `backend/app/research/sim_lab/__init__.py`
  - `backend/app/research/sim_lab/service.py`
  - `backend/app/api/routes/research_runs.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py -q` -> 11 passed, 1 warning.
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/simulation/test_historical_replay_engine.py -q` -> 21 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 179 passed.
  - `python -m pytest backend/tests/unit -q` -> 1131 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
  - Live WebSocket smoke on `ws://127.0.0.1:8000/api/v1/research/sim_lab/stream`
    emitted first `session_started`, last `session_completed`, and included
    `bar`, `signal_plan`, `virtual_fill`, `position`, and `equity`.
- Blockers:
  - C3 remains open. Current stream converts deterministic replay candidates
    into simulation-only SignalPlan messages, but the simulator still needs a
    true Deployment -> SignalPlan runtime path before Nanyel approval for C3.
- Approval status:
  - Ready for Nanyel review for C2.

Broker order trace audit and route:

- Started at: 2026-04-27 14:48:11 -04:00
- Completed at: 2026-04-27 14:53:56 -04:00
- Scope: answer operator question whether Alpaca broker order
  `c2aade6d-805b-488d-9f7c-cf060e2b619a` can be traced to Account,
  Deployment, and SignalPlan.
- Finding:
  - The broker order maps to internal order
    `17a571ce-44e7-483f-b0a9-4b3d935be64e`.
  - Account id is `e43733eb-4d90-473b-af46-6aaac06e85f7`.
  - It is a manual operator order, so Deployment and SignalPlan lineage are
    intentionally null.
  - Manual MRNA broker position is Account-owned, but current broker position
    snapshot has null Deployment/SignalPlan/position-lineage fields.
- Completed:
  - `OrderDetail.deployment_id` now allows null for manual operator orders.
  - Added `GET /api/v1/operations/broker-orders/{broker_order_id}` to trace
    from the Alpaca id the operator sees back to internal order detail.
  - Terminal mapped broker orders now report the internal terminal status
    instead of `mapped_unknown` when they are no longer in open-order snapshots.
- Live verification:
  - `GET /api/v1/operations/broker-orders/c2aade6d-805b-488d-9f7c-cf060e2b619a`
    returned the mapped internal order, Account id, broker mapping, and filled
    status.
- Files touched:
  - `backend/app/operations/models.py`
  - `backend/app/operations/service.py`
  - `backend/app/api/routes/operations.py`
  - `backend/tests/unit/operations/test_operations_center_service.py`
  - `backend/tests/unit/api/test_operations_routes.py`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/operations/test_operations_center_service.py backend/tests/unit/api/test_operations_routes.py -q` -> 32 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 179 passed.
  - `python -m pytest backend/tests/unit -q` -> 1130 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
- Blockers:
  - Position snapshots are Account-traceable now, but manual/external broker
    positions cannot truthfully infer Deployment/SignalPlan lineage.
- Approval status:
  - Ready for Nanyel review.

Sim Lab C1 batch create-run endpoint:

- Started at: 2026-04-27 14:37:35 -04:00
- Completed at: 2026-04-27 14:41:22 -04:00
- Scope: add the requested `POST /api/v1/research/sim_lab/runs` batch route
  for a synchronous-style fixed-window Sim Lab replay.
- Completed:
  - Added `backend/app/research/sim_lab/service.py`.
  - Added `POST /api/v1/research/sim_lab/runs`.
  - The route executes the existing deterministic `HistoricalReplayEngine`,
    persists `SimulationRunEvidence`, and returns events, orders, fills,
    positions, trades, and equity curve.
  - Existing `/api/v1/sim-lab/sessions/{run_id}` can read the persisted run.
- Nanyel guardrails:
  - Research remains evidence-only.
  - No broker provider call, broker submit, Account mutation, or broker truth
    write is introduced.
- Files touched:
  - `backend/app/research/sim_lab/__init__.py`
  - `backend/app/research/sim_lab/service.py`
  - `backend/app/api/routes/research_runs.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/simulation/test_historical_replay_engine.py -q` -> 20 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 179 passed.
  - `python -m pytest backend/tests/unit -q` -> 1127 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
- Blockers:
  - C2/C3 remain open. Existing batch engine uses the historical replay
    simulation boundary; stream mode still needs explicit WebSocket control and
    stronger SignalPlan-path evidence.
- Approval status:
  - Ready for Nanyel review for C1.

Operations overview broker-open-order aggregate:

- Started at: 2026-04-27 14:30:20 -04:00
- Completed at: 2026-04-27 14:34:33 -04:00
- Scope: close the remaining mismatch after Alpaca live verification where
  Account detail and Account summaries saw broker open orders but overview
  `open_orders_count` still counted internal ledger rows only.
- Finding:
  - BrokerAdapter direct call against the stored Alpaca paper Account returned
    3 open broker orders: TSL stop-limit and two NVDA limit orders.
  - Restarting the backend loaded the patched BrokerSync polling path and
    persisted all 3 orders into Operations Account detail.
  - Overview aggregate still needed to sum Account broker-open-order counts.
- Completed:
  - `RuntimeOverview.open_orders_count` now aggregates Account summary
    broker-open-order counts.
  - Added regression coverage for an external Alpaca broker order with no
    matching internal ledger row.
  - Restarted backend on `127.0.0.1:8000`.
- Live verification:
  - `GET /api/v1/operations/accounts/e43733eb-4d90-473b-af46-6aaac06e85f7`
    returns 3 `open_broker_orders`.
  - `GET /api/v1/operations/overview` returns Account
    `open_orders_count: 3` and overview `open_orders_count: 3`.
- Files touched:
  - `backend/app/operations/service.py`
  - `backend/tests/unit/operations/test_operations_center_service.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/LOCKS.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend/tests/unit/operations/test_operations_center_service.py -q` -> 17 passed, 1 warning.
  - `python -m pytest backend/tests/unit/brokers/test_alpaca_live_adapter.py backend/tests/unit/brokers/test_broker_sync_reconciliation.py -q` -> 35 passed, 1 warning.
  - `python -m pytest backend/tests/unit -q` -> 1124 passed, 6 warnings.
  - `python -m pytest backend/tests/unit/lint -q` -> 177 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
- Blockers:
  - None.
- Approval status:
  - Ready for Nanyel review.

Account open-order polling source fix:

- Started at: 2026-04-27 14:14:25 -04:00
- Completed at: 2026-04-27 14:24:20 -04:00
- Scope: answer and fix operator report that Account open orders should not
  show zero when Alpaca has broker-side open orders.
- Finding:
  - Open orders poll from the per-Account `AlpacaBrokerAdapter` through
    `BrokerSyncService.reconcile(account_id)`.
  - `reconcile()` persists the current Account broker open-order snapshot set
    through `replace_broker_open_order_snapshots(...)`.
  - Operations reads those persisted snapshots only; it does not call Alpaca.
  - Polling was too dependent on stream startup and boot could mark a poll
    successful without a real reconcile.
  - Alpaca open-order REST calls used `get_orders()` without an explicit
    `status=open` request and then filtered out several non-terminal Alpaca
    statuses.
- Completed:
  - `AlpacaBrokerAdapter.list_open_orders(...)` now calls Alpaca with
    `GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500, nested=False)`.
  - Alpaca open-order filtering now preserves every normalized non-terminal
    status instead of a narrow allowlist.
  - Account Trade Sync starts BrokerSync REST polling before stream construction,
    so REST reconciliation still runs when the WebSocket fails to open.
  - Manual-trade bootstrap now attempts a real initial
    `BrokerSyncService.reconcile(account.id)` and no longer marks sync fresh
    without broker truth.
- Nanyel guardrails:
  - BrokerAdapter remains the broker REST read boundary.
  - BrokerSync remains the only broker truth writer.
  - Operations remains a projection of persisted broker truth.
- Files touched:
  - `backend/app/brokers/alpaca.py`
  - `backend/app/runtime/runtime_context.py`
  - `backend/tests/unit/brokers/test_alpaca_live_adapter.py`
  - `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
  - `backend/tests/unit/runtime/test_runtime_context.py`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
  - `COORDINATION/LOCKS.md`
  - `COORDINATION/LEDGER.md`
- Tests run:
  - `python -m pytest backend/tests/unit/brokers/test_alpaca_live_adapter.py backend/tests/unit/brokers/test_alpaca_broker_adapter.py backend/tests/unit/brokers/test_broker_sync_reconciliation.py backend/tests/unit/runtime/test_runtime_context.py backend/tests/unit/operations/test_operations_center_service.py -q` -> 105 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 177 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1123 passed, 6 warnings.
- Blockers:
  - Running backend must be restarted to pick up this code.
- Next action:
  - Restart backend, then inspect live `/api/v1/operations/accounts/{account_id}`
    for non-empty `open_broker_orders` when Alpaca has open orders.
- Approval status:
  - Ready for Nanyel review.

Nanyel Account Trade Sync reconciliation design recorded:

- Started at: 2026-04-27 14:14:25 -04:00
- Completed at: 2026-04-27 14:14:25 -04:00
- Scope: record the operator-approved Alpaca account truth doctrine and inform
  Claude so frontend/Operations surfaces do not treat WebSocket health as full
  Account truth.
- Decision:
  - Alpaca trade stream emits events only.
  - Alpaca REST remains required for account snapshots, full positions, and
    open-order reconciliation.
  - Account Trade Sync listens, reconnects, buffers, and reports freshness.
  - BrokerSync remains the only writer of broker-derived truth.
  - Operations must show stream state separately from REST reconciliation
    freshness.
- Roadmap update:
  - Added `Slice 11: Account Trade Sync Reconciliation Scheduler` to
    `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`.
- Files touched:
  - `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
  - `COORDINATION/INBOX_CLAUDE.md`
  - `COORDINATION/LEDGER.md`
- Tests run:
  - Not run; documentation/coordination-only design update.
- Blockers:
  - None.
- Next action:
  - Implement Slice 11 with adaptive per-Account REST reconciliation,
    Operations-visible sync profile, jitter/backoff, and tests.
- Approval status:
  - Nanyel design directive accepted for implementation planning.

Strategy backend A3/A4 authoring support:

- Started at: 2026-04-27 14:02:06 -04:00
- Completed at: 2026-04-27 14:07:44 -04:00
- Scope: close Claude's Strategy authoring backend dependency without touching
  runtime, broker, Account, or Deployment ownership.
- Completed:
  - Added `StrategyService.edit_version(...)` for draft StrategyVersion edits.
  - Added `PATCH /api/v1/strategies/{strategy_id}/versions/{version_id}`.
  - Frozen StrategyVersions reject edits with
    `strategy_version is frozen and cannot be edited`.
  - Extended `StrategyVersionRecord` with optional `frozen_by`.
  - Freeze route now persists optional `X-Operator-Session-Id` publisher
    attribution.
  - Recorded Nanyel gate A3, A4, G1, and G4 evidence in
    `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`.
- Nanyel guardrails:
  - Strategy remains reusable logic/version ownership only.
  - No Account risk, broker truth, order, or runtime state introduced.
- Files touched:
  - `backend/app/strategies/models.py`
  - `backend/app/strategies/service.py`
  - `backend/app/api/routes/strategies.py`
  - `backend/tests/unit/strategies/test_strategy_service.py`
  - `backend/tests/unit/api/test_strategy_routes.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/INBOX_CLAUDE.md`
- Tests run:
  - `python -m pytest backend/tests/unit/strategies/test_strategy_service.py backend/tests/unit/api/test_strategy_routes.py -q` -> 12 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 177 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1122 passed, 6 warnings.
- Blockers:
  - None for A3/A4 backend.
- Next action:
  - Continue the next open backend acceptance gate.
- Approval status:
  - Ready for Nanyel review for A3/A4 backend.

Backtest API B6 and Regime F1-F2 research evidence slice:

- Started at: 2026-04-27 13:55:10 -04:00
- Completed at: 2026-04-27 14:02:06 -04:00
- Scope: add deterministic regime classification and join regime evidence into
  backtest results without changing broker/account/order truth.
- Completed:
  - Added `backend/app/research/regimes/RegimeClassifier` with cached
    classification per `(symbol, timeframe, bar_window)`.
  - Backtest evidence now stamps every generated bar with
    bull/bear/sideways/volatile/trending regime labels and confidence.
  - Backtest results and metrics now include per-regime metric breakdown.
  - Recorded Nanyel gate B6, F1, and F2 evidence in
    `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`.
- Nanyel guardrails:
  - Research remains evidence-only.
  - No order, broker, Account, or runtime truth mutation.
- Files touched:
  - `backend/app/research/regimes/__init__.py`
  - `backend/app/research/regimes/classifier.py`
  - `backend/app/research/backtests/service.py`
  - `backend/app/api/routes/research_runs.py`
  - `backend/tests/unit/research/test_regime_classifier.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/INBOX_CLAUDE.md`
- Tests run:
  - `python -m pytest backend/tests/unit/research/test_regime_classifier.py backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/domain/test_research_evidence_contracts.py -q` -> 19 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 177 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1120 passed, 6 warnings.
- Blockers:
  - F3 remains open until Sim Lab and Walk-Forward join their bar series to
    regime labels.
- Next action:
  - Review Strategy backend routes for Claude's authoring frontend dependency,
    especially draft-version edit.
- Approval status:
  - Ready for Nanyel review for B6, F1, and F2.

Backtest API B1-B5 research evidence slice:

- Started at: 2026-04-27 13:50:17 -04:00
- Completed at: 2026-04-27 13:55:10 -04:00
- Scope: make `/api/v1/research/backtests` accept operator-grade create inputs
  and return durable status, results, metrics, and cost model evidence without
  creating a second runtime or broker truth writer.
- Completed:
  - Added deterministic backtest evidence service under `backend/app/research/backtests/`.
  - Extended `BacktestRun` with additive evidence fields: universe, timeframe,
    initial_capital, cost_model, status, status_history, and results.
  - Added `/api/v1/research/backtests` create/list/status/results/metrics/cancel
    routes while preserving existing `/api/v1/backtests` aliases.
  - Recorded Nanyel gate B1-B5 evidence in `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`.
- Nanyel guardrails:
  - Research produces evidence only.
  - No broker submission, broker sync write, Account mutation, or second runtime.
- Files touched:
  - `backend/app/research/__init__.py`
  - `backend/app/research/backtests/__init__.py`
  - `backend/app/research/backtests/service.py`
  - `backend/app/domain/research_evidence.py`
  - `backend/app/api/routes/research_runs.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `backend/tests/unit/domain/test_research_evidence_contracts.py`
  - `COORDINATION/NANYEL_ACCEPTANCE_GATE.md`
  - `COORDINATION/LEDGER.md`
  - `COORDINATION/INBOX_CLAUDE.md`
- Tests run:
  - `python -m pytest backend/tests/unit/api/test_research_run_routes.py backend/tests/unit/domain/test_research_evidence_contracts.py -q` -> 17 passed, 1 warning.
  - `python -m pytest backend/tests/unit/lint -q` -> 175 passed.
  - `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings.
  - `python -m pytest backend/tests/unit -q` -> 1116 passed, 6 warnings.
- Blockers:
  - None for B1-B5.
- Next action:
  - Add deterministic Regime classifier/cache and stamp per-bar/per-regime
    metrics into BacktestRun evidence for B6/F1-F4.
- Approval status:
  - Ready for Nanyel review for B1-B5; B6 remains open.

Data Center Historical Datasets — read-only inspection API + UI:

- Started at: 2026-04-26 22:15:00 -04:00
- Completed at: 2026-04-26 23:50:00 -04:00
- Scope: one reusable HistoricalDataSet mental model → many bars → many tool
  usages, with a **single** operator visual inspection surface before Chart
  Lab, Sim Lab, or backtests. Fixture-backed catalog until persistence lands.
- Completed:
  - Backend read routes under `/api/v1/data-center/...` with typed responses
    and in-memory `HistoricalBar` rows (full column contract including optional
    intraday fields on the Alpaca fixture slice).
  - Frontend route `/data-center/historical-datasets`: inventory table, selected
    dataset metadata + warnings, read-only `PriceChart` (candles + volume + VWAP
    when present), paginated raw bar grid, Radix side drawer for provider
    decision + quality report + usage history.
  - `PriceChart` gained `dataInspectionMode` using chart `priceScale` margins
    (not Chart Lab streaming semantics).
  - API contract test extended for the new GET surface; dedicated pytest module
    for list/detail/bars.
- Nanyel guardrails:
  - Read-only catalog and bars; no order placement; no broker truth writer; no
    alternate runtime root.
- Files touched:
  - `backend/app/data_center/historical_catalog.py`
  - `backend/app/data_center/__init__.py`
  - `backend/app/api/routes/data_center.py`
  - `backend/app/api/server.py`
  - `backend/tests/unit/api/test_data_center_routes.py`
  - `backend/tests/unit/api/test_frontend_api_contract.py`
  - `frontend/src/api/historicalDatasets.ts`
  - `frontend/src/api/schemas/historicalDatasets.ts`
  - `frontend/src/routes/DataCenterHistoricalDatasets.tsx`
  - `frontend/src/components/charts/PriceChart.tsx`
  - `frontend/src/router.tsx`
  - `frontend/src/components/layout/SideNav.tsx`
- Tests run:
  - `python -m pytest backend\tests\unit\api\test_data_center_routes.py backend\tests\unit\api\test_frontend_api_contract.py -q`
    -> 5 passed, 5 warnings
  - `npm.cmd run typecheck` from `frontend` -> passed
  - `npm.cmd test` from `frontend` -> 10 passed and banned-name lint clean
- Blockers:
  - None.
- Next action:
  - Persist HistoricalDataSet / HistoricalBar and wire real provider resolution
    + usage telemetry from research runs.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Research run APIs V1 completed:

- Started at: 2026-04-27 02:40:00 -04:00
- Completed at: 2026-04-27 02:58:53 -04:00
- Scope: expose the backend APIs needed by the frontend research surfaces
  without creating a second runtime or allowing research systems to trade.
- Completed:
  - Added evidence-backed research APIs:
    - `GET/POST /api/v1/backtests`
    - `GET /api/v1/backtests/{run_id}`
    - `POST /api/v1/backtests/{run_id}/cancel`
    - `GET/POST /api/v1/sim-lab/sessions`
    - `GET/DELETE /api/v1/sim-lab/sessions/{session_id}`
    - `POST /api/v1/sim-lab/sessions/{session_id}/run`
    - `GET /api/v1/sim-lab/sessions/{session_id}/results`
    - `GET/POST /api/v1/optimization/runs`
    - `GET/DELETE /api/v1/optimization/runs/{run_id}`
    - `GET/POST /api/v1/walk-forward/runs`
    - `GET/DELETE /api/v1/walk-forward/runs/{run_id}`
  - Added typed frontend API clients and schemas in `frontend/src/api`.
  - Updated API contract guard to include the research routes.
  - Hardened research evidence validation so broker/account truth fields are
    rejected even when hidden inside nested metrics.
  - Updated Production Readiness API gap matrix.
- Nanyel guardrails:
  - Research APIs persist/query evidence only.
  - No broker submit/cancel path introduced.
  - No broker truth writer introduced.
  - No alternate live/runtime root introduced.
- Files touched:
  - `backend/app/api/routes/research_runs.py`
  - `backend/app/api/server.py`
  - `backend/app/domain/research_evidence.py`
  - `backend/tests/unit/api/test_research_run_routes.py`
  - `backend/tests/unit/api/test_frontend_api_contract.py`
  - `frontend/src/api/researchRuns.ts`
  - `frontend/src/api/schemas/researchRuns.ts`
  - `Operations_Production_Readiness/API_AND_READ_MODEL_GAPS.md`
- Tests run:
  - `python -m pytest backend\tests\unit\api\test_research_run_routes.py backend\tests\unit\domain\test_research_evidence_contracts.py -q`
    -> 13 passed, 1 warning
  - `python -m pytest backend\tests\unit\api\test_research_run_routes.py backend\tests\unit\api\test_frontend_api_contract.py backend\tests\unit\api -q`
    -> 88 passed, 5 warnings
  - `python -m pytest backend\tests\unit -q`
    -> 1076 passed, 6 warnings
  - `npm.cmd run typecheck` from `frontend`
    -> passed
  - `npm.cmd test` from `frontend`
    -> 10 passed and banned-name lint clean
  - `npm.cmd run build` from `frontend`
    -> passed; Vite emitted chunk-size warning
- Blockers:
  - None.
- Next action:
  - Continue backend hardening: StrategyVersion ownership boundaries, then
    multi-leg SignalPlan/RiskResolver quantity semantics.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Platform live stock hub feed decoupled from Chart Lab config:

- Started at: 2026-04-27 02:36:00 -04:00
- Completed at: 2026-04-27 02:39:55 -04:00
- Scope: close ProdReadiness coordination ask that Dashboard showed
  `alpaca / stock / TEST` because the platform hub used ChartLabConfig during
  backend boot.
- Finding:
  - `bootstrap_streams()` resolved the platform live stock hub `data_feed`
    through `ChartLabConfig.from_env()`.
  - Chart Lab has its own one-symbol FAKEPACA/test-stream override, so that
    route was able to leak `test` into the platform live stock pipeline.
- Completed:
  - Added `_platform_live_stock_data_feed()` in
    `backend/app/runtime/runtime_context.py`.
  - Platform live stock hub now reads `alpaca_data_feed` directly from
    operator settings/env.
  - `test` is rejected as a platform live stock data feed and falls back to
    `iex` with a warning.
  - Chart Lab can still use FAKEPACA/test for its one-symbol chart stream
    without changing the platform hub identity.
- Files touched:
  - `backend/app/runtime/runtime_context.py`
  - `backend/tests/unit/runtime/test_runtime_context.py`
- Tests run:
  - `python -m pytest backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\api\test_system_streams_route.py backend\tests\unit\api\test_server_startup.py -q`
    -> 33 passed, 5 warnings
  - `python -m pytest backend\tests\unit -q`
    -> 1069 passed, 6 warnings
  - `npm.cmd test` from `frontend`
    -> 10 passed and banned-name lint clean
  - `npm.cmd run typecheck` from `frontend`
    -> passed
  - `npm.cmd run build` from `frontend`
    -> passed; Vite emitted only the existing chunk-size warning
- Blockers:
  - Running backend must be restarted so the HubRegistry boots with the new
    feed identity.
- Next action:
  - Restart backend and confirm Dashboard shows `alpaca / stock / SIP`.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Frontend API contract verification completed:

- Started at: 2026-04-27 02:31:44 -04:00
- Completed at: 2026-04-27 02:34:59 -04:00
- Scope: ensure the active `frontend/` application has backend APIs for every
  route it currently calls after the new frontend cutover.
- Completed:
  - Audited `frontend/src/api` against FastAPI registered routes.
  - Added `backend/tests/unit/api/test_frontend_api_contract.py` to lock the
    current frontend route contract.
  - Added `Operations_Production_Readiness/FRONTEND_API_CONTRACT_AUDIT.md`.
  - Updated `Operations_Production_Readiness/API_AND_READ_MODEL_GAPS.md` for
    Strategies, Watchlists, and Deployments status.
- Decision:
  - Current frontend API contract: PASS.
  - Remaining API gaps are research create-run product surfaces, not current
    frontend boot blockers: Backtests, Sim Lab, Optimization, Walk-Forward.
- Tests run:
  - `npm.cmd run typecheck` from `frontend` -> passed
  - `npm.cmd test` from `frontend` -> 10 passed and banned-name lint clean
  - `npm.cmd run build` from `frontend` -> passed; Vite emitted only the
    existing chunk-size warning
  - `python -m pytest backend\tests\unit\api -q` -> 80 passed, 5 warnings
  - `python -m pytest backend\tests\unit\api\test_frontend_api_contract.py backend\tests\unit\api -q`
    -> 82 passed, 5 warnings
- Next action:
  - Implement research run APIs using research evidence contracts and the
    unified backend computation layer. Do not create alternate runtimes.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Account Trade Sync freshness poll completed:

- Started at: 2026-04-27 02:09:34 -04:00
- Completed at: 2026-04-27 02:15:31 -04:00
- Scope: answer and fix operator report that the Account still showed stale
  data in the frontend.
- Finding:
  - The Broker Trade Update Stream was no longer lazy; it starts at backend
    boot and after Account creation.
  - The stale badge was caused by BrokerSync freshness aging out after quiet
    periods with no broker trade events.
- Completed:
  - `TradeEventDispatcher` now starts a BrokerSync polling loop when the
    per-Account stream opens.
  - The poll loop calls BrokerSyncService reconciliation on a cadence below
    the stale threshold, so quiet Accounts stay fresh when broker truth can be
    reached.
  - Broker events still route through BrokerSync before fan-out.
  - No broker truth writer was added outside BrokerSync.
- Files touched in this iteration:
  - `backend/app/runtime/runtime_context.py`
  - `backend/tests/unit/runtime/test_runtime_context.py`
- Tests run:
  - `python -m pytest backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\api\test_system_streams_route.py backend\tests\unit\brokers\test_broker_sync_reconciliation.py -q`
    -> 52 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    -> 1066 passed, 6 warnings
  - `npm.cmd test` from `new-frontend`
    -> 10 passed and banned-name lint clean
- Blockers:
  - The running backend process must be restarted to pick up this runtime
    singleton change.
- Next action:
  - Restart backend and verify the Account card changes from stale to fresh
    after the first BrokerSync poll.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Market-data pipeline identity correction completed:

- Started at: 2026-04-27 01:54:53 -04:00
- Completed at: 2026-04-27 02:09:34 -04:00
- Scope: enforce Nanyel clarification that market-data pipelines are asset
  pipelines (`stock`, `crypto`, `option`, etc.), while paper/live are Account
  metadata only and drive broker API endpoints.
- Completed:
  - Replaced market-data pipeline `trading_mode` identity with
    `asset_class`.
  - Kept the backend startup hub keyed as the shared `stock` pipeline.
  - Updated Operations stream projection and both frontend stream displays to
    show asset class instead of paper/live mode.
  - Preserved `TradingMode` only where it belongs: Broker Account metadata and
    broker adapter endpoint selection.
  - Fixed Chart Lab `new-frontend` typecheck by normalizing incoming bar
    `timeframe`.
- Files touched in this iteration:
  - `backend/app/market_data/pipeline.py`
  - `backend/app/market_data/pipeline_registry.py`
  - `backend/app/market_data/__init__.py`
  - `backend/app/api/routes/market_data.py`
  - `backend/app/api/routes/system_streams.py`
  - `backend/app/runtime/runtime_context.py`
  - `backend/tests/unit/market_data/test_pipeline_registry.py`
  - `backend/tests/unit/api/test_system_streams_route.py`
  - `new-frontend/src/api/schemas/system.ts`
  - `new-frontend/src/routes/Operations.tsx`
  - `new-frontend/src/routes/Dashboard.tsx`
  - `new-frontend/src/routes/ChartLab.tsx`
  - `frontend/src/systemStreams.js`
- Tests run:
  - `python -m pytest backend\tests\unit\market_data backend\tests\unit\api\test_system_streams_route.py backend\tests\unit\api\test_market_data_delete_route.py backend\tests\unit\runtime\test_runtime_context.py -q`
    -> 148 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    -> 1065 passed, 6 warnings
  - `npm.cmd test` from `frontend`
    -> 42 passed and frontend check passed for 29 files
  - `npm.cmd test` from `new-frontend`
    -> 10 passed and banned-name lint clean
  - `npm.cmd run typecheck` from `new-frontend`
    -> passed
  - `npm.cmd run build` from `new-frontend`
    -> passed; Vite emitted only the existing chunk-size warning
- Blockers:
  - None for this slice.
- Next action:
  - Continue Promotion/Program migration shim review and keep removing active
    product language that implies a second runtime.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Automatic market-data and Account trade-sync startup completed:

- Started at: 2026-04-27 01:23:51 -04:00
- Completed at: 2026-04-27 01:39:07 -04:00
- Scope: ensure the shared Live Stock Market Data Stream starts when the
  backend starts from the operator-configured Alpaca data provider, and ensure
  Broker Trade Update Streams/BrokerSync are running for every configured
  Alpaca Account.
- Nanyel rule:
  - One shared live stock market-data stream.
  - One Broker Trade Update Stream per Account.
  - BrokerSync is ready before broker events can arrive.
  - Front-end configured provider credentials must survive restart; no hidden
    env-only dependency for configured Market Data Providers.
- Completed:
  - FastAPI startup now builds per-account BrokerSync/manual-trade composition
    before opening streams.
  - Broker Account creation and credential replacement wire the per-account
    BrokerSync/manual stack before starting or refreshing that Account's trade
    stream.
  - Market Data Provider credentials are now stored encrypted-at-rest in
    `market_data_credentials.enc`.
  - Market Data catalog exposes `get_credentials(service_id)` and deletes
    stored credentials when the provider is deleted.
  - The shared market-data hub factory reads credentials from the configured
    default Alpaca provider before falling back to env vars.
  - Chart Lab health now treats a configured Alpaca provider with stored
    credentials as stream-capable even without `ALPACA_API_KEY` in env.
  - System Streams empty-state copy now says the market-data pipeline should
    start automatically at backend boot.
- Files touched in this iteration:
  - `backend/app/api/server.py`
  - `backend/app/api/routes/broker_accounts.py`
  - `backend/app/api/routes/chart_lab.py`
  - `backend/app/market_data/alpaca.py`
  - `backend/app/market_data/catalog.py`
  - `backend/app/market_data/credential_store.py`
  - `backend/app/market_data/runtime.py`
  - `backend/app/market_data/__init__.py`
  - `backend/app/runtime/runtime_context.py`
  - `frontend/src/systemStreams.js`
  - related API, runtime, market-data, and frontend tests.
- Tests run:
  - `python -m pytest backend\tests\unit\market_data backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\api\test_broker_accounts_routes.py backend\tests\unit\api\test_server_startup.py backend\tests\unit\api\test_system_streams_route.py -q`
    -> 157 passed, 5 warnings
  - `python -m pytest backend\tests\unit\brokers backend\tests\unit\api\test_operations_trade_stream_route.py -q`
    -> 113 passed, 1 warning
  - `python -m pytest backend\tests\unit\api\test_chart_lab_route.py backend\tests\unit\market_data\test_market_data_catalog.py backend\tests\unit\runtime\test_runtime_context.py -q`
    -> 53 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    -> 1024 passed, 6 warnings
  - `python -m pytest backend\tests\smoke -q`
    -> 6 passed, 1 warning
  - `npm.cmd test` from `frontend`
    -> 42 passed and frontend check passed for 29 files
- Blockers:
  - None for this slice.
- Next action:
  - Continue with Promotion/Program migration shim review, unless Nanyel wants
    a live Operations Center verification pass first.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

Reusable deployment components rename completed:

- Started at: 2026-04-27 01:13:18 -04:00
- Completed at: 2026-04-27 01:23:51 -04:00
- Scope: encode Nanyel clarification that StrategyVersion and Universe are
  reusable components selected by Deployment, not risk owners and not runtime
  roots.
- Nanyel rule:
  - StrategyVersion owns reusable trading logic/version identity.
  - Universe/Watchlist owns reusable eligible-symbol evidence.
  - Risk remains separate from both and is resolved for each Account by
    RiskResolver.
  - Deployment selects reusable components and emits SignalPlans.
- Completed:
  - Renamed active `ResolvedProgramComponents` to
    `ResolvedDeploymentComponents`.
  - `FeaturePlan` now carries `strategy_version_id`; legacy
    `program_version_id` is migration-only input.
  - Chart Lab and Sim Lab now use `components.strategy.id` for research session
    construction.
  - Runtime, pipeline, smoke, and paper tooling no longer use
    `components.program`.
  - Added component boundary validation that rejects risk ownership leaking into
    StrategyVersion or Universe.
- Files touched in this iteration:
  - `backend/app/features/planner.py`
  - `backend/app/features/__init__.py`
  - `backend/app/chart_lab/preview_service.py`
  - `backend/app/simulation/historical_replay.py`
  - `backend/app/domain/simulation.py`
  - `backend/app/pipeline/orchestrator.py`
  - `backend/app/runtime/broker_runtime_orchestrator.py`
  - `tools/run_paper_runtime.py`
  - `tools/run_paper_runtime_dry_run.py`
  - related feature, chart-lab, simulation, pipeline, runtime, smoke, and tool
    tests.
- Tests run:
  - `python -m pytest backend\tests\unit\features backend\tests\unit\chart_lab backend\tests\unit\simulation backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\runtime backend\tests\unit\tools\test_paper_operator_tools.py -q`
    -> 296 passed, 2 warnings
  - `python -m pytest backend\tests\unit\domain\test_domain_boundaries.py -q`
    -> 38 passed
  - `python -m pytest backend\tests\unit -q`
    -> 1017 passed, 6 warnings
  - `python -m pytest backend\tests\smoke -q`
    -> 6 passed, 1 warning
- Scans:
  - No active `ResolvedProgramComponents` or `components.program` references in
    `backend/app`, `tools`, or `backend/tests`.
  - StrategyVersion and Universe risk-owner scan is clean except migration
    validation text in `backend/app/features/planner.py`.
- Blockers:
  - None for this slice.
- Next action:
  - Review remaining `ProgramVersion` surfaces in promotion/domain as explicit
    migration shims or rename them to Strategy readiness/promotion contracts.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

StrategyVersion runtime rename and risk ownership iteration completed:

- Started at: 2026-04-27 01:07:46 -04:00
- Completed at: 2026-04-27 01:13:18 -04:00
- Scope: finish collapsing ProgramVersion language into StrategyVersion where it
  touches runtime and Operations, while preserving the rule that StrategyVersion
  does not own Account risk.
- Nanyel rule:
  - StrategyVersion owns reusable trading logic/version identity.
  - Account/RiskResolver owns final Account-specific risk and sizing.
  - Program is not an active product/runtime concept.
- Completed:
  - Runtime `DeploymentContext` now exposes `strategy_version_id` and
    `strategy_version` instead of active `ProgramVersion` ownership.
  - Operations deployment/order projections now use `strategy_version_id` and
    `strategy_version`.
  - Runtime state uses `signal_plan_count` and `last_signal_plan_timestamp`
    instead of active ExecutionIntent labels.
  - StrategyVersion domain guardrail test now rejects risk, sizing,
    buying-power, and broker-account ownership fields.
  - Legacy persisted runtime state keys are migration-only compatibility input.
- Files touched in this iteration:
  - `backend/app/runtime/models.py`
  - `backend/app/runtime/broker_runtime_orchestrator.py`
  - `backend/app/operations/models.py`
  - `backend/app/operations/service.py`
  - `backend/tests/unit/operations/test_operations_center_service.py`
  - `backend/tests/unit/api/test_operations_routes.py`
  - `backend/tests/unit/domain/test_domain_boundaries.py`
  - `backend/tests/unit/persistence/test_sqlite_persistence.py`
- Tests run:
  - `python -m pytest backend\tests\unit\operations backend\tests\unit\api\test_operations_routes.py backend\tests\unit\runtime -q`
    -> 88 passed, 2 warnings
  - `python -m pytest backend\tests\unit\domain\test_domain_boundaries.py -q`
    -> 38 passed
  - `python -m pytest backend\tests\unit\runtime backend\tests\unit\operations backend\tests\unit\api\test_operations_routes.py backend\tests\unit\persistence\test_sqlite_persistence.py backend\tests\unit\domain\test_domain_boundaries.py -q`
    -> 145 passed, 2 warnings
  - `python -m pytest backend\tests\unit -q`
    -> 1017 passed, 6 warnings
  - `python -m pytest backend\tests\smoke -q`
    -> 6 passed, 1 warning
- Blockers:
  - None for this slice.
- Next action:
  - Rename `ResolvedProgramComponents` and remaining paper runtime tooling away
    from Program language without moving risk ownership into StrategyVersion.
- Approval status:
  - Ready for Nanyel review.

Previous completed action:

ExecutionIntent compatibility removal iteration started:

- Started at: 2026-04-27 00:48:59 -04:00
- Scope: remove remaining active `ExecutionIntent` compatibility surfaces from
  runtime/pipeline results and protective order paths.
- Nanyel rule:
  - No `ExecutionIntent` as forward runtime spine.
  - No hidden compatibility surface where SignalPlan can be bypassed.
- Current scan:
  - `ExecutionIntent` remains in runtime models, pipeline result models,
    protective compatibility paths, paper smoke tooling, and tests.
  - `Program` shims remain broader and will be addressed after the
    ExecutionIntent surface is eliminated.
- First action: replace protective `ExecutionIntent` route with a SignalPlan
  route, then remove `execution_intents` from `PipelineResult`.

Previous completed action:

Nanyel deviation correction iteration completed:

- Started at: 2026-04-27 00:27:05 -04:00
- Completed at: 2026-04-27 00:45:21 -04:00
- Scope: backend-only correction until Nanyel approval.
- Governing standard:
  - `AGENTS.md` Nanyel Coordinator / Evaluator / Approver standard.
  - `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`.
- Audit artifact:
  `Operations_Turtle_Shell_Artifacts/NANYEL_DEVIATION_CORRECTION_AUDIT.md`
- Completed:
  - Removed the legacy runtime engine implementation and export.
  - Rewired paper dry-run tooling to use the single RuntimeOrchestrator path.
  - Stopped the entry runtime from building `ExecutionIntent` before
    RiskResolver.
  - Added `RiskResolver.lifecycle_sizing_from_risk_profile(...)` so Account
    quantity begins behind RiskResolver.
  - Runtime entry flow now evaluates Governor from SignalPlan.
  - Wired close/logical_exit to cancel superseded passive position-management
    orders before submitting the exit order.
  - Attached BrokerAdapter and BrokerSync to OrderManager in the runtime
    composition root.
  - Runtime and manual preflight rejection now update internal ledger advisory
    truth directly instead of writing through BrokerSync.
  - Runtime preflight buying power now reads BrokerSyncService latest Account
    snapshot.
  - Manual preflight uses configured Broker Account snapshot and fails closed
    without direct broker snapshot fetch.
  - Deployment exit management now blocks same-Account multiple active lineage
    ambiguity instead of overwriting by account id.
- Nanyel decision:
  - Approved for this correction slice.
  - Full platform approval still requires later removal of Program and
    ExecutionIntent migration shims across research, chart, simulation,
    promotion, operations, and compatibility surfaces.
- Files touched:
  - `backend/app/risk_resolver/service.py`
  - `backend/app/risk_resolver/__init__.py`
  - `backend/app/pipeline/orchestrator.py`
  - `backend/app/orders/manager.py`
  - `backend/app/api/routes/manual_trade.py`
  - `backend/app/runtime/__init__.py`
  - `backend/app/runtime/recovery_orchestrator.py`
  - `tools/run_paper_runtime_dry_run.py`
  - `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
  - `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
  - `backend/tests/unit/runtime/test_recovery_orchestrator.py`
  - `backend/tests/unit/orders/test_order_manager.py`
  - `backend/tests/unit/tools/test_paper_operator_tools.py`
  - `backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py`
  - `backend/tests/smoke/test_paper_runtime_smoke.py`
  - `Operations_Turtle_Shell_Artifacts/NANYEL_DEVIATION_CORRECTION_AUDIT.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Files removed:
  - `backend/app/runtime/engine.py`
  - `backend/tests/unit/runtime/test_runtime_engine.py`
- Tests run:
  - `python -m pytest backend\tests\unit\risk_resolver backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py -q`
    result: 39 passed, 1 warning
  - `python -m pytest backend\tests\unit\orders\test_order_manager.py backend\tests\unit\pipeline\test_runtime_orchestrator.py -q`
    result: 76 passed, 1 warning
  - `python -m pytest backend\tests\unit\api\test_manual_trade_preflight.py backend\tests\unit\api\test_broker_accounts_routes.py -q`
    result: 8 passed, 1 warning
  - `python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\api\test_manual_trade_preflight.py backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py -q`
    result: 151 passed, 2 warnings
  - `python -m pytest backend\tests\unit\tools\test_paper_operator_tools.py -q`
    result: 18 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    result: 1006 passed, 6 warnings
  - `python -m pytest backend\tests\smoke -q`
    result: 6 passed, 1 warning
- Blockers: none for this correction slice.
- Remaining risks:
  - Program/ExecutionIntent migration shims still exist outside the corrected
    forward entry runtime path.
  - Automatic lifecycle child-leg live submission remains gated until
    leg-specific order shapes and activation sequencing are safe.
- Approval status: Nanyel approved this correction slice.
- Next action:
  `Create and execute Program/ExecutionIntent migration-shim removal plan.`

Previous completed action:

Alpaca multi-leg capability and pending-exit priority review completed:

- Started at: 2026-04-27 00:11:57 -04:00
- Completed at: 2026-04-27 00:20:31 -04:00
- Scope: backend broker capability, lifecycle order priority, and safe
  multi-leg submission gates.
- Coordination note: requested `Nanyel` skill is not installed in this session;
  Coordinator carried that role directly.
- Audit artifact:
  `Operations_Turtle_Shell_Artifacts/ALPACA_MULTILEG_AND_PENDING_EXIT_PRIORITY_AUDIT.md`
- Completed:
  - Added explicit broker-native multi-leg unsupported violation code.
  - Added preflight fields for native multi-leg request and leg counts.
  - Rejected broker-native multi-target bracket requests with operator advisory.
  - Rejected runner behavior as a broker-native multi-leg concept.
  - Preserved multiple targets, stops, runner, and logical exits as internal
    SignalPlan lifecycle legs.
  - Added position-management priority rules.
  - Added helpers to find pending position-management orders.
  - Added helpers to find passive orders superseded by close/logical_exit.
  - Ran Alpaca Agent, Angry Architect, and seasoned trader review cycle.
- Specialist verdict:
  - Contract and ledger boundary are approved.
  - Automatic live submission of lifecycle child legs is not approved yet.
  - Runtime must still wire cancel/replace sequencing, leg-specific order
    shapes, BrokerSync-confirmed quantity caps, and same-symbol lineage
    ambiguity blocking before multi-leg live submission.
- Files touched:
  - `backend/app/brokers/capabilities.py`
  - `backend/app/brokers/preflight.py`
  - `backend/app/orders/manager.py`
  - `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
  - `backend/tests/unit/orders/test_order_manager.py`
  - `Operations_Turtle_Shell_Artifacts/ALPACA_MULTILEG_AND_PENDING_EXIT_PRIORITY_AUDIT.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend\tests\unit\brokers\test_alpaca_preflight_service.py backend\tests\unit\orders\test_order_manager.py -q`
    result: 54 passed, 1 warning
  - `python -m pytest backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\pipeline -q`
    result: 188 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    result: 1010 passed, 6 warnings
- Blockers: none for this contract slice.
- Approval status: coordinator approved for contract and ledger boundary only;
  live multi-leg auto-submission remains blocked until the next execution
  choreography slice.
- Next action:
  `Runtime cancel/replace and lifecycle leg activation plan.`

Previous completed action:

SignalPlan leg allocation and lifecycle quantity semantics completed:

- Started at: 2026-04-27 00:03:00 -04:00
- Completed at: 2026-04-27 00:09:35 -04:00
- Scope: backend contracts and RiskResolver allocation semantics.
- Audit artifact:
  `Operations_Turtle_Shell_Artifacts/SIGNALPLAN_LEG_ALLOCATION_AUDIT.md`
- Doctrine:
  - One SignalPlan is one lifecycle trade idea.
  - Targets, stops, runner, and logical exits are lifecycle legs, not separate
    trade ideas.
  - RiskResolver evaluates total Account risk first, then assigns quantities to
    lifecycle legs.
  - Fractional vs whole-share support is Account/Broker capability metadata and
    must be explicit in allocation.
  - Whole-share allocation must never exceed total resolved quantity.
- Completed:
  - Added `RiskResolvedLegAllocation`.
  - Added `RiskResolverResult.leg_allocations`.
  - Added `RiskResolverResult.fractional_quantity_allowed`.
  - Added `RiskResolverResult.quantity_rounding_policy`.
  - Added `LifecycleSizingInput`.
  - Added `RiskResolver.resolve_lifecycle(...)`.
  - Runtime opening SignalPlans now use lifecycle risk resolution.
  - Added `OrderManager.create_signal_plan_leg_orders(...)`.
  - Fractional allocation preserves exact target/runner quantities.
  - Whole-share allocation floors targets and assigns remainder to runner.
- Files touched:
  - `backend/app/domain/signal_plan.py`
  - `backend/app/domain/__init__.py`
  - `backend/app/risk_resolver/service.py`
  - `backend/app/risk_resolver/__init__.py`
  - `backend/app/orders/manager.py`
  - `backend/app/pipeline/orchestrator.py`
  - `backend/tests/unit/risk_resolver/test_risk_resolver_contract.py`
  - `backend/tests/unit/domain/test_signal_plan_contracts.py`
  - `backend/tests/unit/orders/test_order_manager.py`
  - `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
  - `Operations_Turtle_Shell_Artifacts/SIGNALPLAN_LEG_ALLOCATION_AUDIT.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend\tests\unit\risk_resolver backend\tests\unit\domain\test_signal_plan_contracts.py -q`
    result: 20 passed
  - `python -m pytest backend\tests\unit\orders\test_order_manager.py -q`
    result: 38 passed, 1 warning
  - `python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py -q`
    result: 33 passed, 1 warning
  - `python -m pytest backend\tests\unit\risk_resolver backend\tests\unit\domain\test_signal_plan_contracts.py backend\tests\unit\orders backend\tests\unit\pipeline\test_runtime_orchestrator.py -q`
    result: 100 passed, 1 warning
  - `python -m pytest backend\tests\unit\runtime backend\tests\unit\decision backend\tests\unit\persistence -q`
    result: 102 passed, 2 warnings
  - `python -m pytest backend\tests\unit -q`
    result: 1006 passed, 6 warnings
- Blockers: none.
- Approval status: coordinator approved for this slice.
- Remaining risks:
  - Pending exit exposure must be reconciled before automatic child-leg
    submission.
  - Broker-native bracket/OCO support needs a dedicated Alpaca capability slice.
  - Same-symbol multiple active lineages on one Account need ambiguity handling.
  - Runtime records lifecycle allocations in Account Evaluation; automatic
    child-leg broker submission remains gated until priority and broker
    bracket/OCO semantics are finalized.

Previous completed action:

Position management order semantics completed:

- Started at: 2026-04-26 23:37:35 -04:00
- Completed at: 2026-04-26 23:46:24 -04:00
- Scope: backend order semantics with operator-facing clarity review.
- Audit artifact:
  `Operations_Turtle_Shell_Artifacts/POSITION_MANAGEMENT_ORDER_SEMANTICS_AUDIT.md`
- Support roles engaged and reviewed:
  - Alpaca Agent
  - Seasoned Quant Trader
  - Full Backend Engineer
  - Front End Experience Designer / Fullstack Engineer
- Architectural review: approved for this slice.
- Completed:
  - Defined `SignalPlan.side` as position bias and `InternalOrder.side` as
    broker action.
  - Long position-management orders now produce broker sell action.
  - Short position-management orders now produce broker buy action.
  - `OrderManager.create_signal_plan_order(...)` now accepts Account-specific
    `position_side` and `opening_signal_plan_id`.
  - Position-management SignalPlan orders now require real opening SignalPlan
    lineage.
  - Legacy `OrderManager.create_order(...)` now inverts side for non-open
    ExecutionIntent exits.
  - Deployment runtime passes Account-specific position side, position lineage,
    and opening SignalPlan lineage.
  - Protective `process_protective_intent(...)` now uses active Account-owned
    Position lineage or creates no order.
  - Governor protective bypass now includes close, reduce, target, stop, trail,
    breakeven, runner, logical_exit, tp, sl, and scale.
  - Broker and market preflight now carry `is_position_management` so a
    sell-to-close long exit is not treated as a new short.
- Files touched:
  - `backend/app/orders/manager.py`
  - `backend/app/brokers/capabilities.py`
  - `backend/app/brokers/preflight.py`
  - `backend/app/governor/service.py`
  - `backend/app/pipeline/orchestrator.py`
  - `backend/tests/unit/orders/test_order_manager.py`
  - `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
  - `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
  - `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
  - `backend/tests/unit/governor/test_portfolio_governor.py`
  - `Operations_Turtle_Shell_Artifacts/POSITION_MANAGEMENT_ORDER_SEMANTICS_AUDIT.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend\tests\unit\orders\test_order_manager.py -q`
    result: 37 passed, 1 warning
  - `python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py -q`
    result: 33 passed, 1 warning
  - `python -m pytest backend\tests\unit\brokers\test_alpaca_broker_adapter.py backend\tests\unit\brokers\test_alpaca_preflight_service.py -q`
    result: 34 passed, 1 warning
  - `python -m pytest backend\tests\unit\governor\test_portfolio_governor.py -q`
    result: 26 passed, 1 warning
  - `python -m pytest backend\tests\unit\runtime -q`
    result: 69 passed, 2 warnings
  - `python -m pytest backend\tests\unit\decision -q`
    result: 10 passed
  - `python -m pytest backend\tests\unit\orders -q`
    result: 46 passed, 1 warning
  - `python -m pytest backend\tests\unit\persistence -q`
    result: 23 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    result: 1002 passed, 6 warnings
- Blockers: none.
- Approval status: coordinator approved after specialist and architecture review.
- Remaining risks:
  - Manual operator close/reduce side semantics still need an operator-flow
    review because manual side is currently broker action.
  - RiskResolver still needs lifecycle quantity semantics for reduce/target/
    runner and pending-exit exposure caps.
  - Same-symbol multiple active lineages on one Account still need stronger
    lineage selection or ambiguity blocking.

Previous completed action:

DeploymentPositionManager runtime model completed:

- Started at: 2026-04-26 23:18:03 -04:00
- Completed at: 2026-04-26 23:32:44 -04:00
- Scope: backend runtime model only.
- Audit artifact:
  `Operations_Turtle_Shell_Artifacts/DEPLOYMENT_POSITION_MANAGER_AUDIT.md`
- Completed:
  - Added nullable Position lineage fields to `BrokerPositionSnapshot`.
  - Added `SQLiteRuntimeStore.list_broker_position_snapshots_by_deployment(...)`.
  - Added runtime-only `DeploymentPositionManager`.
  - Updated Deployment runtime so Watchlist/Universe gates entries.
  - Updated Deployment runtime so Account-owned Positions scoped by
    `deployment_id` drive exit / management SignalPlans.
  - Preserved independent Account evaluation:
    Account with Position acts; closed or missing Position ignores.
  - Ensured symbols removed from Watchlist can still be evaluated for exits.
  - Preserved BrokerAdapter submission boundary and BrokerSync truth boundary.
- Files touched:
  - `backend/app/brokers/models.py`
  - `backend/app/persistence/runtime_store.py`
  - `backend/app/pipeline/orchestrator.py`
  - `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
  - `backend/tests/unit/persistence/test_sqlite_persistence.py`
  - `Operations_Turtle_Shell_Artifacts/DEPLOYMENT_POSITION_MANAGER_AUDIT.md`
  - `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- Tests run:
  - `python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py -q`
    result: 31 passed, 1 warning
  - `python -m pytest backend\tests\unit\persistence\test_sqlite_persistence.py -q`
    result: 19 passed, 1 warning
  - `python -m pytest backend\tests\unit\runtime -q`
    result: 69 passed, 2 warnings
  - `python -m pytest backend\tests\unit\decision -q`
    result: 10 passed
  - `python -m pytest backend\tests\unit\orders -q`
    result: 33 passed, 1 warning
  - `python -m pytest backend\tests\unit\persistence -q`
    result: 23 passed, 1 warning
  - `python -m pytest backend\tests\unit -q`
    result: 973 passed, 6 warnings
- Blockers: none.
- Approval status: coordinator approved for this slice.
- Remaining risks:
  - Protective `process_protective_intent(...)` remains a compatibility shim.
  - Exit order side semantics need a future broker-facing review for long and
    short close/reduce direction.

Previous completed action:

Chart Lab FAKEPACA issue fixed:

- Root cause: Chart Lab was in Auto mode and an Alpaca Market Data provider
  role was tagged for `Test streaming`, so provider roles forced the
  `FAKEPACA` synthetic stream.
- System settings already had `alpaca_use_test_stream=false`, `alpaca_data_feed=sip`,
  and default symbol `SPY`, but Auto mode allowed the provider test role to win.
- Set `chart_lab_one_symbol_fakepaca=false` to pin Chart Lab to live symbols.
- Verified clean backend on `8001` reports:

```text
test_stream=false
default_symbol=SPY
data_feed=sip
```

- Started a fresh frontend at `http://127.0.0.1:5176` with
  `VITE_API_BASE=http://127.0.0.1:8001` so it does not hit stale port `8000`
  listeners.

Clean Chart Lab URL:

```text
http://127.0.0.1:5176/chart_lab.html
```

Previous completed action:

Operations Center stream/status cleanup completed:

- Ready deployments now render under `Ready / idle deployments` instead of
  disappearing when no Deployment is active.
- Live stock market-data streams now project as `mode_neutral` from the API.
- The Streams UI no longer shows paper/live mode on Market Data Pipelines.
- A running Broker Trade Update Stream is no longer marked stale only because
  there have been no recent order/fill events.
- Quiet trade streams now show an idle note instead of an alarm.
- Existing stale BrokerSync remains a real warning in Operations Center.

Validation:

```text
Test run: 2026-04-26 23:10:40 -04:00
Command: python -m pytest backend\tests\unit\api\test_system_streams_route.py -q
Result: 3 passed, 1 warning

Test run: 2026-04-26 23:10:40 -04:00
Command: npm.cmd test
Result: 42 passed; frontend check passed for 29 files
```

Runtime note:

```text
Old backend listeners on port 8000 were still serving stale route code and
Windows did not release them cleanly. A clean fixed backend was started on
8001 and a clean frontend was started on 5175 pointing to it.
```

Clean URLs:

```text
Frontend: http://127.0.0.1:5175/
Backend:  http://127.0.0.1:8001/
```

Previous completed action:

Frontend dev server restart completed:

- Stopped duplicate project Vite/uvicorn dev processes.
- Started backend API at `http://127.0.0.1:8000`.
- Started frontend Vite dev server at `http://127.0.0.1:5173`.
- Confirmed frontend HTML returns `200`.
- Confirmed served `src/main.js` returns `200` and no duplicate
  `createSystemSettingsApi` import is present.
- Confirmed Vite proxy to `/api/v1/operations/overview` returns `200`.
- Confirmed direct backend `/api/v1/system/status` returns `200` and reports
  Alpaca paper endpoint: `https://paper-api.alpaca.markets`.

Next operator action:

```text
Open or hard-refresh http://127.0.0.1:5173/
```

Previous completed action:

Operations Center loading issue fixed:

- Frontend root cause: `frontend/src/main.js` imported
  `createSystemSettingsApi` twice. ES module parsing failed before the
  Operations Center could mount, leaving the static `index.html` loading
  placeholder visible.
- Backend root cause: existing SQLite runtime databases could fail opening
  before migration because SignalPlan lineage indexes were created before old
  `internal_orders` tables had the new lineage columns.
- Fixed frontend duplicate import.
- Moved SignalPlan lineage indexes to the migration-safe path and added a
  regression test for existing `internal_orders` tables.
- Confirmed `/api/v1/operations/overview` returns `200`.

Test runs:

```text
Test run: 2026-04-26 23:18:06 -04:00
Command: python -m pytest backend\tests\unit\persistence\test_sqlite_persistence.py backend\tests\unit\api\test_operations_routes.py -q
Result: 30 passed, 1 warning

Test run: 2026-04-26 23:19:11 -04:00
Command: npm.cmd test
Result: 41 passed; frontend check passed for 29 files

Test run: 2026-04-26 23:19:11 -04:00
Command: TestClient GET /api/v1/operations/overview
Result: 200

Test run: 2026-04-26 23:21:35 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 964 passed, 6 warnings
```

Files touched:

- `frontend/src/main.js`
- `backend/app/persistence/models.py`
- `backend/tests/unit/persistence/test_sqlite_persistence.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Restart the frontend dev server and backend API process if they are already
running, then reload the Operations Center page. The static loading placeholder
should be replaced by the mounted Operations Center overview.
```

Approval status:

```text
Approved for Operations Center loading fix.
```

Previous completed action:

Operator requested steps 1 through 4 completed:

- Opt-in Alpaca FAKEPACA stream check passed.
- Real Alpaca paper checks were attempted with opt-in flags and skipped because
  `ALPACA_BASE_URL` is not set to `https://paper-api.alpaca.markets`.
- Chart Lab preview now emits and optionally records `ChartLabPreviewEvidence`
  through a research evidence recorder boundary.
- Sim Lab historical replay now emits and optionally records
  `SimulationRunEvidence` through a research evidence recorder boundary.
- Operations service now lists and loads detailed research evidence.
- Operations API now exposes read-only research evidence list/detail routes.
- Day-zero unit, smoke, and integration gates passed.

Guardrail correction:

```text
An initial Sim Lab evidence sink name violated the no-runtime-persistence
guardrail. It was corrected to a research evidence recorder boundary before
approval.
```

Test runs:

```text
Test run: 2026-04-26 23:05:52 -04:00
Command: python -m pytest backend\tests\unit\chart_lab backend\tests\unit\simulation backend\tests\unit\operations backend\tests\unit\api\test_operations_routes.py backend\tests\unit\persistence\test_sqlite_persistence.py -q
Result: 59 passed, 1 warning

Test run: 2026-04-26 23:07:18 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 963 passed, 6 warnings

Test run: 2026-04-26 23:08:09 -04:00
Command: python -m pytest backend\tests\smoke -q
Result: 6 passed, 1 warning

Test run: 2026-04-26 23:08:16 -04:00
Command: python -m pytest backend\tests\integration -q -rs
Result: 27 passed, 3 skipped, 1 warning

Test run: 2026-04-26 23:08:44 -04:00
Command: RUN_ALPACA_FAKEPACA_STREAM=1 RUN_ALPACA_PAPER_INTEGRATION=1 RUN_ALPACA_PAPER_CRYPTO_STREAM=1 python -m pytest backend\tests\integration\test_alpaca_fakepaca_stream.py backend\tests\integration\test_alpaca_paper_integration.py backend\tests\integration\test_alpaca_paper_crypto_stream.py -q -rs
Result: 1 passed, 2 skipped, 2 warnings
```

Files touched:

- `backend/app/chart_lab/preview_service.py`
- `backend/app/simulation/models.py`
- `backend/app/simulation/historical_replay.py`
- `backend/app/operations/service.py`
- `backend/app/api/routes/operations.py`
- `backend/tests/unit/chart_lab/test_chart_lab_preview_service.py`
- `backend/tests/unit/simulation/test_historical_replay_engine.py`
- `backend/tests/unit/operations/test_operations_center_service.py`
- `backend/tests/unit/api/test_operations_routes.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/BACKEND_READINESS_REPORT.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Set ALPACA_BASE_URL=https://paper-api.alpaca.markets and rerun real Alpaca
paper checks, or continue wiring Backtest, Optimization, and Walk-Forward
research producers into the evidence recorder boundary.
```

Approval status:

```text
Approved for operator-requested steps 1 through 4.
No local backend blocker remains.
Real Alpaca paper-network validation remains environment-blocked until
ALPACA_BASE_URL is set to the paper endpoint.
```

End-to-end backend readiness pass completed:

- Created `Operations_Turtle_Shell_Artifacts/BACKEND_READINESS_REPORT.md`.
- Unit suite passed.
- Smoke runtime suite passed.
- Integration/e2e suite passed, with only intentional opt-in Alpaca/network
  checks skipped.
- No blocking backend failures remain in the local readiness gate.

Test runs:

```text
Test run: 2026-04-26 22:36:02 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 959 passed, 6 warnings

Test run: 2026-04-26 22:36:02 -04:00
Command: python -m pytest backend\tests\smoke -q
Result: 6 passed, 1 warning

Test run: 2026-04-26 22:36:02 -04:00
Command: python -m pytest backend\tests\integration -q -rs
Result: 27 passed, 3 skipped, 1 warning
```

Skipped integration checks:

```text
RUN_ALPACA_FAKEPACA_STREAM=1 required for Alpaca FAKEPACA stream test.
RUN_ALPACA_PAPER_CRYPTO_STREAM=1 required for real Alpaca paper trade-update stream test.
RUN_ALPACA_PAPER_INTEGRATION=1 required for real Alpaca paper integration checks.
```

Files touched:

- `Operations_Turtle_Shell_Artifacts/BACKEND_READINESS_REPORT.md`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Approval status:

```text
Backend Turtle Shell readiness gate passes for local validation.
Not real-money live trading certification until opt-in real broker checks pass
and the operator explicitly enables live order submission.
```

Next action:

```text
Operator should choose whether to run opt-in Alpaca paper/Fakepaca checks now,
or proceed to the next execution phase using the validated backend foundation.
```

Research evidence persistence and Operations summary completed:

- Added `research_evidence` SQLite table.
- Added `SQLiteRuntimeStore.save_research_evidence(...)`.
- Added `SQLiteRuntimeStore.load_research_evidence(...)`.
- Added `SQLiteRuntimeStore.list_research_evidence(...)` with filters for
  Strategy, Strategy version, and evidence type.
- Added `ResearchEvidenceSummary` to Operations models.
- `RuntimeOverview` now includes research evidence summary counts and latest
  evidence timestamps.
- This remains evidence-only: no broker submit, no broker truth write, no
  alternate runtime.

Bounded contexts:

```text
Research Evidence Context
Persistence Context
Operations Context
```

Guardrail check:

```text
No new runtime root introduced.
No broker submit path introduced.
No broker truth writes introduced.
No research-to-order shortcut introduced.
```

Test runs:

```text
Test run: 2026-04-26 22:31:31 -04:00
Command: python -m pytest backend\tests\unit\persistence\test_sqlite_persistence.py backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\domain\test_research_evidence_contracts.py backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py -q
Result: 38 passed, 1 warning

Test run: 2026-04-26 22:31:31 -04:00
Command: python -m pytest backend\tests\unit\persistence backend\tests\unit\operations backend\tests\unit\domain backend\tests\unit\chart_lab backend\tests\unit\simulation backend\tests\unit\promotion -q
Result: 126 passed, 1 warning

Test run: 2026-04-26 22:31:31 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 959 passed, 6 warnings
```

Files touched:

- `backend/app/persistence/models.py`
- `backend/app/persistence/runtime_store.py`
- `backend/app/operations/models.py`
- `backend/app/operations/service.py`
- `backend/tests/unit/persistence/test_sqlite_persistence.py`
- `backend/tests/unit/operations/test_operations_center_service.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Approval status:

```text
Approved for research evidence persistence and Operations summary.
Next checkpoint is an end-to-end backend readiness pass across runtime,
research tools, broker boundaries, streams, and Operations.
```

Next action:

```text
Run the end-to-end backend readiness pass, document any blockers, and produce
the final Turtle Shell readiness status for trading/backtesting/simulation
work.
```

Slice 10 Research Evidence Contracts completed:

- Added `ChartLabPreviewEvidence`.
- Added `BacktestRun`.
- Added `SimulationRunEvidence`.
- Added `OptimizationRun`.
- Added `WalkForwardRun`.
- Added `PromotionEvidenceBundle`.
- Exported the contracts through `backend.app.domain`.
- Research evidence rejects broker/order/fill/position truth fields.
- Promotion evidence reports readiness as evidence only; it does not grant
  trading authority.
- Persistence/query support is explicitly deferred to the next storage/API
  slice.

Bounded contexts:

```text
Research Evidence Context
Promotion Context
Operations Context
```

Guardrail check:

```text
No research runtime introduced.
No broker submit path introduced.
No broker truth writes introduced.
No SignalPlan bypass introduced.
Research produces evidence only.
```

Test runs:

```text
Test run: 2026-04-26 22:24:27 -04:00
Command: python -m pytest backend\tests\unit\domain\test_research_evidence_contracts.py backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py -q
Result: 9 passed

Test run: 2026-04-26 22:24:27 -04:00
Command: python -m pytest backend\tests\unit\chart_lab backend\tests\unit\simulation backend\tests\unit\promotion backend\tests\unit\domain\test_research_evidence_contracts.py -q
Result: 41 passed, 1 warning

Test run: 2026-04-26 22:24:27 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 957 passed, 6 warnings
```

Files touched:

- `backend/app/domain/research_evidence.py`
- `backend/app/domain/__init__.py`
- `backend/tests/unit/domain/test_research_evidence_contracts.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Approval status:

```text
Approved for Slice 10 Research Evidence Contracts.
Defined Operation Turtle Shell backend lockdown slices are complete.
Remaining production hardening is now follow-on implementation, not an
architecture blocker.
```

Next action:

```text
Start the next implementation sequence: persist/query research evidence,
surface it in Operations, then run an end-to-end backend readiness pass for
backtest, Chart Lab, Sim Lab, optimization, walk-forward, and runtime.
```

Slice 9 GovernorRequest canonical field migration completed:

- `GovernorRequest` now accepts canonical request fields directly:
  `deployment_id`, `symbol`, optional `signal_plan_id`, optional
  `position_lineage_id`, broker freshness, portfolio, and order intent.
- `PortfolioGovernor` now evaluates deployment pause, projected state, symbol,
  and order intent from canonical request fields.
- Runtime pipeline now builds GovernorRequest without passing
  `ExecutionIntent`.
- `ExecutionIntent` remains only as a compatibility output/shim for legacy
  runtime consumers.
- Guardrail lint caught and blocked an attempted Program lineage leak in the
  pipeline; the active pipeline path was corrected before final test approval.

Bounded contexts:

```text
Governor Context
SignalPlan Context
Runtime Composition Root
Operations Context
```

Guardrail check:

```text
No new runtime root introduced.
No Program lineage extended in pipeline.
ExecutionIntent is not the active GovernorRequest spine.
SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> Order remains intact.
```

Test runs:

```text
Test run: 2026-04-26 22:19:52 -04:00
Command: python -m pytest backend\tests\unit\governor backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\runtime\test_runtime_engine.py -q
Result: 45 passed, 1 warning

Test run: 2026-04-26 22:19:52 -04:00
Command: python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 143 passed, 2 warnings

Test run: 2026-04-26 22:19:52 -04:00
Command: python -m pytest backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py backend\tests\unit\governor backend\tests\unit\pipeline\test_runtime_orchestrator.py -q
Result: 41 passed, 1 warning

Test run: 2026-04-26 22:19:52 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 949 passed, 6 warnings
```

Files touched:

- `backend/app/governor/models.py`
- `backend/app/governor/service.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/governor/test_portfolio_governor.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Approval status:

```text
Approved for Slice 9 GovernorRequest canonical field migration.
Slice 9 Runtime Spine Rewire is complete.
Not final Turtle Shell approval yet.
Next slice: Research Evidence Contracts.
```

Next action:

```text
Begin Slice 10: define research evidence contracts for Chart Lab, Backtest, Sim
Lab, Optimization, Walk-Forward, and Promotion without creating an alternate
runtime or bypassing SignalPlan.
```

Slice 9 live-account submission enablement gate completed:

- Automated live broker submission is default-denied.
- `RuntimeOrchestrator` now requires explicit
  `live_order_submission_enabled=True` before a `BROKER_LIVE` adapter can
  submit an automated order.
- Disabled live submission records a rejected broker result with
  `live_submission_disabled` through BrokerSync, so Operations has evidence and
  the broker is not called.
- `BrokerRuntimeDeployment` now carries the explicit live submit enablement
  flag.
- Broker runtime now treats paper/live as Account and Deployment metadata: the
  Account mode must match the Deployment mode, without creating a second
  runtime root.

Bounded contexts:

```text
Account Context
Governor Context
Broker Integration Context
Runtime Composition Root
Operations Context
```

Guardrail check:

```text
No separate paper runtime introduced.
No separate live runtime introduced.
No broker submit outside BrokerAdapter.
No hidden live submit path.
Disabled live submit produces visible BrokerSync evidence.
```

Test runs:

```text
Test run: 2026-04-26 22:13:28 -04:00
Command: python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\runtime\test_broker_runtime_orchestrator.py -q
Result: 42 passed, 1 warning

Test run: 2026-04-26 22:13:28 -04:00
Command: python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 142 passed, 2 warnings

Test run: 2026-04-26 22:13:28 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 948 passed, 6 warnings
```

Files touched:

- `backend/app/pipeline/orchestrator.py`
- `backend/app/runtime/broker_runtime_orchestrator.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Approval status:

```text
Approved for Slice 9 live-account submission enablement gate.
Not final Turtle Shell approval yet.
Remaining gate:
- GovernorRequest migration away from execution_intent shim
```

Next action:

```text
Continue Slice 9 by replacing GovernorRequest.execution_intent dependency with
canonical request fields while preserving the ExecutionIntent shim only for
legacy result consumers.
```

Slice 9 stable Account SignalPlan order idempotency gate completed:

- SignalPlan order client ids are now deterministic by Account, Deployment,
  SignalPlan, lifecycle intent, Position lineage, and leg label.
- `OrderManager.create_signal_plan_order(...)` now returns the existing order
  when the same Account + SignalPlan lifecycle is reprocessed.
- Runtime now skips broker submission when the idempotent SignalPlan order
  already exists and is no longer in `created` state.
- SQLite-backed order ledgers now support client order id lookup, so the same
  idempotency rule works in broker runtime/persistent restart scenarios.

Bounded contexts:

```text
SignalPlan Context
Order / Trade / Position Context
Broker Integration Context
Runtime Composition Root
```

Guardrail check:

```text
No new runtime root introduced.
No broker submit outside BrokerAdapter.
No broker truth writes outside BrokerSync.
No automated order without SignalPlan lineage.
```

Test runs:

```text
Test run: 2026-04-26 22:06:25 -04:00
Command: python -m pytest backend\tests\unit\orders\test_order_manager.py backend\tests\unit\pipeline\test_runtime_orchestrator.py -q
Result: 46 passed, 1 warning

Test run: 2026-04-26 22:06:25 -04:00
Command: python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 138 passed, 2 warnings

Test run: 2026-04-26 22:06:25 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 944 passed, 6 warnings
```

Files touched:

- `backend/app/control_plane/client_order_id.py`
- `backend/app/orders/ledger.py`
- `backend/app/orders/manager.py`
- `backend/app/persistence/runtime_store.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Approval status:

```text
Approved for Slice 9 stable Account SignalPlan order idempotency.
Not final Turtle Shell approval yet.
Remaining gates:
- explicit live-account submission enablement gate
- GovernorRequest migration away from execution_intent shim
```

Next action:

```text
Continue Slice 9 with explicit live-account submission enablement so a live
broker Account cannot submit unless the operator has deliberately enabled live
submission for that Account/runtime path.
```

Slice 9 idempotency gate started:

- Target: stable Account SignalPlan order idempotency.
- Rule: reprocessing the same Account + SignalPlan + lifecycle intent must not
  create a duplicate internal order or duplicate broker submission.
- Scope guard: live-account submission gate and GovernorRequest canonical
  migration remain next gates after idempotency.

Slice 9 multi-account SignalPlan fan-out completed after two iterations and
agent review:

- Review agents:
  - Architect: reviewed invariants and required account-specific fan-out fixes.
  - Experienced Trader: reviewed practical trade-flow acceptance criteria.
  - Alpaca Expert: reviewed Alpaca/account/broker boundary risks.
- Iteration 1:
  - Added one-SignalPlan-to-many-Account fan-out in `RuntimeOrchestrator`.
  - Added direct test proving one SignalPlan creates two account evaluations
    and two account-scoped orders.
- Iteration 2:
  - Added account-specific Governor broker freshness and portfolio inputs.
  - Added test proving one account can be stale/blocked without blocking the
    other account.
  - Added `BrokerRuntimeDeployment.account_ids` so one Deployment can carry
    multiple subscribed Accounts without a second runtime root.
  - Added runtime test proving one Deployment fans out to multiple Accounts.
  - Updated broker submit freshness recording to use `order.account_id`.

Approval status:

```text
Approved for Slice 9 multi-account fan-out contract.
Not final Turtle Shell approval yet.
Remaining gates:
- stable retry idempotency for Account SignalPlan client order ids
- explicit live-account submission enablement gate
- GovernorRequest migration away from execution_intent shim
```

Test runs:

```text
Test run: 2026-04-26 21:54:44 -04:00
Command: python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\runtime\test_broker_runtime_orchestrator.py backend\tests\unit\governor -q
Result: 51 passed, 1 warning

Test run: 2026-04-26 21:54:44 -04:00
Command: python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 136 passed, 2 warnings

Test run: 2026-04-26 21:54:44 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 942 passed, 6 warnings
```

Files touched:

- `backend/app/pipeline/orchestrator.py`
- `backend/app/runtime/broker_runtime_orchestrator.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Continue Slice 9 with stable Account SignalPlan order idempotency and explicit
live-account submission enablement before moving to GovernorRequest canonical
field migration.
```

Slice 9 multi-account fan-out review operation started:

- Architect review agent activated.
- Experienced Trader review agent activated.
- Alpaca Expert review agent activated.
- Plan: run two iterations, collect review findings, refine, test, and record
  approval state.

Iteration 1 target:

```text
Add a minimal multi-account fan-out contract around the existing
RuntimeOrchestrator so one SignalPlan can be evaluated for multiple Accounts
without creating a second runtime root or bypassing BrokerAdapter/BrokerSync.
```

Guardrail check:

```text
No frontend work.
No new runtime root.
No component-owned broker path.
No direct signal-to-order shortcut.
```

Slice 9 protective lifecycle SignalPlan path completed:

- `process_protective_intent(...)` remains callable for compatibility.
- Internally, protective close/reduce/target/stop/trail/breakeven/runner and
  logical-exit order intents now synthesize a SignalPlan lifecycle record.
- Protective orders now flow through:
  `SignalPlan -> RiskResolver -> AccountSignalPlanEvaluation -> Governor trace -> create_signal_plan_order`.
- Protective orders now carry `origin=signal_plan`, `signal_plan_id`,
  `current_signal_plan_id`, `position_lineage_id`, `account_evaluation_id`,
  and `governor_decision_id`.
- Existing broker/order intent behavior such as `STOP_LOSS` remains preserved
  for adapter compatibility.

Bounded contexts:

```text
SignalPlan Context
Account Evaluation Context
RiskResolver Context
Governor Context
Order / Trade / Position Context
```

Guardrail check:

```text
No new runtime root introduced.
No direct protective ExecutionIntent-to-order creation remains in the pipeline.
Protective orders now carry SignalPlan lifecycle lineage.
Manual operator orders remain explicit manual authority.
```

Test runs:

```text
Test run: 2026-04-26 21:43:37 -04:00
Command: python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\orders\test_order_manager.py -q
Result: 41 passed, 1 warning

Test run: 2026-04-26 21:43:37 -04:00
Command: python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 132 passed, 2 warnings

Test run: 2026-04-26 21:43:37 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 938 passed, 6 warnings
```

Files touched:

- `backend/app/control_plane/client_order_id.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Continue Slice 9 with multi-account SignalPlan fan-out: one SignalPlan should
be evaluated independently by every subscribed Account, with separate
RiskResolverResult, AccountSignalPlanEvaluation, Governor trace, and order
decision per Account.
```

Slice 9 continuation started:

- Target: move protective close/reduce/logical-exit order creation onto the
  SignalPlan lifecycle path.
- Scope guard: do not combine this with multi-account fan-out in the same patch.
- Compatibility guard: keep existing `process_protective_intent(...)` callable
  while its internal order creation uses SignalPlan lineage.

Next action:

```text
Map protective ExecutionIntent path and implement the smallest bridge to create
protective orders through SignalPlan -> Account Evaluation -> RiskResolver ->
Governor trace -> OrderManager.create_signal_plan_order.
```

Slice 9 Runtime Spine Rewire first backend patch completed:

- Added `OrderManager.create_signal_plan_order(...)`.
- Added SignalPlan client order id generation.
- Runtime pipeline now builds `SignalPlan` from SignalEngine candidates.
- Runtime pipeline now creates Account-specific `RiskResolverResult`.
- Runtime pipeline now creates `AccountSignalPlanEvaluation` and Governor trace
  before order creation.
- Runtime pipeline now creates automated opening orders through SignalPlan
  lineage instead of active Program lineage.
- Pipeline results now expose SignalPlans and Account Evaluations.
- `ExecutionIntent` remains as a compatibility shim in result output and
  GovernorRequest until the next rewiring slice.

Bounded contexts:

```text
SignalPlan Context
Account Evaluation Context
RiskResolver Context
Governor Context
Order / Trade / Position Context
```

Guardrail check:

```text
No new runtime root introduced.
No direct signal-to-order shortcut remains for automated opening orders.
New automated opening orders use SignalPlan lineage.
ExecutionIntent remains a shim, not the forward order creation spine.
```

Test runs:

```text
Test run: 2026-04-26 21:33:29 -04:00
Command: python -m pytest backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 48 passed, 1 warning

Test run: 2026-04-26 21:33:29 -04:00
Command: python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\risk_resolver backend\tests\unit\governor -q
Result: 132 passed, 2 warnings

Test run: 2026-04-26 21:33:29 -04:00
Command: python -m pytest backend\tests\unit\tools\test_paper_operator_tools.py -q
Result: 18 passed, 1 warning

Test run: 2026-04-26 21:33:29 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 938 passed, 6 warnings
```

Files touched:

- `backend/app/control_plane/client_order_id.py`
- `backend/app/orders/manager.py`
- `backend/app/pipeline/models.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Continue Slice 9 by making one SignalPlan fan out to multiple Accounts and by
moving protective close/reduce/logical-exit paths onto SignalPlan lifecycle
orders instead of ExecutionIntent-only protective shims.
```

Slice 9 Runtime Spine Rewire started:

- Bounded contexts:
  - Deployment Context
  - SignalPlan Context
  - Account Evaluation Context
  - RiskResolver Context
  - Governor Context
  - Order / Trade / Position Context
- Guardrail target:
  - one runtime composition root
  - no new runtime root
  - no direct signal-to-order shortcut
  - Program and ExecutionIntent remain migration shims only

Next action:

```text
Map the current runtime order path, choose the smallest composition root to
rewire, and preserve tests after the first backend patch.
```

Broker test discipline added to Turtle Shell controls:

- Broker-facing tests must use an already configured Broker Service or the
  frontend-configured Broker Account.
- Intentional test order submission is allowed when validating order
  submission, rejection, BrokerSync truth, or operator advisory behavior.
- Broker-facing tests must route through BrokerAdapter and BrokerSync.
- Any real broker order test must identify the order as a test order and record
  the configured account/service source, broker mode, command, and result.

Files touched:

- `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`
- `Operations_Turtle_Shell_Artifacts/BACKEND_LOCKDOWN_AGENT_PLAN.md`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Begin Slice 9: Runtime Spine Rewire. Move runtime flow toward
SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> Order while
preserving Program/ExecutionIntent as migration shims only.
```

Slice 8 Live Stock Market Data Stream Lock completed:

- `HubKey` now identifies the shared live stock stream by provider and data
  feed only. Paper/live is Account metadata, not stream identity.
- `MarketDataStreamHub.start()` opens the stream envelope even when there are
  zero subscribed symbols.
- `MarketDataStreamHub.status()` exposes canonical
  `LiveStockMarketDataStreamStatus`.
- `bootstrap_streams()` starts the shared live stock stream envelope at app
  load when runtime bootstrap runs.
- Chart Lab and broker runtime entrypoint consume the shared hub registry
  instead of creating component-owned live stock streams.
- `/api/v1/system/streams` now projects mode-neutral market-data stream status,
  stream state, last error, and last message timestamp.
- Updated `NEXT_IMPLEMENTATION_SEQUENCE.md` with Slice 8 completed status.

Bounded contexts:

```text
Market Data / Feature Computation Context
Operations Context
```

Guardrail check:

```text
No second runtime introduced.
No component-owned live stock stream added.
No separate paper/live market-data runtime path remains in HubKey.
Live stock stream can stay open with zero subscriptions.
```

Test runs:

```text
Test run: 2026-04-26 21:17:40 -04:00
Command: python -m pytest backend\tests\unit\market_data\test_market_data_stream_hub.py backend\tests\unit\market_data\test_live_stock_stream_status.py backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\runtime\test_broker_runtime_supervisor.py backend\tests\unit\api\test_system_streams_route.py -q
Result: 44 passed, 1 warning

Test run: 2026-04-26 21:17:40 -04:00
Command: python -m pytest backend\tests\unit\market_data backend\tests\unit\runtime backend\tests\unit\api\test_system_streams_route.py -q
Result: 185 passed, 2 warnings

Test run: 2026-04-26 21:17:40 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 936 passed, 6 warnings
```

Files touched:

- `backend/app/runtime/runtime_context.py`
- `backend/app/runtime/broker_runtime_entrypoint.py`
- `backend/app/api/routes/chart_lab.py`
- `backend/app/api/routes/system_streams.py`
- `backend/app/market_data/alpaca.py`
- `backend/app/market_data/pipeline.py`
- `backend/app/market_data/stream_hub.py`
- `backend/tests/unit/api/test_system_streams_route.py`
- `backend/tests/unit/market_data/test_market_data_stream_hub.py`
- `backend/tests/unit/runtime/test_runtime_context.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Begin Slice 9: Runtime Spine Rewire. Move runtime flow toward
SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> Order while
preserving Program/ExecutionIntent as migration shims only.
```

Domain-Driven Design considerations incorporated:

- Created `Operations_Turtle_Shell_Artifacts/DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`.
- Added bounded contexts, aggregate ownership, domain events, commands,
  anti-corruption layers, repository ownership guidance, implementation
  priorities, and DDD acceptance criteria.
- Updated `README.md` required artifact list.
- Updated `TURTLE_SHELL_GUARDRAILS.md` Agent Start Checklist.
- Updated `HANDOFF_PROTOCOL.md` start order, handoff rules, and emergency
  recovery rules.
- Updated `BACKEND_LOCKDOWN_AGENT_PLAN.md` continuity and non-negotiable rules.
- Updated `NEXT_IMPLEMENTATION_SEQUENCE.md` required reading order and
  Coordinator Gate.
- Verified DDD references across Operation Turtle Shell artifacts.

Verification:

```text
Verification run: 2026-04-26 20:59:59 -04:00
Command: rg "DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS|bounded context|DDD" Operations_Turtle_Shell_Artifacts -g "*.md"
Result: DDD references present in README, HANDOFF_PROTOCOL, BACKEND_LOCKDOWN_AGENT_PLAN, NEXT_IMPLEMENTATION_SEQUENCE, TURTLE_SHELL_GUARDRAILS, OPERATION_STATUS, and DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS
```

Files touched:

- `Operations_Turtle_Shell_Artifacts/DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`
- `Operations_Turtle_Shell_Artifacts/README.md`
- `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`
- `Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md`
- `Operations_Turtle_Shell_Artifacts/BACKEND_LOCKDOWN_AGENT_PLAN.md`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Continue Slice 7 by routing TradeEventDispatcher delivery through
AlpacaAccountStreamAdapter -> BrokerStreamRouter -> BrokerSyncService before
fan-out to UI/API subscribers, so subscribers consume broker-synced truth.
```

Turtle Shell guardrails incorporated:

- Created `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`.
- Updated agent start requirements in `HANDOFF_PROTOCOL.md`.
- Updated continuity requirements in `BACKEND_LOCKDOWN_AGENT_PLAN.md`.
- Updated implementation rules and Coordinator Gate in `NEXT_IMPLEMENTATION_SEQUENCE.md`.
- Updated `README.md` primary artifact list and required reading order.
- Verified guardrail references across Operation Turtle Shell artifacts.

Verification:

```text
Verification run: 2026-04-26 20:54:38 -04:00
Command: rg "TURTLE_SHELL_GUARDRAILS|Agent Start Checklist|Before doing work|Start Order For Any New Agent" Operations_Turtle_Shell_Artifacts -g "*.md"
Result: guardrail references present in README, HANDOFF_PROTOCOL, BACKEND_LOCKDOWN_AGENT_PLAN, NEXT_IMPLEMENTATION_SEQUENCE, and TURTLE_SHELL_GUARDRAILS
```

Files touched:

- `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`
- `Operations_Turtle_Shell_Artifacts/README.md`
- `Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md`
- `Operations_Turtle_Shell_Artifacts/BACKEND_LOCKDOWN_AGENT_PLAN.md`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Continue Slice 7 by routing TradeEventDispatcher delivery through
AlpacaAccountStreamAdapter -> BrokerStreamRouter -> BrokerSyncService before
fan-out to UI/API subscribers, so subscribers consume broker-synced truth.
```

Started Slice 7 Account Trade Sync unification:

- Added canonical `AccountTradeSyncStatus` reporting to `TradeEventDispatcher`.
- Added `TradeEventDispatcherRegistry.statuses()` for Operations visibility.
- Added explicit operator trade-sync pause and resume methods.
- Prevented subscriber activity from silently restarting an operator-paused
  trade sync.
- Fixed broker preflight import cycle by importing `InternalOrder` directly
  from `backend.app.orders.models`.
- Updated `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
  with Slice 7 progress and latest baseline.

Test runs:

```text
Test run: 2026-04-26 20:43:07 -04:00
Command: python -m pytest backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\runtime\test_broker_runtime_supervisor.py backend\tests\unit\brokers\test_account_trade_sync_status.py -q
Result: 29 passed, 1 warning

Test run: 2026-04-26 20:43:07 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 930 passed, 5 warnings
```

Next action:

```text
Continue Slice 7 by routing TradeEventDispatcher delivery through
AlpacaAccountStreamAdapter -> BrokerStreamRouter -> BrokerSyncService before
fan-out to UI/API subscribers, so subscribers consume broker-synced truth.
```

Reviewed broker preflight slice and fixed enforcement gap:

- Broker preflight was implemented but not mandatory on submit paths.
- Runtime Alpaca submit now runs broker capability preflight and market-rule
  preflight before `adapter.submit_order`.
- Manual Alpaca submit now runs the same preflight before `broker_adapter.submit_order`.
- Rejected preflight results are written back as rejected broker results so the
  ledger records the failure instead of silently skipping.
- Runtime preflight rejection test proves the Alpaca client is not called.
- Manual preflight rejection test proves the manual route releases idempotency
  and records rejected ledger state before returning operator-facing error.
- Updated `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
  with current verified baseline and completed slices.

Test runs:

```text
Test run: 2026-04-26 20:38:16 -04:00
Command: python -m pytest backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\brokers backend\tests\unit\api\test_manual_trade_preflight.py -q
Result: 120 passed, 1 warning

Test run: 2026-04-26 20:38:16 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 927 passed, 5 warnings
```

Files touched in this slice:

- `backend/app/brokers/preflight.py`
- `backend/app/brokers/__init__.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/app/api/routes/manual_trade.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/api/test_manual_trade_preflight.py`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Begin Slice 7: Account Trade Sync unification. Ensure one Account Trade Sync
per validated Alpaca Account stays open until app shutdown or explicit
operator trade-sync pause, and all trade-update fan-out consumes BrokerSync
truth.
```

Broker preflight service slice completed:

- Added executable `AlpacaBrokerPreflightService`.
- Added executable `MarketRulePreflightService`.
- Added provider-specific checks for Alpaca order type, TIF, asset class,
  extended-hours shape, simple order class boundary, required prices, session
  state, halted/tradable/fractionable state, shortability, easy-to-borrow, and
  buying power.
- Expanded Alpaca adapter translation beyond market-only to support market,
  limit, stop, and stop-limit internal order shapes with explicit SDK request
  class selection.
- Added operator-advisory messages for rejected broker and market preflight.

Test runs:

```text
Test run: 2026-04-26 20:30:21 -04:00
Command: python -m pytest backend\tests\unit\brokers -q
Result: 97 passed, 1 warning

Test run: 2026-04-26 20:33:29 -04:00
Command: python -m pytest backend\tests\unit\brokers -q
Result: 101 passed, 1 warning

Test run: 2026-04-26 20:33:29 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 925 passed, 5 warnings
```

Files touched in this slice:

- `backend/app/brokers/preflight.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/__init__.py`
- `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Next action:

```text
Wire Broker preflight into broker order submit orchestration so no Alpaca order
can reach adapter.submit_order without passing broker capability and market-rule
preflight, with operator-facing rejection details preserved.
```

Started full backend orchestration and entered active Coordinator mode.

Spawned specialist agents for:

- Full Stack Developer Backend Reality Map
- Alpaca Agent and Alpaca Order Compliance
- Angry Architect architecture violation audit
- Research and Computation alignment audit

Local coordinator scan confirmed current backend still uses `ExecutionIntent`,
`ProgramVersion`, `ResolvedProgramComponents`, and `BrokerRuntime*` as active
spine concepts. Drafting Backend Reality Map while agents continue.

Merged all Phase 0 specialist findings into:

- `Operations_Turtle_Shell_Artifacts/BACKEND_REALITY_MAP.md`

Phase 0 baseline verdict:

```text
Reality map accepted as honest baseline.
Backend ship gate does not pass.
Phase 1 contract work may begin.
```

Previously completed: created the backend lockdown agent plan and added required specialist agents:

- Coordinator
- Angry Architect
- Product Manager
- Alpaca Agent
- Alpaca Order Compliance Agent
- Broker Error And Advisory Agent
- Market Rules And Session Agent
- Full Stack Developer

Locked additional runtime rules:

- one shared Live Stock Market Data Stream
- stream opens on backend app load when enabled
- stream stays open until app shutdown
- no component-owned live stock stream
- one Account Trade Sync per validated Alpaca Account
- Account Trade Sync opens after Account creation and credential validation
- trading pause does not imply trade-sync pause

## Next Action

Create Phase 1 contracts for:

- SignalPlan
- Account Evaluation
- RiskResolver
- Governor request/decision
- Order lineage
- Position explanation context
- Live Stock Market Data Stream status
- Account Trade Sync status
- Alpaca capability/preflight rules

## Files Touched

- `Operations_Turtle_Shell_Artifacts/README.md`
- `Operations_Turtle_Shell_Artifacts/BACKEND_LOCKDOWN_AGENT_PLAN.md`
- `Operations_Turtle_Shell_Artifacts/BACKEND_REALITY_MAP.md`
- `Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

## Tests Run

No backend tests run for this documentation update.

## Decisions Made

- Operation Turtle Shell is backend-only.
- The backend doctrine is locked around Strategy, Watchlist, Deployment,
  SignalPlan, Account Evaluation, RiskResolver, Governor, Order Ledger,
  BrokerAdapter, BrokerSync, Position Truth, and Operations Center.
- Backtest, Sim Lab, Walk-Forward, Optimization, Chart Lab, and Live must share
  Feature Engine, Signal Engine, RiskResolver, and order creation logic.
- Alpaca remains behind BrokerAdapter and BrokerSync.
- Alpaca capability rules must be provider-specific and must not contaminate the
  core SignalPlan model.
- Broker errors require canonical codes and operator advisory.

## Blockers

Backend ship remains blocked.

Phase 1 contract work is unblocked.

## Approval Status

Phase 0 Backend Reality Map accepted as baseline.

Awaiting Phase 1 contract artifacts.

Phase 1 code contract slice completed:

- Added `backend/app/domain/signal_plan.py`
- Exported SignalPlan, Account Evaluation, RiskResolver, GovernorDecisionTrace,
  and PositionExplanationContext contracts from `backend/app/domain/__init__.py`
- Added `backend/app/brokers/capabilities.py`
- Exported broker capability, broker advisory, and market-rule preflight
  contracts from `backend/app/brokers/__init__.py`
- Added focused contract tests

Test run:

```text
Test run: 2026-04-26 20:02:26 -04:00
Command: python -m pytest backend\tests\unit\domain\test_signal_plan_contracts.py backend\tests\unit\brokers\test_broker_capability_contracts.py -q
Result: 21 passed, 1 warning
```

Order lineage contract slice completed:

- Extended `backend/app/orders/models.py` with `SIGNAL_PLAN` origin and
  nullable SignalPlan/Position lineage fields.
- Added `backend/tests/unit/orders/test_order_lineage_contract.py`.

Test run:

```text
Test run: 2026-04-26 20:03:54 -04:00
Command: python -m pytest backend\tests\unit\domain\test_signal_plan_contracts.py backend\tests\unit\brokers\test_broker_capability_contracts.py backend\tests\unit\orders\test_order_lineage_contract.py backend\tests\unit\orders\test_order_manager.py -q
Result: 45 passed, 1 warning
```

Stream status contract slice completed:

- Added `LiveStockMarketDataStreamStatus`.
- Added `AccountTradeSyncStatus`.
- Added tests proving one live stock stream can be open with zero subscriptions
  and trading-paused Accounts can still have open Account Trade Sync.

Test run:

```text
Test run: 2026-04-26 20:06:22 -04:00
Command: python -m pytest backend\tests\unit\domain backend\tests\unit\orders backend\tests\unit\brokers backend\tests\unit\market_data -q
Result: 285 passed, 1 warning
```

Architecture guardrail lint slice completed:

- Added `backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py`.
- Guardrails freeze known Program lineage shims and runtime authority roots.
- New files cannot spread Program lineage or new runtime authority classes
  without approval.

Test run:

```text
Test run: 2026-04-26 20:07:41 -04:00
Command: python -m pytest backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py backend\tests\unit\domain backend\tests\unit\orders backend\tests\unit\brokers backend\tests\unit\market_data -q
Result: 287 passed, 1 warning
```

SignalPlanBuilder bridge slice completed:

- Added `backend/app/decision/signal_plan_builder.py`.
- Exported `SignalPlanBuilder`.
- Added `backend/tests/unit/decision/test_signal_plan_builder.py`.
- Current SignalEngine candidate output can now become a neutral SignalPlan
  without Account quantity, broker truth, or Governor approval.

Test run:

```text
Test run: 2026-04-26 20:08:52 -04:00
Command: python -m pytest backend\tests\unit\decision backend\tests\unit\domain\test_signal_plan_contracts.py backend\tests\unit\orders\test_order_lineage_contract.py backend\tests\unit\brokers\test_broker_capability_contracts.py backend\tests\unit\brokers\test_account_trade_sync_status.py backend\tests\unit\market_data\test_live_stock_stream_status.py -q
Result: 39 passed, 1 warning
```

Full backend unit checkpoint completed:

```text
Test run: 2026-04-26 20:09:55 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 904 passed, 5 warnings
```

Runtime rewiring sequence artifact completed:

- Added `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`.

Persistence-ready lineage slice completed:

- Added nullable SignalPlan/Position lineage columns to runtime SQLite schema.
- Added indexes for `signal_plan_id`, `opening_signal_plan_id`, and
  `position_lineage_id`.
- Added store query helpers for SignalPlan and Position lineage.
- Added persistence test for save/load/query of SignalPlan order lineage.

Test run:

```text
Test run: 2026-04-26 20:12:54 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 905 passed, 5 warnings
```

RiskResolver boundary slice completed:

- Added `backend/app/risk_resolver/service.py`.
- Added `backend/app/risk_resolver/__init__.py`.
- Added `backend/tests/unit/risk_resolver/test_risk_resolver_contract.py`.
- RiskResolver is now the first explicit boundary that can produce final
  Account-specific quantity/notional from a neutral SignalPlan.

Test run:

```text
Test run: 2026-04-26 20:14:29 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 909 passed, 5 warnings
```

## Handoff Status

Coordinator actively starting Slice 8 Live Stock Market Data Stream Lock with support agents.

## Required Start Block For Next Agent

The next agent must update this section before work begins:

```text
Work session status: in_progress
Agent role:
Started at:
Last heartbeat:
Current phase:
Current task:
Expected next checkpoint:
Files expected to inspect:
```

## Required End Block For Next Agent

The next agent must update this section before work ends:

```text
Work session status: handoff_ready | blocked | failed | completed
Ended at:
Latest completed action:
Next action:
Files touched:
Tests run:
Blockers:
Approval status:
```

## 2026-04-27 01:54:53 -04:00 - Nanyel Runtime Naming Cleanup

Completed action:
- Applied AGENTS.md / Nanyel standard: paper/live are Account metadata, not runtime products.
- Renamed controlled tooling from `tools/run_paper_runtime.py` and `tools/run_paper_runtime_dry_run.py` to `tools/run_runtime_smoke.py` and `tools/run_runtime_dry_run.py`.
- Renamed active runtime module files from broker-runtime filenames to account-trading filenames while preserving existing compatibility exports.
- Replaced active UI mode labels with plain `Paper` / `Live`.
- Renamed market-data consumer/mode terms from `BROKER_RUNTIME` / `LIVE_RUNTIME` to `ACCOUNT_TRADING` / `LIVE_TRADING`.
- Updated `new-frontend/README.md` to state the doctrine directly: paper/live are Account metadata and there is one runtime path.

Files touched:
- `backend/app/runtime/account_trading_entrypoint.py`
- `backend/app/runtime/account_trading_orchestrator.py`
- `backend/app/runtime/account_trading_supervisor.py`
- `backend/app/runtime/__init__.py`
- `backend/app/market_data/data_intent.py`
- `backend/app/market_data/resolver.py`
- `backend/app/promotion/service.py`
- `backend/app/api/routes/manual_trade.py`
- `backend/app/broker_accounts/credential_store.py`
- `tools/run_runtime_smoke.py`
- `tools/run_runtime_dry_run.py`
- `backend/tests/unit/tools/test_account_operator_tools.py`
- `backend/tests/unit/runtime/test_broker_runtime_entrypoint.py`
- `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
- `backend/tests/unit/runtime/test_broker_runtime_supervisor.py`
- `backend/tests/unit/market_data/test_resolver.py`
- `backend/tests/unit/market_data/test_market_data_catalog.py`
- `frontend/src/brokers.js`
- `frontend/src/providers.js`
- `new-frontend/README.md`
- `new-frontend/package.json`
- `new-frontend/tsconfig.json`
- `Operations_Turtle_Shell_Artifacts/BACKEND_REALITY_MAP.md`
- `Operations_Production_Readiness/CURRENT_STATE_AUDIT.md`
- `Operations_Production_Readiness/TESTING_AND_ACCEPTANCE_PLAN.md`

Tests run:
- `python -m pytest backend\tests\unit\tools\test_account_operator_tools.py backend\tests\unit\runtime\test_broker_runtime_entrypoint.py backend\tests\unit\runtime\test_broker_runtime_orchestrator.py backend\tests\unit\runtime\test_broker_runtime_supervisor.py backend\tests\unit\market_data\test_resolver.py backend\tests\unit\market_data\test_market_data_catalog.py backend\tests\unit\lint -q` -> 267 passed, 2 warnings.
- `npm.cmd test` in `frontend/` -> 42 passed; frontend check passed.
- `npm.cmd test` in `new-frontend/` -> 10 passed; banned-name lint clean.
- `npm.cmd run lint` in `new-frontend/` -> passed.
- `npm.cmd run typecheck` in `new-frontend/` -> passed.
- `npm.cmd run build` in `new-frontend/` -> passed.

Blockers:
- None for this naming cleanup.

Next action:
- Continue Promotion/Program migration shim review, unless operator asks to cut fully to `new-frontend/` first.

Approval status:
- Coordinator-approved under Nanyel doctrine for this cleanup.

## 2026-04-27 03:37:16 -04:00 - Account Positions and Alpaca Account Snapshot Hardening

Work session status: completed

Started at:
- 2026-04-27 03:28:00 -04:00

Last heartbeat:
- 2026-04-27 03:37:16 -04:00

Completed action:
- Pulled in Alpaca Expert review for Account sync truth and pertinent `/v2/account` fields.
- Confirmed BrokerSync reconciliation was polling account, positions, and open orders, but positions were not being persisted for Operations/frontend visibility.
- Added durable replacement of broker position snapshots during reconcile so Operations can project current open positions per Account.
- Added stream position-update persistence so live trade/position events also refresh the broker position read model.
- Expanded the Alpaca account snapshot contract with leverage/margin/PDT/status/currency/transfer fields needed for operator advisory and account health.
- Hardened Alpaca optional numeric normalization for blank optional provider fields.
- Expanded frontend schemas and Account UI surfaces so the card/drawer can show persisted open positions and pertinent account details.

Files touched:
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/models.py`
- `backend/app/brokers/sync.py`
- `backend/app/persistence/runtime_store.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `frontend/src/api/schemas/accounts.ts`
- `frontend/src/api/schemas/operations.ts`
- `frontend/src/routes/Accounts.tsx`
- `frontend/src/routes/AccountDetailDrawer.tsx`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\brokers\test_broker_sync_reconciliation.py backend\tests\unit\brokers\test_alpaca_broker_adapter.py backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\persistence\test_sqlite_persistence.py -q` -> 78 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1103 passed, 6 warnings.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npm.cmd test` in `frontend/` -> 10 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.

Blockers:
- None.

Next action:
- Restart or let the backend poll once with the real configured Alpaca Account. Account cards should now receive persisted broker positions and richer account snapshot fields from BrokerSync. If the UI still shows stale/no positions after a fresh poll, inspect the live Operations account endpoint payload against Alpaca `list_positions` for that account.

Approval status:
- Coordinator-approved under Nanyel doctrine. BrokerSync remains the only broker truth writer; frontend receives read-model truth only.

## 2026-04-27 03:42:29 -04:00 - Backend Three-Pass Iteration Review

Work session status: completed

Started at:
- 2026-04-27 03:38:00 -04:00

Last heartbeat:
- 2026-04-27 03:42:29 -04:00

Completed action:
- Iterated through backend needs three times with separate lenses:
  1. Broker and Account truth.
  2. Runtime spine and domain boundaries.
  3. Operations and API readiness.
- Created `Operations_Turtle_Shell_Artifacts/BACKEND_THREE_PASS_ITERATION_REVIEW.md`.
- Confirmed Account snapshots, broker open orders, broker positions, and BrokerSync freshness are persisted through BrokerSync/runtime store read models.
- Confirmed direct Alpaca trading calls remain inside the Alpaca broker adapter boundary.
- Confirmed StrategyVersion still rejects risk, Account, universe, watchlist, and runtime ownership fields.
- Confirmed Operations account APIs expose Account snapshot, sync freshness, open broker orders, internal order summary, and persisted broker positions.
- Cleaned one stale Operations docstring from broker-paper wording to Account runtime wording.
- Updated `NEXT_IMPLEMENTATION_SEQUENCE.md` verified backend baseline to the current 1103-test run.

Files touched:
- `backend/app/operations/service.py`
- `Operations_Turtle_Shell_Artifacts/BACKEND_THREE_PASS_ITERATION_REVIEW.md`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\lint backend\tests\unit\domain\test_domain_boundaries.py backend\tests\unit\api\test_operations_routes.py backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\brokers\test_broker_sync_reconciliation.py -q` -> 272 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1103 passed, 6 warnings.

Blockers:
- None.

Next action:
- After backend restart or next live BrokerSync poll, verify real configured Alpaca Account payloads through `/api/v1/operations/overview`, `/api/v1/operations/accounts/{account_id}`, and `/api/v1/system/streams`.

Approval status:
- Coordinator-approved. Three backend passes completed without finding a blocking architecture deviation.

## 2026-04-27 03:47:42 -04:00 - Frontend API Handshake Review

Work session status: completed

Started at:
- 2026-04-27 03:43:00 -04:00

Last heartbeat:
- 2026-04-27 03:47:42 -04:00

Completed action:
- Audited frontend API clients against registered backend FastAPI routes.
- Confirmed every current frontend HTTP API route is registered by backend.
- Confirmed Chart Lab WebSocket route is registered.
- Found and fixed one concrete response-schema mismatch:
  `MarketDataProvidersApi.delete(...)` expected a service record, while backend
  returns a deletion response.
- Added `MarketDataServiceDeletionResponseSchema`.
- Updated frontend delete client to parse the deletion response.
- Added frontend API handshake tests for the market-data delete contract.
- Added backend assertion for market-data delete response message.
- Created `Operations_Turtle_Shell_Artifacts/FRONTEND_API_HANDSHAKE_REVIEW.md`.

Files touched:
- `frontend/src/api/providers.ts`
- `frontend/src/api/schemas/providers.ts`
- `frontend/src/api/apiHandshake.test.ts`
- `backend/tests/unit/api/test_market_data_delete_route.py`
- `Operations_Turtle_Shell_Artifacts/FRONTEND_API_HANDSHAKE_REVIEW.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\api\test_frontend_api_contract.py backend\tests\unit\api\test_market_data_delete_route.py backend\tests\unit\api\test_research_run_routes.py -q` -> 10 passed, 5 warnings.
- `npm.cmd test` in `frontend/` -> 13 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.
- `python -m pytest backend\tests\unit -q` -> 1103 passed, 6 warnings.

Blockers:
- None.

Next action:
- Live smoke the configured backend after restart against `/api/v1/operations/overview`, `/api/v1/operations/accounts/{account_id}`, and `/api/v1/system/streams`.

Approval status:
- Coordinator-approved. Frontend API handshakes match the backend route surface after the market-data delete schema correction.

## 2026-04-27 03:51:04 -04:00 - Live Sync No Lazy Loading Enforcement

Work session status: completed

Started at:
- 2026-04-27 03:48:00 -04:00

Last heartbeat:
- 2026-04-27 03:51:04 -04:00

Completed action:
- Traced Account Trade Sync startup paths through backend startup, Account
  creation, credential replacement, Operations WebSocket subscription, and
  system stream status projection.
- Confirmed backend startup wires BrokerSync/manual-trade composition before
  opening streams.
- Confirmed backend startup starts one Account Trade Sync per configured
  Alpaca Account with credentials.
- Confirmed Account create and credential replacement explicitly start/restart
  Account Trade Sync.
- Removed the remaining lazy startup fallback from
  `TradeEventDispatcher.subscribe(...)`.
- Updated runtime test coverage so browser subscriptions cannot start live sync.
- Created `Operations_Turtle_Shell_Artifacts/LIVE_SYNC_NO_LAZY_LOADING_REVIEW.md`.

Files touched:
- `backend/app/runtime/runtime_context.py`
- `backend/tests/unit/runtime/test_runtime_context.py`
- `Operations_Turtle_Shell_Artifacts/LIVE_SYNC_NO_LAZY_LOADING_REVIEW.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\api\test_server_startup.py backend\tests\unit\api\test_system_streams_route.py backend\tests\unit\api\test_operations_trade_stream_route.py -q` -> 42 passed, 5 warnings.
- `python -m pytest backend\tests\unit -q` -> 1103 passed, 6 warnings.
- `npm.cmd run typecheck` in `frontend/` -> passed.

Blockers:
- None.

Next action:
- On backend restart, verify `/api/v1/system/streams` shows every configured
  Alpaca Account Trade Sync without needing to open Operations/Brokers pages.

Approval status:
- Coordinator-approved. Live sync is backend-lifecycle-started only; frontend subscriptions are listeners only.

## 2026-04-27 03:55:21 -04:00 - Account Counts Must Not False-Zero

Work session status: completed

Started at:
- 2026-04-27 03:52:00 -04:00

Last heartbeat:
- 2026-04-27 03:55:21 -04:00

Completed action:
- Investigated Account card `Open Orders 0` / `Positions 0` display.
- Found the frontend Account card defaulted the per-account Operations detail
  arrays to empty while the query was loading, which could show a false zero.
- Updated Account cards to use Operations overview AccountSummary counts as
  the card count source, while still using detail arrays for previews.
- Hardened Operations overview so persisted broker position snapshots are
  included in account discovery and global open-position totals even without a
  live in-memory BrokerSync reader.
- Added backend test proving persisted broker positions count in overview
  without a live reader.

Files touched:
- `frontend/src/routes/Accounts.tsx`
- `backend/app/operations/service.py`
- `backend/tests/unit/operations/test_operations_center_service.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\api\test_operations_routes.py -q` -> 27 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1104 passed, 6 warnings.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npm.cmd test` in `frontend/` -> 13 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.

Blockers:
- None.

Next action:
- Refresh Accounts after backend restart / next BrokerSync poll. If the card
  still shows zero, inspect `/api/v1/operations/overview` and
  `/api/v1/operations/accounts/{account_id}` directly; the card now follows
  those Operations read-model counts.

Approval status:
- Coordinator-approved. Account cards no longer manufacture zero counts from
  unloaded detail arrays.

## 2026-04-27 12:18:36 -04:00 - Research Create-Run API Handoff For Frontend

Work session status: completed

Started at:
- 2026-04-27 12:13:00 -04:00

Last heartbeat:
- 2026-04-27 12:25:46 -04:00

Completed action:
- Executed the frontend functionality handoff request while Claude/new frontend
  work is ready for research create-run APIs.
- Confirmed backend V1 research APIs exist for Backtests, Sim Lab,
  Optimization, and Walk-Forward.
- Added HTTP-level FastAPI contract tests that exercise frontend-shaped JSON
  requests/responses for backtest create/list/cancel, Sim Lab create/run,
  Optimization create, and Walk-Forward create.
- Updated research route placeholder copy so it no longer says the APIs are
  missing.
- Created `Operations_Turtle_Shell_Artifacts/RESEARCH_CREATE_RUN_API_HANDOFF.md`
  for Claude/front-end pickup.
- Fixed the frontend build blocker from the functionality slice by adding
  `ManualOrderDrawer`, wired through the existing manual trade API boundary.
  It submits only through `/api/v1/broker-accounts/{account_id}/orders` and
  keeps BrokerAdapter/BrokerSync boundaries intact.

Files touched:
- `backend/tests/unit/api/test_research_run_routes.py`
- `frontend/src/routes/Backtests.tsx`
- `frontend/src/routes/SimLab.tsx`
- `frontend/src/routes/Optimization.tsx`
- `frontend/src/routes/WalkForward.tsx`
- `frontend/src/routes/ManualOrderDrawer.tsx`
- `Operations_Turtle_Shell_Artifacts/RESEARCH_CREATE_RUN_API_HANDOFF.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\api\test_research_run_routes.py -q`
  -> 8 passed, 1 warning.
- `python -m pytest backend\tests\unit\api\test_research_run_routes.py backend\tests\unit\api\test_frontend_api_contract.py -q`
  -> 10 passed, 5 warnings.
- `python -m pytest backend\tests\unit -q`
  -> 1106 passed, 6 warnings.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npm.cmd test` in `frontend/` -> 13 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.

Blockers:
- None.

Next action:
- Hand Claude the green API contract for adding guarded research create-run
  controls. Manual order drawer now compiles and remains behind the backend
  manual trade boundary.

Approval status:
- Coordinator-approved. Backend unit suite and frontend build are green.

## 2026-04-27 12:38:00 -04:00 - Account Sync Stale Badge Corrected

Work session status: completed

Started at:
- 2026-04-27 12:30:00 -04:00

Last heartbeat:
- 2026-04-27 12:38:00 -04:00

Completed action:
- Investigated operator report that the Account page still showed Sync Stale.
- Found stale backend reload listeners on port `8000`; replaced them with one
  clean backend process from the current worktree.
- Confirmed `/api/v1/system/streams` now reports one `stock` Alpaca SIP market
  data hub and one running Account Trade Sync with `is_stale=false`.
- Confirmed `/api/v1/operations/overview` reports Account BrokerSync fresh,
  latest sync at `2026-04-27T16:36:42Z`, and 4 open positions.
- Found the remaining mismatch: `/api/v1/broker-accounts` projected old
  embedded Account freshness from the Account row while Operations projected
  current BrokerSync truth.
- Updated BrokerAccountService listing to overlay the latest persisted broker
  account snapshot and BrokerSync freshness before returning Account cards.
- Restarted backend again after the code fix and confirmed
  `/api/v1/broker-accounts` now returns `is_stale=false`.

Files touched:
- `backend/app/broker_accounts/service.py`
- `backend/tests/unit/broker_accounts/test_alpaca_paper_account_service.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\broker_accounts\test_alpaca_paper_account_service.py backend\tests\unit\api\test_broker_accounts_routes.py backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\api\test_operations_routes.py -q`
  -> 56 passed, 1 warning.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `python -m pytest backend\tests\unit -q` -> 1107 passed, 6 warnings.

Runtime verification:
- `GET /api/v1/broker-accounts` -> Account `is_stale=false`.
- `GET /api/v1/operations/overview` -> no stale sync accounts; positions count 4.
- `GET /api/v1/system/streams` -> Account Trade Sync running and not stale.

Blockers:
- None.

Next action:
- Hard-refresh the frontend Accounts page. It should now show Sync Fresh from
  both Account list and Operations read models.

Approval status:
- Coordinator-approved. BrokerSync truth now wins over stale embedded Account
  metadata in the Account list response.

## 2026-04-27 03:04:43 -04:00 - StrategyVersion Ownership Guardrail Hardening

Work session status: completed

Started at:
- 2026-04-27 03:00:00 -04:00

Last heartbeat:
- 2026-04-27 03:04:43 -04:00

Completed action:
- Applied AGENTS.md / Nanyel standard to StrategyVersion ownership.
- Confirmed StrategyVersion owns reusable trading logic only: feature refs plus entry/exit rules.
- Confirmed Deployment owns watchlist selection and subscribed Account selection.
- Added explicit StrategyVersion validation rejecting risk, Account, universe, watchlist, deployment, and runtime ownership fields.
- Added domain boundary tests proving StrategyVersion cannot own risk or universe/watchlist concerns.

Files touched:
- `backend/app/domain/strategy.py`
- `backend/tests/unit/domain/test_domain_boundaries.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\domain\test_domain_boundaries.py backend\tests\unit\strategies backend\tests\unit\deployments -q` -> 68 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1089 passed, 6 warnings.

Blockers:
- None.

Next action:
- Continue backend hardening with RiskResolver lifecycle quantity semantics: one SignalPlan lifecycle may contain multiple legs, RiskResolver sizes the whole Account-specific plan, then allocates quantities by leg while respecting fractional/share constraints.

Approval status:
- Coordinator-approved under Nanyel doctrine. StrategyVersion does not own risk or universe.

## 2026-04-27 03:10:07 -04:00 - RiskResolver Lifecycle Quantity Semantics Hardening

Work session status: completed

Started at:
- 2026-04-27 03:04:43 -04:00

Last heartbeat:
- 2026-04-27 03:10:07 -04:00

Completed action:
- Reviewed the existing SignalPlan lifecycle sizing path for multi-leg plans.
- Confirmed RiskResolver already sizes the whole Account-specific SignalPlan lifecycle first, then allocates entry, stop, targets, and runner legs.
- Hardened SignalPlan target labels so target legs cannot duplicate each other or collide with reserved lifecycle labels such as `entry`, `stop`, or `runner`.
- Hardened whole-share lifecycle allocation so a 100% target-only plan assigns rounding remainder to the final target instead of silently leaving shares unmanaged.
- Added a RiskResolver warning when an open lifecycle plan intentionally leaves Account quantity unmanaged because targets do not cover 100% and no runner exists.

Files touched:
- `backend/app/domain/signal_plan.py`
- `backend/app/risk_resolver/service.py`
- `backend/tests/unit/domain/test_signal_plan_contracts.py`
- `backend/tests/unit/risk_resolver/test_risk_resolver_contract.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\domain\test_signal_plan_contracts.py backend\tests\unit\risk_resolver backend\tests\unit\orders\test_order_manager.py -q` -> 64 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1095 passed, 6 warnings.

Blockers:
- None.

Next action:
- Continue backend hardening with runtime startup guarantees: verify market data stream starts at backend load from configured Alpaca Data Provider and one Account Trade Sync starts for every validated Alpaca Account.

Approval status:
- Coordinator-approved under Nanyel doctrine. Multi-leg SignalPlan lifecycle semantics remain one plan, Account-specific RiskResolver sizing, and child leg allocation without Strategy-owned risk.

## 2026-04-27 03:15:45 -04:00 - Account Trade Sync Startup Guarantee Hardening

Work session status: completed

Started at:
- 2026-04-27 03:10:07 -04:00

Last heartbeat:
- 2026-04-27 03:15:45 -04:00

Completed action:
- Reviewed backend startup wiring for the shared live stock market-data stream and one Account Trade Sync per validated Alpaca Account.
- Confirmed FastAPI startup builds per-account BrokerSync/OrderManager stacks before opening broker trade streams.
- Added `TradeEventDispatcherRegistry.bind_account(...)` so an Account Trade Sync can be created or refreshed with concrete BrokerAdapter and BrokerSync boundaries.
- Added `ensure_account_trade_sync_started(...)` so account creation and credential replacement do not rely on boot-time resolver state.
- Updated broker-account create flow to bind and start the Account Trade Sync from the just-configured Account stack.
- Updated broker-account credential replacement to restart the Account Trade Sync so rotated credentials take effect without app restart.

Files touched:
- `backend/app/runtime/runtime_context.py`
- `backend/app/api/routes/broker_accounts.py`
- `backend/tests/unit/runtime/test_runtime_context.py`
- `backend/tests/unit/api/test_broker_accounts_routes.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\api\test_broker_accounts_routes.py backend\tests\unit\api\test_server_startup.py -q` -> 40 passed, 5 warnings.
- `python -m pytest backend\tests\unit -q` -> 1100 passed, 6 warnings.

Blockers:
- None.

Next action:
- Continue backend hardening with Operations visibility/read-model review so stream failures, stale BrokerSync, and Account-specific trade sync state stay readable for multi-account operation.

Approval status:
- Coordinator-approved under Nanyel doctrine. There is still one runtime; paper/live remain Account metadata; trade sync is per Account and bound to BrokerAdapter + BrokerSync.

## 2026-04-27 03:21:23 -04:00 - Account Card Sync Visibility Fix

Work session status: completed

Started at:
- 2026-04-27 03:16:00 -04:00

Last heartbeat:
- 2026-04-27 03:21:23 -04:00

Completed action:
- Investigated the Accounts card showing `Sync Fresh` and `Stale` at the same time.
- Confirmed the two labels came from different truths: BrokerSync freshness and Account Trade Stream glyph state.
- Fixed Account/Operations UI to display BrokerSync `Last sync` from `last_successful_sync_at`, then `last_poll_sync_at`, then `last_event_at`, then `last_sync_at`.
- Fixed trade stream glyph mapping so a running quiet Alpaca trade stream does not show `Stale` just because no orders/fills have arrived.
- Added shared frontend helper `latestBrokerSyncTimestamp(...)`.

Files touched:
- `frontend/src/api/schemas/accounts.ts`
- `frontend/src/lib/brokerSync.ts`
- `frontend/src/routes/Accounts.tsx`
- `frontend/src/routes/AccountDetailDrawer.tsx`
- `frontend/src/routes/Operations.tsx`
- `frontend/src/routes/Dashboard.tsx`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npm.cmd test` in `frontend/` -> 10 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.
- `python -m pytest backend\tests\unit\api\test_system_streams_route.py backend\tests\unit\runtime\test_runtime_context.py -q` -> 34 passed, 1 warning.

Blockers:
- None.

Next action:
- Continue Operations visibility/read-model hardening after operator verifies the Account card now shows one coherent sync story.

Approval status:
- Coordinator-approved under Nanyel doctrine. Account UI now separates BrokerSync truth from quiet-but-open Account Trade Stream state.

## 2026-04-27 03:27:05 -04:00 - Open Broker Orders Visibility Fix

Work session status: completed

Started at:
- 2026-04-27 03:22:00 -04:00

Last heartbeat:
- 2026-04-27 03:27:05 -04:00

Completed action:
- Investigated why an Account with broker-side open orders could still show `Open Orders 0`.
- Found BrokerSync reconciliation fetched Alpaca open orders but did not persist the current open-order snapshot set for Operations visibility.
- Added `SQLiteRuntimeStore.replace_broker_open_order_snapshots(...)` so each poll replaces the Account's broker open-order truth with the current broker response.
- Updated `BrokerSyncService.reconcile(...)` to persist current open broker orders before Operations reads them.
- Added tests proving BrokerSync persists open-order snapshots and Operations account summary count matches the visible broker order list.
- Updated the Account card to preview open broker orders directly, not only hide them behind the View drawer.
- Expanded the Account detail open-order table with side, quantity, status, and order type.

Files touched:
- `backend/app/brokers/sync.py`
- `backend/app/persistence/runtime_store.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `backend/tests/unit/operations/test_operations_center_service.py`
- `frontend/src/api/schemas/operations.ts`
- `frontend/src/routes/Accounts.tsx`
- `frontend/src/routes/AccountDetailDrawer.tsx`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\brokers\test_broker_sync_reconciliation.py backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\api\test_operations_routes.py backend\tests\unit\persistence\test_sqlite_persistence.py -q` -> 67 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1102 passed, 6 warnings.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npm.cmd test` in `frontend/` -> 10 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.

Blockers:
- None.

Next action:
- Operator should refresh the frontend after the next BrokerSync poll/reconcile. If orders still do not appear, inspect the live `/api/v1/operations/accounts/{account_id}` response and Alpaca adapter `list_open_orders` result for that Account.

Approval status:
- Coordinator-approved under Nanyel doctrine. BrokerSync remains the only broker truth writer; Operations only projects persisted broker truth.
## 2026-04-27 01:54:53 -04:00 - Nanyel Runtime Naming Cleanup

Completed action:
- Applied AGENTS.md / Nanyel standard: paper/live are Account metadata, not runtime products.
- Renamed controlled tooling from `tools/run_paper_runtime.py` and `tools/run_paper_runtime_dry_run.py` to `tools/run_runtime_smoke.py` and `tools/run_runtime_dry_run.py`.
- Renamed active runtime module files from broker-runtime filenames to account-trading filenames while preserving existing compatibility exports.
- Replaced active UI mode labels with plain `Paper` / `Live`.
- Renamed market-data consumer/mode terms from `BROKER_RUNTIME` / `LIVE_RUNTIME` to `ACCOUNT_TRADING` / `LIVE_TRADING`.
- Updated `new-frontend/README.md` to state the doctrine directly: paper/live are Account metadata and there is one runtime path.

Files touched:
- `backend/app/runtime/account_trading_entrypoint.py`
- `backend/app/runtime/account_trading_orchestrator.py`
- `backend/app/runtime/account_trading_supervisor.py`
- `backend/app/runtime/__init__.py`
- `backend/app/market_data/data_intent.py`
- `backend/app/market_data/resolver.py`
- `backend/app/promotion/service.py`
- `backend/app/api/routes/manual_trade.py`
- `backend/app/broker_accounts/credential_store.py`
- `tools/run_runtime_smoke.py`
- `tools/run_runtime_dry_run.py`
- `backend/tests/unit/tools/test_account_operator_tools.py`
- `backend/tests/unit/runtime/test_broker_runtime_entrypoint.py`
- `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
- `backend/tests/unit/runtime/test_broker_runtime_supervisor.py`
- `backend/tests/unit/market_data/test_resolver.py`
- `backend/tests/unit/market_data/test_market_data_catalog.py`
- `frontend/src/brokers.js`
- `frontend/src/providers.js`
- `new-frontend/README.md`
- `new-frontend/package.json`
- `new-frontend/tsconfig.json`
- `Operations_Turtle_Shell_Artifacts/BACKEND_REALITY_MAP.md`
- `Operations_Production_Readiness/CURRENT_STATE_AUDIT.md`
- `Operations_Production_Readiness/TESTING_AND_ACCEPTANCE_PLAN.md`

Tests run:
- `python -m pytest backend\tests\unit\tools\test_account_operator_tools.py backend\tests\unit\runtime\test_broker_runtime_entrypoint.py backend\tests\unit\runtime\test_broker_runtime_orchestrator.py backend\tests\unit\runtime\test_broker_runtime_supervisor.py backend\tests\unit\market_data\test_resolver.py backend\tests\unit\market_data\test_market_data_catalog.py backend\tests\unit\lint -q` -> 267 passed, 2 warnings.
- `npm.cmd test` in `frontend/` -> 42 passed; frontend check passed.
- `npm.cmd test` in `new-frontend/` -> 10 passed; banned-name lint clean.
- `npm.cmd run lint` in `new-frontend/` -> passed.
- `npm.cmd run typecheck` in `new-frontend/` -> passed.
- `npm.cmd run build` in `new-frontend/` -> passed.

Blockers:
- None for this naming cleanup.

Next action:
- Continue Promotion/Program migration shim review, unless operator asks to cut fully to `new-frontend/` first.

Approval status:
- Coordinator-approved under Nanyel doctrine for this cleanup.
## 2026-04-27 12:46:20 -04:00 - Alpaca Account Sync Efficiency Hardening

Work session status: completed

Started at:
- 2026-04-27 12:36:00 -04:00

Last heartbeat:
- 2026-04-27 12:46:20 -04:00

Completed action:
- Used Alpaca-agent review to confirm the target sync model: event-first broker truth, REST only for startup snapshots, reconciliation, open-order polling, and stream failure recovery.
- Confirmed Alpaca Trading API trade update streams are account-scoped, so Ultimate Trader keeps one Account Trade Sync per configured Account unless/until a true Alpaca Broker API SSE integration is introduced.
- Confirmed Alpaca Broker API SSE trade events are the future multi-account-efficient path because broker SSE supports real-time replayable events with `since` / `since_id`.
- Hardened `BrokerSyncService.reconcile(...)` so recurring quiet polling no longer calls broker `get_order` for terminal internal orders (`filled`, `canceled`, `rejected`, `failed`).
- Preserved open broker order detection: broker-side open orders are still fetched and compared against all local client order IDs, so external/missing local orders remain visible.
- Added regression coverage proving terminal historical orders are skipped during quiet polling while active orders are still reconciled.

Files touched:
- `backend/app/brokers/sync.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\brokers\test_broker_sync_reconciliation.py -q` -> 24 passed, 1 warning.
- `python -m pytest backend\tests\unit\brokers -q` -> 109 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1108 passed, 6 warnings.

Resource-efficiency recommendation:
- Keep one always-open Account Trade Sync per Alpaca Account.
- Use stream events as first truth movement.
- Keep REST polling, but make it adaptive: startup/reconnect/full reconcile immediately, open orders every 30-60s when stream is healthy, positions/account every 60-120s, slower off-hours, faster only when degraded or an order is active.
- Add jitter and per-account backoff before scaling beyond the first few Accounts.

Blockers:
- None.

Next action:
- Add an adaptive Account Sync scheduler with per-account jitter/backoff and Operations-visible sync profile, then consider Alpaca Broker API SSE only if the product moves from individual Trading API keys to Broker API-managed accounts.

Approval status:
- Coordinator-approved under Nanyel doctrine. BrokerSync remains the only broker truth writer; BrokerAdapter remains the only broker submission/read boundary; no second runtime introduced.
## 2026-04-27 12:50:47 -04:00 - External Alpaca Order Stream Visibility Fix

Work session status: completed

Started at:
- 2026-04-27 12:47:00 -04:00

Last heartbeat:
- 2026-04-27 12:50:47 -04:00

Completed action:
- Traced Account Trade Sync storage and projection path.
- Confirmed trade streams are in-memory per-account `TradeEventDispatcher` objects, while broker truth snapshots persist in SQLite runtime tables.
- Found live stream error for account `e43733eb-4d90-473b-af46-6aaac06e85f7`: `broker_sync_route_failed:unknown internal order client_order_id: 25f62981-fa75-4932-964d-99ddc9eab1e4`.
- Root cause: Alpaca stream events for broker-side/external orders not created by Ultimate Trader were treated as unknown internal orders and surfaced as stream errors before Operations could preserve them.
- Extended `BrokerOrderUpdateEvent` with optional broker order details needed to preserve external open orders.
- Updated Alpaca stream normalization to carry symbol, side, qty, order type, limit price, and stop price from order payloads.
- Updated `BrokerSyncService.handle_order_update(...)` so unknown external active order updates are persisted as broker open order snapshots through BrokerSync, not treated as stream-route failures.
- Terminal or incomplete external order events still refresh sync state without inventing internal order truth.

Files touched:
- `backend/app/brokers/models.py`
- `backend/app/brokers/stream.py`
- `backend/app/brokers/sync.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\brokers\test_broker_sync_reconciliation.py backend\tests\unit\brokers\test_broker_stream_router.py -q` -> 36 passed, 1 warning.
- `python -m pytest backend\tests\unit\brokers backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\api\test_operations_routes.py -q` -> 137 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1109 passed, 6 warnings.

Blockers:
- Running backend must be restarted to pick up this code change.

Next action:
- Restart backend, then re-check `/api/v1/system/streams` for cleared route error and `/api/v1/operations/accounts/{account_id}` for `open_broker_orders`.

Approval status:
- Coordinator-approved under Nanyel doctrine. BrokerSync remains the only broker truth writer; no internal order is fabricated for external broker orders.
## 2026-04-27 13:05:17 -04:00 - Market Close Validation Readiness Pass

Work session status: completed

Started at:
- 2026-04-27 12:55:00 -04:00

Last heartbeat:
- 2026-04-27 13:05:17 -04:00

Completed action:
- Switched into market-close validation focus: stabilize broker/Operations APIs, verify research path, and create a same-day validation Strategy artifact.
- Fixed Alpaca adapter status normalization so `partial_fill` maps to `BrokerOrderStatus.PARTIAL_FILL`.
- Fixed Operations projection so manual operator orders without Deployment lineage do not produce `None` deployment ids or break `/api/v1/operations/overview`.
- Hardened Strategy repository startup against incompatible legacy `strategies` table shape by archiving old legacy table and recreating the canonical schema.
- Restarted backend on port 8000 after patches.
- Created validation Strategy `Market Close Validation - SPY Momentum Smoke`.
- Created StrategyVersion `SPY 1m momentum smoke v1`.
- Recorded one evidence-backed BacktestRun against `spy_1m_alpaca_sip` to prove research create/list/evidence projection path.
- Added executive runbook at `Operations_Production_Readiness/MARKET_CLOSE_VALIDATION_RUNBOOK.md`.

Files touched:
- `backend/app/brokers/alpaca.py`
- `backend/app/operations/service.py`
- `backend/app/strategies/persistence.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `backend/tests/unit/operations/test_operations_center_service.py`
- `backend/tests/unit/strategies/test_strategy_service.py`
- `Operations_Production_Readiness/MARKET_CLOSE_VALIDATION_RUNBOOK.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Live validation artifacts:
- `strategy_id`: `b928618f-78ec-48c2-80ca-22fbe02dfae0`
- `strategy_version_id`: `4dc3f3d8-60e3-4764-8940-da9e6da1b290`
- `backtest_run_id`: `6ae443c6-1f11-4226-bfff-74ce109bd1e2`

Tests run:
- `python -m pytest backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\api\test_operations_routes.py backend\tests\unit\brokers\test_alpaca_broker_adapter.py backend\tests\unit\brokers\test_broker_sync_reconciliation.py -q` -> 75 passed, 1 warning.
- `python -m pytest backend\tests\unit\strategies\test_strategy_service.py backend\tests\unit\api\test_frontend_api_contract.py -q` -> 12 passed, 5 warnings.
- `python -m pytest backend\tests\unit -q` -> 1110 passed, 6 warnings.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npm.cmd test` in `frontend/` -> 43 passed; banned-name lint clean.
- `npm.cmd run build` in `frontend/` -> passed; Vite chunk-size warning only.

Blockers:
- Full historical backtest engine is not yet wired behind the V1 Backtest API. Current create-run path records research evidence only.

Next action:
- Wire real historical backtest execution behind `/api/v1/backtests` using the shared Feature Engine and SignalPlan path. Do not create a second runtime.

Approval status:
- Approved for same-day operator validation of platform stability and research API path. Not approved yet for performance claims or automated trading promotion.

## 2026-04-27 22:05:12 -04:00 - Strategy Builder / AI Composer Frontend Contract Hardening

Work session status: completed

Started at:
- 2026-04-27 21:59:43 -04:00

Last heartbeat:
- 2026-04-27 22:05:12 -04:00

Completed action:
- Audited the Strategy Builder / AI Composer backend contract surface.
- Confirmed feature catalog lookup, shorthand normalization, condition-tree validation, LogicalExitRule validation, AI draft generation, reuse matching, draft save, and research launch planning are exposed through the Strategies API.
- Added additive `StrategyDraft.launch_plans` for Chart Lab, Backtest async job, and Walk-Forward async job.
- Added tests for requested LogicalExitRule kinds, frontend-safe response cores, and launch-plan payload templates.
- Created Claude handoff doc for direct frontend implementation.

Files touched:
- `backend/app/domain/strategy_draft.py`
- `backend/app/strategy_composer/service.py`
- `backend/app/strategy_composer/__init__.py`
- `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`
- `backend/tests/unit/api/test_strategy_composer_api.py`
- `docs/system_rebuild_outputs/STRATEGY_BUILDER_FRONTEND_CONTRACT.md`
- `COORDINATION/INBOX_CLAUDE.md`
- `COORDINATION/LEDGER.md`
- `COORDINATION/LOCKS.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

Tests run:
- `python -m pytest backend\tests\unit\strategy_composer backend\tests\unit\api\test_strategy_composer_api.py -q` -> 23 passed, 1 warning.
- `python -m pytest backend\tests\unit -q` -> 1221 passed, 6 warnings.

Blockers:
- None.

Next action:
- Claude can build Strategy Builder / AI Composer frontend from `docs/system_rebuild_outputs/STRATEGY_BUILDER_FRONTEND_CONTRACT.md`.

Approval status:
- Approved under Nanyel doctrine. Strategy remains logic-only; Strategy does not own Risk or Universe; composer save is draft-only; no Deployment, Account attachment, broker action, or live-readiness claim is created.
