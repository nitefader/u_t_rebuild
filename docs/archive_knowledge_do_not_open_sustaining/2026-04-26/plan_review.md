# Architectural Review — Ultimate Trading OS Rebuild

**Date:** 2026-04-24
**Posture:** Critique + amend the Master Blueprint
**Method:** Four parallel agent lenses (Architecture / UX-Time-to-Market / Operational Safety / Strategy Authoring Quality), synthesized here

---

## Executive Summary

The blueprint is structurally sound and the Operations Center spine is honest. The four-lens review surfaced **42 distinct recommendations**, of which **18 are HIGH severity** and **2 represent live policy violations** in the current backend (a new `app/services/` bucket and a `ServiceMode.PAPER/LIVE` enum that re-introduces banned terms the Mode Naming Contract explicitly forbids).

The dominant pattern across lenses is the same: **the v2 mockup got the vocabulary right but underdelivers on the *result surfaces* the spec requires.** Kill modals warn but never render the structured cancellation result. The promotion gate has no `unknown` state, so missing inputs render as green. Unknown-intent broker orders are flagged but offer no triage path. The AI Composer's reuse-first patterns exist on the Composer screen and nowhere else — Components, Universes, and Programs editors still require typed syntax.

Five amendments to the blueprint, six new UI panels, and a context-sensitive (Tier A/B/C) promotion gate are recommended. The companion file [mockup_review.html](mockup_review.html) applies every UI-surface recommendation.

---

## Authority Order Used

1. [docs/system_rebuild_outputs/08_synthesis_blueprint_output.md](docs/system_rebuild_outputs/08_synthesis_blueprint_output.md) — Master Blueprint
2. [docs/system_rebuild_outputs/MODE_NAMING_CONTRACT.md](docs/system_rebuild_outputs/MODE_NAMING_CONTRACT.md) — banned terms
3. [docs/Canonical_Architecture.md](docs/Canonical_Architecture.md), [docs/Control_Plane_Spec.md](docs/Control_Plane_Spec.md), [docs/Feature_Engine_Spec.md](docs/Feature_Engine_Spec.md), [docs/Feature_Vocabulary_Catalog.md](docs/Feature_Vocabulary_Catalog.md), [docs/Services_Architecture_Market_Data_AI.md](docs/Services_Architecture_Market_Data_AI.md)
4. [ui_mockup_v2.html](ui_mockup_v2.html) — UI baseline
5. [backend/app/](backend/app/) — current implementation
6. [docs/User_Journey_Validations.md](docs/User_Journey_Validations.md) — describes outcomes, not architecture

---

## A. Architecture & Domain Integrity (5 HIGH, 5 MED, 3 LOW)

| # | Sev | Title | Evidence | Proposed change | Blueprint § | UI surface |
|---|---|---|---|---|---|---|
| A1 | HIGH | `ServiceMode.PAPER/LIVE` standalone enum | [backend/app/services/service_resolver.py:21-22](backend/app/services/service_resolver.py); used as user-facing `mode` field | Replace with `TradingMode.BROKER_PAPER/LIVE` from [backend/app/domain/trading_mode.py](backend/app/domain/trading_mode.py). Remove `mode` from `MarketDataServiceRecord` entirely (Yahoo has no concept of paper/live). | §15 Mode Naming Contract; §10 banned terms | Services Center cards |
| A2 | HIGH | Generic `app/services/` bucket reintroduced | [backend/app/services/__init__.py](backend/app/services/__init__.py) — directly forbidden by Blueprint §15 | Move provider/credential mgmt into canonical buckets: `market_data/`, `ai/`, `broker_accounts/`. Delete `app/services/`. Resolver can live as `market_data/resolver.py`. | §15, §10 | Delete `frontend/services.html`; absorb into Providers + AI Builder |
| A3 | HIGH | AI service surface owned by generic Services bucket | [backend/app/services/models.py:93](backend/app/services/models.py); `/services/ai` API | Move `AIServiceRecord` to `app/ai/providers.py`; rename API to `/ai/providers` | §10, §15 | AI Builder page absorbs AI provider config |
| A4 | MED | `ProgramVersion` has draft/frozen but no immutability lock or content hash | [backend/app/domain/program.py:24-66](backend/app/domain/program.py) — Pydantic mutable, no hash | Add `model_validator` preventing mutation when `status==FROZEN`. Compute `composition_hash` over the 5 component-version IDs at freeze; store on ProgramVersion. Deployments reference `(program_version_id, composition_hash)`; mismatch on reload is a hard block (tamper-evident). | §3, §15, §13 | Programs list (frozen badge surfaces hash); Deployments detail |
| A5 | MED | OrderManager bypasses BrokerSync for position reads | [backend/app/orders/manager.py:222-226](backend/app/orders/manager.py) — direct `broker_adapter.get_positions()` | Route `_has_backing_position` through `BrokerSync.last_positions()` cache | §15 BrokerSync as broker-truth writer | None directly |
| A6 | MED | Account/Deployment Pause state lives on `GovernorPolicy` not ControlPlane | [backend/app/governor/service.py:36-53](backend/app/governor/service.py) reads `paused_account_ids` from policy | Remove pause/kill fields from `GovernorPolicy`. `PortfolioGovernor.evaluate` calls `ControlPlane.can_open_new_position()` and short-circuits. | §2 layer separation, §15 | Operations Center + Governor must read same source |
| A7 | MED | `client_order_id` format diverges from Blueprint canonical | [backend/app/control_plane/client_order_id.py](backend/app/control_plane/client_order_id.py) emits `{prog}-{deploy8}-{intent}-{rand8}` (Control_Plane_Spec format), not Blueprint's `utos-{acct8}-{dep8}-{prog8}-{intent}-{seq}` | Reconcile to one format (recommend Blueprint §8: includes acct8 + utos prefix + sequence). Update generator + parser; keep legacy parser tolerant during transition. | §8, §13 stop-ship test | Operations Center order detail rendering |
| A8 | MED | Mockup nav statically pins `data-mode="broker-paper"` for Operate group | [ui_mockup_v2.html:425-427](ui_mockup_v2.html) | Drop static pin; mode chip per row already correct. Real impl derives from active deployment's TradingMode. | Mode Naming Contract user-facing labels | Sidebar nav |
| A9 | MED | Mockup uses bare `paper` / `live` cells in tables | [ui_mockup_v2.html:1492,1495,1254](ui_mockup_v2.html) | Render as canonical `mode-label` chips. Replace stream "live" badge with "streaming" or "connected" to disambiguate from BROKER_LIVE. | Mode Naming Contract Banned Terms | Broker Accounts page, Operations Center stream chip |
| A10 | LOW | "Live Monitoring" prose still present | [ui_mockup_v2.html:1245,2259](ui_mockup_v2.html) | Strike both. Replace with "Authoritative runtime state" and "Deployments & Operations." | §10 banned names | Operations Center page-sub, Journey Hub row |
| A11 | LOW | Old reference docs describe `LiveMonitor` POST routes as P0 | [docs/User_Journey_Validations.md:241-244](docs/User_Journey_Validations.md) | Tag rows with `do_not_implement` pointing to Operations Center routes | §14, §10 | None |
| A12 | LOW | `MarketDataServiceConfig.mode` overloads two concepts | [backend/app/services/service_resolver.py:88-100](backend/app/services/service_resolver.py) | Split: market-data services have `provider` only; broker creds carry `TradingMode` | §1 separation of governor / broker | Services Center forms |
| A13 | MED | No banned-pattern lint pre-commit | None | Add ruff/regex rule that blocks `class .*Mode.*\(.*Enum.*\)` containing `PAPER`/`LIVE` outside `domain/trading_mode.py` | New | None |

### Backend audit summary
The core spine is correctly placed: `domain/`, `features/`, `decision/`, `governor/`, `orders/`, `brokers/`, `simulation/`, `chart_lab/`, `control_plane/`, `runtime/`, `operations/`, `promotion/`. The truly banned names (`LiveMonitor`, `AccountGovernor`, `StrategyGovernor`, runtime `AccountAllocation`) are absent from runtime code — only in test fixtures (deliberate) and `reference_audits/`. Alpaca calls are restricted to `backend/app/brokers/alpaca.py` and `backend/app/market_data/alpaca.py`. PortfolioGovernor approval is enforced before order creation. **Drift began with the recent (2026-04-24 20:36–22:42) Services Center work**: `app/services/` bucket + `ServiceMode.PAPER/LIVE` enum directly violate Blueprint §15. ProgramVersion enforces no-inline-behavior cleanly but lacks content-hash freeze. OrderManager bypasses BrokerSync for read-only position checks. Governor duplicates ControlPlane state. `client_order_id` does not yet include `acct8` or `utos-` prefix.

---

## B. UX & Time-to-Market (6 HIGH, 7 MED, 1 LOW)

The AI Composer is the showcase for reuse-first, no-syntax UX. **The rest of the application has not yet inherited those primitives.** Most friction is on the manual editors (Components, Universes, Programs, Sim Lab, Backtests, Optimizations, Chart Lab) where users still type into bare `<input>` and `<select>` fields.

| # | Frict. | Title | Where it bites | Proposed change | Dimension |
|---|---|---|---|---|---|
| B1 | HIGH | Strategy Controls editor uses raw text inputs | [ui_mockup_v2.html:573-591](ui_mockup_v2.html) — sessions, regime gates typed by hand | Replace with same visual pill builder as AI Composer Step 6: session window picker (start/end + tz dropdown), regime-permission condition row identical to entry pills, blackout chips with calendar autosuggest. Reuse pill on each editor card. | No-syntax |
| B2 | HIGH | Risk/Execution/Universe cards have NO reuse pill | [ui_mockup_v2.html:595-672, 676-717](ui_mockup_v2.html) | Every component card gets `.reuse-pill` + match bar. "82% match · Use this · Variant · Compare." Risk: "3 of your existing profiles fall within ±20% of these caps." Universes: "84% overlap with 'High-Volume ETFs.'" | Reuse-first |
| B3 | HIGH | No global cross-library search | Top bar | Add Cmd+K command palette: free-text query → grouped results across Strategies / Controls / Risk / Execution / Universes / Programs / Features / Backtests, with per-row "Use in current draft." | Reuse-first |
| B4 | HIGH | No onboarding / first-run flow | Cold start; sidebar lacks "Get started" | Add `Get Started` page + 4-step setup checklist (connect broker → confirm provider → pick template → run AI Composer with prefilled prompt → save first Program). Persistent banner until dismissed. | Time-to-market |
| B5 | HIGH | Program Composer uses 5 vanilla selects, no diff/match awareness | [ui_mockup_v2.html:740-758](ui_mockup_v2.html) | Replace selects with component-cards: chosen version, last-edit date, "Use newer version (v3.3 available)," similarity to currently deployed Program, inline "Diff from v3.2" link. | Reuse-first |
| B6 | HIGH | No Program-version diff across all five components | Programs page | Add "Diff vs previous version" panel showing 5-row delta (one row per component) with old → new version IDs, links to per-component diffs, plain-English AI summary ("Risk changed Conservative→Aggressive · Universe unchanged · Execution Native→Trailing"). | Reuse-first / lineage |
| B7 | MED | Validation errors lack inline fix actions | [ui_mockup_v2.html:510-520, 1033](ui_mockup_v2.html) | Every error gets an actionable button: "Replace `gap_fill_pct` → Suggest registry-equivalent" (calls AI), "Open in Composer to fix," "Drop this condition." Extend the AI Composer Validation Status pattern to library cards. | Time-to-market |
| B8 | MED | Chart Lab and Sim Lab use raw text/number inputs | [ui_mockup_v2.html:794-805, 897-913](ui_mockup_v2.html) | Symbol → autocomplete from frozen Universe. Date range → calendar widget with presets ("last 30 trading days / since last earnings / current quarter"). Lookback → "Auto (warmup-aware)" default. "Replay last successful run" button. | No-syntax |
| B9 | MED | Reuse mining / consolidation alerts absent | Components page | Library Health banner per component-tab: "Detected 3 near-duplicate Risk Profiles → Review consolidations." Side panel proposes canonical version, lists which Programs would auto-rebind. | Reuse-first |
| B10 | MED | Optimization parameter ranges typed by hand | [ui_mockup_v2.html:1064-1101](ui_mockup_v2.html) | Auto-populate sweep table from AI Composer Backtest Plan's Sensitivity Tests; user toggles each row on/off. WF "Folds" picker shows tooltip recommending folds based on dataset length. | No-syntax + time-to-market |
| B11 | MED | Universe screener filters not editable inline | [ui_mockup_v2.html:676-717](ui_mockup_v2.html) | Add Screener Rules tab on each Universe with same `.cond-row` builder used for entries. Auto-suggest thresholds from registry + user's historical screener values. | No-syntax |
| B12 | MED | Example prompts not diverse enough | [ui_mockup_v2.html:1602-1610](ui_mockup_v2.html) — all entry-style strategies | Chip categories: Strategy / Risk / Controls / Screener / Variant. 2 chips per category. "Modify existing program" chip ("Take Momentum v3 and add an earnings blackout"). | Reuse-first |
| B13 | MED | Step-toggle exists but unwired to flow narrative | AI Composer step-cards | One-line summary next to each toggle: "Off: skip this step · component will be linked from existing library only." Toggling off collapses the step and shows existing-component picker. | Reuse-first |
| B14 | LOW | Step-card editing creates draft state but Cancel doesn't show diff | [ui_mockup_v2.html:1646-1736](ui_mockup_v2.html) | Inline mini-diff: "+1 condition · 1 threshold changed · 0 features removed." | Time-to-market |

### New screens worth adding
- **Get Started / Onboarding** — cold-start checklist; primary action: "Generate my first Program."
- **Global Cmd+K palette** — cross-library search; primary: "Insert into current draft."
- **Library Health** — surfaces near-duplicates, stale Universes, unused Programs.
- **Program Diff** — visualizes 5-component delta between Program versions.
- **Reuse Mining sidebar** (slot on every editor) — "this component now overlaps 91% with X — link instead?"
- **Screener Rules tab** on Universes — visual filter builder.

### Top 3 changes for fastest time-to-market
1. **Promote AI Composer primitives to every editor** (visual pills, registry-fed autocomplete, reuse pill, validation sidebar). Removes ~80% of typed syntax platform-wide without inventing new components.
2. **Ship Get Started checklist + Cmd+K palette.** Closes the cold-start cliff.
3. **Wire reuse mining into library + Program Composer** (Library Health banner, match-percent on every card, 5-row Program-level diff). Prevents the post-50-strategies sprawl.

---

## C. Operational Safety (5 HIGH, 5 MED, 2 LOW)

The mockup gets the *vocabulary* of safety right (intent badges, frozen plans, mode labels, fail-closed prose) but underdelivers on the *result surfaces* the spec explicitly requires. **The single biggest concrete gap is the missing structured Cancellation Result Panel — building it once unlocks honest fail-closed UX for kill, pause, resume, flatten, and auto-pause-on-invalidation in one component.**

| # | Sev | Title | Failure mode | v2 coverage | Proposed change | Spec rule |
|---|---|---|---|---|---|---|
| C1 | HIGH | Kill modal warns but result panel is missing four-bucket cancellation result | Operator confirms global kill, sees only a green toast and a banner — never the structured `CancellationResult`. If `kill_state_fetch_failed`, toast still says "executed." | [ui_mockup_v2.html:2293-2308](ui_mockup_v2.html); `confirmKill()` at 2429-2436 fires green toast unconditionally | After confirm, render **Cancellation Result Panel** with four collapsible sections (Canceled / Skipped-Protective / Skipped-Unknown / Errors). Each lists `{order_id, client_order_id, symbol, side, qty, intent, reason, deployment_id}`. Top red strip if `kill_state_fetch_failed`. Add `kill_state_fetch_failed` column to event log. | Control_Plane_Spec Phase 6, Hard Rule #5 |
| C2 | HIGH | Recovery surface invisible post-startup | After crash/restart, operator can't see which deployments are `recovered_ready` vs `blocked_recovery`, or what `reconciliation_issues` exist | [ui_mockup_v2.html:1539](ui_mockup_v2.html) — single audit-log row mentions it | Add **Recovery & Reconciliation** card at top of Operations Center (visible when last-startup-was-recent). Three lists: `recovered_ready[]`, `blocked_recovery[{deployment, blocker_reason, required_action}]`, `reconciliation_issues[{type, account, deployment, internal_state, broker_state, suggested_resolution}]`. Add Recovery Status column on Deployments table. | Blueprint §13; recovery_orchestrator contract |
| C3 | HIGH | Per-symbol market-data staleness has no operator surface | Operator can't tell that MSFT entries are blocked because MSFT 1m bars are 90s stale, while the rest of the account is fine | Account-level staleness only ([line 1429](ui_mockup_v2.html)); per-symbol only inside Chart Lab | Add **Market-Data Health** panel to Operations Center listing per-symbol last-bar / last-tick timestamps and "blocked / fresh / stale" badge with threshold. On positions table, per-row stale chip when symbol's data falls behind. | §15 "Market data stale blocks affected symbols" |
| C4 | HIGH | Unknown external broker order has no triage workflow | System keeps flagging the same order forever; operator must touch broker out-of-band, defeating audit | Banner + row only ([line 1281, 1286](ui_mockup_v2.html)); no row actions | Row-level actions: `Inspect`, `Adopt to deployment...` (binds to chosen deployment_id; updates internal mapping; never overrides client_order_id), `Cancel at broker (manual)` (logs as `manual_cancel_unknown` audit), `Acknowledge / Mute` (with required justification + TTL). All produce audit entries. | §15 "Unknown intent kept and flagged, never auto-canceled"; Phase 4 |
| C5 | HIGH | Live-mode confirmation is one-time, not session-scoped/strictest | Spec demands "strictest operator confirmation, freshness, and control-plane gates" for `BROKER_LIVE`; v2 has a single checkbox-style gate row | [ui_mockup_v2.html:774](ui_mockup_v2.html) | **Live Operator Mode**: typed-confirmation modal (operator types account_id last 4 + literal "LIVE START") + 30-minute session token re-acquired between actions. Persistent red top-bar banner when active showing "session expires in N minutes." Backend `live_session_token` enforces per-action revalidation. | MODE_NAMING_CONTRACT §BROKER_LIVE; §13 "explicit operator approval" |
| C6 | MED | Daily-loss / drawdown lockout scope wrong; release time vague | Risk Profiles can be linked to multiple programs/accounts. v2 banner is keyed to Profile, not account. Release time "Until 00:00 ET" — TZ unclear. | [ui_mockup_v2.html:634-636](ui_mockup_v2.html) | Surface lockouts at **per-account scope** in Operations Center and on each Broker Account card: account, deployments affected, trigger details, trigger time, calendar version, explicit release timestamp in ET *and* operator-local TZ, manual override button (with audit). | §15; Control_Plane governor halt SM |
| C7 | MED | Feature-plan freshness during deployment has no auto-pause path visible | Plan can become invalid mid-session (stream gap → warmup violated; provider switch → cache invalid). v2 is start-time only. | Static informational banner on Deployments page only | `Plan health` column on Deployments: `warm / warming / invalid / stale-stream`. On invalidation, deployment auto-transitions to `paused (plan_invalid)` and emits toast + banner. Reuse cancellation-result panel for the auto-pause sweep. | §13; §15 |
| C8 | MED | WebSocket→polling fallback never surfaces | Stream silently dies; operator sees plausible-looking "1s ago" indefinitely | Single hardcoded "live" badge at [line 1254](ui_mockup_v2.html) | Top-bar `Stream:` chip with 3 states (`stream-live | polling-fallback | dead`), tooltip showing `last_heartbeat_ts`, `since_last_tick_ms`, `fallback_since`. Yellow banner during polling fallback; red banner blocking new opens if dead. | §15; §13 stop-ship test |
| C9 | MED | Calendar / event-day warnings absent on deployment plane | Deployment with 15:55 cutoff on a 13:00-close day will close late | Calendar version on Strategy Controls only ([line 587](ui_mockup_v2.html)) | **Today's Session** ribbon at top of Operations Center: `Today: 2026-04-24 — Half-day close 13:00 ET (Good Friday eve)` with affected deployments listed. T-30m banner before close. Block deployment-start if start window post-dates today's close. | Migration plan; §15 |
| C10 | MED | Promotion gate fail-closed-on-missing-input not visible | All 12 gates render binary pass/fail/warn. Missing inputs default to "not shown," opposite of fail-closed | [ui_mockup_v2.html:763-774](ui_mockup_v2.html) | Add fourth state `unknown` (gray) that **counts as fail** for promotion. Each row shows input timestamp/source. If any required input is `unknown` or older than its TTL, Promote button stays disabled with red banner explaining which input is missing. | §13; Hard Rule #5 |
| C11 | MED | Per-deployment pause action shows no result detail | Operator clicks Pause, sees only aggregate counts in audit log | [ui_mockup_v2.html:1332](ui_mockup_v2.html) | Per-action result drawer (same component as kill result panel) opens after pause/resume/stop. Persists last result on the deployment row. | Phase 6 UI result messaging — applies to all control-plane actions |
| C12 | LOW | Bracket leg "held" status not differentiated visually | At-a-glance reading conflates "broker has it queued" with "broker holding pending parent fill" | [ui_mockup_v2.html:1273-1284](ui_mockup_v2.html) | Group bracket legs visually under parent (indented row). Tooltip on `held`: "Bracket leg — Alpaca status `held`. Becomes active only on parent fill." | Control_Plane_Spec Alpaca SDK Verification |
| C13 | LOW | PDT surface informational only; no preflight block | UI doesn't block 4th day-trade in 5-day window pre-submission | Static `Yes/No` PDT cell on broker accounts | PDT widget: `day_trade_count_5d`, `remaining_before_bust`, `equity_above_25k_buffer`. Reject (with explanation modal) any new open that would bust PDT; surface projected count in Decision Inspector. | §8; §15 "Governor approves every new exposure" |

### Banned-pattern check (where v2 implicitly violates spec)
- **"Never silent success"** — kill modal copy at [line 2301](ui_mockup_v2.html) asserts it; `confirmKill()` at [2429-2436](ui_mockup_v2.html) unconditionally fires a green toast. **Hard Rule #5 violated in code.**
- **"Stale blocks new opens"** — partially honored: account scope OK, symbol scope missing entirely.
- **"Fail closed"** — Promotion Gate has no `unknown` state; missing inputs default to invisible.
- **"Protective orders survive pause/kill"** — claim asserted in copy ([lines 1341, 2300](ui_mockup_v2.html)) but `orders_skipped_protective[]` list is never rendered. Operator cannot verify the claim.
- **"Unknown intent kept and flagged, never auto-canceled"** — flag present, no triage path. Operators will work around via broker UI, defeating audit.

### Recommended sequence for safety surface additions (priority order)
1. **Cancellation Result Panel** (kill, account-pause, deployment-pause, flatten share one component)
2. **Recovery & Reconciliation panel**
3. **Live Operator Mode session + typed confirm**
4. **Per-symbol market-data health surface**
5. **Unknown-intent triage workflow**
6. **Stream / polling-fallback chip and banner**
7. **Per-account daily-loss / drawdown / PDT lockout surfaces** with explicit release timestamps
8. **Today's Session ribbon**
9. **Plan-health column + auto-pause-on-invalidation**
10. **Promotion gate `unknown` state with TTL'd inputs**
11. **Bracket leg visual grouping**

---

## D. Strategy Authoring Quality (5 HIGH, 7 MED, 1 LOW)

A "fast" composer that lets bad strategies through is worse than a slow one that catches them. The current uniform promotion gate (warn-only on missing Walk-Forward / Optimization, hard-fail only on unsupported features) **is wrong for risk-asymmetric instruments**.

| # | Sev | Title | Risk | v2 coverage | Proposed change |
|---|---|---|---|---|---|
| D1 | HIGH | Overfit detection absent in AI Composer when reusing similar | Composer surfaces "92% similar" (line 1971) but never shows whether siblings have *passing* OOS evidence; user inherits overfit invisibly | Similar Strategy Patterns shows similarity % only | Augment rows with: median OOS Sharpe of matched siblings, decay band, "broken-pattern" flag if any sibling deprecated for OOS failure. Block "Use this" reuse if >50% of high-similarity matches have severe-decay history. |
| D2 | HIGH | Walk-Forward warn-not-block wrong for leveraged ETFs / derivatives | TQQQ's path-dependent decay can blow up a strategy that backtests cleanly. Warn-only lets it reach paper without OOS evidence. | "Leveraged ETF: volatility elevated" soft yellow flag only | Make WF + Optimization + CPCV all hard-required for Programs touching: leveraged/inverse ETFs, options, futures, ADV<$5M, hard-to-borrow shorts. Keep warn-only for unleveraged equity/ETF. |
| D3 | HIGH | No regime-conditional metrics on Backtest Detail | A 2023→2026 backtest is a near-monotonic bull regime; without conditioning, Sharpe 1.84 is bull-market overfit by default | [ui_mockup_v2.html:1038-1056](ui_mockup_v2.html) — equity curve + plan ref only | Mandatory regime-conditional table on Backtest Detail: rows = {bull, bear, sideways, high-vol, low-vol, high-trend, low-trend}; cols = {trades, Sharpe, win%, PF, max DD}. Block promotion if any non-degenerate regime (≥30 trades) shows Sharpe < 0.5 or PF < 1.0. |
| D4 | HIGH | Cost sensitivity column-only, not stress-tested by default | Strategy "Fragile" on Run #0140 still gets to "Overfit warning" status, not blocked | Single "Cost model" dropdown ([line 1019](ui_mockup_v2.html)); badge appears post-hoc | Every backtest auto-runs cost sweep (base, +5/+10/+20 bps slippage; ×1, ×2 commission; +1 tick wider spread). Reject promotion if Sharpe at +10 bps < 0.5× base, or any cost stress flips PF < 1.0. |
| D5 | HIGH | Sample-size / statistical-power not surfaced | A user could promote a strategy with claimed Sharpe 2.0 on 80 trades because gate threshold is ≥100 | Single "Min trades 100" threshold ([line 1895](ui_mockup_v2.html)) | Compute and display 95% CI on Sharpe (Lo-MacKinlay or bootstrap): "Sharpe 1.84 [95% CI: 1.42–2.26], n=847, power=0.91". Block promotion if lower CI bound < 0.5. |
| D6 | MED | Evidence record missing reproducibility primitives | Auditor / future-you cannot reproduce bit-for-bit | [ui_mockup_v2.html:1171-1187](ui_mockup_v2.html) — 11 fields | Extend Evidence schema: `code_commit`, `engine_version`, `feature_registry_version`, `calendar_version`, `adjustment_policy`, `data_asof`, `governor_policy_hash`, `rng_seed`, `container_image_digest`. Render under "Reproducibility" section. Reject promotion if any field is null. |
| D7 | MED | AI Composer bias warnings shallow | Only flags TQQQ generically; no warnings for short-lookback × many-params overfit, sample-size vs claimed Sharpe, condition tree degeneracy, similarity-to-broken-pattern | [lines 1959-1967](ui_mockup_v2.html) | Expand Validation Status to **Bias & Sanity Checks** panel with 8 specific warning classes (see below). |
| D8 | MED | No-lookahead enforcement asserted but not visibly tested | "Enforced" is a label; no proof of which lookahead test ran | Two label cells, no detail | Make "No lookahead detected" expandable to show test ledger: every feature reference parsed, bar index it resolved to, "forming-bar access attempts: 0 (engine rejects)". Tie to FeatureKey determinism stop-ship test. |
| D9 | MED | ORB completion gate hidden in pre-trading-window | If user shortens window to 09:30 with 15m ORB, system should refuse | Chart Lab shows annotation; Composer Strategy Controls doesn't | Composer must compute `min(trading_window_start) ≥ session_open + ORB_window_minutes` and block if violated. Sim Lab `feature_unavailable` events aggregate into "First N bars unusable per session" KPI on Backtest Detail. |
| D10 | MED | Multi-tf source-bar provenance missing in Sim Lab inspector | Quiet alignment bugs become invisible | [Decision inspector lines 2322-2350](ui_mockup_v2.html) — no source-bar timestamps | Each feature reference shows source-bar tuple: `15m.rsi:length=14[0] = 56.2 (sourced from 15m bar 09:45 ET, completed 10:00 ET)`. Acceptance test: parity between sim and runtime source-bar hashes. |
| D11 | MED | Feature warmup blocks runtime but not test/run in UI | User can launch a backtest where the first 200 bars are silently invalid | Feature Plan side card shows warmup but doesn't gate the Run button | Backtest engine drops/flags warmup period. UI shows "Effective backtest period: 2023-01-04 → 2026-04-01 (first 2 trading days excluded for warmup)". Block run if requested period ≤ warmup. |
| D12 | MED | Strategy diversity not measured in Evidence aggregate | Three correlated Programs at 30% each is one 90% bet, not diversification | None | Add "Program correlation matrix" section: pairwise correlation of daily returns across deployed Programs over last 90 sessions. Flag any pair with |ρ| > 0.7 as effective duplicate. |
| D13 | LOW | Cold-data risk not flagged when universe span ≠ backtest span | Survivorship and structural-break biases enter silently | None | Composer flags per universe snapshot: `{first_listed, last_split, recent_constituent_change, missing_data_pct_by_symbol}`. Block if >5% of universe lacks coverage over requested period. |

### Promotion Gate amendment proposal — Tiered enforcement

Replace uniform gate with **context-sensitive Tier A/B/C**:

- **Tier A (strict, hard-block)** — Programs touching leveraged/inverse ETFs (TQQQ, SQQQ, SOXL…), options, futures, ADRs with thin float, ADV < $5M, hard-to-borrow shorts. Required: Chart Lab + Sim Lab (governor enforced) + Backtest with cost sweep + Optimization with IS→OOS decay ≤ 1.0 + Walk-Forward (≥6 folds, median OOS Sharpe ≥ 0.7×IS) + CPCV pass + regime breakdown showing no regime with Sharpe < 0.5 (n≥30) + sample-size 95% lower CI ≥ 0.5.
- **Tier B (standard, current rules)** — Unleveraged equity, large-cap ETFs, ADV > $5M. Required: Chart Lab + Sim Lab + Backtest. Strongly recommended: Optimization, Walk-Forward (warn-only).
- **Tier C (reduced, informational)** — Paper-only sandbox with capital tag. Required: Chart Lab + Sim Lab.

Tier is computed automatically from Universe + ExecutionStyle + RiskProfile and rendered as a badge on Programs. Operators **cannot manually downgrade** Tier A → Tier B; the system enforces.

### AI Composer Bias & Sanity Checks panel — eight warning classes
1. **Leveraged-instrument** (high) — "TQQQ is a 3x leveraged ETF. Daily reset compounding causes path-dependent decay (median 1y decay ~8–15%). Strict promotion gate engaged."
2. **Sample-size** — "At 5m intraday with 09:45–11:00 window (~15 bars/day) and ~3% firing rate, expect ~110 trades/year. A 1-year backtest will not give Sharpe within ±0.6. Recommend ≥3 years."
3. **Parameter-density** — "Strategy has 6 tunable parameters over a 2-year backtest. Grid search risks overfit. Recommend Bayesian sweep + CPCV."
4. **Similar-broken-pattern** — "92% similar to ORB Momentum, 87% to VWAP Breakout. 2 of 5 high-similarity matches were deprecated for severe IS→OOS decay. Review before reuse."
5. **Condition-tree degeneracy** — "All 5 entry conditions AND-combined; joint hit-rate over last 90 sessions is 0.4% — only ~3 trades/symbol/year. Statistics from a backtest will be unreliable."
6. **Trading-window vs ORB consistency** — "Window starts 09:45 ET. 15m ORB completes 09:45 ET. First usable bar is 09:50; raise window start or shorten ORB."
7. **Backtest period vs fold count** — "6 walk-forward folds on 2-year period gives ~12 OOS trades/fold. Reduce to 4 folds or extend to 4 years."
8. **Cost-fragility forecast** — "Intraday breakouts are slippage-sensitive. Cost sweep (5/10/20 bps) auto-runs; reject if Sharpe at +10 bps falls below 1.0."

### ColdStrategyDetector — auto-run before Program freeze
Deterministic checker `ColdStrategyDetector.run(program_draft)` fires before any draft → frozen transition. Emits a single `CompositeOverfitScore` in [0, 1] with **hard block at score > 0.7**, surfaces seven sub-signals:

| Signal | Threshold | Weight |
|---|---|---|
| IS→OOS decay sibling-inheritance | weighted median decay > 1.0 Sharpe | 0.25 |
| Parameter density | `params/log(trades) > 0.4` | 0.15 |
| Sample-size deficiency | 95% lower CI on Sharpe < 0.5 | 0.20 |
| Condition-tree rarity | joint AND firing rate < 1% | 0.10 |
| Single-regime concentration | >70% of period in one regime | 0.15 |
| Cost fragility | Sharpe at +10 bps / base < 0.5 | 0.25 |
| Lookahead-test coverage | any unverified feature reference | 0.40 (auto-block) |

Score is recorded on the Evidence record for the freeze attempt. Rejected freezes go to a `cold_strategy_log` so users see *why* and what to fix. The detector is the same code path used by the AI Composer's bias panel — UI shows live preview as the draft is edited, score drops as user fixes conditions, lengthens backtest, or adds Walk-Forward.

---

## E. Cross-Cutting Recommendations (highest leverage)

These recommendations span more than one lens. Land these first.

| # | Title | Lenses | Why it matters |
|---|---|---|---|
| X1 | **Cancellation Result Panel** (shared component for kill / pause / resume / flatten / auto-pause-on-invalidation) | Safety + UX | Honors Phase 6 contract end-to-end, unblocks 5 separate UI surfaces with one component. Solves C1, C7, C11. |
| X2 | **Composition-hash freeze + Evidence reproducibility section** | Architecture + Quality | A4 + D6 share the same fix: freeze the Program by content, record the freeze inputs in Evidence. |
| X3 | **Tier A/B/C Promotion Gate + `unknown` state** | Safety + Quality | C10 + D2 + the Tier proposal converge into one gate engine. Without it, leveraged-ETF strategies promote on warn-only. |
| X4 | **AI Composer primitives lifted to all editors** (Components, Universes, Programs, Sim Lab/Chart Lab inputs) | UX (B1, B5, B8, B11) + Quality (D9 visible in Composer) | Single biggest reduction in syntax surface. |
| X5 | **Live Operator Mode session token** | Safety + Architecture | C5 + A9 — strict live confirmation enforced by backend, not just UI. |
| X6 | **Per-account scope for stale / lockout / market-data health** | Safety + UX | C3, C6, C8 all root in scope drift; one architectural cleanup of `Stale`/`Lockout` events with consistent `(account_id, scope, reason, release_at)` payload solves all three. |
| X7 | **Banned-name lint + canonical mode enum guard** in CI | Architecture | A1, A2, A3, A12, A13 — prevent reintroduction of `ServiceMode.PAPER/LIVE`-class drift. |

---

## F. Risk Matrix (recommendations by implementation risk)

### LOW risk — UI/copy/lint changes
A8, A9, A10, A11, A13, B7, B12, B14, C12, D8, D11

### MED risk — adds new components/panels
B1, B2, B3, B4, B5, B6, B8, B9, B10, B11, B13, C1, C2, C3, C8, C9, C11, C13, D3, D4, D5, D7, D10, D12, D13

### HIGH risk — touches core domain or governor / control-plane
A1, A2, A3, A4, A5, A6, A7, A12, C4, C5, C6, C7, C10, D1, D2, D6, D9, **all of E (cross-cutting)**

---

## G. Suggested Execution Order

**Phase 1 — Stop the bleeding** (week 1, all LOW–MED risk):
1. Banned-name lint in CI (X7) → prevents new drift while we clean up old drift
2. Strike `app/services/` bucket; migrate to `market_data/`, `ai/`, `broker_accounts/` (A1, A2, A3, A12)
3. v2 mockup naming hygiene (A8, A9, A10) — apply in `mockup_review.html` (this PR)
4. Cancellation Result Panel (X1, C1, C11) — single shared component

**Phase 2 — Trust foundations** (week 2):
5. Composition-hash freeze on ProgramVersion (A4, X2)
6. Evidence reproducibility section (D6, X2)
7. ControlPlane as sole owner of pause/kill state; Governor consumes it (A6)
8. `client_order_id` reconciliation (A7)

**Phase 3 — Operator-grade safety** (week 3):
9. Recovery & Reconciliation panel (C2)
10. Per-symbol Market-Data Health (C3, X6)
11. Unknown-intent triage workflow (C4)
12. Live Operator Mode session token (C5, X5)

**Phase 4 — Quality gate** (week 4):
13. Promotion Gate `unknown` state + Tier A/B/C engine (C10, D2, X3)
14. Cost-sweep + sample-size CI auto-run (D4, D5)
15. Regime-conditional metrics on Backtest Detail (D3)
16. ColdStrategyDetector (D-summary)

**Phase 5 — Time-to-market UX** (week 5):
17. AI Composer primitives lifted to all editors (X4, B1, B5, B8, B11)
18. Reuse pills + match-percent across libraries (B2, B9)
19. Cmd+K palette + Get Started checklist (B3, B4)
20. Program Diff view (B6)

---

## H. Honest Accounting

- **Where the lenses found nothing material:** None. All four lenses returned actionable findings; none was padding.
- **Where I'd push back on a lens:** D2's Tier A/B/C is the most consequential change and it would be wise to gut-check the threshold rules (which symbols qualify for Tier A?) against your actual desired risk envelope before codifying.
- **Where the blueprint itself needs updating, not just code:**
  - §15 Hard Rules: add explicit "No `Services Center` UI page; no `app/services/` directory."
  - §3 Final Program shape: add `composition_hash` field + freeze immutability rule.
  - §8 vs Control_Plane_Spec Phase 1: reconcile `client_order_id` format.
  - §13 Promotion gates: replace uniform gate with Tier A/B/C.
  - MODE_NAMING_CONTRACT Banned Terms: extend to "internal enum values whose semantics are 'system mode' must use `TradingMode`".

The companion file [mockup_review.html](mockup_review.html) applies every UI-surface recommendation in this document.

---

## I. AGENT ALIGNMENT — Broker + Streaming Model (FINAL · binding)

This section supersedes any earlier broker-hierarchy proposal. The user has aligned the model. The four-lens review is folded under the constraints below.

### Final domain model

**BrokerAccount** — flat. No `BrokerConnection`. No `BrokerSubAccount`.

- Each API key set = one `BrokerAccount`
- Mode is `BROKER_PAPER` or `BROKER_LIVE` (canonical `TradingMode` enum)
- Owns balances, positions, orders, fills, restrictions (PDT, day-trade BP)
- Example: `Alpaca-Paper-1`, `Alpaca-Paper-2`, `Alpaca-Paper-3`, `Alpaca-Live-1` are **four distinct BrokerAccounts** — not sub-accounts of a wrapper.

**MarketDataPipeline** — first-class but **mediated by FeatureEngine.** Deployments do NOT bind to Pipelines directly. Pipelines are inputs to the FeatureEngine, which is the only computation layer (Blueprint §5).

- **Default scope per FeatureKey-class.** Defaults are set at the *feature class*, not the Deployment: "for streaming intraday bars → `alpaca-premium-1`; for daily historical → `yfinance-historical`; for OPRA options → `polygon-options`". The resolver picks the default unless an explicit per-feature override exists.
- **Resolution scope = FeatureKey.** For every FeatureKey in a Deployment's FeaturePlan, the FeatureEngine resolver picks a Pipeline that satisfies it. Different features in the same Deployment may resolve to different Pipelines.
- **Demand-dedup scope = FeatureKey.** Deeper than symbol-level — if two Deployments need `5m.close[0]` for AAPL, FeatureEngine subscribes once. Dedup key = full canonical FeatureKey including timeframe, parameters, and adjustment policy.

**Deployment** — does NOT carry a `pipeline_id`.

- Runs one `Program`
- Attached to **one** `BrokerAccount` (its trade route — broker side only)
- Hands its FeaturePlan to the FeatureEngine
- Consumes `FeatureSnapshot`s from FeatureEngine; never sees Pipelines

**FeatureEngine** — owner of Pipeline subscriptions.

- Receives FeaturePlans from Deployments
- Resolves each FeatureKey to a Pipeline (using per-class defaults + overrides)
- Manages subscription lifecycle: subscribe / unsubscribe / dedup / warmup
- Exposes a **Subscription Map** as an operator surface (which features are live, which Pipelines serve them, which Deployments depend on them)

**Key implication 1: a single BrokerAccount can host deployments whose features come from different Pipelines.**

```
BrokerAccount: Alpaca-Live-1
  ├── Deployment A: Day-trade momentum on TQQQ
  │     features: 5m bars, level-2     →  FeatureEngine resolves to alpaca-premium-1
  └── Deployment B: Position rebalance on SPY (weekly)
        features: 1w bars only          →  FeatureEngine resolves to yfinance-historical
```

The BrokerAccount is unchanged. Each Deployment hands its FeaturePlan to FeatureEngine, which subscribes accordingly.

**Key implication 2: a single Deployment can mix Pipelines per FeatureKey.** Multi-timeframe AND multi-capability are both FeatureEngine concerns:

```
Deployment X · FeaturePlan:
  ├─ 3m.close[0]              →  resolved to alpaca-premium-1  (1m base, 3m derived)
  ├─ 1w.high[0]               →  resolved to yfinance-historical (1d base, 1w derived)
  ├─ 5m.option_iv[0] (NVDA)   →  resolved to polygon-options
  └─ news.corporate_events    →  resolved to news-vendor

FeatureEngine subscribes to 4 different Pipelines on this Deployment's behalf.
The Deployment never knows; it just receives FeatureSnapshots.
```

**Capability-matching rule (per-FeatureKey, not per-Deployment):** for every FeatureKey, the resolver picks a Pipeline whose capabilities (finest native timeframe, instrument coverage, streaming/historical, etc.) satisfy that key's requirements. A FeatureKey needing 1m bars → `yfinance-historical` rejected with `UNSUPPORTED_TIMEFRAME`; resolver tries the next candidate.

**Hard rules:**
- Roll coarser, never finer. The FeatureEngine derives coarser timeframes by aggregation; Pipelines never invent finer bars.
- One subscription per `(FeatureKey)` in the FeatureEngine's subscription map. Demand-dedup is at the feature level.
- Deployments do not name Pipelines. Any code path that lets a Deployment specify `pipeline_id` is a bug.

**The edge case I previously flagged** (equity + OPRA options + news in one strategy) **is no longer an edge case.** It's the normal case. FeatureEngine resolves each FeatureKey to whatever Pipeline can serve it; multiple Pipelines per Deployment is the default, not a workaround.

**PortfolioGovernor** — name preserved. **Per-BrokerAccount scope** (NOT one global governor).

```
BrokerAccount A  → PortfolioGovernor A
BrokerAccount B  → PortfolioGovernor B
BrokerAccount C  → PortfolioGovernor C
BrokerAccount D  → PortfolioGovernor D
```

Each governor:
- Reads THAT account's positions, buying power, open orders
- Enforces THAT account's risk / exposure / max-position limits
- Approves or rejects trades for THAT account only
- Consults the global ControlPlane for kill / pause state, but makes its own per-account decision

### Hard constraints (binding)

Do NOT:
- Introduce `BrokerConnection`
- Introduce `BrokerSubAccount` layer
- Duplicate streaming per `BrokerAccount`
- Merge AI services and market-data systems
- Rename `PortfolioGovernor`
- Share one global governor across accounts

Do:
- One `MarketDataPipeline` subscribes once per symbol; data fans out to all consumer `BrokerAccount`s
- One `PortfolioGovernor` instance per `BrokerAccount`
- AI Services and Market Data live in separate API surfaces (`/api/v1/ai/...` vs `/api/v1/market-data/...`)

### Implications for prior plan_review.md recommendations

**Superseded:**
- The earlier Section I `BrokerVendor` / `BrokerConnection` / `BrokerSubAccount` model — **rejected**. Flat `BrokerAccount` stands.
- Recommendation A6 (Governor pause state on ControlPlane) — **modified**. Each per-account `PortfolioGovernor` *consults* `ControlPlane.can_open_new_position(account_id, deployment_id)` for kill/pause state, then makes its own per-account approval decision.

**Still valid (unchanged):**
- A1, A2, A3 — delete `app/services/`, migrate AI services to `app/ai/`, eliminate `ServiceMode.PAPER/LIVE`
- A4 — `composition_hash` freeze on `ProgramVersion`
- A7 — `client_order_id` format
- All UX lens findings (B1–B14)
- All Safety lens findings (C1–C13), with C3/C8 footnote: per-symbol staleness has fan-out blast radius across all consumer `BrokerAccount`s — surface it
- All Quality lens findings (D1–D13)
- The Tier A/B/C promotion gate
- The ColdStrategyDetector
- Banned-name lint (X7)

**Largest remaining amendment:** `MarketDataPipeline` as first-class concept. Required before any further runtime work that assumes one-stream-per-account.

### Sixth amendment to the Master Blueprint (revised)

Add to §3 Canonical Domain Model:
- **`MarketDataPipeline`** — independent of `BrokerAccount`. May be marked default for a vendor. Selected per `Deployment`; fans out to many consumer Deployments via demand-dedup at `(provider, environment, symbol)`.

Add to §15 Hard Rules:
- "Streaming is pipeline-aware. One `MarketDataPipeline` subscribes once per symbol; data is fanned out to all consumer Deployments. Per-account streaming is forbidden."
- "PortfolioGovernor is per-`BrokerAccount` scope. Each `BrokerAccount` has exactly one governor instance. Governors do not approve trades across accounts."
- "AI Services and Market Data are separate systems. They do not share API surfaces, providers, or capability tags."

### Sequencing

Insert into Section G execution order **between phases 2 and 3**:

- **Phase 2.5 — MarketDataPipeline extraction**:
  - New domain model `MarketDataPipeline` in `backend/app/market_data/pipeline.py`
  - Resolver moves from `app/services/service_resolver.py` → `app/market_data/resolver.py`
  - Streaming dedup at the pipeline layer, not the broker-adapter layer
  - UI: Providers page Market Data Pipelines surface; BrokerAccount cards show `pipeline_id` binding
  - Deployment binding gets a `pipeline_id` field

This precedes Phase 3 (operator-grade safety) because per-symbol staleness blast radius is meaningful only once Pipelines are first-class.

### Risk

HIGH. Touches domain, runtime, broker-sync, several UI pages. Cannot be ad-hocked. Migration sequence:

1. Add `MarketDataPipeline` model + persistence
2. Existing `BrokerAccount` rows migrate to point at a default Pipeline (one per provider/environment that account currently uses)
3. Resolver returns `pipeline_id` (it just looks up the Pipeline that wraps the chosen provider)
4. UI surfaces the binding
5. Streaming engine is refactored to dedup by Pipeline rather than per BrokerAccount

---

## J. Resolver Visibility Contract (per Phase 1 task + alignment)

The user's Phase 1 Resolver Visibility task is approved with the refinements below. **Mounted under Providers → Market Data Pipelines, not as a separate Services Center page.**

### Resolver output contract (binding)

Every resolver invocation must return:

```
{
  "symbol":              "AAPL",                        // per-symbol when input is multi-symbol
  "selected_provider":   "alpaca",
  "pipeline_id":         "pipeline-alpaca-premium-1",   // REQUIRED — Pipeline binding visible
  "selection_strategy":  "auto" | "default-preferred" | "manual-override",
  "reason":              "BEST_AVAILABLE_FOR_TIMEFRAME", // frozen enum
  "rejected_providers": [
    { "provider": "yfinance", "code": "UNSUPPORTED_TIMEFRAME" },
    { "provider": "polygon",  "code": "CREDENTIAL_MISSING"   }
  ],
  "resolver_input_hash":  "sha256:...",                 // for replay
  "resolver_version":     "0.9.4",
  "decided_at":           "2026-04-25T19:32:18.214Z",
  "invocation_context":   "chart_lab" | "sim_lab" | "broker_runtime" | "backtest"
}
```

### Frozen rejection codes

- `UNSUPPORTED_TIMEFRAME`
- `UNSUPPORTED_INSTRUMENT`
- `CREDENTIAL_MISSING`
- `CAPABILITY_TIER_INSUFFICIENT`
- `MODE_MISMATCH`
- `RATE_LIMIT_EXCEEDED`
- `OPERATOR_VETO`
- `STREAM_NOT_AVAILABLE`
- `HISTORICAL_NOT_AVAILABLE`

Free-text reasons in audit logs are **forbidden**. UI maps codes → human strings.

### Renaming

`mode (auto / default / manual)` — banned wording. Mode is reserved for `TradingMode` per MODE_NAMING_CONTRACT. Use **`selection_strategy`** with values `auto` / `default-preferred` / `manual-override`.

### Determinism is a backend invariant, not a UI surface

`Same input → same output` belongs in `backend/tests/unit/market_data/test_resolver_determinism.py` as a stop-ship test, not as a UI badge. The UI surfaces a "last determinism test passed at <timestamp>" line for confidence, but does NOT attempt to detect nondeterminism live. If determinism breaks, CI fails; the panel does not become a graveyard for it.

### What the Phase 1 ship delivers

- ✅ Resolver Result Panel under Providers → Market Data Pipelines
- ✅ Per-symbol rows when input is multi-symbol
- ✅ `pipeline_id` binding visible per Deployment (default vs override)
- ✅ `selection_strategy` (renamed off "mode")
- ✅ Frozen rejection-code enum; UI maps codes to strings
- ✅ Debug section (collapsed) with `resolver_input_hash`, `resolver_version`, `decided_at`, `invocation_context`, `code_commit`
- ✅ Stop-ship pytest determinism test in CI
- ❌ No standalone "Services Center" page
- ❌ No new sidebar entry
- ❌ No "mode" wording for selection strategy
