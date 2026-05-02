# HARD.md → Digestible Milestones

**Source:** [HARD.MD](HARD.MD) (Coordinator synthesis 2026-05-01)
**Branch:** feature/cleanup-modern-core
**Target density:** 10 broker Accounts (per memory)
**Doctrine:** Operation Turtle Shell ([Operations_Turtle_Shell_Artifacts/](Operations_Turtle_Shell_Artifacts/))

---

# 📋 Execution Order & Status Tracker

> **Numbering convention:** `S#` = step in execution order. Parentheses `(S2|S3|S4)` = parallel-runnable, no shared files, different owners. `[S#]` = deferrable / opt-in. **M-IDs are stable** — they never change, so audit links back to HARD.MD priority labels (P0-1, P0-2, etc.) hold across renumbering.

## Compact route

```
S1 → (S2 | S3 | S4) → S5 → S6 → (S7 | S8) → S9 → S10    [S11 opt-in]
```

## Status table (update in place — this is the dashboard)

| Step | Parallel-with | M-ID | Title | Owner | HARD.MD label | Gate (must be done first) | Status |
|------|---------------|------|-------|-------|---------------|---------------------------|--------|
| **S1** | — | M6 | Account Trade Sync startup orchestration | Backend Spine | P1-5 | — | ✅ done (re-baseline 2026-05-02 — already shipped in `runtime_context.bootstrap_streams` + `TradeEventDispatcher`; HARD.MD finding stale) |
| **S2** | S3, S4 | M1 | Slice 11 REST reconciliation scheduler | Backend Spine | P0-1 | S1 | ✅ done (2026-05-02 06:30, Claude sub-agent — split orders/positions+account cadence + jitter + degraded fast-path) |
| **S3** | S2, S4 | M3 | Alpaca preflight hardening (1 PR) | Alpaca | P0-3, P1-1, P1-2, P1-4 | — | ✅ done (2026-05-02 08:30, Claude Alpaca Expert sub-agent — 7 rules, +43 tests) |
| **S4** | S2, S3 | M8 | Frontend trust pass | Frontend | P1-8, P1-9, P1-10, P1-11 | — | ✅ done (2026-05-02 04:50, Claude) |
| **S5** | — | M2 | Unmanaged broker position visibility & gating | Backend Spine + Alpaca | P0-2 | S2; Q1 answered | ✅ done backend (2026-05-02 12:30, Claude — model + classification + Governor PortfolioSnapshot.unmanaged_positions concentration include + factory wire-up; +17 tests across two suites) |
| **S6** | — | LIVE-VERIFY | Monday live-market verification (full spine fresh fill) | **Operator** | HARD.MD line 97 | S1+S2+S3+S5 all green | 🟢 unblocked — operator can now verify |
| **S7** | S8 | M5 | Trailing stop support | Alpaca | P1-3 | S3 | ✅ done (2026-05-02 08:30, Claude Alpaca Expert sub-agent — bundled with M3) |
| **S8** | S7 | M7 | Strategy null-guard + 10-Account density test | Backend Spine | P1-6, P1-7 | S1; Q6 answered | ✅ done (2026-05-02 11:30, Track C Claude sub-agent — null-guard at RuntimeOrchestrator.__init__ + 10-Account × 5-symbol density test passes with P99 latency cap) |
| **S9** | — | M9 | Explainers + minor frontend cleanup + Compose Defaults selectors (Item A) | Frontend + Backend | P2 batch | S4; Q5, Q7 answered | ✅ done end-to-end (2026-05-02 05:05+11:30, Claude — frontend Compose Defaults + 5 explainers + a11y; backend Refresh Sync endpoint + logical-exit closed-bars 3-case tests) |
| **S10** | — | M10 | Error taxonomy + live-mode init guard | Alpaca + Backend Spine | P2-tail | S9; Q3 answered | ✅ done (2026-05-02 11:30+12:30, Claude — BrokerErrorEvent + apply_result audit log shipped; AlpacaBrokerAdapter live-mode env+per-Account guard enforced; PUT /allow-live route + composition wires allow_live through 4 adapter sites; +3 tests) |
| **[S11]** | opt-in | M4 | Native bracket / OCO / OTO submission | Alpaca | P0-4 | S3; Q4 answered | ✅ done (2026-05-02 08:30, Claude Alpaca Expert sub-agent — preflight blanket reject removed; FOLLOWUP-A native OCO post-fill already shipped by Codex 2026-04-30) |
| **S12** | — | M11 | Account Guardian Assignment | Backend Spine + Frontend | S5; inherits Q1 fail-closed | ✅ done end-to-end (2026-05-02 05:15→12:30, Claude — frontend + health predicate + Account fields + PUT /guardian + adoption pathway 4-case logic in `apply_guardian_adoption` + `position_has_active_protective_orders` + production wire via `BrokerSync.guardian_context_provider`; 48+20 tests) |

**Legend:** ☐ todo · ◐ in-progress · ✅ done · ⊘ skipped · ⛔ blocked

## Live-trading gate

`S1 + S2 + S3 + S5 + S6` (operator verification) must be ✅ before live trading.
**S11/M4 is intentionally NOT on the gate** — internal-leg decomposition is sufficient (HARD.MD §17).

## Open Questions → Steps they gate

| Q | Question | Gates step |
|---|----------|------------|
| Q1 | Unmanaged-position policy: fail-closed vs fail-open with warning | S5 |
| Q2 | Slice 11 cadence values + per-Account vs per-env config | S2 |
| Q3 | Live-mode enablement mechanism (env / per-Account / operator confirm) | S10 |
| Q4 | Native bracket vs decompose preference when both valid | S11 |
| Q5 | `closed_only=True` — Strategy-level setting or hardcoded for `logical_exit` | S9 |
| Q6 | Multi-Account ceiling vs target | S8 |
| Q7 | Components route + ResearchEvidencePage — wire or delete | S9 |

## Audit trail

Every Step row carries:
- A **Step #** (execution order — may renumber if scope changes)
- An **M-ID** (stable; cross-references the milestone body in this file)
- A **HARD.MD label** (P0-1 / P0-2 / P1-x / P2 — cross-references the source synthesis)
- A **Gate** (explicit dependency, in Step terms — auditable predicate)
- A **Status** (single source of truth — flip in place as work moves)

To audit: pick any Step row → follow M-ID to its milestone body for spec → follow HARD.MD label to the source finding → check Gate column for what must be true first.

---

## Global Assumptions
- A1. Backend unit baseline = **1103 passing**; every milestone preserves this and net-adds tests.
- A2. No `uvicorn --reload` with broker WS (per memory: orphan-guard / 1-conn slot).
- A3. Multi-Account fan-out (Slice 9) is wired and correct; we are layering on top of it.
- A4. `client_order_id` schema `sigplan-{acct8}-{plan8}-{intent}-{hash10}` is the canonical form (playbook §2 wording is equivalent).
- A5. Operator runs ~10 Alpaca Accounts; 10 is the **target with headroom**, not a hard ceiling (resolve Q6 before M7).
- A6. Production-grade only — no temporary shims, no parallel forks (per memory).

## Global Non-Functional Requirements
- NFR1. Fail-closed on broker truth gaps (per Playbook §15).
- NFR2. Deterministic `client_order_id`; idempotent restart preserved end-to-end.
- NFR3. P99 per-bar pipeline latency must not regress on the 10-Account load test.
- NFR4. No silent operator actions — every destructive action has confirmation + post-action evidence.
- NFR5. Every new backend field lives on exactly one of the four ownership layers (Strategy / StrategyControls / ExecutionPlan / Account+Governor).
- NFR6. Roadmap status (`researchRoadmap.ts`) flips to **shipped** in the same slice that ships it.

---

## Open Questions (resolve before the gated milestone)
- Q1. **Unmanaged-position policy** — fail-closed (default per Playbook §15) vs fail-open with warning. **Gates M2.**
- Q2. **Slice 11 cadence parameters** — orders 30–60s / positions+account 60–120s. Per-Account vs per-env config. **Gates M1.**
- Q3. **Live-mode enablement** — env var, per-Account flag, or operator confirmation? **Gates M10.**
- Q4. **Native bracket vs internal-leg decomposition preference** when both are valid. **Gates M4.**
- Q5. **`closed_only=True`** — Strategy-level setting or hardcoded for `logical_exit`? **Gates M9 logical-exit test.**
- Q6. **Multi-Account ceiling vs target** — affects scheduler jitter + dispatcher design. **Gates M7.**
- Q7. **Components route + ResearchEvidencePage** — wire or delete. **Gates M9.**

---

# Priority 0 — Trading Safety (must land before live)

## M1 — Slice 11: Account Trade Sync REST Reconciliation Scheduler
**Maps to:** P0-1 · **Repair Step 1** · [Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md](Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md) §Slice 11
**Pairs with:** **M6** — scheduler is meaningless without the boot orchestration that enumerates Accounts and opens streams. Ship M1+M6 as a single "broker truth foundation" track.
**Why first:** Without it, Governor `is_stale` reflects WS health, not REST truth. Everything downstream depends on broker truth.

### Functional Requirements
- FR1.1 Adaptive per-Account scheduler around the existing registry.
- FR1.2 REST reconcile triggers: **on startup**, **on reconnect**, **on event-gap**.
- FR1.3 Periodic cadence on healthy stream: orders **30–60s**, positions+account **60–120s** (Q2).
- FR1.4 Faster cadence on degraded stream; jitter + per-Account backoff sized for 10 Accounts (A5).
- FR1.5 Operations API surfaces **stream freshness** separately from **REST freshness**.
- FR1.6 Governor gating consumes both freshness signals (today: only `broker_sync.is_stale`).

### Non-Functional Requirements
- NFR1.1 No thundering herd at 10 Accounts (jitter on first tick + per-Account phase offset).
- NFR1.2 Backoff bounded; failures don't starve other Accounts.
- NFR1.3 Cadence values are **configurable per Account or env** (Q2 outcome).

### Tests (non-negotiable)
- T1.1 Stream alive + REST dead → Governor blocks new opens.
- T1.2 Reconnect path triggers REST reconcile within bound.
- T1.3 Periodic cadence stays within configured bounds under steady state.
- T1.4 10 Accounts: per-Account ticks don't collide; backoff isolation works.

### Assumptions
- AS1.1 `backend/app/brokers/sync.py` `sync_open_orders/positions/account/reconcile()` are correct primitives — only the **caller** is missing.
- AS1.2 Operations page can grow two freshness columns without redesign.

### Owner: Backend Spine

---

## M2 — Unmanaged Broker Position Visibility & Gating
**Maps to:** P0-2 · **Repair Step 2** · Playbook §15
**Why second:** Without this, Governor concentration gates run on a partial portfolio view.
**Gated by:** Q1 (fail-closed vs fail-open).

### Functional Requirements
- FR2.1 Add `unmanaged_broker_position: bool` to `BrokerPositionSnapshot`.
- FR2.2 In `BrokerSync._enrich_position_snapshot_with_lineage`, classify any broker position with no `position_lineage_id` as unmanaged.
- FR2.3 Surface unmanaged positions in Operations (badge + count + per-symbol list).
- FR2.4 Include unmanaged positions in `GovernorRequest.portfolio.positions` for concentration evaluation.
- FR2.5 Adoption flow remains explicit and gated (no implicit adoption).
- FR2.6 Default policy: **fail-closed** unless Q1 lands otherwise.

### Non-Functional Requirements
- NFR2.1 Classification is idempotent across reconciles.
- NFR2.2 No silent "protection" of unmanaged positions ever (Playbook §15).
- NFR2.3 Operator can see *why* concentration was denied (unmanaged contribution shown).

### Tests
- T2.1 Broker-only position classified as `unmanaged_broker_position=True`.
- T2.2 Unmanaged position contributes to concentration eval; new opens blocked when threshold crossed.
- T2.3 Protective order on unmanaged position requires explicit adoption (no auto-OCO).
- T2.4 Adoption flips `unmanaged → managed` cleanly.

### Owner: Backend Spine + Alpaca

---

## M3 — Alpaca Preflight Hardening (single PR)
**Maps to:** P0-3, P1-1, P1-2, P1-4 · **Repair Step 3**
**Why third:** Pure preflight; lands clean once M1/M2 stabilize broker truth.

### Functional Requirements
- FR3.1 Stop-distance ≥ **$0.01** vs base price (Playbook §7).
- FR3.2 Reject **fractional + short** combinations (Playbook §9).
- FR3.3 Extended-hours rule (Playbook §10): allow `limit + (DAY|GTC)`; reject IOC/FOK/OPG/CLS and non-limit.
- FR3.4 Reject **OTO replace**.
- FR3.5 Reject **notional replace**.
- FR3.6 Explicit **qty XOR notional** check.
- FR3.7 **Short-side BP estimate** plumbed through `MarketRulePreflightRequest` — `max(limit, 1.03·ask)·qty` (Playbook §11). Requires `ask_price` input.

### Non-Functional Requirements
- NFR3.1 All new rules return structured rejection codes (not raw strings) — wire toward M10 error taxonomy.
- NFR3.2 Each rule independently testable via parametrized table.

### Tests (one parametrized table per rule)
- T3.1 stop $0.005 reject / $0.01 accept.
- T3.2 fractional+short reject.
- T3.3 EH+limit+gtc accept; EH+limit+ioc reject; EH+market reject.
- T3.4 OTO replace reject.
- T3.5 qty+notional reject; neither reject.
- T3.6 notional replace reject.
- T3.7 short-BP-insufficient reject; sufficient accept.

### Owner: Alpaca

---

## M4 — Native Bracket / OCO / OTO Submission
**Maps to:** P0-4 · **Repair Step 4**
**Gated by:** Q4 (native vs decompose preference when both valid).
**Deferrable:** Per HARD.MD §17, P0-4 is **opt-in** — internal-leg decomposition can carry live trading; M4 unlocks native shapes when we want them. Not a hard live-gate.

### Functional Requirements
- FR4.1 Remove blanket `UNSUPPORTED_ORDER_CLASS` block at `preflight.py:245-250`.
- FR4.2 Route shape-validated requests through existing `_validate_native_bracket_preflight` / `_validate_native_oco_preflight` in `alpaca.py:348-392` (currently dead code).
- FR4.3 **Multi-target (>1 TP) still decomposes** into internal legs sharing one SignalPlan/Position lineage.
- FR4.4 BrokerSync reconciles every child leg back to parent lineage.
- FR4.5 Q4 outcome encoded as a deterministic policy (not per-call decision).

### Non-Functional Requirements
- NFR4.1 No regression on internal-leg decomposition path (dual support).
- NFR4.2 Single reconciliation surface — child fills always reach the same `Position`.

### Tests
- T4.1 Bracket buy: TP>stop, DAY/GTC, no EH, whole-share → accepted.
- T4.2 Multi-TP decomposed into shared-lineage legs.
- T4.3 Native bracket child-leg fills reconciled to same Position.
- T4.4 OCO/OTO shape edges (per playbook).

### Owner: Alpaca

---

# Priority 1 — Runtime Visibility & Correctness

## M5 — Trailing Stop Support
**Maps to:** P1-3 · **Repair Step 5**

### Functional Requirements
- FR5.1 Add `trail_price` / `trail_percent` to `InternalOrder` ([backend/app/orders/models.py](backend/app/orders/models.py)).
- FR5.2 Preflight: exactly one of `trail_price` XOR `trail_percent`.
- FR5.3 TIF must be `day` or `gtc`.
- FR5.4 Cannot be used as a bracket `stop_loss` leg.
- FR5.5 Advisory text: "no extended-hours protection."
- FR5.6 `BrokerOrderClass.TRAILING_STOP` becomes reachable from a real order path.

### Tests
- T5.1 Both trail_price + trail_percent → reject.
- T5.2 Trail + EH → advisory present.
- T5.3 Trail used as bracket stop_loss leg → reject.

### Owner: Alpaca

---

## M6 — Account Trade Sync Startup Orchestration
**Maps to:** P1-5 · **Repair Step 6**
**Memory link:** `feedback_no_uvicorn_reload_with_broker_ws.md`

### Functional Requirements
- FR6.1 App-boot loop: enumerate validated Alpaca Accounts.
- FR6.2 Per Account: instantiate `BrokerSyncService`, wire `AlpacaAccountStreamAdapter.subscribe()`.
- FR6.3 Mark Account stale until first event arrives.
- FR6.4 Log per-Account startup result (success / failure / latency).
- FR6.5 Pause does **not** close the stream — only suspends signal acceptance.

### Non-Functional Requirements
- NFR6.1 Orphan-guard from 2026-05-01 still functions; no `--reload` regression.
- NFR6.2 Boot time scales linearly with Account count up to 10.

### Tests
- T6.1 Boot opens one trade sync per validated Alpaca Account.
- T6.2 Pause leaves stream open.
- T6.3 Orphan-guard works without `--reload`.

### Owner: Backend Spine

---

## M7 — Strategy Null-Guard + 10-Account Density Test
**Maps to:** P1-6, P1-7 · **Repair Step 7**
**Gated by:** Q6 (ceiling vs target).

### Functional Requirements
- FR7.1 Explicit null-guard in `pipeline/orchestrator.py:445` — `Deployment.components.strategy is None` fails fast at start, not at first bar.
- FR7.2 New load test: **10 Accounts × 5 symbols × 1m bars**.
- FR7.3 Assert: zero dropped bars; bounded per-stage P99 latency.

### Non-Functional Requirements
- NFR7.1 Test runs in CI within reasonable time (cap, e.g., 60s wall).
- NFR7.2 Latency budget documented per stage (signal eval, governor, order submit, broker sync).

### Tests
- T7.1 Deployment with `strategy=None` raises at start.
- T7.2 Density test passes P99 latency target, drops zero bars.

### Owner: Backend Spine

---

## M8 — Frontend Trust Pass
**Maps to:** P1-8, P1-9, P1-10, P1-11 · **Repair Step 8**

### Functional Requirements
- FR8.1 `ToastProvider` + `useToast()` (Radix Toast). Wired into all mutation paths.
- FR8.2 Standardize `HoldToArmConfirm` for all destructive actions:
  - StrategiesV4 delete ([frontend/src/routes/StrategiesV4.tsx:181-187](frontend/src/routes/StrategiesV4.tsx#L181-L187))
  - Watchlists bulk delete
  - Operations global kill (upgrade to **typed-confirm + reason**, currently plain Button at [frontend/src/routes/Operations.tsx:60](frontend/src/routes/Operations.tsx#L60))
- FR8.3 Wrap all chart containers (ChartLab `PriceChart`, `StrategyPreviewChart`, SimLab) with explicit **Loading / Empty / Stale / Error** states. Detect WS drop → Stale.
- FR8.4 Vitest cases for every destructive confirm flow + ≥1 happy-path mutation per page.

### Non-Functional Requirements
- NFR8.1 Toasts emitted on **every** successful mutation in Accounts/Operations/Watchlists.
- NFR8.2 No new design system — extend existing primitives.

### Tests (vitest)
- T8.1 `DangerConfirm` requires name match + reason ≥ 3 chars.
- T8.2 `HoldToArmConfirm` requires hold timer.
- T8.3 Chart container shows Stale on WS drop.
- T8.4 Toast emitted on successful mutation per route.

### Owner: Frontend

---

# Priority 2 — Polish & Tail

## M9 — Explainers + Minor Frontend Cleanup
**Maps to:** P2 batch · **Repair Step 9**
**Gated by:** Q7 (Components/ResearchEvidencePage decision).
**Note:** T9.3 (logical-exit closed-bars) is correctness, not polish — it should ride alongside M2, not wait for the P2 wave (HARD.MD §38, §79).

### Functional Requirements
- FR9.1 Backfill `frontend/src/routes/explainerContent.ts` for the **11 missing slugs**: Watchlists, Deployments, RiskPlans, Screeners, ChartLab, SimLab, Backtests, Optimization, WalkForward, ExecutionPlans, StrategyControls.
- FR9.2 Account card "Refresh Sync" button (manual REST trigger).
- FR9.3 `aria-invalid` / `aria-describedby` on `TextField`.
- FR9.4 Null-guard `detailFrom(body)` at [frontend/src/api/client.ts:57-65](frontend/src/api/client.ts#L57-L65).
- FR9.5 Decide Components route + `ResearchEvidencePage`: wire or delete (per Q7).
- FR9.6 WS hook exposes sequence-gap detection.
- FR9.7 Logical-exit closed-bars test (per Q5 outcome).

### Tests
- T9.1 Each new explainer slug renders non-empty content.
- T9.2 Refresh Sync triggers REST reconcile.
- T9.3 Logical-exit: 2 closed + 1 open → no SignalPlan; 3 closed → emitted; in-progress 4th does not re-emit.

### Owner: Frontend + Backend (Refresh Sync endpoint)

---

## M10 — Error Taxonomy + Live-Mode Init Guard
**Maps to:** P2-tail · **Repair Step 10**
**Gated by:** Q3 (live-mode enablement).

### Functional Requirements
- FR10.1 Structured `BrokerErrorEvent` per Playbook §17: `family`, `severity`, `source`, `operator_advisory`, `raw_broker_code`, `raw_broker_message`.
- FR10.2 `AlpacaBrokerCapabilities` `__init__` raises if `mode==BROKER_LIVE` without explicit gate satisfied (Q3).
- FR10.3 RiskResolver detail surfaced in Operations API (today only embedded in `AccountSignalPlanEvaluation.risk_resolver_result`).
- FR10.4 `client_order_id` mapping logged in `BrokerSync.apply_result` (audit trail for mismatch root-cause). *(Sourced from HARD.MD §35 P2 list; folded here, not in original Repair Step 10.)*

### Non-Functional Requirements
- NFR10.1 Errors no longer leak as raw exceptions to logs.
- NFR10.2 Live-mode gate is **explicit and revocable** at the per-Account level.

### Tests
- T10.1 BROKER_LIVE without gate → init raises.
- T10.2 Each error family produces a structured event with required fields.
- T10.3 RiskResolver detail visible in Operations API response.

### Owner: Alpaca + Backend Spine

---

# "Left Work" Cross-Cuts (from HARD.MD lines 95–113)
These are not standalone milestones; they fold into the milestones above.

| Item | Folds into | Driver |
|---|---|---|
| Monday live-market verification (full spine fresh fill) | Acceptance gate **after** M1+M2+M3+M6 | **Operator** (not Claude) |
| Protective order restart recovery (ATR warmup on fresh bars) | M2 + M9 logical-exit test | Backend |
| Logical exits bars-since-entry rule under live hours | M9 (T9.3) — promote to ride with M2 | Backend |
| Alpaca OCO audit edge — nested OCO child confirmation post-downtime/partial-fill | M4 (T4.3) extended | Alpaca |
| Branch cleanup (legacy Program shims, old Strategy Builder leftovers) | Continuous on `feature/cleanup-modern-core` | See Legacy Elimination Ledger below |
| UI walk-through of v4 surfaces | Manual acceptance during M8 | **Operator** |

> **Owner attribution note:** HARD.MD only assigns explicit owners to P0 (rows 12–16). P1/P2 owners in this doc are inferred from file ownership and existing specialist sweeps.

---

# Cross-Functional Optimal Route — Architecture + UI Board

The single-file sequence above is correct as a dependency map but suboptimal as a delivery plan. Three owners can run **in parallel** on most of this work. The route below maximizes throughput, minimizes blocking, and folds legacy elimination into the wave it naturally belongs in.

## Lanes (run in parallel)

```
                   WAVE 1 — Broker Truth          WAVE 2 — Live Gate          WAVE 3 — Trust + Tail
                   (week 1)                        (week 2)                    (week 3+)
                   ─────────────────              ────────────────             ───────────────────
Backend Spine  ──▶ M6 boot orchestration ──▶ M1 scheduler ──▶ M2 unmanaged ──▶ M7 density+null ──▶ M9.7 logical-exit test
                                                                              (in parallel ↘)
Alpaca         ──▶ M3 preflight hardening ──────────────────▶ M5 trail stop ──▶ M4 native bracket (opt-in)
                                                                              (in parallel ↘)
Frontend       ──▶ M8 trust pass (toasts, confirms, charts) ─────────────────▶ M9 explainers + dead-route purge
                                                                                                    │
                                                                                                    ▼
                                                                                              M10 error taxonomy
                                                                                              + live-mode gate
```

## Critical path to live trading

`M6 → M1 → M2 → operator Monday verification`. Everything else is parallel-runnable on independent owners. M3 lands in Wave 1 alongside the broker-truth track because it shares no files with M1/M2/M6 and removes a class of round-trip rejections that would muddy live verification.

**M4 is explicitly NOT on the critical path** — internal-leg decomposition is sufficient for live (HARD.MD §17). Schedule M4 only when operator wants native broker OCO behavior.

## Force multipliers (do these first within their lane)

1. **M6 (boot orchestration)** unlocks every per-Account behavior — M1 scheduler, M2 unmanaged classification, M7 density test, the operator Monday verification. Without M6 the rest is bench-tested only.
2. **M3 (preflight hardening)** is one PR that closes one P0 + three P1s. Highest-density work in the doc.
3. **M8 ToastProvider** unblocks every other frontend mutation pattern — every later mutation can land its toast for free once the provider exists.

## Scalability checkpoints (10 → beyond)

The architecture must hold past 10 Accounts even if the operator stays at 10. These are the load-bearing decisions:

| Decision | Where it scales | Where it breaks |
|---|---|---|
| Per-Account scheduler with jitter (M1) | Stateless ticks; jitter prevents thundering herd | Single global scheduler with shared queue would synchronize REST hits |
| Per-Account stream (M6) | Alpaca is 1-conn-per-account; one stream each is the only correct shape | Multiplexing breaks the orphan-guard model |
| Shared market-data hub + per-Account dispatcher (Slice 9, already wired) | Symbol fan-in once, fan-out N times | Per-Account market data subscriptions would 10× the upstream cost |
| Governor evaluation (M2) | Stateless per-request | Concentration eval that requires global lock would serialize at scale |
| Frontend Operations table (M8) | Virtualized list per Account row | Today renders all rows; fine at 10, will jank at 50+ |

**Q6 (Multi-Account ceiling vs target)** must be answered before M7 codes the load test target. Recommendation: **target 10, design for 25, document break-points at 50.**

## Legacy Stack Elimination Ledger

Folded into the wave that naturally retires it — no separate "cleanup" milestone.

| Legacy item | Eliminated in | How |
|---|---|---|
| Dead `_validate_native_bracket_preflight` / `_validate_native_oco_preflight` in `alpaca.py:348-392` | **M4** | Reactivated, no longer dead code |
| Plain Buttons for destructive actions (StrategiesV4 delete, Operations global kill, Watchlists bulk delete) | **M8** | Standardized to `HoldToArmConfirm` / typed-confirm |
| `ManualOrderDrawer`'s bespoke inline-Banner pattern | **M8** | Subsumed by ToastProvider |
| `DangerConfirm` vs `HoldToArmConfirm` vs plain Button drift | **M8** | One pattern wins per action class |
| 11 missing explainer slugs (empty drawer fallback) | **M9** | Backfilled |
| Components route as PlaceholderPage | **M9** (per Q7) | Wire or delete |
| `ResearchEvidencePage` dead code | **M9** (per Q7) | Wire or delete |
| Raw exception leaks (no structured `BrokerErrorEvent`) | **M10** | Playbook §17 taxonomy |
| Old vanilla-JS Strategy Builder leftovers | **Continuous on this branch** | Per memory: `feedback_frontend_full_redesign.md` |
| Legacy "Program" shims (non-core) | **Continuous on this branch** | Branch is `feature/cleanup-modern-core` |
| Backend `strategies_v4` parallel package | **Slice 11/12** (NOT now) | Per memory: `project_strategy_ide_v4_legacy_cutover_split.md` — do not fight the lock |
| `BatchFeatureEngine` (already deleted Slice 5) | ✅ Done | Per memory: `reference_canonical_feature_engine.md` |

## What this route is NOT doing

- **Not** sequencing M5, M7, M8, M9 behind the P0 wave. They have different owners and zero file overlap with M1/M2/M3/M6.
- **Not** treating M4 as a live-trading blocker.
- **Not** opening a separate "branch cleanup" milestone. Cleanup that has a natural home in another wave goes there; cleanup that doesn't (Program shims, Strategy Builder leftovers) is continuous on this branch.
- **Not** touching the backend `strategies_v4` parallel package — locked until Slice 11/12 per memory.

---

# Single-Owner Sequencing Summary (fallback if running solo)

If only one owner is available, collapse the parallel groups by inserting them sequentially in any order within each `(...)` group:

```
S1 ─► S2 ─► S3 ─► S4 ─► S5 ─► S6 ─► S7 ─► S8 ─► S9 ─► S10    [S11 opt-in]
(M6)  (M1)  (M3)  (M8)  (M2) (live) (M5)  (M7)  (M9)  (M10)   (M4)
```

**Live-trading gate:** S1 + S2 + S3 + S5 + S6 all green.
*(S11/M4 is intentionally excluded from the live gate — see HARD.MD §17.)*

**Test budget:** preserve 1103 baseline; net-add ~80–120 tests across milestones.
