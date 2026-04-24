Chart Lab Output
1. Final Chart Lab Definition
Chart Lab is the signal and component validation surface.

It answers one question:

Given this Program and this historical market context, why would the system want or not want a trade at this bar?

Chart Lab is not an execution simulator and not a performance engine.

Chart Lab displays:

bars
canonical Feature Engine outputs
multi-timeframe aligned features
signal markers
condition truth
signal non-fire reasons
Strategy Controls allow/block preview
Risk Profile sizing preview
Execution Style order-shape preview
Portfolio Governor allow/block preview
Chart Lab never advances simulated account state. It inspects decisions at bars.

2. What Chart Lab Can Validate
Chart Lab validates whether the Program components are coherent before simulation.

It can validate:

Area	Chart Lab Output
Historical bars	OHLCV chart from normalized market data
Feature availability	warmup, unavailable, stale, unsupported feature states
Feature correctness	canonical values from Feature Engine
Multi-timeframe alignment	which higher-timeframe bar was visible at each lower-timeframe bar
Strategy signal truth	condition-by-condition true/false
Signal marker placement	entry/exit candidate marker on chart
Non-fire reasons	which condition or missing feature prevented a signal
Strategy Controls preview	whether controls would allow/block candidate intent
Risk Profile preview	estimated size for one hypothetical candidate
Execution Style preview	order shape that would be produced from one candidate
Portfolio Governor preview	whether one hypothetical candidate would pass governor checks
Component completeness	whether Program references required frozen component versions
Feature compatibility	whether Program uses supported features for selected consumer mode
Chart Lab can answer:

Did the signal fire here?
Which condition caused it?
Which features were used?
Was the daily feature aligned correctly?
Was the ORB complete yet?
Would Strategy Controls block this bar?
What size would Risk Profile suggest?
What order shape would Execution Style create?
Would Governor allow this hypothetical candidate?
Chart Lab cannot answer:

Would this order fill?
What would PnL be?
How many positions would be open later?
Would drawdown breach after a sequence of trades?
How robust is this over many folds?
3. What Chart Lab Must Not Do
Chart Lab must not:

simulate fills
create simulated orders
partially fill orders
track positions
track account cash
update equity
show PnL curves
show drawdown curves
evolve exposure over time
replay order state
apply slippage models
model stop/target execution
model trailing stop movement after entry
perform portfolio accounting over a sequence
submit real broker orders
call Alpaca
compute features independently
define indicator semantics
replace Sim Lab
replace Backtest
replace Walk-Forward
mark a Program paper-ready by itself
Chart Lab may preview a stop candidate or target candidate as a visual level. It may not claim that either would have filled.

Chart Lab may preview an Execution Style bracket shape. It may not simulate bracket activation, partial fills, or child-order lifecycle.

Chart Lab may preview Governor allow/block for a single hypothetical candidate. It may not evolve Governor state through a sequence of trades.

4. Difference vs Sim Lab
Chart Lab validates signal and component interpretation.

Sim Lab validates runtime behavior.

Capability	Chart Lab	Sim Lab
Plot bars	Yes	Focused symbol only
Plot canonical features	Yes	Only as trace/support
Show condition truth	Yes	Yes, inside decision trace
Show why signal fired	Yes	Yes
Preview controls allow/block	Yes	Yes
Preview risk sizing	Yes, single candidate only	Yes, evolving simulated equity
Preview execution shape	Yes, static	Yes, full order lifecycle
Governor check	Single hypothetical candidate	Advisory/enforced over evolving simulated portfolio
Simulate orders	No	Yes
Simulate fills	No	Yes
Partial fills	No	Yes
Positions	No	Yes
PnL	No	Yes
Drawdown	No	Yes
Exposure over time	No	Yes
Replay clock	Bar inspection only	Full event/bar replay
Promotion evidence	Signal validation evidence only	Simulation evidence
Chart Lab stops at:

CandidateTradeIntent + component previews
Sim Lab continues through:

orders → fills → positions → PnL → exposure → event log
5. Difference vs Backtest
Chart Lab is inspection-oriented.

Backtest is measurement-oriented.

Capability	Chart Lab	Backtest
Visual signal inspection	Primary purpose	Secondary/debug only
Full historical performance	No	Yes
Trade ledger	No	Yes
Metrics	No	Yes
Equity curve	No	Yes
Drawdown	No	Yes
Monte Carlo	No	Yes
Walk-forward	No	Separate validation layer
Optimization	No	Feeds Optimization
Signal truth table	Yes	Stored as optional diagnostics
Feature overlay	Yes	Optional diagnostics
Paper/live readiness by itself	No	No, must combine with Sim Lab and gates
Backtest may report that a Program performed well.

Chart Lab may only report that the signals and components are understandable and correctly aligned on selected charts.

6. Feature Engine Integration
Chart Lab consumes Feature Engine output only.

Flow:

Program selection
→ Feature Planner validates Program for chart_lab
→ historical bars are loaded
→ Feature Engine batch/replay computes FeatureFrames
→ Chart Lab requests FeatureSnapshots for visible range
→ Signal Engine evaluates snapshots
→ component preview services evaluate optional previews
→ UI renders bars/features/markers/truth
Chart Lab cannot compute:

EMA
RSI
ATR
VWAP
ORB
prior-day levels
session state
regime
portfolio features
Chart Lab receives:

FeatureFrameSet
FeatureSnapshot
availability flags
warmup regions
alignment info
provenance
unsupported feature errors
Required FeatureSnapshot fields:

timestamp
symbol
base_timeframe
features
availability
higher_timeframe_sources
session_state
warm_state
provenance
Multi-timeframe display must show the source bar used.

Example:

At 2026-04-24 10:35 ET on 5m chart:
  5m.close[0] came from 10:30-10:35 bar
  15m.opening_range_high came from completed 09:30-09:45 ORB window
  1h.ema:length=20[0] came from completed 09:00-10:00 bar
  1d.high[0] came from previous completed daily bar
ORB display rules:

ORB high/low unavailable before completion.
opening_range_complete=false must be visible.
After completion, ORB levels freeze for session.
Chart Lab must not draw a final ORB level into pre-completion bars as if it was known.
7. Strategy / Program Preview Model
Chart Lab supports two preview levels:

Strategy Preview
Program Preview
Strategy Preview
Used when validating signal logic before full Program composition.

Inputs:

StrategyVersion
symbol
timeframe
date range
FeaturePlan for strategy features
Outputs:

feature overlays
condition truth
candidate signal markers
missing feature errors
Strategy Preview does not evaluate:

Strategy Controls
Risk Profile
Execution Style
Portfolio Governor
Program Preview
Used when validating the complete Program.

Inputs:

Frozen or draft Program
symbol
timeframe
date range
optional portfolio/governor snapshot
Outputs:

feature overlays
condition truth
candidate signal markers
Strategy Controls allow/block preview
Risk Profile sizing preview
Execution Style order-shape preview
Portfolio Governor allow/block preview
component completeness status
feature compatibility status
Program Preview is preferred. Strategy Preview is allowed only for early authoring.

Preview Chain
For each selected bar:

FeatureSnapshot
→ Signal Engine
→ CandidateTradeIntent or no-signal reason
→ StrategyControls preview
→ RiskProfile sizing preview
→ ExecutionStyle shape preview
→ PortfolioGovernor preview
If the Signal Engine emits no candidate, downstream previews are disabled for that bar unless the user creates a manual hypothetical candidate.

Manual Hypothetical Candidate
Chart Lab may allow the user to inspect:

What if I entered long here?
What if I exited here?
This creates a non-persistent preview only.

It may show:

risk size
execution shape
governor allow/block
It may not create:

simulated order
simulated position
PnL
trade record
8. UI Model
Chart Lab uses an inspection-first layout.

Top Bar
Always visible:

Program / Strategy selector
symbol selector
timeframe selector
date range
feature status
component completeness
mode: Strategy Preview | Program Preview
Main Chart
Displays:

OHLCV bars
selected Feature Engine overlays
ORB levels after availability
prior-day levels
signal candidate markers
blocked signal markers
selected bar cursor
Feature overlays must show availability gaps.

Warmup regions must be shaded or clearly marked.

Feature Panel
Shows canonical features for selected bar:

feature name
syntax
value
availability
source timeframe
source timestamp
provenance
Condition Truth Panel
For selected bar:

condition tree
true/false per node
feature values used
comparison operator
threshold
final signal result
It must show why a signal did not fire.

Examples:

No entry because:
  5m.close[0] > 5m.ema:length=20[0] = true
  5m.rsi:length=14[0] < 30 = false
  opening_range_complete = true
Final result: false
Controls Preview Panel
Only in Program Preview.

Shows:

allowed | blocked
reason
session state
cooldown state
trade cap state
event blackout state
regime state
Risk Preview Panel
Only after a candidate exists or manual hypothetical is created.

Shows:

suggested quantity
risk amount
notional
stop candidate used
max risk constraint
rejection reason if any
Must label this as sizing preview, not actual order sizing.

Execution Shape Panel
Shows static order shape:

order type
side
qty from risk preview
limit/stop prices if applicable
time in force
bracket legs
trailing configuration
scale-out plan
Must label:

Order shape preview only. No fills simulated.
Governor Preview Panel
Shows single-candidate decision:

would allow | would block
reason
projected exposure
projected open risk
conflict notes
snapshot used
Must label:

Single-candidate governor preview. Does not evolve portfolio state.
Marker Types
Required chart markers:

candidate_entry
candidate_exit
blocked_by_signal
blocked_by_controls
blocked_by_risk
blocked_by_governor
feature_unavailable
manual_hypothetical
No fill markers. No PnL markers.

9. Backend API Requirements
Required API surface:

POST /chart-lab/sessions
GET  /chart-lab/sessions/{session_id}
GET  /chart-lab/sessions/{session_id}/bars
GET  /chart-lab/sessions/{session_id}/features
GET  /chart-lab/sessions/{session_id}/markers
GET  /chart-lab/sessions/{session_id}/snapshot
GET  /chart-lab/sessions/{session_id}/condition-truth
POST /chart-lab/sessions/{session_id}/preview-candidate
GET  /chart-lab/sessions/{session_id}/component-preview
Create Session Request
mode: strategy_preview | program_preview
strategy_version_id: required for strategy_preview
program_version_id: required for program_preview
symbol
timeframe
date_range
feature_overlays
optional_governor_snapshot_id
Create Session Response
session_id
mode
symbol
timeframe
date_range
feature_plan_id
component_status
feature_status
warnings
Bars Response
Uses normalized market bars only:

timestamp
open
high
low
close
volume
session_state
Features Response
timestamp
feature_key
syntax
value
availability
source_timeframe
source_timestamp
provenance
Markers Response
timestamp
symbol
marker_type
side
reason
candidate_id
Snapshot Request
timestamp
Snapshot Response
feature_snapshot
higher_timeframe_alignment
session_context
warm_state
Condition Truth Response
timestamp
signal_result
condition_tree
node_results
feature_values
non_fire_reasons
candidate_trade_intent
Preview Candidate Request
timestamp
symbol
side
intent_type: entry | exit
manual: true | false
Component Preview Response
candidate_trade_intent
controls_preview
risk_preview
execution_shape_preview
governor_preview
Backend hard rules:

Chart Lab APIs never return simulated fills.
Chart Lab APIs never return positions.
Chart Lab APIs never return PnL curves.
Chart Lab APIs never mutate account or deployment state.
Chart Lab APIs never call broker adapters.
Chart Lab APIs must use Feature Engine and Signal Engine contracts.
10. Acceptance Tests
Chart Lab session cannot start if selected feature is not in Feature Registry.

Chart Lab session cannot start if historical bars are missing.

Chart Lab uses Feature Engine output for EMA overlay.

Chart Lab uses Feature Engine output for ORB levels.

ORB levels are not visible before ORB completion.

Multi-timeframe alignment panel shows source timestamp for 1d.high[0].

A 5m chart using 1h.ema:length=20[0] displays only completed 1h values.

Warmup region is marked unavailable.

Signal marker appears only where Signal Engine emits CandidateTradeIntent.

No-signal bar shows condition-level non-fire reason.

Condition Truth Panel shows every node in nested condition tree.

Strategy Preview does not show Risk Profile panel.

Strategy Preview does not show Execution Style panel.

Strategy Preview does not show Governor panel.

Program Preview shows component completeness.

Controls Preview blocks outside-session candidate.

Controls Preview shows cooldown block reason.

Risk Preview sizes a hypothetical candidate without creating an order.

Execution Shape Preview shows bracket structure without creating orders.

Governor Preview shows would-block reason without changing governor state.

Manual hypothetical candidate is clearly labeled as manual.

Chart Lab does not create orders.

Chart Lab does not create fills.

Chart Lab does not create positions.

Chart Lab does not show PnL.

Chart Lab does not call Alpaca or Broker Adapter.

Chart Lab cannot mark Program paper-ready by itself.

Blocked signal marker distinguishes signal failure from controls/risk/governor block.

Feature provenance is visible for selected bar.

Feature unavailable state prevents misleading false condition display.

Exported Chart Lab evidence includes feature snapshot, condition truth, and component previews only.

Chart Lab and Sim Lab produce the same Signal Engine result for the same FeatureSnapshot.

Chart Lab and Backtest use the same Feature Engine FeatureKey values for the same timestamp.

11. First Implementation Tasks
Define ChartLabSession
Durable or cache-backed session object containing:

mode
strategy/program id
symbol
timeframe
date range
FeaturePlan id
selected overlays
Wire Chart Lab to Feature Planner
No session can start without a valid FeaturePlan for chart_lab.

Render Feature Engine overlays only
Remove or forbid local chart indicator calculations.

Implement FeatureSnapshot endpoint
Selected bar inspection depends on this.

Implement Condition Truth endpoint
Must use Signal Engine, not frontend logic.

Implement Multi-Timeframe Alignment display
Every higher-timeframe value must show its source bar.

Implement ORB availability rendering
Do not draw final ORB levels before completion.

Implement Strategy Preview mode
Signal-only validation.

Implement Program Preview mode
Full component preview without execution simulation.

Implement Component Preview service
Runs:

Strategy Controls preview
Risk Profile sizing preview
Execution Style shape preview
optional Governor preview
Stops before orders.

Implement Marker taxonomy
Markers must distinguish:

candidate signal
signal failed
controls blocked
risk blocked
governor blocked
feature unavailable
Block forbidden outputs
No PnL, positions, fills, or simulated orders in Chart Lab APIs.

Add evidence export
Export:

chart context
FeatureSnapshot
condition truth
component previews
provenance
Add parity test with Sim Lab
Same Program, symbol, timestamp, FeatureSnapshot must produce identical signal/controls/risk preview up to the point where Sim Lab begins order simulation.

Add parity test with Backtest
Same Program, symbol, timestamp must use identical FeatureKeys and feature values.