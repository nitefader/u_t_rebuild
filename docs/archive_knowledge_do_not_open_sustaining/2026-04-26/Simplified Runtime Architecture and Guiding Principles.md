# Trading OS - Simplified Runtime Architecture and Guiding Principles

**Version:** 1.2
**Date:** April 25, 2026
**Purpose:** This document is the single source of truth for the simplified Trading OS architecture and product model.

---
# Operator's vision ***
There is no seprate path for Alpaca Paper vs Alpaca Live, etc - The main things seperating them are the Endpoints for the API or Streaming, but there is no seperate create paper button its creat account button and then I can choose paper or live for the backend to derive the right context driven url or connection or streaming etc.
No Patching. No Forking to Get Work Done. Fix issues and then Next Step.
Everything is passed through the lens of is this Production Grade?
All agents must think like owners of the system!

## 1. Core Philosophy

The Trading OS should be powerful, but easy to reason about.

The system should avoid a maze of entities. Most complexity should live in resolvers and services, not in dozens of saved tables.

The platform model is:

- A **Strategy** defines when and how it wants to trade.
- A **Watchlist** defines what symbols may be available.
- A **Deployment** is a running publisher configuration for a Strategy.
- A **SignalPlan** is the neutral trade idea emitted by a Deployment.
- An **Account** independently decides whether to accept, size, reject, or ignore each SignalPlan.
- The **Governor** protects the Account before any order reaches the broker.
- The **OrderManager** creates internal orders.
- The **BrokerAdapter** submits approved orders to the broker.
- **BrokerSync** reconciles broker truth back into Orders and Trades.

There is no user-facing **Program** entity.

The user builds Strategies, deploys them, subscribes Accounts, and monitors runtime behavior.

---

## 2. Final Architecture Summary

A Strategy defines when and how it wants to trade.

Watchlists define what symbols are available.

An Account defines how much risk is allowed and where broker execution happens.

A Deployment is a running publisher configuration for a Strategy.

Accounts subscribe to Deployments.

A Deployment emits SignalPlans.

Each Account evaluates each SignalPlan against its own risk rules, broker state, account restrictions, symbol restrictions, exposure, and Governor rules.

Approved Accounts create account-specific Orders.

Trades are account-specific.

The Strategy does not know money.

The Deployment does not force Accounts to trade.

The Account/Governor protects the money.

---

## 3. Core Flow

Simplified flow:

```text
Strategy
→ Deployment
→ SignalPlan
→ Account Risk Manager / Governor
→ Order
→ Broker
→ BrokerSync
→ Trade Ledger

Detailed flow:

User creates and validates a Strategy.
User creates a Deployment from the Strategy plus selected Watchlists.
The Deployment runs, evaluates the Strategy, and emits SignalPlans.
Subscribed Accounts receive each SignalPlan.
Each Account’s Risk Manager and Governor evaluates the SignalPlan independently.
If approved, the Account creates an Order.
BrokerAdapter submits the Order to the broker.
BrokerSync updates Orders, Trades, account state, positions, and fills.
Operations Center monitors the entire runtime.
4. Core Saved Entities for V1

Only these major entities are persisted in V1:

Strategy
Watchlist
Account
Deployment
SignalPlan
Order
Trade

Everything else should start as JSON config, resolver logic, runtime events, or lightweight audit records.

Avoid over-modeling these as separate first-class entities in V1:

Program
SignalVersion
TradingControlsVersion
ExecutionStyleVersion
UniverseDefinition
UniverseSubscription
ResolvedUniverseSnapshot
AccountRiskProfile table
RiskCard table
ExecutionLeg
StopRule
TargetRule
BreakevenRule
TrailingRule

These can be promoted later only if the product proves they need first-class lifecycle, UI, ownership, and audit behavior.

5. Non-Negotiable Rules
Rule 1: No Program entity

There is no Program entity in the user-facing model or core simplified model.

The user builds Strategies.

The user deploys Strategies.

Accounts subscribe to Deployments.

Rule 2: Strategy is dumb

Strategy must not own:

Account risk
Money
Broker credentials
Buying power
Account restrictions
Portfolio exposure
Runtime broker state
Final position sizing
Actual final account execution decision

Strategy only knows:

Entry logic
Exit logic
Required features
Trading windows
Execution plan
Optional compatibility preferences
Rule 3: Deployment publishes, Accounts decide

Deployment emits SignalPlans.

Deployment does not make account-specific risk decisions.

Deployment does not size final orders.

Deployment does not submit orders directly.

Each Account independently accepts, rejects, sizes, or ignores each SignalPlan.

Rule 4: Governor is the final gate

No new order reaches BrokerAdapter without Governor approval.

Rule 5: Orders and Trades are account-specific

Every Order belongs to an Account.

Every Trade belongs to an Account.

Every Order and Trade must link back to the SignalPlan and Deployment that caused it.

Rule 6: Resolvers do the work

Resolvers and services interpret configs at runtime.

Saved entities should stay simple.

Important resolvers:

UniverseResolver
FeatureEngine
SignalResolver
WindowResolver
ExecutionResolver
RiskResolver
Governor
BrokerCapabilityResolver
6. Strategy

A Strategy is dumb, portable, reusable trading logic.

A Strategy does not know what Account it will run on.

A Strategy does not know how much money the Account has.

A Strategy does not know final position size.

A Strategy does not own actual live symbol membership.

A Strategy only defines when and how it wants to trade.

Strategy owns
Signal conditions
Entry rules
Exit rules
Required features
Trading windows
Execution plan
Stop and target plan
Optional compatibility preferences
Strategy must not own
Risk profile
Account risk appetite
Broker account
Capital allocation
Buying power
Portfolio exposure
Broker restrictions
Runtime state
Final tradable universe
Account-specific order quantity
7. Strategy Config Shape

Strategy can be stored as one entity with a config JSON.

Example:

{
  "id": "strat_orb_runner_001",
  "name": "ORB Breakout with Runner",
  "version": "v1.2",
  "status": "frozen",
  "signal": {
    "entry_condition": "close > opening_range_high AND volume > volume_sma_20",
    "exit_condition": "close < ema_20",
    "required_features": [
      "5m.close[0]",
      "5m.opening_range_high:session=regular,window_minutes=15",
      "5m.volume_sma:length=20[0]",
      "5m.ema:length=20[0]",
      "5m.atr:length=14[0]"
    ]
  },
  "windows": {
    "entry_windows": [
      { "start": "09:45", "end": "11:30" }
    ],
    "no_new_entries_after": "15:30",
    "force_flatten_at": "15:55"
  },
  "execution": {
    "entry_order_type": "market",
    "initial_stop": {
      "type": "atr",
      "atr_length": 14,
      "multiple": 1.0
    },
    "targets": [
      { "name": "T1", "qty_pct": 25, "r_multiple": 1.0 },
      { "name": "T2", "qty_pct": 25, "r_multiple": 2.0 },
      { "name": "T3", "qty_pct": 25, "r_multiple": 3.0 },
      {
        "name": "Runner",
        "qty_pct": 25,
        "trail": { "type": "atr", "multiple": 1.5 }
      }
    ],
    "breakeven": {
      "trigger": "after_T1",
      "offset_r": 0.0
    }
  },
  "compatibility": {
    "asset_classes": ["equity", "etf"],
    "preferred_min_avg_volume": 1000000,
    "supports_leveraged_etfs": true,
    "supports_shorts": false
  }
}
8. Strategy Reuse Across Multiple Deployments

One Strategy can be reused by multiple Deployments.

A Strategy is reusable trading logic.

A Deployment is a running publisher configuration for that Strategy.

This means the same Strategy can be deployed more than once with different Watchlists, runtime overrides, account subscribers, or operational purpose.

Example

Strategy:

ORB Breakout with Runner

Deployment A:

Name: ORB Runner - Leveraged ETFs
Strategy: ORB Breakout with Runner
Watchlists: Leveraged ETFs, High Volume Momentum
Subscribed Accounts: Aggressive Paper, Aggressive Live

Deployment B:

Name: ORB Runner - Conservative ETFs
Strategy: ORB Breakout with Runner
Watchlists: SPY/QQQ/DIA ETFs, Blue Chip Momentum
Subscribed Accounts: Conservative Paper, Conservative Live

Deployment C:

Name: ORB Runner - End-of-Day Movers
Strategy: ORB Breakout with Runner
Watchlists: End-of-Day Movers, 3 Percent Drop Scanner
Subscribed Accounts: Paper Research Account

Rules:

Strategy is reusable.
Deployment is the publisher configuration.
Accounts subscribe to Deployments.
Orders and Trades remain account-specific.

This avoids copying Strategy logic while still allowing different watchlist configurations and account subscriber sets.

9. Deployment

A Deployment is a running publisher configuration for a Strategy.

Deployment is not one Strategy on one Account.

Deployment is not copied per Account.

Deployment is not the final account-level execution authority.

Deployment runs the Strategy, watches eligible symbols, evaluates signals, and publishes SignalPlans.

Deployment owns
strategy_id
watchlist_ids
subscribed_account_ids
status
runtime_overrides_json
runtime health
emitted SignalPlans
symbol eligibility context
operational state
Deployment does not own
Account money
Final position sizing
Account risk
Broker truth
Account-specific order state
Account-specific fills
Account-specific trade state
10. Deployment Publisher Model

The Deployment watches symbols, evaluates the Strategy, and emits SignalPlans.

Accounts subscribe to the Deployment.

Each Account independently decides whether to accept, size, reject, or ignore each SignalPlan.

Example

Deployment:

ORB Breakout With Runner

Subscribed Accounts:

Alpaca Paper Account A
Alpaca Paper Account B
Alpaca Live Account C
Conservative Retirement Account
Aggressive Test Account

When TQQQ fires:

SignalPlan:

Buy TQQQ
Entry: market
Stop: 1 ATR
Targets: T1, T2, T3, Runner

Account A:

Accepts, buys 5 shares

Account B:

Accepts, buys 20 shares

Live Account C:

Rejects, TQQQ not allowed

Retirement Account:

Rejects, leveraged ETFs blocked

Aggressive Account:

Accepts, buys 50 shares

Same Deployment.

Different account outcomes.

11. Deployment Example
{
  "id": "dep_orb_001",
  "strategy_id": "strat_orb_runner_001",
  "name": "ORB Runner - Main",
  "watchlist_ids": ["wl_liquid_etfs", "wl_momentum"],
  "subscribed_account_ids": ["acc_paper_01", "acc_live_01", "acc_conservative_01"],
  "status": "running",
  "runtime_overrides": {
    "blocked_symbols": ["TQQQ"],
    "paused_symbols": ["SOXL"],
    "force_include_symbols": []
  }
}
12. SignalPlan

A SignalPlan is the neutral trade idea emitted by a Deployment.

SignalPlan represents what the Strategy wants to do.

SignalPlan does not represent what any specific Account actually did.

SignalPlan should not contain final account-specific quantity.

Final quantity belongs to the Account risk layer.

SignalPlan owns
deployment_id
strategy_id
symbol
side
reason
feature evidence
signal timestamp
entry plan
stop plan
target plan
runner plan
valid_until
universe context
execution instructions before account sizing
SignalPlan must not own
Final account quantity
Account buying power
Account-specific approval
Account-specific rejection
Broker order id
Final fill state
13. SignalPlan Example
{
  "signal_plan_id": "sig_20260425_103512",
  "deployment_id": "dep_orb_001",
  "strategy_id": "strat_orb_runner_001",
  "symbol": "SPY",
  "side": "buy",
  "reason": "Opening range breakout confirmed on high volume",
  "entry": {
    "order_type": "market"
  },
  "stop": {
    "type": "atr",
    "multiple": 1.0
  },
  "targets": [
    { "name": "T1", "qty_pct": 25, "r_multiple": 1.0 },
    { "name": "T2", "qty_pct": 25, "r_multiple": 2.0 },
    { "name": "T3", "qty_pct": 25, "r_multiple": 3.0 },
    {
      "name": "Runner",
      "qty_pct": 25,
      "trail": { "type": "atr", "multiple": 1.5 }
    }
  ],
  "universe_context": {
    "source_watchlists": ["wl_liquid_etfs", "wl_momentum"],
    "inclusion_reason": "SPY included by liquid ETF watchlist and momentum scan",
    "resolved_at": "2026-04-25T10:35:00-04:00"
  },
  "valid_until": "2026-04-25T11:30:00-04:00"
}
14. Account

Account owns risk, broker connection, broker state, and final decision making.

Risk belongs to Account, not Strategy.

Paper vs Live belongs to Account, not Deployment.

A paper Account can subscribe to a Deployment and execute in paper.

A live Account can subscribe to the same Deployment and execute live.

The Deployment itself does not need to become paper or live.

Account owns
Broker connection
Broker mode: paper or live
Credentials reference
Risk config
Broker restrictions
Buying power
Broker sync state
Open orders
Open positions
Fills
Account-level pause or kill state
Symbol restrictions
Final execution approval through Governor
Account does not own
Strategy logic
Signal computation
Feature computation
Watchlist refresh logic
Deployment publishing logic
15. Account Example
{
  "id": "acc_paper_01",
  "name": "Alpaca Paper - Aggressive",
  "broker": "alpaca",
  "mode": "paper",
  "risk_config": {
    "risk_appetite": 8,
    "max_risk_per_trade_pct": 1.0,
    "max_daily_loss_pct": 3.0,
    "max_drawdown_pct": 8.0,
    "max_open_positions": 6,
    "max_symbol_concentration_pct": 30,
    "allow_leveraged_etfs": true,
    "allow_shorts": true,
    "blocked_symbols": []
  }
}
16. Risk Appetite

Risk appetite can use a 0 to 10 score:

0 = capital preservation, very conservative
5 = balanced
10 = speculative or aggressive

The score should map to concrete enforceable rules.

The score itself should not be the rule.

Example risk rules:

Max risk per trade
Max daily loss
Max drawdown
Max open positions
Max symbol concentration
Allowed asset classes
Blocked symbols
Shorting allowed or not
Leveraged ETFs allowed or not
Manual approval required or not

The Strategy says:

I want in.

The Account/Governor says:

Are you allowed to enter, given account risk, broker state, symbol restrictions, exposure, stale sync, and pause state?
17. Governor

The Governor remains the final internal authority before broker execution.

No new order should reach BrokerAdapter without Governor approval.

The Governor protects the Account.

The Deployment does not force Accounts to trade.

Governor evaluates
Account risk config
Buying power
Broker restrictions
Symbol restrictions
Existing positions
Existing open orders
Daily loss
Drawdown
Max open positions
Symbol concentration
Account pause state
Global kill state
Broker sync freshness
SignalPlan expiration
Duplicate execution protection
Governor flow
SignalPlan emitted
→ Account receives SignalPlan
→ RiskResolver sizes or rejects
→ Governor approves or rejects
→ OrderManager creates internal order
→ BrokerAdapter submits to broker
18. Watchlists and Universe

Universe should not be part of Strategy.

Strategy should not own actual symbols.

Strategy may have loose compatibility preferences, such as:

Works best on liquid ETFs
Requires 5m bars
Avoids illiquid names
Supports equities only

Actual tradable symbols come from the Deployment’s selected Watchlists and the UniverseResolver.

Use Watchlists as the saved user-facing object.

Watchlist types

Static Watchlist:

Handpicked symbols like TQQQ, SPY, QQQ

Dynamic Watchlist:

Daily movers
3 percent drops
End-of-day momentum
High-volume names
Gap scanners
Sector movers

Watchlists can refresh on a schedule:

Every 5 minutes
Every 10 minutes
Hourly
Daily
End of day

The Deployment asks:

What symbols are eligible right now?

The UniverseResolver answers using selected Watchlists, filters, runtime overrides, and account-independent eligibility rules.

19. Runtime Symbol Overrides

If TQQQ is in a dynamic Watchlist but the operator does not want it traded, the user should not edit the Strategy.

The user should apply a runtime override.

Possible symbol override actions:

Pause symbol
Block symbol
Close-only symbol
Force include
Force exclude
Flatten now

These can live inside Deployment.runtime_overrides_json or similar runtime config.

Rule:

Manual negative overrides beat dynamic watchlist inclusion.

If TQQQ is blocked or paused, no dynamic scanner should sneak it back into trading 10 minutes later.

20. Freezing

Freezing still matters, but what gets frozen is limited.

Frozen in Strategy
Signal logic
Feature requirements
Trading windows
Execution plan
Strategy version
Can change at runtime
Watchlist membership
Resolved symbols
Symbol pauses or blocks
Account risk profile
Account subscriptions
Deployment status
Runtime overrides

This avoids forcing the user to pause, refreeze, and redeploy every time symbols or accounts change.

21. Paper vs Live

Paper vs Live belongs to the Account, not the Deployment.

A Deployment publishes SignalPlans.

A paper Account can subscribe and execute in paper.

A live Account can subscribe and execute live.

The Deployment itself does not need a paper/live mode.

Broker execution mode is account-specific.

22. Execution Plan

Execution behavior should be config-driven, not over-modeled.

Do not create too many execution entities in V1.

Avoid creating separate tables for:

ExecutionStyle
ExecutionLeg
StopRule
TargetRule
BreakevenRule
TrailingRule

Instead, keep execution behavior in:

Strategy.config.execution

Then let ExecutionResolver convert that config into SignalPlans and order intents.

23. Four Targets / Runner Handling

Do not create four target entities.

Represent targets inside Strategy.config.execution.

ExecutionResolver reads the config and creates the appropriate SignalPlan and order plan.

Example:

T1 sells 25 percent at 1R
T2 sells 25 percent at 2R
T3 sells 25 percent at 3R
Runner trails remaining 25 percent by ATR
24. Four Stops Handling

"Four stops" can mean two different things.

24.1 Multiple Stop Candidates

Example candidates:

ATR stop
Previous candle low
Opening range low
Fixed percent stop

StopResolver chooses based on a rule:

Tightest
Widest
Priority order
Highest confidence

Example:

{
  "initial_stop": {
    "selection": "tightest",
    "candidates": [
      { "type": "atr", "multiple": 1.0 },
      { "type": "feature", "value": "5m.low[1]" },
      { "type": "feature", "value": "5m.opening_range_low:session=regular,window_minutes=15" },
      { "type": "percent", "value": 1.0 }
    ]
  }
}
24.2 Stop Progression

Example progression:

At entry: 1 ATR stop
After T1: move to breakeven
After T2: trail by 1.5 ATR
After T3: trail by 1 ATR

Example:

{
  "stop_progression": [
    {
      "when": "entry_filled",
      "stop": { "type": "atr", "multiple": 1.0 }
    },
    {
      "when": "T1_filled",
      "stop": { "type": "breakeven", "offset_r": 0.0 }
    },
    {
      "when": "T2_filled",
      "stop": { "type": "atr_trail", "multiple": 1.5 }
    },
    {
      "when": "T3_filled",
      "stop": { "type": "atr_trail", "multiple": 1.0 }
    }
  ]
}

Both can be represented in Strategy.config.execution.

25. Account Execution Decision

SignalPlan is neutral.

Each Account needs its own decision trace.

This can start as a lightweight event or log record, not necessarily a major business entity.

Example:

{
  "signal_plan_id": "sig_20260425_103512",
  "account_id": "acc_paper_01",
  "decision": "accepted",
  "qty": 20,
  "reason": "Risk approved",
  "created_order_ids": ["ord_123"]
}

Rejected example:

{
  "signal_plan_id": "sig_20260425_103512",
  "account_id": "acc_conservative_01",
  "decision": "rejected",
  "reason": "Leveraged ETFs are blocked for this account"
}

This lets the system answer:

Which accounts accepted the signal?
Which accounts rejected it?
Why did each account make its decision?
What quantity did each approved account choose?
Which orders were created from the SignalPlan?
26. Idempotency

A SignalPlan must not accidentally create duplicate account orders.

For each Account, a SignalPlan can produce at most one active accepted execution decision unless explicitly retried with a new idempotency key.

Suggested idempotency key:

signal_plan_id + account_id + intent

Example:

sig_20260425_103512:acc_paper_01:open

If the system retries processing, it must detect that the Account already processed the SignalPlan.

27. SignalPlan Expiration

SignalPlans must have validity windows.

Expired SignalPlans cannot create new opening orders.

Protective exits may still be evaluated if tied to an existing Account position.

Rule:

No new opening order can be created from an expired SignalPlan.

SignalPlan should include:

{
  "created_at": "2026-04-25T10:35:12-04:00",
  "valid_until": "2026-04-25T11:30:00-04:00"
}
28. Traceability Rules

Traceability should be simple:

One Strategy can have many Deployments.
One Deployment emits many SignalPlans.
Many Accounts can subscribe to one Deployment.
Each Account can accept or reject each SignalPlan.
Orders are account-specific.
Trades are account-specific.
Every Order links back to a SignalPlan.
Every Trade links back to a SignalPlan.
Every SignalPlan links back to a Deployment.
Every Deployment links back to a Strategy.

This avoids duplicating Deployments per Account while still preserving full auditability.

29. Simplified Runtime Flow
Deployment starts
→ UniverseResolver gets eligible symbols from selected Watchlists
→ FeatureEngine computes required features
→ SignalResolver checks Strategy signal rules
→ WindowResolver checks Strategy windows
→ ExecutionResolver builds SignalPlans
→ Deployment publishes SignalPlans
→ Subscribed Accounts evaluate each SignalPlan
→ RiskResolver / Governor checks Account risk
→ Approved Accounts create account-specific Orders
→ BrokerAdapter submits to each Account’s broker
→ BrokerSync updates Order and Trade ledgers
→ Operations Center monitors everything
30. Product Navigation

Simplified sidebar idea:

Strategies
Watchlists
Accounts
Deployments
Chart Lab
Sim Lab
Backtests
Risk Cards
Operations Center
Orders & Trades

Risk Cards can be hidden under Accounts at first if we want an even simpler UI.

31. Simplified V1 Entity Shape
Strategy
id
name
version
status
config_json
created_at
updated_at
Watchlist
id
name
type
config_json
latest_symbols_json
created_at
updated_at
Account
id
name
broker
mode
credentials_ref
risk_config_json
status
created_at
updated_at
Deployment
id
name
strategy_id
watchlist_ids
subscribed_account_ids
status
runtime_overrides_json
created_at
started_at
paused_at
stopped_at
SignalPlan
id
deployment_id
strategy_id
symbol
side
order_plan_json
universe_context_json
status
created_at
valid_until
Order
id
signal_plan_id
deployment_id
account_id
symbol
intent
side
qty
status
client_order_id
broker_order_id
created_at
updated_at
Trade
id
signal_plan_id
deployment_id
account_id
symbol
side
qty
entry_price
exit_price
pnl
status
created_at
updated_at
32. Product Mental Model

The user should think:

I build a Strategy.
I deploy the Strategy with Watchlists.
The Deployment publishes trade ideas.
Accounts subscribe to the Deployment.
Each Account decides whether to trade.
Operations Center shows what happened.

The user should not think:

I need to create Programs.
I need to duplicate Deployments for every Account.
I need to refreeze a Strategy every time a Watchlist changes.
I need to edit Strategy logic to block one symbol.
33. Final Locked Direction

A Deployment is a running Strategy publisher.

A Strategy can be reused across multiple Deployments.

A Deployment is not copied per Account.

A Deployment emits SignalPlans.

Accounts subscribe to Deployments.

Each Account independently accepts, rejects, sizes, and executes SignalPlans through its own risk profile and broker connection.

Orders and Trades are account-specific.

Strategy defines when and how it wants to trade.

Watchlists define what symbols are available.

Account defines how much risk is allowed.

Resolvers calculate runtime decisions.

Governor protects the Account.

OrderManager and BrokerAdapter handle execution.


## Streaming & Runtime Connections

- There is **one shared Market Data Pipeline** for stocks. It starts automatically and stays running for the lifetime of the system.
- There is **one Broker Trade Update Stream per Account**. These streams start automatically for every configured Account when the system boots, regardless of whether the Account has any Deployments subscribed.
- Accounts are independent entities. They must support both automated SignalPlans and manual trading entered by the user.
- The system must continue running all streams and Deployments until the user explicitly shuts it down.
- Operations Center must provide clear visibility into:
  - Market Data Pipeline status
  - Status of every Account’s Broker Trade Update Stream
  - Running Deployments
  - Any connection issues or stale states

34. Approval Statement

This document is the living truth for the simplified Trading OS architecture.

Any future change that violates these principles requires explicit review.

Approved direction date: April 25, 2026

---

## 35. Operator Addendum - SignalPlan Lifecycle and Account-Owned Positions

Approved by Operator: April 26, 2026

### 35.1 Account Must Track Related Close Signals

If an Account accepts an opening SignalPlan, that Account must continue listening
to the same Deployment signal stream for related close, reduce, scale-out, stop,
target, and logical-exit SignalPlans.

Reason:

A Strategy may open a position with an entry, stop, and targets, but also define
logical exit rules.

Example:

```text
Open long:
  entry with stop, target, and runner plan

Logical exit:
  if 5m.RSI_21 crosses_above 15m.RSI_21, exit long positions
```

The Account and Governor that accepted the original open SignalPlan must
prioritize and enforce related close/reduce SignalPlans for positions created
from that original signal lineage.

Close SignalPlans may represent:

- full close
- partial close, such as close 50 percent
- target fill / scale-out
- stop exit
- trailing-stop update
- breakeven move
- runner management
- logical exit rule

The model must stay future-proof for partial exits and position-management
events. Do not assume every close SignalPlan means flatten 100 percent.

### 35.2 Account Owns Position Truth and Explanation

The Account owns positions.

For every account-owned position, the system must be able to explain:

- why the position exists
- which SignalPlan opened it
- which Deployment and Strategy produced the signal
- when it opened
- how it was sized
- what risk rules and Governor decision approved it
- what stop, target, runner, or logical-exit plan applies
- which related close/reduce SignalPlans have been received
- which orders, fills, and trades changed the position
- current status, exposure, remaining quantity, and risk

Position explanation is not optional operator decoration. It is part of the
account-owned truth model.

### 35.3 AI Position Explanation

The UI should expose an "Explain this position" AI action.

The AI may use the position explanation context to provide a detailed assessment,
including signal lineage, account decision trace, Governor reasoning, open risk,
protective orders, related close/reduce signals, fills, and current state.

AI explanation remains advisory only.

AI must not:

- approve a trade
- reject a trade
- resize a position
- submit an order
- cancel an order
- override the Governor
- modify broker/account truth




#addendum
if a account takes a Signal Plan it must now look for any signal closeures from that pipeline
## reasoning a Strategy might open a signal with Stop Entry Target, and also have a logical exit plan, example is 5m.RSI_21 crosses_above 15m.RSI_21 then exit long positions. The Account and Portfilio governor who receive the initial open signal should prioritxe this and enforce the close signal for the positions related to this signal -- Note: it might also be a close 50% or etc so keep this in mind and future proof it

# account position
The account owns the position and logic and must be able to explain why , when, how, and other facts about each positions, There should also be an AI button for explain this position the AI will have the proper context to give a detailed assessment.
Approved by Operator  date: April 26, 2026
