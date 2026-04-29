# Production Readiness Execution Plan

This is the sequenced plan from current state to production-ready
Ultimate Trader. Slices are sized for one-PR delivery. Every slice
ships its final shape (no temporary paths, no stubs, no patching).

Legend:
- **LOE** estimates assume one focused engineer-day per unit.
- **Owner** is the agent best suited to lead (Claude / Codex / Cursor /
  VS Code), confirmed in [AGENT_TASK_MATRIX.md](./AGENT_TASK_MATRIX.md).
- **Best tool** is the primary tool for the slice's main work.
- **Gates** are blocking pre-conditions. **Exit criteria** are the
  proofs that close the slice.

## Slice ordering principle

1. Ship doctrine guardrails first so future PRs cannot regress.
2. Build domain + persistence + service for each spine module before
   API or UI consumes it.
3. Wire one spine slice end-to-end (publisher → evaluator →
   resolver → governor → order → broker → sync → position) before
   filling out research surfaces.
4. Frontend pages come after their backing read-model exists.
5. Promotion / cutover comes last and is rehearsed.

---

## Phase 0 — Doctrine guardrails (1.5 days, parallelizable)

### S0.1 — Banned-name lint expansion
- Owner: Claude
- Best tool: Grep + small pytest extension to existing
  `backend/tests/unit/lint/test_no_banned_mode_enums.py`.
- LOE: 0.5
- Files: new `backend/tests/unit/lint/test_no_banned_product_names.py`,
  new `frontend/scripts/lint-banned-names.mjs`.
- Tests: pytest + node test runner.
- Gates: AGENTS.md and NAMING_CONTRACT.md frozen.
- Exit: `pytest backend/tests/unit/lint -q` passes; `npm test
  --prefix frontend` passes; new tests fail loudly when "Program",
  "Account Governor", "Services Center", "Paper Runtime", "Live
  Runtime" appear in production code (excluding doctrine docs and
  archived folders).

### S0.2 — Architecture import guardrail
- Owner: Codex
- Best tool: AST-based import scan in pytest.
- LOE: 0.5
- Files: extend `backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py`.
- Tests: import scan ensures `backend/app/runtime/` does not import
  `domain.program` once spine is migrated; for now, mark known
  legacy imports and add a regression watchlist.
- Gates: S0.1 in.
- Exit: New test runs in CI; legacy imports listed under a
  `_PROGRAM_LEGACY_ALLOWLIST` that empties as later slices land.

### S0.3 — Operation status board live
- Owner: Claude
- Best tool: Edit / Write.
- LOE: 0.25
- Files: `Operations_Production_Readiness/OPERATION_STATUS.md`.
- Gates: this folder created.
- Exit: status board contains a heartbeat entry per slice, updated by
  whichever agent runs that slice.

---

## Phase 1 — Domain + Persistence backbone (3 days)

### S1.1 — Strategy / Watchlist / Deployment / SignalPlan persistence
- Owner: Codex
- Best tool: Edit + pytest.
- LOE: 1
- Files: `backend/app/persistence/models.py`, `runtime_store.py`,
  `backend/tests/unit/persistence/test_sqlite_persistence.py`.
- Tables: `strategies`, `strategy_versions`, `watchlists`,
  `watchlist_snapshots`, `deployments`, `signal_plans`,
  `account_signal_plan_evaluations`, `governor_decision_traces`,
  `position_lineages`, `account_risk_configs`,
  `account_restrictions`.
- Gates: S0.1 in.
- Exit: persistence round-trips for each new table; reconciliation
  test demonstrates indexes resolve `(account_id, deployment_id)`,
  `(deployment_id, status)`, `(account_id, signal_plan_id)`.

### S1.2 — Strategy + Watchlist services
- Owner: Codex
- Best tool: Edit + pytest.
- LOE: 1
- Files: new `backend/app/strategies/` package (service.py,
  models.py, runtime_service.py), new `backend/app/watchlists/`.
- Domain: `StrategyVersion` (existing), new `WatchlistVersion`,
  `WatchlistSnapshot`, `WatchlistMembershipRule`.
- Gates: S1.1.
- Exit: unit tests for create / list / version / freeze / validate
  per service; lint guardrails pass.

### S1.3 — Deployment service (without publisher loop)
- Owner: Codex
- Best tool: Edit + pytest.
- LOE: 1
- Files: new `backend/app/deployments/` package (service.py,
  models.py).
- Capabilities: create deployment with `strategy_version_id`,
  `watchlist_ids[]`, `subscribed_account_ids[]`,
  `runtime_overrides`; list, get, update, delete (when safe);
  start/stop/pause/resume/flatten (delegating to control plane and
  runtime supervisor).
- Gates: S1.1, S1.2.
- Exit: unit tests for lifecycle transitions; control plane gates
  pause / resume; recovery state respected.

---

## Phase 2 — DeploymentPublisher + Account Evaluator (4 days)

### S2.1 — DeploymentPublisher runtime
- Owner: Codex (Claude reviews doctrine)
- Best tool: Edit + pytest + Plan agent for design.
- LOE: 1.5
- Files: new `backend/app/runtime/deployment_publisher.py`,
  refactor `backend/app/runtime/__init__.py`.
- Behavior: per-tick `evaluate_entries(watchlist)` and
  `evaluate_exits(positions filtered by deployment_id)`, emit
  `SignalPlan` records via `SignalPlanBuilder`. Idempotent per
  `(deployment_id, evaluation_tick, symbol, intent)`. Persists
  SignalPlan with status `CREATED` then `PUBLISHED`.
- Gates: S1.1, S1.2, S1.3.
- Exit: tests show one Deployment evaluating Watchlist and Positions
  emits the right SignalPlan kinds; running twice does not duplicate;
  paused Deployment emits nothing; PositionLineage filter is correct.

### S2.2 — AccountSignalPlanEvaluator
- Owner: Codex
- Best tool: Edit + pytest.
- LOE: 1
- Files: new `backend/app/decision/account_evaluator.py`,
  `backend/app/runtime/runtime_context.py` (wire registry).
- Behavior: subscribe to published SignalPlans; for each subscribed
  Account, persist `AccountSignalPlanEvaluation` with explicit
  participation_decision and rejection reasons; if PARTICIPATE,
  call RiskResolver; if allowed, call Governor; if approved, hand
  to OrderManager. Idempotent per `(account_id, signal_plan_id)`.
- Gates: S2.1, governor + risk_resolver refactor (next slices) —
  this slice ships a stub for those calls behind feature gates so
  the loop is observable; the *real* governor / risk_resolver land
  in S2.3 / S2.4 within the same phase.
- Exit: tests show one SignalPlan, two Accounts, two distinct
  evaluations.

### S2.3 — RiskResolver wiring with AccountRiskConfig
- Owner: Codex
- Best tool: Edit + pytest.
- LOE: 0.75
- Files: `backend/app/risk_resolver/service.py`,
  `backend/app/broker_accounts/models.py` (add `AccountRiskConfig`
  fields or new model), `backend/app/risk_resolver/contexts.py`.
- Replace: `StaticSizingInput` / `LifecycleSizingInput` with
  `AccountRiskContext` derived from the persisted Account risk
  config + Account snapshot + broker capability.
- Gates: S1.1 (account_risk_configs), S2.2.
- Exit: tests show fixed-shares, fixed-dollar, risk-percent-equity
  sizings produce correct results; fractional vs whole-share rounding
  policy honored; broker capability filters.

### S2.4 — Governor refactor + GovernorDecisionTrace
- Owner: Codex (Claude reviews)
- Best tool: Edit + pytest.
- LOE: 0.75
- Files: `backend/app/governor/service.py`,
  `backend/app/governor/models.py`,
  `backend/tests/unit/governor/test_portfolio_governor.py`.
- Behavior: accept `(SignalPlan, RiskResolverResult, AccountContext,
  PolicyState)`; emit `GovernorDecisionTrace`; persist; legacy
  `GovernorDecision` retained only as internal helper or removed.
- Gates: S2.2, S2.3.
- Exit: tests show all banned conditions reject, all allowed
  conditions approve, every decision is persisted with full reasons.

### S2.5 — OrderManager SignalPlan-driven entrypoint
- Owner: Codex (Claude doctrine review)
- Best tool: Edit + pytest.
- LOE: 1
- Files: `backend/app/orders/manager.py`, `models.py`,
  `backend/tests/unit/orders/test_order_manager.py`.
- Behavior: `create_orders_from_evaluation(account_id, signal_plan,
  risk_result, governor_trace)` returns the entry order plus
  protective leg orders for an opening plan; for related plans,
  returns the position-management orders. Legacy
  `create_order(execution_intent=...)` flagged as deprecated and
  wrapped behind a no-op shim that raises if called from
  non-manual-trade callers (manual trade keeps its own path).
- Gates: S2.4.
- Exit: tests show full lineage columns populated end-to-end;
  protective intents bypass open-only governor checks; idempotency
  enforced.

---

## Phase 3 — Position Lineage + Operations extension (2 days)

### S3.1 — PositionLineage service
- Owner: Codex
- Best tool: Edit + pytest.
- LOE: 1
- Files: new `backend/app/positions/` package (service.py,
  models.py).
- Behavior: build a `PositionLineage` per opening SignalPlan that
  filled; update on related SignalPlans, fills, partial closes;
  produce `PositionExplanationContext` on demand.
- Gates: S2.5.
- Exit: tests show open → partial close → full close lineage; tests
  show explanation context returns all required fields.

### S3.2 — Operations Center extensions
- Owner: Cursor (UI-adjacent backend) or Codex
- Best tool: Edit + pytest.
- LOE: 1
- Files: `backend/app/operations/service.py`,
  `backend/app/api/routes/operations.py` (extend with
  `/signal-plans`, `/evaluations`, `/governor-decisions`,
  `/positions`, `/positions/{lineage_id}/explain`).
- Gates: S2.x and S3.1.
- Exit: API tests show the timelines per-Deployment, per-Account,
  per-Strategy, per-symbol.

---

## Phase 4 — Strategies / Watchlists / Deployments API (2 days)

### S4.1 — Strategies route
- Owner: Cursor or Codex
- Best tool: Edit + pytest.
- LOE: 0.75
- Files: new `backend/app/api/routes/strategies.py`, register in
  `backend/app/api/server.py`.
- Gates: S1.2.
- Exit: CRUD + freeze + validate; API tests pass.

### S4.2 — Watchlists route
- Owner: Cursor or Codex
- Best tool: Edit + pytest.
- LOE: 0.75
- Files: new `backend/app/api/routes/watchlists.py`.
- Gates: S1.2.
- Exit: CRUD + snapshot + preview; API tests pass.

### S4.3 — Deployments route
- Owner: Cursor or Codex
- Best tool: Edit + pytest.
- LOE: 0.5
- Files: new `backend/app/api/routes/deployments.py`.
- Gates: S1.3, S2.1.
- Exit: CRUD + start/stop/pause/resume/flatten + subscribe; API
  tests pass.

---

## Phase 5 — Account Risk + Position Explain APIs (1 day)

### S5.1 — Account risk-config + restrictions routes
- Owner: Cursor
- Best tool: Edit + pytest.
- LOE: 0.5
- Files: extend `backend/app/api/routes/broker_accounts.py` (or new
  `account_risk.py`).
- Gates: S2.3.
- Exit: GET / PUT for risk config; GET / PUT for restrictions;
  composed `risk-card` read.

### S5.2 — Position explain + AI advisory route
- Owner: Cursor
- Best tool: Edit + pytest.
- LOE: 0.5
- Files: extend operations.py and ai.py.
- Gates: S3.1.
- Exit: explain returns canonical context; AI advisory accepts the
  context only (never raw provider input from the frontend).

---

## Phase NF — New frontend (full redesign, replaces old `frontend/`)

The current `frontend/` is rejected per
[FRONTEND_STRUCTURE_DECISION.md](./FRONTEND_STRUCTURE_DECISION.md).
The new app is built in `new-frontend/`, then renamed to `frontend/`
at cutover. The old `frontend/` is deleted at NF.5.

Stack (subject to operator confirmation): React + TypeScript +
Vite + Tailwind + Radix UI + TanStack Query + TanStack Router +
Zustand + lightweight-charts + Lucide + Vitest + Playwright.

Phase NF runs in parallel with backend Phases 1–5 from the moment
the operator approves the stack. Pages render empty-states cleanly
for any read-model that has not landed yet.

### NF.0 — Scaffold
- Owner: Cursor
- Best tool: Edit + npm.
- LOE: 1
- Files: new `new-frontend/` tree (vite.config.ts, tsconfig.json,
  tailwind.config.ts, eslint, prettier, src/main.tsx, src/api/client.ts,
  src/api/ws.ts, src/styles/theme.css, app shell layout, system
  status badge).
- Gates: S0.1 banned-name guardrail extended to cover the new
  source tree; operator approves stack and folder convention.
- Exit: dev server boots; type-check + Vitest + ESLint clean;
  banned-name lint runs in CI; theme tokens load; app shell renders
  with placeholder routes.

### NF.1 — Operations parity
- Owner: Cursor
- LOE: 2
- Files: routes for Operations + drill-ins, hooks for
  `/api/v1/operations/*`, system streams panel, trade stream WS
  hook, global kill / pause / resume / flatten with Danger
  primitive.
- Gates: NF.0.
- Exit: new Operations matches the old Operations on every panel
  the old one had, plus a Position Explain drawer scaffold;
  component tests pass; broker-safe E2E covers kill/pause/resume.

### NF.2 — Accounts + Providers + Settings
- Owner: Cursor
- LOE: 2
- Files: Accounts list/detail with inline credential editor,
  Providers (Market Data + AI tabs) with provider cards, Settings
  (platform preferences only).
- Gates: NF.1.
- Exit: full CRUD against existing endpoints; component tests pass;
  no banned product names; explainer drawer wired.

### NF.3 — Strategies, Watchlists, Deployments, Components, Dashboard
- Owner: Cursor (depends on backend Phase 1–4 read-models)
- LOE: 3
- Files: routes/components for the four mandated new surfaces plus
  Dashboard.
- Gates: backend Phase 1 (S1.2, S1.3) and Phase 4 routes (S4.1,
  S4.2, S4.3) for the corresponding surface; Dashboard depends on
  S7.0 below.
- Exit: each surface renders empty/happy/degraded states; type-safe
  against backend Zod schemas; component tests pass.

### NF.3a — Dashboard read-model (server)
- Owner: Codex (parallel with NF.3 Dashboard)
- LOE: 0.5
- Files: new `backend/app/api/routes/dashboard.py`.
- Gates: backend Phase 2 spine (so the read can include recent
  SignalPlans / open positions / signals today). May ship a
  partial-fields version earlier with explicit `null`s.

### NF.4 — Research surfaces (Chart Lab, Sim Lab, Backtests, Optimization, Walk-Forward)
- Owner: Cursor + Codex (APIs from Phase 8 backend)
- LOE: 2
- Files: routes/components/hooks against research APIs.
- Gates: backend Phase 8 APIs land for the corresponding surface.
- Exit: research evidence renders for all five drill-ins; charts
  use lightweight-charts.

### NF.5 — Cutover and deletion of old `frontend/`
- Owner: Cursor (rename) + Claude (review) + Operator (approve)
- LOE: 0.5
- Files: delete `frontend/`; rename `new-frontend/` → `frontend/`;
  update `package.json` scripts and any references (`docs/`, CI
  scripts, repo `package.json`).
- Gates: NF.1–NF.4 complete; nine mandated surfaces feature-parity
  reached; broker-safe E2E green; operator approves cutover.
- Exit: repo has one frontend; operator's bookmark serves the new
  app; archived references purged; banned-name lint passes against
  the renamed `frontend/` tree.

---

## Phase 9 — Promotion + Migration + Cutover (2 days)

### S9.1 — Promotion gate refactor (StrategyVersion-keyed)
- Owner: Codex
- LOE: 0.5
- Files: `backend/app/promotion/service.py`,
  `backend/tests/unit/promotion/test_promotion_gate.py`.
- Exit: gate evaluates by `strategy_version_id` + paper deployment
  evidence; legacy program-keyed path quarantined behind a single
  migration call.

### S9.2 — Program → Strategy/Deployment migration
- Owner: Codex
- LOE: 0.5
- Files: `backend/app/api/routes/system_migration.py` (add migration
  endpoint), `backend/app/persistence/runtime_store.py` (one-time
  migration).
- Exit: any persisted Program-style records translate cleanly into
  Strategy + Deployment + Watchlist; or backend refuses to start
  with a clear operator error if migration is required and not yet
  performed.

### S9.3 — Retire Program from runtime + domain
- Owner: Claude (review) + Codex (delete)
- LOE: 0.5
- Files: delete `backend/app/domain/program.py` (or move to
  `archive_knowledge_do_not_open_sustaining`); remove all imports
  from `backend/app/runtime/`, `backend/app/orders/`,
  `backend/app/operations/`.
- Exit: import guardrail (S0.2) `_PROGRAM_LEGACY_ALLOWLIST` is empty.

### S9.4 — Day Zero rehearsal
- Owner: Claude
- LOE: 0.5
- Files: log run results into `Operations_Production_Readiness/
  cutover-rehearsal-<date>.md`.
- Exit: full Day Zero Runbook passes on a paper Account end-to-end
  with no manual log fishing.

---

## First 10 tasks to execute (prioritized)

| # | Task | Slice | Owner | Gate |
|---|---|---|---|---|
| 1 | Approve this plan | — | Nanyel (operator) | None — operator decision |
| 2 | Banned-name lint expansion | S0.1 | Claude | (1) |
| 3 | Architecture import guardrail | S0.2 | Codex | (2) |
| 4 | OPERATION_STATUS.md heartbeat live | S0.3 | Claude | (1) |
| 5 | Persistence: strategies/watchlists/deployments/signal_plans/evaluations/governor_traces/position_lineages/account_risk_configs/account_restrictions | S1.1 | Codex | (3) |
| 6 | Strategy + Watchlist services | S1.2 | Codex | (5) |
| 7 | Deployment service (no publisher yet) | S1.3 | Codex | (6) |
| 8 | DeploymentPublisher | S2.1 | Codex (Claude reviews) | (7) |
| 9 | AccountSignalPlanEvaluator | S2.2 | Codex | (8) |
| 10 | Governor refactor + GovernorDecisionTrace + RiskResolver Account-driven inputs (parallel pair, must land together) | S2.3+S2.4 | Codex | (9) |

Each task is gated by both a domain readiness check and a doctrine
review by Claude before merge. No task may regress an existing
production-grade module.

## What can run in parallel

- S0.1, S0.2, S0.3 are independent.
- S1.2 (Strategy) and the Watchlist service inside S1.2 can run in
  parallel once S1.1 lands.
- Phase 4 routes (S4.1, S4.2, S4.3) can run in parallel after the
  services land.
- **Phase NF (new frontend) runs in parallel with backend Phases
  1–5 from the moment the operator approves the stack.** NF.0 can
  start the same hour Phase 0 ends. NF.1 (Operations parity) lands
  against the existing operations API and does not block on the
  backend rebuild. NF.2 (Accounts/Providers/Settings) likewise.
- NF.3 surfaces each block only on their corresponding backend
  read-model: Strategies on S1.2 + S4.1, Watchlists on S1.2 + S4.2,
  Deployments on S1.3 + S4.3, Dashboard on NF.3a.
- NF.4 research surfaces gate only on Phase 8 APIs and are parallel
  to each other.

## What must run serial

- The Phase 2 spine slices (S2.1 → S2.2 → S2.5) form the production
  loop and must land in order; S2.3 and S2.4 can land between S2.2
  and S2.5 but must be merged before S2.5 wires the new
  OrderManager entrypoint.
- S3.1 must land before S3.2.
- S9.1 / S9.2 / S9.3 are strictly serial with S9.4 last.
- NF.0 → NF.1 → NF.2 → NF.3 → NF.4 → NF.5 is the new-frontend
  serial chain. NF.5 cutover cannot run until every other NF phase
  is complete and the broker-safe E2E is green.

## Slice quality bar (every PR must satisfy)

- No banned product names introduced.
- No new direct-provider call from the frontend.
- No new broker-truth writer outside BrokerSync.
- New service has unit tests + at least one integration / end-to-end
  test where the slice claims behavior.
- New API has API test.
- New UI page has node test (renders empty / happy / degraded).
- `OPERATION_STATUS.md` updated with start_at, current phase,
  completed actions, files touched, tests run, approval status.
