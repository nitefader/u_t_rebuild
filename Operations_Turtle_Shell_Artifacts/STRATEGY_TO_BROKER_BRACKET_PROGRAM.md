# Strategy-to-Broker Bracket Program

Owner: Claude (operator override into Codex-owned `backend/app/{governor,pipeline,runtime,strategies,orders,brokers,persistence,domain,strategy_composer,signal_planner,deployments}/` and `frontend/src/`).
Started: 2026-04-29 21:52:00 -04:00.
Operator basis: Nanyel — *"Run this end-to-end yourself. Do not wait for Codex."* and *"Add these items to the same end-to-end program plan."* and *"You go online and research Alpaca too"* and *"check if it supports notional and fractional orders etc."*.
Doctrine references: `HANDOFF_PROTOCOL.md`, `TURTLE_SHELL_GUARDRAILS.md`, `GOVERNOR_WIRING_MAP.md`, `RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT.md`, `MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md`, `COORDINATION/PROTOCOL.md`.

Approved saved entities (operator approval received in resume prompt 2026-04-29):
- `strategy_controls_versions` (immutable; binds to `deployments`, not to `strategy_versions` — see Doctrine Clarification below)
- `execution_plan_versions` (immutable; binds to `deployments`; replaces ad-hoc "execution_style_versions" naming where the operator wrote both — `execution_plan` is the doctrine-correct singular name per `MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md`)
- FKs on `deployments`: `strategy_controls_version_id`, `execution_plan_version_id`, `risk_plan_version_id`

### Doctrine Clarification — Deployment is the Binder (not StrategyVersion)

`MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md` lines 159–164 lock this:

> StrategyVersion = pure logic. Deployment = binds StrategyVersion + ControlsVersion + ExecutionPlanVersion. This allows the same StrategyVersion to run with different controls or execution plans.

So the FKs go on `deployments`, NOT on `strategy_versions`. This makes the same `StrategyVersion` reusable across different control regimes (e.g. tight cooldown vs. permissive cooldown) and different execution policies (e.g. post-fill bracket on Account-A vs. native bracket on Account-B). The Strategy stays "what setup qualifies"; the Deployment composes the executable package.

---

## 0 · The Operator-Locked Doctrine (re-stated)

> Strategy stays reusable logic. StrategyControls are upstream gates only. ExecutionPlan owns order execution behavior. SignalPlan stays neutral and quantity-free. Account/RiskResolver/Governor own sizing and approval. BrokerAdapter submits only. BrokerSync remains truth writer. No hidden runtime path. No silent naked position.

This program does **not** introduce a second runtime, does **not** introduce ExecutionIntent, and does **not** write broker truth outside BrokerSync. It only:

- Persists the missing component versions so the operator's bracket params survive save→reload.
- Adds a deterministic resolution path from `Deployment(execution_plan_version)` → `SignalPlan.{stop,targets}` → `OrderManager` child orders → `BrokerAdapter.submit_order` → `BrokerSync` reconciliation.
- Adds two execution modes (`post_fill_bracket` default, `native_alpaca_bracket` optional) inside the existing `BrokerAdapter` boundary.

---

## 1 · The Bug Today (with file:line proof)

1. **StrategyControls drop on save.** `backend/app/strategy_composer/service.py:584-628` reads `request.draft.strategy_controls` for coherence checking but never persists it. Operator-edited cooldown / session windows / horizon vanish after save→reload.
2. **ExecutionPlan drops on save.** `request.draft.execution_style` is round-tripped in the response snapshot but never written to a versioned table. The operator's "5% stop / 10% target" is decorative.
3. **Compose buildRequest hardcodes a single preset.** `frontend/src/routes/StrategyCompose.tsx` hardcodes `market_entry_market_exit` (per resume prompt's operator quote — the exact line will be located in T-2 to keep the diff minimal).
4. **SignalPlanBuilder ignores the preset.** SignalPlan ships with `entry={market}`, `stop=None`, `targets=()` for almost every preset. The neutral `SignalPlanStop` and `SignalPlanTarget` types exist (`backend/app/domain/signal_plan.py:70-86`) but are not populated.
5. **AlpacaBrokerAdapter ignores `order_class`.** `to_alpaca_order_request` at `backend/app/brokers/alpaca.py:283-299` never passes `order_class`, `take_profit`, or `stop_loss`. Native Alpaca bracket is **fully unwired** today.
6. **No post-fill protective placer.** When a market entry fills, BrokerSync writes truth but no component reads "you are now long 100 SHRT-CO at $42.50, the SignalPlan said 5% stop / 10% target, please submit those." Position lives naked.

Net effect: an operator-composed strategy with "market entry, +10% target / -5% stop" reaches Alpaca as a **naked market order**.

---

## 2 · Alpaca Native Bracket — Verified Constraints (2026-04-29 online + SDK source)

Verified against `https://docs.alpaca.markets/docs/orders-at-alpaca`, `https://docs.alpaca.markets/docs/fractional-trading`, and the alpaca-py SDK at `.venv/Lib/site-packages/alpaca/trading/{enums,requests}.py`.

| Constraint | Outcome |
|---|---|
| `OrderClass.BRACKET` exists | Yes (`alpaca/trading/enums.py:103-118`) — values: `simple`, `mleg`, `bracket`, `oco`, `oto`. |
| Native bracket structure | Entry leg + `TakeProfitRequest(limit_price)` + `StopLossRequest(stop_price, [limit_price])`. Two exit legs are conditional; on fill of one the other auto-cancels. |
| Bracket on long side | Supported. |
| Bracket on short side | Supported in principle (must be ETB; account ≥ $2,000 equity). |
| Bracket TIF | `day` or `gtc` only. Other TIF values are rejected. |
| Bracket extended hours | Not supported. |
| Bracket + fractional shares | **Not supported.** Fractional is `simple` order class only. |
| Bracket + notional value (`notional` instead of `qty`) | **Not supported.** Notional is `simple` order class only, and notional orders cannot be replaced. |
| Concurrent long+short brackets on same symbol | **Forbidden** ("all open bracket orders must be on the same side and must be entry orders"). |
| Fractional sell side | Always marked long (no fractional shorts). |

**Doctrine implication.** Native bracket is a narrow path. The runtime must inspect the resolved order and either:

- Submit native bracket when **whole-share, day/gtc, RTH-only, ETB-if-short, no-notional, single-side-per-symbol**.
- Otherwise: per operator instruction *"fail clearly if Alpaca rejects the structure"* — refuse to submit native bracket. The fallback is `post_fill_bracket`, which is the default mode anyway.

Both modes route through `BrokerAdapter.submit_order` (the only allowed broker submit boundary per `TURTLE_SHELL_GUARDRAILS.md:121-124`), and both reconcile through `BrokerSync` (the only allowed broker truth writer per `TURTLE_SHELL_GUARDRAILS.md:121-124`).

---

## 3 · Slice Plan

Each slice is independently shippable. Tests run after every slice. Each slice gets its own commit.

### T-1 · Persistence trio

**New saved entities (operator-approved):**

- `strategy_controls_versions`
  - `(id, strategy_controls_id, version, payload_json, created_at)`
  - PK on `id`; UNIQUE `(strategy_controls_id, version)`
  - Immutable rows (no updates after insert)
  - FK `strategy_controls_version_id NULL` on `strategy_versions` (existing table)
- `execution_plan_versions`
  - `(id, execution_plan_id, version, payload_json, created_at)`
  - PK on `id`; UNIQUE `(execution_plan_id, version)`
  - Immutable rows
  - Note: this table replaces the never-persisted `ExecutionStyleVersion` domain object. The doctrine-correct name is **execution_plan** per `MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md`. The Python model `ExecutionStyleVersion` is renamed to `ExecutionPlanVersion` in this slice.
  - FK `execution_plan_version_id NULL` on `deployments`
- FK `risk_plan_version_id NULL` on `deployments` (already declared in `MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md`).

**Repos / services:** `backend/app/persistence/runtime_store.py` gains:

- `save_strategy_controls_version(version: StrategyControlsVersion) -> None`
- `load_strategy_controls_version(strategy_controls_version_id: UUID) -> StrategyControlsVersion | None`
- `save_execution_plan_version(version: ExecutionPlanVersion) -> None`
- `load_execution_plan_version(execution_plan_version_id: UUID) -> ExecutionPlanVersion | None`

`StrategyComposerService.save_draft` is updated to:

1. Persist `request.draft.strategy_controls` as `StrategyControlsVersion` v1 (or v+1 if updating an existing controls id).
2. Persist `request.draft.execution_style` as `ExecutionPlanVersion` v1.
3. Set `strategy_controls_version_id` on the saved `StrategyVersion`.
4. Return both ids in the response.

**Acceptance test (must fail before slice, pass after):** save a draft with `strategy_controls.cooldown_after_loss_minutes=15` and `execution_style.preset.kind="bracket_stop_target"` with `stop_pct=5, target_pct=10`. Reload by id. Both values survive.

### T-2 · Compose / API wiring

- `frontend/src/components/strategy_builder/editor/sections/StopTargetExecutionSection.tsx` (existing) gains:
  - Stop-pct input
  - Target-pct input
  - `execution_mode` select: `post_fill_bracket` (default) | `native_alpaca_bracket`
- `frontend/src/routes/StrategyCompose.tsx::buildRequest()` stops hardcoding `market_entry_market_exit`; instead reads the section's preset spec.
- Backend `POST /api/v1/strategies/draft/save` round-trips the new `execution_mode` field on `ExecutionPlanVersion`.
- `frontend/src/api/schemas/strategyComposer.ts` adds `execution_mode` to the zod schema.

**Acceptance test:** in compose, type 10 / 5 → save → close → reopen. Both values still 10 / 5; `execution_mode=post_fill_bracket` selected.

### T-3 · SignalPlan enrichment

- `backend/app/signal_planner/builder.py` (existing builder) gains a deterministic resolver:
  1. Look up the active deployment's `execution_plan_version_id`.
  2. Load the `ExecutionPlanVersion`.
  3. From the preset spec (`BracketStopTargetPreset` etc.), populate:
     - `SignalPlan.entry` (order_type, limit_price, time_in_force_preference)
     - `SignalPlan.stop` (`type`, `stop_price` *only* if entry is a limit at known price; otherwise `rule="post_fill_pct"` with stop_pct stored in `stop.rule`)
     - `SignalPlan.targets` (with label, action=`reduce`/`close`, `quantity_pct=100` for stop_target preset, `price` *only* if entry is a limit; otherwise resolved post-fill in T-4)
- Long and short are both populated symmetrically — `SignalPlan.side` is already set upstream; the builder just clones the bracket params for whichever side.
- **No quantity** — SignalPlan stays neutral. Doctrine guard already in `SignalPlan.reject_account_execution_fields` (`signal_plan.py:127-149`).

**Acceptance test:** with the persisted ExecutionPlan from T-1, build a SignalPlan for symbol `AAPL` side=long. SignalPlan has `stop.rule="post_fill_pct:5"` and `targets[0].label="t1"`, `targets[0].quantity_pct=100`, `targets[0].rule="post_fill_pct:10"`. Short-side SignalPlan has the same payload, side flipped.

### T-4 · Order execution (the main feature)

Two execution modes in the `OrderManager` + `AlpacaBrokerAdapter`:

#### Mode A — `post_fill_bracket` (default)

1. RiskResolver/Governor approve the SignalPlan; `AccountSignalPlanEvaluation` carries resolved quantity.
2. `OrderManager.submit_entry_from_signal_plan(...)` builds an `InternalOrder` for the entry leg only. `BrokerAdapter.submit_order` ships it.
3. `BrokerSync` ingests trade-update stream events. When the entry order reaches `FILLED` (or partial-fill, see below), `BrokerSync` emits a domain event `EntryFilled(order_id, signal_plan_id, account_id, fill_price, fill_qty)`.
4. A new component **ProtectiveOrderPlacer** (in `backend/app/orders/protective_placer.py`) subscribes to that event:
   - Reads the SignalPlan's `stop.rule` and `targets[*].rule`.
   - Computes `stop_price = fill_price * (1 - stop_pct/100)` for long, `(1 + stop_pct/100)` for short.
   - Computes `target_price = fill_price * (1 + target_pct/100)` for long, `(1 - target_pct/100)` for short.
   - Builds two child `InternalOrder`s with `parent_order_id=entry.order_id`, `order_class="oco"` (the protective pair is mutually-exclusive — first to fill cancels the other).
   - Submits via `BrokerAdapter.submit_order`. Alpaca: pass an OCO bracket on the exit pair (`OrderClass.OCO`).
5. **Idempotency**: ProtectiveOrderPlacer keys off `(signal_plan_id, fill_price)`. Re-emit of the same fill event does not create duplicate child orders. A protective-placement record is persisted (`protective_placements` row) before submit; if the row exists the second emission is a no-op.
6. **Partial fills**: Each `EntryFilled` event with cumulative `filled_qty` > the last placement's `covered_qty` triggers an *incremental* protective placement for the new uncovered shares only. Total protective qty across all placements equals total filled qty.

#### Mode B — `native_alpaca_bracket` (optional)

Pre-flight check (in OrderManager before submit):

- Resolved order is whole-share (no fractional, no notional).
- TIF is DAY or GTC.
- Not extended hours.
- If short: account is configured for shorting, symbol is ETB-classified.
- No concurrent open bracket on the same symbol on this account.

If pre-flight passes:

1. Build entry `InternalOrder` with `order_class="bracket"`. Stop/target prices come from the SignalPlan; for market entries we approximate with a reference price (last-trade) — the operator must explicitly set entry as a *limit* for native bracket because Alpaca needs concrete limit/stop prices on the child legs at submit time.
2. `AlpacaBrokerAdapter.to_alpaca_order_request` checks `order.order_class == "bracket"`, attaches `order_class=BRACKET`, `take_profit=TakeProfitRequest(limit_price=target_price)`, `stop_loss=StopLossRequest(stop_price=stop_price)`.
3. Alpaca returns parent + 2 child broker_order_ids. BrokerSync ingests all three trade-update streams and writes truth normally.

If pre-flight fails: per operator *"fail clearly if Alpaca rejects the structure"* — `OrderManager` raises `BracketModeUnsupported` with a structured reason. The operator sees an Operations-Center reject card. The system does not silently degrade to `post_fill_bracket` — that would be a hidden runtime path.

#### Boundary discipline

- `OrderManager.submit_entry_from_signal_plan(...)` is the **only** new entry point. No second runtime root. No order flow that bypasses Governor.
- All child orders carry `parent_order_id` lineage. All carry `signal_plan_id`, `account_id`, `deployment_id`, `strategy_id`, `position_lineage_id` per `TURTLE_SHELL_GUARDRAILS.md:104-110`.
- `BrokerSync` is the only broker truth writer. ProtectiveOrderPlacer subscribes to BrokerSync events; it does not poll Alpaca directly.

### T-5 · Position protection verification

- `Operations` page gains a "Protection status" column on the Open Positions card: `protected` (stop+target placed), `pending_protection` (entry filled, protective not yet ack'd), `naked` (entry filled, protective failed — alarm).
- An invariant test: after entry fill, every signal-plan-originated position must have at least one open child stop within N seconds (configurable; default 30s) or surface a `protection_failed_after_fill` alarm.
- Reject visibility: when Governor rejects the entry, the operator sees the rejection card on Operations with `rule_id`, `account_missing_risk_plan_for_horizon` or whichever rule fired.

### T-6 · TOCTOU hardening

- `RuntimeStore` opens a single `with self._connection() as conn` block per evaluation that does the composite read of:
  - `deployment(execution_plan_version_id, risk_plan_version_id, risk_horizon)`
  - `account_risk_plan_map[(account_id, horizon)]`
  - `risk_plan_version` row
  - `account_risk_config` row
- SQLite is set to `journal_mode=WAL` at composition root (one-time PRAGMA on connection-pool init). All composite reads use a single shared connection within the orchestrator evaluation step.
- Concurrent-PUT test: spawn a thread that PUTs `/risk-plan-map` while the orchestrator is in the middle of a Governor evaluation. The orchestrator must either see the *old* coherent snapshot OR the *new* coherent snapshot, never a mix.
- If the runtime detects a row-version mismatch mid-evaluation, it fails closed (no order placed) with `rule_id="risk_plan_map_concurrent_modification"`.

### T-7 · Daily risk state aggregator + cooldown

- New `backend/app/runtime/daily_account_state.py`:
  - `DailyAccountState` snapshot: `(account_id, market_day, realized_pnl, unrealized_pnl_at_eod, drawdown_pct, last_loss_at, total_loss_today)`.
  - Source of truth: BrokerSync fills + position truth (no shadow ledger).
  - Reset boundary: market day rollover (first trade event after 09:30 ET, or explicit operator reset).
  - Restart-safe persistence: `daily_account_states` table, primary key `(account_id, market_day)`. Reloaded on orchestrator boot.
- `PortfolioGovernor.evaluate()` gains two new checks (after numeric-limit checks):
  - `daily_loss_pct_exceeded`: `realized_pnl_pct <= -active_policy.max_daily_loss_pct`
  - `drawdown_pct_exceeded`: `drawdown_pct >= active_policy.max_drawdown_pct`
- Cooldown: a third check, `cooldown_after_loss_active`: if `(now - last_loss_at)` < `active_policy.cooldown_after_loss_minutes`, reject *open* signal plans only. Protective exits (CLOSE/STOP/TARGET intent) bypass — same rule as guardrails §rule-1.
- Operations page: a new "Daily Risk State" card per Account showing realized P&L, drawdown, cooldown remaining. Updates from the same store the Governor reads.

---

## 4 · The Wiggum 3-Pass Loop

Per operator: each slice + the program as a whole runs three passes.

- **Pass 1**: implement baseline. Tests pass.
- **Pass 2**: adversarial hardening. I deliberately attack each slice for race conditions, lineage gaps, doctrine drift, dead branches, missing pre-flight, missing rollback, idempotency holes. Every BUG/RISK fixed in-slice.
- **Pass 3**: simplify, verify doctrine, remove overengineering. Re-read the program against `TURTLE_SHELL_GUARDRAILS.md`. Delete anything that doesn't strengthen the spine. Re-confirm test counts.

### Critical Agents (per operator — invoked across the loop)

- **Architecture critic** at end of T-1, T-3, T-4 (doctrine-heavy slices). Independent review of bounded-context ownership, runtime composition root, broker boundary, lineage requirements.
- **UX/UI critic** at end of T-2 and T-5 (operator-visible slices). Compose Page 2 bracket inputs, Operations protection status card, friendly rejection text.
- **Adversarial critic** at every slice closeout — race conditions, lineage gaps, doctrine drift, dead branches, missing pre-flight, idempotency holes.
- **Helper/parallel agents** for non-overlapping work blocks (e.g., T-2 frontend while T-3 backend; T-6 + T-7 in parallel since they touch different doctrine layers).
- **Fast-is-smooth-is-accurate** discipline: don't sprint into the next slice without each tier of tests green.

When a critical agent surfaces a finding, I triage it like Slice A/B: BUG/RISK = fix in-slice; NIT = ledger as followup unless trivial.

---

## 5 · Test Acceptance Matrix

Per operator. All required:

| # | Scenario | Mode | Slice |
|---|---|---|---|
| 1 | Long market + 5% stop + 10% target, post-fill | `post_fill_bracket` | T-4 |
| 2 | Short market + 5% stop + 10% target, post-fill | `post_fill_bracket` | T-4 |
| 3 | Long native Alpaca bracket | `native_alpaca_bracket` | T-4 |
| 4 | Short native Alpaca bracket if supported, else explicit unsupported result | `native_alpaca_bracket` | T-4 |
| 5 | Partial fill idempotency | `post_fill_bracket` | T-4 |
| 6 | Reload persistence | both | T-1+T-2 |
| 7 | Governor rejection blocks orders | both | T-7 |
| 8 | BrokerSync lineage preserved | both | T-4+T-5 |

---

## 6 · Per-Pass Log

A timestamped log file per pass: `docs/agent_logs/YYYY-MM-DD_HH-mm-ss_bracket_execution.md`. The first log file (`2026-04-29_21-52-19_bracket_execution.md`) is created at slice start. Each entry includes:

- pass number
- timestamp
- files changed
- decisions made
- blockers and 5 Whys
- tests run
- test results
- remaining gaps
- next action

---

## 7 · Decision Log

| # | Decision | Reasoning |
|---|---|---|
| D1 | Default mode = `post_fill_bracket` | Operator directive. Symmetric for shorts, handles partial fills cleanly, doesn't require operator to commit to whole-share day-only RTH-only orders. |
| D2 | Native = `native_alpaca_bracket`, optional | Operator directive. Cleaner for "I want one click that places a 3-leg bracket on a long-side limit entry on AAPL right now and lets Alpaca manage it" — but the constraint matrix is narrow (whole-share, day/gtc, RTH, etc). |
| D3 | Doctrine name is `ExecutionPlan`; Python identifier `ExecutionStyleVersion` stays for now | `MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md` uses `ExecutionPlan` for the **persisted entity** and the **table name**. The internal Python class identifier `ExecutionStyleVersion` has 94 import sites across backend + tests; renaming the identifier is a clean follow-up slice with its own contract. T-1 keeps the class identifier `ExecutionStyleVersion`, names the **table** `execution_plan_versions`, names the **Deployment FK** `execution_plan_version_id`, and adds a doctrine-aligned class docstring noting the rename plan. The `execution_mode` field is the new operator-visible feature added to this class. Production-grade still holds — there are no parallel paths or scaffolding. |
| D4 | OCO is the right Alpaca order_class for the *exit pair* in `post_fill_bracket` | The two protective legs are mutually exclusive — first to fill cancels the other. That's exactly OCO. Native-bracket BRACKET is a 3-leg single submit; the post-fill flow already submitted leg 1, so legs 2+3 are an OCO pair, not a fresh bracket. |
| D5 | ProtectiveOrderPlacer is a subscriber, not a runtime entry point | TURTLE_SHELL_GUARDRAILS.md §47-69 bans new runtime roots. ProtectiveOrderPlacer is wired into the existing `BrokerSync.on_order_update` callback chain via the orchestrator composition root. |
| D6 | Idempotency key is `(signal_plan_id, covered_qty_breakpoint)` | Allows re-emission of the same fill event to no-op, while still allowing a *new* fill (more shares filled) to trigger an incremental protective placement. |
| D7 | TOCTOU fix uses single `with conn` block + WAL, not optimistic version stamps | WAL gives reader-writer concurrency without blocking. Single connection per evaluation gives transactional consistency. Optimistic version stamps are a heavier refactor for the same outcome. |
| D8 | Daily-state source of truth is BrokerSync fills, not a shadow ledger | TURTLE_SHELL_GUARDRAILS.md §39: BrokerSync is the only broker-truth writer. The daily-state aggregator is a *projection* of BrokerSync events, persisted for restart-safety, never a write source. |
| D9 | Alpaca capabilities flag `supports_brackets` defaults to `false` until T-4 lands the wiring | Avoids declaring a capability we haven't implemented. T-4 flips it to `true`. |
| D10 | Production-grade only | Per memory entry `feedback_production_grade_only`. No TODO comments, no half-implementations, no scaffolding code. Each slice ships its final shape. |

---

## 8 · Lease Plan

Backend leases (filed at slice start):

- `backend/app/persistence/`
- `backend/app/strategy_composer/`
- `backend/app/domain/{execution_style,signal_plan,strategy_controls}.py`
- `backend/app/signal_planner/`
- `backend/app/orders/`
- `backend/app/brokers/{adapter,alpaca,sync}.py`
- `backend/app/runtime/`
- `backend/app/governor/`
- `backend/app/pipeline/orchestrator.py`
- `backend/app/api/routes/`

Frontend leases (filed at T-2):

- `frontend/src/routes/StrategyCompose.tsx`
- `frontend/src/components/strategy_builder/`
- `frontend/src/api/schemas/strategyComposer.ts`
- `frontend/src/routes/Operations.tsx`

TTL 2h max per `COORDINATION/PROTOCOL.md`.

---

## 9 · Rollback Posture

If any slice's tests regress beyond fixable, revert that slice's commit only. Each slice is a single commit with a descriptive title. The slice boundaries are designed so reverting T-N does not break T-(N+1)'s prerequisites — earlier slices are net-additive.

The exception: T-3 depends on T-1's persisted entities. If T-1 is reverted, T-3 must also be reverted.

---

## 10 · "Production-Ready" Definition

Per operator: *"Do not claim production-ready until T-6 and T-7 are either complete or explicitly marked as blocking gaps."*

This program reaches production-ready when:

- T-1 through T-7 all shipped and tested.
- All 8 acceptance scenarios in §5 pass.
- Both Wiggum Pass 2 and Pass 3 closed with zero remaining BUG-severity findings.
- Backend pytest ≥ 1476 passing (current baseline) plus the new per-slice tests.
- Frontend vitest ≥ 379 passing plus new tests.
- `tsc --noEmit` clean.

Any slice marked as a blocking gap is called out explicitly here, with a one-paragraph rationale and a re-engagement plan.
