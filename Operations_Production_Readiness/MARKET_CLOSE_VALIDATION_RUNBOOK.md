# Market Close Validation Runbook

Last updated: 2026-04-27 13:05:17 -04:00

Purpose: get Ultimate Trader ready for a credible same-day strategy validation
before market close without bypassing the production architecture.

## Executive Objective

Validate that the platform can support a disciplined quant workflow today:

1. Broker Accounts stay synchronized.
2. Market Data Stream is running on the configured stock data feed.
3. Historical datasets are visible and queryable.
4. Strategy and StrategyVersion can be created without owning Account risk or
   universe/watchlist truth.
5. Research evidence can be recorded and surfaced in Operations.
6. No research workflow trades or bypasses BrokerAdapter, BrokerSync,
   RiskResolver, Governor, or the Order Ledger.

## Current Validated Artifact

Strategy:

- `Market Close Validation - SPY Momentum Smoke`
- `strategy_id`: `b928618f-78ec-48c2-80ca-22fbe02dfae0`

StrategyVersion:

- `SPY 1m momentum smoke v1`
- `strategy_version_id`: `4dc3f3d8-60e3-4764-8940-da9e6da1b290`
- Entry rule: SPY 1m close above VWAP and positive 5-bar return.
- Exit rule: SPY 1m close below VWAP.
- No Account risk, Account money, universe, watchlist, broker credentials, or
  final quantity is owned by the StrategyVersion.

Research evidence:

- `backtest_run_id`: `6ae443c6-1f11-4226-bfff-74ce109bd1e2`
- Dataset reference: `spy_1m_alpaca_sip`
- Status: recorded.

Important limitation:

- The V1 Backtest API currently records research evidence. It does not yet
  execute the full historical engine. Treat this as API/readiness validation,
  not performance proof.

## Current System State

Validated at 2026-04-27 13:05:17 -04:00:

- Backend running on `http://127.0.0.1:8000`.
- Alpaca endpoint: paper.
- Alpaca data feed: SIP.
- Market Data Hub: `alpaca / stock / sip`, connected.
- Account Trade Sync: running for both configured Alpaca Broker Accounts.
- Operations overview: healthy, no stale sync accounts.
- Open broker orders: 0.
- Open positions: 5 on `OtijiTrader - Paper 1`.
- Research evidence summary includes one `backtest_run`.

## Fixes Applied During Readiness Pass

1. Alpaca stream status compatibility:
   - Alpaca emitted `partial_fill`.
   - Adapter now maps both `partial_fill` and `partially_filled` to
     `BrokerOrderStatus.PARTIAL_FILL`.

2. Operations projection stability:
   - Manual operator orders have no Deployment lineage by design.
   - Operations now filters nullable deployment ids before building deployment
     summaries.

3. Strategy persistence schema hardening:
   - Live database had an older incompatible `strategies` table.
   - Strategy repository now archives incompatible legacy tables and recreates
     the canonical Strategy table shape.

## Tests Run

- `python -m pytest backend\tests\unit\operations\test_operations_center_service.py backend\tests\unit\api\test_operations_routes.py backend\tests\unit\brokers\test_alpaca_broker_adapter.py backend\tests\unit\brokers\test_broker_sync_reconciliation.py -q`
  - 75 passed.
- `python -m pytest backend\tests\unit\strategies\test_strategy_service.py backend\tests\unit\api\test_frontend_api_contract.py -q`
  - 12 passed.
- `python -m pytest backend\tests\unit -q`
  - 1110 passed.
- `npm.cmd run typecheck`
  - passed.
- `npm.cmd test`
  - 43 passed; banned-name lint clean.
- `npm.cmd run build`
  - passed; Vite chunk-size warning only.

## Next Two-Hour Execution Plan

1. Use the Strategy page to inspect the validation Strategy and Version.
2. Use Data Center to inspect `spy_1m_alpaca_sip` bars.
3. Use Backtests to confirm the recorded research evidence appears.
4. Use Operations to confirm:
   - Account sync stays fresh.
   - Market Data Hub stays connected.
   - Trade streams stay open.
   - Positions and open orders match broker truth.
5. Do not promote, deploy, or automate trading from this research evidence yet.
6. Next backend build slice: wire the real historical backtest executor behind
   the research create-run API using the shared Feature Engine and SignalPlan
   path.

## Approval Status

Readiness path is approved for operator validation.

Not approved yet for performance claims or automated trading promotion.
