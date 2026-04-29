# Current State Audit

Snapshot date: 2026-04-27.

> **Coordination notice (2026-04-27 01:01:09 -04:00):** the original
> body of this audit predates the discovery of Operation Turtle
> Shell (`../Operations_Turtle_Shell_Artifacts/`). Operation Turtle
> Shell has completed slices 1–10 of the backend doctrine spine;
> their `OPERATION_STATUS.md` and `NEXT_IMPLEMENTATION_SEQUENCE.md`
> are the authoritative current-state for the backend. Sections in
> this audit that describe the runtime spine, governor, risk
> resolver, orders, deployment publisher, and account fan-out as
> "broken / missing" are **superseded** by the deltas listed in
> `## Coordination delta` below. Read that section first if you only
> have time to read one part of this audit.

This audit is a hard read of what exists in the repo today against the
locked doctrine. Items are labeled:

- ✅ **PRODUCTION-READY** — already aligned, tested, and load-bearing.
- 🟡 **PARTIAL** — exists but not wired, half-aligned, or under-tested.
- 🔴 **BROKEN / MISALIGNED** — actively contradicts doctrine and must
  be rebuilt or rewired.
- ⚪ **MISSING** — required by doctrine, does not exist yet.

## Coordination delta vs. Operation Turtle Shell (authoritative)

The following items in the original audit body are stale. The
coordination delta is the authoritative current state.

| Original finding | Authoritative current state |
|---|---|
| 🔴 RuntimeEngine is Program-centric, builds ExecutionIntent | ✅ `backend/app/runtime/engine.py` and the legacy `RuntimeEngine` are **removed** by Operation Turtle Shell (Nanyel Deviation Correction Iteration, 2026-04-27 00:27:05 → 00:45:21 -04:00) |
| 🔴 Two parallel runtime objects | ✅ Single composition root via `pipeline/orchestrator.py` (`RuntimeOrchestrator`); `BrokerRuntimeOrchestrator` and `BrokerRuntimeSupervisor` retained as broker-paper coordinators only |
| 🟡 SignalPlanBuilder is dead code | ✅ Wired: SignalEngine → SignalPlanBuilder → neutral SignalPlan publication into the runtime pipeline |
| ⚪ No DeploymentPublisher | ✅ `DeploymentPositionManager` (runtime-only) plus pipeline-driven SignalPlan emission cover entries from Watchlist and exits from Account-owned Positions filtered by `deployment_id` |
| ⚪ No AccountSignalPlanEvaluator | ✅ Pipeline produces per-Account `RiskResolverResult`, `AccountSignalPlanEvaluation`, `GovernorDecisionTrace`, order decision; one SignalPlan fans out to many subscribed Account ids |
| 🟡 RiskResolver inputs are temporary placeholders | ✅ `RiskResolver.lifecycle_sizing_from_risk_profile(...)` is the first quantity boundary; `LifecycleSizingInput`, `RiskResolvedLegAllocation`, `fractional_quantity_allowed`, `quantity_rounding_policy` all live |
| 🔴 Governor reads ExecutionIntent / emits legacy `GovernorDecision` | ✅ `GovernorRequest` now accepts canonical fields (deployment_id, symbol, signal_plan_id, position_lineage_id, order_intent, broker freshness, portfolio); `PortfolioGovernor` evaluates from canonical request and produces `GovernorDecisionTrace`; protective bypass extended to all position-management intents |
| 🔴 OrderManager production entrypoint is ExecutionIntent | ✅ `OrderManager.create_signal_plan_order(...)` and `create_signal_plan_leg_orders(...)` are canonical; legacy `create_order(execution_intent=...)` is shim only and inverts side for non-open exits; lineage columns populated |
| ⚪ No PositionLineage service | 🟡 `BrokerPositionSnapshot` carries nullable Position lineage fields; `SQLiteRuntimeStore.list_broker_position_snapshots_by_deployment(...)` exists; `DeploymentPositionManager` consumes it. A standalone `PositionLineage` aggregate that builds `PositionExplanationContext` on demand is still pending |
| ⚪ No persistence of GovernorDecisionTrace | 🟡 Persistence-Ready Lineage slice (Turtle Shell Slice 2) added nullable lineage columns to `internal_orders` for `governor_decision_id`, `account_evaluation_id`, `signal_plan_id`, `opening_signal_plan_id`, `position_lineage_id`. Standalone `governor_decision_traces` table is still pending |
| ⚪ Account Trade Sync per-Account at boot | ✅ Unified per Operation Turtle Shell Slice 7; `TradeEventDispatcher.status()` exposes canonical `AccountTradeSyncStatus`; events route through `BrokerStreamRouter` and `BrokerSyncService` before fan-out |
| ⚪ Live Stock Market Data Stream unified, mode-neutral, boot-started | ✅ Slice 8; `HubKey` provider+feed only; envelope opens with zero subscriptions; `/api/v1/system/streams` projects mode-neutral status |
| ⚪ Research evidence persistence | ✅ Slice 10; ChartLab/Backtest/Sim Lab/Optimization/Walk-Forward/Promotion contracts persist; `/api/v1/operations/research-evidence` queries them |
| ⚪ Banned-name lint guardrails | ✅ Both operations contribute: Turtle Shell `test_turtle_shell_architecture_guardrails.py` (Program lineage, runtime authority); Production Readiness `test_no_banned_product_names.py` (human-readable banned phrases and identifiers). 149 lint tests pass at 2026-04-27 |
| Legacy `ExecutionIntent` shims | 🟡 Active removal in flight under Operation Turtle Shell — ExecutionIntent compatibility removal iteration started 2026-04-27 00:48:59 -04:00 |
| Legacy `Program` shims | 🟡 Allowlisted in `PROGRAM_LINEAGE_ALLOWED_FILES`, shrinking per slice; full removal is the Coordinator's stated next step after ExecutionIntent removal |

Items that remain **MISSING** and are squarely in the Production
Readiness operation's scope (frontend + user-facing CRUD layer +
operator readiness):

- ⚪ Strategies / Watchlists / Deployments as **user-facing durable
  entities** with their own services, persistence (top-level
  tables), and `/api/v1` CRUD routes. The runtime consumes their
  shapes; they are not yet first-class operator entities.
- ⚪ AccountRiskConfig / AccountRestrictions modeled per Account
  with API.
- ⚪ Position Explain API + AI advisory `explain_position`
  surface backed by `PositionExplanationContext`.
- ⚪ Dashboard read-model `/api/v1/dashboard/summary`.
- ⚪ Frontend full redesign (Operation Turtle Shell explicitly
  bans frontend work).

The original audit body below is preserved for historical context.
Sections marked stale by the table above must be read alongside it.

## 1. Documentation

✅ Active doctrine set is consistent and minimal:

- [docs/ULTIMATE_TRADER_MANDATE.md](../docs/ULTIMATE_TRADER_MANDATE.md)
- [docs/architecture/CANONICAL_RUNTIME_ARCHITECTURE.md](../docs/architecture/CANONICAL_RUNTIME_ARCHITECTURE.md)
- [docs/architecture/NAMING_CONTRACT.md](../docs/architecture/NAMING_CONTRACT.md)
- [docs/architecture/SIGNALPLAN_POSITION_LIFECYCLE.md](../docs/architecture/SIGNALPLAN_POSITION_LIFECYCLE.md)
- [docs/architecture/STREAMS_AND_PROVIDERS.md](../docs/architecture/STREAMS_AND_PROVIDERS.md)
- [docs/architecture/BACKEND_MODULE_MAP.md](../docs/architecture/BACKEND_MODULE_MAP.md)
- [docs/architecture/OPERATOR_EXPERIENCE.md](../docs/architecture/OPERATOR_EXPERIENCE.md)
- [docs/architecture/UI_VISUAL_DIRECTION.md](../docs/architecture/UI_VISUAL_DIRECTION.md)
- [docs/operations/RUNTIME_SHIP_GATE.md](../docs/operations/RUNTIME_SHIP_GATE.md)
- [docs/operations/DAY_ZERO_RUNBOOK.md](../docs/operations/DAY_ZERO_RUNBOOK.md)
- [docs/implementation/IMPLEMENTATION_LOG.md](../docs/implementation/IMPLEMENTATION_LOG.md)
- [docs/implementation/NEXT_BUILD_PLAN.md](../docs/implementation/NEXT_BUILD_PLAN.md)

🟡 The `NEXT_BUILD_PLAN.md` is correct but fragmentary. The plan in
this folder is the operative one going forward.

🔴 No active doc points the reader at the *gap* between doctrine and
running code. That is what this audit closes.

## 2. Domain contracts (`backend/app/domain/`)

✅ SignalPlan, AccountSignalPlanEvaluation, GovernorDecisionTrace,
RiskResolverResult, RiskResolvedLegAllocation, PositionExplanationContext
exist with correct lineage fields and reject Account-execution leakage
([backend/app/domain/signal_plan.py:101](../backend/app/domain/signal_plan.py#L101)).

✅ TradingMode (BROKER_PAPER / BROKER_LIVE) is Account metadata
([backend/app/domain/trading_mode.py](../backend/app/domain/trading_mode.py)).

✅ StrategyVersion exists with rules / candidate intent shape
([backend/app/domain/strategy.py](../backend/app/domain/strategy.py)).

🔴 `ProgramVersion` still exists and is *load-bearing* across runtime
and orders — directly violates the doctrine ban
([backend/app/domain/program.py](../backend/app/domain/program.py)).
Doctrine ban in
[docs/architecture/NAMING_CONTRACT.md:36](../docs/architecture/NAMING_CONTRACT.md#L36).

🔴 `ResolvedProgramComponents` (in `backend/app/features`) bundles
strategy + execution_style + risk_profile + universe_snapshot. Used as
the runtime configuration object — keeps the Program model alive even
though the user-facing concept is meant to be Strategy + Deployment.

⚪ No Watchlist domain contract beyond `UniverseSnapshot`. Doctrine
calls Watchlist a first-class product entity; no `Watchlist` /
`WatchlistVersion` schema, no membership rules, no dynamic-rules
contract.

⚪ No Deployment domain contract. The runtime has `DeploymentContext`
but it carries `program: ProgramVersion`, not `strategy_id +
watchlist_ids + subscribed_account_ids + runtime_overrides`.

⚪ No `AccountRiskConfig` / `AccountRestrictions` / `AccountKillSwitch`
contracts. Risk lives only in `RiskProfileVersion` keyed to a Program.

⚪ No `PositionLineage` aggregate. Position truth is read off broker
position snapshots but not joined to opening SignalPlan, Account
evaluation, Governor decision, related SignalPlans, orders, fills.

## 3. Runtime spine (`backend/app/runtime/`)

🔴 `RuntimeEngine` operates on `ResolvedProgramComponents`, builds an
`ExecutionIntent` with `program_version_id`, calls Governor on the
ExecutionIntent
([backend/app/runtime/engine.py:286-360](../backend/app/runtime/engine.py#L286-L360)).
This is the legacy Program-centric pipeline. SignalPlanBuilder is *not
called*. RiskResolver is *not called*. AccountSignalPlanEvaluation is
*not produced*. Position lineage is *not written*.

🔴 `BrokerRuntimeOrchestrator` ties Deployment to a single
`account_id` (with a half-built `account_ids` tuple), composes the
pipeline by `RuntimeOrchestrator`, and does broker preflight gating.
The whole composition assumes Program semantics. Multi-account fan-out
exists in seams (`broker_freshness_by_account`, `portfolio_snapshot_by_account`)
but no SignalPlan/per-Account-evaluation step actually runs
([backend/app/runtime/account_trading_orchestrator.py](../backend/app/runtime/account_trading_orchestrator.py)).

🟡 `runtime_context.py` correctly owns process-singleton hub registry,
trade dispatcher registry, and manual trade registry
([backend/app/runtime/runtime_context.py](../backend/app/runtime/runtime_context.py)).
Boot-time stream start works. Live stock market-data hub is created and
started. Per-Account trade dispatchers are eagerly started. This is
the *one* doctrine-aligned production path that already works.

🟡 Recovery orchestrator exists but is wired against `ResolvedProgramComponents`
and Program-centric runtime state.

## 4. Decision (`backend/app/decision/`)

🟡 `SignalEngine` evaluates StrategyVersion → `CandidateTradeIntent`.
This is fine internally but the consumer is the legacy ExecutionIntent
path
([backend/app/decision/signal_engine.py](../backend/app/decision/signal_engine.py)).

🟡 `SignalPlanBuilder` is correct and complete but *not called* by
production code
([backend/app/decision/signal_plan_builder.py:21](../backend/app/decision/signal_plan_builder.py#L21)).

⚪ No `DeploymentPublisher` service that:
   1. Iterates Watchlist symbols → entry candidates → SignalPlan(open).
   2. Iterates Account-owned Positions filtered by `deployment_id` →
      exit candidates → SignalPlan(close|reduce|target|stop|trail|
      breakeven|runner|logical_exit).
   3. Hands SignalPlans to subscribed Accounts.

## 5. RiskResolver (`backend/app/risk_resolver/`)

✅ `RiskResolver.resolve_static` and `resolve_lifecycle` produce
correct `RiskResolverResult` shapes including leg allocations for
target/runner/stop with whole-share rounding policy
([backend/app/risk_resolver/service.py](../backend/app/risk_resolver/service.py)).

🟡 Inputs are `StaticSizingInput` / `LifecycleSizingInput` placeholders
acknowledged as "temporary while runtime migrates away from
ExecutionIntent." Real Account-specific sizing (risk-percent equity,
fixed dollar with broker buying power, fractional capability per
broker) is not yet pulled from the Account context.

🟡 Not wired into the production runtime.

## 6. Governor (`backend/app/governor/`)

🟡 `PortfolioGovernor.evaluate` checks global kill, account/deployment
pause, broker sync staleness, max open positions, gross/net exposure
caps, symbol concentration, and open risk
([backend/app/governor/service.py:27](../backend/app/governor/service.py#L27)).
The list is the right list.

🔴 Input shape is `GovernorRequest` carrying `execution_intent` and
`order_intent`, not `SignalPlan` + `RiskResolverResult` + Account
context. Doctrine wants Governor to evaluate per-Account against an
Account-resolved plan.

🔴 Output is `GovernorDecision` (legacy shape). The doctrine's
`GovernorDecisionTrace` exists in domain but is not produced.
Two parallel decision shapes is doctrine-banned.

⚪ No persistence of GovernorDecisionTrace per SignalPlan per Account.
Operations cannot answer "why was this position opened?" with full
governor context.

## 7. OrderManager (`backend/app/orders/`)

✅ Internal order intents, idempotency, client_order_id formats,
position-management priority ordering, ledger replace semantics, and
broker_sync wiring are well-modelled
([backend/app/orders/manager.py](../backend/app/orders/manager.py)).

✅ SignalPlan-aware columns exist on the persisted internal order
schema (`signal_plan_id`, `opening_signal_plan_id`,
`current_signal_plan_id`, `position_lineage_id`,
`account_evaluation_id`, `governor_decision_id`, `leg_label`,
`lifecycle_intent`)
([backend/app/persistence/models.py:4](../backend/app/persistence/models.py#L4)).

🔴 `OrderManager.create_order` is called from the ExecutionIntent path.
It does not consume `(SignalPlan, RiskResolverResult,
GovernorDecisionTrace)` directly. The columns above are populated only
from manual-trade and from a half-wired pass-through.

## 8. Brokers (`backend/app/brokers/`)

✅ BrokerAdapter is the only submission boundary. BrokerSync is the
only broker truth writer. AlpacaBrokerAdapter, AlpacaAccountStreamAdapter,
BrokerStreamRouter, BrokerStreamRunner, AlpacaBrokerPreflightService,
MarketRulePreflightService all exist and are well-tested.

✅ Capability profiles, fractional/extended-hours rules, fakepaca test
stream support exist
([backend/app/brokers/capabilities.py](../backend/app/brokers/capabilities.py),
[backend/app/brokers/preflight.py](../backend/app/brokers/preflight.py)).

✅ BrokerSync `apply_result`, `sync_open_orders`, `sync_positions`,
`sync_account`, reconciliation, freshness — all correct
([backend/app/brokers/sync.py](../backend/app/brokers/sync.py)).

🟡 Multiple Account / multi-mode test coverage is good but does not yet
include cross-Account SignalPlan fan-out.

## 9. Broker Accounts (`backend/app/broker_accounts/`)

✅ Unified `BrokerAccountService` (one create, one credentials replace,
one delete) with provider+mode pinning, encrypted `BrokerCredentialStore`,
inline validation
([backend/app/broker_accounts/service.py](../backend/app/broker_accounts/service.py)).

✅ Boot-time `bootstrap_streams` starts trade dispatcher per Account
and starts manual-trade composition root
([backend/app/runtime/runtime_context.py:540](../backend/app/runtime/runtime_context.py#L540)).

🟡 `AccountRiskConfig`, `AccountRestrictions`, `AccountKillSwitch`,
`AccountSubscribedDeployments`, `AccountSymbolBlocklist` are not
modelled. Risk lives only in the runtime governor policy and Program
risk profile.

## 10. Market data (`backend/app/market_data/`)

✅ MarketDataStreamHub, AlpacaMarketDataAdapter, pipeline registry,
resolver, capability profiles, validation, catalog, data intent — all
exist with broad unit-test coverage.

🟡 The frontend Providers page still exposes "pipelines" and "services"
language, which is internal nomenclature. Doctrine-clean naming on the
operator surface is "Market Data Providers" with provider cards. The
pipeline/service distinction needs to be moved behind the page.

## 11. AI (`backend/app/ai/`)

✅ AI provider catalog, validation, runtime advisory boundary
([backend/app/ai/](../backend/app/ai/)). Routes expose CRUD, set-default,
validate.

⚪ No `Explain this position` advisory endpoint that consumes a
`PositionExplanationContext` (because the context is not produced).

## 12. Operations (`backend/app/operations/`)

✅ `OperationsCenterService` produces `RuntimeOverview`, per-Account,
per-Deployment, per-Order projections; control-plane commands flow
through it
([backend/app/operations/service.py](../backend/app/operations/service.py)).

🟡 The projection consumes `ResolvedProgramComponents` shapes
indirectly. It does not surface SignalPlans, AccountSignalPlanEvaluations,
or position lineage explanation context — because those records are
not produced.

⚪ No "recent SignalPlans by Deployment", "Account decisions by
SignalPlan", "GovernorDecisionTrace timeline", "Position explanation"
panels.

## 13. Persistence (`backend/app/persistence/`)

✅ SQLite runtime store with `internal_orders`, `trades`,
`broker_order_mappings`, `broker_accounts`, `broker_account_snapshots`,
`broker_position_snapshots`, `broker_open_order_snapshots`,
`broker_sync_freshness`, `deployment_runtime_states`,
`portfolio_governor_states`, `control_plane_states`,
`manual_order_idempotency`, `manual_trade_audit_events`,
`research_evidence`
([backend/app/persistence/models.py](../backend/app/persistence/models.py)).

⚪ No tables for: `strategies`, `strategy_versions`, `watchlists`,
`watchlist_versions`, `deployments`, `signal_plans`,
`account_signal_plan_evaluations`, `governor_decision_traces`,
`account_risk_configs`, `position_lineages`, `risk_cards`.

⚪ Migration path: legacy Program-centric records, if any exist
locally, must be migrated to the Strategy/Deployment model. The
`system_migration` route handles only legacy market-data catalog.

## 14. API routes (`backend/app/api/routes/`)

✅ Operations read+control surface, Broker Accounts CRUD, Manual
Trade per Account, Market Data services/pipelines, AI providers,
System Status, System Settings, System Streams, Chart Lab, System
Migration.

⚪ Missing routes (full list in
[API_AND_READ_MODEL_GAPS.md](./API_AND_READ_MODEL_GAPS.md)):
  - `/api/v1/strategies` (CRUD, version, validate)
  - `/api/v1/watchlists` (CRUD, static + dynamic, snapshot)
  - `/api/v1/deployments` (CRUD, start/stop/pause, subscribe/unsubscribe Accounts)
  - `/api/v1/signal-plans` (list / detail by Deployment, by Account, by symbol)
  - `/api/v1/accounts/{id}/risk-config`
  - `/api/v1/accounts/{id}/positions/{lineage_id}/explain`
  - `/api/v1/accounts/{id}/evaluations` (per SignalPlan decisions)
  - `/api/v1/governor/policy` (read/write)
  - `/api/v1/governor/decisions` (timeline)
  - `/api/v1/sim-lab/runs` (CRUD)
  - `/api/v1/backtests` (CRUD, evidence already exists)
  - `/api/v1/optimization` (jobs, results)
  - `/api/v1/walk-forward` (jobs, results)
  - `/api/v1/promotion` (paper → live gate evaluate)
  - `/api/v1/dashboard/summary` (single read-model for the home page)

## 15. Frontend (`frontend/`)

🟡 Vite multi-page app with five static pages: Operations, Chart Lab,
Brokers (Accounts), Providers, Settings. Vanilla JS modules, hand-rolled
state per page. No router, no SPA framework, no shared store.

⚪ Missing pages required by doctrine: Dashboard, Strategies,
Components, Watchlists, Deployments. Detail panels missing: Orders,
Trades, Positions, SignalPlans, Backtests, Optimizations, Walk-Forward,
Sim Lab, Risk Cards, Position Explanation drawer.

🟡 Naming violations on operator surface:

- Top-nav label "Brokers" → should be "Accounts" per doctrine
- Mode labels in `brokers.js` were corrected to plain `"Paper"` /
  `"Live"` so paper/live are Account metadata, not runtime products
  ([frontend/src/brokers.js:13-15](../frontend/src/brokers.js#L13-L15))
- Providers page mixes "services" and "pipelines" terminology that
  doctrine wants hidden
- `index.html` title: "Operations Center · Trading OS" — fine; but
  `<title>` and brand mark "Trading OS" should be normalized to
  "Ultimate Trader" everywhere

🟡 Test coverage: `brokers.test.mjs`, `chartLab.test.mjs`,
`marketDataPipelines.test.mjs`, `operationsCenter.test.mjs`,
`operationsTradeStream.test.mjs`. Adequate for current pages, no
coverage for missing pages.

## 16. Tests (`backend/tests/`)

✅ 82 backend test files across all modules. Solid unit coverage on
domain contracts, brokers, governor, risk_resolver, orders, persistence,
operations, ai, chart_lab, control_plane, decision, features, market_data,
pipeline, promotion, runtime, simulation, broker_accounts, lint
guardrails (banned mode enums, turtle shell architecture, feature
engine isolation).

✅ 7 integration tests (alpaca paper, fakepaca, crypto, broker truth
money path, manual trade loop, feature demand resolver→pipeline,
resolver→pipeline-id).

✅ 1 smoke test for account runtime.

⚪ Missing test surfaces:
  - DeploymentPublisher: SignalPlan emission for entries from
    Watchlist and exits from Position lineage scoped by deployment_id
  - Multi-Account fan-out: one SignalPlan, two Accounts decide
    differently
  - AccountSignalPlanEvaluation: persistence and re-emission semantics
  - GovernorDecisionTrace: produced and persisted per evaluation
  - Position lineage: opened, related close/reduce, partial fills,
    explanation context built end-to-end
  - SignalPlan idempotency per Account
  - Banned name guardrails extended to UI labels and API responses
    (Program, Account Governor, Services Center, Paper/Live Runtime)

## 17. Naming and ownership violations

| Where | Violation | Source |
|---|---|---|
| Domain | `ProgramVersion` is load-bearing | [domain/program.py](../backend/app/domain/program.py) |
| Domain | `RiskProfileVersion`, `ExecutionStyleVersion` keyed to Program | [domain/risk_profile.py](../backend/app/domain/risk_profile.py) |
| Runtime | `DeploymentContext.program: ProgramVersion` | [runtime/models.py:43](../backend/app/runtime/models.py#L43) |
| Runtime | `ExecutionIntent` carries `program_version_id` | [runtime/models.py:90](../backend/app/runtime/models.py#L90) |
| Runtime | RuntimeEngine builds ExecutionIntent, not SignalPlan | [runtime/engine.py:286](../backend/app/runtime/engine.py#L286) |
| Governor | Reads ExecutionIntent, emits legacy GovernorDecision | [governor/service.py](../backend/app/governor/service.py) |
| Operations service | Surfaces Program / Deployment fused, no SignalPlans | [operations/service.py](../backend/app/operations/service.py) |
| Frontend | Top nav still says "Brokers"; mode labels are now plain Paper / Live | [frontend/src/brokers.js:13](../frontend/src/brokers.js#L13) |
| Frontend | Providers exposes "pipelines" / "services" language | [frontend/src/providers.js](../frontend/src/providers.js) |
| Branding | Title says "Trading OS" instead of "Ultimate Trader" | [frontend/index.html](../frontend/index.html) |
| Persistence | No table for strategies, watchlists, deployments, signal_plans, account_evaluations, position_lineages | [persistence/models.py](../backend/app/persistence/models.py) |

## 18. Hidden / duplicate runtime paths

- The `RuntimeEngine` (per-deployment in-process) and
  `BrokerRuntimeOrchestrator` (broker-paper supervisor) are *not the
  same* runtime. The orchestrator wraps a `pipeline.RuntimeOrchestrator`
  that re-implements bar→signal→intent. There is overlap and the truth
  about which one runs in production is murky. Doctrine demands one
  loop.
- Manual-trade flow has its own composition stack registered in
  `ManualTradeRegistry` parallel to the runtime stack. Wiring is
  documented but the two stacks must demonstrably share the per-Account
  ledger. Tests cover this; the architecture, however, deserves a
  single composition root.
- `bootstrap_streams` and `bootstrap_manual_trade_composition` run on
  app startup. They share a `broker_account_service` but build
  independent adapter instances. Acceptable, but the resolver pattern
  should be pinned to a single rotation strategy.

## 19. Strengths to preserve

These already meet production-grade and must not be regressed:

- Encrypted `BrokerCredentialStore` and unified `BrokerAccountService`
- `bootstrap_streams` boot-time auto-start of trade dispatchers and
  market-data hub (per Account, regardless of Deployment subscription)
- BrokerAdapter / BrokerSync ownership boundaries
- Manual trade idempotency, audit events, preflight, control-plane
  gating
- Operator-visible Account Trade Sync states and Live Stock Market
  Data Stream status (system_streams)
- SQLite atomic IO and runtime store schema for orders/trades/sync
- Domain SignalPlan / Account evaluation / Governor trace contracts
  (already correct — they just need to be produced)
- Lint guardrails: no banned mode enums, turtle shell architecture,
  feature engine isolation

## 20. Unknowns to inspect next

If a follow-up pass picks this up, these are the targets it should
read in full before deciding:

- `backend/app/pipeline/orchestrator.py` — confirm whether this is the
  *real* runtime spine and whether it short-circuits the
  `RuntimeEngine`. Important for deciding refactor vs replace.
- `backend/app/runtime/recovery_orchestrator.py` — confirm whether
  recovery is Program-coupled or already SignalPlan-aware.
- `backend/app/control_plane/service.py` — confirm whether
  cancellation scopes, kill, pause, resume already cover Account /
  Deployment / SignalPlan lineage.
- `backend/app/promotion/service.py` — confirm whether the paper→live
  promotion gate is still keyed on Program freezing or whether it can
  be re-keyed to Strategy version + Deployment evidence.
- `backend/app/simulation/engine.py` and `historical_replay.py` — the
  Sim Lab and Backtest contracts to confirm research evidence already
  flows through `domain.research_evidence`.
- `frontend/src/operationsCenter.js` (full file) — confirm what
  Operations already renders so the Dashboard/Operations split stays
  clean.

## 21. Risk register (top items)

1. **Two parallel runtime objects** (`RuntimeEngine`,
   `BrokerRuntimeOrchestrator` + `pipeline.RuntimeOrchestrator`) make
   "what runs in production" unprovable until consolidated.
2. **Domain has correct doctrine, runtime does not** — it is easy to
   ship things that pass `pytest backend/tests/unit/domain` and still
   violate doctrine in the live path.
3. **Frontend lacks 4 of 9 mandated nav surfaces**, including
   Dashboard, Strategies, Watchlists, Deployments.
4. **No SignalPlan persistence** — even if produced in-memory, no
   audit, no Operations panel, no explanation context.
5. **Naming violations on the operator surface** can mislead an
   operator into believing paper and live are separate products.
