import type { RoadmapItem } from "./RoadmapCard";

/**
 * Research-surface roadmaps.
 *
 * Each page lists items that were explicitly out-of-scope of the slice that
 * built it, plus shipped follow-ups so operators see what's actually built.
 * Run-lifecycle items are listed first because they are the most
 * operator-visible UX surface (drawer → job → monitor → toast → result).
 */

const RUN_LIFECYCLE: RoadmapItem = {
  title: "Async job queue + per-fold/per-candidate progress + cancel",
  status: "planned",
  category: "Run lifecycle",
  description:
    "Drawer POSTs to /api/v1/research/jobs/{kind}, returns immediately with a job_id, and closes. The JobMonitor pulse-dot in each research page header shows active + recent jobs with progress bars, status badges, per-job Cancel button, and a link to the result run when complete. Walk-Forward emits per-fold progress; Optimization emits per-candidate progress; Backtest reports run-level status. Cancellation is cooperative — services check between iterations and abort cleanly. Polls every 2s when active jobs exist, every 15s when terminal. You can navigate freely or close the browser; the job keeps running and the JobMonitor catches up.",
};

const NOTIFICATIONS: RoadmapItem = {
  title: "Completion toast + Dashboard 'last 10 runs' card",
  status: "planned",
  category: "Run lifecycle",
  description:
    "Global JobToaster mounted at the AppShell level fires a toast whenever any research job transitions to a terminal state (completed → 'View results' link to the right surface; failed → error preview with link; canceled → muted confirmation). The Dashboard 'Recent research runs' hub card (ResearchJobsHubCard) shows the latest 10 runs across all kinds with the same progress-bar + per-row Cancel + click-through to surface — operators see recent runs without navigating to a research page first. Polls 2s when active jobs exist, 15s when terminal.",
};

export const BACKTESTS_ROADMAP: RoadmapItem[] = [
  RUN_LIFECYCLE,
  NOTIFICATIONS,
  // — Adjacent research surfaces (already shipped or in design)
  {
    title: "Walk-Forward (rolling-window validation + recommended risk plan)",
    status: "planned",
    category: "Adjacent research surfaces",
    description:
      "Same engine; per-fold IS+OOS replays; recommended risk plan emerges from the sweep; ship/no-ship recommendation enum with max-DD gates. Live now under Walk-Forward.",
  },
  {
    title: "Optimization (parameter sweep on one window + landscape + WF handoff)",
    status: "planned",
    category: "Adjacent research surfaces",
    description:
      "Grid + random search across a parameter grid; full landscape with heatmap when 2 dimensions; explicit 'needs walk-forward validation' banner; one-click handoff to WF with the top-K candidates pre-filled. Live now under Optimization.",
  },
  // — Strategy + RiskPlan authoring
  {
    title: "Risk Plan picker + product-facing Risk Plan model",
    status: "planned",
    category: "Strategy + Risk Plan authoring",
    description:
      "Risk Plans have a first-class list, 10-tab detail, full Create/Edit drawer with §9.4 validation feedback, AI-draft section, Account-default assignment, and Compare two plans. The Backtest / Walk-Forward / Optimization drawers all accept a Risk Plan via picker (no more UUID paste). Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §4 + §8 + §9 + §10.",
  },
  {
    title: "Strategy authoring UI for logical exit rules",
    status: "shipped",
    category: "Strategy + Risk Plan authoring",
    description:
      "Strategies page ships a typed BuilderPane (no JSON textareas) with a visual condition pill builder + a LogicalExitRulePicker that honors all seven LogicalExitRule kinds (feature_condition / bars_since_entry / time_in_position_seconds / time_of_day_et / minutes_before_session_close / session_window / hybrid). Hybrid recursively composes child rules with operator=all|any. Doctrine-locked: time/bars/session/feature/hybrid exits all live under SignalPlan.intent=logical_exit, never as a sibling top-level intent. Same picker is reused inside the AI Composer's edit-before-save pane.",
  },
  {
    title: "Full-page Strategy Builder + catalog-driven feature picker",
    status: "shipped",
    category: "Strategy + Risk Plan authoring",
    description:
      "Visual builder is now a dedicated route (/strategies/:strategyId/builder/new and /strategies/:strategyId/builder/:versionId) instead of a cramped drawer. Three-column layout: section nav · BuilderPane · live Validation + Feature Plan Preview. The new FeaturePicker replaces the bare text field with a Radix popover that surfaces the live FeatureRegistry catalog grouped by namespace (Price / Technical / Session / Portfolio); selecting a kind opens a per-feature parameter form (timeframe, length, source, session, lookback) and emits canonical `5m.kind:params[lookback]` syntax. The unified feature engine computes every supported kind for both research and live runtime, so the picker no longer needs to flag a batch-vs-stream taxonomy. Add Version + Edit Draft both link into the builder; creating a Strategy now lands the operator directly on the builder for the first version.",
  },
  {
    title: "Strategy IDE v4 — expression engine, IDE shell, starter strategies, full cutover",
    status: "shipped",
    category: "Strategy + Risk Plan authoring",
    description:
      "The v4 IDE is now the canonical strategy authoring surface at /strategies/compose. Slices 1–8.6: Python-style expression engine (IncrementalFeatureEngine), Monaco editor, feature palette, variables strip, long/short tabs, stops/legs/exits/execution preview, 12 starter strategy templates, full library list at /strategies (edit, duplicate, delete). Legacy composer routes and component tree removed; backend legacy CRUD stays alive for runtime/research until Slice 11.",
  },
  {
    title: "AI Strategy Composer (wizard → prefilled editor, 12 templates, coherence validator)",
    status: "shipped",
    category: "Strategy + Risk Plan authoring",
    description:
      "/strategies/compose mounts OUTSIDE the AppShell — sidenav and topbar are gone while composing. Two-page flow: Page 1 (wizard) presents curated 12 starter templates (ORB, VWAP Reclaim, Supertrend, RSI Mean Reversion, Connors RSI-2, IBS, Ichimoku, MA Pullback, ATR Breakout, FVG+HTF, Gap-and-Go, Prior Day H/L) with inline prompt textarea, guiding checkboxes for direction/horizon/timeframe/htf-confirmation/stops/targets, and side-panel template picker. Page 2 (prefilled editor) exposes 14 fixed sections (summary, long entry, short entry, entry plan, stop plan, target plan, runner plan, logical exit, time-based exit, execution preset, strategy controls, validation warnings, research actions) pre-populated from template + AI or template defaults. FeatureIndex mounts as a drawer scoped to section edits, not a permanent left rail. Coherence validator surfaces 15 rules (HTF not in entry, unsupported features, intraday with no time exit, etc.) with severity bars on affected sections; Save disables if errors exist. Save posts StrategyDraft to /composer/drafts and lands on /strategies/:id with a 'Verify in Backtest' deep-link toast pre-bound to saved StrategyVersion. Strategy Controls are first-class Page 2 fields; StrategyDraft carries the concrete SignalPlan shape bound post-deployment via Watchlist. Page 2 collapsed from 14-section TOC layout to 4 tabs (Core / Signals / Stop·Target·Execution / Controls) with per-tab error counts and blueprint chips; validation panel and research deep-links moved into the sticky save bar. Stop · Target · Execution tab gates the Stop / Target / Runner cards on the active execution preset (market-in/market-out and stop-entry/market-out hide all three; bracket+target shows stop+target only; bracket+runner and multi-target scale-out show all three) and renders an ExecutionPreviewRail diagramming entry / stop / target / runner price levels from the active preset overrides. Save-bar Validation badge tones itself by max severity (red for errors, amber for warnings, muted for info-only advisory notes) so informational coherence checks are surfaced without an extra button. Strategy Controls section split into two cards (Timeframe & horizon, Session windows); Cooldowns & caps, PDT & gap risk, and Regime filter cards stay on the roadmap pending a frontend Zod schema catch-up to backend fields and brand-new backend slices respectively.",
  },
  // — Engine completeness
  {
    title: "Reduce / partial-close in SimulatedBroker",
    status: "planned",
    category: "Engine completeness",
    description:
      "RiskResolver supports `action=reduce + quantity_pct=N` for LogicalExitRules; today SimulatedBroker.submit_close_order closes the full requested qty. Planned: honor partial reduce so 'reduce 50% after 15 minutes' actually halves the position.",
  },
  {
    title: "Cost-aware execution (slippage moves fill price; spread gates limit fills)",
    status: "planned",
    category: "Engine completeness",
    description:
      "Cost model is metrics-only post-fill today. Planned: slippage shifts the broker's actual fill price (so PnL and stop-eligibility reflect the same fill), spread gates limit-fill behavior, partial fills tie to bar volume. Touches SimulatedBroker; benefits Sim Lab + Backtest equally.",
  },
  {
    title: "Short-side entries",
    status: "shipped",
    category: "Engine completeness",
    description:
      "Full short-side support across SignalEngine, RiskResolver, and SimulatedBroker. SHORT entries route as sell-to-open; protective stops trigger on bar.high; trailing stops ratchet DOWN; cover fills compute realized PnL as (entry − exit). SimulatedPosition.qty is signed; SimulatedTrade.side reflects the opener direction. Cross-side flips while a position is open are still rejected with reason 'opposite_side_position_open' (tracked separately).",
  },
  {
    title: "Cross-side position flips (long ↔ short while a position is open)",
    status: "planned",
    category: "Engine completeness",
    description:
      "Today the spine emits a single OPEN SignalPlan and rejects opposite-side entries while a position is held. Planned: when an entry rule fires opposite to the current side, the spine flattens the existing position and opens the new side in one bar — required for symmetric long/short strategies that switch on regime change.",
  },
  {
    title: "Multi-strategy portfolio backtest",
    status: "parked",
    category: "Engine completeness",
    description:
      "One strategy per backtest today. Multi-strategy portfolios (ensembles, allocation across strategies, cross-strategy risk caps) are not currently scheduled.",
  },
  {
    title: "Borrow / T+1 settlement / market impact",
    status: "parked",
    category: "Engine completeness",
    description:
      "Cost model carries no borrow / settlement / market-impact terms; only commission + slippage. Parked until live execution data demands it.",
  },
  // — Validation
  {
    title: "Benchmark alpha / beta vs SPY",
    status: "planned",
    category: "Validation",
    description:
      "Backtest evidence does not currently report alpha vs a benchmark; planned for the polish slice that follows the Risk Plans CRUD work.",
  },
  {
    title: "Live-vs-backtest reconciliation harness",
    status: "parked",
    category: "Validation",
    description:
      "Compare a strategy's live (paper) trades against what the backtest would have produced over the same window. Planned for after live runtime instrumentation matures.",
  },
];

export const WALK_FORWARD_ROADMAP: RoadmapItem[] = [
  RUN_LIFECYCLE,
  NOTIFICATIONS,
  // — Validation surfaces already scaffolded but awaiting backend data
  {
    title: "Per-fold IS / OOS chart with shading",
    status: "planned",
    category: "Visualisations awaiting backend evidence",
    description:
      "Frontend scaffold exists behind AwaitingApiOrError; backend serves per-fold metrics on WalkForwardRun.metrics.folds. Planned: a dedicated chart component that plots IS/OOS Sharpe + return per fold with IS/OOS shading on the equity curve.",
  },
  {
    title: "Parameter stability heatmap",
    status: "planned",
    category: "Visualisations awaiting backend evidence",
    description:
      "Show how often each parameter combination won across folds — the candidate landscape from the Optimization slice can drive this directly.",
  },
  {
    title: "OOS regime breakdown",
    status: "planned",
    category: "Visualisations awaiting backend evidence",
    description:
      "Break down OOS performance per regime (bull / bear / chop / volatile / trending) so operators can gate deployment on regime fit.",
  },
  {
    title: "Equity curve with IS/OOS shading",
    status: "planned",
    category: "Visualisations awaiting backend evidence",
    description:
      "Single equity curve across the full window with shaded bands marking each fold's IS vs OOS region.",
  },
  // — Recommendation persistence
  {
    title: "Save recommended Risk Plan as a real RiskPlanVersion",
    status: "planned",
    category: "Recommendation persistence",
    description:
      "The 'Save as Risk Plan' button on the WF RecommendedRiskPlanCard opens the Risk Plan Create drawer pre-filled with the recommendation parameters and source=walk_forward_recommended. Operator reviews, tightens, and saves explicitly — AI / research never silently mints a Risk Plan (per non-negotiable §13).",
  },
  // — Search depth
  {
    title: "Strategy-parameter sweeps (vs risk-plan sweeps)",
    status: "parked",
    category: "Search depth",
    description:
      "WF currently sweeps RiskPlan fields. Strategy-parameter sweeps (e.g. SMA length, RSI threshold) need parameterized strategies — `SignalRule` referencing `${sma_length}` placeholders that the sweep grid binds.",
  },
  {
    title: "Live / paper integration",
    status: "parked",
    category: "Search depth",
    description:
      "Walk-forward output is research evidence only — never live promotion. The deployment-attachment freeze rule remains the sole live-readiness gate.",
  },
];

export const OPTIMIZATION_ROADMAP: RoadmapItem[] = [
  RUN_LIFECYCLE,
  NOTIFICATIONS,
  // — Search algorithms
  {
    title: "Bayesian / sequential search",
    status: "planned",
    category: "Search algorithms",
    description:
      "Grid + random search shipped in v1. Planned: a Bayesian (or other sequential acquisition function) wrapper around the same per-candidate runner so the search adapts to prior results — useful when the parameter space is large.",
  },
  {
    title: "Parallel candidate execution",
    status: "planned",
    category: "Search algorithms",
    description:
      "Sequential execution today. Each candidate is independent so multi-process parallelism is straightforward; deferred to a follow-up slice that handles process-pool lifecycle + per-candidate fault isolation.",
  },
  {
    title: "Pareto multi-objective optimization",
    status: "parked",
    category: "Search algorithms",
    description:
      "Single-objective (max_dd_bounded_sharpe) today. Pareto frontier (e.g. maximise Sharpe AND minimise max-DD as a frontier) is interesting but not currently scheduled.",
  },
  // — Search depth
  {
    title: "Strategy-parameter sweeps (vs risk-plan sweeps)",
    status: "parked",
    category: "Search depth",
    description:
      "Optimization currently sweeps RiskPlan fields only. Strategy-parameter sweeps need parameterized strategies — same dependency as Walk-Forward.",
  },
  // — Recommendation persistence
  {
    title: "Save winner as a draft Risk Plan version",
    status: "planned",
    category: "Recommendation persistence",
    description:
      "The 'Save winner as Risk Plan' button on the Optimization detail page opens the Risk Plan Create drawer pre-filled with the best parameters and source=optimization_generated. Operator must review, validate with Walk-Forward, and click Save — the button is enabled even when WF validation hasn't been run yet, but the drawer carries the 'hypothesis only' AI note prominently.",
  },
];
