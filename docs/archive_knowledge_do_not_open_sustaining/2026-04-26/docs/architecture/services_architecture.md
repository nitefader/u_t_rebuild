# Services Architecture

**Status:** Active implementation  
**Scope:** Providers page, Market Data Services, Market Data Pipelines, Chart Lab, Sim Lab, Backtest, Broker Runtime

## Core Model

Broker Accounts remain the primary operating entities. They own trading identity, capital, positions, orders, fills, broker restrictions, and broker truth. Provider services are supporting capabilities used by the platform.

Market Data Services are provider configuration records. Market Data Pipelines are the reusable stream/fetch identities selected from those services. Neither computes features, generates signals, approves risk, creates orders, submits orders, reconciles broker truth, or replaces BrokerSync. FeatureEngine remains the only computation layer for features.

## Data Intent

Every market-data request is described by a small Data Intent:

- `consumer`: `chart_lab`, `sim_lab`, `backtest`, `broker_runtime`, `operations_preview`
- `mode`: `batch`, `replay`, `live_preview`, `live_runtime`
- `symbols`, `timeframe`, optional `start_at` and `end_at`
- capability requirements: streaming, intraday, historical, realtime
- `tolerance`: `low_latency`, `normal`, `fault_tolerant`
- `purpose`: warmup, signal preview, simulation replay, backtest, runtime trading, or long-horizon analysis

Intent rules are deterministic. Broker Runtime always requires realtime streaming and intraday data when using intraday timeframes. Backtests over daily, weekly, or monthly long ranges do not require streaming. Chart Lab batch and Sim Lab historical replay do not require streaming. Sim Lab live simulation requires live market data, but still does not use BrokerAdapter.

## Capability Model

Each Market Data Service exposes machine-readable capabilities:

- provider: `alpaca`, `yahoo`, `future`
- service type: `market_data`
- mode: `paper`, `live`, `none`
- status: `draft`, `valid`, `invalid`, `disabled`
- default flag
- support flags for historical, streaming, intraday, daily, weekly, monthly, realtime, and long-range history
- credential requirement
- cost class and latency class

Provider defaults are intentionally conservative. Alpaca is credentialed, low-latency, historical, streaming, intraday, daily-capable, and realtime-capable. Yahoo is free historical data, daily/weekly/monthly-capable, non-streaming, non-realtime, and treated as delayed or normal latency.

## Service Resolver

The resolver accepts a Data Intent, configured Market Data Services, and selection mode:

- `auto`: rank valid enabled services by compatibility and efficiency
- `default`: use the configured default only if it satisfies the intent
- `explicit`: use the selected service only if it satisfies the intent

Disabled and invalid services are hard rejected. Services missing required streaming, realtime, intraday, or historical capability are hard rejected. Runtime trading prefers Alpaca or another valid streaming realtime provider. Long-range daily, weekly, and monthly historical requests prefer lower-cost historical providers when they satisfy the request.

Resolver output is UI-ready: selected service id/name/provider, decision, reason code, explanation, and rejected candidates with precise explanations.

## Providers Page CRUD

The Providers page manages configured supporting services before runtime wiring:

- Market Data Services can be created, edited, validated, disabled, and set as the single Market Data default.
- Market Data Pipelines can be created from services and selected by resolver output.
- AI Services can be created, edited, validated, disabled, and set as the single AI default.
- Secrets are represented to the UI only as masked credential presence and non-secret credential references.
- Masked placeholders are not accepted as replacement secrets.
- Invalid or disabled services cannot become defaults.
- Disabling a default service clears its default flag.

Provider validation is provider-aware but intentionally narrow. Alpaca requires API key, secret, and paper/live mode, and validation is abstracted behind a fakeable validator. Yahoo requires no credentials and validates as historical-only. Groq requires an API key and validates through the AI validator boundary. Other AI providers may be created as drafts and validated through the same boundary without adding SDK-specific behavior yet.

The persisted Market Data Services feed the Data Intent resolver. Disabled and invalid services remain rejected by resolver policy. Runtime consumers attach to Market Data Pipelines, not directly to provider SDKs.

## Streams

Market data stream and broker account event stream are separate.

Market data stream answers what the market is doing. It is shared across accounts and belongs to Market Data Pipelines selected from Market Data Services. Shared bars flow through the market data layer and then FeatureEngine.

Broker account event stream answers what happened to account orders, fills, positions, and broker state. It is account-scoped and belongs to BrokerSync. Broker account event streams are not modeled as Market Data Services or Market Data Pipelines.

## Providers Page UX

Data Source selectors display:

- Data Source Mode: Auto Recommended, Use Default, Choose Manually
- Detected Intent: consumer, timeframe, date range, streaming required, intraday required
- Selected Service: name, provider, and explanation
- Rejected services collapsed with reasons

The frontend displays resolver decisions from backend/platform state. It must not call Alpaca, Yahoo, or other providers directly.

## Non-Goals

This implementation does not implement provider fallback, add A/B provider testing, create per-account data-provider overrides, merge Broker Accounts into provider services, or change FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, or BrokerSync.

It also does not wire runtime trading to the Services registry or add live trading behavior.
