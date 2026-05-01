# Deployment should bind the full executable package:

Deployment
- StrategyVersion
- StrategyControlsVersion
- ExecutionPlanVersion
- WatchlistSnapshot / Watchlist policy
- Subscribed Accounts

That is the clean spine. Strategy stays reusable, Controls define when it can act, Execution Plan defines how orders are expressed, and Watchlist defines what symbols are eligible. Your existing doctrine already says Strategy must not own Account risk, money, broker positions, final size, or final execution decision, while Deployment owns Strategy reference, Watchlists, subscribed Accounts, runtime overrides, and emitted SignalPlans.

Below is the robust plan I would give the agents.

# Ultimate Trader Executable Strategy Spine Plan


Risk & Governor Model
Risk Plan

Defines policy limits:

max positions
max exposure
max open risk
concentration
etc.

Multiple Risk Plans may exist per Account (e.g. scalping vs swing).

RiskResolver

Calculates:

position size
max loss
exposure impact
buying power requirement
Governor

Final enforcement gate:

checks live account state
enforces limits
blocks unsafe trades

Core rule:

No order reaches BrokerAdapter without Governor approval.
Cross-System Consistency


## Core Decision

A Deployment must bind the complete executable strategy package:

- `strategy_version_id`
- `strategy_controls_version_id`
- `execution_plan_version_id`
- `watchlist_snapshot_id` or watchlist refresh policy
- subscribed `account_ids`

This makes Deployment the runtime package that publishes SignalPlans, while Accounts independently decide whether to act.

## Final Spine

```text
StrategyVersion
+ StrategyControlsVersion
+ ExecutionPlanVersion
+ WatchlistSnapshot
-> Deployment
-> SignalPlan
-> Account Evaluation
-> RiskResolver
-> Governor
-> OrderManager
-> BrokerAdapter
-> BrokerSync
-> Position Truth
-> Operations Center
Domain Separation
StrategyVersion = What setup qualifies

Owns:

required features
entry logic
stop logic
target logic
runner logic
logical exit logic
signal rules
feature references

Does not own:

symbols
final quantity
broker credentials
account risk
live positions
final approval
StrategyControlsVersion = When the strategy may act

Owns:

trading horizon
allowed directions
trading windows
no-new-entry-after time
force-flat-by time
time-based exits
cooldowns
max trades per session
regular/extended-hours preference
higher-timeframe confirmation requirement
regime filter references

Controls are enforced before SignalPlan creation.

ExecutionPlanVersion = How the plan becomes orders

Owns:

entry order type
stop order type
target order type
OCO/bracket/staged behavior
post-fill placement policy
replacement behavior
order offsets
time-in-force preferences
partial-fill handling policy

Execution Plan does not create signals. It translates SignalPlans into broker-valid order instructions.

WatchlistSnapshot = What symbols are eligible

Owns:

symbol set
source lineage
screener run id if generated
timestamp
added/removed diff
provider evidence
staleness status

Watchlist changes affect new entries only. Existing positions remain Account-owned.

Required Persisted Entities
1. StrategyVersion

Already exists, but must reference:

strategy_controls_version_id
execution_plan_version_id

Or Deployment must bind those independently. Preferred:

StrategyVersion = pure logic
Deployment = binds StrategyVersion + ControlsVersion + ExecutionPlanVersion

This allows the same StrategyVersion to run with different controls or execution plans.

2. StrategyControlsVersion

Add:

table: strategy_controls_versions
record: StrategyControlsVersionRecord
service: StrategyControlsService
repository: StrategyControlsRepository

Immutable. New edit creates new version.

3. ExecutionPlanVersion

Add:

table: execution_plan_versions
record: ExecutionPlanVersionRecord
service: ExecutionPlanService
repository: ExecutionPlanRepository

Immutable. New edit creates new version.

4. Deployment Binding

Deployment must include:

deployment_id
strategy_version_id
strategy_controls_version_id
execution_plan_version_id
watchlist_ids
active_watchlist_snapshot_ids
subscribed_account_ids
runtime_status

Deployment must not own Account money, broker truth, final size, or positions.

Runtime Flow
1. Deployment starts

Load exact versions:

StrategyVersion
StrategyControlsVersion
ExecutionPlanVersion
WatchlistSnapshot
Subscribed Accounts

Validate:

StrategyVersion exists and is frozen
ControlsVersion exists
ExecutionPlanVersion exists
WatchlistSnapshot has symbols
Accounts exist and are valid
Market data provider supports required symbols/timeframes
Account Trade Sync is visible for each Account
Live Stock Market Data Stream is healthy

The platform requires one live stock market data stream and one trade sync stream per Account.

2. Market data arrives

Feature Engine computes required features from StrategyVersion.

No feature list from UI should drive runtime. Saved StrategyVersion is the source of truth.

3. Strategy evaluates

Strategy logic checks:

features
entry rules
stop/target logical definitions
logical exit rules
4. StrategyControls gate

Before SignalPlan creation, Controls check:

allowed direction
trading window
cooldown
max trades/session
no-new-entry-after
force-flat rules
session preference
time-based exit rules

If controls fail, no opening SignalPlan is produced.

5. Deployment emits SignalPlan

SignalPlan must include:

signal_plan_id
deployment_id
strategy_id
strategy_version_id
watchlist_snapshot_id
symbol
side
intent
entry
stop
targets
runner
logical_exit
expires_at
feature_snapshot
reason

The SignalPlan contract already includes symbol, entry, stop, targets, runner, and logical exit fields.

SignalPlan remains neutral. It does not contain final Account quantity.

Execution Handling
Example

Operator wants:

Market entry
Stop 5% below fill
Target 10% above fill

Strategy defines:

stop_plan:
  type: percent_from_entry_fill
  value: 5

target_plan:
  type: percent_from_entry_fill
  value: 10

ExecutionPlan defines:

entry:
  order_type: market

stop_order:
  order_type: stop_market
  placement: after_entry_fill

target_order:
  order_type: limit
  placement: after_entry_fill

placement_policy:
  type: post_fill_bracket

SignalPlan carries logical stop/target intent.

OrderManager waits for fill if needed.

BrokerSync confirms fill price.

Then ExecutionPlan calculates:

Long fill at 100:
stop = 95
target = 110

Short fill at 100:
stop = 105
target = 90
Preferred Broker Approach

Use post-fill bracket placement, not native Alpaca bracket first.

Reason:

handles partial fills better
symmetric for long and short
aligns with BrokerSync as truth writer
keeps execution behavior deterministic
lets OrderManager create children after confirmed fill

BrokerSync must remain the writer of broker-derived order/fill/position truth.

Account Evaluation

Each subscribed Account evaluates every SignalPlan independently.

Account Evaluation checks:

account pause
account restrictions
symbol restrictions
existing positions
open orders
whether SignalPlan opens or manages a position

Many Accounts can evaluate one SignalPlan differently.

RiskResolver

RiskResolver computes final Account-specific size.

Inputs:

SignalPlan
StrategyControlsVersion
ExecutionPlanVersion
Account risk config
Account buying power
existing positions
open orders
stop distance
target distribution
runner exposure

RiskResolver is the first place final quantity may appear.

For percent-from-fill stops, estimated stop distance can be calculated from expected entry reference, then finalized after fill.

Governor

Governor is final Account protection gate before OrderManager.

Checks:

sync freshness
buying power
restrictions
daily loss
drawdown
concentration
max open positions
duplicate execution
global kill
Account pause
Deployment pause
SignalPlan expiration

No broker order reaches BrokerAdapter without Governor approval.

OrderManager

OrderManager creates internal orders only after Governor approval.

Required order lineage:

account_id
deployment_id
strategy_id
strategy_version_id
strategy_controls_version_id
execution_plan_version_id
signal_plan_id
opening_signal_plan_id
current_signal_plan_id
position_lineage_id
account_evaluation_id
governor_decision_id
lifecycle_intent
leg_label

Internal orders must link to SignalPlan and Position lineage.

BrokerAdapter

BrokerAdapter submits/cancels/replaces broker orders only.

It must not:

create internal orders
size trades
approve trades
mutate broker truth
bypass BrokerSync
BrokerSync

BrokerSync writes:

order status
broker order mapping
fills
positions
account snapshots
sync freshness

When fill arrives:

BrokerSync records fill
-> emits internal fill event
-> OrderManager / ExecutionPlan handler creates child stop/target orders if required
-> BrokerAdapter submits children
-> BrokerSync reconciles child order truth
Position Behavior

Positions are Account-owned.

Existing positions must continue to be managed even if:

symbol leaves Watchlist
ControlsVersion changes
ExecutionPlanVersion changes
Deployment entry universe refreshes

Position explanation context must show why the position exists, which SignalPlan opened it, what Account risk rules applied, and which orders/fills changed it.

Cross-Lab Handling
Chart Lab

Purpose:

visual signal and rule inspection

Uses:

StrategyVersion
StrategyControlsVersion
ExecutionPlanVersion
selected symbols / snapshot

Behavior:

shows where entries would trigger
overlays stops/targets from ExecutionPlan
no broker calls
no real orders
no Account risk approval

Chart Lab must use the same Feature Engine and SignalPlan path as runtime, but stop before Account Evaluation.

Sim Lab

Purpose:

forward or historical simulation with fake orders/fills

Uses full package:

StrategyVersion
StrategyControlsVersion
ExecutionPlanVersion
WatchlistSnapshot
Simulated Account Risk

Behavior:

produces simulated SignalPlans
runs simulated Account Evaluation
runs RiskResolver
applies simulated Governor
creates simulated orders/fills/positions
tests post-fill stop/target placement logic

Sim Lab must not call brokers.

Backtest

Purpose:

historical replay

Uses exact package:

StrategyVersion
StrategyControlsVersion
ExecutionPlanVersion
WatchlistSnapshot
data range
cost model
slippage model

Must record:

strategy version
controls version
execution plan version
watchlist snapshot
feature engine version
assumptions
warnings
metrics
reproducibility key

Backtest must not use a separate backtest-only strategy path.

Optimization Lab

Purpose:

tune parameters

Allowed:

tune Strategy parameters
tune StrategyControls parameters
tune ExecutionPlan parameters within the selected plan family
tune stop percent, target percent, ATR multiple, offsets, cooldown, windows

Not allowed by default:

switching between unrelated execution plan families inside one optimization run unless explicitly configured as a comparison study

Output:

OptimizationRun
- base package fingerprint
- parameter search space
- best candidate package
- metrics
- overfit warnings

Optimization must produce evidence, not mutate live Deployment.

Walk-Forward

Purpose:

robustness validation

Uses:

StrategyVersion
StrategyControlsVersion
ExecutionPlanVersion
WatchlistSnapshot policy

Rules:

train window may optimize parameters
test window must use frozen chosen package
each fold records exact package versions
execution plan family should remain fixed unless the walk-forward study explicitly compares execution families

Output:

WalkForwardRun
- folds
- package per fold
- metrics
- degradation
- warnings
Promotion Gate

Promotion should require or warn on evidence:

Chart Lab preview
Backtest
Sim Lab
Optimization
Walk-Forward
Paper Deployment evidence

Promotion must answer:

is Strategy ready for paper?
is Strategy ready for live Account subscription?
what package versions were validated?
did validation use the same ExecutionPlanVersion?
are controls different from tested controls?
are warnings present?

Research systems must produce evidence, not alternate runtime truth.

Deployment Update Behavior
Updating Controls

Default:

Apply after current session

Affects:

new SignalPlan production

Does not affect:

existing positions
historical SignalPlans
filled orders
Updating ExecutionPlan

Default:

Apply to new SignalPlans only

Can optionally allow:

Apply now to new child orders only
Apply after current position closes
Apply after current session

Never silently rewrites existing broker orders.

Updating Watchlist

Affects:

new entries only

Does not affect:

existing positions
position-management SignalPlans
Updating Strategy

Default:

requires new Deployment version or explicit deployment package update

Because Strategy logic changes what qualifies as a trade idea.

Audit Model

Every major event must produce an audit record:

DeploymentPackageCreated
DeploymentPackageUpdated
ControlsVersionChanged
ExecutionPlanVersionChanged
WatchlistSnapshotChanged
SignalPlanPublished
AccountEvaluationCompleted
RiskResolved
GovernorDecisionMade
OrderCreated
BrokerOrderSubmitted
BrokerFillSynced
PositionUpdated

Each audit record should include:

old_version_ids
new_version_ids
operator_id
reason
timestamp
apply_mode
affected_deployment_id
Required API Additions
Strategy Controls
POST /api/v1/strategy-controls
GET  /api/v1/strategy-controls/{id}/versions
POST /api/v1/strategy-controls/{id}/versions
Execution Plans
POST /api/v1/execution-plans
GET  /api/v1/execution-plans/{id}/versions
POST /api/v1/execution-plans/{id}/versions
Deployment Package
GET  /api/v1/deployments/{id}/package
POST /api/v1/deployments/{id}/package/update
POST /api/v1/deployments/{id}/apply-controls-version
POST /api/v1/deployments/{id}/apply-execution-plan-version
POST /api/v1/deployments/{id}/refresh-watchlist-snapshot
Research Evidence
POST /api/v1/chart-lab/previews
POST /api/v1/backtests
POST /api/v1/sim-lab/runs
POST /api/v1/optimizations
POST /api/v1/walk-forward/runs
GET  /api/v1/strategies/{id}/evidence
Required Slices
Slice 1: Persistence Package

Add:

StrategyControlsVersion persistence
ExecutionPlanVersion persistence
Deployment package binding
save/reload wiring
audit events

No runtime behavior yet.

Slice 2: Compose + Editor Wiring

Add UI fields for:

Stop Plan
Target Plan
Execution Plan
Strategy Controls
Package preview

Ensure save/reload works.

Slice 3: Runtime Package Loader

Deployment loads exact:

StrategyVersion
StrategyControlsVersion
ExecutionPlanVersion
WatchlistSnapshot

Reject invalid/missing package.

Slice 4: SignalPlan Enrichment

SignalPlanBuilder produces:

entry
stop
targets
runner
logical exits
watchlist snapshot lineage
controls/execution metadata references
Slice 5: Order Translation Layer

Add:

SignalPlan + ExecutionPlan -> InternalOrder instructions

Support:

market entry
percent-from-fill stop
percent-from-fill target
long and short
post-fill bracket placement
Slice 6: Broker Paper Verification

Test with Alpaca paper:

long market + stop/target
short market + stop/target
partial fill behavior
cancel/replace behavior
rejection handling
Slice 7: Cross-Lab Alignment

Chart Lab, Sim Lab, Backtest, Optimization, Walk-Forward all consume the same executable package.

Slice 8: Promotion Gate Alignment

Promotion checks whether evidence used the same package versions as the candidate Deployment.

Required Tests
Persistence Tests
controls save/reload
execution plan save/reload
deployment package save/reload
immutable version creation
no orphan version refs
SignalPlan Tests
long market entry with 5 percent stop and 10 percent target
short market entry with mirrored stop/target
SignalPlan contains no final Account quantity
SignalPlan references Strategy/Controls/Execution/Watchlist lineage
RiskResolver Tests
stop distance from percent stop
stop distance from ATR stop
long/short symmetry
runner and target exposure
Governor Tests
rejects expired SignalPlan
rejects paused Account
rejects stale sync
rejects duplicate execution
approves valid bracket SignalPlan
OrderManager Tests
creates entry order
waits for fill when stop/target relative to fill
creates stop/target children after fill
handles partial fill
preserves lineage
Broker Tests
Alpaca market order submission
child stop order submission
child target order submission
short-side behavior
rejection handling
BrokerSync fill reconciliation
Research Tests
Chart Lab renders same stop/target logic
Backtest uses same ExecutionPlanVersion
Sim Lab uses same post-fill behavior
Optimization does not mutate live package
Walk-Forward records package per fold
Non-Negotiables
No symbols inside Strategy
No Account risk inside Strategy
No execution mechanics buried inside Strategy logic
No Strategy Controls inside SignalPlan as enforcement logic
No final quantity inside SignalPlan
No broker truth outside BrokerSync
No direct provider calls from frontend
No separate backtest-only execution path
No hidden runtime package changes
Final Approval Statement


## Risk Horizon and Account RiskPlan Doctrine

A Deployment does not own the final RiskPlan.

A Deployment declares the intended risk horizon for the run:

- scalping
- intraday
- swing
- position
- other

Each Account owns its own RiskPlan mapping by horizon.

```text
AccountRiskPlanMap
  scalping -> RiskPlanVersion
  intraday -> RiskPlanVersion
  swing -> RiskPlanVersion
  position -> RiskPlanVersion
  other -> RiskPlanVersion

When a Deployment publishes a SignalPlan, each subscribed Account resolves risk independently:

Deployment.risk_horizon
-> Account.risk_plan_for_horizon
-> RiskResolver
-> Governor
-> OrderManager

This allows multiple Accounts to subscribe to the same Deployment while applying different risk appetites.

Example:

Deployment A
  Strategy: RSI Pullback
  Controls: 09:30-16:00
  ExecutionPlan: Market Entry + Bracket
  Watchlist: Premarket Gappers
  Risk Horizon: swing

Account 1
  swing -> Conservative Swing Risk Plan

Account 2
  swing -> Aggressive Swing Risk Plan

Both Accounts receive the same SignalPlan, but size, exposure, and approval can differ.

Rules
Strategy may suggest an ideal horizon, but does not enforce it.
Deployment selects the active risk horizon.
Account owns the RiskPlan mappings.
RiskResolver uses the Account’s mapped RiskPlan for the Deployment horizon.
Governor remains the final Account protection gate.
If an Account has no RiskPlan for the Deployment horizon and no other fallback, the Account must reject or ignore the SignalPlan.
The operator must see which RiskPlan each Account resolved for the Deployment.

correction:

```text
Deployment chooses horizon.
Account chooses risk plan.
Governor enforces.

Approve the executable package model:

Deployment = StrategyVersion + StrategyControlsVersion + ExecutionPlanVersion + WatchlistSnapshot + Accounts

This is the correct production-grade model.

It supports:

strategy reuse
control-only updates
execution-only updates
dynamic Watchlists
auditability
backtest/sim/live parity
safer optimization and walk-forward validation
explainable positions
broker-safe order translation


addition: 

ExecutionPlan decides preferred order expression

Examples:

market exit during regular session
limit exit during extended hours
stop-market during regular session
stop-limit during extended hours
4. Broker/Market preflight enforces what is actually allowed

Examples:

market order rejected in extended hours
short sale restriction
fractional rules
TIF rules
asset tradability
Add this to ExecutionPlan
exit_order_policy:
  regular_hours:
    order_type: market
    time_in_force: day

  extended_hours:
    order_type: limit
    time_in_force: day
    extended_hours: true
    limit_price_source: bid_ask_offset
    offset_bps: 20

  fallback:
    if_market_order_not_allowed: convert_to_limit
    if_no_quote_available: require_operator

For force-flat:

force_flat_policy:
  regular_hours:
    order_type: market

  extended_hours:
    order_type: limit
    limit_price_source: bid_ask_offset
Important rule

StrategyControls should not know Alpaca order rules.

It can say:

flatten at 16:05

But it should not say:

use extended-hours limit order

That’s execution and market-rule territory.

Final doctrine line
Trading windows trigger eligibility and time-based actions.
ExecutionPlan translates those actions into order preferences.
MarketRulePreflight validates and adapts them to broker/session rules.

Approved By Nanyel 4/29/2026