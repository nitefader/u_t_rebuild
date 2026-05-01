# 02 Frontend / Website Page Audit

Scope reviewed: React routes, side navigation, page-level API clients, obvious disabled/dead controls, mocked/awaiting panels, and operator-facing doctrine alignment.

## Findings

### F01 - Strategy creation has two active routes, and primary links still use the old Composer

- severity: high
- file path: `frontend/src/router.tsx`, `frontend/src/components/layout/SideNav.tsx`, `frontend/src/routes/Strategies.tsx:52`, `frontend/src/routes/StrategyDetail.tsx:118`, `frontend/src/routes/StrategyBuilder.tsx:253`, `frontend/src/routes/StrategyCompose.tsx:321`
- issue: The router exposes both `/strategies/compose` and `/strategies/compose-v4`. SideNav points to v4, but Strategies, StrategyDetail, and StrategyBuilder still link to `/strategies/compose`. The old route contains a skip-wizard stub and labels itself `Composer`.
- why it matters: Operators can enter two different authoring systems. That creates duplicate product paths and stale terminology.
- recommended fix: Choose v4 as the primary route, update all creation links/tests, and retire or redirect `/strategies/compose` after any needed migration.
- suggested agent prompt: "Make Strategy Compose v4 the only primary strategy authoring entry point. Update route links, tests, and copy. Redirect or quarantine legacy /strategies/compose without keeping it as an active product path."

### F02 - Operations timeline calls missing SignalPlan and GovernorDecision routes

- severity: high
- file path: `frontend/src/api/timelines.ts:24`, `frontend/src/api/timelines.ts:59`, `frontend/src/routes/OperationsTimelines.tsx:83`, `frontend/src/routes/OperationsTimelines.tsx:272`, `backend/app/api/routes/operations.py:145`
- issue: Frontend calls `/api/v1/operations/signal-plans` and `/api/v1/operations/governor-decisions`, but backend only registers `/api/v1/operations/evaluations` for this timeline family.
- why it matters: Operations cannot trace the full runtime spine. Operators see "awaiting" panels instead of live SignalPlan/Governor visibility.
- recommended fix: Add backend read models/routes or remove the tabs until the routes exist. Keep Account evaluations tab live because its backend route exists.
- suggested agent prompt: "Implement Operations read models for SignalPlans and GovernorDecision traces, register `/api/v1/operations/signal-plans` and `/api/v1/operations/governor-decisions`, then update Operations tests to expect data instead of 404."

### F03 - Operations tests explicitly bless missing timeline routes

- severity: high
- file path: `frontend/src/routes/Operations.test.tsx:55`
- issue: Tests mock 404 for SignalPlans, evaluations, and GovernorDecision endpoints. Backend now has evaluations, but the test still treats it as awaiting in several cases.
- why it matters: A user-facing broken path can pass as intentional. This hides runtime observability gaps.
- recommended fix: Update tests to reflect registered `/operations/evaluations`; add failing expectations for missing SignalPlan/Governor routes until repaired.
- suggested agent prompt: "Refresh Operations timeline tests so registered routes must return real data. Keep 404-awaiting behavior only for endpoints that are intentionally absent."

### F04 - Position explanation drawer is not backed by API routes

- severity: high
- file path: `frontend/src/routes/PositionExplainDrawer.tsx:29`, `frontend/src/api/positions.ts:17`, `backend/app/api/routes/broker_accounts.py:61`, `backend/app/api/routes/ai.py:40`
- issue: UI expects `GET /api/v1/broker-accounts/{account}/positions/{lineage}/explain` and `POST /api/v1/ai/explain-position`. Backend broker account and AI routers do not register those paths.
- why it matters: Position Truth -> Operations explanation is part of doctrine. The operator cannot inspect why a position exists or what manages it.
- recommended fix: Implement a PositionLineage explanation route from Account-owned position truth and add an optional AI advisory endpoint that consumes the deterministic context.
- suggested agent prompt: "Build the Position explanation backend boundary: deterministic position context first, AI advisory second. Wire PositionExplainDrawer to real routes and tests."

### F05 - Walk-forward detail panels advertise missing subroutes

- severity: medium
- file path: `frontend/src/routes/WalkForward.tsx:267`, `frontend/src/routes/WalkForward.tsx:280`, `frontend/src/routes/WalkForward.tsx:293`, `frontend/src/routes/WalkForward.tsx:306`, `backend/app/api/routes/research_runs.py:646`
- issue: The Walk Forward page has panels for folds, parameter stability, OOS regime breakdown, and equity curve, but backend registers only list/create/get/delete/save-risk-plan for walk-forward runs.
- why it matters: The route appears feature-complete but important diagnostic data never loads.
- recommended fix: Either register the subroutes from persisted run metrics or collapse the panels to fields that actually exist.
- suggested agent prompt: "Wire WalkForward detail panels to real backend data. Add subroutes or remove panels until the data model exists; update tests to stop accepting placeholder-only detail states."

### F06 - Backtest page has stale awaiting copy for registered results/metrics endpoints

- severity: medium
- file path: `frontend/src/routes/Backtests.tsx:374`, `frontend/src/routes/Backtests.tsx:392`, `backend/app/api/routes/research_runs.py:377`, `backend/app/api/routes/research_runs.py:392`
- issue: UI says metrics/results endpoints are not registered, but backend registers both under `/api/v1/research/backtests/{run_id}/results` and `/metrics`.
- why it matters: Operators can misread real 5xx/contract failures as normal awaiting work.
- recommended fix: Replace stale awaiting copy with real loading/error messages and ensure endpoint errors are surfaced honestly.
- suggested agent prompt: "Update Backtests endpoint state copy now that results and metrics routes exist. Add tests for 404 vs 500 behavior."

### F07 - Operator-facing IDs are still primary labels in several Operations surfaces

- severity: medium
- file path: `frontend/src/routes/OperationsTimelines.tsx:206`, `frontend/src/routes/OperationsTimelines.tsx:311`, `frontend/src/routes/AccountDetailDrawer.tsx:360`, `frontend/src/routes/Operations.tsx:731`, `frontend/src/routes/Operations.tsx:927`, `frontend/src/components/backtests/RiskDecisionCardDrawer.tsx:181`
- issue: Account, Deployment, Strategy version, SignalPlan, and order IDs appear as primary labels in tables/cards/drawers.
- why it matters: AGENTS.md requires operator-facing data to prefer display names, symbols, account names, deployment names, strategy names, readable statuses, and reason codes before raw IDs.
- recommended fix: Extend backend DTOs or frontend lookup joins with display names. Keep raw IDs as copyable secondary detail.
- suggested agent prompt: "Audit Operations and risk drawers for raw UUID-first displays. Add readable names/labels to DTOs or client joins, and move raw IDs to secondary detail."

### F08 - Strategy Builder research action links are disabled placeholders

- severity: medium
- file path: `frontend/src/components/strategy_builder/editor/EditorPage.tsx:301`
- issue: `Verify in Backtest`, `Sim Lab`, and `Chart Lab` render as disabled links with `href="#"`.
- why it matters: These are natural next steps after authoring a Strategy. Disabled anchor controls read like connected workflow but do nothing.
- recommended fix: Wire to real routes with draft/version context or hide until a saved StrategyVersion exists.
- suggested agent prompt: "Wire Strategy Builder research action links to Backtest, Sim Lab, and Chart Lab with saved StrategyVersion context. Hide or disable with clear saved-version prerequisite only when unavailable."

### F09 - Full frontend test run is order-sensitive/flaky

- severity: high
- file path: `frontend/src/routes/StrategyComposeV4.test.tsx`, `frontend/src/strategy_ide_v4/StarterStrategyPanel.test.tsx`, `frontend/src/strategy_ide_v4/starterStrategies.ts:50`
- issue: `npm.cmd test` failed with two suites failing to collect around `starterStrategies.ts`, but targeted reruns of both suites passed.
- why it matters: CI can fail nondeterministically and hide actual regressions in the strategy IDE.
- recommended fix: Investigate shared global state, crypto/randomUUID mocking, test isolation, and Vitest config. Make full test order deterministic.
- suggested agent prompt: "Debug full Vitest order sensitivity around StrategyComposeV4 and StarterStrategyPanel. Reproduce with randomized/shuffled order if available, isolate global crypto/mock leakage, and add cleanup."

### F10 - Monaco integration looks mostly healthy

- severity: low
- file path: `frontend/src/strategy_ide_v4/strategyExprMonacoProviders.ts:19`, `frontend/src/strategy_ide_v4/strategyExprMonacoProviders.ts:27`, `frontend/src/strategy_ide_v4/strategyExprMonacoProviders.ts:238`
- issue: No blocking issue found. The provider uses one global registration and disposes previous completion/hover providers.
- why it matters: Monaco completion providers can duplicate if registered repeatedly. This file already handles that pattern.
- recommended fix: Keep the global-disposable pattern and add regression tests if more providers are introduced.
- suggested agent prompt: none.
