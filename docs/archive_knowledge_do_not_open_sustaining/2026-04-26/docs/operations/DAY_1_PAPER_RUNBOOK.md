# Day-1 Paper Trading Runbook

## Pre-Market

- Confirm the backend uses the intended runtime database.
- Run the Paper Runtime Ship Gate validation commands.
- Open Operations Center and verify global kill is inactive only after all checks pass.
- Confirm every active deployment is `BROKER_PAPER`.
- Confirm broker sync freshness is current for each account.

## Credential Verification

- Validate Alpaca paper credentials from Operations Center.
- Never paste masked credentials into replacement fields.
- If credentials are replaced, keep the account paused until broker sync succeeds.
- Confirm UI never displays saved secret values.

## Account And Deployment Readiness

- Confirm account mode, equity, buying power, open orders, positions, and sync timestamps.
- Confirm target deployments are running only after recovery is complete.
- Confirm account pause, deployment pause, and global kill buttons are visible.
- Confirm stale sync warnings are absent.

## Market Open Observation

- Watch the Operations overview during the first completed bars.
- Confirm last runtime event and last broker sync timestamps advance.
- Inspect every new internal order before trusting the session state.
- Treat unknown broker mapping or stale sync as unsafe.

## Order Detail Procedure

1. Open account or deployment detail.
2. Click the order detail control.
3. Verify internal order id, client order id, account, deployment, program, symbol, side, quantity, filled quantity, intent, status, and timestamps.
4. Verify broker mapping shows broker order id and broker status, or clearly says unknown/stale.
5. Verify fill truth is listed separately from internal order truth.

## During Session

- Monitor broker sync freshness, open orders, positions, latest runtime events, and latest governor decisions.
- Use account pause for account-specific risk.
- Use deployment pause for one strategy/runtime instance.
- Use global kill for any platform-wide uncertainty.
- Do not clear global kill until restart persistence and sync freshness are verified.

## Emergency Controls

- Account pause: blocks new opens for one broker account.
- Deployment pause: blocks new opens for one deployment only.
- Global kill: blocks all new opens and must survive restart.
- Flatten controls may report unsupported/not ready; do not assume a flatten occurred without explicit result detail.

## End Of Day

- Pause deployments or stop runtime.
- Confirm no unexpected open orders.
- Confirm positions match the intended paper session state.
- Capture Operations overview, account detail, deployment detail, and any order detail panels for orders submitted.
- Save backend logs and runtime database snapshot.

## Success Criteria

- No live account is used.
- All orders are created by OrderManager, submitted by BrokerAdapter, and reconciled by BrokerSync.
- Broker sync remains current.
- Operators can explain every open order from the order detail panel.

## Stop Runtime Immediately

- Global kill does not block new opens.
- Account mode is live or unknown.
- Broker sync is stale or unknown.
- Credential replacement happens while an account is actively trading.
- Broker mapping is missing for submitted orders and does not recover.
- UI, API, or tests report unsafe or ambiguous state.
