System Unification Output
1. Final Mental Model
The system has three truths:

Program truth
What should be traded.

Governor truth
Whether the system is allowed to trade it.

Broker truth
What actually exists at the broker.

Everything else is support machinery.

Final model:

Program defines intent.
Deployment runs intent.
Feature Engine computes facts.
Signal Engine emits candidate trade intent.
Governor approves or rejects.
Execution Engine builds orders.
Broker Adapter sends orders.
Broker Account reports truth.
There is no second runtime path. There is no allocation-runtime hybrid. There is no strategy-direct-to-backtest/live shortcut. There is no broker call outside the broker adapter.

2. Design-Time Model
Design-time objects are reusable, versioned, and non-runtime.

Required design-time objects:

Object	Owns	Cannot Own
Strategy	Signal rules, feature requirements, entry/exit intent logic, stop/target candidates	Sizing, broker calls, session permission, order types
StrategyControls	Timeframe, session windows, cooldowns, event blackout, regime permission	Signal logic, sizing, broker calls
RiskProfile	Position sizing policy, loss limits, exposure limits	Signal logic, order mechanics, broker truth
ExecutionStyle	Order expression: market/limit/stop-limit, TIF, bracket, trailing, scale-out mechanics	Signal truth, portfolio approval, risk budget
Universe	Tradable symbol source and resolution rules	Signal logic, risk, execution
Program	References to exact component versions	Inline behavior of any kind
Watchlist becomes a source for Universe. It is not itself the full runtime universe contract.

Final Program shape:

Program
  id
  name
  version
  status: draft | frozen | deprecated
  strategy_version_id
  strategy_controls_version_id
  risk_profile_version_id
  execution_style_version_id
  universe_version_id
  created_at
  frozen_at
Program may contain:

metadata
version
component references
frozen snapshot ids
validation status summary
Program may not contain:

inline indicators
inline conditions
inline risk settings
inline execution policy
inline session settings
inline symbol lists except through a frozen Universe reference
runtime state
broker account id
deployment status
live universe cache
promotion state beyond eligibility summary
3. Runtime Model
Deployment is the only runtime unit.

Final runtime objects:

Object	Purpose
Deployment	Runs one frozen Program on one Broker Account under one Portfolio Governor
PortfolioGovernor	Final internal authority for new exposure
BrokerAccount	Broker-facing account and broker truth
Order	Internal durable order record mapped to broker order
Trade	Durable trade/fill lifecycle record
RuntimeState	Deployment health, stream freshness, feature warmup, last decision
AccountAllocation is killed as a runtime object.

If the concept is still needed, it is redefined strictly as:

CapitalAllocationPolicy
  broker_account_id
  program_id
  max_allocated_capital
  max_position_pct
  notes
It has no lifecycle. It cannot be started, paused, promoted, stopped, killed, or monitored. It is an input to the Governor, not a runtime unit.

4. Signal-to-Order Flow (Exact)
The chain is fixed:

Market Data Stream
→ Bar Builder
→ Feature Engine
→ Signal Engine
→ Strategy Controls Gate
→ Risk Engine
→ Execution Intent Builder
→ Portfolio Governor
→ Order Manager
→ Broker Adapter
→ Alpaca
→ Broker Sync
→ Order Ledger / Trade Ledger
→ Monitor
Exact responsibilities:

Market Data Stream
Receives raw ticks/bars from provider.

Bar Builder
Normalizes timestamps, symbols, sessions, and timeframes.

Feature Engine
Computes all required features from the active Deployment feature plan.

Signal Engine
Reads features and evaluates Strategy rules.

Signal Engine stops at:

CandidateTradeIntent
Signal Engine may emit:

symbol
side
entry intent
exit intent
signal timestamp
feature values used
stop candidate
target candidate
confidence/diagnostics if available
Signal Engine may not:

size the position
choose order type
call Alpaca
check account buying power
approve portfolio exposure
mutate deployment state
Strategy Controls Gate
Allows or blocks the candidate based on time/session/cooldown/event/regime rules.

Risk Engine
Converts candidate intent into risk-bounded sizing or rejects it.

Execution Intent Builder
Applies Execution Style and creates a normalized order intent.

Portfolio Governor
Performs final approval using current and projected portfolio state.

Order Manager
Creates internal durable Order records before broker submission.

Broker Adapter
The only layer allowed to call Alpaca.

Alpaca
External broker.

Broker Sync
Reconciles broker orders, fills, positions, restrictions, buying power.

Ledgers
Order and Trade ledgers are updated from broker truth.

Who calls Alpaca:

Only Broker Adapter.
No route, service, governor, strategy, deployment loop, monitor page, or execution style may call Alpaca directly.

5. Governor vs Broker Account (Final Decision)
Governor is separate: yes.

They are different entities and must never be merged.

Portfolio Governor Owns
The Governor owns internal permission.

It owns:

final approval/rejection for new exposure
projected post-trade exposure checks
account-wide and portfolio-wide risk constraints
cross-program symbol conflict checks
correlation/concentration limits
daily loss lockout
drawdown lockout
pause state for governed scope
kill state interpretation for new opens
decision log
rejection reasons
protective-exit allowance rules
It does not own:

broker credentials
broker balances as source of truth
broker positions as source of truth
broker order submission
signal computation
feature computation
order mechanics
strategy definitions
Broker Account Owns
Broker Account owns external broker truth.

It owns:

broker identity
paper/live mode
encrypted broker credentials
broker balances
buying power
broker positions
broker orders
broker fills
broker restrictions
PDT status
account sync freshness
It does not own:

risk policy
strategy permission
final approval rules
program lifecycle
signal logic
execution style
kill/pause semantics, except as observed state from broker if broker itself restricts trading
Final relationship:

BrokerAccount has one or more Deployments.
PortfolioGovernor governs one BrokerAccount or portfolio scope.
Deployment references exactly one PortfolioGovernor.
PortfolioGovernor reads BrokerAccount truth but does not become BrokerAccount.
6. Deployment Model (Final)
Deployment is the only thing that runs.

Final shape:

Deployment
  id
  program_version_id
  broker_account_id
  portfolio_governor_id
  mode: paper | live
  status: created | warming | running | paused | stopping | stopped | failed
  feature_plan_id
  started_at
  paused_at
  stopped_at
  last_heartbeat_at
  last_market_data_at
  last_broker_sync_at
Deployment owns:

runtime lifecycle
link to frozen Program
link to Broker Account
link to Portfolio Governor
active feature plan
runtime health
stream freshness
warmup state
last decision timestamps
Deployment does not own:

strategy logic
controls logic
risk policy
execution policy
portfolio authority
broker truth
capital allocation lifecycle
promotion workflow
Allowed Deployment actions:

create from frozen Program
warm up
start
pause new opens
resume new opens
stop
fail
restart from persisted state
Forbidden Deployment actions:

mutate Program components
bypass Governor
submit broker orders directly
hold inline risk overrides
act as Portfolio Governor
act as Broker Account
7. Streaming + Data Flow
Market data streaming is owned by the Market Data Service.

The Market Data Service owns:

provider connections
subscriptions
raw message ingestion
reconnects
provider error handling
stream freshness
raw event normalization
It does not compute trading features.

Streaming flow:

Provider Stream
→ Market Data Service
→ Normalized Market Event
→ Bar Builder
→ Runtime Bar Store
→ Feature Engine
→ Feature Cache
→ Signal Engine notification
Feature Engine receives completed normalized bars, not raw provider chaos.

Rules:

Raw provider messages never go directly to Strategy.
Raw provider messages never go directly to Signal Engine.
Feature Engine never owns websocket/provider credentials.
Market Data Service never computes RSI, EMA, ATR, VWAP, regimes, or portfolio features.
Bar Builder is responsible for timeframe aggregation and session-aware bar completion.
Feature Engine is responsible for feature computation and cache updates.
Signal Engine runs only after required features are warm and current.
Broker streaming is separate.

Broker stream flow:

Alpaca Account Stream
→ Broker Adapter
→ Broker Sync
→ Order Ledger / Trade Ledger / BrokerAccount snapshot
→ Portfolio Governor state refresh
→ Operations Center
Market data stream and broker account stream must not be merged into one undifferentiated event bus.

8. Simplified Architecture (No fluff)
Keep these layers only:

1. Design-Time
   Strategy
   StrategyControls
   RiskProfile
   ExecutionStyle
   Universe
   Program

2. Data + Features
   MarketDataService
   BarBuilder
   FeatureEngine
   FeatureCache

3. Decision
   SignalEngine
   StrategyControlsGate
   RiskEngine
   ExecutionIntentBuilder
   PortfolioGovernor

4. Execution
   OrderManager
   BrokerAdapter
   BrokerAccount
   OrderLedger
   TradeLedger

5. Runtime
   Deployment
   RuntimeState
   OperationsCenter

6. Validation
   ChartLab
   SimLab
   Backtest
   Optimize
   WalkForward
   ValidationEvidence
Remove or collapse these as independent architectural concepts:

AccountAllocation as runtime
separate DeploymentManager authority
separate AccountGovernor authority
separate LiveMonitor authority
ProgramBacklogItem from trading-domain language
DataService mixing AI and market data providers
route aliases that imply different concepts for the same page
direct backtest/simulation strategy execution paths that skip Program resolution
any service that calls Alpaca outside Broker Adapter
Minimal correct product navigation:

Build
  Strategies
  Components
  Universes
  Programs

Validate
  Chart Lab
  Sim Lab
  Backtest
  Optimize
  Walk-Forward
  Evidence

Operate
  Deployments
  Operations Center
  Portfolio Governor

Admin
  Broker Accounts
  Providers
  Audit Logs
  Backup
9. Hard Rules (Non-negotiable)
Governor and Broker Account are separate entities.

Broker Account is broker truth only.

Portfolio Governor is final internal authority only.

Deployment is the only runtime unit.

AccountAllocation is not a runtime entity and cannot have lifecycle actions.

Program contains references only. No inline behavior.

Every Program must reference exact frozen component versions.

No Strategy can compute features.

No Signal Engine path can size, approve, build, or submit orders.

Feature Engine is the only feature computation layer.

Market Data Service owns streaming connections, not feature computation.

Bar Builder owns normalization and timeframe aggregation.

Signal Engine consumes Feature Engine outputs only.

Risk Engine sizes or rejects; it does not approve portfolio exposure.

Execution Intent Builder shapes order intent; it does not submit orders.

Portfolio Governor must approve every new exposure.

Order Manager must create an internal order before broker submission.

Broker Adapter is the only Alpaca caller.

Broker Sync is the only updater of broker-truth snapshots.

Protective exits are allowed during pause/kill unless explicitly blocked by broker truth.

Kill/pause stops new opens; flatten closes positions. These are never the same action.

Unknown order intent is never canceled automatically.

Chart Lab validates signals only.

Sim Lab validates execution only.

Backtest, Sim Lab, Paper, and Live must use the same Feature Engine and Signal Engine contracts.

Operations Center is the only authoritative runtime UI.

Historical evidence must reference immutable Program/component versions.

No live Deployment may start without frozen Program, Feature Plan, Portfolio Governor, Broker Account, and Order Ledger enabled.