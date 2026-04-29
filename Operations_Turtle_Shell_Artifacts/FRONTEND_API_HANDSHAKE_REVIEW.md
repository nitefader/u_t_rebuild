# Frontend API Handshake Review

Operation: Turtle Shell

Reviewed at: 2026-04-27 03:47:42 -04:00

Status: completed

Purpose: verify the frontend API clients and Zod schemas match backend routes
and response contracts.

## Surfaces Reviewed

- Accounts: `/api/v1/broker-accounts`
- Operations: `/api/v1/operations`
- System: `/api/v1/system`
- Market Data Providers: `/api/v1/market-data/services`
- AI Providers: `/api/v1/ai/providers`
- Chart Lab: `/api/v1/chart-lab`
- Strategies: `/api/v1/strategies`
- Watchlists: `/api/v1/watchlists`
- Deployments: `/api/v1/deployments`
- Data Center historical datasets: `/api/v1/data-center/historical-datasets`
- Research run evidence APIs:
  - `/api/v1/backtests`
  - `/api/v1/sim-lab/sessions`
  - `/api/v1/optimization/runs`
  - `/api/v1/walk-forward/runs`

## Findings

### Pass

- Every currently called frontend HTTP route is registered in FastAPI through
  `backend/tests/unit/api/test_frontend_api_contract.py`.
- Chart Lab WebSocket route is registered.
- Account Operations schema includes Account snapshot, BrokerSync freshness,
  open broker orders, internal order ledger summary, and broker positions.
- System stream schema supports one shared stock market-data hub plus per-Account
  trade streams.
- Research run API surfaces are registered and evidence-backed.

### Fixed

- Frontend market-data service delete expected a `MarketDataServiceRecord`, but
  backend returns `MarketDataServiceDeletionResponse`.
- Added `MarketDataServiceDeletionResponseSchema`.
- Updated `MarketDataProvidersApi.delete(...)` to parse the deletion response.
- Added frontend API handshake tests proving the delete response is not parsed
  as a service record.
- Added backend assertion for the market-data delete response message.

## Verification

```text
python -m pytest backend\tests\unit\api\test_frontend_api_contract.py backend\tests\unit\api\test_market_data_delete_route.py backend\tests\unit\api\test_research_run_routes.py -q
Result: 10 passed, 5 warnings

npm.cmd test
Result: 13 passed; frontend banned-name lint clean

npm.cmd run build
Result: passed; Vite chunk-size warning only

python -m pytest backend\tests\unit -q
Result: 1103 passed, 6 warnings
```

## Decision

Pass.

The known frontend API mismatch found in this pass is fixed and covered by
tests. No backend route gap remains for the current frontend API client surface.

## Next Backend/API Needs

1. Add live smoke verification after backend restart against:
   - `/api/v1/operations/overview`
   - `/api/v1/operations/accounts/{account_id}`
   - `/api/v1/system/streams`
2. Keep `test_frontend_api_contract.py` updated whenever a frontend API client
   adds a new route.
3. Add route-level response fixture tests for high-risk pages:
   - Accounts
   - Operations
   - Deployments
   - Providers
4. Keep frontend provider schemas as read-model schemas only. No direct Alpaca,
   Yahoo, or AI provider calls from frontend code.
