# Operation Turtle Shell Backend Lockdown Agent Plan

Mission: build a clean, solid, production-ready backend foundation.

No frontend work. No visual polish. No scattered experiments. Every task must
answer:

```text
Does this make the backend stronger, cleaner, and more reusable?
```

If the answer is no, park it.

## Continuity Rule

Operation Turtle Shell must survive agent changes, lost context, timeouts, or
credit exhaustion.

Before doing work, every agent must read:

1. `Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md`
2. `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
3. `Operations_Turtle_Shell_Artifacts/BACKEND_LOCKDOWN_AGENT_PLAN.md`
4. `Operations_Turtle_Shell_Artifacts/BACKEND_REALITY_MAP.md`
5. `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`
6. `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`
7. `Operations_Turtle_Shell_Artifacts/DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`

`TURTLE_SHELL_GUARDRAILS.md` is mandatory. If a planned change conflicts with
it, stop and document the conflict as a blocker in `OPERATION_STATUS.md`.

`DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md` is mandatory. Before coding, every
agent must identify the bounded context that owns the change. If ownership is
unclear, stop and document the ambiguity as a blocker in `OPERATION_STATUS.md`.

Before ending work, every agent must update `OPERATION_STATUS.md` with the
current phase, completed action, next action, touched files, tests, blockers,
and approval status.

Before starting work, every agent must update `OPERATION_STATUS.md` with the
work session status, agent role, started_at timestamp, current phase, current
task, and expected next checkpoint.

For longer work, every agent must update `OPERATION_STATUS.md` with a heartbeat
before moving to a new subtask.

No agent may restart the operation from scratch unless the status file says to
do so.

All timestamps must use explicit date and time syntax:

```text
Date: YYYY-MM-DD
Time: HH:mm:ss
DateTime: YYYY-MM-DD HH:mm:ss -04:00
```

Do not use vague timing language such as today, tomorrow, yesterday, later, or
recent in official Turtle Shell artifacts.

## Final Backend Doctrine

Ultimate Trader backend converges on this flow:

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

Research systems must feed the same doctrine:

```text
Chart Lab
-> Backtest / Sim Lab
-> Optimization
-> Walk-Forward
-> Promotion Evidence
-> Deployment
-> SignalPlan
```

Backtester, Sim Lab, Walk-Forward, Optimization, and Live must share the same:

- Feature Engine
- Signal Engine
- RiskResolver
- Order creation logic
- lineage contracts
- result/evidence contracts

Runtime market data has exactly one shared live stock data stream:

```text
Backend app startup
-> Live Stock Market Data Stream opens
-> all runtime components subscribe/unsubscribe through the shared stream
-> stream stays open even with zero active symbol subscriptions
-> backend app shutdown
-> stream closes
```

No component may create its own live stock stream for equities. Strategies,
Deployments, Chart Lab previews that need live data, Operations, Watchlists, and
future runtime tools must all consume the shared stream through one backend
boundary.

Broker Account trade updates follow the same always-visible discipline:

```text
Account created
-> credentials validated
-> provider is Alpaca
-> one Account Trade Sync opens for that Account
-> Account Trade Sync stays open until backend app shutdown or explicit operator
   trade-sync pause
```

Account trading pause and Account Trade Sync pause are different controls.
Pausing trading must not make broker truth invisible. If the operator pauses
trading, Account Trade Sync should normally remain open so orders, fills,
positions, rejects, cancels, restrictions, and snapshots stay visible.

## Agent Roster

### Coordinator

Owns final approval.

Responsibilities:

- keep all agents backend-only
- enforce canonical names
- prevent duplicate concepts
- sequence work
- resolve conflicts
- approve or reject artifacts
- decide what gets implemented

Final approval question:

```text
Does this make the backend simpler, stronger, and aligned to the locked doctrine?
```

### Angry Architect

Owns architectural discipline.

Personality for this role: strict, skeptical, intolerant of vague names,
duplicate flows, hidden coupling, and frontend-driven backend design.

Responsibilities:

- reject old names such as Program, Services Center, Paper Runtime, Live Runtime,
  and Account Governor as active product concepts
- reject any design that makes paper/live separate product paths
- reject any design that splits live, backtest, sim, optimization, or
  walk-forward into separate logic engines
- reject over-modeled execution-leg entities unless proven necessary
- require lineage from Strategy through SignalPlan to Order and Position
- require Account ownership of Position truth

Approval standard:

```text
No clever maze. No duplicate runtime. No hidden broker truth. No mushy names.
```

### Product Manager

Owns product clarity and operator intent.

Responsibilities:

- define what the operator needs to understand
- ensure Accounts, Deployments, SignalPlans, Positions, and stream health are
  explainable
- define acceptance criteria for backend contracts
- keep AI advisory only
- make sure future UI/API surfaces can show failure, freshness, and lineage

Approval standard:

```text
An operator should understand what exists, why it exists, and what state it is in.
```

### Alpaca Agent

Owns broker-specific Alpaca correctness.

Responsibilities:

- verify Alpaca remains behind BrokerAdapter and BrokerSync
- ensure Account metadata drives Alpaca paper/live endpoints
- ensure Account Trade Sync is one stream per Account and always starts when the
  app is running
- ensure Alpaca order/fill/account/position truth enters through BrokerSync only
- verify manual trading and automated trading share Account truth
- identify Alpaca-specific constraints without leaking Alpaca into core domain

Approval standard:

```text
Alpaca is a provider behind boundaries, not a backend architecture.
```

### Alpaca Order Compliance Agent

Owns Alpaca order capability coverage.

Responsibilities:

- map supported Alpaca order types by asset class
- map supported Alpaca time-in-force values by asset class and order type
- map order class support such as simple, bracket, OCO, OTO, and trailing stop
- define preflight validations before BrokerAdapter submission
- define replacement/cancel rules and lifecycle expectations
- ensure unsupported combinations fail before broker submission when knowable
- ensure supported combinations remain possible through canonical contracts
- keep Alpaca-specific capability rules outside core Strategy and SignalPlan
  doctrine

Approval standard:

```text
If Alpaca would reject a known invalid order shape, Ultimate Trader should reject
it earlier with a clear operator-facing reason.
```

### Broker Error And Advisory Agent

Owns broker error taxonomy and operator guidance.

Responsibilities:

- normalize Alpaca API errors into canonical backend error codes
- separate validation errors, broker rejects, transport errors, auth errors,
  rate limits, buying-power failures, asset restrictions, and session errors
- define retryable vs non-retryable failures
- define operator advisory messages for each known failure family
- ensure errors appear in Operations and Account/Position explanation context
- make failures copyable and useful for LLM/operator review

Approval standard:

```text
No opaque broker failure. Every failure needs a code, source, severity, and
operator advisory.
```

### Market Rules And Session Agent

Owns market-hours, session, fractional, shorting, and asset-rule validation.

Responsibilities:

- define regular-hours vs extended-hours validation
- define fractional order rules
- define short-sale checks and easy-to-borrow checks
- define asset tradability checks
- define options, crypto, OTC, and equities differences
- define buying-power prechecks and margin-related warnings
- define market clock/calendar dependencies
- ensure regulatory/session rules are preflighted before BrokerAdapter
  submission when possible

Approval standard:

```text
The backend must know when an order is structurally valid, session-valid,
asset-valid, and Account-valid before it reaches Alpaca.
```

### Full Stack Developer

For this operation, this role works backend-first only.

Responsibilities:

- map current backend modules to the locked doctrine
- identify contract gaps
- propose minimal implementation steps
- create tests for backend contracts
- avoid frontend changes
- avoid UI-driven shortcuts

Approval standard:

```text
The backend contract must be reusable by API, UI, tests, and future agents.
```

## Non-Negotiables

- Read and follow `TURTLE_SHELL_GUARDRAILS.md` before implementation.
- Read and follow `DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md` before implementation.
- No frontend work.
- No new UI artifacts.
- No old product names as active concepts.
- No separate paper/live runtime.
- No separate logic engines per mode.
- No duplicate live stock data streams.
- No broker truth outside BrokerSync.
- No broker calls outside BrokerAdapter or approved broker sync boundaries.
- No component-owned live market data socket for stocks.
- No missing Account Trade Sync for a validated Alpaca Account.
- No silent closure of Account Trade Sync because an Account is idle, paused for
  trading, or not subscribed to a Deployment.
- No hidden failure states.
- No order without SignalPlan lineage, except explicit manual operator orders.
- No Position without Account ownership.
- No AI mutation of trade/account/broker truth.
- Broker-facing tests must use an already configured Broker Service or the
  frontend-configured Broker Account.
- Submitting broker orders during tests is allowed when the test explicitly
  validates order submission, rejection, BrokerSync truth, or operator advisory
  behavior. Those tests must route through BrokerAdapter/BrokerSync and make the
  test order clearly identifiable.

## Phase 0: Repo Reality Check

Goal: know what exists before changing anything.

Tasks:

1. Inventory current backend modules.
2. Mark each module as:
   - keep
   - rename/alias
   - refactor
   - archive later
   - do not touch in this operation
3. Identify old names still active in backend code.
4. Identify tests that currently protect useful behavior.
5. Identify tests that encode old naming or old runtime concepts.

Expected artifact:

```text
Backend Reality Map
```

Must include:

- current module path
- current responsibility
- target doctrine responsibility
- risk level
- recommended action

Coordinator gate:

```text
No implementation starts until the reality map is accepted.
```

## Phase 1: Core Domain Contract Lock

Goal: define the exact backend shape of Strategy, Deployment, SignalPlan,
Account, and Account Evaluation.

### 1. Strategy

Strategy is reusable trading logic and execution-plan config.

Strategy owns:

- signal rules
- feature requirements
- trading windows
- entry plan
- stop plan
- target plan
- runner plan
- logical exit plan
- compatibility preferences

Strategy must not own:

- Account risk
- Account money
- broker credentials
- broker positions
- final quantity
- final broker execution decision

Output contract:

```text
StrategyConfig
StrategyVersion or equivalent versioned Strategy record
```

### 2. Watchlist

Watchlist is the source of eligible symbols.

Watchlist may be:

- static
- dynamic
- provider-backed
- query-backed

Yahoo-powered dynamic Watchlists are allowed as a provider-backed source, not as
core Strategy logic.

Output contract:

```text
Watchlist
WatchlistSnapshot
WatchlistSymbol
WatchlistSource
```

### 3. Deployment

Deployment is a running Strategy publisher over selected Watchlists.

Deployment owns:

- Strategy reference
- Watchlist references
- subscribed Account ids
- runtime overrides
- runtime status
- emitted SignalPlans
- symbol eligibility context

Deployment must not:

- own Account money
- own broker truth
- size final orders
- submit broker orders
- be duplicated per Account

Output contract:

```text
Deployment
DeploymentRuntimeState
DeploymentSymbolEligibility
```

### 4. SignalPlan

SignalPlan is a neutral trade or position-management plan emitted by a
Deployment.

SignalPlan must support:

- open
- close
- reduce
- target
- stop
- trail
- breakeven
- runner
- logical_exit

SignalPlan does not contain final Account quantity.

Output contract:

```text
SignalPlan
SignalPlanIntent
SignalPlanEntry
SignalPlanStop
SignalPlanTarget
SignalPlanRunner
SignalPlanLineage
SignalPlanManagementRule
```

### 5. Account

Account is the broker-connected trading account with metadata, credentials,
risk config, restrictions, and position ownership.

Many Accounts can exist.

Account owns:

- broker provider metadata
- broker mode metadata
- credential reference
- risk config
- broker restrictions
- buying power
- sync state
- orders
- positions
- fills
- pause/kill state
- symbol restrictions
- final approval path through Governor

Output contract:

```text
Account
AccountRiskConfig
AccountRestrictions
AccountTradeSyncStatus
```

### 6. Account Evaluation

Account Evaluation is the per-Account interpretation of a SignalPlan.

It answers:

- should this Account participate?
- what size is allowed?
- what risk would this create?
- does this relate to an existing Position?
- is this a close, partial close, stop, target, trail, runner, or logical exit?
- what does the Governor need to know?

Output contract:

```text
AccountSignalPlanEvaluation
RiskResolverResult
GovernorRequest
GovernorDecision
```

Coordinator gate:

```text
Core contracts are accepted only if one Deployment can emit one SignalPlan and
many Accounts can evaluate it differently.
```

## Phase 2: Multi-Leg SignalPlan Lock

Goal: represent 4-target-plus-runner trades as one trade lifecycle, not
separate independent positions.

Rule:

```text
One trade idea = one opening SignalPlan.
Targets, stop, trail, and runner are management instructions inside the
SignalPlan lifecycle.
```

Example structure:

```text
SignalPlan
  intent: open
  symbol: SPY
  side: long
  entry:
    type: limit
    price: 500.00
  stop:
    type: fixed
    price: 495.00
  targets:
    - label: T1
      action: reduce
      quantity_pct: 25
      price: 505.00
    - label: T2
      action: reduce
      quantity_pct: 25
      price: 510.00
    - label: T3
      action: reduce
      quantity_pct: 25
      price: 515.00
    - label: T4
      action: reduce
      quantity_pct: 15
      price: 520.00
  runner:
    quantity_pct: 10
    management: trailing_or_logical_exit
  logical_exit:
    rule: 5m.RSI_21 crosses_above 15m.RSI_21
```

RiskResolver sees:

- total proposed position
- total max loss
- stop distance
- target distribution
- runner exposure
- existing Account exposure
- buying power impact
- concentration impact
- duplicate exposure risk

Governor sees:

- Account sync freshness
- Account pause/kill state
- Deployment pause state
- SignalPlan expiration
- buying power
- restrictions
- open orders
- existing positions
- daily loss and drawdown
- max open positions
- concentration
- duplicate execution protection
- total risk of the full lifecycle

Order Ledger may create several internal orders, but all must link to:

- Account id
- Strategy id
- Deployment id
- SignalPlan id
- opening SignalPlan id when applicable
- current SignalPlan id
- Position lineage id
- intent
- leg label when applicable

Coordinator gate:

```text
Targets can become multiple orders, but they cannot become multiple unrelated
positions or unrelated trade ideas.
```

## Phase 3: SignalPlan To Order Flow

Goal: lock the flow from neutral SignalPlan to Account-specific orders.

Required flow:

```text
Deployment emits SignalPlan
-> Account receives SignalPlan
-> Account Evaluation decides participation
-> RiskResolver computes Account-specific size and risk
-> Governor approves/rejects with reasons
-> OrderManager creates internal orders
-> BrokerAdapter submits/cancels/replaces broker orders
-> BrokerSync writes broker truth
-> Position truth updates
-> Operations Center surfaces status
```

Required tests:

- one SignalPlan can be evaluated by multiple Accounts
- Accounts can accept/reject differently
- final quantity is Account-specific
- Governor rejection prevents OrderManager creation
- OrderManager preserves SignalPlan lineage
- BrokerAdapter never receives unapproved orders
- BrokerSync is the only writer of broker-derived truth
- partial close SignalPlan reduces Position without flattening all
- logical exit SignalPlan closes or reduces only the related Position
- target legs remain tied to one opening SignalPlan

Coordinator gate:

```text
No live, sim, or backtest mode may bypass this flow once the contracts exist.
```

## Phase 4: Unified Computation Layer

Goal: ensure every mode uses the same computation core.

Shared backend components:

- Feature Engine
- Signal Engine
- Strategy config parser
- SignalPlan builder
- RiskResolver
- Order creation logic

Modes that must share this:

- Chart Lab
- Backtest
- Sim Lab
- Optimization
- Walk-Forward
- Live Deployment

Feature Engine requirements:

- batch and streaming parity
- same feature key identity
- same timeframe alignment rules
- same warmup behavior
- same missing-data behavior
- same calendar/session behavior
- deterministic replay support
- incremental live support

Required tests:

- same bars + same Strategy config produce same features in batch and streaming
- same features + same Strategy config produce same SignalPlan candidate
- Chart Lab cannot create orders
- Sim Lab cannot call brokers
- Backtest cannot call brokers
- Live cannot use a separate signal path

Coordinator gate:

```text
No duplicate feature or signal logic by mode.
```

## Phase 5: Watchlist And Dynamic Source Contract

Goal: define Watchlists as reusable symbol sources for Deployments.

Watchlist types:

- static symbols
- dynamic query
- provider-backed
- generated snapshot

Yahoo integration belongs behind a Watchlist source/provider boundary.

Yahoo dynamic queries may include:

- movers
- volume
- price range
- market cap
- sector
- gap up/down
- relative volume
- news availability

Future AI news analysis may enrich Watchlists, but AI remains advisory and
provider-backed. It is not core V1 trading logic.

Output contracts:

```text
WatchlistSource
WatchlistQuery
WatchlistSnapshot
WatchlistRefreshResult
WatchlistSymbolEvidence
```

Required tests:

- static Watchlist resolves deterministically
- dynamic Watchlist creates snapshot evidence
- Yahoo provider failures are visible
- Deployment uses Watchlist snapshot, not an invisible live query
- AI news enrichment cannot approve trading

Coordinator gate:

```text
Deployments consume Watchlist snapshots. They do not hide provider queries
inside Strategy logic.
```

## Phase 6: Streams And Runtime Foundation

Goal: lock runtime streams and monitoring.

Required runtime streams:

- one shared Live Stock Market Data Stream for stocks
- one Account Trade Sync per Account

Live Stock Market Data Stream:

- selected from Market Data Providers
- starts on backend app load when enabled
- remains open until backend app exit/shutdown
- may have zero or many subscriptions
- is reused by every backend component that needs live stock data
- is the only live stock data stream/socket in the platform
- supports component-level subscriptions without creating component-level streams
- exposes freshness, provider, subscriptions, reconnect count, last error
- exposes whether the stream is open, connected, authenticated, degraded,
  reconnecting, down, or disabled by Settings
- does not silently close just because no symbols are currently subscribed

Account Trade Sync:

- starts for every configured Account while app is running
- starts immediately after an Account is created, credentials are validated, and
  provider is Alpaca
- opens exactly one trade stream per Account
- starts even if Account is paused
- starts even if Account is not subscribed to a Deployment
- starts even if no automated trading is active
- remains open until backend app shutdown or explicit operator trade-sync pause
- treats trading pause and trade-sync pause as separate states
- watches orders, fills, cancels, rejects, positions, snapshots, restrictions
- exposes freshness, connection state, reconnect count, last error
- exposes whether the stream is open, connected, authenticated, degraded,
  reconnecting, down, disabled by operator, or unavailable because credentials
  are invalid

Required tests:

- backend startup opens the Live Stock Market Data Stream when enabled
- Live Stock Market Data Stream remains open with zero subscriptions
- multiple components subscribe through the same shared stream instance
- component unsubscribe does not close the shared stream while the app is still
  running
- backend shutdown closes the shared stream cleanly
- backend startup starts Account Trade Sync for each Account
- creating and validating an Alpaca Account starts one Account Trade Sync
- validated Alpaca Account has exactly one Account Trade Sync
- trading-paused Account still has Account Trade Sync open
- explicit operator trade-sync pause closes or suspends only that Account Trade
  Sync and makes the state visible
- resuming operator trade-sync pause reopens that Account's trade stream
- app shutdown closes all Account Trade Sync streams cleanly
- failed Account Trade Sync is visible
- Live Stock Market Data Stream failure is separate from Account Trade Sync
  failure
- Operations can report all stream states

Coordinator gate:

```text
No component gets a private live stock stream. No Account is invisible just
because it is paused or idle.
```

## Phase 7: Research And Promotion Alignment

Goal: align Backtest, Sim Lab, Chart Lab, Walk-Forward, Optimization, and
Promotion with the canonical backend.

Required contracts:

- `ChartLabPreview`
- `BacktestRun`
- `SimulationRun`
- `OptimizationRun`
- `WalkForwardRun`
- `PromotionEvidence`
- `StrategyReadinessReport`

Each result must include:

- Strategy id/version/config fingerprint
- Watchlist snapshot id
- data range
- feature engine version/fingerprint
- signal engine version/fingerprint
- assumptions
- warnings
- errors
- metrics
- lineage
- reproducibility key

Promotion should answer:

- is the Strategy ready for paper Deployment?
- is the Strategy ready for live Account subscription?
- what evidence exists?
- what evidence is missing?
- what warnings are present?
- what blocks promotion?

Coordinator gate:

```text
Research systems produce evidence. They do not become alternate live runtimes.
```

## Phase 8: Operations Contract

Goal: make backend truth visible to the future UI and operators.

Operations Center backend should expose:

- Market Data Stream status
- Account Trade Sync status for every Account
- running Deployments
- recent SignalPlans
- Account evaluations
- Governor decisions
- open Orders
- open Positions
- stale sync states
- stream errors
- broker sync errors
- research/promotion readiness status

Required contracts:

- `OperationsSnapshot`
- `RuntimeStatusEnvelope`
- `StreamStatus`
- `AccountTradeSyncStatus`
- `LiveStockMarketDataStreamStatus`
- `DeploymentStatus`
- `SignalPlanStatus`
- `PositionExplanationContext`

Coordinator gate:

```text
Nothing mission-critical can fail silently or appear healthy without evidence.
```

## Agent Assignment Matrix

### Task 1: Backend Reality Map

Owner: Full Stack Developer

Reviewers:

- Angry Architect
- Coordinator

Deliverable:

```text
Backend module inventory with target doctrine mapping.
```

### Task 2: SignalPlan Contract

Owner: Angry Architect

Reviewers:

- Product Manager
- Full Stack Developer
- Coordinator

Deliverable:

```text
SignalPlan contract with multi-leg lifecycle support.
```

### Task 3: Account Evaluation And RiskResolver Contract

Owner: Full Stack Developer

Reviewers:

- Angry Architect
- Alpaca Agent
- Coordinator

Deliverable:

```text
Account-specific evaluation flow and Governor request shape.
```

### Task 4: Alpaca Boundary Audit

Owner: Alpaca Agent

Reviewers:

- Angry Architect
- Coordinator

Deliverable:

```text
Audit proving Alpaca is contained behind BrokerAdapter and BrokerSync.
```

### Task 5: Alpaca Order Capability Matrix

Owner: Alpaca Order Compliance Agent

Reviewers:

- Alpaca Agent
- Market Rules And Session Agent
- Angry Architect
- Coordinator

Deliverable:

```text
Alpaca order type, order class, time-in-force, asset-class, fractional,
extended-hours, replacement, and cancel capability matrix.
```

Required coverage:

- equities
- fractional equities
- OTC assets
- options
- crypto
- market orders
- limit orders
- stop orders
- stop-limit orders
- trailing stop orders where supported
- bracket orders
- OCO orders
- OTO orders
- DAY
- GTC
- IOC
- FOK
- OPG
- CLS
- extended-hours eligibility
- notional vs quantity rules
- order replacement support
- cancel support

Expected backend output:

```text
BrokerCapabilityMatrix
BrokerOrderPreflightRequest
BrokerOrderPreflightResult
BrokerOrderCapabilityViolation
```

Coordinator gate:

```text
Order capability rules must be provider-specific and must not contaminate the
core SignalPlan model.
```

### Task 6: Broker Error And Operator Advisory Taxonomy

Owner: Broker Error And Advisory Agent

Reviewers:

- Alpaca Agent
- Product Manager
- Coordinator

Deliverable:

```text
Canonical broker error taxonomy with operator advisory messages.
```

Required error families:

- authentication
- authorization
- missing credentials
- mode mismatch
- buying power
- margin
- short-sale restriction
- not easy to borrow
- asset not tradable
- asset not fractionable
- market closed
- extended-hours unsupported
- unsupported order type
- unsupported time in force
- unsupported order class
- invalid price
- invalid quantity
- invalid notional
- duplicate client order id
- rate limited
- broker unavailable
- stream disconnected
- order rejected
- order canceled externally
- stale BrokerSync
- unknown broker response

Expected backend output:

```text
BrokerErrorCode
BrokerErrorFamily
BrokerErrorSeverity
BrokerOperatorAdvisory
BrokerFailureEvent
```

Coordinator gate:

```text
The operator must know what failed, where it failed, whether it is retryable,
and what to check next.
```

### Task 7: Market Rules And Session Preflight

Owner: Market Rules And Session Agent

Reviewers:

- Alpaca Order Compliance Agent
- Alpaca Agent
- Full Stack Developer
- Coordinator

Deliverable:

```text
Provider-aware market rules preflight contract.
```

Required checks:

- market clock
- regular-hours eligibility
- extended-hours eligibility
- fractional eligibility
- notional vs quantity exclusivity
- shorting eligibility
- easy-to-borrow status
- buying power estimate
- crypto 24/7 behavior
- options day-only behavior
- OTC limitations
- asset tradable status
- account mode/provider compatibility

Expected backend output:

```text
MarketRulePreflightRequest
MarketRulePreflightResult
MarketRuleViolation
MarketSessionState
```

Coordinator gate:

```text
Market/session rules are enforced before BrokerAdapter submission when they are
knowable from local Account, asset, clock, and provider capability state.
```

### Task 8: Unified Computation Plan

Owner: Full Stack Developer

Reviewers:

- Angry Architect
- Product Manager
- Coordinator

Deliverable:

```text
Plan proving backtest, sim, optimization, walk-forward, Chart Lab, and live use
one Feature Engine and SignalPlan path.
```

### Task 9: Watchlist Source Contract

Owner: Product Manager

Reviewers:

- Full Stack Developer
- Angry Architect
- Coordinator

Deliverable:

```text
Watchlist static/dynamic/provider-backed contract, including Yahoo source rules.
```

### Task 10: Stream Runtime Contract

Owner: Alpaca Agent

Reviewers:

- Full Stack Developer
- Product Manager
- Coordinator

Deliverable:

```text
Live Stock Market Data Stream and Account Trade Sync startup/monitoring
contract.
```

### Task 11: Operation Acceptance Checklist

Owner: Coordinator

Reviewers:

- Angry Architect
- Product Manager
- Alpaca Agent
- Alpaca Order Compliance Agent
- Broker Error And Advisory Agent
- Market Rules And Session Agent
- Full Stack Developer

Deliverable:

```text
Final backend lockdown checklist with pass/fail status.
```

## Implementation Order

Agents must work in this order unless the Coordinator changes priority:

1. Backend Reality Map
2. Core Domain Contract Lock
3. Multi-Leg SignalPlan Lock
4. SignalPlan to Account Evaluation to Governor flow
5. Order Ledger lineage
6. Alpaca boundary audit
7. Alpaca order capability matrix
8. Broker error and operator advisory taxonomy
9. Market/session/rules preflight
10. Unified computation plan
11. Watchlist source contract
12. Stream runtime contract
13. Operations snapshot contract
14. Research and promotion alignment
15. Final acceptance checklist

## Definition Of Done

Operation Turtle Shell is done when:

- core contracts are explicit
- old names are identified and contained
- multi-leg SignalPlans are represented as one lifecycle
- Account Evaluation and Governor flow is locked
- Order Ledger lineage is locked
- Alpaca boundaries are confirmed
- Alpaca order types, order classes, TIFs, and asset-class constraints are
  mapped
- broker error codes and operator advisory messages are canonical
- market/session/fractional/shorting/buying-power rules have a preflight
  contract
- Feature Engine unification is planned
- Watchlists have a provider-backed source model
- Live Stock Market Data Stream and Account Trade Sync are clearly separated
- research systems produce evidence, not alternate runtime truth
- Operations can expose all critical backend status
- Coordinator and Angry Architect both approve

## Final Warning From The Angry Architect

Do not make a second runtime.

Do not hide broker truth.

Do not create a new saved entity because a field felt complicated.

Do not let paper/live split the architecture.

Do not let UI needs corrupt backend contracts.

Build the spine first. Everything else hangs from it.
