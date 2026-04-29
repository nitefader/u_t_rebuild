# Front End Prompt Agents

This is the coordinator brief for any agent or engineer working on the Ultimate
Trader frontend.

Use the active docs only. Archived docs are historical context and must not be
used as product authority.

## Mission

Build the Ultimate Trader frontend as a production operator console.

The interface must make runtime truth visible:

- what is running
- what is paused
- what is stale
- what is down
- what failed
- what needs operator attention
- why each Account, Deployment, SignalPlan, Order, Trade, or Position exists

Beauty matters, but beauty must serve operational clarity. Cards, badges,
icons, dashboards, tables, and explainers are approved only when they expose
real system state.

## Source Of Truth

Read these first:

- `docs/ULTIMATE_TRADER_MANDATE.md`
- `docs/architecture/NAMING_CONTRACT.md`
- `docs/architecture/CANONICAL_RUNTIME_ARCHITECTURE.md`
- `docs/architecture/SIGNALPLAN_POSITION_LIFECYCLE.md`
- `docs/architecture/STREAMS_AND_PROVIDERS.md`
- `docs/architecture/OPERATOR_EXPERIENCE.md`
- `docs/architecture/UI_VISUAL_DIRECTION.md`
- `docs/implementation/NEXT_BUILD_PLAN.md`

If any old prompt, page, component, mockup, comment, or archived doc conflicts
with those files, the active docs win.

## Coordinator Model

Codex is the coordinator and final approval gate.

Recommended working roles:

- UX Architecture Lead
- Frontend Product Engineer
- Visual Systems / UX Design Lead

Each role may recommend changes, but final acceptance requires coordinator
approval against the gates in this file.

## UX Architecture Lead

Owns:

- page map
- navigation
- operator workflows
- hierarchy of information
- names and labels
- prevention of duplicate product concepts

Primary responsibility:

Make the frontend match the simplified runtime architecture exactly.

The navigation should stay minimal:

- Dashboard
- Strategies
- Components
- Watchlists
- Accounts
- Deployments
- Operations
- Providers
- Settings

Detail views, drawers, tabs, or subroutes may expose:

- SignalPlans
- Positions
- Orders
- Trades
- Account Decisions
- Governor Decisions
- BrokerSync details
- explanation context

Do not add top-level navigation for every backend object unless operator
workflow proves it is necessary.

## Frontend Product Engineer

Owns:

- page implementation sequence
- shared status primitives
- page-level state requirements
- API contract readiness
- error, empty, loading, stale, and disabled states
- websocket or stream status presentation
- production workflow completeness

Primary responsibility:

Build visibility before authoring polish.

Before serious page work, define or confirm the contracts required by the UI:

- `SignalPlan`
- `SignalPlanIntent`
- `AccountDecisionTrace`
- `GovernorDecision`
- `OrderLineage`
- `PositionExplanationContext`
- `StreamStatus`
- `AccountTradeSyncStatus`

The UI must never fake confidence. If a contract is missing, stale, or partial,
the page should show that limitation explicitly.

## Visual Systems / UX Design Lead

Owns:

- cards
- badges
- icon language
- tables
- page density
- spacing
- color semantics
- explainer drawer pattern
- responsive behavior

Primary responsibility:

Carry forward the clean visual ideas from the original repo without carrying
forward old names or old architecture.

Approved visual patterns:

- compact Account cards
- compact provider cards
- dashboard KPI cards
- factual badges
- icon-led buttons
- dense but readable tables
- status strips with last updated times
- right-side explainer drawer
- inline credential and validation feedback

Avoid:

- marketing hero sections
- decorative dashboards
- vague status text
- hidden controls
- nested decorative cards
- single-color theme dominance
- old product concepts made pretty

## Canonical Runtime Flow

Every page should respect this flow:

```text
Strategy
-> Deployment
-> SignalPlan
-> Account Risk Decision
-> Governor
-> OrderManager
-> BrokerAdapter
-> BrokerSync
-> Trade / Position Truth
-> Operations Center
```

Short UI explanation form:

```text
Strategy -> Deployment -> SignalPlan -> Account Decision -> Governor -> Order -> BrokerSync -> Position
```

## Canonical Names

Use these names:

- Ultimate Trader
- Strategy
- Watchlist
- Deployment
- SignalPlan
- Account
- Governor
- Order
- Trade
- Position
- Market Data Provider
- Market Data Stream
- Account Trade Sync
- AI Provider
- BrokerAdapter
- BrokerSync
- Operations Center

The product label is `Account`.

Backend code may use `BrokerAccount` only when needed to distinguish from other
technical account concepts. In the UI and operator docs, use `Account`.

## Banned Names

Do not use these as active product concepts:

- Program
- Account Governor
- Services Center
- Paper Runtime
- Live Runtime
- Deployment per Account
- Strategy Account
- Broker Connection as a separate V1 entity
- Broker SubAccount
- Market Data Service Center

Paper and live are Account metadata, not separate product paths.

Example:

```text
Account
  broker_provider: alpaca
  broker_mode: paper | live
```

## Page Responsibilities

### Dashboard

Dashboard is the operator overview.

It should summarize:

- Live Stock Market Data Stream status
- Account Trade Sync summary
- number of Accounts
- running Deployments
- recent SignalPlans
- open Positions
- open Orders
- critical warnings
- stale/down states
- global kill state

Every card must drill into the page that owns the detail.

### Operations

Operations is the runtime command center.

It must show:

- Live Stock Market Data Stream status
- Account Trade Sync status for every Account
- running Deployments
- Account pause/resume state
- global kill state
- stale sync states
- stream errors
- recent SignalPlans
- Account decisions
- Governor decisions
- open Orders
- open Positions
- broker sync errors

Nothing mission-critical should disappear into console logs.

### Accounts

Accounts is where Broker Accounts live.

Many Accounts can exist.

Each Account may have metadata such as:

- broker provider
- broker mode
- credentials
- risk config
- restrictions
- pause/kill state

Each Account should have one Account Trade Sync while the app is running,
whether the Account is paused, resumed, subscribed, idle, paper, or live.

Account cards should show:

- Account name
- broker provider
- broker mode
- credential status
- Account Trade Sync status
- sync freshness
- equity
- cash
- buying power
- day P&L
- open Position count
- open Order count
- subscribed Deployment count
- top warnings

Account detail should expose:

- overview
- risk
- restrictions
- Positions
- Orders
- Account Trade Sync
- credentials
- explanation context

### Positions

The Account owns Positions.

Every Position must be explainable.

Position detail should answer:

- why the Position exists
- which SignalPlan opened it
- which Deployment and Strategy produced it
- when it opened
- how it was sized
- what Account risk rules applied
- what Governor decision approved it
- what stop, target, runner, or logical-exit plan applies
- which related SignalPlans have been received
- which Orders and fills changed it
- current quantity
- current exposure
- current protective Orders
- unresolved risks
- whether sync state is fresh or stale

Expose an `Explain Position` action. AI is advisory only.

### Deployments

Deployment is a running Strategy publisher.

Deployment owns:

- Strategy reference
- Watchlist references
- subscribed Account ids
- runtime overrides
- runtime status and health
- emitted SignalPlans
- symbol eligibility context

Deployment does not own broker truth, Account money, final size, or final broker
submission.

Deployment views should show:

- status
- subscribed Accounts
- emitted SignalPlans
- Account decisions per SignalPlan
- runtime overrides
- health
- recent errors

### SignalPlans

SignalPlans are neutral plans emitted by Deployments.

SignalPlan intents include:

- open
- close
- reduce
- target
- stop
- trail
- breakeven
- runner
- logical_exit

Do not assume every close SignalPlan means flatten 100 percent. A SignalPlan may
close all, reduce part, move a stop, scale out at a target, or enforce a logical
exit.

If an Account accepts an opening SignalPlan, it must keep processing related
SignalPlans from the same Deployment for that resulting Position.

### Strategies

Strategies define reusable trading logic and execution plan configuration.

Strategies own:

- signal rules
- required features
- trading windows
- entry plan
- stop plan
- target plan
- runner plan
- logical exit plan
- compatibility preferences

Strategies do not own Account risk, broker credentials, broker positions, final
quantity, or final Account execution decisions.

### Watchlists

Watchlists are saved symbol sources.

Watchlists may be static or dynamic.

Deployment runtime overrides may pause, block, force include, or force exclude
symbols without changing Strategy logic.

### Providers

Providers has exactly two buckets:

- Market Data Providers
- AI Providers

Do not put Accounts in Providers.

Do not call this Services.

Market Data Provider cards should show:

- provider name
- validation status
- default live stock data provider flag
- credentials present/missing
- live and historical capabilities
- last validation time
- last error

AI Provider cards should show:

- provider name
- model/default model
- validation status
- credentials present/missing
- advisory-only badge
- last validation time
- last error

### Settings

Settings should be small.

Settings may include:

- start Live Stock Market Data Stream on backend startup
- selected default Market Data Provider
- selected default AI Provider
- UI theme
- log/export preferences
- operator confirmation preferences

Settings must not become a runtime control dump.

Runtime controls belong in Operations, Accounts, Deployments, or Providers.

## Build Sequence

Do not start with the prettiest page. Start with shared truth surfaces.

Recommended implementation sequence:

1. Shared runtime status primitives
2. Explainer drawer contract
3. Operations Center
4. Accounts
5. Position detail and `Explain Position`
6. Deployments and SignalPlans
7. Strategies
8. Watchlists
9. Providers
10. Dashboard
11. Settings cleanup

Dashboard comes after the detail surfaces have real status data to summarize.

## Status And Badge Language

Use compact factual badges.

Approved examples:

- `Active`
- `Paused`
- `Paper`
- `Live`
- `Alpaca`
- `Default`
- `Sync Fresh`
- `Sync Stale`
- `Trade Sync Connected`
- `Account Trade Sync Down`
- `Credentials Valid`
- `Needs Credentials`
- `Advisory Only`

Color semantics:

- green: healthy, connected, profitable, approved
- red: failure, blocked, live danger, kill, destructive action
- amber: warning, stale, manual attention
- blue/cyan: neutral platform action or information
- purple: AI only
- gray: unknown, disabled, idle

Do not show safety claims without fresh backend evidence.

## Explainer Drawer

Every major page should have an explainer action.

The drawer should include:

- what this page does
- where it fits in the runtime flow
- key actions
- background logic
- what can fail here
- what the operator should check before trusting it
- copyable context for LLM review

Explainers must use canonical names only.

## Failure Visibility

The UI must show explicit evidence for success and failure.

Required states:

- loading
- empty
- connected
- disconnected
- stale
- down
- blocked
- rejected
- degraded
- unknown
- last updated
- last error

Do not hide failures behind console logs.

Do not show "all good" without last-updated evidence.

## AI Rules

AI may:

- explain Positions
- explain pages and controls
- summarize runtime state
- analyze logs
- help draft Strategy ideas
- produce copyable context

AI may not:

- approve trades
- reject trades
- override Governor
- submit Orders
- cancel Orders
- resize Positions
- mutate Account truth

AI UI must be labeled advisory only.

## Final Approval Gates

A frontend change is approved only if it passes all gates:

1. Uses canonical names.
2. Does not revive banned product concepts.
3. Makes mission-critical failures visible.
4. Shows freshness or evidence for runtime status.
5. Preserves many-Account support.
6. Treats paper/live as Account metadata.
7. Keeps Providers to Market Data Providers and AI Providers.
8. Keeps Account Trade Sync separate from Market Data Stream.
9. Keeps Account ownership of Positions clear.
10. Supports related SignalPlans for close, reduce, target, stop, trail,
    breakeven, runner, and logical exit.
11. Keeps AI advisory only.
12. Provides an operator path to explain important state.

If a proposed UI fails one gate, it is not ready.

## First Assignment For Frontend Agents

Design the first implementation slice around runtime visibility:

```text
Shared Status Primitives
-> Operations Center
-> Accounts
-> Position Explanation
```

Before writing UI code, identify the exact backend fields needed for:

- Live Stock Market Data Stream status
- Account Trade Sync status
- Account card summary
- Position explanation context
- recent SignalPlans
- Account decisions
- Governor decisions
- open Orders
- open Positions

No page is considered production-grade until it can show stale/down/error states
clearly.
