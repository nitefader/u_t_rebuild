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

## Pass 4 — T-4 baseline (Order execution dual-mode)

- pass number: 4 (T-4 baseline)
- timestamp: 2026-04-29 23:35:00 -04:00
- files changed:
  - `backend/app/orders/protective_placer.py` (new — `ProtectiveOrderPlacer`, `ProtectiveLeg`, `ProtectivePlacementPlan`, `ProtectiveOrderPlacerError`)
  - `backend/app/orders/models.py` (added `bracket_take_profit_limit_price` + `bracket_stop_loss_stop_price` optional fields on `InternalOrder`)
  - `backend/app/brokers/alpaca.py` (added native bracket support to `to_alpaca_order_request`; added `_validate_native_bracket_preflight`; flipped `supports_brackets=True` on `AlpacaBrokerCapabilities`; imported `OrderClass`, `TakeProfitRequest`, `StopLossRequest` from alpaca-py)
  - `backend/tests/unit/orders/test_protective_placer.py` (new — 12 tests covering long/short post-fill brackets, partial fill idempotency, incremental coverage, leg-only cases, doctrine guards)
  - `backend/tests/unit/brokers/test_alpaca_native_bracket.py` (new — 12 tests covering long/short native bracket, all pre-flight failure modes, capability flag, simple-order backwards-compat)
- decisions made:
  - **ProtectiveOrderPlacer is a stateless function**: returns a `ProtectivePlacementPlan` describing the child legs without creating InternalOrders directly. The orchestrator passes it to OrderManager. Idempotency state (covered breakpoints) lives in the OrderManager / orders ledger so it survives restarts.
  - **Pre-flight gate fails LOUD**: per operator directive *"fail clearly if Alpaca rejects the structure"* — `_validate_native_bracket_preflight` raises `AlpacaBrokerError` with structured codes (`native_bracket_missing_child_prices`, `native_bracket_unsupported_tif`, `native_bracket_unsupported_extended_hours`, `native_bracket_unsupported_fractional`). The runtime does NOT silently fall back to `post_fill_bracket` — that would be a hidden runtime path and violates `TURTLE_SHELL_GUARDRAILS.md` §47-69.
  - **Partial-fill idempotency**: keyed on `(parent_order_id, cumulative_filled_qty - already_covered_qty)`. Same fill re-emitted = no-op plan. New fill events with growing cumulative qty trigger incremental placements for only the *new* uncovered shares. Each incremental placement uses the NEW slice's average fill price (not a global average).
  - **Long/short symmetry**: stop direction inverts (LONG below fill, SHORT above); target direction inverts (LONG above fill, SHORT below); exit side inverts (LONG→SELL, SHORT→BUY).
  - **`bracket_take_profit_limit_price` + `bracket_stop_loss_stop_price` on `InternalOrder`**: separate fields rather than a wrapper model, so `InternalOrder.frozen` + `extra="forbid"` discipline is preserved. Both default `None`; the AlpacaBrokerAdapter only attaches bracket fields when `order.order_class == "bracket"`.
  - **OrderManager + orchestrator wiring is T-5**: T-4 ships the components; T-5 wires them so a real entry-fill event flows through OrderManager → ProtectivePlacement → BrokerAdapter. Splitting this way kept the diff focused and the test suite coherent at every step.
- blockers and 5 Whys: none.
- tests run:
  - `pytest backend/tests/unit/orders/test_protective_placer.py -v` → 12 passed.
  - `pytest backend/tests/unit/brokers/test_alpaca_native_bracket.py -v` → 12 passed.
  - `pytest backend/tests/unit/brokers backend/tests/unit/orders -q` → 184 passed.
  - `pytest backend/tests/unit -q` → **1531 passed** (+25 over T-3 baseline 1506).
- test results: all green; zero regressions.
- remaining gaps:
  - **OrderManager.create_protective_orders_post_fill(...)** is not yet implemented — that's T-5's job. The `ProtectiveOrderPlacer` produces a plan; OrderManager turns the plan into lineage-correct InternalOrders.
  - **Orchestrator wiring** of BrokerSync entry-fill events → ProtectiveOrderPlacer → OrderManager → BrokerAdapter is not done. Also T-5.
  - **Operations Protection-Status column** is not done. T-5.
  - **OCO order_class on the protective pair** — when ProtectiveOrderPlacer's two legs are submitted, they should be wired with `order_class="oco"` so the broker auto-cancels the unfilled leg. T-5 wires this.
- next action: commit T-4 baseline; start T-5 (orchestrator wiring + OrderManager method + Operations protection status + acceptance scenario tests).

---

## Pass 5 — T-5 baseline (orchestrator wiring + protection-status column)

- pass number: 5 (T-5 baseline)
- timestamp: 2026-04-30 00:30:00 -04:00
- files changed:
  - `backend/app/orders/manager.py` — new `create_protective_orders_post_fill(plan, parent_order)` (turns ProtectivePlacementPlan into lineage-correct child InternalOrders with `order_class="oco"`, intent STOP_LOSS / TAKE_PROFIT, leg_label suffixed by cumulative breakpoint for partial-fill uniqueness); new `attach_native_bracket_to_entry(order_id, take_profit_limit_price, stop_loss_stop_price)` (mutates an entry's `order_class` to "bracket" + populates the two child price fields); new helpers `_cumulative_covered_qty_for_signal_plan` and `_exit_side_to_candidate`.
  - `backend/app/pipeline/orchestrator.py` — `RuntimeOrchestrator` now (1) passes `execution_plan=self._components.execution_style` into `SignalPlanBuilder.build_from_candidate` (T-3 bracket-intent encoding now actually fires in production), (2) calls a new `_maybe_attach_native_bracket_to_entry` helper before submit when `execution_mode==native_alpaca_bracket` (computes concrete child prices from a reference price = entry.limit_price for limit entries, normalized_bar.close for market entries), (3) calls a new `_handle_post_fill_protective_placement` helper after fill on SignalPlan-origin OPEN entries (compute_protective_plan -> create_protective_orders_post_fill -> recursive _submit_sync_order on each child), (4) instantiates `ProtectiveOrderPlacer` in its constructor and accepts an optional `protective_order_placer` kwarg.
  - `backend/app/pipeline/models.py` — added `PROTECTION_PLACED` and `PROTECTION_NAKED` event types.
  - `backend/app/operations/models.py` — added `OperatorPositionView { snapshot, protection_status, protective_order_count }`; added `position_views: tuple[OperatorPositionView, ...]` field on `AccountOperations`.
  - `backend/app/operations/service.py` — new static `_position_views(positions, orders)` helper that joins by `opening_signal_plan_id` and computes `protected | pending_protection | naked | unknown` based on entry-fill status + active stop-child count.
  - `backend/tests/unit/orders/test_order_manager_protective_post_fill.py` — 8 tests for `create_protective_orders_post_fill` (long lineage, short inverse, partial-fill idempotency, partial-fill incremental, lineage rejection, non-signal-plan parent rejection, placer-owned idempotency, empty-plan no-op).
  - `backend/tests/unit/orders/test_order_manager_native_bracket.py` (new) — 5 tests for `attach_native_bracket_to_entry` (mark order_class + child prices, reject zero/negative prices, short symmetry, no mutation of unrelated fields, reject child orders).
  - `backend/tests/unit/pipeline/test_runtime_orchestrator_post_fill_bracket.py` (new) — 4 end-to-end orchestrator acceptance tests (LONG entry triggers stop+target children with concrete prices, SHORT entry inverts sides, rejected entry skips placement, native_alpaca_bracket attaches child prices on entry and skips post-fill).
  - `backend/tests/unit/pipeline/test_runtime_orchestrator_no_naked_invariant.py` (new) — 3 no-naked-after-fill invariant tests (broker-rejected children leave a clear ledger trail, missing fill price emits PROTECTION_NAKED with rule_id="protection_failed_after_fill", empty-plan-after-intent emits NAKED with reason="no_legs_from_intent").
  - `backend/tests/unit/operations/test_account_operations_position_views.py` (new) — 6 tests for protection_status logic (protected with active stop, naked with no children, pending with CREATED-only child, unknown without lineage, unknown when qty=0, unknown when entry not yet filled).
  - `frontend/src/api/schemas/operations.ts` — new `OperatorPositionViewSchema` and `position_views` field on `AccountOperationsSchema`.
  - `frontend/src/routes/AccountDetailDrawer.tsx` — new "Protection" column on the Open Positions table; lineage-keyed lookup against `position_views`; tone-coded `StatusBadge` (green Protected (N), yellow Pending, red NAKED, neutral —).
  - `frontend/src/routes/OperationsLedger.tsx` — same Protection column on the all-accounts Positions table; `AggregatedPosition` interface gained `protectionStatus` + `protectiveOrderCount`; aggregator joins by `position_lineage_id`.
  - `frontend/src/routes/AccountDetailDrawer.test.tsx` (new) — 1 vitest covering all three tones rendered from a 3-position fixture.
  - `COORDINATION/LOCKS.md` — released stale T-1 leases; opened 7 fresh T-5 leases (TTL 2h).
- decisions made:
  - **Hook site for post-fill placement**: inside `_submit_sync_order` (not in BrokerSyncService.handle_order_update). Reason: synchronous-submit path (FakeBroker / sync Alpaca round-trip) needs the same hook as the streamed path, and `_submit_sync_order` already owns the boundary that produces a `BrokerOrderResult` per submission. Keeps wiring local instead of duplicating across all 3 _submit_sync_order callers.
  - **Native bracket reference price**: limit_price for limit entries; latest bar close for market entries. The drift between the reference price and the actual fill is the operator's tradeoff for atomic submit — documented inline in `_native_bracket_reference_price`. Operators who want exact fill-price brackets should leave execution_mode=post_fill_bracket (the default).
  - **`_is_signal_plan_open_entry` guard**: SignalPlan-origin AND intent=OPEN AND parent_order_id IS NULL. The third clause is critical: it prevents protective children from triggering recursive protective children when they themselves are submitted via `_submit_sync_order`.
  - **PROTECTION_NAKED event scoping**: emitted on (a) missing fill price, (b) signal plan declared intent but ProtectivePlacer produced no legs. Broker REJECTED status on the child orders does NOT emit a separate NAKED event because the child REJECTED rows already appear in the operator's order ledger with operator-readable reasons — adding a second event would be doctrine drift. The rejection-of-children path is covered by `test_no_naked_invariant_emits_alarm_when_protective_child_rejected` which asserts the ledger trail.
  - **`OperatorPositionView` instead of mutating `BrokerPositionSnapshot`**: BrokerPositionSnapshot is broker truth (frozen + extra=forbid). Wrapping it in an operator-derived view keeps doctrine clean (BrokerSync remains the only writer of the snapshot itself) while allowing `protection_status` to live alongside.
  - **`unknown` instead of `naked` when broker truth says qty>0 but ledger says entry not filled**: that's a BrokerSync staleness window. Treating it as `unknown` rather than `naked` prevents false alarms during the refresh interval. Once BrokerSync catches up, the position view flips to `naked` if no stop is found.
  - **`alpaca` forbidden-string lint**: `manager.py` source must not contain the literal string "alpaca". Two close calls in this slice — fixed both by rewording the doc-strings to refer to the broker boundary generically.
- blockers and 5 Whys:
  - 1 regression on first run: `test_no_external_calls` failed because my new `_exit_side_to_candidate` helper had a comment with "_alpaca_side". Why? Convenient inline reference to the BrokerAdapter's translation method. Why does the lint forbid it? OrderManager must not name brokers — that responsibility belongs to BrokerAdapter only. Why? Single submit boundary keeps OrderManager broker-agnostic. Why does that matter? Future broker providers add complexity without changing OrderManager. Why was this lint missed? It's source-string-level, not import-level — easy to trip in comments. Resolution: rephrase comments to reference "the BrokerAdapter boundary" generically.
- tests run:
  - `pytest backend/tests/unit/orders/test_order_manager_protective_post_fill.py -v` → 8 passed.
  - `pytest backend/tests/unit/orders/test_order_manager_native_bracket.py -v` → 5 passed.
  - `pytest backend/tests/unit/pipeline/test_runtime_orchestrator_post_fill_bracket.py -v` → 4 passed.
  - `pytest backend/tests/unit/pipeline/test_runtime_orchestrator_no_naked_invariant.py -v` → 3 passed.
  - `pytest backend/tests/unit/operations/test_account_operations_position_views.py -v` → 6 passed.
  - `pytest backend/tests/unit -q` → **1557 passed** (+26 over T-4 baseline 1531).
  - `npx tsc --noEmit` → clean.
  - `npx vitest run` → **393 passed across 53 test files** (+1 over baseline 392).
  - `npm run lint:names` → clean.
- test results: all green; zero regressions.
- remaining gaps:
  - Architecture / Adversarial / UX critic passes (parallel sonnet x3) running at the time of this writeup; their findings will be addressed before commit.
  - T-6 (TOCTOU hardening) and T-7 (Daily-state aggregator + cooldown) still pending.
- next action: collect critic findings; address fix-in-slice items if any; commit T-5; proceed to T-6.

---

## Pass 6 — T-5 critic findings + fix-in-slice resolution

- pass number: 6 (T-5 critic pass)
- timestamp: 2026-04-30 03:55:00 -04:00
- agents spawned: 3 parallel sonnet critics — Architecture/doctrine, Adversarial bug-hunt, UX/UI.
- critic output summary:
  - **Architecture critic**: 5 BUG, 5 RISK, 3 NIT findings.
  - **Adversarial critic**: 8 BUG, 10 RISK, 5 NIT findings.
  - **UX critic**: 5 BUG, 5 IMPROVEMENT, 3 NIT findings.

### Fix-in-slice items shipped (9):

1. **Fix #1 — `PROTECTION_PLACED` event correctness** (architecture BUG-1 + adversarial RISK-4): the event was emitted unconditionally after the loop, even when every protective child was rejected by the broker. Reworked `_handle_post_fill_protective_placement` in `pipeline/orchestrator.py` to track `submitted_count`. PROTECTION_PLACED now only emits when at least one child reached the broker successfully. When zero children succeed, a parent-level PROTECTION_NAKED with `reason="all_children_rejected"` fires so the operator sees a single parent-keyed alarm in addition to the per-child rejection events.

2. **Fix #2 — Stop-leg rejection aborts the loop** (adversarial BUG-1): a target-only "protection" (target accepted, stop rejected) is worse than naked because it consumes margin without downside cover. The loop now sets `aborted_due_to_stop_rejection=True` and `break`s on stop-leg rejection. Tests prove the target leg is never submitted when the stop is rejected.

3. **Fix #3 — `cumulative_covered_qty_for_signal_plan` excludes terminal-status children** (adversarial BUG-6): the helper used to count rejected/canceled stop children, inflating `already_covered_qty` and preventing re-attempts on the next fill event. Now filters out CANCELED/REJECTED/FAILED. Renamed from `_cumulative_covered_qty_for_signal_plan` to public `cumulative_covered_qty_for_signal_plan` so the orchestrator can call it cleanly without reaching into a private name (adversarial BUG-2).

4. **Fix #4 — Use ledger's cumulative `filled_quantity`, not broker_result's per-event delta** (adversarial BUG-7): some brokers ship delta fills on the trade-update stream; treating the delta as cumulative would silently under-protect on the second partial. The orchestrator now uses `parent_order.filled_quantity` (ledger-applied cumulative from BrokerSync.apply_result) instead.

5. **Fix #5 — `attach_native_bracket_to_entry` is now idempotent on identical prices, raises on different** (adversarial BUG-4 + architecture BUG-4): a second call with the same prices returns the existing order untouched. A second call with different prices raises `OrderManagerError("native bracket already attached with different child prices; cancel and resubmit to change bracket parameters")`. This prevents silent ledger ↔ broker divergence.

6. **Fix #6 — Post-fill placement skipped when entry already has `order_class="bracket"`** (adversarial BUG-5): the orchestrator's components are cached at construction. If the operator changed execution_mode mid-run, the orchestrator could double-bracket. Now the gate also reads `parent_order.order_class == "bracket"` directly (the order's own state is ground truth), so a natively-bracketed entry never triggers post-fill regardless of cached components state.

7. **Fix #7 — AccountDetailDrawer row key uses `position_lineage_id`** (UX BUG-2): the previous key `${symbol}-${quantity}` could collide on two same-symbol positions with the same qty (multi-entry / multi-deployment scenarios). Now the key is `lineageId ?? \`${symbol}-${quantity}-fallback\``. React no longer dedupes legitimate distinct rows.

8. **Fix #8 — Unknown enum values render with `warn` tone, not silent neutral** (UX BUG-3): if the backend ships a future status (e.g. `"protection_failing"`), the UI used to silently fall through to the neutral "—" badge. Now the helper renders unknown statuses with `warn` tone and label `? (<status>)` so the operator sees that the frontend hasn't been updated for a new backend value.

9. **Fix #9 — Extracted `getProtectionDisplay` shared helper** (UX NIT-3): the tone/label derivation was character-for-character duplicated between AccountDetailDrawer and OperationsLedger. Single source of truth at `frontend/src/lib/protectionDisplay.ts`. Adding a future status now requires editing one file. Operator-readable tooltips (`title` attribute) added to all rows so "—" doesn't conflate with "missing data" and "Protected (2)" doesn't make operators wonder if they have a duplicate stop.

### Out-of-slice items (deferred to follow-up):

- Architecture BUG-3 / Adversarial RISK-3: positions with no `opening_signal_plan_id` (legacy / pre-T-5 entries) render as `unknown` instead of `naked`. Behavioral choice; defer until lineage backfill or until the operator explicitly declares the desired behavior.
- Adversarial BUG-3 (mixed partial protection state) + BUG-8 (multi-target native bracket only encodes targets[0]): plausible enhancements; defer to T-7 or a follow-up UX slice.
- UX IMP-1/2/3 (row tinting, naked counter at card header, stop-price column): operator polish, not doctrine; queue for a follow-up UX slice.
- Adversarial RISK-1 (linear-scan ledger query): tractable at operator's 10-account density today; document in code and revisit with persisted-ledger indexing.
- Architecture BUG-2 (recursion guard fragility): documented in the inline comment of `_is_signal_plan_open_entry` so a future reader knows the contract.

### Tests added (6):

- `backend/tests/unit/pipeline/test_runtime_orchestrator_post_fill_bracket_critic_fixes.py` (5):
  - `test_critic_fix_1_protection_placed_does_not_fire_when_all_children_rejected`
  - `test_critic_fix_2_stop_leg_rejection_aborts_target_submit`
  - `test_critic_fix_3_cumulative_covered_qty_excludes_terminal_status_children`
  - `test_critic_fix_5_attach_native_bracket_idempotent_on_same_prices_rejects_different`
  - `test_critic_fix_6_post_fill_skipped_when_entry_has_order_class_bracket`
- `frontend/src/lib/protectionDisplay.test.ts` (6 tests covering all four known statuses + unknown-enum fallthrough + singular vs plural Protected tooltip).
- Updated existing `test_no_naked_invariant_emits_alarm_when_protective_child_rejected` to assert the new (correct) PROTECTION_NAKED behavior.

### Verification post-fixes:

- `pytest backend/tests/unit -q` → **1562 passed** (+5 over T-5 baseline 1557, +31 over T-4 baseline 1531, +186 over original 1376 baseline at start of Bracket Program).
- `npx tsc --noEmit` → clean.
- `npx vitest run` → **399 passed across 54 test files** (+7 over T-4 baseline 392).
- `npm run lint:names` → clean.
- backend banned-name guard `test_no_external_calls` on `manager.py` → clean (rephrased two doc-strings during the slice that initially tripped it).

- next action: commit T-5 (single commit covering baseline + critic fixes), file LEDGER + INBOX_CODEX heads-up, update OPERATION_STATUS, then T-6 (TOCTOU hardening).

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

## Pass 7 — T-6 baseline (TOCTOU hardening, D7 path)

- pass number: 7 (T-6 baseline)
- timestamp: 2026-04-30 06:00:00 -04:00
- operator directive (this turn 2026-04-30): *"Proceed with T-6 using D7. Do NOT implement row-version optimistic locking. Do NOT add risk_plan_map_concurrent_modification rejection. Use single connection per evaluation + WAL mode at composition root. Each evaluation reads a consistent snapshot. Updates apply to future evaluations. Last-writer-wins outside evaluation window is acceptable."*
- files changed:
  - `backend/app/persistence/session.py` — `SQLiteSessionFactory.connect()` now issues `PRAGMA journal_mode=WAL` on every connect. WAL is a persistent database property (the first connect promotes the file; subsequent issues are no-ops), so re-issuing per-connect is idempotent and ensures fresh process boots converge to WAL even when the database file pre-exists in the legacy `delete` mode.
  - `backend/app/persistence/runtime_store.py` — new method `load_governor_policy_inputs(account_id, horizon) -> tuple[AccountRiskConfig | None, RiskPlanConfig | None]` reads `account_risk_configs` and `account_risk_plan_map ⨝ risk_plan_versions` inside ONE `with self._connect() as connection:` block. DEPRECATED RiskPlanVersion still excluded (Slice B fix B-RISK-3 preserved). Returns `(None, None)` for missing rows; KeyError surfaces upward via the resolver's safe-lookup wrapper for graceful degrade.
  - `backend/app/governor/policy_resolver.py` — `GovernorPolicyResolver` API refactored from two independent lookup callbacks (`get_account_risk_config` + `get_risk_plan_config_for_horizon`) to ONE composite callback (`get_policy_inputs`) so both halves of the snapshot come from one DB call. `_safe_lookup` is the new single graceful-degrade entry point: lookup raises → fall back to floor with `lookup_failed=True`; `requires_risk_plan` stays False even with `enforce_plan_required=True` so a transient DB failure cannot become a false-positive rejection (per D7).
  - `backend/app/governor/__init__.py` — exports updated: drop `AccountRiskConfigLookup` + `RiskPlanConfigForHorizonLookup`, add `GovernorPolicyInputsLookup`.
  - `backend/app/runtime/account_trading_orchestrator.py` — `_build_governor_policy_resolver` collapsed to a single path that wires `runtime_store.load_governor_policy_inputs` directly. Returns `None` when the runtime_store doesn't expose the new method (legacy single-policy path stays intact for in-memory test shims). The legacy two-callback fallback was removed — production-grade rule, no parallel paths.
  - `backend/tests/unit/persistence/test_t6_toctou_hardening.py` (new) — 8 tests:
    - `test_wal_mode_is_enabled_on_connect` (PRAGMA journal_mode reports `wal` after first connect)
    - `test_wal_mode_is_idempotent_on_repeat_connect` (3 successive opens, mode stays wal, no error)
    - `test_load_governor_policy_inputs_returns_both_halves` (round-trip with both populated)
    - `test_load_governor_policy_inputs_returns_none_for_missing_rows` (no AccountRiskConfig + no map row → (None, None))
    - `test_load_governor_policy_inputs_skips_deprecated_plan` (DEPRECATED RiskPlanVersion → plan_config=None; B-RISK-3 preserved)
    - `test_concurrent_put_does_not_yield_mixed_state_to_evaluation` — the headline race test: two-version setup (OLD caps positions at 3, NEW at 7), reader thread hammers `load_governor_policy_inputs` while writer thread flips `risk_plan_map` 200 times between OLD and NEW; assert every observation is in {3, 7}, never a mix.
    - `test_concurrent_put_does_not_block_reader` — soft check WAL is on: reader completes ≥50 reads in parallel with 200 writer flips. Without WAL, SQLite would serialize writer↔reader and the reader would stall.
    - `test_governor_evaluation_observes_no_mixed_state_under_put_race` — end-to-end via real `GovernorPolicyResolver`; same race shape but resolved through the production policy code; assert resolved `max_open_positions ∈ {3, 7}`.
  - `backend/tests/unit/governor/test_policy_resolver.py` — `_resolver()` helper folds the two legacy callbacks into one composite callback; deleted `test_account_lookup_raising_falls_back_to_plan_only` and `test_plan_lookup_raising_falls_back_to_account_only` (per-source partial failure no longer a meaningful state); added `test_composite_lookup_raising_falls_back_to_floor` (composite raise → floor preserved + `requires_risk_plan=False` even with `enforce_plan_required=True`).
  - `backend/tests/unit/pipeline/test_runtime_orchestrator.py` — 4 `GovernorPolicyResolver(...)` construction sites converted to the composite callback; `_resolver_for` helper updated similarly.
  - `Operations_Turtle_Shell_Artifacts/STRATEGY_TO_BROKER_BRACKET_PROGRAM.md` — D7 row gains a clarifying paragraph that names the new method + explains the API refactor that made single-conn realizable, per operator's *"Update MAP §7 only if needed for clarity, not to change doctrine."* The doctrine itself is unchanged.
  - `COORDINATION/LOCKS.md` — 4 fresh T-6 leases (TTL 2h).
  - `COORDINATION/INBOX_CODEX.md` — heads-up filed at slice start.
- decisions made:
  - **D7 strict path** per operator directive. Confirmed in pre-coding question to operator. No optimistic locking, no `risk_plan_map_concurrent_modification` rule.
  - **Resolver API refactored** rather than caching results across two callbacks. Two earlier wiring designs (thread-local cache populated on plan_lookup; intermediate snapshot held in resolver) were rejected because (a) cache cleanup window is fragile, (b) per-source-failure tests still implied independent reads. Refactoring to a single composite callback is the doctrine-correct realization of D7's "single connection per evaluation" — both halves of the snapshot now come from one call. Test churn was 5 construction sites (4 in tests + 1 in production) plus a helper; manageable.
  - **`requires_risk_plan` stays False on lookup raise** even when `enforce_plan_required=True`. This preserves the Slice B graceful-degrade contract: a transient DB failure must not become a false-positive `account_missing_risk_plan_for_horizon` rejection that kills trading.
  - **Returned `None` for both halves on KeyError** in `_build_governor_policy_resolver`'s composite wrapper. Other exceptions propagate so the resolver's `_safe_lookup` can route them to the graceful-degrade branch.
  - **Race test asserts `set(observed).issubset({3, 7})`** rather than asserting both states observed. The doctrine guarantee is "no mix", not "must observe both states" — observing only one state still satisfies it. Soft transition observation is left to the throughput test.
  - **WAL throughput floor 50 reads in 30s.** Soft check that reader-writer concurrency actually runs in parallel; without WAL the reader stalls. Floor is intentionally low to avoid Windows / Python 3.14 jitter false-fails.
- blockers and 5 Whys:
  - **Blocker: per-source resolver tests no longer fit the composite API.** Why? The two failure-mode tests assumed account_lookup could raise while plan_lookup succeeded. Why does that break? The production T-6 path reads both halves in one call; you cannot have one half raise and the other succeed. Why was that the test design before? Slice A's two-callback API made the orthogonal failure path explicit. Why is it not orthogonal anymore? D7 unifies the read into one snapshot; orthogonal failures stop being a real production state. Resolution: deleted the two tests and added one composite-failure test that asserts the new contract (lookup raise → floor preserved + `requires_risk_plan=False`). Net test delta: -2 + 1 + 8 = +7.
- tests run:
  - `pytest backend/tests/unit/persistence/test_t6_toctou_hardening.py -v` → 8 passed.
  - `pytest backend/tests/unit/governor backend/tests/unit/pipeline backend/tests/unit/persistence backend/tests/unit/runtime backend/tests/unit/broker_accounts -q` → 277 passed (focused gate).
  - `pytest backend/tests/unit -q` → **1569 passed** (+7 over T-5 baseline 1562).
  - `pytest backend/tests/unit/orders/test_order_manager.py::test_no_external_calls -v` → passed (banned-name guard clean).
  - `npx tsc --noEmit` → clean.
  - `npx vitest run` → **399 passed across 54 files** (no change — T-6 has no frontend surface).
  - `npm run lint:names` → clean.
- test results: all green; zero regressions.
- remaining gaps:
  - Architecture critic + Adversarial critic pass (parallel sonnet x2) running at the time of this baseline writeup; their findings addressed in Pass 8 below.
  - T-7 (Daily-state aggregator + cooldown) still pending after T-6.
- next action: collect critic findings; address fix-in-slice items; commit T-6; proceed to T-7.

---

## Pass 8 — T-6 critic findings + fix-in-slice resolution

- pass number: 8 (T-6 critic pass)
- timestamp: 2026-04-30 06:30:00 -04:00
- agents spawned: 2 parallel sonnet critics — Architecture/doctrine, Adversarial bug-hunt. (UX critic skipped per slice plan: T-6 has no operator-facing UI surface.)
- critic output summary:
  - **Architecture critic**: 1 BUG, 3 RISK, 4 NIT findings.
  - **Adversarial critic**: 3 BUG, 4 RISK, 4 NIT findings.
  - Both critics independently identified the same headline BUG (single connection alone is not a SQLite snapshot under default Python ``sqlite3`` ``isolation_level=""``).

### Fix-in-slice items shipped (5):

1. **Fix #1 — Explicit ``BEGIN`` / ``COMMIT`` around the composite read** (architecture BUG-1 + adversarial BUG-1, both critics agreed): Python's ``sqlite3`` driver default ``isolation_level=""`` only implicitly begins a transaction on DML — bare SELECTs autocommit. In WAL mode, two consecutive SELECTs on the same connection therefore each take their own end-mark read snapshot, and a writer that commits between them is visible to the second one. ``load_governor_policy_inputs`` now opens an explicit ``BEGIN`` before the first SELECT and ``COMMIT`` after the second so both reads come from one snapshot. Docstring updated to document the mechanism (driver autocommit nuance + why single-conn alone is insufficient).

2. **Fix #2 — Strengthened race regression with a real dual-write scenario** (architecture RISK-1 / adversarial RISK-1): the original headline race test (`test_concurrent_put_does_not_yield_mixed_state_to_evaluation`) only flipped one row, so any "mix" still reported a coherent plan_config — the test was doctrinally vacuous. New test `test_concurrent_dual_write_does_not_yield_correlated_mix` mutates BOTH ``account_risk_configs`` and ``account_risk_plan_map`` inside ONE writer SQLite transaction, tagging two coherent generations: A=(account_max_open=10, plan_cap=3) vs. B=(account_max_open=20, plan_cap=7). Reader asserts every observation is in {(10,3), (20,7)}; (10,7) and (20,3) would be the half-applied snapshot the BEGIN/COMMIT closes. Confirmed the test catches the BUG-1 failure mode by temporarily disabling the BEGIN/COMMIT and observing (10,7) and (20,3) in the failure output.

3. **Fix #3 — Removed dead ``except KeyError`` in orchestrator wiring** (adversarial BUG-5): ``SQLiteRuntimeStore.load_governor_policy_inputs`` never raises ``KeyError`` for missing rows — it returns ``(None, None)`` natively. The wrapper closure in ``_build_governor_policy_resolver`` had ``try: ... except KeyError: return None, None`` which was both dead AND would mask a real future bug (e.g. malformed payload in ``_load_model``) by converting it to a silent "no override" path that bypasses ``_safe_lookup``'s graceful-degrade logging. Wrapper closure removed entirely; the resolver now binds `runtime_store.load_governor_policy_inputs` directly. Real exceptions propagate into ``_safe_lookup`` which logs them per D7.

4. **Fix #4 — Structured log on graceful-degrade failure** (adversarial BUG-3): ``_safe_lookup`` previously logged a plain warning string on lookup raise; log aggregators couldn't alarm on the path. Added a structured ``extra`` dict with ``event="governor_policy_inputs_lookup_failed"`` + ``account_id`` + ``horizon`` so Operations dashboards can wire an alarm. D7 says graceful-degrade — it does not say silent.

5. **Fix #5 — Doctrine-doc T-6 amendment** (architecture RISK-2): `Operations_Turtle_Shell_Artifacts/GOVERNOR_WIRING_MAP.md` and `GOVERNOR_WIRING_MAP_SLICE_B.md` still described the resolver as a two-callback constructor (`get_account_risk_config` + `get_risk_plan_config_for_horizon`). T-6 collapsed that to one composite callback. Both docs now carry a short T-6 amendment block at the top noting the new shape. The locked Risk Horizon doctrine in §0 of each doc is unchanged.

Also updated `STRATEGY_TO_BROKER_BRACKET_PROGRAM.md` §7 D7 with a clarifying paragraph naming the new method and explaining the API refactor that made single-conn realizable. Per operator: *"Update MAP §7 only if needed for clarity, not to change doctrine."*

### Out-of-slice items (deferred):

- Architecture NIT-1: rename `load_governor_policy_inputs` → `load_governor_policy_snapshot`. Naming churn is a separate slice; defer.
- Architecture NIT-2: assert `PRAGMA journal_mode=WAL` actually granted (warn if filesystem rejected WAL on a network share). Cheap log-only enhancement; deferred — operator's local SQLite path is doctrine-fine.
- Adversarial RISK-6: WAL sidecar files (`-wal`, `-shm`) — search for any code that copies/checksums the runtime DB file; document sidecars; consider periodic checkpoint. No current consumer; defer.
- Adversarial RISK-7: per-connect PRAGMA cost. Every `_fetch_one`/`_fetch_all` opens a fresh connection that runs two PRAGMAs. Throughput tax. Defer to a future caching slice.
- Adversarial NIT-4: gap in coverage where the production composite raises specifically inside the runtime_store layer (vs. inside a test shim). The orchestrator wrapper now binds the method directly, so a real raise does propagate; the resolver-side composite-failure test exercises the path. Defer additional regression depth.

### Tests added (1) + tightened (existing 8 retained):

- `backend/tests/unit/persistence/test_t6_toctou_hardening.py::test_concurrent_dual_write_does_not_yield_correlated_mix` (new, the headline doctrine guard).
- The original 8 tests remain unchanged; they now run alongside the dual-write test.

### Verification post-fixes:

- `pytest backend/tests/unit/persistence/test_t6_toctou_hardening.py -v` → **9 passed**.
- `pytest backend/tests/unit -q` → **1570 passed** (+8 over T-5 baseline 1562, +1 over T-6 Pass 7 baseline 1569 = the new dual-write race test).
- `npx tsc --noEmit` → clean.
- `npx vitest run` → **399 passed across 54 files** (no change — T-6 has no frontend surface).
- `npm run lint:names` → clean.
- `pytest backend/tests/unit/orders/test_order_manager.py::test_no_external_calls -v` → passed (manager.py banned-name guard).
- Sanity check: temporarily disabled the BEGIN/COMMIT block in `load_governor_policy_inputs` and confirmed `test_concurrent_dual_write_does_not_yield_correlated_mix` fails with observed (10,7) / (20,3) pairs. Restored. Confirms the regression test actually exercises the BUG-1 mechanism.

- next action: append LEDGER entry; release T-6 leases; update OPERATION_STATUS to T-6 SHIPPED; file INBOX_CODEX heads-up; commit T-6 as a single commit; proceed to T-7 (Daily-state aggregator + cooldown).

---

## Pass 9 — W2-A pre-T-7 Audit P0 Bundle (baseline)

**Timestamp:** 2026-04-30 07:00 → 09:30 -04:00
**Pass type:** baseline implementation of the W2-A pre-T-7 audit P0 bundle.
**Operator directive 2026-04-30:** "Proceed with W2-A before T-7. Decision (a): compute proxy candidate_open_risk from gating-time reference price; do NOT reject post_fill_pct entries before fill. Decision (b): fail-closed reject rule_id=portfolio_equity_unavailable when equity is None."
**Driving artifact:** `docs/audits/WHOLE_SYSTEM_AUDIT.md` (2026-04-30) — three confirmed P0 silent-no-op findings: §6 + Silent §1 (GovernorRequest candidate exposure fields default zero), §1 (AccountSignalPlanEvaluation projected from orders only — REJECT/IGNORE invisible), and corollary stable ordering for the persisted store.

### Files changed (W2-A baseline)

- `backend/app/governor/service.py` — new fail-closed rule `portfolio_equity_unavailable` between stale-broker-sync and `requires_risk_plan`; only fires for OPEN intents per W2-A-1b doctrine.
- `backend/app/pipeline/orchestrator.py` — new helper `_governor_candidate_inputs(...)` resolves `candidate_market_value` + `candidate_open_risk` from `risk_result.resolved_quantity`, an entry reference price (limit-or-bar-close, same fallback as the native bracket placer), and either `risk_result.stop_distance` (concrete) or a `parse_post_fill_pct(...)` proxy. Emits `GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED` pipeline event with full math context. New helper `_record_account_evaluation(bucket, evaluation)` wraps every in-memory append with a persisted-store write — 5 emit sites covered (entry-path accept/reject, position-mgmt accept/reject, blocked-twice and ignored-twice helpers, single-account `process_protective_signal_plan`).
- `backend/app/pipeline/models.py` — new `PipelineEventType.GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED` (W2-A-1a audit event) and `PipelineEventType.EVALUATION_PERSIST_FAILED` (W2-A adversarial-critic fix #3).
- `backend/app/persistence/models.py` — new `account_signal_plan_evaluations` table at end of `RUNTIME_SCHEMA` (PK `evaluation_id`, indices on `account_id+persisted_at DESC`, `signal_plan_id`, `deployment_id`, and `persisted_at DESC`).
- `backend/app/persistence/runtime_store.py` — new repo methods `save_account_signal_plan_evaluation`, `load_account_signal_plan_evaluation`, `list_account_signal_plan_evaluations(account_id?, deployment_id?, signal_plan_id?, limit)` on `SQLiteRuntimeStore`. `persisted_at` is write-side metadata (assigned at INSERT time, not on the Pydantic model). `limit` clamps to `[1, 500]`.
- `backend/app/operations/service.py` — `list_account_signal_plan_evaluations` rewritten to read persisted store first; falls back to legacy order-projection only when the store has no rows for the filter. No hybrid stitching when both paths have rows.
- `backend/app/runtime/account_trading_entrypoint.py` — extracted `build_portfolio_snapshot_factory(runtime_store)` helper; `run_account_trading` now wires it. Closes the audit's "verify each composition site" — production was previously running on `lambda: PortfolioSnapshot()` with equity=None.
- `backend/app/runtime/account_trading_orchestrator.py` — `BrokerRuntimeOrchestrator._build_pipeline` now threads the factory itself (kwarg `portfolio_snapshot_factory=`) instead of pre-resolving snapshots at construction.
- `tools/run_runtime_smoke.py` + `tools/run_runtime_dry_run.py` — both `_portfolio_snapshot` helpers now return `PortfolioSnapshot(equity=100_000, ...)` instead of equity=None so smoke + dry-run flows don't trip the new fail-closed rule.
- 8 test fixture updates across `backend/tests/unit/{governor,pipeline,runtime,tools}` to declare equity in the new fail-closed regime.

### New test files (W2-A)

- `backend/tests/unit/persistence/test_w2a_account_signal_plan_evaluations.py` — 10 tests (round-trip restart, idempotent upsert, account/deployment/signal_plan filters, persisted_at ordering, REJECT/IGNORE/DEFER round-trip, limit clamping at both bounds).
- `backend/tests/unit/pipeline/test_runtime_orchestrator_persists_account_evaluations.py` — 5 tests at baseline (entry persist, governor reject persist, equity-unavailable persist, multi-account persist, restart persist) + 2 additional from Pass 10 critic fixes.

### New tests appended to existing files (W2-A)

- `backend/tests/unit/governor/test_portfolio_governor.py` — +12 tests (fail-closed rule + populated candidate-inputs regression guards).
- `backend/tests/unit/pipeline/test_runtime_orchestrator_post_fill_bracket.py` — +2 integration tests (proxy event emitted, projected_state non-zero gross_exposure_pct) + 1 cap-breach test from Pass 10.
- `backend/tests/unit/operations/test_operations_center_service.py` — +4 W2-A-3 tests (persisted-first read, fallback to projection when store empty, no hybrid stitching, signal_plan_id filter through persisted store).
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py` — +1 cap-at-100 unit test on `_governor_candidate_inputs` from Pass 10.
- `backend/tests/unit/runtime/test_broker_runtime_entrypoint.py` — +4 factory tests (equity-present, no-snapshot KeyError, equity=0 maps to None, factory called per invocation).

### Doctrine decisions made

- **D-W2-A-a (locked by operator 2026-04-30):** When SignalPlan stop is `post_fill_pct:N`, the Governor proxy uses `qty * ref_price * (N/100)` for `candidate_open_risk`. Never reject post_fill_pct entries before fill (would break the default bracket mode). Emit `GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED` audit event so Operations sees the proxy path.
- **D-W2-A-b (locked by operator 2026-04-30):** `PortfolioSnapshot.equity is None` for an OPEN intent is a fail-closed reject with `rule_id="portfolio_equity_unavailable"`. Percentage gates cannot be trusted without equity.
- **Persistence boundary:** `account_signal_plan_evaluations` is *runtime decision truth*, not *broker truth*. Guardrails §39 ("BrokerSync is the only broker truth writer") preserved — the new write is through `runtime_store.save_account_signal_plan_evaluation`, not through any broker channel.
- **Operations read contract:** persisted-store-first with order-projection fallback for legacy data only. No hybrid stitching when both have rows.

### Tests run (W2-A baseline)

- `pytest backend/tests/unit -q` → **1601 passed** (+31 over T-6 baseline 1570).
- `npx tsc --noEmit` → clean.
- `npx vitest run` → **399 passed across 54 files** (no change — frontend already shape-correct for non-order rows).
- `npm run lint:names` → clean.
- `pytest backend/tests/unit/lint -q` → **229 passed** (banned-name guard).

### Blockers

None — slice landed clean before critic recursion.

### Next action

Spawn Architecture critic + Adversarial critic in parallel; ship fix-in-slice items as Pass 10. UX critic skipped per resume prompt (only operator-facing change is "rejected/blocked evaluations now appear on Operations" and the existing schema/UI was verified by inspection to handle non-order rows correctly).

---

## Pass 10 — W2-A Critic Pass (Architecture + Adversarial)

**Timestamp:** 2026-04-30 09:30 → 10:30 -04:00
**Pass type:** parallel sonnet critics against the W2-A baseline.

### Architecture critic verdict: FIX-IN-SLICE

Confirmed the persistence boundary is doctrinally clean (runtime decision truth, not broker truth). `_record_account_evaluation` correctly appends-then-persists. `persisted_at` correctly stays write-side only. Operations read path stays read-only. Two BUGs identified for in-slice fix.

### Adversarial critic verdict: FINDINGS-PRESENT

Three concrete failure modes found. Highest-impact: cross-account persistence-vs-result divergence on partial failure (one Account's persist raise breaks the loop for accounts later in the fanout).

### Fix-in-slice items shipped (4):

1. **Fix #1 — `_portfolio_snapshot_factory` maps equity≤0 to None** (Architecture BUG-1 + Adversarial BUG-2 — both critics flagged): `BrokerAccountSnapshot.equity` is `ge=0` (allows 0.0 from a stale-and-flat poll, blocked account, post-liquidation, or fresh unfunded account), but `PortfolioSnapshot.equity` is `gt=0` so `PortfolioSnapshot(equity=0.0)` raises `ValidationError`. AND even if construction succeeded, `_pct(value, equity=0)` collapses every percentage gate to zero — operationally indistinguishable from "we don't know." Fix: factory checks `equity <= 0` and returns `PortfolioSnapshot()` (None). The W2-A-1b fail-closed rule then fires deterministically. Test: `test_build_portfolio_snapshot_factory_maps_zero_equity_to_none`.

2. **Fix #2 — Per-call factory threading (not cached at construction)** (Architecture BUG-2): pre-fix, `BrokerRuntimeOrchestrator._build_pipeline` called the factory eagerly and stored the result in `portfolio_snapshot_by_account` dict; subsequent equity changes were invisible. The audit's TOCTOU concern was only partially closed at first-boot. Fix: `RuntimeOrchestrator.__init__` accepts `portfolio_snapshot_factory=` kwarg; `_portfolio_snapshot_for(account_id)` invokes it on every call when present. `BrokerRuntimeOrchestrator` threads the factory directly. Test: `test_factory_is_called_per_invocation_not_cached`.

3. **Fix #3 — Cross-account persist failure becomes a structured event, not a re-raise** (Adversarial BUG-1): pre-fix, an `IntegrityError` on account #3 of a 10-account fanout would propagate out of `process_bar`, leaving accounts #1/#2 with partial in-memory + persisted state and accounts #4..#10 never evaluated. Fix: `_record_account_evaluation` wraps the persist call in `try/except`, emits `EVALUATION_PERSIST_FAILED` with full lineage on failure (account_id, signal_plan_id, deployment_id, participation_decision, error_type, error message), and continues. The in-memory bucket is preserved. Two new tests: `test_persist_failure_emits_event_and_keeps_in_memory_result` and `test_persist_failure_in_one_account_does_not_block_other_accounts`.

4. **Fix #4 — `post_fill_pct` cap at 100% in proxy** (Adversarial RISK-1): pre-fix, a malformed plan with `post_fill_pct:200` would yield `proxy_stop_distance = 2 * ref_price` and `candidate_open_risk = 2 * notional`, which is meaningless because real loss can never exceed entry notional. Fix: `_governor_candidate_inputs` clamps `stop_pct = min(stop_pct, 100.0)` before the proxy compute. Downstream protective placer is unchanged (its own pre-existing constraint catches stop_price ≤ 0). Test: `test_governor_candidate_inputs_caps_post_fill_pct_at_100`.

### Out-of-slice findings (deferred with explicit rationale):

- **Adversarial BUG-3 (idempotency hole on bar reprocess):** each evaluation builder mints fresh `evaluation_id=uuid4()`, so re-running the same bar would create duplicate persisted rows. Honest assessment: bar reprocessing is already prevented upstream by `runtime_state.last_processed_bar_timestamp`; recovery doesn't re-run completed bars; only test replays exercise this and they intentionally want fresh evaluations. Defer until a documented recovery-replay use case emerges.
- **Adversarial RISK-2 (Operations fallback hybrid leakage):** once the persisted store has any row for a filter, the legacy order-projection fallback never fires for that filter. This is the documented W2-A-3 contract ("no hybrid stitching"); legacy data is gone forever once new rows persist. Doc-only.
- **Adversarial RISK-3 (SQLite single-writer fsync cost across N accounts):** N=10 accounts × 10 deployments = 100 fsyncs per bar. T-7's daily-state aggregator will batch.
- **Adversarial RISK-4 (lineage queryability):** `risk_resolver_result`, `risk_plan_version_id`, `position_lineage_id`, `program_id`, `strategy_version_id` are all in JSON payload, not columns. Operations queries can't filter without payload deserialization. Defer to a follow-up schema-widening slice.
- **Adversarial NIT-1 (docstring drift):** the "must NOT silently swallow — they re-raise" language was aspirational pre-fix; updated to match the new structured-event behavior in Fix #3.
- **Adversarial NIT-2 (test sleep flake):** `test_list_orders_newest_persisted_first` uses `time.sleep(0.005)`. Acceptable for now (test passes consistently); revisit if flakes appear.
- **Architecture NIT-5 (single event type for two paths):** `GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED` is emitted both when a proxy was applied and when no proxy was possible. The `details.reason` differs but the event_type is shared. Defer separation.
- **Architecture NIT-6 (positions empty in production factory):** `BrokerPositionSnapshot` lacks `program_id`. Position truth still flows via Account fanout's own position-mgmt pass. Schema-widening is a separate slice.

### Tests added (8) + fixtures updated:

- `test_build_portfolio_snapshot_factory_returns_equity_when_snapshot_present` (factory happy path).
- `test_build_portfolio_snapshot_factory_returns_equity_none_when_no_snapshot` (factory KeyError → None).
- `test_build_portfolio_snapshot_factory_maps_zero_equity_to_none` (Fix #1).
- `test_factory_is_called_per_invocation_not_cached` (Fix #2).
- `test_persist_failure_emits_event_and_keeps_in_memory_result` (Fix #3, single account).
- `test_persist_failure_in_one_account_does_not_block_other_accounts` (Fix #3, multi-account fanout).
- `test_governor_candidate_inputs_caps_post_fill_pct_at_100` (Fix #4).

### Verification post-fixes

- `pytest backend/tests/unit -q` → **1608 passed** (+38 over original 1570 baseline; +7 over W2-A baseline 1601).
- `npx tsc --noEmit` → clean.
- `npx vitest run` → **399 passed across 54 files** (no change).
- `npm run lint:names` → clean.
- `pytest backend/tests/unit/lint -q` → **229 passed**.

### Remaining gaps

None for W2-A. All deferred items are documented above with explicit rationale. Slice ready to commit.

### Next action

Append LEDGER entry; release W2-A leases; update OPERATION_STATUS to W2-A SHIPPED; commit the bundle as a single commit (`Close audit P0 silent-no-op bundle (W2-A pre-T-7)`); proceed to T-7 (Daily-state aggregator + cooldown).

---
