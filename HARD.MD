ULTIMATE TRADER FACT-FINDING SYNTHESIS
Coordinator synthesis — 2026-05-01. Sources: Alpaca Compliance, Backend Spine, UX/Usability, Frontend Engineer specialist sweeps. No code changed.

1. Executive Summary
Ultimate Trader's canonical spine is wired and working through Slice 10. SignalPlan → AccountEvaluation → RiskResolver → Governor → OrderManager → BrokerAdapter → BrokerSync runs end-to-end with deterministic client_order_id, multi-Account fan-out, idempotent restart, and protective-exit fast-path. The frontend SPA has all 9 nav routes built (no Placeholders on the critical path), strong loading/empty/error patterns, and Zod-typed API schemas. Doctrine naming is clean — no Program, Services Center, or Paper Runtime leakage.

The gaps are concentrated in two zones. (a) Broker correctness: Slice 11 (Account Trade Sync reconciliation scheduler) is queued, native bracket/OCO/OTO submission is preflight-blocked, several Alpaca preflight rules are missing or wrong (stop-distance threshold, fractional+short, extended-hours+GTC, OTO replace, qty/notional conflict), and manual broker positions are silently invisible to Governor concentration gates. (b) Operator trust at action-time: there is no toast system, dangerous actions on Account/Operations pages lack confirmation or post-action evidence, ChartLab has no stream-disconnected state, and 11 of ~17 explainer slugs render an empty drawer.

Nothing should be shipped to live trading until the four P0s in §2 are closed. P1s (~10 items) are the right ladder once P0s land. P2s are mostly polish and can be batched.

2. P0 — Trading Safety Findings (must fix before live)
#	Finding	Evidence	Owner
P0-1	Account Trade Sync REST reconciliation has no scheduler. Stream-only freshness can hide stale positions/orders/account; Governor's is_stale reflects WS health, not REST truth. (Slice 11 queued.)	backend/app/brokers/sync.py has sync_open_orders/positions/account/reconcile() but no periodic caller; governor/service.py:68 gates only on broker_sync.is_stale	Backend Spine
P0-2	Manual / unknown-origin broker positions bypass Governor concentration gates. sync_positions() reads them but GovernorRequest.portfolio.positions carries only opted-in lineage positions. Playbook §15 forbids silent "protection."	backend/app/brokers/sync.py:161 + backend/app/governor/service.py (no manual-position path); no unmanaged_broker_position classification anywhere	Backend Spine + Alpaca
P0-3	Stop-price $0.01 threshold not validated; fractional+short not rejected. Both will be rejected by Alpaca after a round trip; fractional shorts are silently flipped long.	backend/app/brokers/preflight.py:196-203 (only TIF=DAY check), no stop-distance check anywhere; playbook §7 + §9	Alpaca
P0-4	Native bracket/OCO/OTO unconditionally rejected at preflight even when shape is valid. Forces every multi-leg lifecycle through internal-leg decomposition; partial fills + exit pairing become our problem instead of Alpaca's.	backend/app/brokers/preflight.py:245-250 blanket UNSUPPORTED_ORDER_CLASS; alpaca.py:348-392 has shape validators that are dead code	Alpaca
P0-1 and P0-2 are the most consequential — they let the system silently drift from broker truth. P0-3 is one preflight pass. P0-4 is opt-in: ship internal-leg decomposition first, then unblock native shapes.

3. P1 — Runtime Visibility & Correctness Findings
#	Finding	Evidence
P1-1	Extended-hours preflight rejects valid GTC limits and accepts invalid IOC/FOK/OPG/CLS. Per playbook §10 EH supports limit + (day OR gtc); current code only allows DAY and never rejects EH+IOC.	preflight.py:156
P1-2	OTO replacement and notional replacement not blocked at preflight. Both are unsupported by Alpaca; today they leak to the adapter.	preflight.py REPLACE path; alpaca.py:215-224
P1-3	Trailing stop fields missing on InternalOrder. No trail_price / trail_percent; BrokerOrderClass.TRAILING_STOP enum exists but is unreachable.	backend/app/orders/models.py; brokers/capabilities.py
P1-4	Short-side buying-power estimate not implemented (max(limit, 1.03·ask)·qty per playbook §11). Governor approves shorts that Alpaca then rejects.	preflight.py market-rule path (no ask input)
P1-5	Account Trade Sync startup not orchestrated. No code at app boot iterates validated Alpaca Accounts and opens one stream per Account. Combined with the orphan-guard memory note (no --reload allowed), this is fragile.	backend/app/brokers/stream.py:33-73; no caller in main.py / runtime entrypoint
P1-6	Strategy attachment is not null-guarded. A loaded Deployment with components.strategy=None will crash at first bar.	pipeline/orchestrator.py:445 accesses self._components.strategy without check
P1-7	Multi-Account density (~10) untested. Per-Account fan-out is wired (Slice 9), but no e2e test with 10 subscribed Accounts × shared market-data hub × per-Account dispatcher. The user's memory pins this as a hard target.	pipeline/orchestrator.py:540 fan-out loop; tests use 1–2 Accounts
P1-8	No toast / notification system in the SPA. Pause/Resume/Flatten/Emergency-Exit/Bulk-Delete complete silently. ManualOrderDrawer is the only place with post-action evidence (inline Banner).	frontend/src/routes/Accounts.tsx, Operations.tsx, Watchlists.tsx
P1-9	Dangerous actions lack uniform confirmation. Operations global-kill is a plain Button; StrategiesV4 delete is a plain Button; Providers delete uses DangerConfirm; Deployments uses HoldToArmConfirm. The strongest pattern (typed account name + reason) lives only in ManualOrderDrawer.	Operations.tsx:60, StrategiesV4.tsx:181-187, Providers.tsx, Deployments.tsx
P1-10	Charts have no disconnect/stale state. ChartLab PriceChart and StrategyPreviewChart render blank on WS drop or empty data. SimLab same.	frontend/src/routes/ChartLab.tsx:70-80; components/charts/SimLabReplayChart.tsx
P1-11	Test coverage on destructive flows ~0. 16 of 71 route/drawer files have tests; pause/resume/stop/flatten/emergency-exit/bulk-delete confirm flows are untested.	frontend/src/routes/*.test.tsx count
4. P2 — UX & Frontend Polish Findings
Explainer drawer registered for only 6 of ~17 pages — clicking Explain on Watchlists/Deployments/RiskPlans/Screeners/ChartLab/SimLab/Backtests/Optimization/WalkForward/ExecutionPlans/StrategyControls renders empty content (frontend/src/routes/explainerContent.ts).
Error taxonomy partial. BrokerOrderResult lacks playbook §17's structured family/severity/source/operator_advisory/raw_broker_code/raw_broker_message. Errors leak to logs as raw exceptions.
client_order_id mapping not traced/audited. BrokerSync.apply_result validates the match but doesn't log it; mismatch detection works but is hard to root-cause. (backend/app/control_plane/client_order_id.py:41-63 uses sigplan-{acct8}-{plan8}-{intent}-{hash10} — note: not the literal ut:… form in the playbook §2; functionally equivalent but worth documenting.)
Live mode not gated at adapter init — AlpacaBrokerCapabilities.supports_broker_live=False but no __init__ guard raises if mode==BROKER_LIVE is passed.
RiskResolver detail not exposed in Operations API — embedded inside AccountSignalPlanEvaluation.risk_resolver_result only.
Logical-exit "3 closed bars" not verified — wiring exists end-to-end, but no test asserts the rule fires on closed bars only, not in-progress.
Account card has no manual "Refresh Sync" action.
api/client.ts:57-65 detailFrom(body) — missing null-guard before "detail" in body.
TextField missing aria-invalid / aria-describedby.
WS hook doesn't expose sequence-gap detection.
ResearchEvidencePage appears to be dead code (no route mounts it).
Components route is a PlaceholderPage — decide whether to wire or delete from the nav.
5. Repair Sequence
The order is chosen so each step lands on a green test suite and unlocks the next.

Step 1 — Slice 11 reconciliation scheduler (P0-1). Adaptive per-Account scheduler around the existing registry: REST reconcile on startup, on reconnect, on event-gap; periodic 30–60s orders / 60–120s positions+account on healthy stream; faster cadence on degraded; jitter + per-Account backoff sized for 10 Accounts. Surface stream freshness separately from REST freshness in Operations. Already specified in NEXT_IMPLEMENTATION_SEQUENCE.md §Slice 11 — execute as written.

Step 2 — Unmanaged-position visibility & gating (P0-2). Add unmanaged_broker_position: bool to BrokerPositionSnapshot; classify any broker position with no position_lineage_id as unmanaged in BrokerSync._enrich_position_snapshot_with_lineage. Surface in Operations. Include unmanaged positions in GovernorRequest.portfolio.positions for concentration evaluation (fail-closed). Adoption flow stays explicit and gated.

Step 3 — Alpaca preflight hardening (P0-3, P1-1, P1-2, P1-4). One PR adding: stop-distance ≥ $0.01 vs base price; fractional+short rejection; EH allows DAY|GTC, rejects IOC/FOK/OPG/CLS and non-limit; OTO replace rejection; qty XOR notional explicit check; notional replace rejection; short-side BP estimate plumbed through MarketRulePreflightRequest (needs ask_price).

Step 4 — Native bracket/OCO/OTO submission (P0-4). Remove blanket UNSUPPORTED_ORDER_CLASS block; route shape-validated requests through the existing _validate_native_bracket_preflight / _validate_native_oco_preflight paths in alpaca.py. Multi-target (>1 TP) still decomposes into internal legs sharing one SignalPlan/Position lineage. BrokerSync must already reconcile every child leg (verify with new tests).

Step 5 — Trailing stop support (P1-3). Add trail_price / trail_percent to InternalOrder; preflight: exactly one set, TIF ∈ {day, gtc}, not used as bracket stop_loss leg; advisory text marks "no extended-hours protection."

Step 6 — Account Trade Sync startup orchestration (P1-5). App-boot loop: query validated Alpaca Accounts → instantiate BrokerSyncService per Account → wire AlpacaAccountStreamAdapter.subscribe() → mark stale until first event → log per-Account startup result. Keeps the no---reload rule from memory.

Step 7 — Strategy null-guard + 10-Account density test (P1-6, P1-7). Add explicit guard in pipeline orchestrator + a load test (10 Accounts × 5 symbols × 1m bars) that asserts no dropped bars and bounded per-stage latency.

Step 8 — Frontend trust pass (P1-8, P1-9, P1-10, P1-11). Add ToastProvider + useToast() (Radix Toast). Standardize on HoldToArmConfirm for everything destructive (StrategiesV4 delete, Watchlists bulk delete, Operations global kill); upgrade Operations global kill to typed-confirm + reason. Wrap all chart containers with explicit Loading/Empty/Stale/Error states. Add vitest cases for every destructive confirm flow and at least one happy-path mutation per page.

Step 9 — Explainers + minor frontend (P2 batch). Backfill explainerContent.ts for the 11 missing slugs. Account "Refresh Sync" button. aria-invalid on TextField. Null-guard detailFrom. Decide Components and ResearchEvidencePage (wire or delete).

Step 10 — Error taxonomy + live-mode init guard (P2-tail). Structured BrokerErrorEvent per playbook §17; raise on BROKER_LIVE until explicitly enabled; expose RiskResolver detail in Operations API.

6. Test Plan
Every step above ships with tests. The non-negotiables:

P0-1: stream-only freshness ≠ REST freshness — kill REST while stream is alive, assert Governor blocks new opens; reconnect path triggers REST reconcile; periodic cadence within bounds.
P0-2: broker-only position is classified unmanaged_broker_position; included in concentration eval; protective order requires explicit adoption.
P0-3 / P1-x preflight: one parametrized table per rule (stop $0.005 reject / $0.01 accept; fractional+short reject; EH+limit+gtc accept; EH+limit+ioc reject; EH+market reject; OTO replace reject; qty+notional reject; short-BP estimate insufficient reject).
P0-4 native shapes: bracket buy with TP>stop, day/gtc, no EH, whole-share — accepted; multi-TP decomposed into shared-lineage legs; child-leg fills reconciled by BrokerSync to the same Position.
P1-5: boot opens one trade sync per validated Alpaca Account; pause does not close it; orphan-guard still works without --reload.
P1-6: Deployment with strategy=None fails fast at start, not at first bar.
P1-7: 10 Accounts × 5 symbols load test passes p99 latency target and drops zero bars.
P1-8/9/10: vitest cases — DangerConfirm requires name match + reason ≥ 3 chars; HoldToArmConfirm requires hold timer; chart container shows Stale state on WS drop; toast emitted on every successful mutation in Accounts/Operations/Watchlists.
Logical-exit closed-bars: 2 closed + 1 open → no SignalPlan; 3 closed → emitted; in-progress 4th does not re-emit.
Backend unit baseline today is 1103 passed (NEXT_IMPLEMENTATION_SEQUENCE.md). The repair sequence should preserve that count plus net-add ~80–120 tests.

7. Open Questions
Adoption policy for unmanaged broker positions — fail-closed (block opens until adopted/dismissed) or fail-open with visible warning? Playbook §15 implies fail-closed; confirm before P0-2 lands.
Slice 11 cadence parameters — playbook §16 suggests 30–60s orders / 60–120s positions+account; final values should be configurable per Account or environment.
Live-mode enablement — what is the gating mechanism (env var, per-Account flag, operator confirmation)? Affects P2-tail.
Native bracket vs internal-leg decomposition — when both are valid (single TP + stop, day/gtc, no EH), do we prefer native bracket (broker handles OCO logic) or always decompose (uniform code path)? Trade-off: latency + reliability vs single reconciliation surface.
Logical-exit "closed bar" semantics — already implied by "3 one-minute bars" doctrine, but no test pins it. Should closed_only=True be a Strategy-level setting, or hardcoded for logical_exit?
Multi-Account scale beyond 10 — is 10 a hard ceiling or a target with headroom? Affects scheduler jitter and dispatcher coordination design.
Components and ResearchEvidencePage routes — wire or delete?
End of synthesis. ~3.5 pages. Specialists' full reports retained in conversation history if you want to drill into any specific finding.

Want me to /schedule a recurring agent to re-run this fact-finding sweep monthly, or open Step 1 (Slice 11 scheduler) as the first implementation slice?


Left work, as I see it:

Monday live-market verification
Confirm the modern spine with a fresh fill: Deployment -> SignalPlan -> Account evaluation -> Order -> Alpaca -> BrokerSync -> Position -> protective OCO.

Protective order restart recovery
Current old TQQQ case cannot be protected because the stale SignalPlan lacks ATR value. The code now refuses to guess, correctly. Need verify fresh/recomputed ATR warmup during live bars.

Logical exits
Recheck the bars-since-entry exit rule during market hours. It should exit after the configured bar count, but restart lineage/entry timestamp gaps can still block old positions.

Alpaca OCO audit edge
Need improve/verify nested OCO child confirmation after downtime or partial fills, especially broker-generated child IDs.

Clean-up branch work
You’re already on feature/cleanup-modern-core. Good next branch tasks: remove remaining non-core legacy Program shims where safe, tighten docs/KB, and prune old frontend Strategy Builder leftovers now replaced by v4.

UI/operator polish
Frontend is running, but the new v4 surfaces should get a quick browser walk-through: Deployments, Strategy V4 Compose, Operations, Execution Plans, Strategy Controls.