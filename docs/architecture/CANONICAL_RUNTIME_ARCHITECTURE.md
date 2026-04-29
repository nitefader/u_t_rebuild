# Canonical Runtime Architecture

Ultimate Trader is a Strategy publisher plus Account decision platform.

## Core Flow

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

## Strategy

A Strategy is reusable trading logic and configuration.

Strategy owns:

- signal rules
- required features
- trading windows
- entry plan
- stop plan
- target plan
- runner plan
- logical exit plan
- compatibility preferences

Strategy must not own:

- Account risk
- Account money
- broker credentials
- broker positions
- final size
- final Account execution decision

Execution behavior starts in `Strategy.config.execution` for V1. Do not create
mandatory ExecutionStyle, StopRule, TargetRule, or RiskProfile tables unless a
future product need proves they need first-class lifecycle.

## Watchlist

A Watchlist is a saved source of symbols.

Watchlists can be static or dynamic. Deployment runtime overrides may pause,
block, force include, or force exclude symbols without changing Strategy logic.

## Deployment

A Deployment is a running Strategy publisher.

Deployment owns:

- Strategy reference
- Watchlist references
- subscribed Account ids
- runtime overrides
- runtime status and health
- emitted SignalPlans
- symbol eligibility context

Deployment must not:

- own Account money
- size final orders
- submit orders
- own broker truth
- be duplicated per Account

## SignalPlan

A SignalPlan is a neutral plan emitted by a Deployment.

SignalPlans can represent:

- open
- close
- reduce partial quantity
- scale-out target
- stop exit
- trailing stop update
- breakeven move
- runner management
- logical exit

SignalPlan does not contain final Account quantity. Final quantity belongs to
the Account risk decision.

## Account

An Account owns:

- broker provider metadata
- broker mode metadata such as paper/live
- credential reference
- risk config
- broker restrictions
- buying power
- broker sync state
- open orders
- positions
- fills
- pause/kill status
- symbol restrictions
- final approval path through Governor

The same Deployment can publish one SignalPlan and many Accounts can respond
differently.

## Governor

Governor is the final internal Account protection gate before BrokerAdapter.

Governor checks:

- Account risk config
- broker sync freshness
- buying power
- broker restrictions
- Account restrictions
- symbol restrictions
- existing positions
- open orders
- daily loss
- drawdown
- max open positions
- concentration
- duplicate execution protection
- global kill
- Account pause
- Deployment pause
- SignalPlan expiration

No new broker order reaches BrokerAdapter without Governor approval.

## Truth Writers

OrderManager creates internal orders.

BrokerAdapter submits and cancels broker orders.

BrokerSync writes broker-derived truth:

- order status
- broker order mapping
- fills
- positions
- Account snapshots
- sync freshness

Only BrokerSync writes broker truth.
