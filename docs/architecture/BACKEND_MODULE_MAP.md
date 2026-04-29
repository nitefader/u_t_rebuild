# Backend Module Map

This map ties the Ultimate Trader product model to backend modules.

## Domain

`backend/app/domain`

Owns portable contracts:

- Strategy config shapes
- Watchlist-adjacent domain contracts
- SignalPlan target contract
- TradingMode enum where backend needs exact mode values

Target change: add explicit `SignalPlan` and position-management contracts.

## Features

`backend/app/features`

Owns feature identity, planning, computation, and cache.

Feature code must not call providers directly. Feature demand flows to resolver
and streams; completed bars flow back to Feature Engine.

## Market Data

`backend/app/market_data`

Owns Market Data Providers, provider validation, resolver, stream hub, pipeline
registry, and normalized market data.

Target simplification:

- product label: Market Data Providers
- runtime label: Live Stock Market Data Stream
- one platform live stock stream while app is running

## Broker Accounts

`backend/app/broker_accounts`

Owns Account creation, provider metadata, mode metadata, credentials references,
validation, and Account lifecycle.

Product label is Account. Backend name may remain BrokerAccount.

## Runtime

`backend/app/runtime`

Owns Deployment runtime, startup orchestration, stream composition, and
Deployment health.

Target change: Deployment publishes SignalPlans to subscribed Accounts instead
of directly executing for one Account.

## Governor

`backend/app/governor`

Owns final Account protection decision before BrokerAdapter.

Governor is Account-scoped. It must support opening and related close/reduce
SignalPlans.

## Orders

`backend/app/orders`

Owns internal Account-specific orders and idempotency.

Target change: orders link to SignalPlan lineage and position-management intent.

## Brokers

`backend/app/brokers`

Owns BrokerAdapter and broker stream adapters.

BrokerAdapter submits/cancels. BrokerSync reconciles truth. No UI, AI, Chart
Lab, Sim Lab, or Backtest bypasses this boundary.

## Operations

`backend/app/operations`

Owns operator-facing runtime state:

- Accounts
- Deployments
- SignalPlans
- orders
- trades
- positions
- Live Stock Market Data Stream status
- Account Trade Sync status
- stale/down/error states

## Persistence

`backend/app/persistence`

Owns durable runtime storage.

Target change: persist SignalPlan lineage, Account decision trace, and position
explanation context where needed.

## AI

`backend/app/ai`

Owns advisory AI provider runtime.

AI can explain. AI cannot trade.
