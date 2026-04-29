# Turtle Shell Guardrails

Operation: Turtle Shell
Purpose: prevent architecture drift while agents implement the Ultimate Trader backend.

## Prime Directive

Build the backend spine first.

Every change must support this flow:

```text
Strategy
-> Watchlist
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

If a change does not strengthen this flow, stop and document it as a blocker.

## Non-Negotiable Rules

1. No frontend work.
2. No new runtime root.
3. No separate paper runtime.
4. No separate live runtime.
5. No Program as an active product concept.
6. No ExecutionIntent as the forward runtime spine.
7. No Account Governor naming.
8. No Services Center naming.
9. No broker truth writes outside BrokerSync.
10. No broker submit/cancel outside BrokerAdapter.
11. No direct provider calls from frontend or feature code.
12. No component-owned live stock market stream.
13. No AI mutation of account, broker, order, trade, or position truth.
14. No order without SignalPlan lineage, except explicit manual operator orders.
15. No position without Account ownership and explanation context.

## Runtime Composition Root Rule

There must be one runtime composition root.

That root owns:

* Deployment startup and shutdown
* SignalPlan publication
* Account fan-out
* Account Evaluation creation
* RiskResolver invocation
* Governor invocation
* OrderManager handoff
* runtime status projection

Forbidden without approval:

* new runtime entrypoint
* new orchestrator owning order flow
* new broker runtime loop by paper/live mode
* new per-component live stock stream
* runtime shortcut from signal to order

## SignalPlan Rule

SignalPlan is neutral.

Must NOT contain:

* final Account quantity
* broker order id
* Governor approval

Final quantity begins only at RiskResolver.

## Account Evaluation Rule

Each Account evaluates the same SignalPlan independently.

Accounts may:

* accept
* reject
* defer
* size differently

## RiskResolver Rule

First boundary that computes final quantity.

## Governor Rule

Final protection gate.

No order reaches BrokerAdapter without approval.

## Order Lineage Rule

Every order must link to:

* account_id
* strategy_id
* deployment_id
* signal_plan_id
* position_lineage_id

## Multi-Leg Lifecycle Rule

One trade idea = one SignalPlan lifecycle.

Targets, stops, runner = lifecycle, not new trades.

## Broker Boundary Rule

* BrokerAdapter submits
* BrokerSync writes truth

No other component writes broker truth.

## Market Data Rule

One shared Live Stock Market Data Stream.

No component-specific streams.

## Account Trade Sync Rule

One trade sync per Account.

Must stay open even if trading is paused.

## Research Systems Rule

Research (Chart Lab, Backtest, Sim Lab):

* produce evidence
* do NOT trade
* do NOT bypass SignalPlan

## AI Rule

AI is advisory only.

Cannot:

* submit orders
* modify positions
* override Governor

## Naming Rules

Allowed:

* Strategy
* SignalPlan
* Account
* Governor
* Order
* Position

Banned:

* Program
* Services Center
* Paper Runtime

## Agent Start Checklist

Must read:

1. HANDOFF_PROTOCOL.md
2. OPERATION_STATUS.md
3. BACKEND_LOCKDOWN_AGENT_PLAN.md
4. BACKEND_REALITY_MAP.md
5. NEXT_IMPLEMENTATION_SEQUENCE.md
6. TURTLE_SHELL_GUARDRAILS.md
7. DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md

Before coding, identify the bounded context that owns the change. If ownership
is unclear, stop and document a blocker in `OPERATION_STATUS.md`.

## Agent End Checklist

Must update OPERATION_STATUS.md with:

* completed
* next action
* files touched
* tests run

## Test Discipline

After each change:

* run tests
* do not proceed if failing

## Broker Test Discipline

Broker-facing tests must use an already configured Broker Service or the
frontend-configured Broker Account.

Allowed:

* configured Alpaca Broker Service
* configured Alpaca Broker Account
* explicit test order submission when the test is intentionally validating
  order flow, BrokerAdapter behavior, BrokerSync truth, broker rejection, or
  operator advisory behavior

Required:

* use the Account's configured provider, mode, credentials, and broker metadata
* route broker calls through BrokerAdapter and BrokerSync boundaries
* make submitted test orders clearly identifiable by test client order id,
  test notes, or equivalent lineage metadata
* record the command, account, broker mode, and result in the test output or
  operation status when a real broker order is submitted

Forbidden:

* ad hoc broker credentials in tests
* direct Alpaca calls from test-only shortcuts that bypass BrokerAdapter
* fake paper/live runtimes created only for tests
* hidden live broker side effects

## Blocker Rules

Stop if:

* second runtime appears
* ExecutionIntent extended
* broker truth written outside BrokerSync
* private data stream created

## Final Warning

Do not make a second runtime.

Do not hide broker truth.

Do not extend ExecutionIntent.

Build the spine first. Everything else hangs from it.
