# Phase 1 Core Backend Contracts

Last updated: 2026-04-26 19:59:00 -04:00

Operation: Turtle Shell

Phase: Phase 1: Core Domain Contract Lock

Status: draft in progress

Owner: Coordinator

## Purpose

These contracts define the backend spine that implementation must converge on.

The goal is to replace the current executable spine:

```text
CandidateTradeIntent -> ExecutionIntent -> Order
```

with the locked doctrine:

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
```

## Contract Rules

- SignalPlan is neutral.
- SignalPlan does not contain final Account quantity.
- Account Evaluation is Account-specific.
- RiskResolver computes allowed size and risk impact.
- Governor is the final Account protection gate before order creation.
- Order Ledger preserves SignalPlan and Position lineage.
- BrokerAdapter submits/cancels/replaces broker orders.
- BrokerSync writes broker-derived truth.
- Position truth belongs to Account.
- AI may explain but may not mutate truth.

## Hard Gates Added By Review

### Runtime Composition Root Gate

Implementation must choose one runtime composition root. That root owns:

- Deployment startup/shutdown
- SignalPlan publication
- Account fan-out
- Account Evaluation creation
- RiskResolver invocation
- Governor invocation
- OrderManager handoff
- stream status projection

All other runtime-like modules must become pure components, adapters, read
models, test harnesses, or explicit migration shims.

Forbidden without Coordinator and Angry Architect approval:

```text
new runtime entrypoint
new orchestrator owning order flow
new broker runtime loop by mode
new per-component live stock stream
```

### Program Lineage Ban Gate

Program lineage is not accepted in new runtime contracts.

Forbidden outside explicit migration shims:

```text
Program
ProgramVersion
program_id
program_version_id
OrderOrigin.PROGRAM
build_program_client_order_id
```

Required lint gate:

```text
No active runtime/order/governor/operations contract may introduce Program
lineage. Existing Program names must be isolated behind named migration shims
until removed.
```

### Paper/Live Account Metadata Gate

Paper and live are Account metadata only.

Forbidden:

```text
paper runtime
live runtime
load_active_broker_paper_deployments
paper-only runtime preflight
runtime selection by paper/live path
```

Allowed:

```text
Account.broker_mode = paper | live | provider-supported mode
BrokerAdapter derives endpoint behavior from Account metadata
```

### BrokerSync Truth Gate

Only BrokerSync may write or reconcile broker-derived truth.

Broker-derived truth includes broker order status, fills, broker order ids,
broker position snapshots, account snapshots, broker restrictions, and sync
freshness.

Routes, OrderManager, recovery, runtime, and UI-facing services may request
actions or read projections, but they must not write broker truth directly.

Required tests:

- OrderManager does not read broker positions directly.
- Recovery routes broker truth through BrokerSync.
- Manual trade route uses an application service, not direct broker truth
  mutation.
- BrokerSyncService resolves fill events to internal `order_id` by
  `client_order_id`.

## Canonical Enums

### SignalPlanIntent

```text
open
close
reduce
target
stop
trail
breakeven
runner
logical_exit
```

### SignalPlanSide

```text
long
short
flat
```

### SignalPlanStatus

```text
created
published
expired
partially_executed
executed
superseded
canceled
failed
```

SignalPlanStatus is global to the neutral SignalPlan. Account-specific accepted,
rejected, blocked, stale, and deferred states belong on
AccountSignalPlanEvaluation.

### AccountEvaluationStatus

```text
accepted
rejected
blocked
needs_operator_attention
deferred
stale
```

### GovernorDecisionStatus

```text
approved
rejected
blocked
degraded
requires_operator
```

## Strategy Contract

Strategy is reusable trading logic and execution-plan configuration.

Strategy owns:

- signal rules
- feature requirements
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
- final quantity
- final broker execution decision

Minimum contract:

```text
Strategy
  strategy_id
  strategy_version_id
  name
  status
  config_fingerprint
  feature_requirements
  signal_rules
  execution_plan
  created_at
  updated_at
```

Implementation note:

Current `ProgramVersion` can temporarily serve as a migration shim only. It must
not remain the active product concept.

## Watchlist Contract

Watchlist is the source of eligible symbols.

Minimum contract:

```text
Watchlist
  watchlist_id
  name
  source_type: static | dynamic | provider_query | generated_snapshot
  provider
  query
  symbols
  created_at
  updated_at
```

Snapshot contract:

```text
WatchlistSnapshot
  watchlist_snapshot_id
  watchlist_id
  generated_at
  symbols
  evidence
  provider_errors
  stale
```

Implementation note:

Current `UniverseSnapshot` is the migration source for WatchlistSnapshot.

## Deployment Contract

Deployment is a running Strategy publisher over selected Watchlists.

Minimum contract:

```text
Deployment
  deployment_id
  strategy_id
  strategy_version_id
  watchlist_ids
  subscribed_account_ids
  runtime_status
  runtime_overrides
  created_at
  updated_at
```

Deployment must not:

- own Account money
- own broker truth
- size final orders
- submit broker orders
- be duplicated per Account

## SignalPlan Contract

SignalPlan is a neutral trade or position-management plan emitted by a
Deployment.

Minimum contract:

```text
SignalPlan
  signal_plan_id
  deployment_id
  strategy_id
  strategy_version_id
  watchlist_snapshot_id
  symbol
  side
  intent
  status
  entry
  stop
  targets
  runner
  logical_exit
  related_position_lineage_id
  opening_signal_plan_id
  supersedes_signal_plan_id
  expires_at
  created_at
  published_at
  reason
  feature_snapshot
  warnings
```

Rules:

- `opening_signal_plan_id` is null for an opening plan.
- Related close/reduce/target/stop/trail/breakeven/runner/logical_exit plans
  must reference the opening SignalPlan or Position lineage.
- `targets` are lifecycle instructions, not separate trade ideas.
- `runner` is lifecycle management, not a separate position.
- `logical_exit` can close or reduce and must specify scope.

## SignalPlan Lifecycle Invariants

One opening SignalPlan represents one proposed Position lifecycle.

Lifecycle instructions inside that plan may become multiple order legs, but they
remain related to one opening SignalPlan and one Position lineage.

Required invariants:

- Targets, stops, runners, breakeven, trail updates, and logical exits never
  create unrelated Positions.
- Partial fills update remaining target and runner quantities proportionally or
  through an explicit recalculation rule.
- Superseded SignalPlans must point to the prior SignalPlan they replace.
- A close/reduce/target/stop/trail/breakeven/runner/logical_exit SignalPlan must
  reference either `opening_signal_plan_id` or `position_lineage_id`.
- Protective order replacement must preserve lineage.
- A full close marks the Position lineage closed only after BrokerSync confirms
  broker truth.
- A partial close/reduce never marks the Position lineage closed unless
  BrokerSync confirms zero remaining quantity.

## SignalPlan Entry

```text
SignalPlanEntry
  order_type: market | limit | stop | stop_limit
  limit_price
  stop_price
  time_in_force_preference
  extended_hours_preference
  entry_window
```

Important:

`time_in_force_preference` is not guaranteed executable. Broker-specific
capability validation happens later.

## SignalPlan Stop

```text
SignalPlanStop
  type: fixed | trailing | indicator | none
  stop_price
  trailing_amount
  trailing_percent
  rule
  required: true | false
```

## SignalPlan Target

```text
SignalPlanTarget
  label
  action: reduce | close
  quantity_pct
  price
  rule
  order_type_preference
```

Rules:

- Target quantity percentages must not exceed 100 percent combined with runner.
- Targets belong to the opening SignalPlan lifecycle.
- Targets may become internal order legs but not independent Positions.

## SignalPlan Runner

```text
SignalPlanRunner
  quantity_pct
  management: hold | trail | logical_exit | manual_review
  trail_rule
  logical_exit_rule
```

## SignalPlan Logical Exit

```text
SignalPlanLogicalExit
  rule
  action: close | reduce
  quantity_pct
  applies_to: full_position | runner | remaining_quantity
```

Example:

```text
rule: 5m.RSI_21 crosses_above 15m.RSI_21
action: close
applies_to: remaining_quantity
```

## Account Evaluation Contract

Account Evaluation is the Account-specific interpretation of one SignalPlan.

Minimum contract:

```text
AccountSignalPlanEvaluation
  evaluation_id
  account_id
  signal_plan_id
  deployment_id
  strategy_id
  status
  participation_decision
  risk_resolver_result
  governor_request
  governor_decision
  created_at
  evaluated_at
  rejection_reasons
  warnings
```

Participation decision:

```text
participate
ignore
reject
defer
requires_operator
```

Rules:

- Many Accounts can evaluate one SignalPlan differently.
- Account pause may block trading but must not block Account Trade Sync.
- Account Evaluation must identify whether a SignalPlan opens a new Position or
  manages an existing Position.

## RiskResolver Contract

RiskResolver computes Account-specific sizing and risk impact.

Minimum contract:

```text
RiskResolverResult
  account_id
  signal_plan_id
  allowed
  resolved_quantity
  resolved_notional
  max_loss
  stop_distance
  buying_power_required
  projected_exposure
  projected_concentration
  existing_position_context
  related_open_orders
  violations
  warnings
```

Rules:

- RiskResolver is the first place final Account quantity may appear.
- Strategy and SignalPlan may describe desired structure, but not final
  Account-specific quantity.
- RiskResolver evaluates the entire lifecycle, including targets and runner, as
  one proposed trade.

## Governor Request Contract

Governor is the final internal Account protection gate before OrderManager.

Minimum request:

```text
GovernorRequest
  account_id
  signal_plan_id
  deployment_id
  strategy_id
  intent
  resolved_quantity
  risk_resolver_result
  account_sync_state
  account_pause_state
  global_kill_state
  deployment_pause_state
  buying_power
  restrictions
  existing_positions
  open_orders
  daily_loss
  drawdown
  duplicate_execution_key
```

Minimum decision:

```text
GovernorDecision
  governor_decision_id
  account_id
  signal_plan_id
  status
  approved
  reasons
  violations
  warnings
  evaluated_at
```

Rules:

- No broker order reaches BrokerAdapter without Governor approval.
- Close/reduce/target/stop/trail/breakeven/runner/logical_exit still pass
  through Governor, but their risk interpretation differs from opening risk.

## Order Lineage Contract

Internal orders must link to SignalPlan and Position lineage.

Minimum additions to InternalOrder:

```text
strategy_id
strategy_version_id
deployment_id
signal_plan_id
opening_signal_plan_id
current_signal_plan_id
position_lineage_id
account_evaluation_id
governor_decision_id
leg_label
lifecycle_intent
```

Lifecycle intents:

```text
open
close
reduce
target
stop
trail
breakeven
runner
logical_exit
manual_operator
```

Manual orders:

- may have null Strategy/Deployment/SignalPlan lineage
- must still have Account id
- must still use Order Ledger
- must still route BrokerAdapter -> BrokerSync for broker truth

## Position Explanation Context

Every Account-owned Position must be explainable.

Minimum contract:

```text
PositionExplanationContext
  account_id
  position_lineage_id
  symbol
  side
  current_quantity
  average_entry
  current_market_value
  unrealized_pnl
  opening_signal_plan_id
  current_signal_plan_ids
  deployment_id
  strategy_id
  account_evaluation_ids
  governor_decision_ids
  order_ids
  fill_ids
  active_stop
  active_targets
  runner_state
  logical_exit_state
  sync_state
  unresolved_risks
  explanation_generated_at
```

Must answer:

- why the Position exists
- which SignalPlan opened it
- what Account risk rules applied
- what Governor decision approved it
- what related SignalPlans have been received
- which Orders and fills changed it
- whether sync state is fresh or stale

## Live Stock Market Data Stream Status

There is one shared Live Stock Market Data Stream for stocks.

Minimum contract:

```text
LiveStockMarketDataStreamStatus
  stream_id
  provider_id
  enabled_by_settings
  open
  connected
  authenticated
  status: open | connected | reconnecting | degraded | down | disabled
  subscribed_symbols
  consumer_ids
  last_message_at
  last_bar_at_by_symbol
  reconnect_count
  last_error
  started_at
```

Rules:

- It opens on backend app load when enabled.
- It remains open until backend app shutdown.
- It may have zero active symbol subscriptions.
- No component gets its own live stock stream.

## Account Trade Sync Status

There is one Account Trade Sync per validated Alpaca Account.

Minimum contract:

```text
AccountTradeSyncStatus
  account_id
  provider
  broker_mode
  enabled
  open
  connected
  authenticated
  status: open | connected | reconnecting | degraded | down | operator_paused | credentials_invalid
  last_event_at
  last_sync_write_at
  reconnect_count
  last_error
  started_at
  operator_paused_at
```

Rules:

- Starts after Account creation and credential validation.
- Starts at app load for every validated Alpaca Account.
- Stays open when trading is paused.
- Closes only on backend shutdown or explicit operator trade-sync pause.
- Routes broker events through BrokerSync before fan-out to subscribers.

## Alpaca Capability Preflight

Alpaca capability rules are provider-specific.

Minimum contract:

```text
BrokerCapabilityMatrix
  provider
  asset_class
  order_type
  time_in_force
  order_class
  extended_hours
  fractional_allowed
  short_allowed
  replace_supported
  cancel_supported
  supported
  reason_if_unsupported
```

Preflight request:

```text
BrokerOrderPreflightRequest
  account_id
  provider
  broker_mode
  asset_class
  symbol
  side
  quantity
  notional
  order_type
  time_in_force
  order_class
  extended_hours
  limit_price
  stop_price
```

Preflight result:

```text
BrokerOrderPreflightResult
  allowed
  violations
  warnings
  normalized_request
  operator_advisory
```

Rules:

- Known invalid Alpaca order shapes fail before broker submission.
- Core SignalPlan does not become Alpaca-specific.
- BrokerAdapter remains the provider boundary.

## Market Rule Preflight

Market rule preflight is separate from broker capability preflight.

Minimum request:

```text
MarketRulePreflightRequest
  account_id
  provider
  broker_mode
  symbol
  asset_class
  side
  quantity
  notional
  order_type
  time_in_force
  order_class
  extended_hours
  market_session
  market_clock
  asset_tradable
  asset_fractionable
  shortable
  easy_to_borrow
  halted
  buying_power
```

Minimum result:

```text
MarketRulePreflightResult
  allowed
  session_state
  violations
  warnings
  operator_advisory
```

Violation families:

```text
market_closed
extended_hours_unsupported
asset_not_tradable
asset_not_fractionable
asset_halted
short_not_allowed
not_easy_to_borrow
buying_power_insufficient
invalid_notional_quantity_combo
unsupported_asset_class_for_mode
```

## Phase 1 Required Tests

Contract tests to add before implementation is accepted:

- SignalPlan supports all canonical intents.
- SignalPlan does not contain final Account quantity.
- one SignalPlan can be evaluated by multiple Accounts.
- Accounts can accept/reject/size differently.
- RiskResolver is the first contract with final quantity.
- Governor rejection prevents OrderManager creation.
- Orders preserve SignalPlan and Position lineage.
- close/reduce SignalPlans reference opening SignalPlan or Position lineage.
- target legs do not become unrelated positions.
- Account Trade Sync stays open when Account trading is paused.
- Live Stock Market Data Stream can be open with zero subscriptions.
- Alpaca capability preflight rejects known unsupported order shapes.
- MarketRulePreflight rejects known invalid session/asset/account states.
- lint gate blocks Program lineage outside migration shims.
- runtime architecture test blocks new runtime composition roots without
  Coordinator approval.
- runtime tests prove paper/live are Account metadata, not separate runtime
  paths.
- BrokerSync boundary tests prove broker truth mutation stays in BrokerSync.

## Phase 1 Gate

Status: draft in progress

Gate to pass:

```text
Contracts are accepted when implementation can proceed without ambiguity about
SignalPlan neutrality, Account-specific sizing, Governor authority, order
lineage, stream ownership, and broker capability preflight.
```
