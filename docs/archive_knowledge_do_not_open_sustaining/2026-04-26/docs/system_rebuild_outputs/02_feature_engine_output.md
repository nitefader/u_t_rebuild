Feature Engine Output
1. Final Feature Engine Definition
The Feature Engine is the only place where market, session, derived, and portfolio features are computed.

It serves every consumer:

Chart Lab
Sim Lab historical replay
Sim Lab live stream
Backtest
Optimization
Walk-forward
Paper trading
Live trading
Portfolio Governor
There is one feature system with two execution modes:

batch/replay
incremental/streaming
Both modes must produce the same feature values for the same input bars, same calendar, same FeatureSpec, same warmup policy, and same feature implementation version.

The Feature Engine does not evaluate strategy logic. It does not approve trades. It does not build orders.

It only does this:

FeatureSpec declarations
→ FeaturePlan
→ normalized bars/session context/portfolio state
→ computed FeatureFrames
→ current or historical feature values
2. Core Objects
FeatureSpec
One immutable request for one feature.

FeatureSpec
  kind
  namespace
  timeframe
  source
  params
  lookback
  shift
  scope
  version
Required fields:

Field	Decision
kind	Canonical feature name from registry
namespace	price, technical, session, event, portfolio, derived
timeframe	Canonical timeframe only: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mo
source	Required for source-based features: open, high, low, close, volume, hlc3, ohlc4
params	Canonical registry-defined params only
lookback	Bar index offset, where 0 means current completed bar
shift	Causality shift applied by feature implementation
scope	symbol, session, or portfolio
version	Feature implementation version
FeatureSpec is immutable. Any edit creates a new spec.

FeatureKey
One deterministic key for one FeatureSpec.

Format:

{version}|{scope}|{timeframe}|{namespace}.{kind}|source={source}|params={canonical_params}|lookback={lookback}|shift={shift}
Examples:

v1|symbol|5m|price.close|source=close|params={}|lookback=0|shift=0
v1|symbol|5m|price.close|source=close|params={}|lookback=1|shift=0
v1|symbol|1d|price.high|source=high|params={}|lookback=0|shift=0
v1|session|15m|session.opening_range_high|source=high|params={session=regular,window_minutes=15}|lookback=0|shift=0
v1|symbol|5m|technical.ema|source=close|params={length=20}|lookback=0|shift=0
v1|portfolio|1m|portfolio.open_risk_pct|source=portfolio|params={}|lookback=0|shift=0
Hard decisions:

14 and 14.0 are the same parameter.
Params are sorted.
Defaults are injected before key creation.
Unsupported params are rejected.
Timeframe aliases are rejected, not normalized silently. 60m is invalid. Use 1h.
Feature implementation version is part of the key.
Feature Registry
The registry is the only source of feature truth.

It defines:

feature name
namespace
supported scopes
supported timeframes
required source fields
allowed params
default params
warmup rule
causality rule
batch implementation
incremental implementation
output dtype
AI-safe description
consumer support flags
No feature exists unless it is in the registry.

Feature Planner
The planner builds the feature contract for a Program, consumer, symbol set, mode, and date/session range.

It resolves requirements from:

Strategy
Strategy Controls
Risk Profile
Execution Style
Universe
Portfolio Governor
It outputs:

FeaturePlan
  plan_id
  consumer
  mode
  program_version_id
  symbols
  timeframes
  feature_specs
  feature_keys
  warmup_by_timeframe
  dependencies
  alignment_rules
  data_requirements
  session_requirements
  portfolio_requirements
  unsupported_feature_errors
If unsupported features exist, planning fails. Execution never starts.

Feature Cache
One cache interface, two backing behaviors:

Research cache: batch/replay runs
Runtime cache: streaming deployments
Both use the same FeatureKey.

Feature Engine
The engine owns execution.

It exposes:

plan(program, consumer, mode) -> FeaturePlan
compute_batch(plan, bars, context) -> FeatureFrameSet
warm_stream(plan, historical_bars, context) -> RuntimeFeatureState
update_stream(runtime_state, normalized_bar_or_portfolio_event) -> FeatureUpdate
get_value(feature_key, symbol, timestamp) -> value
get_snapshot(symbol, timestamp, required_keys) -> FeatureSnapshot
3. Feature Declaration Syntax
The Trading OS uses one feature reference syntax everywhere.

Canonical syntax:

{timeframe}.{feature}[{lookback}]
{timeframe}.{feature}
{timeframe}.{feature}:{params}[{lookback}]
Examples:

5m.close[0]
5m.close[1]
1d.high[0]
15m.opening_range_high
5m.ema:length=20[0]
1h.rsi:length=14[0]
5m.vwap:session=regular[0]
Rules:

5m.close[0] means the latest completed 5m close.
5m.close[1] means the previous completed 5m close.
1d.high[0] means the latest completed daily high.
If [n] is omitted, [0] is implied.
A feature without params uses registry defaults.
Params must match registry names exactly.
opening_range_high is a session feature, not a rolling high.
Cross-timeframe references are explicit. A 5m strategy using 1d.high[0] must declare it.
No implicit current-forming bar access exists.
Current incomplete bars are not visible to strategies unless a registry feature explicitly supports forming=true. Initial system version forbids forming=true.
Allowed price shorthand:

5m.open[0]
5m.high[0]
5m.low[0]
5m.close[0]
5m.volume[0]
Equivalent expanded FeatureSpec:

5m.close[1]
→ kind=close
→ namespace=price
→ timeframe=5m
→ source=close
→ lookback=1
→ params={}
→ scope=symbol
Rejected syntax examples:

60m.close[0]              # invalid timeframe
5min.close[0]             # invalid timeframe
5m.foo[0]                 # unsupported feature
5m.ema:period=20[0]       # invalid param name; use length
5m.close[-1]              # future lookahead forbidden
5m.close[current]         # unsupported
4. Multi-Timeframe Model
Multi-timeframe support is first-class.

A strategy running on 5m may request:

5m.close[0]
15m.opening_range_high
1h.ema:length=20[0]
1d.high[0]
The Feature Planner must produce separate frame requirements:

SPY 5m
SPY 15m
SPY 1h
SPY 1d
Alignment rule:

Lower-timeframe decisions may only see higher-timeframe bars that are already completed.
Example:

A 5m decision at 2026-04-24 10:35 ET may see:

5m.close[0]      completed at 10:35
15m.close[0]     completed at 10:30
1h.close[0]      completed at 10:00
1d.high[0]       previous completed daily bar unless current daily bar is closed
Daily bar rule:

During the trading day, 1d.high[0] is the last completed daily bar.
Today’s in-progress daily high is not 1d.high[0].
Intraday “today so far” features must be separate session features, such as regular_session_high_so_far.
This prevents accidental lookahead.

Cross-timeframe alignment output:

FeatureSnapshot at 5m timestamp T
  5m features as of T
  15m features as of latest completed 15m bar <= T
  1h features as of latest completed 1h bar <= T
  1d features as of latest completed 1d bar <= T
No consumer may hand-align higher timeframe data itself.

5. ORB / Session Feature Model
ORB features are session features.

Canonical ORB features:

opening_range_high
opening_range_low
opening_range_mid
opening_range_width
opening_range_width_pct
opening_range_complete
opening_range_minutes_elapsed
above_opening_range_high
below_opening_range_low
Required params:

session=regular
window_minutes=5 | 15 | 30 | 60
Examples:

15m.opening_range_high:session=regular,window_minutes=15
5m.opening_range_complete:session=regular,window_minutes=15
5m.above_opening_range_high:session=regular,window_minutes=15
Hard ORB rules:

ORB uses session calendar, not naïve clock math.
ORB window starts at the official session open.
Regular session default is 09:30 America/New_York.
Half-days do not change the opening window start.
Holidays produce no ORB values.
ORB high/low are unavailable until enough bars have occurred to cover the configured window.
opening_range_complete=false until the window is complete.
Strategies cannot use final ORB high/low before completion.
If a bar spans the ORB boundary, the Bar Builder must split or correctly attribute the bar. It cannot smear boundary data.
ORB values freeze after completion for that session.
Example for 15-minute ORB:

09:30-09:35  opening_range_complete=false
09:35-09:40  opening_range_complete=false
09:40-09:45  opening_range_complete=true after 09:45 bar completes
09:45+       opening_range_high/low frozen for session
For 1m data, the 15-minute ORB completes after the 09:44 minute bar closes at 09:45.

For 5m data, the 15-minute ORB completes after the third 5m bar closes at 09:45.

ORB does not use future data. It becomes visible only when complete.

6. Batch / Replay Mode
Batch/replay mode is used by:

Chart Lab
Sim Lab historical replay
Backtest
Optimization
Walk-forward
Batch mode input:

FeaturePlan
historical normalized bars
session calendar
event data
portfolio snapshots when needed
Batch mode output:

FeatureFrameSet
  symbol
  timeframe
  timestamp
  feature_key columns
  value
  availability flag
  provenance
Batch mode rules:

All bars must be normalized before feature computation.
Timestamps must be canonical UTC internally.
Session interpretation uses exchange calendar and ET session definitions.
Features must be computed causally.
Non-causal implementations are forbidden unless explicitly shifted to confirmed availability.
Swing/fractal-like features must appear only at the confirmation timestamp, not the source timestamp.
Warmup rows must be marked unavailable, not silently treated as false.
Missing higher-timeframe data fails planning or execution explicitly.
Batch mode may compute vectorized, but output availability must match incremental mode.
Batch mode must be able to replay one bar at a time for parity tests.
Batch replay contract:

for each decision timestamp:
  FeatureEngine.snapshot(timestamp)
  SignalEngine.evaluate(snapshot)
Consumers do not read raw feature DataFrames directly.

7. Incremental / Streaming Mode
Incremental/streaming mode is used by:

Sim Lab live stream
Paper trading
Live trading
Portfolio Governor
Streaming input:

normalized completed bar
session event
portfolio event
broker/account event
Streaming output:

FeatureUpdate
  updated_feature_keys
  symbol
  timeframe
  timestamp
  warm_state
  changed_values
Streaming flow:

Market Data Service
→ Bar Builder
→ Feature Engine runtime state
→ Feature Cache update
→ Signal Engine notification
Streaming rules:

Feature Engine receives completed bars only.
No strategy sees incomplete bars.
Every active Deployment has a FeaturePlan.
Runtime warmup must complete before Signal Engine can emit entry signals.
Features with online formulas must update incrementally.
Features without valid incremental implementations must be blocked from paper/live.
Batch fallback recomputation on every streaming bar is forbidden for live/paper.
EWM-family features must preserve state across updates.
Daily bars must respect half-days.
Calendar uncertainty fails closed for new opens.
Incremental implementation required for initial live/paper support:

open
high
low
close
volume
sma
ema
rsi
atr
vwap
highest
lowest
opening_range_high
opening_range_low
opening_range_complete
prior_day_high
prior_day_low
prior_day_close
session_state
If a Strategy requires a feature without incremental support, it may be used in Chart Lab, Backtest, or Optimization only if registry allows those consumers. It cannot be deployed.

8. Cache Model
The cache is keyed by:

symbol
timeframe
feature_key
data_source_id
calendar_version
feature_version
adjustment_policy
There are two cache scopes.

Research Cache
Used by:

Chart Lab
Sim Lab historical replay
Backtest
Optimization
Walk-forward
Properties:

run-scoped
content-addressed
reusable across runs when provenance matches
safe to persist
Research cache may store full FeatureFrames.

Runtime Cache
Used by:

Sim Lab live stream
Paper
Live
Portfolio Governor
Properties:

deployment-scoped plus shared symbol/timeframe frames
bounded memory
warmup-aware
incremental stateful
rebuildable from persisted bars
Runtime cache stores:

recent raw bars
feature state
latest feature values
warmup counters
availability flags
higher-timeframe alignment pointers
Cache hard rules:

Cache never changes feature semantics.
Cache hit requires exact FeatureKey and provenance match.
Cache must distinguish adjusted vs unadjusted data.
Cache must distinguish provider.
Cache must distinguish calendar version.
Cache must distinguish feature implementation version.
Cache must expose warm, not_warm, stale, and invalid.
Stale cache cannot feed Signal Engine.
Cache eviction must be explicit and bounded.
Runtime cache size must be based on max warmup requirement, not fixed at 250 bars.
Warmup rule:

required_window = max(feature warmup requirement for symbol/timeframe) + safety_buffer
If required warmup exceeds available data, execution blocks with a clear error.

9. Consumer Integration
Chart Lab
Uses batch/replay mode.

Allowed:

display feature overlays
display signal markers
inspect feature values
show unavailable/warmup regions
show unsupported feature errors
Forbidden:

compute local indicator overlays outside Feature Engine
imply deployability if incremental support is missing
Sim Lab Historical Replay
Uses batch/replay mode with replay snapshots.

Allowed:

step through historical FeatureSnapshots
test Signal Engine output
simulate execution using ExecutionStyle
Forbidden:

recompute features in stepper code
Sim Lab Live Stream
Uses incremental/streaming mode.

Allowed:

subscribe to runtime FeatureUpdates
simulate order behavior from live feature/signal stream
Forbidden:

provider streaming directly into Signal Engine
Backtest
Uses batch mode.

Required:

frozen Program version
FeaturePlan
FeatureFrameSet
causal snapshots
run config snapshot
feature provenance snapshot
Forbidden:

direct BacktestEngine._compute_indicators() ownership
Optimization
Uses batch mode.

Required:

one FeaturePlan per candidate or a superset plan when safe
no unsupported generated feature names
deterministic cache reuse
Forbidden:

silently substituting missing features
ranking candidates with partial feature failures
Walk-Forward
Uses batch mode.

Required:

fold-specific FeaturePlans
fold-specific provenance
identical feature semantics across folds
Forbidden:

using different feature implementations between IS and OOS
Paper Trading
Uses incremental/streaming mode.

Required:

active Deployment FeaturePlan
warm runtime cache
batch/live parity-approved features only
FeatureUpdate-driven Signal Engine evaluation
Forbidden:

deployment start if any required feature lacks incremental support
Live Trading
Same as paper, with stricter blocking.

Required:

all paper requirements
broker sync freshness
market data stream freshness
calendar valid for current date
no stale feature state
Forbidden:

live start with feature warnings
Portfolio Governor
Consumes portfolio-scoped features.

Examples:

portfolio.open_risk_pct
portfolio.pending_open_risk_pct
portfolio.gross_exposure_pct
portfolio.symbol_concentration_pct
portfolio.correlation_cluster_exposure_pct
portfolio.broker_sync_stale
portfolio.global_kill_active
Governor features are computed by the Feature Engine from broker/order/trade/runtime state, but Governor remains the decision authority.

Portfolio features must evaluate:

current state
candidate order delta
projected post-trade state
10. Feature Registry Rules
Every registry entry must define:

name
namespace
description
syntax
scope
supported_timeframes
supported_consumers
supported_modes
params
defaults
source requirements
warmup function
dependencies
causality
batch implementation
incremental implementation if stream-supported
output columns
AI compatibility text
examples
Registry support flags:

chart_lab_supported
sim_replay_supported
sim_stream_supported
backtest_supported
optimization_supported
walk_forward_supported
paper_supported
live_supported
governor_supported
Hard rules:

A feature not in the registry does not exist.
A feature cannot be used by a consumer unless that consumer flag is true.
A feature cannot be used in paper/live unless incremental support exists.
A feature cannot be used if its warmup cannot be satisfied.
A feature cannot use future bars.
Confirmation-based features must expose values only when confirmed.
Registry descriptions are used by UI and AI; they must be precise.
Feature implementations must be versioned.
Param defaults must live in the registry.
The registry must generate the public Feature Vocabulary Catalog.
Initial registry must be small.

Initial supported features:

Price:
  open
  high
  low
  close
  volume

Technical:
  sma
  ema
  rsi
  atr
  vwap
  highest
  lowest

Session:
  session_state
  regular_session_high_so_far
  regular_session_low_so_far
  opening_range_high
  opening_range_low
  opening_range_mid
  opening_range_width
  opening_range_width_pct
  opening_range_complete
  prior_day_high
  prior_day_low
  prior_day_close
  gap_pct

Portfolio:
  gross_exposure_pct
  net_exposure_pct
  open_risk_pct
  pending_open_risk_pct
  symbol_concentration_pct
  new_open_slots_remaining
  broker_sync_stale
  global_kill_active
  account_pause_active
  deployment_pause_active
Everything else waits.

11. AI Feature Compatibility
AI may only generate features from the registry vocabulary.

The AI-facing catalog must expose:

feature name
plain-English meaning
syntax examples
allowed params
default params
allowed timeframes
allowed consumers
paper/live support
causality notes
invalid examples
AI generation rule:

AI proposes feature references.
Feature Parser converts to FeatureSpec.
Feature Planner validates.
Unsupported features are rejected with exact registry errors.
AI cannot invent:

indicator names
param names
timeframe aliases
session names
portfolio fields
“current forming bar” syntax
AI response must include compatibility status:

supported_in_chart_lab
supported_in_backtest
supported_in_sim_replay
supported_in_paper
supported_in_live
reason_if_not_supported
Example rejection:

Feature "supertrend" is not in the registry.
Allowed alternatives: ema, atr, highest, lowest, vwap.
This strategy cannot be saved until the feature is replaced or added to the registry.
AI-generated strategies must not be saved as deployable Programs until Feature Planner passes.

12. Acceptance Tests
FeatureSpec / FeatureKey
5m.close[0] parses to one canonical FeatureSpec.
5m.close equals 5m.close[0].
5m.ema:length=20[0] injects all registry defaults.
length=14 and length=14.0 produce the same FeatureKey.
60m.close[0] is rejected.
5m.ema:period=20[0] is rejected.
FeatureKey changes when feature implementation version changes.
Multi-Timeframe
A 5m strategy using 1h.ema:length=20[0] sees only the latest completed 1h bar.
A 5m strategy cannot see the current forming daily bar as 1d.high[0].
Missing 1h data for a required 1h feature blocks execution.
Alignment is identical in batch replay and streaming replay.
ORB / Session
opening_range_complete=false before ORB window completion.
opening_range_high unavailable before ORB completion.
ORB high/low freeze after completion.
Half-day session still completes ORB correctly.
Holiday produces no ORB values and blocks session-dependent new opens.
Batch / Replay
Warmup rows are unavailable, not false.
Swing/fractal-style confirmed features, when later added, appear only at confirmation timestamp.
Backtest cannot compute indicators outside Feature Engine.
Chart Lab overlays match FeatureFrame values exactly.
Streaming
EMA streaming output matches batch replay within defined tolerance.
ATR streaming output matches batch replay within defined tolerance.
Runtime cache warms before Signal Engine emits entries.
Stale market data marks FeatureState stale.
Stream reconnect does not duplicate bars.
Revised bars trigger invalidation or explicit rejection.
Cache
Cache hit requires matching provider, adjustment policy, calendar version, and FeatureKey.
Runtime window size exceeds max warmup requirement.
Evicted runtime cache cannot silently serve stale values.
Feature implementation version bump invalidates old cached features.
Consumer Gating
Paper deployment is rejected if any required feature lacks incremental support.
Live deployment is rejected if any feature has warning status.
Optimization candidate is rejected if AI generated unsupported features.
Portfolio Governor receives projected post-trade portfolio features.
Signal Engine cannot request raw bars directly.
Parity
Same bars through batch mode and streaming replay produce same FeatureSnapshots.
Sim replay and Backtest use identical FeatureSnapshots for the same timestamps.
Paper warmup from historical bars produces the same latest snapshot as batch computation.
Walk-forward folds preserve identical feature semantics.
No consumer has a private indicator implementation.
13. First Implementation Tasks
Lock FeatureSpec and FeatureKey
Implement final immutable FeatureSpec and deterministic FeatureKey.

Remove alternate indicator requirement formats.

Build Feature Parser
Parse syntax:

5m.close[0]
5m.close[1]
1d.high[0]
15m.opening_range_high
5m.ema:length=20[0]
Reject invalid syntax immediately.

Create Registry v1
Add only the initial supported features.

Do not migrate every old indicator.

Make Feature Planner mandatory
Program validation must call Feature Planner.

No Program can become deployable without a valid FeaturePlan.

Separate Bar Builder from Feature Engine
Bar Builder owns:

timestamp normalization
symbol normalization
timeframe aggregation
session-aware bar completion
Feature Engine owns:

features only
Implement batch Feature Engine
Replace backtest-owned indicator computation with Feature Engine batch output.

Backtest consumes FeatureSnapshots.

Implement ORB correctly
Build session features with explicit availability flags.

ORB must not be visible before completion.

Implement runtime Feature Cache
Runtime cache size must derive from warmup requirements.

Remove fixed-size assumptions.

Implement streaming EMA/RSI/ATR/VWAP state
No full rolling-window recompute per bar for live/paper.

Add batch-vs-stream parity harness
Feed the same normalized bars through:

batch mode
streaming replay mode
Compare FeatureSnapshots timestamp by timestamp.

Wire Chart Lab to Feature Engine only
Remove local chart indicator computation.

Chart Lab displays FeatureFrame output.

Wire Sim Lab to FeatureSnapshots
Historical replay and live stream must both consume Feature Engine snapshots/updates.

Block unsupported AI features
AI output must pass registry validation before strategy save.

Publish Feature Vocabulary Catalog from registry
The catalog must be generated from registry metadata, not hand-written separately.

Enforce paper/live deployment gate
Deployment start fails if:

FeaturePlan invalid
feature unsupported in streaming
warmup unavailable
calendar invalid
cache stale
parity status missing for required feature class