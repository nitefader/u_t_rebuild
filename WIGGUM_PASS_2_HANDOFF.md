# Wiggum Pass 2 — Bracket Program T-1..T-7 Adversarial Review: Handoff

**Status as of 2026-04-30**

This document hands off the in-flight P0/P1 fix list from a Wiggum Pass 2
adversarial review of the Bracket Program (T-1..T-7) to a fresh agent.
It is both human-readable (read top-to-bottom) and machine-parseable (each
TODO is a YAML block with a stable id, file refs, acceptance test paths,
and a verification command).

The user operates per these durable preferences (already in
`~/.claude/projects/.../memory/MEMORY.md` — re-read it before starting):

- Production-grade only — no temporary paths, no patching, no throwaway work.
- Operation Turtle Shell owns backend doctrine; read its protocol before any
  backend change.
- Multi-Account target (~10 broker accounts running concurrently).
- "Operator" = the user. When a TODO offers two paths, default to the
  production-grade one but surface the trade-off before coding.

The user explicitly chose **(B) safety-net first, native Alpaca OCO as
follow-up** for the OCO bug pattern. Apply the same lens elsewhere: ship
the durable shape unless the user has already steered toward a safety net.

---

## Status Snapshot

| ID | Title | Severity | Status |
|----|-------|----------|--------|
| P0-1 | Realized PnL ≠ cash flow | P0 | ✅ DONE |
| P0-2 | Cooldown timer uses wall-clock not fill timestamp | P0 | ✅ DONE |
| P0-3 | OCO sibling not canceled on leg fill | P0 | ⚠️ SAFETY NET SHIPPED — durable native-OCO fix still owed |
| P0-4 | Stale `DailyAccountState` bleeds across ET midnight | P0 | ❌ TODO |
| P0-5 | `save_daily_account_state` failures silently swallowed | P0 | ❌ TODO |
| P0-6 | Concurrent partial-fill race in post-fill placement | P0 | ❌ TODO |
| P1-1 | Native vs post-fill bracket use different reference prices | P1 | ❌ TODO |
| P1-2 | `protection_status="protected"` counts stop-only | P1 | ❌ TODO |
| P1-3 | `_native_bracket_reference_price` falls back to stale bar.close | P1 | ❌ TODO |
| P1-4 | `requires_risk_plan` silently skipped when `Deployment.risk_horizon` unset | P1 | ❌ TODO |
| P1-5 | Floor policy loaded once at boot; operator pause not effective until restart | P1 | ❌ TODO |
| P1-6 | Replay path skips `ProtectiveOrderPlacer` entirely | P1 | ❌ TODO |
| P2-1 | `_account_field`/`_plan_field` use `getattr(..., None)` — silent on typos | P2 | ❌ TODO |
| P2-2 | Surface `double_protected` warning on native + post-fill child overlap | P2 | ❌ TODO |
| P2-3 | ET midnight uses `zoneinfo` with bare-except UTC-5 fallback | P2 | ❌ TODO |
| S-1 | Cold-boot fill-before-snapshot silently disarms drawdown gate | Suspected | ❌ INVESTIGATE |
| S-2 | Operator-canceled stop child may be re-placed on next fill | Suspected | ❌ INVESTIGATE |
| S-3 | `attach_native_bracket_to_entry` re-attach uses 1e-9 fp tolerance | Suspected | ❌ INVESTIGATE |
| S-4 | `_daily_states` dict shared by reference across `BrokerSyncService` instances | Suspected | ❌ INVESTIGATE |
| FOLLOWUP-A | Native Alpaca OCO submission (durable P0-3) | P0-followup | ❌ TODO |

Verify command for the whole suite:

```bash
python -m pytest backend/tests/unit -q
```

Last known green: **1671 unit tests pass** as of 2026-04-30 after P0-1, P0-2,
P0-3-safety-net.

---

## Already-Shipped Fixes (Context, Do Not Redo)

### P0-1 — Realized PnL ≠ cash flow ✅

**Bug:** `_fill_cash_flow` recorded every BUY as negative `realized_pnl`, so
the first long entry of the day tripped daily-loss/drawdown/cooldown gates.

**Fix:** Average-cost round-trip semantics. Lots tracked per (account, symbol)
in `DailyAccountState.lots`; opening/adding does NOT realize PnL; closing/
reducing realizes against avg_cost; flips close-then-open. `_fill_cash_flow`
retained for diagnostic callers but no longer drives state.

**Files touched:**
- `backend/app/runtime/daily_account_state.py`
- `backend/tests/unit/runtime/test_daily_account_state.py`

Persistence is non-breaking — `daily_account_states` stores full pydantic
JSON payload, `lots` round-trips without migration.

### P0-2 — Cooldown wall-clock vs fill timestamp ✅

**Bug:** `governor.evaluate()` called `utc_now()` for cooldown elapsed-time
calc → replay/backtest never matched live; cooldown effectively never fired
in research.

**Fix:** Added optional `evaluated_at: datetime | None` field to
`GovernorRequest`. Service uses `request.evaluated_at` when present, falls
back to `utc_now()`. Orchestrator threads its existing `timestamp` parameter
into `GovernorRequest.evaluated_at`.

**Files touched:**
- `backend/app/governor/models.py:120-124` — added field
- `backend/app/governor/service.py:157-162` — uses field
- `backend/app/pipeline/orchestrator.py:1477` — threads timestamp
- `backend/tests/unit/governor/test_governor_daily_risk.py` — added 2 tests

### P0-3 — OCO sibling not canceled on leg fill (SAFETY NET ONLY) ⚠️

**Bug:** `order_class="oco"` children submitted as two **independent,
unlinked broker orders**. AlpacaBrokerAdapter only translates `"bracket"`
(line `backend/app/brokers/alpaca.py:313`). When target fills, stop stays
live → next stop trigger flips position long → flat → silently short.

**Safety net shipped (option B per user):** `BrokerSync.apply_result` now
cancels the live OCO sibling on FILLED transitions. Sibling matched by
`parent_order_id` + slice suffix in `leg_label` (`"stop@10"` ↔ `"target@10"`).

**Files touched:**
- `backend/app/brokers/sync.py` — added `_cancel_oco_siblings`,
  `_slice_suffix_of`, `_LIVE_TERMINAL_STATUSES`
- `backend/tests/unit/brokers/test_broker_sync_oco_sibling_cancel.py` — 8
  regression tests

**STILL OWED:** see `FOLLOWUP-A` below — native Alpaca OCO submission is
the durable shape. Safety net closes the silent-flip risk today; native OCO
removes the race window between target fill and our cancel call.

---

## P0 — Must Fix Before Live Trading

```yaml
id: P0-4
title: Stale DailyAccountState bleeds across ET midnight
severity: P0
status: TODO
location: backend/app/runtime/account_trading_orchestrator.py:431-432
description: |
  _daily_states dict seeded once at boot. After ET midnight rollover, the
  governor evaluation that fires before the new day's first fill reads
  YESTERDAY'S cumulative loss — cooldown from a 23:59 ET loss leaks into
  the next session's first minute.
fix_approach: |
  At Governor evaluate-time (or just before passing daily_state into
  GovernorRequest), check whether _et_market_day(now) != state.market_day
  and return a fresh empty DailyAccountState if so. Reuse
  backend/app/runtime/daily_account_state.py:_et_market_day for the
  comparison so DST handling matches the aggregator.
helpers:
  - "backend/app/runtime/daily_account_state.py:_et_market_day"
  - "backend/app/runtime/daily_account_state.py:DailyAccountState (frozen, can construct fresh)"
  - "backend/app/runtime/account_trading_orchestrator.py — _daily_states owner"
  - "backend/app/pipeline/orchestrator.py:1463 — where daily_state_factory is invoked"
acceptance_tests:
  - "test_daily_state_does_not_bleed_across_et_midnight (in backend/tests/unit/runtime/test_daily_account_state.py or similar)"
  - "Test should: seed state w/ market_day=YESTERDAY and last_loss_at near yesterday's close; evaluate governor at TODAY's open; assert cooldown does NOT fire and state returned is fresh."
verify_command: "python -m pytest backend/tests/unit/runtime backend/tests/unit/pipeline -q"
```

```yaml
id: P0-5
title: save_daily_account_state failures silently swallowed
severity: P0
status: TODO
location: backend/app/brokers/sync.py:448-452
description: |
  bare `except: pass` on persistence write. If save_daily_account_state
  raises (DB locked, disk full), the failure is invisible. Process
  restart resets cooldown/daily-loss to zero with no log.
fix_approach: |
  Replace bare except with structured warn matching the pattern used by
  the policy resolver (search 'policy_resolver' for the canonical log
  call). Include account_id and market_day in the log context. Do NOT
  re-raise — the in-memory state is still valid; this is a durability
  warning, not a correctness halt.
helpers:
  - "backend/app/governor/policy_resolver.py — has the canonical structured-warn pattern"
  - "backend/app/brokers/sync.py:437-452 — _apply_daily_state_fill"
acceptance_tests:
  - "test_save_daily_account_state_failure_logs_warning"
  - "Mock runtime_store.save_daily_account_state to raise; assert log captured with expected context fields; assert in-memory _daily_states still updated."
verify_command: "python -m pytest backend/tests/unit/brokers backend/tests/unit/runtime -q"
```

```yaml
id: P0-6
title: Concurrent partial-fill race in post-fill bracket placement
severity: P0
status: TODO
location:
  - backend/app/pipeline/orchestrator.py:973
  - backend/app/pipeline/orchestrator.py:1137-1148
description: |
  cumulative_covered_qty_for_signal_plan read-then-write is not atomic
  vs concurrent fills coming from BrokerStreamRunner threads. Two
  partial-fill events for the same SignalPlan can race → both compute
  the same cumulative_covered → both submit overlapping protective
  qty → operator gets double-stop coverage on the same position.
fix_approach: |
  EITHER (1) per-parent_order_id lock around the read-compute-submit
  sequence in the orchestrator, OR (2) move post-fill placement onto
  the orchestrator's existing single-threaded queue so all fills for a
  parent serialize. Option (2) is preferred — it matches the doctrine
  that the orchestrator is the only site that decides protective
  placement. Verify with Operation Turtle Shell artifacts.
helpers:
  - "backend/app/orders/manager.py:422 — cumulative_covered_qty_for_signal_plan (current read site)"
  - "backend/app/pipeline/orchestrator.py — stream-event ingress; find the existing queue/dispatcher"
  - "Operations_Turtle_Shell_Artifacts/ — read protocol before changing orchestrator threading"
acceptance_tests:
  - "test_concurrent_partial_fills_do_not_double_protect"
  - "Drive two threads emitting partial-fill events for the same parent_order_id; assert exactly one protective slice is created per cumulative_covered breakpoint; assert sum(child.quantity) <= filled_quantity_so_far."
verify_command: "python -m pytest backend/tests/unit/pipeline backend/tests/unit/orders -q"
```

---

## P0 Follow-up (Owed)

```yaml
id: FOLLOWUP-A
title: Native Alpaca OCO submission (durable P0-3 fix)
severity: P0-followup
status: TODO
description: |
  P0-3 currently has a safety net only — sibling cancel-on-fill in
  BrokerSync. The durable shape is to translate `order_class="oco"`
  through AlpacaBrokerAdapter into Alpaca's native OCO order class so
  mutual exclusion is enforced atomically broker-side, with no race
  window between target fill and our cancel call.
fix_approach: |
  1. Extend BrokerAdapter Protocol with `submit_oco_pair(legs)` (or
     reshape submit_order to accept a paired bundle).
  2. In AlpacaBrokerAdapter, add an `order_class == "oco"` branch in
     the request builder mirroring the existing `"bracket"` branch
     (alpaca.py:313). Per Alpaca docs OCO requires an existing position
     and exactly one stop + one limit leg.
  3. Update create_protective_orders_post_fill callers so the two
     children are submitted as a single OCO group, not two independent
     calls.
  4. Gate scale-out runners (>2 legs per slice) — those can't all fit
     in one OCO group; emit OCO-per-pair or surface a clear error.
  5. Once native OCO is enforcing mutual exclusion broker-side, the
     safety net in BrokerSync._cancel_oco_siblings becomes belt-and-
     suspenders. Keep it (defense in depth, also handles broker reject
     of OCO submission).
constraints:
  - "Alpaca OCO requires existing position — only the post-fill flow can use it (entry must fill first). Already true."
  - "Alpaca OCO supports one stop + one limit per group — multi-target scale-out plans need OCO-per-pair."
  - "Re-confirm with backend/app/brokers/preflight.py:234 — capability profile already mentions OCO support."
helpers:
  - "backend/app/brokers/alpaca.py:300-325 — _build_request, mirror this for OCO"
  - "backend/app/brokers/capabilities.py:23 — BrokerOrderClass.OCO already exists"
  - "backend/app/brokers/preflight.py:219-247 — preflight already aware of OCO"
  - "backend/app/orders/manager.py:342-489 — create_protective_orders_post_fill"
acceptance_tests:
  - "test_alpaca_native_oco_submission (mirrors test_alpaca_native_bracket.py)"
  - "test_post_fill_protective_pair_uses_native_oco_when_two_legs"
  - "test_three_leg_scale_out_falls_back_to_oco_per_pair_or_errors"
verify_command: "python -m pytest backend/tests/unit/brokers backend/tests/unit/orders backend/tests/unit/pipeline -q"
```

---

## P1 — Hardening Before Scale

```yaml
id: P1-1
title: Native vs post-fill bracket use different reference prices for same SignalPlan
severity: P1
status: TODO
location: backend/app/pipeline/orchestrator.py:1020-1056
description: |
  Native bracket path computes child prices from one reference (limit
  price for limit entries, latest bar close for market entries). Post-
  fill path computes from actual fill price. Same SignalPlan in
  research vs live diverges silently.
fix_approach: |
  Pick one reference policy and apply it in both paths. Document the
  choice. Most defensible: post-fill path is canonical (uses actual
  fill); the native-bracket path should approximate that pre-fill but
  surface the divergence in protection_status metadata.
helpers:
  - "backend/app/pipeline/orchestrator.py:_native_bracket_reference_price"
  - "backend/app/orders/protective_placer.py — post-fill reference"
verify_command: "python -m pytest backend/tests/unit/pipeline backend/tests/unit/orders -q"
```

```yaml
id: P1-2
title: protection_status="protected" counts stop-only
severity: P1
status: TODO
location: backend/app/operations/service.py:159-163,209-210
description: |
  A position with rejected target reads "protected" because the check
  counts the stop child only. Multi-target scale-out runner has no stop
  child but also reads protected.
fix_approach: |
  Replace boolean protection_status with protection_coverage_pct
  (0.0..1.0) computed from sum(child.quantity for live protective children)
  / position.qty. UI reads coverage_pct; "protected" alias remains for
  full coverage. See feedback memory on scale-out runner semantics.
helpers:
  - "backend/app/operations/service.py — operator-visible health surface"
  - "MEMORY.md — feedback on scale-out semantics"
verify_command: "python -m pytest backend/tests/unit/operations -q"
```

```yaml
id: P1-3
title: _native_bracket_reference_price falls back to stale bar.close with no freshness check
severity: P1
status: TODO
location: backend/app/pipeline/orchestrator.py:1056
description: |
  Overnight gap → stop computed from yesterday's close → stop hits
  immediately at next-day open fill.
fix_approach: |
  Reject native bracket submission when reference bar is older than a
  configurable freshness threshold (e.g. 5 minutes during RTH). Fail
  closed; the operator can fall back to post-fill path which uses the
  actual fill price.
verify_command: "python -m pytest backend/tests/unit/pipeline -q"
```

```yaml
id: P1-4
title: requires_risk_plan silently skipped when Deployment.risk_horizon unset
severity: P1
status: TODO
location:
  - backend/app/governor/policy_resolver.py:96-127
  - backend/app/pipeline/orchestrator.py:1491
description: |
  Operator escape hatch by omission — leaving Deployment.risk_horizon
  None bypasses the requires_risk_plan check.
fix_approach: |
  Treat missing risk_horizon as fail-closed when policy.requires_risk_plan
  is True. Reject with rule_id="risk_horizon_missing".
verify_command: "python -m pytest backend/tests/unit/governor -q"
```

```yaml
id: P1-5
title: Floor policy loaded once at boot — operator pause needs restart
severity: P1
status: TODO
location: backend/app/governor — wherever PortfolioGovernor is constructed once
description: |
  Operator pause via save_portfolio_governor_state writes to persistence
  but the in-memory governor singleton holds the boot-time copy.
fix_approach: |
  Refresh policy from runtime_store at evaluate-time (with TTL cache to
  avoid hammering the store), or wire a reload signal from the
  operator API endpoint.
verify_command: "python -m pytest backend/tests/unit/governor backend/tests/unit/operations -q"
```

```yaml
id: P1-6
title: Replay path skips ProtectiveOrderPlacer entirely
severity: P1
status: TODO
location: backend/app/simulation/historical_replay.py:330-690
description: |
  Research can't validate the bracket logic that ships to live. Backtests
  pass through with no protective placement at all.
fix_approach: |
  Wire ProtectiveOrderPlacer into the replay engine. Use the same
  protective_placer instance the orchestrator uses; thread the bar
  timestamp into evaluated_at (already supported per P0-2).
helpers:
  - "backend/app/orders/protective_placer.py"
  - "backend/app/simulation/historical_replay.py — replay event loop"
verify_command: "python -m pytest backend/tests/unit/simulation -q"
```

---

## P2 — Smaller Hardening

```yaml
id: P2-1
title: _account_field/_plan_field use getattr(..., None) — silent on typos
severity: P2
status: TODO
description: |
  Replace `getattr(obj, field, None)` with a closed allowlist or direct
  attribute access so a typo'd field name fails loudly.
verify_command: "python -m pytest backend/tests/unit/governor -q"
```

```yaml
id: P2-2
title: Surface double_protected warning when native + post-fill children both exist
severity: P2
status: ✅ DONE
description: |
  Edge case: race between native bracket attach and post-fill placer
  creates double children for the same entry. Detect and surface a
  warning in operations/service.py.
verify_command: "python -m pytest backend/tests/unit/operations -q"
```

```yaml
id: P2-3
title: ET midnight uses zoneinfo with bare-except UTC-5 fallback
severity: P2
status: ✅ DONE
location: backend/app/runtime/daily_account_state.py:21-25
description: |
  If tzdata is missing the fallback is fixed UTC-5 with no DST → silent
  skew. At least log when the fallback fires; ideally fail closed in
  production builds.
verify_command: "python -m pytest backend/tests/unit/runtime -q"
```

---

## Suspected — Investigate Before Fixing

```yaml
id: S-1
title: Cold-boot fill-before-snapshot silently disarms drawdown gate
severity: Suspected
status: INVESTIGATED (guarded by fail-closed equity gate + regression)
description: |
  If first stream event after boot is a FILL before the first
  account-snapshot, equity=None → drawdown_pct=0 even with realized
  loss → drawdown gate silently disarmed.
investigate: |
  Trace BrokerStreamRunner ordering at supervisor cold-boot. Check
  whether account snapshot is required-before-stream or merely
  best-effort. If best-effort, add an "equity_unknown" projected_state
  flag and reject opens until snapshot lands.
helpers:
  - "backend/app/runtime/account_trading_orchestrator.py — boot sequence"
  - "backend/app/brokers/sync.py:440-446 — equity read site"
```

```yaml
id: S-2
title: Operator-canceled stop child may be re-placed on next fill
severity: Suspected
status: ✅ DONE
description: |
  If operator manually cancels a stop child (vs broker-rejected), does
  the next partial-fill event re-place protective coverage and
  effectively undo the operator action?
investigate: |
  Check whether create_protective_orders_post_fill consults canceled-
  by-operator state or only checks "live children of this slice".
  Trade ledger should distinguish reason="operator_cancel" vs
  reason="broker_reject".
helpers:
  - "backend/app/orders/manager.py:342-489"
  - "backend/app/orders/trade_ledger.py"
```

```yaml
id: S-3
title: attach_native_bracket_to_entry re-attach uses 1e-9 fp tolerance
severity: Suspected
status: ✅ DONE
location: backend/app/orders/manager.py:491-535 (attach_native_bracket_to_entry)
description: |
  Re-attach equality check uses a 1e-9 tolerance — fp drift across
  recomputations could false-mismatch identical inputs. Low likelihood
  but worth confirming.
investigate: |
  Read the equality check; assess whether the inputs always come from
  the same source (in which case bit-equality is fine) or from
  recomputation (in which case use a wider tolerance like 1e-6 or
  round to broker tick size).
```

```yaml
id: S-4
title: _daily_states dict shared by reference across BrokerSyncService instances
severity: Suspected
status: ✅ DONE
description: |
  10 deployments × 1 account → multiple BrokerSyncService instances
  may share _daily_states by reference. CPython dict assignment is
  atomic but read-modify-write isn't → total_loss_today could lose
  updates under concurrent fills.
investigate: |
  Confirm whether the dict is one-per-account-runner or one-per-
  service. If shared, add a per-account lock around the
  read-modify-write in _apply_daily_state_fill, OR move all fill
  application onto a single per-account thread.
helpers:
  - "backend/app/brokers/sync.py:437-452 — _apply_daily_state_fill"
  - "backend/app/runtime/account_trading_orchestrator.py:431-432 — owner of _daily_states"
```

---

## Test Coverage Gaps (Add Even Without Fixing)

These tests are missing today and would have caught the bugs above.
Even before the corresponding fix lands, write the failing test to lock
in the regression scope.

```yaml
- id: T-GAP-1
  for: P0-3 (safety net)
  test: "OCO sibling cancellation on target fill"
  status: SHIPPED in test_broker_sync_oco_sibling_cancel.py

- id: T-GAP-2
  for: P0-4
  test: test_cooldown_does_not_bleed_across_market_day_boundary
  location_hint: backend/tests/unit/runtime/test_daily_account_state.py

- id: T-GAP-3
  for: P0-6
  test: test_concurrent_partial_fills_do_not_double_protect
  location_hint: backend/tests/unit/pipeline

- id: T-GAP-4
  for: P1-6
  test: test_replay_post_fill_bracket_matches_live_placer_prices
  location_hint: backend/tests/unit/simulation

- id: T-GAP-5
  for: P1-4
  test: test_requires_risk_plan_skipped_when_deployment_horizon_unset
  location_hint: backend/tests/unit/governor

- id: T-GAP-6
  for: S-1
  test: test_drawdown_gate_silently_disarmed_when_equity_unknown
  location_hint: backend/tests/unit/governor or backend/tests/unit/runtime

- id: T-GAP-7
  for: P0-5
  test: structured_log_assertion_on_save_daily_account_state_failure
  location_hint: backend/tests/unit/brokers

- id: T-GAP-8
  for: P1-1
  test: native_vs_post_fill_price_symmetry_for_same_signal_plan_and_fill_price
  location_hint: backend/tests/unit/pipeline

- id: T-GAP-9
  for: P1-5
  test: floor_policy_refresh_after_operator_pause
  location_hint: backend/tests/unit/governor
```

---

## Working Protocol for the Next Agent

1. **Re-read MEMORY.md first.** The doctrine memories are load-bearing —
   "production-grade only", "Operation Turtle Shell ownership",
   "multi-account density". Don't ship a fix that violates them.

2. **Re-read AGENTS.md** for the Nanyel Coordinator/Evaluator/Approver
   standard before any non-trivial change.

3. **Order suggestion:** P0-4 → P0-5 → P0-6 → FOLLOWUP-A → P1s. Reason:
   P0-4 and P0-5 are small and self-contained; P0-6 is structural
   (touches threading) so do it after P0-4/5 land; FOLLOWUP-A is the
   durable fix you owe for P0-3 and is high-leverage. P1s can be
   parallelized.

4. **Per fix:**
   - Read the file refs in `location` and `helpers`.
   - Run the `verify_command` first to confirm baseline green.
   - Write the regression test first (acceptance test); confirm it
     fails for the right reason.
   - Implement the fix.
   - Re-run `verify_command`; then run the wider sweep
     `python -m pytest backend/tests/unit -q`.
   - Update this file: flip the status row, leave a one-liner pointing
     at the commit SHA.

5. **When in doubt, surface the trade-off.** The user explicitly chose
   safety-net-first for P0-3 after pushback on the workaround pattern.
   Same lens applies elsewhere — when a fix has a "patch now, durable
   later" path AND a "durable now, slower" path, name both before
   coding.

6. **Last green baseline:** 1671 unit tests pass as of 2026-04-30.
   `python -m pytest backend/tests/unit -q`.
