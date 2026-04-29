# Frontend API Contract Audit

Last updated: 2026-04-27 02:36:00 -04:00

Purpose: ensure the active `frontend/` application has the backend API
surface it currently calls, and identify the remaining product APIs needed
before the research pages become fully interactive.

## Decision

Current frontend contract: PASS.

The active `frontend/src/api` client calls are registered in FastAPI.

## Verified Current Frontend API Surface

The current frontend has backend routes for:

- System status, streams, and settings
- Broker Accounts list/create/update credentials/delete
- Operations overview, Account detail, Deployment controls, global controls,
  and research evidence reads
- Market Data Providers
- AI Providers
- Chart Lab health and WebSocket stream
- Strategies and StrategyVersions
- Watchlists and snapshots
- Deployments and Account subscriptions

Backend guardrail added:

```text
backend/tests/unit/api/test_frontend_api_contract.py
```

This test fails if the current frontend client calls an API method/path that
FastAPI does not register.

## Product APIs Still Missing

These are not blockers for the current frontend build because the pages are
read-only evidence surfaces today. They are blockers for full interactive
research workflows:

- `/api/v1/backtests`
- `/api/v1/backtests/{id}`
- `/api/v1/backtests/{id}/cancel`
- `/api/v1/sim-lab/sessions`
- `/api/v1/sim-lab/sessions/{id}`
- `/api/v1/sim-lab/sessions/{id}/run`
- `/api/v1/sim-lab/sessions/{id}/results`
- `/api/v1/optimization/runs`
- `/api/v1/optimization/runs/{id}`
- `/api/v1/walk-forward/runs`
- `/api/v1/walk-forward/runs/{id}`

Nanyel rule: these must produce research evidence and must not become
alternate live runtimes.

## Verification

```text
npm.cmd run typecheck
-> passed

npm.cmd test
-> 10 passed; banned-name lint clean

python -m pytest backend\tests\unit\api -q
-> 80 passed, 5 warnings

python -m pytest backend\tests\unit\api\test_frontend_api_contract.py -q
-> 2 passed, 5 warnings
```

## Next Backend API Priority

Implement research run APIs in this order:

1. Backtests
2. Sim Lab sessions
3. Optimization runs
4. Walk-Forward runs

Each route must call the unified Feature Engine / Signal Engine /
RiskResolver / Governor contracts where applicable, and must store/query
research evidence instead of trading.
