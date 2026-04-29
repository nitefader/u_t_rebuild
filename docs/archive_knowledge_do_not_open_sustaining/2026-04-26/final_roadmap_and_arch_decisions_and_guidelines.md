# Final Roadmap, Architecture Decisions, and Agent Guidelines

## Purpose

This document locks the current backend architecture decisions for the Trading Operating System and gives the agent a clear execution contract.

**Latest product model override:** `Simplified Runtime Architecture and Guiding Principles.md`
is now the first authority for the V1 product model. It overrides older
Program-centric language in this document where they conflict:

- no user-facing `Program` entity in V1
- `Deployment` is a running Strategy publisher, not one Strategy on one Account
- `Deployment` emits account-neutral `SignalPlan`s
- `Account` subscribes to Deployments and independently accepts, rejects, sizes, or ignores each SignalPlan
- `Account` owns risk config and paper/live broker execution mode
- Orders and Trades are account-specific and link back to SignalPlan and Deployment
- if an Account accepts an opening SignalPlan, it must continue processing related close/reduce/scale-out/stop/target/logical-exit SignalPlans from that Deployment for the resulting position
- account-owned positions must be explainable from signal lineage, decision trace, Governor approval, orders, fills, current risk, and related close/reduce signals

This document remains binding for phase order, resolver contract, stop
conditions, validation discipline, logging format, and default engineering
choices where those do not conflict with the simplified model.

The goal is to prevent architecture drift while moving toward a production-grade trading platform with:

- shared market data
- isolated broker-account risk
- feature-driven data demand
- reusable simulation and runtime execution models
- deterministic behavior across Chart Lab, Sim Lab, Backtest, Live Preview, Broker Runtime - Paper, and future Broker Runtime - Live

---

## Final Architecture Principle

```text
Features drive demand.
Pipelines deliver data.
Accounts isolate risk.
Governors approve trades.
BrokerSync writes broker truth.
```

The system must remain simple, scoped, and production-safe.

---

# 1. Final Naming Decisions

## BrokerAccount

Use `BrokerAccount`.

Each BrokerAccount represents one unique broker account / API key set.

A BrokerAccount owns:

- API keys / broker credentials
- paper or live broker mode
- balances
- buying power
- broker positions
- broker orders
- fills
- broker restrictions
- broker sync freshness

Do not introduce these layers right now:

- `BrokerConnection`
- `BrokerSubAccount`

Those are not needed for the current reality because each account has its own API keys and should be treated as a distinct BrokerAccount.

Example:

```text
Alpaca Paper Account 1
Alpaca Paper Account 2
Alpaca Paper Account 3
Alpaca Live Account 1
```

Each is a separate BrokerAccount.

---

## MarketDataPipeline

Use `MarketDataPipeline` for reusable market-data streams.

A MarketDataPipeline owns:

- provider selection
- streaming subscription
- symbol demand deduplication
- consumer tracking
- market-data freshness
- normalized bar delivery

A MarketDataPipeline may feed many BrokerAccounts and many Deployments.

Example:

```text
Alpaca Premium MarketDataPipeline
  -> feeds Deployment A on BrokerAccount 1
  -> feeds Deployment B on BrokerAccount 2
  -> feeds Deployment C on BrokerAccount 3
```

Important rule:

```text
One paid stream can serve many accounts.
Do not open duplicate streams per account.
```

---

## Deployment

A Deployment is a running instance of a Program on one BrokerAccount.

A Deployment owns:

- runtime lifecycle
- selected Program
- selected BrokerAccount
- feature plan reference
- runtime health
- stream freshness dependency
- broker sync dependency

A Deployment does not own:

- broker credentials
- broker truth
- market-data stream ownership
- feature computation logic
- portfolio approval authority

A Deployment declares demand. It does not directly subscribe to providers.

---

## PortfolioGovernor

Keep the name `PortfolioGovernor`.

Do not rename it to:

- Account Manager
- Account Governor
- Broker Manager
- Risk Manager

The PortfolioGovernor is the final internal approval gate before a new trade can open.

It checks:

- exposure
- concentration
- open risk
- pending open risk
- symbol conflicts
- stale broker sync
- account pause
- deployment pause
- global kill
- risk limits

Correct model:

```text
One PortfolioGovernor per BrokerAccount or account-level portfolio scope.
```

Do not use one global PortfolioGovernor for all accounts.

Global kill is separate and belongs to the Control Plane.

---

# 2. Final Data Flow Decision

## Feature-Driven Data Demand

The better architecture is:

```text
Deployment declares Program feature demand
Feature Planner derives data requirements
Resolver selects the right pipeline
Pipeline subscribes/fetches data
Feature Engine computes features
Signal Engine evaluates decisions
```

The Feature Engine ecosystem drives demand, but the Feature Engine itself must not subscribe to external providers.

Correct ownership:

```text
Feature Planner
  -> determines required data inputs

Resolver
  -> chooses provider / pipeline

MarketDataPipeline
  -> subscribes, fetches, normalizes, fans out data

Feature Engine
  -> computes feature values

Signal Engine
  -> evaluates strategy logic
```

Hard rule:

```text
Feature Engine must never call Alpaca, Yahoo, news APIs, or any external provider.
```

---

# 3. Streaming Architecture

## Streaming is Pipeline-Owned, Demand-Driven

The streaming service should not be account-owned or deployment-owned.

Correct model:

```text
Deployment says what it needs.
Feature Planner turns that into data requirements.
Resolver selects the pipeline.
MarketDataPipeline owns the subscription.
BarBuilder builds derived timeframes.
Feature Engine computes features.
Deployment consumes only the relevant snapshots.
```

Accounts own money and broker truth.
Deployments own demand.
Pipelines own streams.
Feature Engine owns computed facts.

---

## No Naive Streaming

Do not do this:

```text
BrokerAccount A -> stream SPY
BrokerAccount B -> stream SPY
BrokerAccount C -> stream SPY
```

Do this:

```text
MarketDataPipeline -> stream SPY once
                  -> feed Deployment A
                  -> feed Deployment B
                  -> feed Deployment C
```

---

## Timeframe Rule

Subscribe once at the lowest required live bar timeframe, generally `1m`, then build higher timeframes internally.

Example:

Deployment requires:

```text
3m data
1w weekly data
```

The pipeline should:

```text
Subscribe to 1m bars
BarBuilder builds 3m bars
BarBuilder builds daily / weekly bars using calendar-aware aggregation
Feature Engine computes 3m and 1w features
```

Do not subscribe separately to 1m, 3m, 1d, and 1w streams.

---

## Calendar-Aware Aggregation

The BarBuilder must handle:

- session boundaries
- holidays
- half-days
- daily bar completion
- weekly bar boundaries
- completed-bar-only semantics

No forming bar access in v1.

Higher timeframe features must only use completed higher timeframe bars.

Example:

```text
A 3m decision at 10:33 ET may use:
- latest completed 3m bar
- latest completed 1h bar
- previous completed daily bar
- previous completed weekly bar
```

It must not use incomplete weekly or daily bars unless a specific future feature explicitly supports “so far” semantics.

---

# 4. News, Events, and AI Context

News and AI context are possible, but they must not be mixed into the market-data stream.

Use separate context lanes.

Correct model:

```text
MarketDataPipeline
  -> bars, quotes, OHLCV

ContextPipeline
  -> news, earnings, macro events, corporate events

AIContextAnalyzer
  -> optional advisory interpretation
```

The Feature Planner may derive both market-data requirements and context requirements from a Program.

Example future features:

```text
earnings_within_3_days
news_risk_high
macro_event_nearby
sentiment_conflict
operator_review_suggested
```

AI may add context, but must not approve or reject trades by itself.

AI may not:

- approve a trade
- reject a trade
- change position size
- submit an order
- override the PortfolioGovernor

AI may:

- suggest drafts
- summarize context
- flag risks
- recommend operator review

---

# 5. Pipeline Capability Edge Cases

Current rule:

```text
One Deployment -> one primary MarketDataPipeline for tradable market data.
```

However, some future strategies may require incompatible capability classes, such as:

- equities bars
- OPRA options data
- crypto data
- corporate news
- macro events

If a Program requires multiple incompatible tradable data classes, do one of the following:

1. Split it into multiple Deployments.
2. Create a formal Bridging Pipeline later.

Bridging Pipeline is out of scope for now.

Clarification:

```text
A Deployment may consume one primary MarketDataPipeline for tradable market data.
Non-price context such as news, earnings, macro events, or AI analysis comes through separate Context/Event pipelines.
```

---

# 6. Broker Events, Orders, and Fills

Market data and broker truth must stay separate.

## Market data flow

```text
MarketDataPipeline
  -> normalized bars
  -> BarBuilder
  -> Feature Engine
  -> Signal Engine
```

## Broker event flow

```text
Alpaca order/fill stream
  -> AlpacaBrokerAdapter
  -> BrokerSync
  -> OrderLedger
  -> TradeLedger
  -> BrokerAccount snapshot
  -> PortfolioGovernor reads updated truth
  -> Operations Center displays it
```

BrokerSync owns broker truth writing.

BrokerSync handles:

- order status updates
- fills
- partial fills
- position reconciliation
- account snapshot updates
- broker sync freshness
- broker order mapping

OrderManager does not listen to fills.
PortfolioGovernor does not own the broker stream.
BrokerAccount stores truth, but does not process trading logic.

---

# 7. Real vs Simulated Execution

There are two execution worlds only.

## Real broker runtime

```text
OrderManager
  -> BrokerAdapter
  -> BrokerSync
  -> OrderLedger / TradeLedger
```

Used by:

- Broker Runtime - Paper
- Broker Runtime - Live later

## Simulated execution

```text
SimulatedOrderManager
  -> SimulatedBroker
  -> SimulatedFillEngine
  -> SimulatedOrderLedger / SimulatedTradeLedger
```

Used by:

- Sim Lab Historical
- Sim Lab Live Simulation
- Backtester

Do not mix real and simulated ledgers.

Reuse the same vocabulary:

- order intent: open, close, tp, sl, scale
- order states: pending, submitted, accepted, partially_filled, filled, canceled, rejected
- fill fields: quantity, price, timestamp, fees, slippage
- trade lifecycle
- position lifecycle
- PnL calculations
- event log

But keep real broker truth and simulated truth separate.

---

# 8. Backtester, Chart Lab, Sim Lab, Live Preview, and Runtime Reuse

All surfaces reuse the same backend spine:

```text
Feature demand
  -> Feature Planner
  -> Resolver
  -> Pipeline or Historical Provider
  -> BarBuilder
  -> Feature Engine
  -> Signal Engine
```

Each surface stops at a different point.

## Chart Lab

Purpose: signal and component inspection.

Backend path:

```text
Historical bars
  -> Feature Engine
  -> Signal Engine
  -> condition truth / signal markers / non-fire reasons
```

Chart Lab must not:

- create orders
- simulate fills
- track positions
- show PnL as execution truth
- call BrokerAdapter
- call Alpaca

---

## Live Preview

Purpose: Chart Lab style inspection over live market data.

Backend path:

```text
MarketDataPipeline
  -> BarBuilder
  -> Feature Engine incremental updates
  -> Signal Engine diagnostics
```

Live Preview must not:

- create real orders
- mutate real ledgers
- use BrokerAdapter

If simulated fills are needed, that becomes Sim Lab Live Simulation.

---

## Sim Lab

Purpose: operational behavior rehearsal with simulated execution.

Backend path:

```text
Feature Engine
  -> Signal Engine
  -> Strategy Controls
  -> Risk
  -> Execution Style
  -> optional PortfolioGovernor
  -> SimulatedOrderManager
  -> SimulatedBroker
  -> SimulatedFillEngine
  -> SimulatedTradeLedger
```

Sim Lab must not use:

- BrokerAdapter
- BrokerSync
- real BrokerAccount truth unless explicitly selected as a starting snapshot
- real OrderLedger
- real TradeLedger

---

## Backtester

Purpose: historical performance measurement.

Backend path:

```text
Historical Provider / Cache
  -> BarBuilder
  -> Feature Engine batch
  -> Signal Engine
  -> simulated execution
  -> metrics
```

Backtester must not compute indicators independently.

No backtest-specific indicator logic.

---

## Broker Runtime - Paper

Purpose: real broker paper execution.

Backend path:

```text
MarketDataPipeline
  -> BarBuilder
  -> Feature Engine incremental
  -> Signal Engine
  -> Strategy Controls
  -> Risk
  -> Execution Style
  -> PortfolioGovernor
  -> OrderManager
  -> BrokerAdapter
  -> BrokerSync
  -> OrderLedger / TradeLedger
```

---

# 9. Resolver Contract

The resolver must become transparent, deterministic, and pipeline-aware.

Do not use `mode` for resolver behavior.

Use:

```text
selection_strategy
```

Allowed values:

```text
auto
default_preferred
manual_override
```

Resolver output should support per-symbol results.

Recommended result shape:

```text
symbol
selected_provider
pipeline_id
selection_strategy
reason
rejected_providers[]
resolver_input_hash
resolver_version
invocation_context
timestamp
```

Rejected providers must use enum codes, not free text.

Example rejection codes:

```text
UNSUPPORTED_TIMEFRAME
UNSUPPORTED_STREAMING
UNSUPPORTED_INTRADAY
CREDENTIAL_MISSING
CAPABILITY_TIER_INSUFFICIENT
MODE_MISMATCH
RATE_LIMIT_EXCEEDED
OPERATOR_VETO
NO_COMPATIBLE_PROVIDER
```

UI may map enum codes to human-readable text, but backend and logs should store codes.

---

# 10. Deployment Lifecycle

Deployment lifecycle should eventually enforce:

```text
created
  -> warming
  -> stream_confirming
  -> running
  -> paused
  -> stopping
  -> stopped
  -> failed
```

A Deployment cannot enter running until:

- Program is valid
- FeaturePlan is valid
- data requirements are resolved
- MarketDataPipeline is selected
- warmup is complete
- latest feature snapshot is warm
- stream freshness is confirmed
- broker sync is fresh
- PortfolioGovernor is available
- Control Plane state allows opens

Fail closed if any required state is missing or stale.

---

# 11. Priority Roadmap

## Phase 1 — Data Flow Lock

Goal:

```text
Feature demand -> Resolver -> MarketDataPipeline works end-to-end.
```

Deliverables:

1. FeaturePlanner outputs `data_requirements`.
2. Resolver returns pipeline-aware result:
   - pipeline_id
   - provider
   - selection_strategy
   - rejection_codes
   - per-symbol rows where needed
3. MarketDataPipeline model / schema exists.
4. MarketDataPipeline tracks:
   - provider
   - environment
   - subscribed symbols
   - consumers / deployment ids
   - freshness by symbol
5. Multiple deployments requesting the same symbol result in one pipeline subscription.

Tests:

- same input produces same resolver output
- resolver input hash is stable
- rejection reasons are enum-only
- duplicate symbol demand dedupes to one subscription
- Feature Engine does not call provider APIs

Exit gate:

```text
A Deployment can declare feature demand, resolve a pipeline, and attach data demand without direct provider calls.
```

---

## Phase 2 — BarBuilder and Streaming Runtime Truth

Goal:

```text
Live bars and broker events produce correct runtime state.
```

Deliverables:

1. BarBuilder builds:
   - 1m
   - 3m
   - 5m
   - 15m
   - 30m
   - 1h
   - 4h
   - 1d
   - 1w
2. Calendar-aware aggregation.
3. Completed-bar-only enforcement.
4. Broker event stream integration:
   - order updates
   - fills
   - partial fills
5. BrokerSync writes:
   - OrderLedger
   - TradeLedger
   - BrokerAccount snapshot
   - freshness state

Tests:

- 1m bars aggregate correctly into higher timeframes
- weekly aggregation respects calendar boundaries
- no incomplete higher timeframe bars leak into decisions
- broker fill updates order and trade ledger
- stale broker sync blocks new opens

Exit gate:

```text
Streaming market data and broker events update runtime state safely.
```

---

## Phase 3 — Execution Alignment

Goal:

```text
Sim Lab, Backtest, and Runtime share the same decision path up to real vs simulated execution.
```

Deliverables:

1. SimulatedOrderManager uses the same ExecutionIntent vocabulary as runtime.
2. Sim Lab respects:
   - Strategy Controls
   - Risk
   - Execution Style
   - optional PortfolioGovernor
3. Backtester uses Feature Engine and Signal Engine only.
4. Simulated ledgers remain separate from real ledgers.
5. Runtime and Sim produce equivalent decisions when given equivalent data.

Tests:

- same feature snapshot and strategy produce same CandidateTradeIntent
- same candidate produces same controls/risk/governor decision
- simulated execution never calls BrokerAdapter
- real runtime never writes simulated ledgers
- no independent indicator computation in Backtester, Chart Lab, or Sim Lab

Exit gate:

```text
Simulated and real execution paths are aligned but safely separated.
```

---

## Phase 4 — Safety and Trust

Goal:

```text
System fails closed under bad or uncertain conditions.
```

Deliverables:

1. Control Plane hydration:
   - global kill
   - account pause
   - deployment pause
2. Intent-aware cancellation result.
3. Unknown broker order triage.
4. BrokerSync reconciliation.
5. Deployment lifecycle enforcement.
6. Resolver visibility:
   - selected provider
   - selected pipeline
   - selection strategy
   - rejection codes
   - debug hash
7. Operations APIs for:
   - deployment health
   - stream freshness
   - broker sync freshness
   - order/fill status
   - governor decisions

Tests:

- kill blocks new opens
- account pause blocks only that account
- deployment pause blocks only that deployment
- protective exits remain allowed when appropriate
- stale data blocks new opens
- stale broker sync blocks new opens
- startup recovery restores control state

Exit gate:

```text
Operator can see and trust why the system is allowed or blocked from trading.
```

---

## Phase 5 — Productization

Goal:

```text
Make backend trust visible and usable in the UI.
```

Deliverables:

1. Operations Center APIs.
2. Resolver panel backend endpoint.
3. MarketDataPipeline health endpoint.
4. BrokerSync health endpoint.
5. Deployment detail endpoint.
6. Promotion/readiness backend:
   - unknown gate state
   - evidence TTLs
   - paper readiness
7. Trade ledger completion:
   - average fill price
   - realized PnL
   - partial fill lifecycle

Exit gate:

```text
The UI can display truthful runtime state without hardcoded assumptions.
```

---

# 12. Non-Negotiable Boundaries

The agent must stop if any of these occur.

## Stop condition 1

Feature Engine calls:

- Alpaca
- Yahoo
- Polygon
- news APIs
- AI APIs
- any provider SDK

## Stop condition 2

Multiple pipelines subscribe redundantly to the same provider/environment/symbol without a deliberate reason.

## Stop condition 3

Backtest, Chart Lab, or Sim Lab computes indicators outside Feature Engine.

## Stop condition 4

Simulated execution calls BrokerAdapter or BrokerSync.

## Stop condition 5

Real broker runtime writes simulated ledgers.

## Stop condition 6

BrokerAdapter is called outside the approved broker boundary.

## Stop condition 7

Free-text rejection reasons are used instead of enum codes.

## Stop condition 8

PortfolioGovernor is renamed to Account Manager or merged into BrokerAccount.

## Stop condition 9

Risk is shared globally across BrokerAccounts without an explicit future multi-account portfolio design.

---

# 13. Required Validation Commands

After every task, run:

```bash
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests -q
cd frontend && npm.cmd run build
cd frontend && npm.cmd test
```

If frontend was not touched, still run the frontend commands unless explicitly impossible in the environment.

---

# 14. Implementation Log Contract

Update:

```text
docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md
```

Use timestamp:

```text
YYYY-MM-DD HH:MM ET
```

Entry format:

```text
## YYYY-MM-DD HH:MM ET - <Task Name>

Task:
- <short factual description>

Files changed:
- <file path>

Implemented:
- <bullet>
- <bullet>

Scope kept out:
- <bullet>

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- <pass/fail summary>

Verification:
- Feature Engine did not call external providers
- Resolver output was not hardcoded
- No duplicate streaming path introduced
- No architecture boundaries violated

Commit:
- <commit hash or pending>
```

Keep the log short and factual.

No fluff.

---

# 15. Git Contract

After implementation and validation:

```bash
git status
git add .
git commit -m "<clear short message>"
git status
```

After commit:

- working tree must be clean
- tests must still pass
- no unrelated files should be changed

---

# 16. Agent Decision Rules

When unsure, choose:

```text
shared pipeline over per-account stream
feature-driven over config-driven
fail-closed over silent success
reuse over duplication
deterministic over smart
explicit enum over free text
completed bars over forming bars
account-isolated risk over global risk
separate simulated truth over mixed ledgers
```

---

# 17. Final Success State

The target state is:

```text
One feature system.
One data-demand flow.
One market-data pipeline model.
One real execution path.
One simulated execution path.
One broker-truth writer.
One governor per BrokerAccount.
Shared data.
Isolated risk.
Visible decisions.
```

Final operating model:

```text
Program defines intent.
Deployment runs intent.
Feature Planner derives demand.
Resolver selects pipelines.
MarketDataPipeline delivers data.
BarBuilder builds canonical bars.
Feature Engine computes facts.
Signal Engine emits candidate trade intent.
Strategy Controls, Risk, and Execution Style shape the candidate.
PortfolioGovernor approves or rejects.
OrderManager records internal orders.
BrokerAdapter submits to Alpaca.
BrokerSync reconciles broker truth.
Operations Center monitors and controls runtime.
```

---

# 18. Immediate Next Task Recommendation

The next backend task should be:

```text
Implement Feature Planner -> Resolver -> MarketDataPipeline wiring.
```

Do not start by adding more UI.
Do not start by adding more streaming behavior.
Do not start by refactoring BrokerAccount hierarchy.

First lock:

```text
feature demand -> data requirements -> pipeline selection -> pipeline demand registration
```

This is the foundation for:

- Chart Lab
- Live Preview
- Sim Lab Live Simulation
- Backtester
- Broker Runtime Paper
- future Broker Runtime Live
- future news/context features
