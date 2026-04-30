# Bracket Execution Program — Agent Log

Started: 2026-04-29 21:52:19 -04:00
Owner: Claude (operator override end-to-end)
MAP: Operations_Turtle_Shell_Artifacts/STRATEGY_TO_BROKER_BRACKET_PROGRAM.md

---

## Pass 0 — Pre-flight (online research, doctrine reads, MAP draft, leases)

- pass number: 0
- timestamp: 2026-04-29 21:52:19 -04:00
- files changed:
  - Operations_Turtle_Shell_Artifacts/STRATEGY_TO_BROKER_BRACKET_PROGRAM.md (new)
  - docs/agent_logs/2026-04-29_21-52-19_bracket_execution.md (this file)
  - COORDINATION/LOCKS.md (leases pending)
  - COORDINATION/INBOX_CODEX.md (heads-up pending)
- decisions made:
  - D1–D10 in MAP §7 (default mode = post_fill_bracket, native is optional, doctrine name = ExecutionPlan, OCO is the post-fill exit pair, ProtectiveOrderPlacer is a subscriber, idempotency key = (signal_plan_id, covered_qty_breakpoint), TOCTOU fix = single conn + WAL, daily-state source = BrokerSync, Alpaca capabilities defaults to false until T-4, production-grade only).
- blockers and 5 Whys:
  - none — pre-flight completed.
- tests run:
  - baseline: backend `python -m pytest backend/tests/unit -q` → 1476 passed.
  - baseline: frontend `npm test --run` → 379 passed across 51 files.
- test results:
  - both green at handoff baseline.
- remaining gaps:
  - all 7 slices pending implementation.
- next action:
  - file leases, file Codex heads-up, begin T-1 (persistence trio).

---

## Pass 1 — T-1 baseline (persistence trio)

- pass number: 1 (T-1 baseline)
- timestamp: 2026-04-29 22:30:00 -04:00
- files changed:
  - `backend/app/domain/execution_style.py` (added `ExecutionMode` enum + `execution_mode` field on `ExecutionStyleVersion` + doctrine docstring)
  - `backend/app/deployments/models.py` (added `strategy_controls_version_id`, `execution_plan_version_id`, `risk_plan_version_id` to `Deployment` + `DeploymentWriteRequest`)
  - `backend/app/deployments/service.py` (round-trip new FKs in `create_deployment` + `update_deployment`)
  - `backend/app/strategy_controls/{__init__,models,persistence}.py` (new package — `StrategyControlsRepository`, `StrategyControlsVersionRecord`, `StrategyControlsVersionNotFoundError`)
  - `backend/app/execution_plans/{__init__,models,persistence}.py` (new package — `ExecutionPlanRepository`, `ExecutionPlanVersionRecord`, `ExecutionPlanVersionNotFoundError`)
  - `backend/app/strategy_composer/service.py` (constructor accepts both repos; `save_draft` now persists controls + plan; helpers return `(payload, persisted_version_id)` tuples)
  - `backend/app/api/routes/strategies.py` (composer route now wires both repos against the runtime DB)
  - `backend/tests/unit/strategy_controls/test_strategy_controls_repository.py` (new — 6 reload-survival tests)
  - `backend/tests/unit/execution_plans/test_execution_plan_repository.py` (new — 6 reload-survival tests, includes native_alpaca_bracket round-trip)
  - `backend/tests/unit/strategy_composer/test_save_draft_persists_versioned_components.py` (new — 3 acceptance tests)
- decisions made:
  - D3 in MAP: Python class identity stays `ExecutionStyleVersion`; new persisted entity uses doctrine name `execution_plan_versions` (table) + `execution_plan_version_id` (FK). Renaming the 94 import sites is a follow-up slice. No parallel paths — there is one model class and one persistence path.
  - Deployment is the binder: FKs `strategy_controls_version_id`, `execution_plan_version_id`, `risk_plan_version_id` go on `deployments`, not on `strategy_versions`. Locked in `feedback_deployment_is_the_binder.md` memory entry.
  - `_persist_*` helpers return `(payload, version_id)` tuples; `version_id` is `None` when no repo is wired (test harness without persistence). The response only carries the version_id when the row is actually durable.
- blockers and 5 Whys: none — T-1 baseline shipped cleanly.
- tests run:
  - `python -m pytest backend/tests/unit/strategy_composer backend/tests/unit/strategy_controls backend/tests/unit/execution_plans backend/tests/unit/deployments -q` → 76 passed.
  - `python -m pytest backend/tests/unit -q` → 1497 passed (+21 over baseline 1476).
- test results: all green; zero regressions.
- remaining gaps:
  - DeploymentRepository doesn't yet have explicit `WHERE execution_plan_version_id=...` indexed lookups (the payload column captures the FK as JSON). Index columns added in T-3 if the orchestrator's resolver needs them.
  - Frontend zod schemas don't yet expose `execution_mode` / the version ids. Done in T-2.
- next action: commit T-1 baseline, then start T-2 (Compose UI bracket params + execution_mode selector + buildRequest dehardcoding).

---

## Pass 2 — T-2 baseline (Compose/API wiring)

- pass number: 2 (T-2 baseline)
- timestamp: 2026-04-29 22:50:00 -04:00
- files changed:
  - `frontend/src/api/schemas/strategyComposer.ts` (added `ExecutionModeSchema`, made `execution_mode` optional on `ExecutionStyleVersionSchema`, added `strategy_controls_version_id` + `execution_plan_version_id` to `StrategyDraftSaveResponseSchema`)
  - `frontend/src/components/strategy_builder/editor/editorState.ts` (added `applyExecutionModeToDraft` + `readExecutionMode` helpers)
  - `frontend/src/components/strategy_builder/editor/Page2TabShell.tsx` (passes `executionMode` + `onExecutionModeChange` to ExecutionPresetSection)
  - `frontend/src/components/strategy_builder/editor/sections/ExecutionPresetSection.tsx` (new operator-visible execution_mode `<select>` with default-vs-native hints)
  - `frontend/src/routes/StrategyCompose.tsx` (replaced hardcoded `market_entry_market_exit` with derivation from wizard intent via `derivePresetFromWizard`; exported the helper)
  - `frontend/src/routes/StrategyCompose.test.tsx` (5 new derivePresetFromWizard tests)
  - `frontend/src/components/strategy_builder/editor/editorState.test.ts` (5 new execution_mode helper tests)
  - `frontend/src/components/strategy_builder/editor/sections/ExecutionPresetSection.test.tsx` (new — 3 selector tests including default + native + change)
- decisions made:
  - `derivePresetFromWizard` ordering: `has_runner` → `bracket_runner` (highest signal); else `has_multiple_targets` → `multi_target_scale_out`; else `has_stop && has_target` → `bracket_stop_target`; else `market_entry_market_exit`. has_stop alone is *post-fill protection*, not a preset shape — operator gets the simplest preset and the runtime will still place a stop after fill.
  - ExecutionMode selector lives on ExecutionPresetSection (the same card that owns the preset) because mode and preset are the operator's two execution-side decisions, side by side. Stop·Target·Execution tab.
  - `readExecutionMode` defaults to `post_fill_bracket` for missing/garbage. The schema's `execution_mode` is `.optional()` (no default in zod) so existing fixtures don't have to be updated; the runtime helper provides the safety net.
- blockers and 5 Whys: none.
- tests run:
  - `npx tsc --noEmit` → clean.
  - `npx vitest run src/routes/StrategyCompose.test.tsx` → 15 passed.
  - `npx vitest run src/components/strategy_builder/editor/editorState.test.ts` → 13 passed.
  - `npx vitest run src/components/strategy_builder/editor/sections/ExecutionPresetSection.test.tsx` → 3 passed.
  - `npm test --run` → **392 passed across 52 files** (+13 over baseline 379).
  - `npm run lint:names` → clean.
  - `python -m pytest backend/tests/unit -q` → **1497 passed** (no regression).
- test results: all green; zero regressions.
- remaining gaps:
  - The Compose Page 2 doesn't yet PUT `execution_plan_version_id` into the Deployment when a deployment is created from a saved strategy. That's T-3's wiring (SignalPlan must know which ExecutionPlan to consult, and the Deployment binding is the lookup key).
  - The frontend doesn't yet display the saved `strategy_controls_version_id` / `execution_plan_version_id` in the Strategy detail. Cosmetic / belongs to a later UX slice; not a doctrine concern for T-2's contract.
- next action: commit T-2 baseline; start T-3 (SignalPlan enrichment — SignalPlanBuilder resolves ExecutionPlanVersion + populates stop/target intent for long & short).

---

## Pass 3 — T-3 baseline (SignalPlan enrichment)

- pass number: 3 (T-3 baseline)
- timestamp: 2026-04-29 23:10:00 -04:00
- files changed:
  - `backend/app/decision/signal_plan_builder.py` (added `ExecutionStyleVersion` parameter, `post_fill_pct_rule()` encoder + `parse_post_fill_pct()` decoder, `_legs_from_execution_plan` for BracketStopTarget / BracketRunner / MultiTargetScaleOut presets)
  - `backend/tests/unit/decision/test_signal_plan_builder_bracket_intent.py` (new — 9 acceptance tests covering long bracket, short bracket symmetry, runner trail, multi-target scale-out, no-bracket fallback, quantity-free guard, legacy candidate path)
- decisions made:
  - **Encoding format**: `post_fill_pct:<pct>` for `SignalPlanStop.rule` and `SignalPlanTarget.rule`. Concrete prices stay None on the SignalPlan (it's neutral). Resolution happens in T-4's ProtectiveOrderPlacer post-fill.
  - **Long/short symmetry**: same percent intent on both sides; concrete price flip happens at fill resolution. SignalPlan.side carries the direction.
  - **Bracket runner mapping**: trail_pct → SignalPlanStop.type="trail" + post_fill_pct rule. first_target_pct + first_slice_pct → single REDUCE target with quantity_pct = first_slice_pct * 100. The remaining quantity stays on the position as the "runner" — managed by the trail rule.
  - **Multi-target scale-out**: tier list expands to `t1..tN` REDUCE targets with each tier's slice_pct expressed as quantity_pct. Optional stop_pct creates the protective stop.
  - **Legacy path preserved**: when `execution_plan=None` or no preset, `_stop_from_candidate` / `_targets_from_candidate` (legacy) still run. SignalPlanTarget label kept as "T1" in legacy path to preserve the existing pipeline test contract.
  - **Doctrine guard**: explicit test asserts no `account_id` / `qty` / `quantity` / `notional` / `resolved_quantity` fields on the SignalPlan when the bracket is populated. SignalPlan stays neutral and quantity-free.
- blockers and 5 Whys:
  - 1 regression on first run: `test_deployment_entry_signal_plan_comes_from_watchlist_universe` expected "T1" label on the legacy candidate path; my change had lowercased to "t1" for stylistic consistency.
    - Why? I changed the legacy label too aggressively.
    - Why was the legacy label uppercase? An earlier slice locked it to "T1" and a pipeline test pinned that.
    - Why pin a label? Operator-visible leg label appears in risk decision traces.
    - Why does T-3 use lowercase "t1"? Because the new bracket presets (BracketStopTarget, BracketRunner, MultiTarget) emit lowercase labels for visual consistency in dashboards.
    - Resolution: keep lowercase for the new bracket-emitted targets, restore "T1" for the legacy candidate path. Legacy contract preserved; new contract uses lowercase. Test passes.
- tests run:
  - `pytest backend/tests/unit/decision/test_signal_plan_builder_bracket_intent.py -v` → 9 passed.
  - `pytest backend/tests/unit -q` → **1506 passed** (+9 over T-2 baseline 1497).
- test results: all green; zero regressions.
- remaining gaps:
  - The orchestrator does not yet pass `execution_plan=` into `SignalPlanBuilder.build_from_candidate(...)`. That wiring lands in T-4 along with the OrderManager/BrokerAdapter changes — the orchestrator needs to load the Deployment's `execution_plan_version_id` and resolve it through the new `ExecutionPlanRepository`.
  - SignalPlan is enriched but no consumer reads it yet. The ProtectiveOrderPlacer (T-4) will subscribe to BrokerSync entry-fill events and decode the `post_fill_pct:*` rules to compute concrete prices.
- next action: commit T-3, then T-4 (the main feature — dual-mode order execution).

---

## Alpaca verification (online + SDK source, locked 2026-04-29 21:50:00 -04:00)

- alpaca-py SDK version present at `.venv/Lib/site-packages/alpaca/`.
- `OrderClass` enum supports BRACKET, OCO, OTO, SIMPLE, MLEG.
- `TakeProfitRequest(limit_price)` + `StopLossRequest(stop_price, [limit_price])` are the canonical bracket child specs.
- Native bracket TIF = day | gtc only.
- Native bracket extended_hours = false.
- Native bracket + fractional / notional = NOT supported.
- Native bracket short side: supported (ETB symbols, account ≥ $2,000 equity).
- Concurrent long+short brackets on the same symbol: forbidden.
- Notional orders cannot be replaced.
- Fractional sells always marked long.

Sources:
- https://docs.alpaca.markets/docs/orders-at-alpaca
- https://docs.alpaca.markets/docs/fractional-trading
- https://docs.alpaca.markets/docs/working-with-orders
- https://forum.alpaca.markets/t/why-is-it-impossible-to-concurrently-open-long-and-short-bracket-orders/13159
- alpaca/trading/enums.py:103-118
- alpaca/trading/requests.py:144-166

---
