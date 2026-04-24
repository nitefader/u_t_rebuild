Master System Reset Output
1. Executive Diagnosis
The current system is not one Trading OS. It is a collection of partially merged systems: strategy builder, component library, backtester, simulator, optimizer, deployment manager, account monitor, live monitor, and governor surfaces. The target docs define a clean architecture, but the reference implementation still violates it in naming, persistence, workflow, and runtime execution.

The core failure is this: the system has no single authoritative lifecycle artifact moving through:

Idea → Program → Validate → Chart Lab → Sim Lab → Backtest → Optimize → Walk-Forward → Paper → Live → Monitor → Improve

Instead, users can enter through Strategies, Programs, Backtests, Sim Lab, Optimization Lab, Dashboard, Account Governor, Deployment Manager, or Live Monitor. These paths mutate or launch overlapping artifacts, creating drift.

The biggest architectural problem is not missing features. It is competing authority:

StrategyVersion.config still carries non-strategy concerns.
TradingProgram references components but also owns inline execution and universe behavior.
Deployment acts as runtime instance, governor stand-in, promotion record, risk link, and observability object.
AccountAllocation overlaps with Deployment.
Portfolio Governor is not a first-class entity.
Feature computation is not yet the single enforced computation layer.
Backtest, simulation, paper, and live are not guaranteed to use the same feature and signal pipeline.
The rebuild must stop extending the old system shape. The reset must enforce one domain model, one runtime path, one computation layer, one promotion state machine, and one operator control surface.

2. Architectural Violations
Program boundary is porous
Canonical rule: Programs reference components.

Violation:

TradingProgram.execution_policy duplicates ExecutionStyle.
TradingProgram.duration_mode duplicates StrategyVersion.duration_mode and StrategyControls.duration_mode.
Program universe behavior is split across watchlist_subscriptions, watchlist_combination_rule, live_universe_*, and SymbolUniverseSnapshot.
Program resolution flattens Strategy Controls, Risk Profile, and Execution Style back into a config blob.
Hard consequence:
The system cannot reliably answer “what exactly was traded?” because effective behavior is reconstructed instead of owned.

Strategy is not signal-only
Canonical rule: Strategy owns signal truth only.

Violation:

StrategyVersion.config still carries stop, target, execution-ish, risk-ish, duration, event, and overlay-derived fields.
Builder flows allow strategy authoring to blur into controls, risk, and execution.
Validation explicitly needs to reject misplaced risk/session/execution fields, meaning the architecture already knows leakage exists.
Hard consequence:
A strategy version is not a clean portable idea. It is a semi-runtime config packet.

Feature Engine is not the only computation layer
Canonical rule: Feature Engine is the only computation layer.

Violation:

Backtest computation uses BacktestEngine._compute_indicators().
Live runtime uses CerebroEngine / IndicatorCache, but still re-enters backtest-style batch indicator computation.
Simulation uses a stepper path.
Chart Lab depends on cached data and local visual overlays.
Technical indicators still exist under backend/app/indicators/*.
Feature planning exists, but not as an unavoidable contract for every mode.
Hard consequence:
The same strategy can produce different signals in Chart Lab, Sim Lab, Backtest, Paper, and Live.

Chart Lab and Sim Lab responsibilities overlap
Canonical rule:

Chart Lab = signal validation.
Sim Lab = execution simulation.
Violation:

Chart Lab overlaps with Simulation Lab on indicators, exploratory validation, and visual behavior.
Simulation Lab overlaps with Backtest on market-data validation and strategy behavior.
Trade replay appears inside Run Details as another simulation-like tool.
Hard consequence:
Users cannot tell whether they are validating signal truth, execution mechanics, historical performance, or runtime behavior.

Governor is not final authority
Canonical rule: Governor is final authority before broker.

Violation:

Control logic is spread across kill_switch, control.py, governor.py, deployment_service.py, account_governor_loop.py, alpaca_service.py, and account routes.
Portfolio Governor is not a first-class persistent ORM entity.
Governor events are tied to ids currently backed by Deployment.
Runtime entry checks historically use deployment/governor status plus kill switch state, not one unavoidable authority path.
Broker order submission safety depends on convention.
Hard consequence:
There is no single proof that every new open passes through the same final authority.

Runtime unit is split
Canonical rule:

Program = design-time package.
Deployment = running instance of a Program on a Broker Account.
Violation:

Deployment and AccountAllocation both represent runtime-ish activation.
Both carry lifecycle/promotion/account-binding meanings.
Promotion exists as strategy promotion, run promotion, deployment promotion, and allocation promotion.
Hard consequence:
The system cannot cleanly define what is being promoted, paused, resumed, stopped, or monitored.

Broker Account and internal account policy are mixed
Canonical rule: Broker Account owns broker truth, not policy.

Violation:

Account stores broker credentials, broker balances, inline risk fields, kill flags, data-service linkage, and risk-profile linkage.
Risk Profile also owns risk limits.
Account Monitor, Credential Manager, Services, and Account Governor all touch adjacent credential/account/control concerns.
Hard consequence:
“Account” is overloaded as broker truth, credential vault, risk surface, runtime control scope, and data provider proxy.

Validation evidence is fragmented
Canonical rule: Validate before promotion.

Violation:

RunMetrics.walk_forward and ValidationEvidence.walk_forward overlap.
Run Details, Optimization Lab, Logs Panel, Journey Validations, and promotion panels all expose partial validation.
Only 3 of 150 journey validations are fully covered, with 145 uncovered.
P0 validation gaps remain around partial fills, kill/pause/flatten, websocket freshness, holiday behavior, no-lookahead, and promotion evidence.
Hard consequence:
The system can appear “ready” while critical validation gates are unproven.

3. Duplicated Responsibilities
Responsibility	Current Duplicate Owners	Required Owner
Signal logic	StrategyVersion.config, builder overlays, backtest config blobs	Strategy + Signal Engine
Feature computation	BacktestEngine, IndicatorCache, technical.py, simulation prep, chart overlays	Feature Engine only
Strategy permission / timing	StrategyControls, EventFilter, StrategyVersion.duration_mode, TradingProgram.duration_mode	Strategy Controls
Risk limits	RiskProfile, Account inline fields, allocation overrides, deployment fields, governor status	Risk Profile + Portfolio Governor
Execution mechanics	ExecutionStyle, TradingProgram.execution_policy, strategy config stop/target/entry fields	Execution Style
Universe definition	Watchlist, WatchlistMembership, data_watchlists, SymbolUniverseSnapshot, program live-universe fields	Watchlist/Universe layer
Runtime activation	Deployment, AccountAllocation, governor allocation routes	Deployment only
Portfolio authority	Deployment, governor_service, account_governor_loop, conflict_resolver, kill switch	Portfolio Governor
Broker truth	Account, alpaca_service, monitor payloads, paper broker, position ledger	Broker Account + Order/Position Ledger
Trade record	Trade, DeploymentTrade, broker responses	Unified Trade Ledger
Order record	Broker responses, OrderAuditEntry, monitor payloads	Persistent Order Ledger
Promotion	Strategy version promotion, run promotion, deployment promotion, allocation promotion	Promotion Gate / Lifecycle Service
Backtest result browsing	Run History, Dashboard recent runs, Optimization Lab results	Validation Hub
Live operations	Account Monitor, Account Governor, Deployment Manager, Live Monitor	Operations Center
Credentials	Services, Credential Manager, Account credentials	Credential Vault / Provider Accounts
Logs/issues/roadmap	Logs Panel, hardcoded UI lists, admin APIs	Admin/Observability layer
4. Missing Layers
Program Lifecycle Orchestrator
Missing authority that owns:

Idea intake
Program creation
validation gates
promotion state
paper/live eligibility
improvement loop
Without it, pages launch each other laterally.

Signal Engine
Feature Engine computes values. Signal Engine evaluates strategy logic against those values.

Current gap:
Strategies and backtest/simulation/live paths still risk evaluating conditions in mode-specific ways.

Required:

no indicator computation
no portfolio checks
no order building
emits only candidate trade intents
Persistent Order Ledger
Current gap:
Orders are core but not first-class durable entities.

Required:

internal order id
broker order id
client order id
intent: open, close, tp, sl, scale
deployment id
program id
broker account id
lifecycle state
parent/child relationship
cancellation/protection classification
Unified Trade Ledger
Current gap:
Trade and DeploymentTrade split research/runtime trade concepts.

Required:

one normalized trade model
mode: backtest, sim, paper, live
source order/fill references
strategy/program/deployment lineage
metrics and replay provenance
Portfolio Governor Entity
Current gap:
Portfolio Governor is serialized through Deployment-ish structures and events.

Required:

first-class governor id
account/portfolio scope
risk profile linkage
active constraints
current state
decision log
projected-state evaluator
Runtime State Store
Current gap:
Runtime state is split across DB fields, in-memory kill switch, deployment status, governor status, broker snapshots, and websocket payloads.

Required:

authoritative deployment state
active feature-plan registration
control-plane state
broker sync freshness
last decision timestamps
restart hydration contract
Feature Provenance Store
Current gap:
Feature plans do not fully capture data source, calendar version, computation version, or cache lineage.

Required:

feature spec version
data provider
timestamp normalization
calendar version
pandas/library version where relevant
warmup policy
batch/live parity evidence
Validation Gate Layer
Current gap:
Validation evidence exists but is scattered.

Required gates:

signal visual validation complete
sim execution validation complete
backtest complete
no-lookahead checks passed
walk-forward passed
optimization/overfit review complete
paper readiness checklist passed
live readiness checklist passed
Operations Center
Current gap:
Live Monitor, Account Monitor, Account Governor, and Deployment Manager compete.

Required:
One surface for:

effective control state
active deployments
open positions
open orders
stale broker sync
websocket freshness
kill/pause/flatten results
governor decisions
Unified Provider/Credential Layer
Current gap:
Services and Credential Manager both handle provider credentials.

Required:

broker trading credentials
market data credentials
AI credentials
explicit provider capability matrix
test history
paper/live mode validation
5. Corrected Architecture
The corrected architecture must be layered like this:

Idea Layer
  Idea
  Hypothesis
  Research notes

Component Layer
  Strategy
  Strategy Controls
  Risk Profile
  Execution Style
  Watchlist / Universe

Program Layer
  Program
    references Strategy
    references Strategy Controls
    references Risk Profile
    references Execution Style
    references Watchlist / Universe
    owns no inline logic

Validation Layer
  Chart Lab
    validates signal truth visually
  Sim Lab
    validates execution behavior mechanically
  Backtest
    validates historical performance
  Optimization
    searches parameters or portfolio weights
  Walk-Forward
    validates robustness and regime stability
  Validation Evidence
    stores gate results

Computation Layer
  Feature Planner
  Feature Registry
  Feature Engine
  Feature Cache
  Signal Engine

Runtime Layer
  Deployment
    running Program on Broker Account
  Runtime Feature Registry
  Runtime State Store
  Order Ledger
  Trade Ledger

Governance Layer
  Portfolio Governor
  Kill / Pause / Flatten Control Plane
  Projected Exposure Evaluator
  Risk Decision Log

Broker Layer
  Broker Account
  Broker Adapter
  Broker Positions
  Broker Orders
  Broker Fills

Operations Layer
  Operations Center
  Monitoring
  Alerts
  Improvement Loop
Correct flow:

Idea
→ Strategy + Components
→ Program
→ Feature Plan
→ Chart Lab signal validation
→ Sim Lab execution simulation
→ Backtest
→ Optimize
→ Walk-Forward
→ Paper Deployment
→ Portfolio Governor approval
→ Broker Account execution
→ Operations Center monitoring
→ Evidence-driven improvement
6. Component Responsibility Table
Component	Owns	Must Not Own	Current Problem
Idea	thesis, hypothesis, notes	executable config	No clean idea layer exists
Strategy	entry logic, exit logic, signal truth, stop/target candidates	sizing, sessions, order mechanics, broker calls	StrategyVersion.config carries too much
Feature Engine	all computed features across modes	signal decisions, order decisions	Backtest/live/sim still compute through separate paths
Signal Engine	evaluates strategy against features	feature computation, risk approval, broker submission	Missing as explicit layer
Strategy Controls	timeframe, sessions, cooldowns, event blackout, regime permission	signal truth, sizing, order mechanics	Still named Strategy Governor in places
Risk Profile	position sizing, max loss, exposure limits, fallback risk protection	entry logic, sessions, order expression	Duplicated by account inline risk
Execution Style	order type, TIF, brackets, trailing, cancel/replace, scale-out mechanics	signal truth, risk budget, portfolio approval	Duplicated by TradingProgram.execution_policy
Watchlist / Universe	tradable symbol set and resolution rules	signal, risk, execution, broker policy	Split across multiple watchlist/universe concepts
Program	immutable references to components	runtime state, broker truth, inline logic	Currently still owns inline execution/universe fields
Chart Lab	visual signal validation	execution simulation, performance claims	Overlaps with Sim Lab and Data Manager
Sim Lab	execution simulation, replay mechanics, fill behavior	signal authoring, portfolio promotion	No durable simulation model
Backtest	historical performance evidence	live runtime truth, manual promotion authority	Overlaps with Optimization and Run Details promotion
Optimization	parameter/weight search	validation proof by itself	Results UI duplicates Run History
Walk-Forward	robustness evidence	generic metric display only	Evidence duplicated across metrics and validation tables
Deployment	running Program on Broker Account	component definitions, governor identity	Overloaded with promotion/risk/governor state
Portfolio Governor	final approval, projected portfolio checks, conflict resolution	signal generation, broker truth storage	Not first-class entity
Broker Account	broker balances, restrictions, positions, fills	internal policy	Mixed with risk and credentials
Order Ledger	internal/broker order lifecycle and intent	strategy approval	Missing first-class persistent entity
Trade Ledger	normalized trade lifecycle across modes	order routing	Split between Trade and DeploymentTrade
Operations Center	monitor/control active runtime	program authoring	Currently split across 4 pages
7. End-to-End Flow
Idea
User records a trading thesis.

Output:

idea record
hypothesis
target market/symbol universe concept
intended holding period
No execution fields allowed.

Program
User assembles reusable components:

Strategy
Strategy Controls
Risk Profile
Execution Style
Watchlist / Universe
Output:

Program draft
Rule:
Program stores references only. No inline trading logic.

Validate
Validation begins by building a Feature Plan from the complete Program.

Output:

feature requirements
data requirements
unsupported-feature errors
warmup requirements
provenance plan
Rule:
If the Feature Engine cannot compute it, the Program cannot proceed.

Chart Lab
Purpose:
Signal validation only.

Inputs:

Program
Feature Plan
cached/historical bars
Signal Engine output
Outputs:

signal markers
feature overlays
visual validation notes
signal mismatch warnings
Forbidden:

execution simulation
paper/live controls
performance claims beyond visual signal evidence
Sim Lab
Purpose:
Execution simulation only.

Inputs:

validated signal stream
Execution Style
Risk Profile
simulated fills
partial-fill and order-state model
Outputs:

execution behavior evidence
order lifecycle replay
fill/slippage diagnostics
Forbidden:

redefining signals
computing features outside Feature Engine
promoting directly to live
Backtest
Purpose:
Historical performance.

Inputs:

immutable Program snapshot
Feature Plan
frozen component versions
data provenance
deterministic engine version
Outputs:

BacktestRun
Trade Ledger entries
metrics
anti-bias evidence
feature provenance
Rule:
Backtest must use the same Feature Engine and Signal Engine as all other modes.

Optimize
Purpose:
Search parameters or weights.

Inputs:

completed backtest evidence
explicit objective
bounded parameter grid
validation constraints
Outputs:

Optimization Profile
Weight Profile or parameter candidate
ranked candidates
overfit warnings
Forbidden:

treating optimizer rank as validation proof
Walk-Forward
Purpose:
Robustness validation.

Inputs:

candidate Program snapshot
fold definition
IS/OOS split
data provenance
Outputs:

fold evidence
degradation profile
promotion eligibility result
Rule:
Walk-forward evidence belongs to Validation Evidence, not scattered metric sidecars.

Paper
Purpose:
Runtime rehearsal.

Inputs:

frozen Program
Broker Account in paper mode
Portfolio Governor
runtime Feature Plan
Outputs:

Deployment
Order Ledger
Trade Ledger
Governor decisions
paper evidence
Rule:
Every new open must pass:
Feature Engine → Signal Engine → Strategy Controls → Risk Profile → Execution Style → Portfolio Governor → Broker Adapter

Live
Purpose:
Real broker execution.

Inputs:

paper-approved Program
live Broker Account
live readiness checklist
explicit operator approval
Outputs:

live Deployment
broker-synced Order Ledger
broker-synced Trade Ledger
Governor decision log
Rule:
Live promotion cannot be launched from Run Details, Optimization Lab, or any analysis surface. It must happen through the promotion gate.

Monitor
Purpose:
Operate the running system.

Single surface:

active deployments
broker account state
open positions
open orders
protective order status
governor decisions
kill/pause/flatten state
stale websocket/broker warnings
Rule:
Operations Center is authoritative. Other pages may link to it but not duplicate it.

Improve
Purpose:
Close the loop.

Inputs:

live/paper deviations
rejected governor decisions
slippage/fill evidence
signal misses
validation failures
Outputs:

new idea notes
new StrategyVersion or component version
new Program version
Rule:
Improvement creates a new immutable version. It does not mutate historical evidence.

8. Hard Rules
Strategy is signal-only.

Programs reference components. Programs do not inline component behavior.

Feature Engine is the only computation layer.

Signal Engine evaluates signals. It does not compute indicators.

Chart Lab validates signals only.

Sim Lab simulates execution only.

Backtest, Sim Lab, Paper, and Live must share the same Feature Engine and Signal Engine.

Strategy Controls own permission timing, sessions, cooldowns, event blackout, and regime gates.

Risk Profile owns sizing and loss/exposure limits.

Execution Style owns order expression only.

Portfolio Governor is the final internal authority.

Broker Account is external truth, not policy.

Deployment is runtime instance only.

AccountAllocation must not coexist as a competing runtime unit.

Portfolio Governor must be a first-class persistent entity.

Orders must be first-class persistent entities.

Trades must be normalized across backtest, simulation, paper, and live.

Kill/pause must stop new opens without flattening positions unless explicitly requested.

Flatten must be separate from kill/pause.

Protective exits must survive pause/kill.

Every order must carry intent.

Unknown order intent must fail closed: keep and flag, never cancel blindly.

Promotion must be one state machine.

Validation evidence must be required before paper/live.

Mutable component edits must create new versions.

Historical runs must store frozen config snapshots.

No page may claim authority over runtime state unless it uses the Operations Center source of truth.

No hardcoded sample/roadmap/known-issue product data belongs in production UI.

Unsupported feature names must be impossible to deploy.

Any stale broker, websocket, feature, or governor state must display as unknown/stale, never safe.

9. Immediate Fix Sequence
Freeze the taxonomy
Rename and enforce:

Strategy Governor → Strategy Controls
Account Governor / bare Governor → Portfolio Governor
Account → Broker Account where broker truth is meant
Trading Program → Program
Deployment → runtime instance only
Remove route aliases that map different concepts to the same page.

Pick one runtime unit
Make Deployment the only runtime instance.

Retire or demote AccountAllocation into either:

deployment creation input, or
allocation policy attached to Portfolio Governor
It must not remain a peer runtime object.

Create first-class Portfolio Governor
Add explicit persistent governor entity.

It owns:

account/portfolio scope
constraints
current state
final approval decisions
projected-state checks
event log
Stop encoding governor identity through Deployment.

Remove inline Program behavior
Program may reference:

StrategyVersion
StrategyControlsVersion
RiskProfileVersion
ExecutionStyleVersion
Watchlist/Universe snapshot
Program must not own:

execution_policy
duplicated duration_mode
live universe cache
inline risk settings
Version all mutable components
Required immutable versions:

Strategy Controls
Risk Profile
Execution Style
Watchlist/Universe snapshot
Program
Backtest and deployment must store exact version ids.

Make Feature Engine mandatory
All modes must call:

Feature Planner
Feature Engine
Signal Engine
Remove direct indicator computation from:

strategy config evaluation
simulation stepper
backtest-only paths
chart-only overlays
live indicator cache bypasses
Split Chart Lab and Sim Lab
Chart Lab:

feature overlays
signal markers
signal condition truth table
Sim Lab:

order lifecycle
fills
partial fills
slippage
stop/target behavior
execution timing
No shared ambiguous “validation” UI without mode labels.

Unify validation gates
Create one Validation Evidence model and one Promotion Gate.

Promotion to paper requires:

Chart Lab signal validation
Sim Lab execution validation
Backtest metrics
Walk-forward evidence
no unsupported features
no open P0 validation failures
Promotion to live requires:

paper runtime evidence
broker sync evidence
order/fill audit evidence
governor readiness
explicit live approval
Create persistent Order Ledger
Before live work continues, implement durable orders.

Minimum fields:

internal id
broker id
client order id
intent
status
symbol
qty
side
order type
parent order id
deployment id
program id
broker account id
timestamps
last broker sync
failure reason
Collapse operations pages
Replace overlapping runtime pages with one Operations Center.

Merge:

Account Monitor
Account Governor
Deployment Manager
Live Monitor
Keep separate admin pages only for:

credentials/providers
backup/restore
audit logs
10. Stop-Ship Risks
Feature computation drift
Backtest, simulation, paper, and live can produce different signals.

Stop-ship because:
A strategy can pass backtest and fail live for architecture reasons, not market reasons.

Lookahead bias in indicators
Swing/fractal-style features may expose future-confirmed values at the original bar.

Stop-ship because:
Backtest performance can be inflated silently.

Live multi-timeframe mismatch
Audit notes indicate multi-timeframe indicators in live mode can diverge or fail relative to backtest.

Stop-ship because:
Any 5m strategy using 1h/daily context may behave differently in production.

No first-class Order entity
Orders are reconstructed from broker payloads and service dataclasses.

Stop-ship because:
Control-plane safety, incident review, partial-fill handling, and protective-order preservation require durable order truth.

Governor not first-class
Portfolio Governor is not modeled as a standalone authority.

Stop-ship because:
The system cannot prove final approval happened consistently.

Deployment vs AccountAllocation split
Two runtime units compete.

Stop-ship because:
Pause, resume, promote, stop, monitor, and audit semantics can target the wrong artifact.

Kill/pause/flatten ambiguity
Multiple pages and APIs expose overlapping emergency actions.

Stop-ship because:
An operator may believe positions were flattened when only new opens were paused, or may cancel protective orders accidentally.

Credential/account/provider split
Services, Credential Manager, Data Manager, and Account setup all touch related provider auth.

Stop-ship because:
Data may work while trading fails, or paper/live mode may be misrepresented.

Hardcoded market calendar risk
Calendar support is hardcoded through 2026 in the reference audit.

Stop-ship before 2027 because:
Session-aware features, half-day handling, blackout rules, and market-hours controls can silently corrupt.

Validation coverage is mostly absent
Only 3 of 150 journeys are fully covered; 145 are uncovered.

Stop-ship because:
Critical P0 flows around live monitoring, partial fills, kill/pause/flatten, websocket freshness, holiday behavior, and promotion evidence remain unvalidated.