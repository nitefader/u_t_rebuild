# Services Architecture — Market Data & AI Services

**Status:** Active Design
**Scope:** Broker Runtime - Paper, Operations Center, Chart Lab, Sim Lab, Backtest, Runtime Data Plane
**Owner:** Trading OS

---

## 1. Purpose

The **Services layer** defines external provider integrations that power the Trading OS.

Services are **supporting capabilities**, not trading runtime entities.

They provide:

- market data
- historical data
- streaming data
- warmup data
- AI generation
- AI reasoning
- AI analysis

Trading activity remains centered on:

> **Broker Accounts → Deployments → Runtime Execution**

Services support broker accounts and deployments. They do not own trading behavior, runtime authority, order state, broker truth, or risk decisions.

---

## 2. Core Principle

> Broker Accounts are primary.
> Services are supporting capabilities.
> The system chooses services contextually, but deterministic runtime rules remain in control.

```text
Broker Account
    ↓
Deployment
    ↓
Program Runtime
    ↓
Feature Engine ← Market Data Services
    ↓
Signal / Controls / Risk / Execution
    ↓
Portfolio Governor
    ↓
Order Manager
    ↓
Broker Adapter
    ↓
Broker Sync
```

AI Services operate outside the execution authority path:

```text
AI Services
→ strategy generation
→ program drafting
→ analysis
→ explanation
→ advisory context
```

AI does not approve trades, override the Governor, or submit orders.

---

## 3. Provider Categories

The Providers page contains provider configurations grouped by capability.

```text
Providers
|-- Market Data Services
|-- Market Data Pipelines
|-- AI Services
```

Broker Accounts are **not** Services.

Broker Accounts stand alone because they represent trading identity, capital, positions, orders, fills, and broker truth.

Services power the system. Broker Accounts are operated by the system.

---

## 4. Market Data Services

### 4.1 Definition

A **Market Data Service** is a configured provider connection capable of supplying market data.

Examples:

- Alpaca
- Yahoo Finance
- future providers such as Polygon or other data vendors

A Market Data Service may support one or more capabilities:

- historical bars
- live streaming bars
- intraday data
- daily data
- weekly data
- monthly data
- symbol lookup
- corporate-action-adjusted data
- warmup data for Feature Engine

---

## 5. Market Data Service Fields

Each Market Data Service should include:

- service id
- display name
- provider type
- credentials, if required
- capabilities
- supported timeframes
- supported lookback windows
- supported asset classes, if known
- validation status
- last validation timestamp
- default eligibility
- active/inactive status

Market Data Service records do not carry Trading OS system mode. Runtime mode is
owned by BrokerAccount and Deployment records. A MarketDataPipeline may carry a
broker-mode binding only when the selected market-data credentials are tied to a
broker paper/live environment.

Trading OS runtime modes remain separate:

```text
CHART_LAB_BATCH
CHART_LAB_LIVE_PREVIEW
SIM_LAB_HISTORICAL
SIM_LAB_LIVE_SIMULATION
BROKER_PAPER
BROKER_LIVE
```

---

## 6. Provider-Aware Configuration

The Services UI must be context-aware.

When the user selects a provider, the form changes based on that provider.

### Alpaca Market Data Service

Fields:

- service name
- API key
- API secret
- market data feed configuration, if supported
- validation button
- set as default option

Capabilities may include:

- historical bars
- live streaming bars
- intraday data
- daily data
- warmup data

### Yahoo Finance Market Data Service

Fields:

- service name
- no credentials required
- validation button
- set as default option, if allowed

Capabilities may include:

- historical daily data
- historical weekly data
- historical monthly data

Yahoo should be treated as historical-only unless explicitly expanded later.

---

## 7. Shared Data Plane

Market data is shared across broker accounts.

```text
MarketDataServiceRecord
-> MarketDataPipeline
-> Bar Builder
-> Feature Engine
-> all active consumers
```

The system must not open duplicate streams per broker account for the same symbol, provider, service, broker-mode binding, and feed.

If five broker accounts trade SPY, the platform should subscribe to SPY once through the selected streaming-capable Market Data Service, then fan out the normalized bars internally.

---

## 8. Default, Selected, and Auto Service Resolution

The system must support three selection modes wherever market data is requested.

```text
Market Data Source Mode:
  1. Default
  2. Selected
  3. Auto
```

### 8.1 Default

Use the configured default Market Data Service.

This is the simplest and safest behavior.

Default is appropriate when:

- the user does not want to think about provider choice
- runtime consistency matters
- the default service is known to support the request

### 8.2 Selected

The user explicitly chooses a Market Data Service.

Selected mode is appropriate when:

- comparing provider outputs
- debugging data differences
- forcing Yahoo for daily historical tests
- forcing Alpaca for intraday tests
- validating provider-specific behavior

### 8.3 Auto

The system selects the most appropriate service based on request context.

Auto mode is not AI magic. It is deterministic provider routing based on capabilities and request requirements.

Auto mode should consider:

- requested consumer
- runtime mode
- timeframe
- symbols
- date range
- lookback length
- need for live streaming
- need for intraday precision
- provider validation status
- provider capability metadata
- default service preference
- provider availability

Auto mode must explain its choice.

Example output:

```text
Selected Alpaca because request requires live 1m streaming bars.
```

Example output:

```text
Selected Yahoo Finance because request is historical weekly data and no intraday precision is required.
```

---

## 9. Data Routing by Context

The Market Data Service Layer should resolve provider choice based on context.

### 9.1 Broker Runtime Intraday

Use a streaming-capable provider.

Preferred:

```text
Alpaca Market Data Service
```

Reason:

- live market data required
- completed intraday bars required
- freshness matters
- runtime decisions depend on current market state

### 9.2 Broker Runtime Swing or Position Programs

Use the default service unless a lower-cost historical provider can safely satisfy non-real-time requirements.

However:

- live runtime still needs current price/freshness for active risk and execution visibility
- position or swing programs may not need high-frequency streams for every decision
- longer timeframe feature refresh can be scheduled instead of continuously streamed

Rule:

> Runtime trading still requires a reliable runtime data source. Long-horizon features may use scheduled historical refresh, but active trading safety cannot depend on stale or unknown data.

### 9.3 Backtest

Auto-selection may choose the most efficient provider.

Examples:

- daily/weekly/monthly historical test: Yahoo may be acceptable
- intraday backtest: Alpaca may be preferred
- unsupported symbol on Yahoo: fallback to Alpaca if configured
- long lookback unavailable from one provider: select provider with sufficient coverage

### 9.4 Chart Lab

Chart Lab should support Default, Selected, and Auto.

Examples:

- intraday chart inspection: Alpaca
- daily/weekly chart inspection: Yahoo may be acceptable
- feature parity inspection for runtime: use the same provider as runtime

### 9.5 Sim Lab

Sim Lab should support Default, Selected, and Auto.

Examples:

- historical replay on daily bars: Yahoo may be acceptable
- live simulation: streaming-capable provider required
- paper-readiness rehearsal: use the same provider intended for Broker Runtime

### 9.6 Feature Warmup

Warmup must be provider-aware.

The selected provider must support:

- required symbols
- required timeframes
- required lookback
- required adjusted/unadjusted policy
- required calendar/session handling

Warmup must never silently shorten lookback.

If no provider can satisfy warmup requirements, runtime start is blocked.

---

## 10. Provider Selection Policy

The provider selector should be deterministic and testable.

It should not depend on AI.

### Inputs

```text
MarketDataRequest
  consumer
  mode
  symbols
  timeframe
  start
  end
  lookback_bars
  requires_streaming
  requires_intraday
  requires_adjusted_data
  preferred_service_id optional
  selection_mode: default | selected | auto
```

### Output

```text
MarketDataResolution
  selected_service_id
  provider
  reason
  confidence
  warnings
  fallback_used
  unsupported_reasons
```

### Stop-Ship Rule

If provider resolution is ambiguous for Broker Runtime, fail closed.

Do not start runtime with unknown provider suitability.

---

## 11. Market Data Service Responsibilities

Market Data Services own:

- provider connection configuration
- credential validation
- historical fetch adapter
- streaming adapter
- provider capability metadata
- stream connection status
- symbol subscription status
- reconnect and backoff state
- market data freshness status

Market Data Services do **not** own:

- feature computation
- signal logic
- strategy controls
- risk approval
- order creation
- order submission
- broker truth
- trade ledger writes

---

## 12. Streaming Architecture

Streaming belongs to MarketDataPipeline.

For Alpaca:

```text
Alpaca MarketDataServiceRecord
-> MarketDataPipeline
-> Alpaca Market Data Adapter
-> Bar Builder
-> Feature Engine
-> Runtime Orchestrator
```

The system should maintain one stream connection per active pipeline identity where possible.

The stream manager tracks:

- connection state
- authenticated state
- subscribed symbols
- last message timestamp
- last bar timestamp by symbol
- reconnect count
- last error
- stale/fresh status

Connection states:

```text
disconnected
connecting
authenticating
connected
subscribed
stale
reconnecting
failed
```

---

## 13. Subscription and Fanout Model

Subscriptions are demand-driven.

Demand may come from:

- Broker Runtime deployments
- Sim Lab live simulations
- Chart Lab live previews
- Operations Center watch panels

The Market Data Service Layer aggregates demand by:

- service id
- broker-mode binding when present
- data feed
- symbol
- base feed type

Example:

```text
SPY 1m bars demanded by:
  - Deployment A on Broker Account 1
  - Deployment B on Broker Account 2
  - Sim Lab Session C
```

The system subscribes once, then fans out normalized completed bars internally.

When demand drops to zero, unsubscribe after a grace period.

---

## 14. Bar Builder and Feature Engine Boundary

The Market Data Service emits normalized market data.

The Bar Builder owns:

- timestamp normalization
- symbol normalization
- duplicate bar handling
- out-of-order handling
- market session attribution
- multi-timeframe aggregation
- completed-bar emission

Feature Engine receives completed bars only.

No Strategy, Signal Engine, Governor, Chart Lab, Sim Lab, or frontend page should consume raw provider messages directly.

---

## 15. Broker Account Event Streaming

Market data streaming and broker account event streaming are separate concerns.

### Market Data Streaming

Answers:

```text
What is the market doing?
```

Used for:

- bars
- features
- signals
- chart updates
- simulation inputs

Owned by:

```text
Market Data Services
```

### Broker Account Event Streaming

Answers:

```text
What happened to my orders, positions, and fills?
```

Used for:

- order status updates
- fills
- partial fills
- cancels
- rejects
- position updates
- broker account truth

Owned by:

```text
Broker Account Runtime / Broker Adapter / Broker Sync
```

Broker account event streaming is account-scoped.

Each broker account may require its own broker event stream because orders, fills, positions, and account state belong to that specific broker account.

---

## 16. Broker Event Flow

For Alpaca account events:

```text
Alpaca Broker Account Stream
→ Alpaca Broker Adapter
→ Broker Sync
→ Order Ledger
→ Trade Ledger
→ Broker Account Snapshot
→ Portfolio Governor State
→ Operations Center
```

Only Broker Sync writes broker truth.

Broker event streams must not write directly to Order Ledger or Trade Ledger without going through Broker Sync.

---

## 17. Important Separation

Do not confuse these two streams:

```text
Market Data Stream:
  price bars, quotes, trades, symbols

Broker Account Stream:
  order updates, fills, cancels, rejects, positions, account events
```

Market data can be shared across all broker accounts.

Broker account events cannot be shared across broker accounts because they are account-specific.

---

## 18. Runtime Data Source Consistency

For Broker Runtime, active deployments should use a consistent market data source.

This prevents:

- inconsistent signals
- provider-specific drift
- runtime/backtest mismatch
- different feature values across accounts

Allowed:

```text
One default streaming-capable Market Data Service feeding many deployments.
```

Not allowed in production runtime v1:

```text
Deployment A uses Alpaca live stream
Deployment B uses Yahoo historical refresh
Deployment C uses another provider
all trading the same market in the same runtime session
```

Research surfaces may allow selected provider comparison, but runtime should remain strict.

---

## 19. AI Services

### 19.1 Definition

An **AI Service** is a configured AI provider used for generation, reasoning, explanation, and analysis.

Examples:

- Groq
- Grok
- Claude
- OpenAI
- Codex-style coding agents
- future local models

### 19.2 Fields

Each AI Service should include:

- service id
- display name
- provider
- API key or auth configuration
- model name
- capability tags
- validation status
- last validation timestamp
- default eligibility
- active/inactive status

Capability tags may include:

- fast
- cheap
- reasoning
- coding
- summarization
- strategy_generation
- market_context
- explanation

---

## 20. AI Selection Modes

AI Services should eventually support the same selection model:

```text
AI Source Mode:
  1. Default
  2. Selected
  3. Auto
```

### Default

Use the configured default AI Service.

### Selected

The user explicitly chooses an AI Service.

### Auto

The system chooses based on task type and service capability metadata.

Examples:

- simple summary: fast/cheap model
- strategy generation: reasoning model
- code generation: coding-capable model
- market context: model configured for market analysis

This is a future extension. The first implementation only needs default and selected.

---

## 21. AI Authority Rules

AI may:

- generate drafts
- suggest strategies
- suggest program components
- explain decisions
- summarize logs
- analyze market context
- recommend tests

AI may not:

- approve trades
- override Portfolio Governor
- bypass Feature Engine
- submit orders
- cancel orders
- change account state
- mark live-ready by itself

AI output must pass deterministic validation before becoming executable.

---

## 22. Providers Page UX

### 22.1 Top-Level Structure

```text
Providers
|-- Market Data Services
|-- Market Data Pipelines
|-- AI Services
```

### 22.2 Market Data Services UX

User can:

- create service
- select provider
- fill provider-aware credentials/configuration
- validate service
- edit service
- deactivate service
- set default service
- inspect capabilities
- inspect last validation result

Provider dropdown examples:

```text
Alpaca
Yahoo Finance
Future Provider
```

Selection behavior:

- provider selection changes required fields
- Alpaca shows key/secret/mode fields
- Yahoo shows no credential fields
- unsupported capability is displayed clearly

### 22.3 Market Data Request UX

Where data is requested, show:

```text
Data Source:
  - Default
  - Auto
  - Select Service
```

If Auto is selected, show the selected provider and reason after resolution.

Example:

```text
Auto selected Alpaca because 1m intraday streaming is required.
```

Example:

```text
Auto selected Yahoo Finance because this is a weekly historical chart request.
```

### 22.4 AI Services UX

User can:

- create AI service
- select provider
- enter key/configuration
- validate service
- set default AI service
- inspect capability tags

Provider dropdown examples:

```text
Groq
Grok
Claude
OpenAI
Codex
Future Provider
```

---

## 23. Interaction With Broker Accounts

Broker Accounts:

- do not store market data service configuration
- do not manage AI service configuration
- do not own streaming market data
- do not decide provider routing

Broker Accounts do own:

- credentials for trading execution
- account validation
- positions
- orders
- fills
- broker restrictions
- buying power
- broker sync freshness
- deployment linkage

Broker Accounts consume the system’s resolved services indirectly through runtime orchestration.

---

## 24. What Should Be Implemented First

Do not overbuild.

### Phase 1

Implement Services registry/configuration:

- Market Data Services CRUD
- AI Services CRUD
- provider-aware forms
- validation status
- default Market Data Service
- default AI Service
- no runtime provider auto-routing yet

### Phase 2

Implement Market Data provider resolution:

- Default / Selected / Auto
- deterministic selection policy
- provider capability metadata
- historical data routing
- warmup routing

### Phase 3

Implement streaming fanout:

- Alpaca market data stream
- demand-based subscription manager
- bar builder integration
- Feature Engine updates
- Runtime Orchestrator integration
- freshness enforcement

### Phase 4

Implement broker account event streaming:

- Alpaca account event stream per broker account
- order/fill/cancel/reject updates
- Broker Sync ingestion
- Operations Center visibility

### Phase 5

Implement AI task routing:

- Default / Selected / Auto for AI
- task-to-capability routing
- advisory-only enforcement

---

## 25. Non-Goals

This design does not:

- make Broker Accounts into Services
- allow Services to own trading behavior
- allow AI to trade
- allow runtime to mix market data providers casually
- allow frontend pages to call providers directly
- require provider auto-routing in the first implementation
- require per-account market data configuration
- replace Broker Sync
- replace Feature Engine
- replace Portfolio Governor

---

## 26. Stop-Ship Conditions

Do not ship Services runtime integration if:

- no default Market Data Service is configured
- selected service is invalid
- selected service lacks required capability
- provider cannot satisfy warmup lookback
- streaming provider is stale or disconnected for Broker Runtime
- symbol is unsupported by selected provider
- Auto selection cannot explain why a provider was selected
- Broker Runtime tries to use Yahoo as a streaming source
- raw provider messages bypass Bar Builder
- feature computation happens outside Feature Engine
- broker event stream writes broker truth outside Broker Sync

---

## 27. Summary

The Services layer provides external capabilities.

Market Data Services provide historical and streaming data.

AI Services provide advisory intelligence.

Broker Accounts remain the operational center of the Trading OS.

Market data is centralized, provider-aware, and shared across accounts.

Broker account events are account-scoped and reconciled through Broker Sync.

Provider selection supports Default, Selected, and Auto modes, but Auto must remain deterministic, explainable, and bounded.

The system should implement the Services foundation first, then add provider routing, then streaming fanout, then broker account event streaming.
