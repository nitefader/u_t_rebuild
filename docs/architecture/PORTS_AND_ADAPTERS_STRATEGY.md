# Ports & Adapters Strategy

**Author:** Solutions Architect (Claude, plan-only mode)
**Date:** 2026-05-02
**Status:** PROPOSAL — pending operator approval. No code in this slice.
**Related:** [CANONICAL_RUNTIME_ARCHITECTURE.md](CANONICAL_RUNTIME_ARCHITECTURE.md), [BACKEND_MODULE_MAP.md](BACKEND_MODULE_MAP.md), [NAMING_CONTRACT.md](NAMING_CONTRACT.md)

---

## 1. Executive Summary

Ultimate Trader's spine is correct in shape but coupled by concrete imports at the boundary points where it matters most: signal evaluation, strategy artifact resolution, and the broker adapter. The system has ~1,750 LOC of legacy strategy stack that cannot be deleted today because **ChartLab and every research lab still load through it**, while the live runtime loads through v4 — a dual stack with no shared interface.

This plan introduces explicit application ports at the boundaries where multiple implementations are realistic (signal sources, market data providers, broker adapters) and canonical contracts at the boundaries where the data shape is what matters (FeatureSnapshot, SignalPlan, Account state). It does **not** introduce ports for CRUD services, simple DTOs, or a generic event bus.

The architectural payoff: future engine swaps (Rust port, ML signal source, options broker) become **registration changes**, not codebase-wide hunts. The naming-tax of `_v4` / `_v5` / `_legacy` suffixes leaking into runtime callers stops happening.

**Final S12 recommendation (Section 13):** Phase 1 (SignalSourcePort) **must** land before any S12 deletion. Survey evidence below makes this non-negotiable, not a preference.

---

## 2. Current Coupling Map

Sourced from three concurrent code surveys (2026-05-02). All file:line citations verified against `feature/cleanup-modern-core` HEAD.

### 2.1 Signal Boundary — TWO STACKS, ZERO INTERFACE

| Caller | Signal path | File:Line |
|---|---|---|
| **Live runtime** | v4 `build_signal_plan_from_v4` | `pipeline/orchestrator.py:2166` |
| **Live runtime (still)** | legacy `SignalEngine.evaluate` | `pipeline/orchestrator.py:474, 2048` |
| **ChartLab** | legacy `SignalEngine.evaluate` (only) | `chart_lab/preview_service.py:301` |
| **Backtests / SimLab / WalkForward / Optimization** | legacy via `HistoricalReplayEngine` | `simulation/historical_replay.py:972, 1059, 1221` |

**Implication.** Legacy is load-bearing for ChartLab + every research lab. V4 is load-bearing for live trading. Deleting legacy without first abstracting the boundary breaks ChartLab and the entire research suite. (See Section 13.)

### 2.2 Strategy Artifact Resolution — TWO LOADERS

| Stack | Loader | Returns |
|---|---|---|
| Legacy | `research/components.py:load_strategy_version()` (line 82–94) | `StrategyVersion` |
| V4 | `strategies_v4/component_loader.py:load_strategy_version_v4()` (line 16–42) | `StrategyVersionV4` |

`Deployment` carries both `strategy_version_id` and `strategy_version_v4_id` as optional FKs (validator requires one). The runtime branches on which is set; research always uses legacy. **There is no `resolve(deployment) -> SignalSource` function.**

### 2.3 Feature Engine Boundary — ALREADY CLEAN

Survey confirmed memory note `reference_canonical_feature_engine.md`:

- `IncrementalFeatureEngine` is the only engine. Three callers (`pipeline/orchestrator.py:205`, `chart_lab/preview_service.py:123`, `simulation/historical_replay.py:757`).
- `build_feature_plan(components, consumer)` is the canonical planner. Four call sites, one per surface.
- **No indicator math anywhere outside `backend/app/features/`.** Frontend confirmed rendering-only.
- `FeatureSnapshot` (`features/frames.py:36`) flows through live + research + ChartLab unchanged.

**Implication.** FeatureEnginePort is largely a documentation exercise — the boundary already exists in practice; we just need to formalize the Protocol and add a lint gate to prevent regression.

### 2.4 Broker Boundary — PROTOCOL EXISTS, CONCRETE LEAKS REMAIN

| Item | Status | Evidence |
|---|---|---|
| `BrokerAdapter` Protocol | ✅ Defined | `brokers/adapter.py:12–44` (8 methods) |
| Concrete leaks | ❌ Present | `runtime/runtime_context.py:161,604,612,646`; `broker_accounts/service.py:77`; `api/server.py:260` import `AlpacaBrokerAdapter` directly |
| Single broker-truth writer | ✅ Holds | All `save_broker_*` calls live inside `brokers/sync.py` |
| Quantity sizing single home | ✅ Holds | `risk_resolver/service.py:259–310` is the only place `final_quantity` resolves |
| Governor as policy gate | ✅ Holds | `governor/service.py:10`; protective-exit bypass at line 44–49 (intent-scoped, correct) |

**Implication.** The broker boundary is mostly right. We need (a) registration to remove the concrete-class import sites and (b) a lint gate to keep the single-writer invariant.

### 2.5 Account State — INFORMAL

`BrokerAccountSnapshot` is read by orchestrator, governor, risk resolver, order manager, and broker accounts service. There is no `AccountStatePort` — each consumer fetches via `BrokerSyncService.fetch_account_snapshot` or reads from cached state. Works today; doesn't scale to "what if account state lives in a different store" without refactor pain.

### 2.6 Guardian — DONE BUT UNDOCUMENTED AS A PORT

`apply_guardian_adoption` (sync.py:1168) + `guardian_context_provider` wire site (sync.py:62, 76). Working in production. Just needs to be named as a port for clarity.

### 2.7 Naming Leak

The string `_v4` appears in: type names (`StrategyVersionV4`), package names (`strategies_v4/`), FK names (`strategy_version_v4_id`), function names (`build_signal_plan_from_v4`, `load_strategy_version_v4`), route prefixes (`/api/v1/strategies/v4/`). This is the leakage the operator is reacting against — it's a versioned **type**, not a versioned **interface**, so callers must spell the version.

---

## 3. Target Port Catalog

Thirteen ports, grouped by spine layer. Numbered to match the operator's spec.

| # | Port | Layer | Multiple impls? | Registry needed? |
|---|---|---|---|---|
| 1 | SignalSourcePort | Decision | Yes (v4, future Rust, future ML) | Yes |
| 2 | StrategyArtifactResolver | Decision | No (one resolver, dispatches) | No |
| 3 | FeatureEnginePort | Computation | No today; future possibly | No |
| 4 | MarketDataPort | Data | Yes (Alpaca, Yahoo, +) | Yes |
| 5 | ResearchReplayPort | Research | One spine; multiple lab views | No |
| 6 | RiskResolverPort | Risk | One impl planned | No |
| 7 | GovernorPort | Risk | One impl planned | No |
| 8 | OrderManagerPort | Execution | One impl planned | No |
| 9 | ExecutionPort / BrokerAdapterPort | Execution | Yes (Alpaca, Fake, +) | Yes (exists informally) |
| 10 | BrokerSyncPort | Truth | One impl planned | No |
| 11 | AccountStatePort | State | One impl; consumer count >5 | No |
| 12 | GuardianAssignmentPort | State | One impl planned | No |
| 13 | NotificationPort | Cross-cut | Multiple sinks (UI, log, audit) | Yes |

**Registries only where multiple implementations are realistic.** Adding a registry for a port with one implementation is ceremony.

---

## 4. Port-by-Port Contracts

Each port section follows the same shape: **purpose · accepts · returns · forbidden · known impls · current code that becomes the first adapter**.

### 4.1 SignalSourcePort

**Purpose.** Convert a strategy artifact + FeatureSnapshot + position context into a canonical `SignalPlan` candidate (or no-fire result with reasons).

**Accepts.**
- Resolved strategy artifact (opaque to caller; produced by `StrategyArtifactResolver`)
- `FeatureSnapshot` (the canonical one from `features/frames.py`)
- `PositionContext` collection
- Evaluation mode hint (`live` / `research` / `chart_verification`)

**Returns.** `SignalEvaluationResult`:
- `signal_plan_candidate: SignalPlan | None` (None = no fire)
- `feature_usage: FeatureUsage` (which features were read)
- `condition_truth: ConditionTruthTree` (per-rule evaluation; powers ChartLab)
- `non_fire_reasons: tuple[str, ...]`
- `source_engine: EngineMetadata` (engine name + version + content hash)

**Must not.** Size trades, submit orders, call brokers, write positions, own risk, own execution plan, mutate Deployment.

**Known implementations (today + roadmap).**
- `V4ExpressionSignalSource` — wraps `build_signal_plan_from_v4`
- `LegacyRuleSignalSource` — wraps `SignalEngine.evaluate` (transitional only; deleted in S12c)
- *Future:* `RustExpressionSignalSource`, `ExternalLLMSignalSource`

**Becomes-first-adapter mapping.**
- V4 adapter: `decision/signal_plan_builder_v4.py` body, with `_strategy_scoped_loader` already in place
- Legacy adapter: `decision/signal_engine.py` + `decision/signal_plan_builder.py` body — keeps callers green during migration; deleted in Phase 5

**Migration rule.** After Phase 1, runtime / ChartLab / research / SimLab / Optimizer / Walk-Forward never import `signal_engine` or `signal_plan_builder_v4` directly. They call `SignalSourcePort`.

---

### 4.2 StrategyArtifactResolver

**Purpose.** Resolve a `Deployment` (or `DeploymentSnapshot`) into a concrete `SignalSourcePort` implementation plus immutable artifact metadata. **This is the field that replaces `_v4` / `_v5` / `_legacy` naming leakage.**

**Accepts.**
- `deployment_id: UUID` OR `deployment_snapshot: DeploymentSnapshot`
- (Internally:) `strategy_artifact_id` (canonical) — resolves whether artifact is v4, future-Rust, etc.

**Returns.**
- `signal_source: SignalSourcePort` (already bound to the loaded artifact)
- `artifact_metadata: StrategyArtifactMetadata` (engine kind, version, content hash, immutable)
- Validation errors if the artifact's engine kind is not registered

**Must not.** Evaluate signals, compute features, mutate strategy/deployment, hide a missing artifact behind a fallback.

**Field-naming rule.** `Deployment` keeps **one** logical FK. We do not introduce `strategy_version_v5_id`. Two acceptable shapes:

- **Option α:** `Deployment.strategy_artifact_id: UUID` (opaque) + `strategy_artifact_kind: StrategyArtifactKind` enum stored alongside. Resolver dispatches on kind.
- **Option β:** Keep `strategy_version_id` as the canonical name and store `kind` on the `strategies` table (one row per artifact, kind discriminator).

**Recommendation:** Option β. It preserves operator-facing naming and avoids a column rename mid-flight. The resolver uses the kind discriminator to pick the adapter.

**Migration impact.** The dual FKs on `Deployment` (`strategy_version_id` + `strategy_version_v4_id`) collapse to one. This is a schema change — see Section 11 risks.

---

### 4.3 FeatureEnginePort

**Purpose.** Single source for feature planning, warmup, hydration, batch and incremental computation, and snapshot emission.

**Accepts.** Feature requirements, symbol, timeframe, data policy, warmup policy, bars / stream events.

**Returns.** `FeatureSnapshot`, warmup status, missing-feature blockers, stale-data blockers.

**Must not.** Call brokers, submit orders, evaluate trade decisions, compute differently per consumer, allow React-side indicator math.

**Status.** Boundary already clean (Section 2.3). Port formalization = Protocol + lint gate. First adapter = `IncrementalFeatureEngine`.

**Rule.** ChartLab, runtime, SimLab, Backtest, Optimizer, Walk-Forward all use this same port. (Already true; this just locks it.)

---

### 4.4 MarketDataPort

**Purpose.** Normalize provider data access for bars (live + historical).

**Accepts.** Symbol(s), timeframe, date range, provider preference, data policy, live/historical request type.

**Returns.** Normalized bars, provider metadata, adjustment policy, freshness status, errors.

**Must not.** Compute indicators, emit SignalPlans, write broker truth, decide trades.

**Implementations.** Alpaca market data, Yahoo historical, future providers.

**Rule.** No direct provider calls from frontend or research services. (Mostly true today; needs lint gate.)

**Registry.** `MarketDataProviderRegistry` keyed by provider id; data policy + capability hints select the provider per request.

---

### 4.5 ResearchReplayPort

**Purpose.** One shared replay spine for backtest / sim / optimization / walk-forward.

**Accepts.** `DeploymentSnapshot`, data policy, run type, replay window, warmup policy.

**Returns.** `ResearchRunArtifact` with event log, feature snapshots, signal evaluations, simulated decisions, simulated fills (when applicable), metrics (when applicable).

**Must not.** Mutate the real Deployment, call real brokers, create hidden synthetic strategy components under real IDs, bypass `FeatureEnginePort` or `SignalSourcePort`.

**First adapter.** `HistoricalReplayEngine` (`simulation/historical_replay.py`), refactored to call `SignalSourcePort` instead of `SignalEngine.evaluate` directly.

**Rule.** Backtests / SimLab / Optimizer / Walk-Forward are **views over this spine**, not separate runtimes. The four research services become orchestrators of replay-window iteration + result aggregation; none of them owns signal-eval or feature-eval logic.

---

### 4.6 RiskResolverPort

**Purpose.** Convert `SignalPlan` + Account context (real or simulated) into final size and risk impact.

**Accepts.** `SignalPlan`, account context, RiskPlan, positions, buying power, restrictions.

**Returns.** Resolved quantity, notional, max loss, exposure impact, violations, warnings.

**Must not.** Submit orders, approve final trade, write broker truth, mutate positions.

**First adapter.** Existing `RiskResolverService` (`risk_resolver/service.py:85`).

**Rule.** Strategy + SignalPlan never carry final Account quantity. RiskResolver is the **first** place final sizing appears. (Already enforced today.)

---

### 4.7 GovernorPort

**Purpose.** Final internal protection gate before order creation.

**Accepts.** RiskResolver result, account state, sync freshness, deployment state, global kill state, restrictions, open orders, existing positions.

**Returns.** Approve / reject / block decision with reasons + violations + warnings + decision trace.

**Must not.** Submit orders, call broker directly, compute indicators, mutate broker truth.

**First adapter.** Existing `PortfolioGovernor` (`governor/service.py:10`).

**Rule.** **No order reaches `BrokerAdapterPort` without `GovernorPort` approval.** Protective-exit intents are pre-approved at the governor level (existing bypass; correct as designed).

---

### 4.8 OrderManagerPort

**Purpose.** Create internal orders from approved Governor decisions. Owns the order ledger.

**Accepts.** Approved Governor decision, SignalPlan lineage, ExecutionPlan, account_id, lifecycle intent.

**Returns.** `InternalOrder` with idempotency key + lineage fields.

**Must not.** Call market-data providers, write broker truth, bypass `BrokerAdapterPort`, bypass `BrokerSyncPort`.

**First adapter.** Existing `OrderManager` (`orders/manager.py:31`).

---

### 4.9 ExecutionPort / BrokerAdapterPort

**Purpose.** Submit, cancel, replace broker orders behind provider adapters.

**Accepts.** `InternalOrder`, broker capability preflight result, account credentials/mode.

**Returns.** Broker submission result, broker order id (if accepted), structured broker errors.

**Must not.** Create internal orders, decide risk, write final broker truth directly into persistence.

**Status.** Protocol already exists at `brokers/adapter.py:12`. Adapters: `AlpacaBrokerAdapter`, `FakeBrokerAdapter`. **Three concrete-import leaks identified** (Section 2.4) — these need port-only references in Phase 4.

**Rule.** Alpaca is **one adapter**, not the architecture. Future Tradier/IBKR/equities-options adapters slot into the registry without touching runtime.

---

### 4.10 BrokerSyncPort

**Purpose.** **Only writer of broker-derived truth.** Single source for orders/fills/positions/account snapshots.

**Accepts.** Broker events, REST reconciliation snapshots, fills, cancels, rejects, positions, account snapshots.

**Returns.** Canonical order / fill / position / account truth, freshness status, sync errors, lineage repair / adoption events.

**Must not.** Evaluate strategies, size trades, submit orders, compute indicators.

**First adapter.** Existing `BrokerSync` + `BrokerSyncService` (`brokers/sync.py`).

**Rule.** **Only `BrokerSyncPort` writes broker truth.** Lint gate enforces (Section 9).

---

### 4.11 AccountStatePort

**Purpose.** Provide canonical Account runtime state to runtime, risk, governor, and operations.

**Accepts.** `account_id`.

**Returns.** Account snapshot, positions, restrictions, open orders, sync freshness, pause/kill state, guardian assignment.

**Must not.** Write broker truth, submit orders, evaluate signals.

**First adapter.** Composition of `BrokerSyncService.fetch_account_snapshot` + `runtime_store.load_broker_account_snapshot` + Guardian state lookup.

**Why this port even when it has one impl.** Five+ consumers (orchestrator, governor, risk resolver, order manager, broker accounts service) read account state today via slightly different paths. Centralizing under a port makes the invariants explicit and catches drift via lint.

---

### 4.12 GuardianAssignmentPort

**Purpose.** Represent Guardian as an Account-scoped role assignment on a normal Deployment. Guardian is **not** a separate entity.

**Accepts.** `account_id`, `deployment_id`.

**Returns.** Guardian assignment state, adoption eligibility, adoption history.

**Rules (locked).**
- Guardian is **not** a separate entity. A Deployment can be Guardian for one Account and a regular Deployment for another.
- Guardian manages its own positions plus orphaned/unknown/bad-owner positions only **inside the checked Account**.
- Guardian does **not** manage healthy positions owned by other Deployments.
- Adoption appends lineage; never hides history.
- Adoption does not bypass Account Evaluation, RiskResolver, Governor, OrderManager, BrokerAdapter, or BrokerSync.

**First adapter.** Existing `BrokerAccount.guardian_deployment_id` + `apply_guardian_adoption` + `guardian_context_provider` wire site (Section 2.6). Already correct; just needs the formal port name.

---

### 4.13 NotificationPort

**Purpose.** Emit operator-visible events for UI toasts, Operations logs, audit trail.

**Accepts.** Domain event, severity, source, operator advisory, related ids.

**Returns.** Notification event + audit trail item.

**Must not.** Mutate trading state, hide failed actions.

**Rule.** No mission-critical action can silently succeed or fail.

**Sinks (registry).** UI toast bus, Operations event log, structured-logger sink, audit-trail sink. Mission-critical actions write to **all** sinks.

---

## 5. Caller Migration Map

For each major caller, the table shows what it imports today and what it imports after Phase 5. Source: code surveys (Section 2). This is the punch list for Phase 1–5 work tickets.

| Caller | Today imports | After migration imports |
|---|---|---|
| `pipeline/orchestrator.py` | `SignalEngine`, `SignalPlanBuilder`, `build_signal_plan_from_v4`, `parse_post_fill_pct`, `IncrementalFeatureEngine`, `FeatureHydrationService`, `AlpacaBrokerAdapter` (type) | `SignalSourcePort`, `StrategyArtifactResolver`, `FeatureEnginePort`, `BrokerAdapterPort`, shared utility module for `parse_post_fill_pct` |
| `chart_lab/preview_service.py` | `SignalEngine`, `IncrementalFeatureEngine`, `StrategyVersion` (legacy domain) | `SignalSourcePort`, `FeatureEnginePort`, `StrategyArtifactResolver` |
| `simulation/historical_replay.py` | `SignalEngine`, `SignalPlanBuilder`, `IncrementalFeatureEngine`, `StrategyVersion` | `SignalSourcePort`, `FeatureEnginePort`, `StrategyArtifactResolver`, shared utility module |
| `research/backtests/service.py` | `HistoricalReplayEngine`, `load_strategy_version()` | `ResearchReplayPort`, `StrategyArtifactResolver` |
| `research/sim_lab/service.py` | `HistoricalReplayEngine` | `ResearchReplayPort` |
| `research/walk_forward/service.py` | `HistoricalReplayEngine` (×2 instantiation sites) | `ResearchReplayPort` |
| `research/optimization/service.py` | `HistoricalReplayEngine` (via `replay_window`) | `ResearchReplayPort` |
| `runtime/runtime_context.py` | `AlpacaBrokerAdapter` (concrete, 4 sites) | `BrokerAdapterPort` + `BrokerAdapterRegistry` |
| `broker_accounts/service.py` | `AlpacaBrokerAdapter` (factory) | `BrokerAdapterPort` |
| `api/server.py` | `AccountScopedAlpacaBrokerAdapter` | `BrokerAdapterRegistry.scoped_for_account(...)` |
| `orders/protective_placer.py` | `parse_post_fill_pct` from `signal_plan_builder` | shared utility module |

**Net effect.** Three direct legacy-engine call sites (`orchestrator`, `chart_lab`, `historical_replay`) become one — they all go through `SignalSourcePort`. Three concrete-adapter import sites become zero.

---

## 6. Ownership Rules

1. **Domain contracts** (`SignalPlan`, `FeatureSnapshot`, `BrokerPositionSnapshot`, `RiskResolverResult`, `GovernorDecision`, `BrokerAccountSnapshot`) are stable Pydantic models in `backend/app/domain/` and `backend/app/governor/models.py` etc. Evolve by additive fields + version tag, never by suffixed type names.
2. **Application services** depend on **ports**, never on concrete adapters. Composition root (`runtime_context.py` + `api/server.py`) is the only place that instantiates concrete adapters.
3. **Adapters** implement ports; they may import domain contracts but never other adapters.
4. **Registries** only exist where multiple implementations are realistic. Each registry has explicit registration (no auto-discovery magic).
5. **Frontend** depends on the API contract only. Indicator math, signal evaluation, and trading logic never appear client-side.

---

## 7. Forbidden Dependencies

These are the lint gates that protect the architecture.

| # | Rule | Enforcement |
|---|---|---|
| F1 | `pipeline/`, `runtime/`, `research/`, `simulation/`, `chart_lab/` may not import `decision/signal_engine` or `decision/signal_plan_builder_v4` after Phase 1 | AST grep in test |
| F2 | `chart_lab/` may not import `risk_plan`, `execution_plan`, `strategy_controls`, `governor`, `risk_resolver`, `orders/manager` | AST grep |
| F3 | `frontend/src/` may not contain indicator math (RSI/EMA/ATR/BB/VWAP/Supertrend) functions | AST grep over .ts/.tsx |
| F4 | Research labs may not call `SignalEngine`/`SignalPlanBuilder` directly; must go through `ResearchReplayPort` | AST grep |
| F5 | Only `brokers/sync.py` may call `runtime_store.save_broker_*` methods | AST grep |
| F6 | `final_quantity` may only be assigned inside `risk_resolver/` | AST grep |
| F7 | `BrokerAdapter.*submit_order` reachable only after a `GovernorDecision.approved == True` | Runtime invariant test |
| F8 | Guardian adoption preserves prior lineage (`adoption_history` length monotonic) | Property test |
| F9 | No new field named `strategy_version_v5_id` or `*_v6_id` | AST grep |
| F10 | No new top-level `runtime/` entrypoint besides the existing one | Module-count test |

---

## 8. Registry / Resolver Design

Explicit registries only:

```python
# pseudocode — final shape decided in Phase 1 implementation
class SignalSourceRegistry:
    def register(self, kind: StrategyArtifactKind, factory: Callable[[ArtifactMetadata], SignalSourcePort]) -> None: ...
    def resolve(self, artifact_metadata: StrategyArtifactMetadata) -> SignalSourcePort: ...

class BrokerAdapterRegistry:
    def register(self, broker_id: str, factory: Callable[[BrokerCredentials], BrokerAdapterPort]) -> None: ...
    def resolve(self, account: BrokerAccount) -> BrokerAdapterPort: ...

class MarketDataProviderRegistry:
    def register(self, provider_id: str, factory: Callable[[ProviderConfig], MarketDataPort]) -> None: ...
    def resolve(self, request: MarketDataRequest) -> MarketDataPort: ...

class NotificationSinkRegistry:
    def register(self, sink_id: str, sink: NotificationSink) -> None: ...
    def fan_out(self, event: NotificationEvent) -> None: ...
```

**Where they live.** `backend/app/composition/registries.py` (new), instantiated once in `api/server.py` at boot, injected through `runtime_context`.

**No registries for:** RiskResolver, Governor, OrderManager, BrokerSync, AccountState, Guardian, FeatureEngine, ResearchReplay. These have one implementation today and one planned.

---

## 9. Migration Phases

Five phases. Each phase keeps tests green at HEAD; no half-deleted runtime ever exists.

### Phase 0 — This document

Architecture plan only. No code.

**Deliverable.** This file. Operator approval.

### Phase 1 — Signal boundary

The most leveraged phase. Survey shows it unblocks both ChartLab and the research suite.

**Steps.**
1. **S12a (extraction).** Move `parse_post_fill_pct` and any other shared utilities from `signal_plan_builder.py` into `decision/signal_plan_common.py`. Re-point 4 callers (`protective_placer.py`, `pipeline/orchestrator.py:1226,1227,1668`). Pure refactor, zero behavior change.
2. **Define `SignalSourcePort` Protocol** + `SignalEvaluationResult` domain shape in `backend/app/decision/ports.py`.
3. **Define `StrategyArtifactResolver`** in `backend/app/decision/strategy_artifact_resolver.py`. Reads `Deployment` → returns `(SignalSourcePort, ArtifactMetadata)`. Internal dispatch on artifact kind.
4. **Adapter: `V4ExpressionSignalSource`** wraps `build_signal_plan_from_v4` body. Adapter: `LegacyRuleSignalSource` wraps `SignalEngine.evaluate` body. Both are thin. Both register in `SignalSourceRegistry` at composition root.
5. **Migrate `pipeline/orchestrator.py`** to call `signal_source.evaluate(snapshot, contexts)` resolved from `StrategyArtifactResolver(deployment)`. Remove the runtime branch on `strategy_version_v4_id`.
6. **Migrate `chart_lab/preview_service.py`** to call `SignalSourcePort`. ChartLab gains v4 strategy support automatically.
7. **Migrate `simulation/historical_replay.py`** to call `SignalSourcePort`. Research labs gain v4 strategy support automatically.
8. **Lint gate F1, F4, F9** added.

**Test gates.** Backend unit baseline preserved (currently 2433). Integration test `test_v4_runtime_e2e.py` still green. New test: `chart_lab/preview` works with a v4 strategy.

**S12 readiness signal.** End of Phase 1, no caller imports `signal_engine` or `signal_plan_builder_v4` directly. **Now S12c is safe.** (See Section 13.)

### Phase 2 — ChartLab boundary

ChartLab as **pure verification surface**, not a half-runtime.

**Steps.**
1. ChartLab reads `FeatureEnginePort` + `SignalSourcePort` only. No `RiskPlan`, `ExecutionPlan`, `StrategyControls` requirements in ChartLab signal mode.
2. ChartLab supports **two modes**: (a) strategy mode (auto-derives feature plan from artifact), (b) feature exploration mode (no strategy required, just a feature ref list).
3. Warmup bars render distinctly (visual + flag in API payload).
4. Lint gate F2 added.

### Phase 3 — Research replay boundary

**Steps.**
1. Define `ResearchReplayPort` Protocol. First adapter: refactored `HistoricalReplayEngine`.
2. Migrate `research/backtests/service.py`, `research/sim_lab/service.py`, `research/walk_forward/service.py`, `research/optimization/service.py` to call `ResearchReplayPort.replay(deployment_snapshot, window, run_type)`. Each lab keeps its own result-aggregation logic; none owns evaluation logic.
3. `DeploymentSnapshot` becomes the only research input. No hidden synthetic strategies under real IDs.
4. Lint gate F4 (already added Phase 1, re-asserted) + a property test that no research code path can mutate a real `Deployment`.

### Phase 4 — Broker + account boundaries

**Steps.**
1. Replace concrete `AlpacaBrokerAdapter` imports in `runtime_context.py` (4 sites), `broker_accounts/service.py:77`, `api/server.py:260` with `BrokerAdapterPort` references resolved from `BrokerAdapterRegistry`.
2. Define `AccountStatePort` Protocol; first adapter aggregates `BrokerSyncService.fetch_account_snapshot` + Guardian state. Migrate orchestrator/governor/risk-resolver/order-manager reads.
3. Define `GuardianAssignmentPort` (rename + formalize existing helpers).
4. Lint gates F5, F6, F7 added.

### Phase 5 — Legacy deletion (S12 proper)

**Steps.**
1. Delete `LegacyRuleSignalSource` adapter (no callers remain after Phase 1).
2. Delete `decision/signal_engine.py`, `decision/signal_plan_builder.py` (utilities already moved in Phase 1's S12a).
3. Delete `backend/app/strategies/` legacy package (excluding `expression_engine/` which v4 uses).
4. Delete `domain/strategy.py` legacy `StrategyVersion` / `SignalRule` / `ConditionNode` / `LogicalExitRule`.
5. Schema migration: drop `Deployment.strategy_version_id` column; rename `strategy_version_v4_id` to `strategy_version_id` (now unambiguous). Add `strategies.kind` discriminator.
6. Test surgery on the 5 mixed test files from S12 survey.
7. Final lint sweep: confirm no `_v4` / `_legacy` / `v5` strings remain in caller code.

---

## 10. Tests & Lint Gates

Concrete test definitions for each forbidden-dependency rule.

| Gate | Test file (proposed) | Mechanism |
|---|---|---|
| F1 — runtime imports concrete signal engine | `backend/tests/unit/lint/test_no_concrete_signal_imports.py` | AST walk over `pipeline/`, `runtime/`, `research/`, `simulation/`, `chart_lab/` rejecting `signal_engine` / `signal_plan_builder_v4` import strings |
| F2 — ChartLab references trading concepts | `backend/tests/unit/lint/test_chart_lab_isolation.py` | AST walk over `chart_lab/` rejecting risk/execution/governor imports |
| F3 — frontend indicator math | `frontend/scripts/lint-no-indicator-math.ts` (vitest or eslint plugin) | AST/regex over `frontend/src/` rejecting indicator function bodies |
| F4 — research bypasses port | `backend/tests/unit/lint/test_research_replay_port_only.py` | AST walk over `research/` |
| F5 — broker truth single writer | `backend/tests/unit/lint/test_broker_truth_writer.py` | grep `save_broker_*` callers; assert all in `brokers/sync.py` |
| F6 — final_quantity assignment site | `backend/tests/unit/lint/test_quantity_resolver_only.py` | AST walk for `final_quantity =` assignments outside `risk_resolver/` |
| F7 — Governor required before broker submit | runtime invariant test in `pipeline/` test suite | Test that `BrokerAdapter.submit_order` is unreachable from a path that didn't pass through `GovernorPort.evaluate` (decision trace assertion) |
| F8 — Guardian one-way adoption | property test in `brokers/test_guardian_adoption_pathway.py` | Already exists; extend to assert `adoption_history` is monotonic |
| F9 — no `_v5_id` field naming leak | `backend/tests/unit/lint/test_no_version_suffix_fields.py` | grep model definitions for `*_v\d+_id` patterns |
| F10 — no new runtime entrypoint | `backend/tests/unit/lint/test_single_runtime_entrypoint.py` | Module-count assertion |

**Existing test count.** 2433 backend unit + 3 v4 integration + ~424 frontend vitest. New gates net-add ~20 tests. Baseline is preserved through every phase.

---

## 11. What Not To Abstract

Important — over-abstraction is its own problem.

- **No abstraction for simple data DTOs.** `SignalPlan`, `BrokerPositionSnapshot`, etc. are data shapes. Hide behind a port and you still have to migrate every reader when the shape changes.
- **No abstraction for CRUD services.** `WatchlistService`, `RiskPlanService`, `ExecutionPlanService` — these read/write rows. No alternate implementation makes sense.
- **No event bus / Kafka / pub-sub fabric.** Modular monolith only. The four registries above are dispatch tables, not message buses.
- **No `BaseService` inheritance.** Composition over inheritance.
- **No `EngineManager` / `ServiceCenter` / `Coordinator` product concepts.** These hide domain language. Names must be specific.
- **No microservices.** Out of scope.

---

## 12. Risks & Trade-offs

| # | Risk | Mitigation |
|---|---|---|
| R1 | Phase 1 transient state has 3 things in the spine (legacy adapter, v4 adapter, port). Brief but real. | Phase 1 scoped tightly. Adapters are thin wrappers. End-of-Phase-1 lint gate F1 enforces zero direct concrete imports — measurable signal that we're done. |
| R2 | Schema migration in Phase 5 (drop `strategy_version_id`, rename `strategy_version_v4_id`) is irreversible on prod. | Phase 5 includes explicit migration script + rollback plan. Operator must approve before running. Local SQLite dev DBs: documented "wipe before pulling Phase 5." |
| R3 | `StrategyArtifactResolver` is a new dispatch boundary. If the artifact's `kind` is unknown, fail-closed is mandatory (no fallback to legacy after Phase 5). | Resolver raises `UnsupportedStrategyArtifact` on unknown kind. No silent default. |
| R4 | `AccountStatePort` consolidation could mask a stale snapshot if cache layer is misconfigured. | Port carries explicit `freshness` field; consumers decide tolerance. Existing freshness invariants (BrokerSync REST cadence) remain authoritative. |
| R5 | Lint gates can become drag if too aggressive. | Each gate has a specific failure message + the policy reference. CI only; not a pre-commit hook. |
| R6 | Ports designed in a vacuum can be wrong-shaped. | Phase 1's `SignalSourcePort` is grounded in two real implementations from day one (legacy + v4). The other ports formalize boundaries that already exist in code. We do not design ports for hypothetical second consumers. |
| R7 | Codex's research lease (active 2026-05-02 12:45 → 17:06) overlaps Phase 2 + Phase 3 territory. | Per operator directive: this plan is owned by the architect. Phase 2/3 sequencing post-Codex-release is a coordination concern, not an architecture concern. Plan stays whole. |

---

## 13. Final S12 Recommendation

The operator asked for a reasoned recommendation between three options:

**A.** Delete first, abstraction later.
**B.** Abstraction first, delete later.
**C.** Hybrid: introduce SignalSourcePort during S12 migration.

### Survey-grounded reasoning

The signal-boundary survey (Section 2.1) revealed something I did not assume going in: **legacy `SignalEngine` is the only signal engine ChartLab and the entire research suite use today.** V4 is live-runtime-only.

That single fact disqualifies **Option A**. Deleting `signal_engine.py` and `signal_plan_builder.py` today breaks `chart_lab/preview_service.py:301`, `simulation/historical_replay.py:972`, plus all four research lab services that delegate through historical replay. There is no `SignalSourcePort` to make v4 fill the gap. ChartLab and Backtests + SimLab + WalkForward + Optimization would all fail at import.

**Option C (hybrid)** sounds attractive but in practice has the same problem. You cannot delete legacy code paths *during* a port migration without crossing a window where some callers go through the port and others go through the legacy directly. That window must close cleanly before any deletion. So the "hybrid" reduces to "abstraction first, delete second" — which is Option B.

**Option B (abstraction first)** is correct, and is what this plan describes. Phase 1 (`SignalSourcePort`) extends v4 to cover ChartLab + research surfaces by registration. Phase 5 then deletes legacy because nothing imports it anymore. The deletion becomes mechanical: the lint gates from Phase 1 already prove no caller depends on the legacy path.

### One nuance worth naming

There is a worthy variation on B: do Phase 1 *as the body of S12 itself*, rebranded. That is, S12 stops being "delete legacy" and becomes "introduce `SignalSourcePort`, route everything through it, then delete legacy at the tail of the same slice." This is the operator's instinct — and I agree with it. It collapses two slices into one, reduces calendar time, and keeps the abstraction work tied to a clear deliverable instead of floating as a "we should do this someday" plan.

### Recommendation

**Execute Phase 1 as the new shape of S12.** Not "S12 then ports later." Not "ports then S12." S12 *is* port introduction + caller migration + legacy deletion in that order, all inside one well-scoped slice with phase-internal commit checkpoints.

Specifically:
- **S12.1** — Phase 1 step 1 (utility extraction). Pure refactor.
- **S12.2** — Phase 1 steps 2–4 (port + resolver + two adapters).
- **S12.3** — Phase 1 steps 5–7 (migrate orchestrator + chart_lab + historical_replay).
- **S12.4** — Phase 1 step 8 (lint gates).
- **S12.5** — Phase 5 (legacy deletion + schema migration + test surgery).

Phases 2, 3, 4 from this plan become **separate follow-on slices**. They are valuable but not on the S12 critical path. Sequencing them after S12 means each is a 1–2 day cleanup against a known-good baseline rather than a multi-week reshape.

---

## 14. Open Questions

1. **Schema field name.** Stick with `strategy_version_id` (Option β, Section 4.2) and add a `kind` discriminator on the `strategies` table — or rename to `strategy_artifact_id`? Recommendation: Option β.
2. **`StrategyArtifactKind` enum.** What values does it take initially? Proposal: `EXPRESSION_V1` (today's "v4"), with future values `EXPRESSION_RUST_V1`, `LLM_SIGNAL_V1`. Note the absence of "v4" / "v5" — these are engine *kinds*, not version numbers.
3. **Schema migration vehicle.** SQLite migrations today are ad-hoc (`CREATE TABLE IF NOT EXISTS`). Should Phase 5 introduce Alembic, or stay ad-hoc with explicit column-add scripts?
4. **Frontend lint gate F3.** Should it be eslint plugin or a vitest unit test? Trade-off: eslint catches at edit-time but adds dev dependency.
5. **Notification sinks scope.** Does Operations event log need to be a sink in this round, or can it stay direct-write? Affects Phase 4 scope.

---

## 15. Approval Checklist

The operator approves this plan if and only if:

- [ ] The thirteen ports listed in Section 3 are the right thirteen.
- [ ] The S12 recommendation in Section 13 (Phase 1 = new S12 shape) is accepted, OR a counter-recommendation is given with reasons.
- [ ] The `StrategyArtifactResolver` field-naming decision is made (Section 4.2 / Open Q1).
- [ ] The schema migration vehicle question (Open Q3) is resolved before Phase 5 starts.
- [ ] The lint-gate enforcement mechanism (CI test, not pre-commit) is acceptable.
- [ ] No registry is added that this plan does not list. New registries require a written justification.

Once approved, Phase 1 starts as `S12.1` (utility extraction) and proceeds slice-by-slice. Each S12.x step ends with backend unit + frontend vitest both green at HEAD.

---

*End of plan. No code changes in this slice.*
