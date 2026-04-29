Repo Cleanup Output
1. Executive Summary
The old repo must not be migrated wholesale. It contains useful lessons, tests, and partial implementations, but its domain model conflicts with the new Trading OS.

The new repo must treat the old project as a reference archive, not a base codebase.

Primary decision:

Copy almost nothing directly.
Reuse concepts selectively.
Rewrite core architecture around the new model.
The old repo has too many overlapping runtime units, UI surfaces, service boundaries, and naming conventions. Migrating files directly would preserve the exact fragmentation the rebuild is meant to remove.

Highest-risk old concepts:

AccountAllocation as runtime object
StrategyGovernor naming
AccountGovernor page/model semantics
Deployment as governor/runtime/promotion hybrid
direct indicator computation outside Feature Engine
duplicate watchlist systems
duplicate credential systems
old monitor/governor/deployment pages
old route aliases
hardcoded roadmap/issues/sample product state
mock/sample data exposed as product behavior
2. Do Not Copy List
Do not copy these as-is into the new repo.

Frontend Pages
frontend/src/pages/AccountGovernor.tsx
frontend/src/pages/AccountMonitor.tsx
frontend/src/pages/DeploymentManager.tsx
frontend/src/pages/LiveMonitor.tsx
frontend/src/pages/SimulationLab.tsx
frontend/src/pages/ChartLab.tsx
frontend/src/pages/OptimizationLab.tsx
frontend/src/pages/RunHistory.tsx
frontend/src/pages/RunDetails.tsx
frontend/src/pages/BacktestLauncher.tsx
frontend/src/pages/TradingPrograms.tsx
frontend/src/pages/StrategyGovernors.tsx
frontend/src/pages/Services.tsx
frontend/src/pages/CredentialManager.tsx
frontend/src/pages/DataManager.tsx
frontend/src/pages/LogsPanel.tsx
Reason:
These pages encode old boundaries, duplicated authority, or mixed responsibilities.

Specific issues:

AccountGovernor, DeploymentManager, and LiveMonitor all compete for runtime authority.
ChartLab and SimulationLab are not cleanly separated by signal validation vs execution simulation.
OptimizationLab, RunHistory, and RunDetails duplicate validation/result surfaces.
TradingPrograms contains too much composition, launch, deployment, and promotion behavior.
StrategyGovernors.tsx preserves wrong terminology.
Services and CredentialManager preserve duplicate credential concepts.
LogsPanel mixes logs, roadmap, issues, journey validation, and feature-build status.
Backend Runtime / Governor Routes
backend/app/api/routes/governor.py
backend/app/api/routes/control.py
backend/app/api/routes/deployments.py
backend/app/api/routes/monitor.py
backend/app/api/routes/programs.py
backend/app/api/routes/strategy_governors.py
Reason:
These routes reflect the old split between account governor, deployment, control, monitor, and program allocation flows.

Do not copy route contracts. Redesign around:

/programs
/deployments
/portfolio-governors
/operations
/control-plane
/broker-accounts
/orders
/trades
Backend Models
Do not copy as canonical:

backend/app/models/trading_program.py
backend/app/models/deployment.py
backend/app/models/strategy_governor.py
backend/app/models/account.py
backend/app/models/trade.py
backend/app/models/deployment_trade.py
backend/app/models/data_service.py
backend/app/models/program_backlog.py
backend/app/models/kill_switch.py
backend/app/models/governor_event.py
Reason:
These models contain naming conflicts or ownership conflicts.

Specific decisions:

AccountAllocation must not survive as runtime.
StrategyGovernor must become StrategyControls.
Account must become BrokerAccount where broker truth is meant.
Trade and DeploymentTrade must be replaced by one Trade Ledger model.
DataService must split market data, broker, and AI providers.
ProgramBacklogItem must not use trading-domain word Program.
KillSwitchEvent must be redesigned under Control Plane audit events.
GovernorEvent must belong to first-class PortfolioGovernor, not Deployment-backed ids.
Backend Services
Do not copy as-is:

backend/app/services/deployment_service.py
backend/app/services/governor_service.py
backend/app/services/account_governor_loop.py
backend/app/services/conflict_resolver.py
backend/app/services/position_ledger.py
backend/app/services/promotion_service.py
backend/app/services/simulation_service.py
backend/app/services/backtest_service.py
backend/app/services/optimization_service.py
backend/app/services/ai_service.py
backend/app/services/alpaca_service.py
backend/app/services/alpaca_stream_manager.py
backend/app/services/alpaca_stream_client.py
backend/app/services/alpaca_account_stream.py
backend/app/services/market_data_service.py
backend/app/services/paper_broker.py
Reason:
Some logic may be useful, but service boundaries are wrong.

Must be rewritten behind new services:

FeatureEngine
SignalEngine
StrategyControlsGate
RiskEngine
ExecutionIntentBuilder
PortfolioGovernorService
OrderManager
BrokerAdapter
BrokerSyncService
MarketDataService
BarBuilder
SimulationEngine
ValidationEvidenceService
Indicator / Feature Computation
Do not copy as live architecture:

backend/app/indicators/*
backend/app/cerebro/*
backend/app/features/* as-is
backend/app/core/backtest.py indicator computation paths
Reason:
The old feature system is partial and split across indicators, cerebro, backtest, cache, and feature planner.

Can be referenced, but not copied directly.

New system must enforce:

FeatureSpec
FeatureKey
FeatureRegistry
FeaturePlanner
FeatureCache
FeatureEngine
Old Docs / Internal Product Artifacts
Do not copy into product docs as active truth:

docs/application-map.md
docs/architecture-presentation.html
docs/System Audit/*
docs/system_rebuild/*
STATE.md
UAT_UX_REPORT.md
iteration_1_plan.md
backend.log
prompts/*
Reason:
Useful as reference only. They reflect old architecture, not target system.

3. Safe Reference List
These can be used for analysis and requirements extraction, not direct implementation.

docs/Canonical_Architecture.md
docs/Control_Plane_Spec.md
docs/Feature_Engine_Spec.md
docs/Feature_Engine_Build.md
docs/Feature_Vocabulary_Catalog.md
docs/User_Journey_Validations.md
docs/System Audit/STRUCTURAL_PROBLEMS_AUDIT.md
docs/System Audit/COMPLETE_ENTITY_MODEL_INVENTORY.md
docs/System Audit/feature_engine_audit.md
docs/System Audit/page_inventory.md
docs/System Audit/COMPLETE_ALPACA_AGENT_INSPECTION.md
docs/System Audit/ai_capability_audit.md
Safe reference value:

terminology problems
user journey gaps
acceptance criteria
known Alpaca pitfalls
feature parity risks
old UI overlap
route inventory
model inventory
Not safe for copying:

old names
old route structure
old page structure
old service boundaries
old promotion model
4. Candidate Reuse List
These may be reused only after boundary review and renaming.

Tests
Candidate reference:

backend/tests/test_feature_catalog.py
backend/tests/test_feature_cache_runtime.py
backend/tests/test_feature_planner.py
backend/tests/test_feature_ingress_contract.py
backend/tests/test_feature_preview.py
backend/tests/test_feature_specs_registry.py
backend/tests/test_alpaca_service.py
backend/tests/test_alpaca_stream_manager.py
backend/tests/test_alpaca_stream_client.py
backend/tests/test_alpaca_account_stream.py
backend/tests/test_alpaca_provider_cache.py
backend/tests/test_alpaca_provider_timezone.py
backend/tests/test_alpaca_base_url_mode_mismatch.py
backend/tests/test_kill_switch.py
backend/tests/test_walk_forward_framework.py
backend/tests/test_backtest_replay_provider_contract.py
backend/tests/test_simulation_ingress.py
Reuse rule:
Use as acceptance-test inspiration. Do not assume old APIs remain.

Market Calendar / Session Logic
Candidate reference:

backend/app/services/market_calendar_service.py
backend/app/features/context/session_context.py
backend/app/features/computations/session.py
Reuse only if:

calendar is not hardcoded through 2026 only
half-days are supported
session features are registry-owned
Feature Engine owns output
no direct strategy evaluation depends on these modules
Alpaca API Knowledge
Candidate reference:

backend/app/services/alpaca_service.py
backend/app/services/alpaca_stream_client.py
backend/app/services/alpaca_stream_manager.py
backend/app/services/alpaca_account_stream.py
Reuse only for:

SDK call patterns
request/response shape
known Alpaca quirks
test fixtures
Do not reuse as service structure. New structure must split:

AlpacaMarketDataAdapter
AlpacaBrokerAdapter
BrokerSyncService
OrderManager
UI Components
Candidate reference:

frontend/src/components/Tooltip.tsx
frontend/src/components/ConfirmationModal.tsx
frontend/src/components/ErrorBoundary.tsx
frontend/src/components/SelectMenu.tsx
frontend/src/components/TickerSearch.tsx
frontend/src/components/Charts/*
frontend/src/hooks/useWebSocket.ts
frontend/src/hooks/usePollingGate.ts
frontend/src/styles/tokens.css
Reuse only if visually and architecturally neutral.

Do not reuse components that carry old domain terms or old API assumptions without rewriting props.

Strategy Builder Pieces
Candidate reference:

frontend/src/components/StrategyBuilder/*
Potential value:

condition tree UI
form primitives
strategy authoring patterns
Must rewrite if:

it lets strategy absorb controls/risk/execution fields
it uses unsupported feature names
it bypasses Feature Registry
it cannot show FeatureSpec compatibility
5. Rewrite From Scratch List
These must be rewritten from scratch.

Core Domain Models
Strategy
StrategyVersion
StrategyControls
StrategyControlsVersion
RiskProfile
RiskProfileVersion
ExecutionStyle
ExecutionStyleVersion
Universe
UniverseSnapshot
Program
ProgramVersion
Deployment
PortfolioGovernor
BrokerAccount
Order
Fill
Trade
ControlPlaneEvent
ValidationEvidence
FeatureSpec
FeaturePlan
FeatureFrame
SimulationSession
ChartLabSession
AIProgramDraft
ProviderCredential
Core Engines
FeatureEngine
SignalEngine
StrategyControlsGate
RiskEngine
ExecutionIntentBuilder
PortfolioGovernor
OrderManager
BrokerSyncService
SimulationEngine
ChartLabPreviewService
ValidationGateService
AIValidationService
Product Surfaces
Rewrite as new pages:

Programs
Components
Universes
Chart Lab
Sim Lab
Backtest
Optimize
Walk-Forward
Deployments
Operations Center
Portfolio Governor
Broker Accounts
Providers
Audit Logs
Alpaca Integration
Rewrite around:

AlpacaMarketDataAdapter
AlpacaBrokerAdapter
MarketDataService
HistoricalDataService
BrokerSyncService
OrderManager
The old single alpaca_service.py style is too broad.

Control Plane
Rewrite around one ControlPlaneService.

Required concepts:

global kill
account pause
deployment pause
flatten
protective order preservation
scope-aware cancellation
unknown order flagging
structured result object
6. Duplicate Concept Findings
Runtime Unit Duplication
Old duplicate:

Deployment
AccountAllocation
Final decision:
Deployment only.

AccountAllocation must be deleted or reduced to non-runtime CapitalAllocationPolicy.

Governor Duplication
Old duplicate:

Account Governor
Portfolio Governor
Strategy Governor
Governor
Strategy Controls
Final decision:

PortfolioGovernor = final portfolio authority
StrategyControls = timing/permission component
No other governor naming.

Account Duplication
Old duplicate:

Account
Broker Account
Account Monitor
Account Governor
Credential account
Data-service account
Final decision:

BrokerAccount = broker truth and broker credentials
ProviderCredential = external provider credentials
PortfolioGovernor = policy
OperationsCenter = monitoring/control UI
Watchlist / Universe Duplication
Old duplicate:

Watchlist
WatchlistMembership
data_watchlists
SymbolUniverseSnapshot
watchlist_subscriptions
live_universe_*
Final decision:

Universe = Program-facing symbol contract
Watchlist = optional Universe source
UniverseSnapshot = frozen resolved symbol set
No second watchlist system under Data Manager.

Feature Computation Duplication
Old duplicate:

BacktestEngine._compute_indicators
technical.py
IndicatorCache
CerebroEngine
simulation prep
chart overlays
Final decision:

FeatureEngine only
Credential Duplication
Old duplicate:

Services
CredentialManager
Account credentials
DataManager provider shortcuts
Final decision:

ProviderCredentials
BrokerAccount credentials
clear provider type separation
Monitoring Duplication
Old duplicate:

AccountMonitor
AccountGovernor
DeploymentManager
LiveMonitor
Dashboard runtime widgets
Final decision:

OperationsCenter is authoritative runtime UI
Validation Duplication
Old duplicate:

RunHistory
RunDetails
OptimizationLab results
Dashboard recent runs
LogsPanel journey validations
Final decision:

ValidationEvidence and dedicated Validate surfaces
Trade / Order Duplication
Old duplicate:

Trade
DeploymentTrade
OrderAuditEntry
broker order payloads
monitor orders
Final decision:

Order Ledger
Fill Ledger
Trade Ledger
7. Naming Problems
Banned names in new repo:

StrategyGovernor
AccountGovernor
Governor as bare name
Account when BrokerAccount is meant
TradingProgram if Program is canonical
Run when BacktestRun or SimulationSession is meant
Services as generic provider page
DataService for AI providers
DeploymentManager as authority page
LiveMonitor as separate authority page
ProgramBacklogItem for delivery planning
Required names:

StrategyControls
PortfolioGovernor
BrokerAccount
Program
Deployment
Universe
UniverseSnapshot
ProviderCredential
MarketDataProvider
AIProvider
BrokerAdapter
OrderManager
BrokerSync
OperationsCenter
ValidationEvidence
ControlPlane
Route naming must match concepts:

/programs
/components/strategy-controls
/components/risk-profiles
/components/execution-styles
/universes
/chart-lab
/sim-lab
/backtests
/optimizations
/walk-forward
/deployments
/operations
/portfolio-governors
/broker-accounts
/providers
/audit-logs
Do not preserve aliases like:

/governor
/governors
/account-governor
/portfolio-governors pointing to deployments
/accounts and /broker-accounts pointing to same old page
8. Sample / Mock Data Risks
The old repo contains sample strategies, golden templates, seed scripts, sample watchlists, sample events, and hardcoded UI issue lists.

High-risk files/concepts:

backend/seed_templates.py
backend/scripts/seed_golden_templates.py
backend/scripts/seed_inventory.py
scripts/seed_strategies.py
backend/configs/strategies/*
backend/configs/watchlists/*
frontend hardcoded roadmap/issues in LogsPanel
docs/user_journey_validations_parsed*.json
sample event seed buttons
sample strategy YAMLs
Risks:

sample data looks like production truth
generated templates may use old boundaries
old YAML strategies may contain inline risk/execution behavior
sample watchlists may bypass Universe model
seed scripts may recreate deprecated entities
hardcoded UI issues/roadmaps become stale product behavior
tests may accidentally depend on sample state
Migration rule:

No sample data enters the new app by default.
Allowed:

tests/fixtures only
clearly named demo mode only
never loaded into production database
never shown as real trading-ready content
All fixtures must state:

not investment advice
not live-ready
for deterministic testing only
9. Migration Rules
Do not copy old app structure
The new repo structure must follow the new architecture, not old directories.

Reference before reuse
Every reused file must have an explicit reason and owner.

No runtime object migration without model review
Anything touching Deployment, Account, Governor, Program, Trade, Order, Simulation, or Feature computation must be redesigned first.

No old route compatibility
Do not preserve old routes for convenience.

No alias routes
One concept gets one route.

No generic service buckets
Split provider, broker, AI, data, and credentials explicitly.

No direct Alpaca calls outside adapters
Any copied Alpaca code must be moved behind adapters.

No indicators outside Feature Engine
Any copied indicator code becomes registry implementation only.

No sample data in production startup
Seed scripts must be test/demo only.

No hardcoded roadmap/issues in product UI
Development tracking belongs outside the trading product.

No old page names if concept changed
Rename before implementation.

No mutable component references in evidence
Backtests, simulations, and deployments must reference frozen component versions.

No AccountAllocation lifecycle
Delete old start/stop/promote allocation flows.

No Chart Lab / Sim Lab blending
Chart Lab stops before orders. Sim Lab owns simulated orders/fills/positions.

No AI-generated unsupported features
AI must use registry vocabulary only.

10. Recommended New Repo Structure
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

    tests/
      fixtures/
      unit/
      integration/
      parity/
      acceptance/

frontend/
  src/
    app/
      routes.tsx
      layout/

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

    components/
      charts/
      feature/
      decision-trace/
      simulation/
      operations/
      forms/
      shared/

    api/
      client.ts
      programs.ts
      features.ts
      chartLab.ts
      simLab.ts
      brokerAccounts.ts
      operations.ts
      ai.ts
11. First Migration Tasks
Create migration inventory
For every old file considered for reuse, classify:

do_not_copy
safe_reference
candidate_reuse
rewrite_from_scratch
Block direct copy of old app folders
Do not bulk-copy:

backend/app
frontend/src/pages
frontend/src/api
Define new domain models first
Start with:

ProgramVersion
Deployment
PortfolioGovernor
BrokerAccount
Order
Trade
FeatureSpec
FeaturePlan
SimulationSession
ChartLabSession
ValidationEvidence
Write naming lint rules
Reject banned names:

StrategyGovernor
AccountGovernor
AccountAllocation as runtime
DataService for AI
generic Governor
Extract only neutral UI primitives
Candidate only:

Tooltip
ConfirmationModal
ErrorBoundary
SelectMenu
TickerSearch
basic chart primitives
Port tests as rewritten acceptance tests
Start from old tests, but rewrite around new contracts.

Priority:

Feature Engine parity
Alpaca boundary
Order attribution
Control Plane cancellation
Chart Lab no-orders rule
Sim Lab no-Alpaca rule
Deployment-only runtime
Build Feature Registry v1
Do this before strategy migration.

No old strategy can migrate until its features are registry-supported.

Convert old sample strategies into test fixtures only
Do not import them as production templates.

Rewrite Alpaca integration behind adapters
Use old repo only to understand SDK behavior.

Create Operations Center from scratch
Do not combine old Account Monitor, Account Governor, Deployment Manager, and Live Monitor code.

Create Sim Lab from scratch
Use old Simulation Lab only for UX lessons.

Create Chart Lab from scratch
Use old Chart Lab only for charting lessons.

Remove hardcoded development artifacts from product UI
No roadmap/issues/journey validation inside LogsPanel equivalent.

Split Provider credentials
Create explicit models for:

BrokerProviderCredential
MarketDataProviderCredential
AIProviderCredential
Create one migration decision log
Every reused old component must list:

source file
new destination
what was reused
what was rejected
boundary review result
tests required