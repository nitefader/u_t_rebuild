# Alpaca Broker Nuance Playbook for Ultimate Trader Agents

Last updated: 2026-05-01  
Source scope: Alpaca public documentation reviewed on 2026-05-01. Agents must verify against current Alpaca docs before changing broker behavior.

## Purpose

This file is mandatory reading for any agent touching Alpaca integration, broker order submission, account sync, position protection, order preflight, market rules, or Operations visibility.

Ultimate Trader doctrine remains the authority:

```text
Strategy
-> Deployment
-> SignalPlan
-> Account Evaluation
-> RiskResolver
-> Governor
-> Order Ledger
-> BrokerAdapter
-> BrokerSync
-> Position Truth
-> Operations Center
```

Alpaca is a provider behind boundaries. Alpaca must not become the architecture.

## Non-Negotiable System Rules

1. Alpaca-specific behavior belongs behind:
   - `BrokerAdapter`
   - `BrokerSync`
   - broker capability preflight
   - market/session preflight
   - account trade sync

2. Core domain models must not become Alpaca-specific:
   - `Strategy`
   - `Deployment`
   - `SignalPlan`
   - `Account Evaluation`
   - `RiskResolver`
   - `Governor`

3. No order reaches Alpaca unless:
   - the Account is valid
   - broker mode is known: `paper` or `live`
   - Account Trade Sync freshness is known
   - RiskResolver resolved account-specific size
   - Governor approved
   - broker capability preflight passed
   - market/session preflight passed
   - Order Ledger created an internal order with lineage

4. Broker-derived truth must only be written by `BrokerSync`.
   - order status
   - broker order id
   - fills
   - partial fills
   - positions
   - account snapshots
   - restrictions
   - sync freshness

5. A manual Alpaca position has no SignalPlan lineage unless Ultimate Trader explicitly adopts it.
   - Do not assume a Deployment can protect an unmanaged broker position.
   - The adoption mechanism must be explicit, auditable, and visible.

---

# 1. Alpaca Environments and Connections

## Trading REST endpoints

Typical direct Trading API endpoints:

```text
Paper: https://paper-api.alpaca.markets
Live:  https://api.alpaca.markets
```

Broker API sandbox endpoints may differ and usually use broker-specific account paths.

Ultimate Trader interpretation:

```text
Account
  broker_provider: alpaca
  broker_mode: paper | live
```

Paper/live must be Account metadata, not separate runtime products.

## Trade update WebSocket

Alpaca trade/account/order updates use WebSocket connections:

```text
Paper: wss://paper-api.alpaca.markets/stream
Live:  wss://api.alpaca.markets/stream
```

The client authenticates, then listens to:

```json
{
  "action": "listen",
  "data": {
    "streams": ["trade_updates"]
  }
}
```

The stream emits trade/order updates such as new, fill, partial_fill, cancel, and reject events.

Ultimate Trader requirement:

- one Account Trade Sync per validated Alpaca Account
- starts at app startup for every validated Alpaca Account
- starts after Account creation and successful credential validation
- remains open even if trading is paused
- trading pause and trade-sync pause are separate controls
- all events route through BrokerSync first, then fan out to Operations/runtime subscribers

## Market data WebSocket

Alpaca market data is a separate system from trade updates.

Do not confuse:

```text
Market Data Stream != Account Trade Sync
```

Ultimate Trader requirement:

- one shared Live Stock Market Data Stream for the platform
- all consumers subscribe through the shared stream
- no component-owned private live stock socket for equities

---

# 2. Order Identity and Idempotency

Alpaca allows a client-provided order identifier. If the client does not provide one, Alpaca generates one.

Ultimate Trader must always provide a deterministic `client_order_id` for automated orders.

Recommended client order id components:

```text
ut:{account_id}:{signal_plan_id}:{intent}:{leg_label}:{idempotency_hash}
```

Constraints:

- Alpaca client order id max length is 128 characters.
- It must be stable for retry/idempotency.
- It must map back to the internal Order Ledger order.
- BrokerSync must resolve fills by broker order id and/or client order id.

Required agent checks:

- Does every automated order have `client_order_id`?
- Can BrokerSync map trade update fills back to internal `order_id`?
- Are duplicate submissions blocked before Alpaca?
- Are manual orders clearly marked as manual operator orders?

---

# 3. Order Classes

Alpaca supports different order classes by asset class.

## Equity order classes

Equity trading supports:

```text
simple / empty
bracket
oco
oto
```

## Options order classes

Options support:

```text
simple / empty
mleg
```

`mleg` is required for multi-leg complex option strategies.

## Crypto order classes

Crypto supports:

```text
simple / empty
```

Ultimate Trader rule:

- Core `SignalPlan` may describe targets, stops, runner, and logical exits.
- Broker preflight decides whether that lifecycle can be expressed as Alpaca `bracket`, `oco`, `oto`, trailing stop, or multiple simple orders.
- Do not leak Alpaca `order_class` into strategy semantics as the primary model.

---

# 4. Bracket Orders

A bracket order is an entry order plus two conditional exits:

```text
entry order
-> take-profit limit order
-> stop-loss stop or stop-limit order
```

When the entry completely fills, the two exit legs become active. One exit filling cancels the other. In highly volatile markets, both exits may fill before cancellation completes, so the system must reconcile broker truth rather than assuming perfect mutual exclusion.

Required fields for Alpaca bracket order:

```json
{
  "symbol": "SPY",
  "side": "buy",
  "type": "market",
  "qty": "100",
  "time_in_force": "gtc",
  "order_class": "bracket",
  "take_profit": {
    "limit_price": "301"
  },
  "stop_loss": {
    "stop_price": "299",
    "limit_price": "298.5"
  }
}
```

Important Alpaca bracket rules:

- `order_class` must be `bracket`.
- `take_profit.limit_price` is required.
- `stop_loss.stop_price` is required.
- `stop_loss.limit_price` is optional.
- If `stop_loss.limit_price` is present, Alpaca queues stop-loss as stop-limit.
- If `stop_loss.limit_price` is absent, Alpaca queues stop-loss as stop.
- For buy brackets, take-profit price must be above stop-loss stop price.
- For sell brackets, take-profit price must be below stop-loss stop price.
- Extended hours are not supported for bracket orders.
- `extended_hours` must be false or omitted.
- `time_in_force` must be `day` or `gtc`.
- Each leg appears as an independent order in GET orders.
- Use `nested=true` when retrieving orders if child legs should be nested under the parent.
- If the take-profit partially fills, Alpaca adjusts the stop-loss to the remaining quantity.
- Replacement supports updating `limit_price` and `stop_price`.
- Bracket order legs are DNR/DNC, meaning Alpaca says the order price will not be adjusted and the order will not be canceled for dividend or similar corporate actions.

Ultimate Trader implication:

- A bracket is a broker execution shape, not the canonical strategy lifecycle.
- If Strategy has 4 targets plus runner, a single Alpaca bracket is not enough.
- If the system needs multiple targets, create internal order legs with one shared SignalPlan/Position lineage.
- Do not create multiple unrelated positions for multiple targets.
- BrokerSync must reconcile every child leg.

---

# 5. OCO Orders

OCO means One-Cancels-Other.

Alpaca OCO is currently an exit-order shape. Use it when the position already exists and the system wants to attach take-profit plus stop-loss exits.

Required shape:

```json
{
  "symbol": "SPY",
  "side": "sell",
  "type": "limit",
  "qty": "100",
  "time_in_force": "gtc",
  "order_class": "oco",
  "take_profit": {
    "limit_price": "301"
  },
  "stop_loss": {
    "stop_price": "299",
    "limit_price": "298.5"
  }
}
```

Important Alpaca OCO rules:

- `order_class` must be `oco`.
- Parent order type must be `limit`.
- `take_profit.limit_price` is required.
- `stop_loss.stop_price` is required.
- `stop_loss.limit_price` is optional.
- Replacement supports updating `limit_price` and `stop_price`.
- With `nested=true`, take-profit appears as parent and stop-loss appears as child.

Ultimate Trader implication:

- OCO may be useful for protecting adopted/manual positions.
- But only if the position is linked to an Account-owned Position context.
- OCO must preserve `opening_signal_plan_id` or `position_lineage_id` when used for system-managed positions.
- For unmanaged manual positions, the system must either:
  - adopt the position explicitly, then create protective OCO/OTO/stop orders, or
  - mark it unmanaged and not protected.

---

# 6. OTO Orders

OTO means One-Triggers-Other.

Alpaca OTO is like a simplified bracket: entry plus either a take-profit or stop-loss, not both.

Important Alpaca OTO rules:

- `order_class` must be `oto`.
- Either `take_profit` or `stop_loss` must be present.
- The rest of the requirements follow bracket order rules.
- Alpaca documentation states order replacement is not supported yet for OTO.

Ultimate Trader implication:

- OTO is useful for entry with only one protective leg, such as a stop-only entry.
- If the system must later move stop, trail, or change protection, verify whether replacement is supported for that order shape. If not, cancel and replace via a controlled lifecycle.

---

# 7. Stop-Loss Threshold Rule for Advanced Orders

For advanced order stop-loss legs, Alpaca can reject the request if the `stop_price` is too close to the base price.

Alpaca rule:

```text
Stop price must be at least $0.01 below the base price for a stop-loss sell,
or at least $0.01 above the base price for a stop-loss buy.
```

Base price is determined as:

- OCO: take-profit limit price
- Bracket or OTO with limit entry: entry limit price
- Any OCO, OTO, or bracket: current market price may also be used

Ultimate Trader preflight requirement:

- reject or warn before submit if stop distance violates the $0.01 threshold
- include operator-facing advisory:
  - `alpaca_stop_price_too_close_to_base_price`
  - include stop price, base price, side, and required minimum distance

---

# 8. Trailing Stop Orders

Alpaca trailing stop orders automatically move the stop price as price moves favorably.

Trailing stop fields:

```text
type: trailing_stop
trail_price: dollar offset from high-water mark
trail_percent: percentage offset from high-water mark
```

Exactly one of `trail_price` or `trail_percent` is required.

Example:

```json
{
  "symbol": "SPY",
  "side": "sell",
  "type": "trailing_stop",
  "qty": "100",
  "time_in_force": "day",
  "trail_price": "6.15"
}
```

Important Alpaca trailing stop rules:

- Sell trailing stop tracks highest price since submission.
- Buy trailing stop tracks lowest price since submission.
- Once stop triggers, it becomes a market order.
- Execution may be worse than stop trigger price.
- Trailing stops do not trigger outside regular market hours.
- Valid TIF values are `day` and `gtc`.
- Trailing stops are currently supported only as single orders, not as bracket/OCO stop-loss legs.
- Corporate actions or incorrect third-party market data can cause premature triggers.
- Alpaca may cancel or adjust pricing/share quantities after stock splits.

Ultimate Trader implication:

- Do not model Alpaca trailing stop as guaranteed protection during extended hours.
- If the Strategy requires extended-hours trailing protection, the system must implement logical trail management internally and submit valid supported orders.
- BrokerSync must own truth after trigger/fill.

---

# 9. Order Types and Time In Force

## Equity whole-share orders

Alpaca supports these broad combinations for whole-quantity equity orders:

| TIF | Market | Limit | Stop | Stop Limit |
|---|---:|---:|---:|---:|
| GTC | yes | yes | yes | yes |
| DAY | yes | yes | yes | yes |
| IOC | maybe by entitlement | maybe by entitlement | no | no |
| FOK | maybe by entitlement | maybe by entitlement | no | no |
| OPG | maybe by entitlement | maybe by entitlement | no | no |
| CLS | maybe by entitlement | maybe by entitlement | no | no |

`IOC`, `FOK`, `OPG`, and `CLS` may require sales/team enablement depending on Alpaca account setup.

## Fractional equity orders

Fractional orders support:

```text
market
limit
stop
stop_limit
TIF = day
```

Alpaca supports either:

```text
qty
```

or

```text
notional
```

but not both. If both are sent, the request is rejected.

`qty` and `notional` may use up to 9 decimal places.

Short sales in fractional orders are not supported. Alpaca marks fractional sell orders long.

## Extended-hours orders

Extended-hours equity orders require:

```text
type = limit
time_in_force = day or gtc
extended_hours = true
```

Rejected:

```text
market + extended_hours
stop + extended_hours
stop_limit + extended_hours
ioc/fok/opg/cls + extended_hours
```

## Crypto orders

Alpaca crypto TIF support:

| TIF | Market | Limit | Stop | Stop Limit |
|---|---:|---:|---:|---:|
| GTC | yes | yes | no | yes |
| DAY | no | yes | no | no |
| IOC | yes | yes | no | no |
| FOK | no | no | no | no |
| OPG | no | no | no | no |
| CLS | no | no | no | no |

Crypto only supports simple order class.

## OTC assets

OTC TIF support:

| TIF | Market | Limit | Stop | Stop Limit |
|---|---:|---:|---:|---:|
| GTC | yes | yes | yes | yes |
| DAY | yes | yes | yes | yes |
| IOC/FOK/OPG/CLS | no | no | no | no |

However, market data for OTC may require special subscriptions. Do not assume data availability.

## Options

Options order TIF support:

| TIF | Market | Limit | Stop | Stop Limit |
|---|---:|---:|---:|---:|
| GTC | yes | yes | yes | yes |
| DAY | yes | yes | yes | yes |
| IOC/FOK/OPG/CLS | no | no | no | no |

Options order class:

```text
simple / empty
mleg for multi-leg complex option strategies
```

Ultimate Trader preflight requirement:

- validate asset class
- validate order type
- validate TIF
- validate order class
- validate extended-hours compatibility
- validate fractional/notional combination
- validate Account entitlements if IOC/FOK/OPG/CLS are attempted
- fail before BrokerAdapter submit when knowable

---

# 10. Extended Hours and 24/5 Trading

Alpaca supports:

```text
Overnight:    8:00 PM - 4:00 AM ET, Sunday to Friday
Pre-market:   4:00 AM - 9:30 AM ET, Monday to Friday
Regular:      9:30 AM - 4:00 PM ET, Monday to Friday
After-hours:  4:00 PM - 8:00 PM ET, Monday to Friday
```

Trading API accounts are enabled for 24/5 trading by default according to Alpaca’s current Trading API documentation, but agents must still verify account settings and asset eligibility.

Overnight trading:

- supports NMS securities
- excludes OTC securities
- uses `overnight_tradable` asset attribute
- can be affected by `overnight_halted`
- only supports limit orders
- supports TIF `day` and `gtc`
- fractional trading is supported
- DTBP does not apply overnight
- overnight max margin buying power is 2x
- overnight data feed depends on market data plan/feed

Ultimate Trader market/session preflight must inspect:

```text
market session
asset tradable
asset overnight_tradable
asset overnight_halted
asset fractionable
order type
TIF
extended_hours flag
buying power type
```

---

# 11. Buying Power and Margin Checks

Alpaca applies buying power checks to orders that open or add to positions.

Important behavior:

- Open buy orders consume buying power while open.
- Open short sell orders also consume buying power.
- Opening short sell order value uses max(limit price, 3 percent above current ask) times quantity.
- Market short order value uses 3 percent above current ask times quantity.
- Buying-power reference changes by session:
  - core session open: far side of NBBO
  - extended hours open: midpoint of inside market
  - pre-market/core/extended closed: latest trade from market cache

Ultimate Trader preflight must:

- include open orders in projected buying power
- include existing positions
- distinguish opening vs closing/reducing orders
- handle short-side buying-power estimate
- treat Account buying power stale if Account Trade Sync is stale
- produce operator-visible reason when blocked

Recommended violation codes:

```text
alpaca_buying_power_insufficient
alpaca_buying_power_stale
alpaca_short_order_buying_power_estimate_failed
alpaca_open_orders_reserve_buying_power
```

---

# 12. Assets, Tradability, Fractionability, Shortability

Agents must query Alpaca asset metadata before assuming a symbol can trade.

Important fields:

```text
class
exchange
symbol
status
tradable
marginable
shortable
easy_to_borrow
fractionable
overnight_tradable
overnight_halted
attributes
```

Required checks:

- `status == active`
- `tradable == true`
- fractional order requires `fractionable == true`
- short order requires `shortable == true`
- short order should check `easy_to_borrow == true` where applicable
- overnight order requires `overnight_tradable == true`
- overnight order must fail or defer if `overnight_halted == true`
- IPO symbols may require limit orders before first exchange trade
- OTC may require special data handling and may not be available on normal data feeds

Ultimate Trader market data implication:

- A tradable symbol is not necessarily available on your selected market data feed.
- Market data subscription errors are not broker execution errors.
- Operations must show market data feed problems separately from Account Trade Sync problems.

---

# 13. Order Lifecycle Statuses

Common Alpaca order statuses:

```text
new
partially_filled
filled
done_for_day
canceled
expired
replaced
pending_cancel
pending_replace
```

Less common statuses:

```text
accepted
pending_new
accepted_for_bidding
stopped
rejected
suspended
```

Important handling rules:

- `filled` is terminal for the order.
- `canceled` and `expired` are terminal for the order.
- `partially_filled` must update remaining quantity and Position truth.
- `pending_cancel` means cancellation is requested but not final.
- `pending_replace` means replacement is pending and cancel may be rejected.
- `accepted` can occur outside trading hours before routing.
- `rejected` must surface operator-visible reason.

Ultimate Trader BrokerSync requirements:

- every status transition is idempotently applied
- fills and partial fills update position truth
- replace/cancel pending states are visible
- no mission-critical order state lives only in logs
- Operations table must expose status, last event time, last error/advisory

---

# 14. Account Activities

Alpaca account activities include:

```text
FILL: order fills, partial and full
TRANS: cash transactions
DIV: dividends
ACATS / ACATC: transfers
CFEE: crypto fee
CSD / CSW: cash deposit/withdrawal
```

Ultimate Trader use:

- `trade_updates` is preferred for live order/fill state.
- Account activities are useful for reconciliation/backfill.
- BrokerSync reconciliation should compare:
  - orders
  - positions
  - account snapshot
  - fills/account activities where needed

---

# 15. Position Sync and Manual Position Adoption

Alpaca positions are broker truth.

Ultimate Trader positions are Account-owned position truth with lineage.

A position opened directly in Alpaca can exist in broker truth without Ultimate Trader lineage.

Agents must distinguish:

```text
broker position exists
```

from:

```text
Ultimate Trader managed position exists with SignalPlan lineage
```

If a manual Alpaca position appears:

Required classification:

```text
unmanaged_broker_position
```

Required operator-visible states:

```text
Detected in Alpaca
No opening SignalPlan
No position_lineage_id
Not protected by Deployment unless adopted
```

Adoption flow, if implemented, must:

1. ingest position through BrokerSync
2. create or attach an Account-owned Position lineage
3. mark source as manual/adopted
4. optionally bind to a Deployment/Strategy only by explicit operator action
5. generate protective SignalPlan or manual protective order request
6. pass RiskResolver/Governor
7. create protective order through OrderManager
8. submit via BrokerAdapter
9. reconcile via BrokerSync

Do not silently “protect” random broker positions without an explicit adoption policy.

---

# 16. Reconciliation Strategy

Account Trade Sync can miss events during disconnects. REST reconciliation is still required.

Recommended BrokerSync reconciliation inputs:

- GET account
- GET positions
- GET open orders
- GET recent closed orders
- GET specific order by broker order id or client order id
- GET activities/fills where needed
- market clock/calendar for session interpretation

Recommended triggers:

- app startup
- Account Trade Sync reconnect
- credential replacement
- order submission
- order rejection
- periodic interval
- operator Refresh Sync
- before live order submission if sync is stale

Required stale-state behavior:

- if Account Trade Sync stale, Governor should block new opening orders
- close/reduce protective actions may be allowed only by explicit policy
- Operations must show stale/down/degraded status
- agent must not treat stale data as healthy

---

# 17. Error and Advisory Taxonomy

Minimum broker error families:

```text
authentication
authorization
missing_credentials
mode_mismatch
buying_power
margin
short_sale_restriction
not_easy_to_borrow
asset_not_tradable
asset_not_fractionable
asset_halted
market_closed
extended_hours_unsupported
unsupported_order_type
unsupported_time_in_force
unsupported_order_class
invalid_price
invalid_stop_distance
invalid_quantity
invalid_notional
qty_notional_conflict
duplicate_client_order_id
rate_limited
broker_unavailable
stream_disconnected
order_rejected
order_canceled_externally
stale_broker_sync
unknown_broker_response
```

Each failure event must include:

```text
code
family
severity
retryable
source
account_id
order_id
client_order_id
symbol
operator_advisory
raw_broker_code
raw_broker_message
timestamp
```

Recommended severities:

```text
info
warning
error
critical
```

Recommended retry logic:

- retry transport failures with backoff
- retry 429 only after rate-limit/backoff
- do not retry validation failures unchanged
- do not retry buying power failures unchanged
- do not retry duplicate client order id by generating random id unless previous order status is resolved
- do not retry unsupported order shape
- do not retry auth failures until credentials are updated

---

# 18. Rate Limits and 429 Handling

Alpaca API responses may return 429 when rate limits are hit. Alpaca references `X-RateLimit-*` response headers in API reference pages.

Ultimate Trader requirement:

- centralize Alpaca HTTP client rate-limit handling
- classify 429 as `rate_limited`
- include retry-after/header context when available
- backoff, do not spin
- surface degraded provider state in Operations
- prevent agents from “fixing” 429 by adding more polling loops

---

# 19. Market Clock and Calendar

Alpaca clock API returns current market timestamp, open/closed state, next open, and next close.

Alpaca calendar API provides trading days from 1970 to 2029 with open/close times and early closures.

Ultimate Trader requirement:

- Market/session preflight must use clock/calendar, not hardcoded weekday assumptions.
- Early closes must be respected.
- Overnight sessions must respect holiday behavior.
- Strategy trading windows must be interpreted against exchange/session calendar.
- “Exit after 3 bars” must specify:
  - timeframe
  - closed bars vs live/in-progress bars
  - session behavior
  - whether after-hours bars count

---

# 20. Market Data Feed Nuances

Alpaca market data supports HTTP and WebSocket.

Important feed nuance:

- Free/default plans may use IEX for latest endpoints.
- SIP may require subscription.
- Overnight market data depends on feed and plan.
- OTC market data may require special subscription.
- Latest endpoints return raw latest data without adjustment.
- Historical endpoints may handle symbol changes via `asof`.
- Stream clients may need to resubscribe after ticker changes.

Ultimate Trader implication:

- Market data resolver must select feed based on:
  - symbol
  - asset class
  - session
  - timeframe
  - historical depth
  - subscription availability
- Provider failure must not be confused with strategy failure.
- FeatureEngine must mark missing/stale bars visibly.
- If a one-minute strategy requires closed bars, no logical exit can fire until the required number of bars is actually available.

---

# 21. Alpaca Order Preflight Checklist

Before submitting an Alpaca order, agents must verify:

## Account

- Account exists
- broker_provider is `alpaca`
- broker_mode is known
- credentials are present
- credentials validated
- account status supports trading
- trading is not blocked
- Account Trade Sync status known
- Account Trade Sync freshness acceptable

## Order lineage

- internal order exists
- order has account id
- automated order has Strategy/Deployment/SignalPlan lineage
- manual order is explicitly marked manual
- lifecycle intent is set
- idempotency/client order id is deterministic

## Asset

- asset exists
- status active
- tradable true
- fractionable if fractional/notional
- shortable/easy-to-borrow if short
- not halted where known
- overnight_tradable if overnight
- not overnight_halted if overnight

## Session

- market clock loaded
- calendar loaded
- session classification known:
  - regular
  - pre-market
  - after-hours
  - overnight
  - closed
  - early close
- extended_hours flag valid for intended session

## Shape

- side valid
- qty xor notional
- order type supported
- TIF supported
- order_class supported
- limit_price present for limit and stop_limit
- stop_price present for stop and stop_limit
- trailing stop has exactly one of trail_price/trail_percent
- advanced order stop price threshold valid
- bracket/OCO/OTO required nested fields present
- bracket extended_hours false/omitted
- bracket/OCO TIF day or gtc
- notional order replacement not attempted
- OTO replacement not attempted unless Alpaca docs change

## Risk

- buying power sufficient
- projected exposure allowed
- position state fresh
- open orders considered
- duplicate order protection passed
- Governor approved

---

# 22. Position Protection Failure Investigation Path

When a position is not protected, agents must follow this order.

## Step 1: Broker truth

Check:

```text
Does Alpaca show the position?
Did BrokerSync ingest it?
Is it visible in runtime store?
Is it visible in Operations?
Is Account Trade Sync connected/fresh?
```

If no, root cause is sync/truth ingestion.

## Step 2: Lineage

Check:

```text
position_lineage_id
opening_signal_plan_id
current_signal_plan_id
deployment_id
strategy_id
```

If missing, classify as unmanaged/manual broker position unless adoption exists.

## Step 3: Deployment coverage

Check:

```text
active Deployment?
Deployment includes Account?
Deployment includes symbol via Watchlist snapshot?
Deployment runtime healthy?
Strategy attached to Deployment?
```

If no, Deployment cannot protect the position.

## Step 4: Strategy management logic

Check:

```text
strategy timeframe = 1m?
logical exit = after 3 bars?
bar source healthy?
closed bars advancing?
FeatureEngine producing 1m bars?
SignalEngine/SignalPlanBuilder producing logical_exit SignalPlan?
```

If no, root cause is computation/signal emission.

## Step 5: Account evaluation

Check:

```text
Was SignalPlan delivered to Account?
Was AccountSignalPlanEvaluation created?
Status accepted/rejected/blocked/deferred/ignored?
```

If no, root cause is fanout/evaluation.

## Step 6: Governor

Check:

```text
Governor request exists?
Governor approved?
If rejected, exact reasons?
```

Common blockers:

```text
stale sync
account paused
deployment paused
global kill
duplicate protection
buying power
position mismatch
symbol restriction
expired SignalPlan
```

## Step 7: Order path

Check:

```text
OrderManager created internal order?
Broker capability preflight passed?
Market rule preflight passed?
BrokerAdapter submitted?
BrokerSync reconciled order/fill?
```

If no, identify boundary and exact error.

---

# 23. Agent Implementation Rules

Agents must not:

- call Alpaca directly from frontend
- call Alpaca directly from Strategy, SignalPlan, Governor, or FeatureEngine
- bypass BrokerAdapter for submit/cancel/replace
- bypass BrokerSync for broker truth writes
- create a second runtime path for paper/live
- create one Deployment per Account just because Alpaca account differs
- silently ignore broker positions without showing unmanaged state
- silently protect unmanaged positions without explicit adoption
- assume bracket orders solve multi-target lifecycle
- assume extended-hours orders support market/stop orders
- assume trailing stops protect outside regular hours
- assume market data feed availability equals tradability
- retry invalid broker orders without changing the invalid shape
- hide raw broker rejection messages from Operations

Agents must:

- update implementation log/status files
- add tests for any new Alpaca rule
- preserve doctrine names
- keep Alpaca provider-specific rules out of core domain
- add operator-facing advisories
- run slice tests and relevant unit tests
- cite Alpaca docs in code comments only when helpful
- keep failures copyable for LLM/operator review

---

# 24. Minimum Tests Agents Should Add

## Broker capability tests

- equity bracket rejects extended_hours true
- bracket requires take_profit.limit_price and stop_loss.stop_price
- bracket buy requires take_profit above stop_loss stop
- OCO parent type must be limit
- OTO requires take_profit or stop_loss
- advanced stop threshold rejects too-close stop
- trailing stop requires trail_price xor trail_percent
- trailing stop rejects unsupported TIF
- notional replacement rejected
- fractional qty + notional conflict rejected
- fractional short rejected
- extended-hours market rejected
- extended-hours limit day accepted
- extended-hours limit gtc accepted
- crypto unsupported TIF rejected
- OTC data warning surfaced
- options mleg only allowed for options

## BrokerSync tests

- trade_update new writes order state
- partial_fill updates order and position
- fill maps to internal order by client_order_id
- cancel/reject visible in Operations
- reconnect triggers reconciliation
- stale sync blocks opening order by Governor

## Position adoption tests

- manual Alpaca position is classified unmanaged
- unmanaged position is visible in Operations
- unmanaged position is not auto-protected without adoption
- adopted position creates position_lineage_id
- protective order for adopted position goes through Governor and OrderManager

## Runtime tests

- one Account Trade Sync per validated Alpaca Account
- trading pause does not close Account Trade Sync
- paper/live are Account metadata
- no duplicate paper runtime path
- one shared Live Stock Market Data Stream
- FeatureEngine missing 1m bars prevents 3-bar logical exit and surfaces reason

---

# 25. Official Source Links

Agents should verify current details against these Alpaca docs before changing behavior:

- Placing Orders: https://docs.alpaca.markets/docs/orders-at-alpaca
- Working with Orders: https://docs.alpaca.markets/docs/working-with-orders
- Create Order Reference: https://docs.alpaca.markets/reference/createorderforaccount
- WebSocket Streaming: https://docs.alpaca.markets/docs/websocket-streaming
- Fractional Trading: https://docs.alpaca.markets/docs/fractional-trading
- 24/5 Trading: https://docs.alpaca.markets/docs/245-trading-for-trading-api
- Market Data API: https://docs.alpaca.markets/docs/about-market-data-api
- Market Data FAQ: https://docs.alpaca.markets/docs/market-data-faq
- Market Clock: https://docs.alpaca.markets/reference/legacyclock-1
- Market Calendar: https://docs.alpaca.markets/reference/legacycalendar
- Account Activities: https://docs.alpaca.markets/docs/account-activities

---

# 26. Final Agent Reminder

Alpaca rules are not optional, but they are also not the architecture.

The architecture is:

```text
Strategy -> Deployment -> SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> Order Ledger -> BrokerAdapter -> BrokerSync -> Position Truth -> Operations Center
```

Every Alpaca nuance must be enforced through provider-specific preflight, adapter translation, sync reconciliation, and operator-visible advisory messages.
