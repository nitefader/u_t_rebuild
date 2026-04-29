# Runtime Ship Gate

Run this gate before trusting Ultimate Trader with broker-connected operation.

## Required Checks

- Backend starts with intended runtime database.
- Live Stock Market Data Stream status is visible.
- Every configured Account shows Account Trade Sync status.
- Failed streams show explicit errors.
- Global kill state is visible and restart-safe.
- Account pause blocks new opens but does not hide Account Trade Sync.
- Deployment pause blocks new opens from that Deployment.
- Broker sync freshness is visible per Account.
- No Account with stale or unknown sync can open new positions.
- Opening SignalPlans are idempotent per Account.
- Related close/reduce SignalPlans are linked to the Account position lineage.
- Position detail explains signal lineage, decision trace, orders, fills, current
  exposure, and risk.
- Manual orders are Account-specific and audited.
- AI explanation is advisory only.

## Validation Commands

```powershell
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests -q
npm.cmd run build --prefix frontend
npm.cmd test --prefix frontend
```

## Stop Ship

Stop immediately if:

- broker mode is ambiguous
- Account Trade Sync is down without an operator-visible error
- Market Data Stream is down without an operator-visible error
- broker sync is stale or unknown
- order or position lineage is missing
- Governor can be bypassed
- BrokerSync can be bypassed for broker truth
- Chart Lab, Sim Lab, Backtest, or AI can submit real orders
- partial close SignalPlans are treated as full flatten
- UI hides a mission-critical failure
