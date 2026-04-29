# Screener / Watchlist UX Fix Plan

Last updated: 2026-04-29 08:06:24 -04:00

## Understanding

The operator asked for the Screener and Watchlist UX findings to be turned into an executable fix plan and shipped under MAP. This slice is a product/readability pass on the discovery flow:

Screener discovery -> Watchlist entry universe -> Deployment entry attachment.

It does not change Strategy logic, SignalPlan generation, Account evaluation, RiskResolver, Governor, Order submission, BrokerAdapter, BrokerSync, or Position truth.

## Relevant System Areas

- `frontend/src/routes/Screeners.tsx`
- `frontend/src/routes/ScreenerDetail.tsx`
- `frontend/src/routes/Watchlists.tsx`
- `frontend/src/components/screener/UniverseSourcePicker.tsx`
- `frontend/src/components/screener/CriteriaEditor.tsx`
- `frontend/src/components/screener/ExpressionPreview.tsx`
- `frontend/src/components/screener/ResultsTable.tsx`
- `frontend/src/components/screener/DiscoveryScheduleControls.tsx`
- Focused route/component tests for those files

## Current Behavior From Code

- Screeners and Watchlists correctly state entry-only doctrine.
- Screener detail exposes run/rerun/compare/save controls, but the labels do not clearly distinguish latest-version actions from selected-run actions.
- Schedule execution history uses short run/snapshot ids as primary visible labels.
- Schedule weekday selection is a raw numeric text input.
- Criterion fallbacks can expose raw field/operator syntax.
- Results table renders every metric with a value and labels the evidence column `Why blocked`, even for matched rows.
- Manual Screener create hides source, timeframe, sorting, tags, and max result defaults.
- Explicit-symbol universe input stores local draft state that can diverge from reset form state.

## Problem / Gap

The flow is doctrine-aligned but too control-dense for operator approval. The UI still asks users to infer which run a button affects and exposes internal-looking representations where readable labels should lead.

## Proposed Solution

Ship a minimal frontend/readability patch:

1. Rename and scope actions:
   - `Run latest version`
   - `Rerun selected run`
   - `Compare with previous run`
   - `Save selected matches`
2. Replace raw schedule weekday input with weekday chips.
3. Replace short-ID schedule execution labels with readable run/snapshot labels; keep ids only in hover/debug text.
4. Add readable criterion formatting for booleans, operators, and field labels.
5. Add ResultsTable column presets and rename `Why blocked` to `Decision reason`.
6. Add template search/show-all behavior.
7. Add advanced run settings to manual Screener creation.
8. Sync `UniverseSourcePicker` explicit-symbol draft state from the controlled value.

## Implementation Plan

- Patch the focused frontend files only.
- Update focused tests to assert human-readable labels and weekday chips.
- Run targeted vitest suites, typecheck, and name lint.
- Ask fresh UX, Nanyel/product, and test-mapper experts to review the final diff.
- Release leases and notify Claude via coordination files.

## Validation Checklist

- Strategy remains symbol-agnostic: verified. This slice touched Screener/Watchlist/Deployment frontend copy and controls only; Strategy files and Strategy logic were not changed.
- SignalPlan correctness: verified. Deployment copy now states entries come from Watchlists and exits come from Account-owned Positions scoped to the Deployment; SignalPlan generation was not changed.
- Feature Engine compatibility: verified. Criterion/result formatting changes are frontend-only and preserve API metric keys.
- No duplicate system introduced: verified. No backend, broker, Account, RiskResolver, Governor, BrokerSync, or Position truth path was changed.
- UI to Backend alignment: verified. Focused frontend tests, full frontend suite, typecheck, name lint, headless script syntax check, and whitespace check passed.

## Expert Findings

- UX/front-end engineer: approved. The action labels now distinguish latest-version, selected-run, schedule, and save-to-Watchlist actions. Remaining risks are non-blocking accessibility/polish items.
- Nanyel/product owner: approved. Doctrine risk is clear: Screeners remain discovery-only, Watchlists remain entry-only, and exits remain Account/Position-owned.
- Test mapper: approved. No further test gate required before closeout; new test files must be included with the final checkpoint.

## Verification Run

- `npx.cmd vitest run src/routes/Screeners.test.tsx src/routes/ScreenerDetail.test.tsx src/routes/Watchlists.test.tsx src/routes/Deployments.test.tsx src/components/screener/DiscoveryScheduleControls.test.tsx src/components/screener/ResultsTable.test.tsx src/components/screener/UniverseSourcePicker.test.tsx src/components/screener/ExpressionPreview.test.tsx` -> 24 passed.
- `npm.cmd test` in `frontend/` -> 44 files / 308 tests passed; `lint:names` clean.
- `npm.cmd run typecheck` in `frontend/` -> passed.
- `node --check scripts/headless-screener-watchlist.mjs` in `frontend/` -> passed.
- `git diff --check` -> passed with CRLF warnings only.
