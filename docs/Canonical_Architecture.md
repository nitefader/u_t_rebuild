# Canonical Architecture

**Timestamp (ET):** 2026-04-22 11:02:07 AM ET

This document defines the canonical domain model for Ultimate Trading Software 2026.
Its purpose is to remove ambiguity between design-time components, runtime instances,
portfolio-level controls, and broker truth.

It should be used as the reference point for:
- model naming
- route naming
- UI labels
- service boundaries
- event naming
- control-plane behavior

If current code or docs conflict with this document, treat this document as the target
architecture for future convergence.

---

## Core Mental Model

The system has two distinct layers:

1. Design-time composition
   What the system is configured to do.

2. Runtime execution
   What is currently running, what is currently allowed, and what the broker says is true.

The clean runtime decision flow is:

`Strategy -> Strategy Controls -> Risk Profile -> Execution Style -> Portfolio Governor -> Broker Account`

---

## Canonical Components

### 1. Strategy

**Purpose:** What to trade and why.

**Owns:**
- entry logic
- exit logic
- stop candidate
- target candidate
- multi-timeframe signal confirmation
- composite signal logic

**Must not own:**
- position sizing
- session windows
- cooldowns
- order type
- broker calls
- portfolio-level checks

**Examples:**
- breakout entry
- mean reversion exit
- ATR-derived stop candidate
- daily trend + 5m trigger confirmation

---

### 2. Strategy Controls

**Purpose:** When a strategy is allowed to act.

**Owns:**
- timeframe
- session windows
- cooldowns
- max trades per session
- regime filter
- earnings blackout / event blackout
- open/close window constraints

**Must not own:**
- signal generation
- sizing
- order mechanics
- broker truth

**Examples:**
- trade only between 09:45 and 15:30 ET
- do not open new trades during earnings blackout
- max 3 entries per session
- block entries in restricted regimes

---

### 3. Risk Profile

**Purpose:** How much risk is allowed.

**Owns:**
- position sizing
- max daily loss
- max positions
- drawdown limits
- exposure limits at the position level
- fallback stop policy when risk protection is required

**Must not own:**
- signal generation
- session logic
- order expression details
- broker execution mechanics

**Examples:**
- 0.5% risk per trade
- max 5 concurrent positions
- stop new opens after 2% daily loss
- drawdown lockout at 10%

---

### 4. Execution Style

**Purpose:** How orders are expressed.

**Owns:**
- market / limit / stop-limit order choice
- bracket order behavior
- trailing stop behavior
- time in force
- cancel / replace rules
- entry offset rules
- scale-out order mechanics

**Must not own:**
- signal truth
- regime/session permission
- risk budgets
- portfolio authority

**Examples:**
- market entry with native bracket
- stop-limit breakout entry
- trailing-stop exit
- cancel unfilled order after 3 bars

---

### 5. Watchlist

**Purpose:** Where the strategy can hunt.

**Owns:**
- symbols
- watchlist combination rules
- resolved symbol sets

**Must not own:**
- signal logic
- sizing logic
- execution logic
- portfolio authority

**Examples:**
- momentum watchlist
- earnings watchlist
- sector rotation watchlist
- union/intersection of watchlists

---

### 6. Program

**Purpose:** The deployable package.

**Owns references to:**
- Strategy
- Strategy Controls
- Risk Profile
- Execution Style
- Watchlist(s)

**Must not own:**
- inline trading logic that belongs in components
- broker truth
- portfolio-level authority
- runtime-only state

**Examples:**
- “Momentum Intraday Program”
- “Swing Earnings Fade Program”

Think of Program as the package that says:
"Run this strategy, under these controls, with this risk profile, using this execution style, on these symbols."

---

### 7. Portfolio Governor

**Purpose:** Final internal authority before broker execution.

**Owns:**
- symbol conflict resolution across programs
- portfolio exposure checks
- concentration limits
- account-wide or portfolio-wide pause/kill behavior
- final approval / rejection for new position-opening orders

**Must not own:**
- signal generation
- low-level broker storage
- technical indicator computation
- component definitions

**Examples:**
- reject opposing positions in the same symbol
- reject new opens after portfolio loss threshold
- block new entries while paused
- allow protective exits while kill/pause is active

This is the last internal gate before an order reaches the broker.

---

### 8. Broker Account

**Purpose:** Real Alpaca endpoint and broker truth.

**Owns:**
- balances
- buying power
- broker positions
- fills
- broker restrictions
- PDT/broker flags
- open orders from broker perspective

**Must not own:**
- internal strategy decisions
- program-level signal logic
- portfolio control rules

**Examples:**
- Alpaca paper account
- Alpaca live account

Broker Account is the external source of truth, not the place where internal policy is decided.

---

## Runtime-Only Concept

### Deployment

**Purpose:** A running instance of a Program on a Broker Account.

**Owns:**
- runtime lifecycle state
- started/stopped/paused status
- current runtime configuration linkage
- timestamps
- runtime health metadata

**Must not own:**
- architecture authority
- component definitions
- portfolio policy

**Examples:**
- Program A running on Broker Account X in paper mode
- Program B running on Broker Account Y in live mode

Program is design-time.
Deployment is runtime.

---

## Responsibility Matrix

| Component | Owns | Must Not Own |
|---|---|---|
| Strategy | Entry, exit, stop candidate, target candidate, multi-timeframe confirmation | Sizing, session rules, broker calls |
| Strategy Controls | Timeframe, sessions, cooldowns, max trades/session, regime/event gating | Signal generation, sizing, order mechanics |
| Risk Profile | Position sizing, max loss, max positions, drawdown limits | Signal logic, session rules, order expression |
| Execution Style | Order form, bracket/trailing/TIF, cancel rules | Signal truth, risk budget, portfolio approval |
| Watchlist | Symbols, combination rules | Signal, risk, execution, broker policy |
| Program | References to all design-time components | Runtime state, broker state, portfolio authority |
| Portfolio Governor | Conflict resolution, exposure, concentration, pause/kill, final approval | Signal generation, broker truth storage |
| Broker Account | Balances, buying power, fills, broker positions, restrictions | Internal architecture decisions |
| Deployment | Runtime instance/lifecycle | Design-time component responsibility |

---

## Naming Standard

| Ambiguous / Old | Canonical Name | Meaning |
|---|---|---|
| `Strategy` | `Strategy` | Signal logic only |
| `Strategy Governor` / bare `Governor` | `Strategy Controls` | When strategy is allowed to act |
| `Risk Profile` | `Risk Profile` | How much risk is allowed |
| `Execution Style` | `Execution Style` | How orders are expressed |
| `Watchlist` | `Watchlist` | Where the strategy can hunt |
| `Trading Program` / `Program` | `Program` | Deployable package |
| `Account Governor` / bare `Governor` | `Portfolio Governor` | Portfolio-level final authority |
| `Account` | `Broker Account` | Real Alpaca account/broker truth |
| `Deployment` | `Deployment` | Running instance of a Program |

---

## Recommended Route Naming

- `/strategies`
- `/strategy-controls`
- `/risk-profiles`
- `/execution-styles`
- `/watchlists`
- `/programs`
- `/portfolio-governors`
- `/broker-accounts`
- `/deployments`

---

## Recommended UI Labels

- `Strategies`
- `Strategy Controls`
- `Risk Profiles`
- `Execution Styles`
- `Watchlists`
- `Programs`
- `Portfolio Governor`
- `Broker Accounts`
- `Deployments`

---

## Recommended Service Naming

- `strategy_service`
- `strategy_controls_service`
- `risk_profile_service`
- `execution_style_service`
- `watchlist_service`
- `program_service`
- `portfolio_governor_service`
- `broker_account_service`
- `deployment_service`

---

## Recommended Event Naming

- `strategy_signal_emitted`
- `strategy_controls_blocked`
- `risk_profile_blocked`
- `execution_style_order_built`
- `portfolio_governor_approved`
- `portfolio_governor_rejected`
- `portfolio_governor_paused`
- `portfolio_governor_resumed`
- `broker_order_submitted`
- `broker_order_canceled`
- `broker_fill_received`
- `deployment_started`
- `deployment_paused`
- `deployment_stopped`

---

## Control-Plane Semantics

### Global Kill

**Intent:** Stop all new position-opening orders platform-wide.

**Should:**
- block all new opens
- pause entry permission globally
- cancel resting opening orders that are not backing existing open positions

**Should not:**
- flatten existing positions automatically
- cancel protective exit orders that are managing existing exposure

Flattening remains a separate explicit action.

---

### Portfolio Governor Pause

**Intent:** Stop new position-opening orders for the governed portfolio/account scope.

**Should:**
- block new opens in that scope
- cancel resting opening orders in that scope that are not backing existing positions

**Should not:**
- flatten positions automatically

---

### Program Pause

**Intent:** Stop new position-opening orders for that program/deployment.

**Should:**
- block new opens for that program
- cancel resting opening orders attributed to that program that are not backing existing positions

**Should not:**
- flatten positions automatically

---

### Flatten

**Intent:** Explicit liquidation of existing positions.

**Should:**
- close positions deliberately
- remain separate from kill/pause semantics

**Should not:**
- be overloaded as a kill switch

---

## Hard Boundary Rules

- Strategy may return signal truth, direction, stop candidate, and target candidate.
- Strategy Controls may allow or deny acting on a signal.
- Risk Profile may resize or reject based on risk limits.
- Execution Style may shape the order but must not invent the trade.
- Portfolio Governor is the last internal approval before broker submission.
- Broker Account is external truth.
- Deployment is runtime state only.

---

## Guidance For Multi-Timeframe Analysis

Multi-timeframe analysis belongs in **Strategy**, not in Strategy Controls.

Reason:
- it affects signal truth
- it is part of “what to trade and why”
- it is not a session/regime permission concern

Examples:
- 5m trigger only if 1h trend is up
- daily bias + intraday entry confirmation

That is Strategy logic.

---

## Guidance For Composite Strategy Logic

If multiple true/false evaluators are needed, they should live in the **Strategy**
domain as composite signal logic, not inside Strategy Controls or Portfolio Governor.

Examples:
- Strategy A returns true
- Strategy B confirms
- Strategy C vetoes

This still belongs to the “what to trade and why” layer.

---

## One-Sentence Mental Model

A Program defines the trade intent, a Deployment runs it, Strategy Controls decide when
it may act, the Portfolio Governor decides whether portfolio-level exposure is allowed,
and the Broker Account is the external source of truth.
