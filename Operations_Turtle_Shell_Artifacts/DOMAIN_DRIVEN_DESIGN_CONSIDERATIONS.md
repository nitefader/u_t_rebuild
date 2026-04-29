# Domain-Driven Design Considerations

Operation: Turtle Shell

Purpose: align Ultimate Trader implementation to clear bounded contexts, aggregate ownership, and clean domain boundaries.

## Core DDD Principle

Ultimate Trader is not a collection of screens or workflows.

It is a domain system with one canonical trading spine:

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

Every implementation must preserve the meaning, ownership, and boundary of each domain.

## Bounded Contexts

### Strategy Context

Owns reusable trading logic.

Owns:

- signal rules
- feature requirements
- trading windows
- entry plan
- stop plan
- target plan
- runner plan
- logical exit plan
- strategy versioning
- strategy configuration fingerprint

Must not own:

- Account risk
- Account money
- broker credentials
- final quantity
- broker order status
- positions

Primary concepts:

- Strategy
- StrategyVersion
- StrategyConfig
- StrategyFingerprint

DDD rule:

Strategy describes what should happen logically.
It does not decide whether any Account can afford it or should execute it.

### Watchlist Context

Owns eligible symbol sources.

Owns:

- static symbol lists
- dynamic queries
- provider-backed symbol sources
- generated snapshots
- symbol evidence
- refresh errors

Primary concepts:

- Watchlist
- WatchlistSource
- WatchlistSnapshot
- WatchlistSymbolEvidence

DDD rule:

Deployment consumes Watchlist snapshots.
Strategy must not hide provider queries inside strategy logic.

### Deployment Context

Owns running Strategy publication.

Owns:

- strategy reference
- watchlist references
- subscribed Account ids
- runtime overrides
- runtime state
- symbol eligibility
- SignalPlan publication

Must not own:

- final quantity
- Account money
- broker credentials
- broker order submission
- broker truth
- position truth

Primary concepts:

- Deployment
- DeploymentRuntimeState
- DeploymentSymbolEligibility

DDD rule:

Deployment publishes SignalPlans.
Accounts decide what to do with them.

### SignalPlan Context

Owns neutral trade intent and lifecycle plan.

Owns:

- opening intent
- close/reduce intent
- targets
- stop
- trail
- breakeven
- runner
- logical exit
- lifecycle lineage
- feature snapshot reason
- expiration

Must not own:

- final Account quantity
- broker order id
- broker status
- Governor approval
- Account-specific buying power decision

Primary concepts:

- SignalPlan
- SignalPlanIntent
- SignalPlanEntry
- SignalPlanStop
- SignalPlanTarget
- SignalPlanRunner
- SignalPlanLogicalExit
- SignalPlanLineage

DDD rule:

SignalPlan is neutral.
Final sizing begins only in RiskResolver.

Important invariant:

One opening SignalPlan represents one proposed Position lifecycle.
Targets, stops, runner, and logical exits are lifecycle instructions, not unrelated trades.

### Account Context

Owns broker-connected trading identity and Account-specific state.

Owns:

- broker provider metadata
- broker mode metadata
- credential reference
- risk configuration
- symbol restrictions
- pause/kill state
- buying power
- broker sync state
- account-level restrictions
- Account-owned positions

Primary concepts:

- Account
- AccountRiskConfig
- AccountRestrictions
- AccountTradeSyncStatus

DDD rule:

Paper and live are Account metadata, not separate runtimes.

### Account Evaluation Context

Owns Account-specific interpretation of a SignalPlan.

Owns:

- participation decision
- accept/reject/defer status
- relation to existing Position
- warnings
- rejection reasons
- risk inspection inputs
- Governor request preparation

Primary concepts:

- AccountSignalPlanEvaluation
- AccountEvaluationStatus
- ParticipationDecision

DDD rule:

The same SignalPlan can be accepted by one Account, rejected by another, and sized differently by a third.

### RiskResolver Context

Owns final Account-specific sizing and risk impact.

Owns:

- resolved quantity
- resolved notional
- max loss
- stop distance
- buying power required
- projected exposure
- projected concentration
- existing position context
- related open orders
- sizing violations
- sizing warnings

Primary concepts:

- RiskResolverResult
- RiskViolation
- RiskWarning

DDD rule:

RiskResolver is the first boundary where final Account quantity may appear.

### Governor Context

Owns final internal protection decision before order creation.

Owns:

- approval/rejection/block decision
- reasons
- violations
- warnings
- duplicate execution protection
- sync freshness checks
- pause/kill checks
- restrictions checks
- drawdown/loss checks
- concentration checks

Primary concepts:

- GovernorRequest
- GovernorDecision
- GovernorDecisionTrace

DDD rule:

No broker order reaches BrokerAdapter unless Governor approves it.

### Order / Trade / Position Context

Owns internal lifecycle records.

Owns:

- internal orders
- order idempotency
- trades
- fills as internal projection
- position lineage
- position explanation context
- lifecycle intent
- leg labels
- Account-owned exposure

Primary concepts:

- Order
- Trade
- Position
- PositionLineage
- PositionExplanationContext

DDD rule:

Orders are Account-specific.
Positions are Account-owned.
Every automated order must preserve SignalPlan lineage.

### Broker Integration Context

Owns broker boundary and broker truth reconciliation.

Owns:

- BrokerAdapter
- BrokerSync
- broker order mapping
- broker fills
- broker status
- account snapshots
- position snapshots
- broker capability preflight
- market-rule preflight
- broker error taxonomy

Primary concepts:

- BrokerAdapter
- BrokerSync
- BrokerCapabilityMatrix
- BrokerOrderPreflightResult
- MarketRulePreflightResult
- BrokerFailureEvent

DDD rule:

BrokerAdapter submits or cancels.
BrokerSync writes broker truth.
No other context writes broker-derived truth.

### Market Data / Feature Computation Context

Owns data provider access and feature generation.

Owns:

- Market Data Providers
- provider validation
- provider capability metadata
- live stock market data stream
- historical data resolution
- normalized bars
- feature identity
- feature planning
- feature computation
- feature cache

Primary concepts:

- MarketDataProvider
- LiveStockMarketDataStream
- FeatureSpec
- FeatureSnapshot
- FeatureEngine

DDD rule:

Feature code must not call providers directly.
Feature demand flows through resolver and stream boundaries.

### Research Evidence Context

Owns research outputs, not runtime truth.

Owns:

- Chart Lab preview evidence
- Backtest runs
- Simulation runs
- Optimization runs
- Walk-forward runs
- promotion evidence
- readiness reports

Primary concepts:

- ChartLabPreviewEvidence
- BacktestRun
- SimulationRunEvidence
- OptimizationRun
- WalkForwardRun
- PromotionEvidenceBundle
- StrategyReadinessReport

DDD rule:

Research systems produce evidence.
They do not become alternate live runtimes.

### Operations Context

Owns operator-visible runtime truth projection.

Owns:

- runtime status
- stream status
- Account Trade Sync status
- Deployment status
- SignalPlan status
- Account evaluations
- Governor decisions
- orders
- fills
- positions
- stale states
- warnings
- failures
- explanation context

Primary concepts:

- OperationsSnapshot
- RuntimeStatusEnvelope
- StreamStatus
- DeploymentStatus
- SignalPlanStatus
- PositionExplanationContext

DDD rule:

Nothing mission-critical should fail silently or appear successful without evidence.

### AI Advisory Context

Owns explanation and assistance only.

Owns:

- explain position
- explain Account
- explain failure
- summarize runtime state
- draft Strategy
- generate copyable review context

Must not own:

- approvals
- rejections
- order submission
- order cancellation
- Account mutation
- broker truth mutation
- Governor override

DDD rule:

AI explains. AI does not trade.

## Aggregate Ownership

### Strategy Aggregate

Aggregate root:

- Strategy

May contain:

- StrategyVersion
- StrategyConfig
- feature requirements
- signal rules
- execution plan config

Must not reference mutable Account state directly.

### Watchlist Aggregate

Aggregate root:

- Watchlist

May contain:

- source definition
- refresh rules
- latest snapshot reference

Snapshot is immutable evidence once generated.

### Deployment Aggregate

Aggregate root:

- Deployment

May contain:

- strategy reference
- watchlist references
- subscribed Account ids
- runtime overrides
- runtime status

Deployment emits SignalPlans but does not own Account decisions.

### SignalPlan Aggregate

Aggregate root:

- SignalPlan

May contain:

- entry plan
- stop plan
- targets
- runner
- logical exit
- lifecycle references

SignalPlan is immutable after publication except for status/supersession metadata.

### Account Aggregate

Aggregate root:

- Account

May contain:

- risk config
- restrictions
- sync state
- pause state
- position references

Account owns Position truth at the product level.

### Position Aggregate

Aggregate root:

- PositionLineage

May contain:

- opening SignalPlan id
- related SignalPlan ids
- order ids
- fill ids
- active targets
- active stop
- runner state
- logical exit state
- current quantity
- explanation context

Position closes only after BrokerSync confirms zero quantity.

### Order Aggregate

Aggregate root:

- Order

May contain:

- lifecycle intent
- leg label
- SignalPlan lineage
- Account id
- broker mapping reference
- internal status

Broker status is reconciled by BrokerSync.

## Domain Events To Consider

Agents should design contracts so these events can exist later, even if not fully implemented immediately.

- StrategyPublished
- WatchlistSnapshotCreated
- DeploymentStarted
- DeploymentPaused
- SignalPlanCreated
- SignalPlanPublished
- SignalPlanExpired
- AccountSignalPlanAccepted
- AccountSignalPlanRejected
- RiskResolved
- GovernorApproved
- GovernorRejected
- OrderCreated
- BrokerOrderSubmitted
- BrokerOrderRejected
- BrokerFillReceived
- BrokerSyncUpdated
- PositionOpened
- PositionReduced
- PositionClosed
- PositionProtectionUpdated
- AccountTradeSyncDown
- LiveMarketDataStreamDown
- PromotionEvidenceRecorded

DDD rule:

Events describe facts that happened.
Commands request actions.
Do not confuse them.

## Commands To Consider

- CreateStrategy
- CreateWatchlist
- StartDeployment
- PauseDeployment
- PublishSignalPlan
- EvaluateSignalPlanForAccount
- ResolveAccountRisk
- RequestGovernorDecision
- CreateOrderFromApprovedSignalPlan
- SubmitOrderToBroker
- CancelBrokerOrder
- ReplaceBrokerOrder
- ApplyBrokerSyncEvent
- GeneratePositionExplanation
- RecordResearchEvidence

DDD rule:

Commands may fail.
Events should represent completed facts.

## Anti-Corruption Layers

Use anti-corruption layers for external systems.

Required anti-corruption layers:

- Alpaca BrokerAdapter
- Alpaca BrokerSync Mapper
- Alpaca Capability Matrix
- Yahoo Market Data Provider
- AI Provider Runtime
- Broker Error Normalizer
- Market Rule Preflight

DDD rule:

External provider models must not leak into core domain contracts.

## Repository Implementation Guidance

Suggested module ownership:

```text
backend/app/domain
  portable contracts and domain language

backend/app/runtime
  Deployment runtime and SignalPlan publication

backend/app/risk_resolver
  Account-specific sizing and risk impact

backend/app/governor
  final protection decision

backend/app/orders
  internal orders, trades, lineage, idempotency

backend/app/brokers
  BrokerAdapter, BrokerSync, preflight, broker errors

backend/app/market_data
  provider catalog, resolver, stream hub, normalized data

backend/app/features
  feature identity, planning, computation, cache

backend/app/decision
  signal engine and SignalPlanBuilder

backend/app/operations
  operator-facing runtime projection

backend/app/persistence
  durable storage

backend/app/ai
  advisory-only AI runtime
```

## Implementation Priorities

Implement in this order:

1. SignalPlan contract
2. Account Evaluation contract
3. RiskResolver contract
4. Governor request/decision contract
5. Order lineage fields
6. Position lineage and explanation context
7. Broker preflight and market-rule preflight
8. BrokerSync truth enforcement
9. One Account Trade Sync per Account
10. One Live Stock Market Data Stream
11. Runtime spine rewire
12. Research evidence contracts
13. Operations snapshot contracts

## DDD Acceptance Criteria

A change is acceptable only if:

- each domain owns its own decisions
- no domain writes another domain's truth directly
- Strategy does not own Account decisions
- SignalPlan remains neutral
- Account Evaluation is Account-specific
- RiskResolver is the first final sizing boundary
- Governor remains the final internal gate
- Order preserves lineage
- BrokerSync remains the only broker truth writer
- Position truth belongs to Account
- Operations exposes runtime truth
- AI remains advisory
- provider-specific rules stay behind anti-corruption layers
- no second runtime is introduced

## Final Agent Instruction

Before coding, identify which bounded context the change belongs to.

If the change crosses contexts, define the command, event, contract, or service boundary.

If ownership is unclear, stop and document a blocker in `OPERATION_STATUS.md`.

Do not solve ambiguity by creating a new entity.

Do not solve pressure by bypassing the domain spine.

Build the domain model first. Implementation follows the model.
