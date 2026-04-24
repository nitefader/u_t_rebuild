Sim Lab Output
1. Final Sim Lab Definition
Sim Lab is the full Program simulation surface.

It answers one question:

If this frozen Program receives this market stream, how would it behave operationally?

Sim Lab is not Chart Lab and not Backtest.

Chart Lab validates signal truth visually.
Sim Lab validates execution behavior and runtime mechanics.
Backtest measures historical performance at scale.
Walk-Forward measures robustness across folds.
Sim Lab runs the complete Program stack without touching a real broker:

FeatureSnapshots
→ Signal Engine
→ Strategy Controls
→ Risk Profile
→ Execution Style
→ Simulated Order Manager
→ Simulated Broker
→ Simulated Position / Trade Ledger
→ Sim Metrics
Sim Lab must support two modes:

Historical Replay
Replay historical bars deterministically.

Live Stream
Run the Program against live market data using simulated execution.

Sim Lab never computes features independently. It consumes Feature Engine output only.

2. What Sim Lab Runs
Sim Lab runs a frozen Program.

Required Program components:

Component	Sim Lab Use
Strategy	Produces candidate signals through Signal Engine
StrategyControls	Blocks/allows signals based on session, cooldown, event, regime, trade caps
RiskProfile	Sizes or rejects candidate trades
ExecutionStyle	Converts approved trade intent into simulated orders
Universe	Provides symbols to simulate
PortfolioGovernor	Optional validation layer, required for paper/live rehearsal
Sim Lab simulates:

candidate signals
blocked signals
order creation
order lifecycle
fills
partial fills
slippage
stop behavior
target behavior
trailing behavior
scale-out behavior
position state
realized PnL
unrealized PnL
drawdown
exposure
buying-power simulation
session windows
cooldowns
max trades per session
event blackout behavior
governor approvals/rejections when enabled
Sim Lab does not simulate:

feature definitions
indicator semantics
real broker routing
real broker latency guarantees
real queue position
exchange microstructure beyond configured fill model
walk-forward folds
optimizer sweeps
3. Historical Replay Mode
Historical Replay mode is deterministic.

Input:

Frozen Program
symbol universe
date range
timeframe
FeaturePlan
FeatureSnapshots from batch/replay Feature Engine
simulation clock settings
fill model
slippage model
optional governor validation config
Output:

SimulationSession
SimulationEvents
SimulatedOrders
SimulatedFills
SimulatedPositions
SimulatedTrades
SimulationMetrics
ReplayTimeline
Replay clock:

paused
step one bar
step one event
play at speed
jump to next signal
jump to next fill
jump to next stop/target event
jump to next governor rejection
Historical Replay rules:

Sim Lab receives FeatureSnapshots timestamp by timestamp.
Signal Engine evaluates each symbol from snapshots.
Strategy Controls are evaluated at the simulation timestamp, not wall-clock time.
Risk Profile uses simulated account equity and simulated open risk.
Execution Style creates simulated order instructions.
Simulated Broker fills orders according to the configured fill model.
Stops/targets/trailing logic are simulated as order behavior, not strategy recomputation.
All events are written to the simulation event log.
Results are reproducible from the same input data, Program version, feature versions, calendar version, and fill model.
Sim Lab does not produce final statistical confidence. That belongs to Backtest and Walk-Forward.
Historical Replay is for inspection, debugging, and behavior validation.

It is not the authoritative performance engine.

4. Live Stream Mode
Live Stream mode simulates against live market data.

Input:

Frozen Program
live symbol universe
active market data stream
incremental Feature Engine updates
simulated account state
fill model
slippage model
optional governor validation config
Output:

LiveSimulationSession
FeatureUpdate timeline
candidate signals
simulated orders
simulated fills
simulated positions
live sim PnL
live sim exposure
stream freshness status
Live Stream flow:

Market Data Service
→ Bar Builder
→ Feature Engine incremental update
→ Sim Lab receives FeatureUpdate / FeatureSnapshot
→ Signal Engine evaluates
→ Program simulation flow runs
→ simulated broker updates positions/orders
→ UI updates
Live Stream rules:

No real broker orders are submitted.
Simulated Broker is mandatory.
Runtime Feature Engine must be warm before entry signals are allowed.
Stream stale state freezes new simulated entries.
Existing simulated protective orders may continue to be evaluated against incoming bars.
Live Stream mode must display stream freshness prominently.
Live Stream mode must never be labeled as paper or live trading.
Broker Account is optional only as a reference for buying-power assumptions. It is not used for execution.
Live Stream is a rehearsal surface.

It is not Paper Trading.

5. Program Simulation Flow
Exact Sim Lab chain:

FeatureSnapshot
→ Signal Engine
→ CandidateTradeIntent
→ StrategyControlsGate
→ RiskEngine
→ ExecutionIntentBuilder
→ optional PortfolioGovernor
→ SimulatedOrderManager
→ SimulatedBroker
→ SimulatedFillEngine
→ SimulatedPositionLedger
→ SimulatedTradeLedger
→ SimulationMetrics
→ SimulationEventLog
Signal Engine
Consumes FeatureSnapshots.

Emits:

CandidateTradeIntent
  timestamp
  symbol
  side
  intent_type: entry | exit
  signal_name
  feature_values_used
  stop_candidate
  target_candidate
  diagnostics
Stops there.

StrategyControlsGate
Emits:

allowed
blocked
block_reason
Block reasons must be explicit:

outside_session
cooldown_active
max_trades_reached
event_blackout
regime_block
feature_unavailable
RiskEngine
Emits:

RiskDecision
  approved | rejected
  qty
  notional
  risk_amount
  rejection_reason
ExecutionIntentBuilder
Emits:

ExecutionIntent
  order_type
  side
  qty
  limit_price
  stop_price
  time_in_force
  bracket_spec
  trailing_spec
  scale_out_spec
Optional PortfolioGovernor
Emits:

GovernorDecision
  approved | rejected
  reason
  projected_exposure
  projected_open_risk
  conflicts
SimulatedOrderManager
Creates durable simulated orders.

Order intents:

open
close
tp
sl
scale
SimulatedBroker
Owns simulated execution only.

It applies:

fill model
slippage model
partial-fill model
order status transitions
buying-power simulation
session restrictions
SimulatedFillEngine
Must support:

full fill
partial fill
no fill
gap-through stop
limit touch fill
limit miss
market fill with slippage
bracket parent/child activation
cancel after N bars
Ledgers
Sim Lab writes separate simulated ledgers, not real broker ledgers.

They must be exportable and comparable to backtest/paper later.

6. Governor Validation Mode
Governor validation is optional for early Sim Lab debugging and required for deployment rehearsal.

Modes:

off
advisory
enforced
Off
Governor is not evaluated.

Use only for strategy/execution debugging.

Advisory
Governor evaluates but does not block.

UI shows:

would_approve
would_reject
reason
Use for understanding portfolio constraints.

Enforced
Governor blocks simulated orders exactly as it would block paper/live orders.

Required before a Program can be marked paper-ready.

Governor validation uses simulated portfolio state:

current simulated positions
pending simulated orders
candidate order delta
projected post-trade exposure
projected post-trade risk
Governor validation must not read real broker positions unless the user explicitly selects a broker-account snapshot as the starting simulation state.

Hard rule:

Paper readiness requires Sim Lab Governor mode = enforced.
7. Multi-Symbol Handling
Programs may contain 50+ symbols. Sim Lab must treat this as normal.

Backend must process all symbols. UI must not show all symbols equally all the time.

Backend Symbol Handling
Simulation runs as a portfolio-level event engine.

Required backend structures:

SimulationSession
SimulationClock
SymbolSimulationState
PortfolioSimulationState
SimulationEventLog
SimulationIndex
Per-symbol state:

symbol
latest_timestamp
feature_warm_state
last_signal
open_orders
open_position
realized_pnl
unrealized_pnl
exposure
last_event_type
status
Portfolio state:

cash
equity
gross_exposure
net_exposure
open_risk
drawdown
active_positions_count
pending_orders_count
symbols_with_alerts
Event indexing is mandatory.

Index by:

timestamp
symbol
event_type
severity
decision_stage
Supported event types:

feature_unavailable
signal_candidate
signal_blocked
risk_rejected
governor_rejected
order_created
order_partially_filled
order_filled
order_canceled
stop_triggered
target_triggered
trailing_stop_updated
position_opened
position_scaled
position_closed
drawdown_alert
exposure_alert
stream_stale
UI Symbol Handling
Do not render 50 full charts.

UI must use progressive disclosure:

Portfolio Summary first
Shows global simulation state.

Event Stream second
Shows what changed and why.

Symbol Table third
One row per symbol.

Focused Symbol Detail
Only one selected symbol gets chart, orders, position, and signal trace.

Filters
Users can filter to:

symbols with positions
symbols with orders
symbols with signals
symbols with blocked signals
symbols with errors
symbols with governor rejections
top PnL movers
top exposure
stale feature state
Default UI should show:

All symbols summarized.
Only active/problem symbols expanded.
No giant grid of charts.
For 50+ symbols, the chart is not the primary UI. The event stream and symbol state table are.

8. UI Model
Sim Lab has one page with two modes:

Historical Replay
Live Stream
Top Bar
Always visible:

Program selector
Mode selector
Simulation status
Feature warm/stale status
Governor mode
Clock / timestamp
Start / pause / step controls
Portfolio Strip
Shows:

sim equity
cash
realized PnL
unrealized PnL
drawdown
gross exposure
open risk
active positions
pending orders
blocked signals count
Main Layout
Left: symbol/event navigation.

Center: focused symbol replay.

Right: decision inspector.

Symbol Table
Columns:

symbol
state
last price
last signal
position
open orders
unrealized PnL
realized PnL
exposure
blocked reason
feature state
Rows must be virtualized for large universes.

Event Stream
Events are grouped by timestamp.

Each event must show:

time
symbol
stage
decision
reason
impact
Clicking an event opens the Decision Inspector.

Focused Symbol Detail
Only for selected symbol:

price chart
signal markers
simulated orders
fills
position lifecycle
stop/target levels
feature values used
Chart data comes from Feature Engine and simulation ledgers.

Decision Inspector
For one timestamp/symbol:

FeatureSnapshot
Signal Engine result
StrategyControls decision
Risk decision
Execution intent
Governor decision
Order/fill outcome
Position impact
This is the most important Sim Lab debugging surface.

It must show where the chain stopped.

Required Empty/Error States
Program has unsupported streaming features
Feature warmup incomplete
No symbols resolved
Missing historical data
Stream stale
Governor rejected all candidates
No signals occurred
Fill model prevented fills
Session closed
No blank panels.

9. Backend API Requirements
Required API surface:

POST /sim-lab/sessions
GET  /sim-lab/sessions/{session_id}
POST /sim-lab/sessions/{session_id}/start
POST /sim-lab/sessions/{session_id}/pause
POST /sim-lab/sessions/{session_id}/step
POST /sim-lab/sessions/{session_id}/jump
POST /sim-lab/sessions/{session_id}/stop
GET  /sim-lab/sessions/{session_id}/events
GET  /sim-lab/sessions/{session_id}/symbols
GET  /sim-lab/sessions/{session_id}/symbols/{symbol}
GET  /sim-lab/sessions/{session_id}/orders
GET  /sim-lab/sessions/{session_id}/positions
GET  /sim-lab/sessions/{session_id}/metrics
GET  /sim-lab/sessions/{session_id}/decision-trace
WS   /sim-lab/sessions/{session_id}/stream
Create Session Request
program_version_id
mode: historical_replay | live_stream
symbols: optional override, must be subset of Program Universe
date_range: required for historical replay
timeframe
initial_cash
fill_model_id
slippage_model_id
partial_fill_model_id
governor_mode: off | advisory | enforced
initial_portfolio_state: empty | imported_snapshot
Session Response
session_id
status
mode
program_version_id
feature_plan_id
governor_mode
symbol_count
started_at
current_timestamp
portfolio_summary
feature_status
stream_status
Step Request
step_type: bar | event | signal | fill | rejection
count
Jump Request
target:
  timestamp
  next_signal
  next_fill
  next_rejection
  next_position_change
  next_error
Events API Filters
symbol
event_type
severity
stage
start_time
end_time
limit
cursor
Decision Trace API
Request:

session_id
symbol
timestamp
Response:

feature_snapshot
signal_decision
controls_decision
risk_decision
execution_intent
governor_decision
order_events
fill_events
position_state_after
metric_delta
10. Data + Feature Engine Integration
Sim Lab integrates with Feature Engine, never around it.

Historical Replay Integration
Sim Lab creates session
→ Feature Planner validates Program for sim_replay
→ Feature Engine computes or loads batch FeatureFrames
→ Sim Lab obtains replay snapshots
→ Simulation clock iterates snapshots
Sim Lab cannot launch if:

FeaturePlan invalid
missing historical bars
missing higher timeframe bars
unsupported feature for sim_replay
warmup cannot be satisfied
calendar unavailable
Live Stream Integration
Sim Lab creates live stream session
→ Feature Planner validates Program for sim_stream
→ Market Data Service subscribes to required symbols
→ Bar Builder emits normalized completed bars
→ Feature Engine updates runtime cache
→ Sim Lab receives FeatureUpdates / snapshots
→ Simulation engine advances
Sim Lab cannot start live stream if:

required feature lacks incremental support
market data stream unavailable
runtime warmup unavailable
symbol count exceeds configured stream subscription limit
calendar invalid
Feature Engine reports stale state
FeatureSnapshot Contract
Sim Lab receives:

timestamp
symbol
timeframe
features
availability
provenance
warm_state
alignment_info
Sim Lab must record which FeatureSnapshot caused each signal or block.

11. Acceptance Tests
Historical replay session cannot start without a frozen Program.

Historical replay session cannot start if Feature Planner rejects a feature.

Live stream session cannot start if any required feature lacks incremental support.

Sim Lab never calls indicator functions directly.

Sim Lab never calls Alpaca.

Signal Engine stops at CandidateTradeIntent.

StrategyControls block outside-session entries using simulation timestamp.

Cooldown blocks repeated entries for the same symbol according to StrategyControls.

Risk Profile sizes a candidate based on simulated equity, not real broker equity.

Execution Style creates bracket child orders when configured.

Partial-fill model can fill only part of an entry order.

Bracket stop/target quantities adjust correctly after partial fill.

Gap-through stop uses configured slippage model.

Limit order can remain unfilled and cancel after configured bars.

Trailing stop updates after favorable price movement.

Position state updates after fill.

Realized and unrealized PnL update separately.

Drawdown updates from simulated equity curve.

Exposure updates after partial fills and closes.

Governor advisory mode logs would-reject without blocking.

Governor enforced mode blocks rejected order intent.

Governor projected exposure includes pending simulated orders.

Historical replay produces identical results when replayed with same inputs.

Live stream stale state blocks new simulated entries.

Existing simulated protective orders continue to evaluate after new entries are blocked.

A 50-symbol Program renders portfolio summary without rendering 50 charts.

Symbol table virtualizes rows for large universes.

Event filters can isolate governor rejections.

Decision Inspector shows the exact stage where a candidate stopped.

No-signal sessions show a clear no-signal state, not an empty chart.

Missing higher-timeframe feature data blocks session start.

Feature warmup rows do not generate entry signals.

Simulated orders use intents: open, close, tp, sl, scale.

Simulated broker order ids never look like real broker order ids.

Sim Lab output is exportable as simulation evidence for promotion review.

12. First Implementation Tasks
Define SimulationSession as durable model
It must store:

mode
Program version
FeaturePlan id
governor mode
initial cash
fill/slippage models
status
current timestamp
Build Simulation Event Log
Every meaningful decision must emit a structured event.

No silent decisions.

Create Simulated Broker
Implement:

order states
fills
partial fills
stops
targets
brackets
trailing stops
cancel-after-bars
Create Simulated Ledgers
Separate from real broker ledgers:

simulated orders
simulated fills
simulated positions
simulated trades
Wire Historical Replay to FeatureSnapshots
Replace any direct indicator or bar-based condition evaluation.

Wire Live Stream to Runtime Feature Updates
Market stream goes through Market Data Service, Bar Builder, Feature Engine, then Sim Lab.

Implement Decision Trace
This is mandatory.

Every signal candidate must be traceable through:

features
signal
controls
risk
execution
governor
order/fill/position result
Implement Multi-Symbol Portfolio Engine
Process all symbols backend-side.

Do not make UI state the source of simulation truth.

Build Large-Universe UI Contract
Portfolio summary, event stream, symbol table, focused symbol detail.

No 50-chart layouts.

Add Governor Modes
Support:

off
advisory
enforced
Paper-readiness requires enforced mode.

Add Fill/Slippage Model Registry
Do not bury fill assumptions in random config fields.

Block Real Broker Calls
Sim Lab must have no import path or service dependency that can submit Alpaca orders.

Add Replay Determinism Test
Same inputs must produce identical event log, orders, fills, positions, and metrics.

Add Stream Staleness Test
When feature stream is stale, new entries stop and UI shows stale state.

Export Simulation Evidence
Simulation result must become validation evidence, not an isolated toy session.