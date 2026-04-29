# Backend Three-Pass Iteration Review

Operation: Turtle Shell

Reviewed at: 2026-04-27 03:40:47 -04:00

Status: completed

Purpose: iterate through backend needs three times before declaring the Account
sync and Operations readiness slice stable.

## Pass 1: Broker And Account Truth

Lens:

- Account snapshots
- open broker orders
- open positions
- BrokerSync freshness
- per-Account trade sync

Findings:

- BrokerSync now polls Account snapshot, positions, and open orders during
  reconcile.
- BrokerSync now persists Account snapshots, broker open orders, broker
  positions, and freshness into the runtime store.
- Position update stream events now persist broker position snapshots before
  fan-out.
- Account Trade Sync stays per Account and uses BrokerSync before subscribers
  receive events.

Decision: pass.

## Pass 2: Runtime Spine And Domain Boundaries

Lens:

- one runtime composition root
- StrategyVersion ownership
- Deployment-owned SignalPlan emission
- Account-specific evaluation
- BrokerAdapter and BrokerSync boundaries

Findings:

- Direct Alpaca trading calls are contained inside the Alpaca broker adapter.
- Manual and automated order paths use BrokerAdapter for submit/cancel.
- Broker truth writes remain behind BrokerSync/runtime store read models.
- StrategyVersion rejects Account, risk, universe, watchlist, and runtime
  ownership fields.
- Program/ExecutionIntent references remain as migration shims and legacy test
  fixtures, not the forward runtime spine.
- DeploymentPositionManager is read-only and scans positions by deployment id.

Decision: pass.

## Pass 3: Operations And API Readiness

Lens:

- Operations account overview
- Account detail API payloads
- open position visibility
- open order visibility
- operator-readable naming

Findings:

- Operations overview exposes broker Account summaries, open broker order
  counts, position counts, sync state, and latest broker sync timestamp.
- Account operations detail exposes Account snapshot, sync freshness, open
  broker orders, internal order summary, and persisted broker positions.
- Frontend-required schemas are covered by backend response models.
- Cleaned one stale docstring that described Operations as broker-paper
  operations; it now uses Account runtime operations.

Decision: pass.

## Remaining Backend Needs

1. Keep retiring Program/ExecutionIntent migration shims after production
   readiness paths no longer depend on them.
2. Add Account-level advisory copy for Alpaca margin and account restriction
   fields now preserved in `BrokerAccountSnapshot`.
3. Add a live endpoint smoke check after backend restart using the configured
   Alpaca Account:

```text
GET /api/v1/operations/overview
GET /api/v1/operations/accounts/{account_id}
GET /api/v1/system/streams
```

4. If live Account positions still do not appear after a fresh BrokerSync poll,
   compare:

```text
BrokerAdapter.get_positions(account_id)
SQLiteRuntimeStore.list_broker_position_snapshots(account_id)
GET /api/v1/operations/accounts/{account_id}
```

## Approval

Coordinator approval: pass.

Nanyel doctrine check:

- one runtime maintained
- paper/live remain Account metadata
- BrokerAdapter remains broker submission boundary
- BrokerSync remains broker truth writer
- Operations remains read-only projection plus operator controls
