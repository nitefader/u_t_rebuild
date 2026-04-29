# Next Build Plan

The next implementation work must reconcile the codebase to the simplified
Ultimate Trader architecture.

## Phase 1: Contracts

Define backend contracts for:

- SignalPlan
- SignalPlan intent
- SignalPlan lineage
- Account decision trace
- Account-owned position explanation context
- related close/reduce SignalPlan handling

Exit gate:

- tests prove opening, partial close, full close, target, stop, and logical-exit
  SignalPlans have explicit intent and lineage.

## Phase 2: Account Subscription Runtime

Move toward:

```text
Deployment publishes SignalPlans
-> subscribed Accounts evaluate independently
-> each Account creates its own order only if approved
```

Exit gate:

- one Deployment can publish one SignalPlan to multiple Accounts
- Accounts can accept/reject differently
- orders remain Account-specific

## Phase 3: Account Trade Sync Always On

Ensure one Account Trade Sync starts for every configured Account at startup,
even when paused or not subscribed to a Deployment.

Exit gate:

- Operations shows sync status per Account
- failures are explicit

## Phase 4: Live Stock Market Data Stream

Ensure the platform live stock data stream starts at app startup when enabled.

Exit gate:

- Operations shows stream status, provider, stale/fresh, last error, reconnects
- no duplicate per-Account market data streams

## Phase 5: Operator Cleanup

Clean UI language:

- Accounts, not broker maze
- Providers with Market Data Providers and AI Providers only
- Settings reduced to meaningful platform preferences
- Operations owns runtime controls and status

Exit gate:

- no active UI text says Services Center, Account Governor, or Paper Runtime as
  a separate product path.
