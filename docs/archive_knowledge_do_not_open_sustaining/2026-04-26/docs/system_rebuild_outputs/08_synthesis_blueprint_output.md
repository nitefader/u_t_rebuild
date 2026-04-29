Trading OS Master Blueprint
1. Executive Summary
The new Trading OS is one system, not a collection of trading tools.

Final operating model:

Program defines intent.
Deployment runs intent.
Feature Engine computes facts.
Signal Engine emits candidate trade intent.
Strategy Controls, Risk, and Execution Style shape the candidate.
Portfolio Governor approves or rejects.
Order Manager records internal orders.
Broker Adapter submits to Alpaca.
Broker Sync reconciles broker truth.
Operations Center monitors and controls runtime.
The old repo must not be copied wholesale. It is reference material only. The new system must be built around one domain model, one feature system, one runtime unit, one broker boundary, one validation path, and one runtime operations surface.

Final core decisions:

Deployment is the only runtime unit.
AccountAllocation is not a runtime concept.
PortfolioGovernor is separate from BrokerAccount.
Program contains references only, never inline trading behavior.
FeatureEngine is the only computation layer.
SignalEngine stops at CandidateTradeIntent.
BrokerAdapter is the only Alpaca caller.
ChartLab validates signals and component previews only.
SimLab simulates execution behavior only.
AI suggests drafts and context; deterministic systems enforce all trading safety.
2. Final Architecture
Minimal final layers:

Design-Time
  Strategy
  StrategyControls
  RiskProfile
  ExecutionStyle
  Universe
  Program

Data + Features
  MarketDataService
  HistoricalDataService
  BarBuilder
  FeatureEngine
  FeatureCache

Decision
  SignalEngine
  StrategyControlsGate
  RiskEngine
  ExecutionIntentBuilder
  PortfolioGovernor

Execution
  OrderManager
  BrokerAdapter
  BrokerSync
  OrderLedger
  TradeLedger
  BrokerAccount

Runtime
  Deployment
  RuntimeState
  OperationsCenter
  ControlPlane

Validation
  ChartLab
  SimLab
  Backtest
  Optimization
  WalkForward
  ValidationEvidence

AI
  ProgramBuilder
  StrategyGenerator
  WatchlistAnalyzer
  SignalContextAnalyzer
  OptimizationAssistant
Removed as independent authority:

AccountGovernor
StrategyGovernor
AccountAllocation runtime lifecycle
duplicate Live Monitor / Account Monitor / Deployment Manager authority
direct indicator computation in backtest, chart, sim, or strategy code
direct Alpaca access outside adapters
generic Services bucket
duplicate watchlist systems
3. Canonical Domain Model
Domain Object	Owns	Must Not Own
Strategy	Signal rules, feature requirements, entry/exit intent logic, stop/target candidates	Sizing, sessions, order types, broker calls
StrategyControls	Timeframe, session windows, cooldowns, trade caps, event blackout, regime permission	Signal logic, sizing, execution
RiskProfile	Position sizing policy, loss limits, exposure limits	Signal logic, order mechanics, broker truth
ExecutionStyle	Order expression, TIF, brackets, trailing, cancel/replace, scale-out mechanics	Signal truth, risk budget, approval
Universe	Tradable symbol source and resolution rules	Signal, risk, execution, broker policy
Program	Exact frozen component references	Inline behavior, broker account, runtime state
Deployment	Running Program on Broker Account under Portfolio Governor	Component definitions, broker truth, portfolio authority
PortfolioGovernor	Final approval, projected exposure/risk checks, conflicts, pause/lockout state	Broker credentials, signal computation, order submission
BrokerAccount	Broker identity, credentials, balances, positions, orders, fills, restrictions	Internal trading policy
Order	Internal and broker order lifecycle, attribution, intent	Strategy approval
Trade	Normalized trade/fill lifecycle across modes	Broker routing
ValidationEvidence	Chart, sim, backtest, optimization, walk-forward evidence	Runtime authority
Final Program shape:

ProgramVersion
  id
  name
  version
  status: draft | frozen | deprecated
  strategy_version_id
  strategy_controls_version_id
  risk_profile_version_id
  execution_style_version_id
  universe_snapshot_id
  validation_status
  created_at
  frozen_at
Program cannot contain inline indicators, conditions, risk fields, session fields, execution policy, runtime state, broker account id, live universe cache, or deployment status.

4. End-to-End Flow
The only valid system flow:

Idea
→ Chart Lab (Batch / Live Preview)
→ Sim Lab (Historical / Live Simulation)
→ Backtest
→ Optimization
→ Walk-Forward
→ Broker Runtime (Paper)
→ Live Promotion Gate
→ Broker Runtime (Live)

This lifecycle uses the canonical mode names from the Mode Naming Contract. It clarifies the mode surfaces without changing architecture or runtime authority.

Broker Runtime (Paper) means:

- full runtime pipeline
- Alpaca Paper broker endpoint/account
- real BrokerAdapter
- real BrokerSync
- fake money
- not Sim Lab
- not Backtest

Broker Runtime (Live) means:

- full runtime pipeline
- Alpaca Live broker endpoint/account
- real BrokerAdapter
- real BrokerSync
- real money

Runtime signal-to-order chain:

Market Data Stream
→ BarBuilder
→ FeatureEngine
→ SignalEngine
→ CandidateTradeIntent
→ StrategyControlsGate
→ RiskEngine
→ ExecutionIntentBuilder
→ PortfolioGovernor
→ OrderManager
→ BrokerAdapter
→ Alpaca
→ BrokerSync
→ OrderLedger / TradeLedger
→ OperationsCenter
No shortcut path may bypass Feature Engine, Portfolio Governor, Order Manager, or Broker Adapter.

5. Feature Engine Model
Feature Engine is the only computation layer.

Required consumers:

Chart Lab
Sim Lab historical replay
Sim Lab live stream
Backtest
Optimization
Walk-forward
Broker Runtime (Paper)
Broker Runtime (Live)
Portfolio Governor
Core objects:

FeatureSpec
FeatureKey
FeatureRegistry
FeaturePlanner
FeatureCache
FeatureEngine
FeatureFrame
FeatureSnapshot
Two execution modes:

batch/replay
incremental/streaming
Canonical feature syntax:

5m.close[0]
5m.close[1]
1d.high[0]
15m.opening_range_high:session=regular,window_minutes=15
5m.ema:length=20[0]
1h.rsi:length=14[0]
Rules:

[0] means latest completed bar.
No current forming bar access in v1.
Timeframe aliases are rejected. Use canonical values like 1h, not 60m.
Unsupported features fail validation.
AI may only use features from the registry.
Multi-timeframe values are aligned by latest completed source bar.
ORB features are session features and are unavailable until the ORB window is complete.
Feature cache keys include feature version, provider, adjustment policy, calendar version, symbol, timeframe, and FeatureKey.
Streaming features must have true incremental implementations for paper/live.
Batch/replay and streaming replay must pass parity tests.
Initial registry should be small:

Price:
  open, high, low, close, volume

Technical:
  sma, ema, rsi, atr, vwap, highest, lowest

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

6. Sim Lab Model
Sim Lab is the full Program simulation surface.

It answers:

If this frozen Program receives this market stream, how would it behave operationally?
Modes:

SIM_LAB_HISTORICAL
SIM_LAB_LIVE_SIMULATION
Sim Lab runs:

Strategy through Signal Engine
Strategy Controls
Risk Profile
Execution Style
optional Portfolio Governor validation
Sim Lab simulates:

candidate signals
blocked signals
order creation
fills
partial fills
slippage
stops/targets
trailing stops
scale-outs
position state
PnL
drawdown
exposure
session rules
Sim Lab must not:

compute features
define indicators
submit real broker orders
replace Backtest
replace Walk-Forward
Exact Sim Lab chain:

FeatureSnapshot
→ SignalEngine
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
Governor modes:

off
advisory
enforced
Paper readiness requires enforced.

For 50+ symbols, backend processes all symbols. UI shows:

portfolio summary
event stream
virtualized symbol table
focused symbol detail
decision inspector
No 50-chart layouts.

7. Chart Lab Model
Chart Lab is the signal and component validation surface.

It answers:

Given this Program and this historical market context, why would the system want or not want a trade at this bar?
Chart Lab can show:

normalized bars
canonical features
multi-timeframe aligned features
ORB availability
signal markers
condition truth
non-fire reasons
Strategy Controls preview
Risk Profile sizing preview
Execution Style order-shape preview
Portfolio Governor single-candidate preview
Chart Lab must not:

simulate fills
create orders
track positions
show PnL
show drawdown curves
evolve account state
replace Sim Lab
replace Backtest
Chart Lab stops at:

CandidateTradeIntent + component previews
Two modes:

Strategy Preview
Program Preview
Strategy Preview validates signal logic only.

Program Preview validates the full component chain up to static previews, but stops before order creation.

8. Alpaca Integration Model
Alpaca is external only.

Alpaca provides:

market data streaming
historical bars
order submission
order status
fills
positions
buying power
restrictions
Alpaca does not define:

features
signals
strategy logic
risk policy
portfolio rules
execution approval
Only these layers may call Alpaca:

AlpacaMarketDataAdapter
AlpacaBrokerAdapter
Market data flow:

Alpaca Stream / Historical Bars
→ AlpacaMarketDataAdapter
→ MarketDataService
→ BarBuilder
→ FeatureEngine
→ SignalEngine
Order flow:

ExecutionIntent
→ PortfolioGovernor approval
→ OrderManager creates internal Order
→ AlpacaBrokerAdapter submits
→ Alpaca
→ BrokerSync
→ OrderLedger / TradeLedger / BrokerAccount snapshot
client_order_id format:

utos-{acct8}-{dep8}-{prog8}-{intent}-{seq}
Allowed intents:

open
close
tp
sl
scale
Control-plane cancellation rule:

Cancel only scope-matching open orders without positions.

Never auto-cancel:

tp
sl
close
scale
unknown
Multiple accounts are supported. Broker account streams are account-scoped. Market data streams are provider/environment-scoped and demand-deduped.

9. AI System Model
AI is advisory and draft-generating only.

AI may propose:

Program drafts
Strategy drafts
component variants
Universe/watchlist candidates
parameter ranges
test plans
overfit warnings
signal context notes
AI may not:

invent unsupported features
define feature semantics
mark a Program deployable
submit orders
call Alpaca
override Strategy Controls
override Risk Profile
override Portfolio Governor
change position size at runtime
flatten, pause, resume, or kill anything
hide validation blockers
fabricate results
AI Program Builder flow:

Plain English
→ intent extraction
→ existing component search
→ reuse / variant / new decision
→ registry-compatible draft components
→ Feature Planner validation
→ user review
→ draft Program
AI must prefer reuse:

exact existing component
→ safe variant
→ new component
AI Feature Compatibility comes entirely from the Feature Registry-generated vocabulary catalog.

Signal Context Analyzer is advisory only and disabled by default for runtime. It can attach context flags but cannot approve or reject trades.

Cost strategy:

deterministic validators first
cheap model first
no AI calls per symbol per bar
context only on candidate signal, refresh, event update, or manual request
cache outputs
summarize long artifacts
require confirmation above budget threshold
10. Repo Structure
Recommended new repo structure:

backend/
  app/
    main.py

    domain/
      strategy.py
      strategy_controls.py
      risk_profile.py
      execution_style.py
      universe.py
      program.py
      deployment.py
      portfolio_governor.py
      broker_account.py
      order.py
      trade.py
      validation.py
      simulation.py
      chart_lab.py
      provider.py
      control_plane.py

    features/
      spec.py
      key.py
      registry.py
      parser.py
      planner.py
      cache.py
      engine.py
      batch.py
      streaming.py
      frames.py
      provenance.py

    market_data/
      service.py
      historical.py
      bar_builder.py
      adapters/
        alpaca_market_data.py

    broker/
      adapters/
        alpaca_broker.py
      order_manager.py
      broker_sync.py
      ledgers.py

    decision/
      signal_engine.py
      controls_gate.py
      risk_engine.py
      execution_intent.py
      governor_engine.py

    simulation/
      engine.py
      simulated_broker.py
      fill_models.py
      event_log.py
      metrics.py

    chart_lab/
      session_service.py
      preview_service.py
      evidence_export.py

    validation/
      backtest_engine.py
      optimization_service.py
      walk_forward.py
      evidence_service.py
      promotion_gate.py

    ai/
      program_builder.py
      strategy_generator.py
      watchlist_analyzer.py
      context_analyzer.py
      optimization_assistant.py
      validators.py
      provenance.py

    api/
      routes/
        programs.py
        components.py
        universes.py
        chart_lab.py
        sim_lab.py
        backtests.py
        optimizations.py
        walk_forward.py
        deployments.py
        operations.py
        portfolio_governors.py
        broker_accounts.py
        providers.py
        control_plane.py
        audit_logs.py
        ai.py

frontend/
  src/
    pages/
      Build/
        Strategies.tsx
        Components.tsx
        Universes.tsx
        Programs.tsx
      Validate/
        ChartLab.tsx
        SimLab.tsx
        Backtests.tsx
        Optimizations.tsx
        WalkForward.tsx
        Evidence.tsx
      Operate/
        Deployments.tsx
        OperationsCenter.tsx
        PortfolioGovernor.tsx
      Admin/
        BrokerAccounts.tsx
        Providers.tsx
        AuditLogs.tsx
        BackupRestore.tsx
Banned names:

StrategyGovernor
AccountGovernor
generic Governor
AccountAllocation as runtime
DataService for AI
DeploymentManager as authority
LiveMonitor as separate authority
11. Backend Implementation Plan
Build backend in this order:

Domain models and frozen version model.
FeatureSpec, FeatureKey, Feature Registry, Feature Parser.
Feature Planner and Program validation.
Batch Feature Engine.
Bar cache, Feature cache, provenance.
Signal Engine.
StrategyControlsGate, RiskEngine, ExecutionIntentBuilder.
Chart Lab session and preview APIs.
Sim Lab simulation engine, simulated broker, event log.
Alpaca adapters, MarketDataService, HistoricalDataService, BarBuilder.
OrderManager, OrderLedger, TradeLedger.
BrokerSync.
PortfolioGovernor.
Deployment warm-up and runtime gates.
ControlPlane.
Backtest, Optimization, WalkForward using FeatureSnapshots.
ValidationEvidence and PromotionGate.
AI draft-generation layer and validators.
Backend must not preserve old routes for compatibility.

12. Frontend Implementation Plan
Build frontend around final workflows, not old pages.

Navigation:

Build
  Strategies
  Components
  Universes
  Programs

Validate
  Chart Lab
  Sim Lab
  Backtests
  Optimizations
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
Priority screens:

Programs: compose references only.
Components: manage Strategy Controls, Risk Profiles, Execution Styles.
Universes: create watchlists/snapshots.
Chart Lab: signal/component inspection only.
Sim Lab: execution simulation only.
Backtests: performance measurement.
Operations Center: authoritative runtime state.
Broker Accounts / Providers: clear credential separation.
AI Builder: draft-only review flow.
Do not reuse old Account Monitor, Account Governor, Deployment Manager, Live Monitor, Logs Panel, or old Simulation/Chart Lab pages as-is.

13. Test and Validation Strategy
Test categories:

unit
integration
parity
acceptance
safety
migration
Required stop-ship tests:

FeatureKey determinism.
Feature parser rejects unsupported syntax.
Batch vs streaming FeatureSnapshot parity.
Multi-timeframe alignment uses latest completed higher-timeframe bar.
ORB unavailable before completion.
Chart Lab creates no orders, fills, positions, or PnL.
Sim Lab never calls Alpaca.
Sim Lab deterministic replay gives identical event logs.
Backtest cannot compute indicators outside Feature Engine.
AI cannot save unsupported features.
Deployment cannot start without warm FeaturePlan.
Broker Adapter is the only Alpaca order caller.
OrderManager creates internal Order before broker submission.
client_order_id includes account, deployment, program, intent, sequence.
Unknown/malformed order intent is never auto-canceled.
Global kill blocks all new opens.
Account pause blocks only that account.
Deployment pause blocks only that Deployment.
Pause preserves protective orders.
Flatten is separate from pause.
Broker stream stale blocks new opens.
Market data stale blocks affected symbols.
Paper/live mode mismatch blocks activation.
Portfolio Governor approves every new exposure.
Operations Center reflects effective runtime state.
Promotion gates:

Validation enforcement levels before Broker Runtime (Paper):

Required before Broker Runtime (Paper):

- Chart Lab validation
- Sim Lab validation
- Backtest with valid metrics

Strongly recommended before Broker Runtime (Paper):

- Optimization
- Walk-Forward

Optional / advanced:

- Monte Carlo
- regime stress tests
- portfolio interaction stress tests

Walk-Forward is not strictly required. Missing Walk-Forward must create a high-severity PromotionGate warning. Missing Optimization must create a PromotionGate warning. These warnings must not block promotion by default.

Broker Runtime (Paper) requires:

frozen Program
valid FeaturePlan
Chart Lab evidence
Sim Lab enforced-governor evidence
Backtest result
no unsupported features
Broker Runtime (Live) requires:

paper evidence
broker sync fresh
market data fresh
order ledger enabled
governor enabled
live readiness checklist
explicit operator approval
14. Migration Plan
Migration rule:

Old repo is reference only. Do not bulk-copy old backend/app or frontend/src/pages.
Do not copy as-is:

old runtime/governor routes
old AccountGovernor, AccountMonitor, DeploymentManager, LiveMonitor pages
old SimulationLab or ChartLab pages
old alpaca_service.py structure
old BacktestEngine._compute_indicators
old StrategyGovernor models/routes/pages
old AccountAllocation runtime lifecycle
old duplicate watchlist/data watchlist systems
old LogsPanel hardcoded roadmap/issues/journey UI
production seed/sample strategies
Candidate reuse only after review:

neutral UI primitives
chart primitives
old tests as acceptance-test inspiration
Alpaca SDK call knowledge
market calendar/session ideas after fixing calendar expiry and boundaries
Migration steps:

Create migration inventory for every considered old file.
Classify: do_not_copy, safe_reference, candidate_reuse, rewrite_from_scratch.
Define new domain models first.
Add naming lint rules for banned names.
Build Feature Registry v1 before any strategy migration.
Convert old sample strategies to test fixtures only.
Rewrite Alpaca integration behind adapters.
Rewrite Chart Lab and Sim Lab from scratch.
Build Operations Center from scratch.
Keep one migration decision log.
15. Hard Rules
Deployment is the only runtime unit.

AccountAllocation is not a runtime entity.

PortfolioGovernor and BrokerAccount are separate.

BrokerAccount owns broker truth only.

PortfolioGovernor is final internal authority only.

Program contains references only.

All deployable Programs reference frozen component versions.

FeatureEngine is the only computation layer.

Feature Registry is the only feature vocabulary.

SignalEngine stops at CandidateTradeIntent.

Strategy may not compute features.

Chart Lab may not create orders, fills, positions, PnL, or drawdown.

Sim Lab may not call Alpaca.

Backtest may not compute indicators privately.

MarketDataService owns provider streaming; BarBuilder owns aggregation; FeatureEngine owns features.

BrokerAdapter is the only Alpaca caller.

OrderManager creates internal orders before broker submission.

Every broker order must be attributable to account, deployment, program, and intent.

Unknown order intent is kept and flagged, never auto-canceled.

Pause/kill stops new opens; flatten closes positions.

Protective orders survive pause/kill.

Broker sync stale blocks new opens.

Market data stale blocks affected new opens.

AI suggests only; deterministic validators enforce.

AI cannot invent unsupported features.

AI cannot approve, reject, size, route, pause, flatten, or submit trades.

No old route aliases.

No generic Services bucket.

No hardcoded development roadmap/issues in product UI.

No production startup sample data.

16. First 10 Engineering Tasks
Create canonical domain models

Implement the new model skeletons for ProgramVersion, Deployment, PortfolioGovernor, BrokerAccount, Order, Trade, FeatureSpec, FeaturePlan, SimulationSession, ChartLabSession, and ValidationEvidence.

Implement Feature Registry v1

Add the small approved feature set only. Generate the Feature Vocabulary Catalog from it.

Implement Feature Parser and FeatureKey

Support canonical syntax and reject unsupported features, params, and timeframe aliases.

Implement Feature Planner

Program validation must fail if required features, timeframes, warmup, or consumer support are invalid.

Implement batch Feature Engine and parity harness

Produce FeatureSnapshots and begin batch-vs-streaming replay parity tests.

Implement Signal Engine

Consume FeatureSnapshots only and emit CandidateTradeIntent with decision diagnostics.

Implement Chart Lab backend contract

Build session, snapshot, condition truth, and component preview endpoints. Enforce no orders/fills/PnL.

Implement Sim Lab core

Build SimulationSession, event log, simulated broker, fill models, simulated ledgers, and decision trace.

Implement Alpaca adapter boundary

Create AlpacaMarketDataAdapter and AlpacaBrokerAdapter; block all other Alpaca access.

Implement OrderManager and BrokerSync foundation

Create internal orders before submission, assign client_order_id, handle partial fills, reconcile broker state, and flag unknown external orders.
