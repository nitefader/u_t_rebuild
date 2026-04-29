# Backend Reality Map

Last updated: 2026-04-26 19:55:00 -04:00

Operation: Turtle Shell

Phase: Phase 0: Repo Reality Check

Work session status: in_progress

Owner: Coordinator

Reviewers:

- Angry Architect
- Full Stack Developer
- Alpaca Agent
- Alpaca Order Compliance Agent
- Broker Error And Advisory Agent
- Market Rules And Session Agent
- Product Manager

## Purpose

This map records what exists in the backend before implementation begins.

No implementation is approved until this map is accepted by the Coordinator and
Angry Architect.

## Coordinator Verdict

The backend has strong functional boundaries, but it is not yet wired around the
locked SignalPlan doctrine.

Phase 0 verdict:

```text
Does not pass backend ship gate.
Passes reality-map gate as an honest baseline.
```

Keep the strongest boundaries:

- Feature Engine
- Signal Engine
- BrokerAdapter
- BrokerSync
- Order Ledger
- Broker Account service
- Market Data Provider layer
- Operations read model
- Chart Lab and Sim Lab foundations

Refactor the live spine:

- replace active `ExecutionIntent` spine with `SignalPlan`
- move Account-specific final quantity into Account Evaluation / RiskResolver
- preserve Governor as the final Account protection gate
- replace `program_id` lineage with Strategy / Deployment / SignalPlan lineage
- keep `BrokerAccount` as backend alias for product `Account`

## Doctrine Flow

Target backend flow:

```text
Strategy
-> Watchlist
-> Deployment
-> SignalPlan
-> Account Evaluation
-> RiskResolver
-> Governor
-> Order Ledger
-> BrokerAdapter
-> BrokerSync
-> Position Truth
-> Operations Center
```

Research support flow:

```text
Chart Lab
-> Backtest / Sim Lab
-> Optimization
-> Walk-Forward
-> Promotion Evidence
-> Deployment
-> SignalPlan
```

## Module Reality Table

| Doctrine Area | Current Backend Modules | Current Responsibility | Risk | Recommended Action |
|---|---|---|---|---|
| Strategy | `backend/app/domain/strategy.py`, `strategy_controls.py`, `execution_style.py`, `risk_profile.py` | Strategy-like logic is split across component schemas. | Medium | Keep, then consolidate doctrine-facing Strategy contract. |
| Watchlist | `backend/app/domain/universe.py` | Universe snapshot/symbol source. | Medium | Rename-alias to Watchlist, then refactor into Watchlist/WatchlistSnapshot. |
| Deployment | `backend/app/runtime/models.py`, `runtime/account_trading_orchestrator.py`, `runtime/account_trading_supervisor.py`, `pipeline/orchestrator.py` | Runtime execution and Account trading orchestration on the shared runtime path. | High | Keep one runtime path. Deployment must publish SignalPlans once to subscribed Accounts. |
| SignalPlan | No explicit module. Closest: `domain/strategy.py::CandidateTradeIntent`, `runtime/models.py::ExecutionIntent`. | Current signal/execution candidate path. | Critical | Add canonical SignalPlan contracts. `ExecutionIntent` is not neutral because it carries quantity and Governor fields. |
| Account | `backend/app/broker_accounts/*` | Broker Account creation, provider/mode metadata, credentials, validation. | Low | Keep. Product label is Account; backend `BrokerAccount` alias is allowed. |
| Account Evaluation | Distributed across `broker_accounts/*`, `control_plane/service.py`, `governor/*`, `orders/manager.py`. | Participation, risk, pause, sync freshness, and order gates are scattered. | High | Add explicit AccountSignalPlanEvaluation contract. |
| RiskResolver | No explicit module. Closest: `runtime/engine.py::ExecutionIntentBuilder._size_from_components`, `domain/risk_profile.py`, `governor/service.py`. | Sizing partly happens before Governor. | Critical | Add explicit RiskResolver. Final size belongs to Account decision path. |
| Governor | `backend/app/governor/models.py`, `governor/service.py` | Final protective gate, currently named `PortfolioGovernor`. | Medium | Keep behavior. Rename-alias to Governor where product-facing. |
| Order Ledger | `backend/app/orders/models.py`, `orders/ledger.py`, `orders/manager.py`, `orders/trade_ledger.py` | Internal orders, idempotency, cancel/replace, manual order support. | Medium | Keep/refactor lineage from `program_id` to SignalPlan lineage. |
| BrokerAdapter | `backend/app/brokers/adapter.py`, `brokers/alpaca.py`, `brokers/fake.py` | Broker submit/cancel/read boundary. | Low | Keep. Add capability/preflight adapter support. |
| BrokerSync | `backend/app/brokers/sync.py`, `brokers/stream.py` | Broker truth writer and stream event router. | Low | Keep. Ensure all broker truth stays here. |
| Position Truth | `brokers/models.py::BrokerPositionSnapshot`, `brokers/sync.py`, `persistence/runtime_store.py`, `operations/service.py` | Broker snapshot position truth exists. | High | Refactor into Account-owned Position truth with SignalPlan lineage and explanation context. |
| Operations Center | `backend/app/operations/*`, `api/routes/operations.py`, `api/routes/operations_trade_stream.py`, `runtime/runtime_context.py` | Runtime state projection and operator visibility. | Medium | Keep. Rename old fields and add SignalPlan/stream status contracts. |
| Feature Engine | `backend/app/features/*` | Feature identity, parsing, planning, batch/incremental computation. | Low | Keep. Ensure all modes use it. |
| Signal Engine | `backend/app/decision/signal_engine.py` | Produces candidate signal decisions from features. | Medium | Keep/rename-alias. Route output into SignalPlan builder. |
| Market Data Providers | `backend/app/market_data/*` | Provider catalog, resolver, adapters, stream hub, pipeline registry. | Medium | Keep. Enforce one shared Live Stock Market Data Stream. |
| Account Trade Sync | `backend/app/runtime/runtime_context.py`, `backend/app/brokers/stream.py`, `backend/app/brokers/sync.py` | Per-account trade stream dispatcher and BrokerSync routing. | Medium | Keep/refactor naming to Account Trade Sync; ensure validated Account starts one stream. |
| Chart Lab | `backend/app/chart_lab/*`, `api/routes/chart_lab.py` | Signal/feature preview. | Medium | Keep. Ensure no order creation and use shared computation contracts. |
| Sim Lab / Backtest | `backend/app/simulation/*` | Deterministic replay with simulated orders/fills/positions. | Medium | Keep. Align result contracts to Strategy evidence and SignalPlan path. |
| Optimization / Walk-Forward | Mostly `backend/app/promotion/*` evidence references, no full engine found. | Promotion checks for evidence presence. | High | Add explicit run/evidence contracts later. Do not fake engines. |
| Promotion | `backend/app/promotion/*` | Readiness gate using simulation/paper/evidence/broker sync. | High | Keep logic, refactor old Program/Paper naming into Strategy readiness evidence. |
| AI Providers | `backend/app/ai/*` | Provider catalog/runtime/validation. | Low | Keep. AI advisory only. |
| Persistence | `backend/app/persistence/*` | Durable runtime storage for orders, sync, governor state, accounts. | Medium | Keep. Add SignalPlan lineage, Account evaluation trace, Position explanation context. |

## Old Names Still Active

| Old Name | Where Active | Risk | Target |
|---|---|---|---|
| `ProgramVersion` | `backend/app/domain/program.py`, `runtime/models.py`, `features/planner.py`, `promotion/*`, tests | High | Strategy version/config compatibility name only, then refactor. |
| `program_id`, `program_version_id` | `orders/models.py`, `orders/manager.py`, `operations/models.py`, `persistence/runtime_store.py`, tests | High | Strategy id plus SignalPlan lineage. |
| `ResolvedProgramComponents` | `features/planner.py`, `runtime/*`, `simulation/*`, `chart_lab/*`, tests | High | Resolved Strategy components / StrategyConfigBundle. |
| `ExecutionIntent` | `runtime/models.py`, `runtime/engine.py`, `orders/manager.py`, tests | Critical | Replace with SignalPlan plus AccountEvaluation/RiskResolver result. |
| `CandidateTradeIntent` | `domain/strategy.py`, `decision/signal_engine.py` | Medium | Signal candidate feeding SignalPlan builder. |
| `UniverseSnapshot` | `domain/universe.py`, feature tests | Medium | WatchlistSnapshot. |
| `PortfolioGovernor` | `governor/service.py`, tests | Medium | Governor. |
| `BrokerRuntime*` migration shims | `runtime/account_trading_orchestrator.py`, `runtime/account_trading_supervisor.py`, tests | High | Account trading runtime shims only; do not create paper/live runtime roots. |
| `PaperRunEvidence` | `promotion/models.py`, tests | Medium | Account-mode evidence. Paper is Account metadata. |
| `Market Data Service` | `market_data/resolver.py`, `api/routes/chart_lab.py`, comments/tests | Medium | Market Data Provider. |

## Severe Gate Findings

### 1. `Program` Is Structural

Finding:

`ProgramVersion`, `program_id`, `program_version_id`, `OrderOrigin.PROGRAM`,
persistence indexes, governor projections, operations summaries, promotion
gates, and client order ids still encode the old concept.

Key files:

- `backend/app/domain/program.py`
- `backend/app/runtime/models.py`
- `backend/app/orders/models.py`
- `backend/app/persistence/models.py`

Gate:

```text
Active runtime lineage must become Strategy -> Deployment -> SignalPlan ->
Account Order. Add a lint gate banning Program lineage outside explicit
migration shims.
```

### 2. Paper/Live Runtime Split Removed From Active Path

Finding:

The active account trading path now loads account-backed deployments without
forking paper and live into separate runtime roots. Paper/live remain Account
metadata, and live order submission still requires explicit enablement and
promotion gates.

Key files:

- `backend/app/runtime/account_trading_orchestrator.py`
- `backend/app/runtime/account_trading_supervisor.py`

Gate:

```text
Replace paper-only runtime loading and preflight with Account-mode-derived
adapter behavior. One runtime loop must accept paper/live by Account metadata.
```

### 3. SignalPlan Is Absent

Finding:

The executable path jumps from `CandidateTradeIntent` to `ExecutionIntent`.
`ExecutionIntent` includes final quantity and Governor fields, so it is not a
neutral SignalPlan.

Key files:

- `backend/app/runtime/models.py`
- `backend/app/runtime/engine.py`
- `backend/app/pipeline/orchestrator.py`

Gate:

```text
Add explicit SignalPlan contracts before more order/runtime work.
```

### 4. Duplicate Runtime Roots Exist

Finding:

Runtime authority is spread across:

- `RuntimeEngine`
- `RuntimeOrchestrator`
- `BrokerRuntimeOrchestrator`
- `BrokerRuntimeSupervisor`
- manual-trade composition registries

Gate:

```text
Choose one runtime composition root. Other runtime modules must become pure
components, adapters, or test harnesses.
```

### 5. Market Data Stream Doctrine Is Not Locked In Code

Finding:

Code still permits market data stream identity by provider, trading mode, and
data feed. This can create duplicate streams by broker mode.

Key files:

- `backend/app/runtime/runtime_context.py`
- `backend/app/market_data/pipeline.py`
- `backend/app/market_data/stream_hub.py`

Gate:

```text
Remove trading mode from live stock stream identity. One selected Live Stock
Market Data Stream must serve all stock consumers.
```

### 6. Services Naming Remains

Finding:

Public/backend market data contracts still expose service naming.

Key files:

- `backend/app/api/routes/market_data.py`
- `backend/app/market_data/models.py`
- `backend/app/market_data/catalog.py`

Gate:

```text
Rename public/backend contracts to MarketDataProvider*. Legacy aliases may
exist only as migration wrappers.
```

### 7. Broker Truth Leaks Outside BrokerSync

Finding:

Some paths fetch or apply broker truth outside the ideal BrokerSync boundary.

Key files:

- `backend/app/orders/manager.py`
- `backend/app/runtime/recovery_orchestrator.py`
- `backend/app/api/routes/manual_trade.py`

Gate:

```text
Routes and OrderManager should call application services. Only BrokerSync
writes/reconciles broker-derived truth.
```

### 8. Multi-Leg Position Lifecycle Is Under-Modeled

Finding:

The backend has order intents for open/close/tp/sl/scale, but no SignalPlan
lineage, no Position explanation context, and no explicit runner/breakeven/
trailing/logical-exit lifecycle contract.

Key files:

- `backend/app/orders/models.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/app/governor/service.py`

Gate:

```text
Block multi-leg runtime until related SignalPlan handling exists for reduce,
partial close, target, stop, trail, breakeven, runner, and logical_exit.
```

## Alpaca And Broker Findings

### Current Strengths

- BrokerAdapter accepts `InternalOrder` and does not create internal orders.
- `InternalOrder` rejects broker fields such as `broker_order_id`,
  `filled_avg_price`, and `broker_status`.
- Account onboarding validates account snapshot, positions, and open orders,
  then persists broker truth through BrokerSync.
- Credential replacement marks broker sync stale with
  `credentials_replaced_requires_broker_sync`.

### Current Gaps

1. Alpaca order support is market-only and fail-closed.
   - `backend/app/brokers/alpaca.py`
   - `InternalOrder` carries `limit_price`, `stop_price`, `order_class`, and
     `extended_hours`, but adapter request translation does not fully support
     them.

2. TIF/order-class compliance is missing.
   - Domain supports broad order types and TIFs.
   - Alpaca adapter only executes market orders and forwards TIF generically.

3. Fill-to-trade attribution is weak.
   - `BrokerSyncService.handle_fill_update()` does not resolve internal
     `order_id` by `client_order_id` before recording fills.

4. Reconcile freshness timing is suspect.
   - `reconcile()` computes sync status before recording successful poll time.

5. Trade stream startup is split.
   - FastAPI startup starts a process dispatcher.
   - Broker runtime entrypoint creates a separate stream when broker-paper
     deployments exist.

6. Process trade dispatcher does not route through BrokerSync first.
   - It fan-outs to subscribers but does not attach `BrokerStreamRouter` /
     `BrokerSyncService`.

7. Manual trade route flow is mostly correct, but private wiring exists.
   - `runtime_context.register_account_in_manual_trade_registry()` assigns
     `order_manager._broker_sync` directly.

8. Runtime entrypoint chooses one primary Alpaca Account even when deployments
   may span Accounts.

### Alpaca Gate

```text
Create provider-specific BrokerCapabilityMatrix and MarketRulePreflight before
expanding Alpaca order support. Unify Account Trade Sync so one stream per
Account routes broker events through BrokerSync, then fans out to subscribers.
```

## Research And Computation Findings

### Unified Today

- `backend/app/features/planner.py` defines shared consumers for runtime, paper,
  chart_lab, sim_replay, backtest, optimization, and walk_forward.
- `BatchFeatureEngine` is used by Chart Lab and historical Sim Lab.
- `IncrementalFeatureEngine` is used by runtime paths.
- Both engines share registry/spec/key/frame contracts.
- `backend/app/decision/signal_engine.py` evaluates `FeatureSnapshot` values and
  emits candidate trade intents.
- Chart Lab preview uses `BatchFeatureEngine` plus `SignalEngine`.
- Sim Lab historical replay uses `BatchFeatureEngine` plus `SignalEngine`.

### Missing Or Weak

- No backend `backtest` module exists.
- No backend `optimization` module exists.
- No backend `walk_forward` module exists.
- Promotion consumes supplied evidence but does not create, persist, fetch, or
  verify evidence itself.
- Sim Lab replay creates `SimulationSession` with default `GovernorMode.OFF`,
  while promotion requires enforced simulation evidence.
- Optimization and Walk-Forward evidence are warnings only.

### Research Gate

```text
Add evidence contracts before promising readiness: ChartLabPreviewEvidence,
BacktestRun, SimulationRunEvidence, OptimizationRun, WalkForwardRun, and
PromotionEvidenceBundle.
```

## Keep

These modules are useful foundations and should not be rewritten blindly:

- `backend/app/features/*`
- `backend/app/decision/signal_engine.py`
- `backend/app/brokers/adapter.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/sync.py`
- `backend/app/brokers/stream.py`
- `backend/app/orders/*`
- `backend/app/broker_accounts/*`
- `backend/app/market_data/*`
- `backend/app/operations/*`
- `backend/app/ai/*`
- `backend/app/persistence/*`

## Refactor First

These are the critical refactor targets:

1. `backend/app/runtime/models.py`
   - Add SignalPlan / AccountEvaluation contracts.
   - Stop treating `ExecutionIntent` as the central runtime object.

2. `backend/app/runtime/engine.py`
   - Convert signal output into neutral SignalPlan.
   - Move final Account quantity out of Strategy-side runtime intent.

3. `backend/app/pipeline/orchestrator.py`
   - Reconcile current pipeline execution with SignalPlan publication.
   - Ensure one Deployment can publish to many Accounts.

4. `backend/app/orders/models.py`
   - Add SignalPlan lineage and Position lineage.
   - Preserve manual operator order path.

5. `backend/app/orders/manager.py`
   - Accept approved Account Evaluation / Governor result instead of raw
     `ExecutionIntent`.
   - Preserve BrokerSync stale gate.

6. `backend/app/governor/*`
   - Keep protective logic.
   - Rename-facing contract to Governor.
   - Add full SignalPlan lifecycle evaluation, including close/reduce/target/
     stop/trail/breakeven/runner/logical_exit.

7. `backend/app/runtime/runtime_context.py`
   - Enforce one shared Live Stock Market Data Stream.
   - Enforce one Account Trade Sync per validated Alpaca Account.
   - Rename comments/status language away from Broker Trade Update Stream where
     operator-facing.

8. `backend/app/promotion/*`
   - Keep readiness logic.
   - Refactor Program/Paper product language into Strategy readiness and Account
     mode evidence.

## Do Not Touch In Phase 0

Do not rewrite these during the reality-map phase:

- broker submission implementation
- BrokerSync reconciliation internals
- feature computation internals
- AI provider runtime
- persistence migrations
- frontend files

## Phase 0 Open Findings

All specialist Phase 0 findings merged:

- Full Stack Developer Backend Reality Map
- Angry Architect architecture violation audit
- Research and Computation alignment audit
- Alpaca boundary and order capability audit

## Phase 0 Gate Status

Status: ready for Coordinator gate decision

Blocking backend ship: yes

Blocking Phase 1 contract work: no

Next action:

```text
Accept this map as the Phase 0 baseline, then begin Phase 1 Core Domain
Contract Lock.
```
