Alpaca Integration Output
1. Architecture Overview
Alpaca is an external provider. It supplies market data, broker state, and order execution. It does not define trading logic.

Final boundary:

Trading OS owns:
  Feature computation
  Signal logic
  Strategy Controls
  Risk Profile
  Execution Style
  Portfolio Governor
  Order Manager
  Control Plane
  Internal ledgers

Alpaca owns:
  market data feed
  historical bar source
  broker order execution
  broker order status
  fills
  positions
  buying power
  broker restrictions
Only two internal layers may talk to Alpaca:

Alpaca Market Data Adapter
Alpaca Broker Adapter
No Strategy, Feature Engine, Signal Engine, Governor, Sim Lab, Chart Lab, Backtest, Optimization, or frontend page may call Alpaca directly.

Primary flows:

Market data:
Alpaca Stream / Historical Bars
→ Alpaca Market Data Adapter
→ Market Data Service
→ Bar Builder
→ Feature Engine
→ Signal Engine

Trading:
CandidateTradeIntent
→ Strategy Controls
→ Risk Engine
→ Execution Intent Builder
→ Portfolio Governor
→ Order Manager
→ Alpaca Broker Adapter
→ Alpaca
→ Broker Sync
→ Order Ledger / Trade Ledger / Broker Account Snapshot
2. Market Data Streaming Model
Market data streaming is owned by the Market Data Service.

Alpaca-specific connection handling is owned by the Alpaca Market Data Adapter.

Ownership
Responsibility	Owner
Alpaca websocket connection	Alpaca Market Data Adapter
Provider authentication	Alpaca Market Data Adapter
Subscription requests	Market Data Service
Subscription translation to Alpaca	Alpaca Market Data Adapter
Reconnect/backoff	Alpaca Market Data Adapter
Symbol/timeframe demand aggregation	Market Data Service
Raw message normalization	Market Data Service
Multi-timeframe bar construction	Bar Builder
Feature computation	Feature Engine
Websocket Management
There is one market data stream manager per Alpaca data environment.

paper data environment if applicable
live data environment if applicable
The stream manager must track:

connection_state
authenticated
subscribed_symbols
last_message_at
last_bar_at_by_symbol
reconnect_count
last_error
rate_limit_state
Connection states:

disconnected
connecting
authenticating
connected
subscribed
stale
reconnecting
failed
Symbol Subscriptions
Subscriptions are demand-driven.

Demand comes from active consumers:

paper/live Deployments
Sim Lab live stream sessions
Chart Lab live preview only if using live data
Operations Center watch panels
Subscription key:

provider
environment
symbol
base_feed_type
Base feed type for v1:

1m bars
All higher timeframes are built internally.

Hard rule:

Subscribe to the lowest required provider-supported bar stream once per symbol.
Build 5m, 15m, 1h, 1d internally.
No component subscribes independently to the same symbol.

The Market Data Service maintains reference-counted demand:

symbol SPY demanded by:
  deployment A
  deployment B
  sim session C
When demand drops to zero, unsubscribe after a short grace period.

Multi-Timeframe Bars
Alpaca provides base bars. The OS builds canonical bars.

Flow:

Alpaca raw bar
→ normalized 1m bar
→ Bar Builder
→ completed canonical bars:
    1m
    5m
    15m
    30m
    1h
    4h
    1d
→ Feature Engine update
Bar Builder owns:

timestamp normalization
symbol normalization
duplicate bar handling
out-of-order handling
market session attribution
half-day daily bar completion
multi-timeframe aggregation
completed-bar emission
Feature Engine receives completed bars only.

No Strategy or Signal Engine sees raw Alpaca messages.

Streaming Freshness
Freshness is tracked by symbol and stream.

Required states:

fresh
delayed
stale
disconnected
unknown
If market data is stale:

new opens are blocked
existing protective exits remain active if broker-side
software-managed exits must enter degraded mode and alert operator
Operations Center must show stale state clearly
3. Historical / Warm-Up Model
Historical data is fetched through the Historical Data Service, using the Alpaca Market Data Adapter when Alpaca is selected as provider.

Fetch Flow
FeaturePlan
→ data requirements
→ Historical Data Service
→ cache lookup
→ Alpaca historical bars if cache miss
→ normalized bar store
→ Bar Builder if aggregation needed
→ Feature Engine warmup
Cache Use
Historical bars are cached before feature computation.

Cache key:

provider
environment
symbol
timeframe
start
end
adjustment_policy
calendar_version
Feature cache is separate from bar cache.

Hard split:

Bar cache stores normalized OHLCV.
Feature cache stores computed FeatureKeys.
Warm-Up Before Live Start
A Deployment cannot enter running until warm-up completes.

Warm-up sequence:

1. Load Deployment and frozen Program
2. Build FeaturePlan
3. Resolve symbols
4. Compute warmup requirements per symbol/timeframe
5. Fetch historical bars from cache or Alpaca
6. Normalize and aggregate bars
7. Warm Feature Engine runtime cache
8. Verify latest required FeatureSnapshot is warm
9. Start market data subscription
10. Confirm stream freshness
11. Allow Signal Engine evaluation
Deployment status flow:

created
→ warming
→ stream_confirming
→ running
Live start fails if:

historical bars unavailable
warmup insufficient
calendar invalid
FeaturePlan invalid
stream cannot subscribe
stream stale at start
account sync stale
broker restrictions unknown
Warm-up must never silently shorten lookback.

If Alpaca cannot provide enough bars, start is blocked with exact reason.

4. Order Lifecycle
The order lifecycle begins after deterministic approval.

Exact chain:

Signal Engine
→ CandidateTradeIntent
→ Strategy Controls
→ Risk Engine
→ Execution Intent Builder
→ Portfolio Governor
→ Order Manager
→ Alpaca Broker Adapter
→ Alpaca
→ Broker Sync
→ Order Ledger
→ Trade Ledger
Execution Intent
Execution Style produces:

ExecutionIntent
  intent: open | close | tp | sl | scale
  symbol
  side
  qty
  order_type
  time_in_force
  limit_price
  stop_price
  bracket_spec
  trailing_spec
  deployment_id
  program_id
  broker_account_id
Order Manager
Order Manager owns internal order creation.

Before broker submission:

create internal Order
status = pending_submission
assign client_order_id
persist full intent
Then:

submit via Alpaca Broker Adapter
If submission succeeds:

store broker_order_id
status = accepted/submitted based on broker response
If submission fails:

status = rejected
store reject reason
emit event
Alpaca Broker Adapter
The adapter maps internal ExecutionIntent to Alpaca request objects.

It owns:

Alpaca order API calls
request construction
response parsing
broker error mapping
broker id capture
It does not own:

approval
sizing
signal logic
risk logic
order intent semantics beyond mapping
Fills
Fills come from broker account stream or polling sync.

Fill flow:

Alpaca fill event
→ Alpaca Broker Adapter parses
→ Broker Sync normalizes
→ Order Ledger updates fill qty/status
→ Trade Ledger updates position/trade lifecycle
→ Broker Account Snapshot updates
→ Portfolio Governor state refreshes
→ Operations Center updates
Partial fills are first-class.

Order states must support:

pending_submission
submitted
accepted
new
partially_filled
filled
canceled
expired
rejected
replaced
pending_cancel
unknown
5. Order Attribution Model
Every broker order must map back to:

Broker Account
Deployment
Program
intent
internal Order
Attribution is required for:

cancellation
protective-order preservation
audit
reconciliation
partial-fill handling
monitoring
client_order_id Format
Use:

utos-{acct8}-{dep8}-{prog8}-{intent}-{seq}
Example:

utos-a1b2c3d4-d9e8f7a6-p3r4o5g6-open-000042
Fields:

Segment	Meaning
utos	platform prefix
acct8	Broker Account id prefix
dep8	Deployment id prefix
prog8	Program version id prefix
intent	open, close, tp, sl, scale
seq	per-deployment monotonic sequence
Intent values:

open
close
tp
sl
scale
Hard rules:

client_order_id must be under Alpaca’s limit.
Internal Order id remains the primary internal id.
client_order_id is broker attribution, not internal truth.
Unknown or malformed client_order_id must never be auto-canceled.
Bracket child orders must be linked internally even if Alpaca does not propagate client ids.
Internal Order Fields
Required:

id
client_order_id
broker_order_id
broker_account_id
deployment_id
program_version_id
intent
symbol
side
qty
filled_qty
order_type
time_in_force
limit_price
stop_price
status
parent_order_id
created_at
submitted_at
last_broker_update_at
reject_reason
6. Multi-Account + Deployment Model
The system supports:

multiple Broker Accounts
paper and live accounts
multiple Deployments per account
one Program deployed multiple times to different accounts
multiple Programs deployed to the same account
Broker Account
Broker Account owns:

broker
environment: paper | live
credentials
buying_power
balances
positions
orders
restrictions
sync_status
Deployment
Deployment references:

program_version_id
broker_account_id
portfolio_governor_id
mode: paper | live
Stream Managers
Market data stream is provider/environment scoped.

Broker account stream is account scoped.

Market data stream:
  shared by many deployments needing symbols

Broker account stream:
  one per Broker Account
Same Account, Multiple Deployments
When multiple Deployments share one Broker Account:

Market Data Service dedupes symbol subscriptions.
Portfolio Governor resolves cross-program conflicts.
Order Manager attributes each order to its Deployment.
Broker Sync reconciles all broker orders for the account.
Operations Center displays account-level and deployment-level views.
No Deployment owns the account.

No Deployment assumes it is alone.

7. Broker State Sync
Broker truth must be synchronized continuously and on demand.

Broker Sync owns reconciliation.

Sync Sources
broker account websocket events
periodic polling
manual refresh
startup hydration
post-order submission refresh
post-disconnect recovery
Synced State
balances
buying_power
positions
open_orders
recent_orders
fills
restrictions
PDT status
account status
Startup Sync
Before any Deployment runs:

1. load Broker Account
2. validate credentials
3. fetch account status
4. fetch balances/buying power
5. fetch positions
6. fetch open orders
7. reconcile open broker orders to internal orders
8. flag unknown external orders
9. start broker account stream
10. mark account sync fresh
Unknown external orders:

are displayed
are not automatically canceled
block live start if they create unsafe ambiguity
require operator review or explicit adoption/ignore action
Reconciliation Rules
Broker Sync compares:

internal Order Ledger
broker open orders
broker recent orders
broker positions
broker fills
Outcomes:

matched
missing_internal_order
missing_broker_order
status_mismatch
fill_mismatch
position_mismatch
unknown_external_order
All mismatches create audit events.

Critical mismatches block new opens for affected scope.

8. Failure Modes
Market Data Websocket Disconnect
Response:

mark stream disconnected
mark affected features stale
block new opens for affected symbols
attempt reconnect with backoff
alert Operations Center
Existing broker-side protective orders remain working at Alpaca.

Software-managed exits require explicit degraded-mode alert.

Market Data Stale
Response:

mark symbol stale
stop Signal Engine entries for symbol
continue broker sync
show stale timer
Historical Fetch Failure
Response:

warmup fails
Deployment remains warming or failed
no Signal Engine evaluation
exact provider error stored
Order Rejected
Response:

internal Order status = rejected
reject reason stored
Governor and Deployment event emitted
position state unchanged unless broker says otherwise
operator alert if protective order rejected
Partial Fill
Response:

update filled_qty
update position partial state
activate proportional protective logic if bracket/child behavior requires
keep remaining order open unless canceled/expired
refresh Governor projected exposure
Partial fill must not be treated as full fill.

Broker Stream Disconnect
Response:

mark account sync stale
block new opens for account
poll broker until stream recovers
alert operator
Reconnect
After reconnect:

fetch account snapshot
fetch open orders
fetch positions
fetch recent fills
reconcile ledgers
clear stale only if reconciliation passes
Rate Limit
Response:

backoff
defer non-critical refreshes
block starts that require missing data
never skip broker reconciliation silently
Alpaca Mode Mismatch
If account is configured paper but credentials/base URL indicate live, or vice versa:

block account activation
block deployment start
show critical configuration error
9. Control Plane Integration
Control Plane owns kill, pause, resume, and flatten semantics.

Alpaca Adapter executes broker operations only after Control Plane decides.

Kill / Pause Semantics
Kill or pause means:

stop new opens
cancel resting opening orders without positions
keep protective/reducing orders
do not flatten positions
Flatten means:

explicitly close positions
They are separate actions.

Required Control Actions
global_kill
global_resume
account_pause
account_resume
deployment_pause
deployment_resume
flatten_account
flatten_deployment_scope_if supported
emergency_exit = pause new opens + explicit flatten
Cancellation Rules
Only cancel orders where:

intent = open
and no existing position requires the order
and scope matches
Never automatically cancel:

tp
sl
close
scale
unknown
Unknown order intent:

keep
flag
require review
Scope Matching
Global kill:

all accounts
all deployments
Account pause:

one Broker Account
all Deployments on account
Deployment pause:

one Deployment only
Protective Orders
Protective orders must survive pause/kill.

Protective order types:

tp
sl
close
scale
If protective order cancellation is explicitly requested, it must be a separate dangerous action with confirmation.

Flatten
Flatten flow:

Control Plane requests flatten
→ Broker Sync fetches latest positions
→ Order Manager creates close intents
→ Portfolio Governor not needed for reducing exposure
→ Broker Adapter submits close orders
→ Broker Sync tracks fills
→ result reports per-symbol success/failure
Flatten must report:

positions requested
orders submitted
fills received
failures
remaining positions
protective orders canceled or retained
10. Backend Components Required
Required components:

AlpacaMarketDataAdapter
AlpacaBrokerAdapter
MarketDataService
HistoricalDataService
BarBuilder
BrokerAccountService
BrokerSyncService
OrderManager
OrderLedger
TradeLedger
ControlPlaneService
BrokerStreamManager
MarketDataStreamManager
AlpacaMarketDataAdapter
Owns:

market data websocket
historical bar API calls
Alpaca market data auth
provider response parsing
provider error mapping
AlpacaBrokerAdapter
Owns:

order submission
order cancellation
position close calls
account API calls
broker order parsing
broker fill parsing
BrokerSyncService
Owns:

account snapshot sync
order reconciliation
position reconciliation
fill processing
staleness detection
unknown external order handling
OrderManager
Owns:

internal order creation
client_order_id assignment
submission orchestration
order status transitions
scope-aware cancellation requests
ControlPlaneService
Owns:

kill/pause/resume/flatten decisions
scope precedence
cancellation policy
operator-facing result object
11. Acceptance Tests
No Strategy, Feature Engine, Signal Engine, Governor, Sim Lab, Chart Lab, or frontend page calls Alpaca directly.

Market Data Service dedupes subscriptions for the same symbol across multiple Deployments.

Market data websocket disconnect marks affected symbols stale.

Stale market data blocks new opens.

Historical warm-up blocks Deployment start when insufficient bars are available.

Warm-up uses cached bars before calling Alpaca.

Bar Builder creates 5m bars from 1m bars.

Bar Builder emits daily bars correctly on half-days.

Feature Engine receives completed normalized bars only.

Order Manager creates internal Order before Alpaca submission.

Alpaca Broker Adapter is the only order submission caller.

client_order_id includes account, deployment, program, intent, and sequence.

Malformed client_order_id parses as unknown and is never auto-canceled.

Multiple Deployments on one account produce distinct order attribution.

Broker Sync updates partial fills without treating them as complete fills.

Broker Sync reconciles open orders after reconnect.

Unknown external broker orders are flagged.

Unknown external broker orders block live start when unsafe.

Account paper/live mode mismatch blocks activation.

Broker stream disconnect marks account sync stale.

Account sync stale blocks new opens for that account.

Order rejection stores broker reject reason.

Protective order rejection raises high-severity alert.

Global kill blocks all new opens.

Account pause blocks only that account.

Deployment pause blocks only that Deployment.

Pause cancels resting open orders without positions.

Pause does not cancel tp, sl, close, or scale orders.

Pause keeps unknown-intent orders and flags them.

Flatten closes positions and is not triggered by pause alone.

Flatten reports per-symbol success/failure.

Reconnect performs full account snapshot reconciliation before clearing stale state.

Rate limit does not cause silent skipped reconciliation.

Paper account order cannot be submitted through live account config.

Live Deployment cannot start until broker sync and market data stream are both fresh.

12. First Implementation Tasks
Create strict Alpaca boundary
Move all Alpaca calls behind:

AlpacaMarketDataAdapter
AlpacaBrokerAdapter
Implement Market Data Service demand registry
Track symbol demand across Deployments and Sim Lab live sessions.

Implement Bar Builder
Build canonical bars internally from base Alpaca bars.

Include half-day handling.

Implement HistoricalDataService
Fetch bars through cache first, Alpaca second.

Implement Deployment warm-up gate
No running state until Feature Engine warmup and stream freshness pass.

Implement Order Manager
Create internal Order before submission.

Assign deterministic client_order_id.

Implement Order Ledger
Persist all internal/broker order lifecycle state.

Implement Broker Sync Service
Startup sync, periodic sync, websocket event sync, reconnect reconciliation.

Implement unknown external order handling
Flag, display, and block live start when unsafe.

Implement partial-fill processing
Update order, position, trade, and governor state incrementally.

Implement control-plane cancellation sweep
Cancel only scope-matching open orders without positions.

Keep protective and unknown orders.

Implement broker/market staleness gates
Block new opens on stale market data or broker sync.

Implement multi-account stream model
One broker stream per Broker Account.

Shared market data streams by provider environment.

Implement mode mismatch validation
Paper/live mismatch is a hard block.

Add integration tests around reconnect
Disconnect, reconnect, snapshot sync, reconciliation, stale clearing.