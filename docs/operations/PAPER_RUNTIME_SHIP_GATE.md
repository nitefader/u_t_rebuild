# Paper Runtime Ship Gate

Use this checklist before any real Alpaca paper trading session.

## Required Checks

- Backend boot check: start the backend with the intended `OPERATIONS_RUNTIME_DB_PATH`; verify no startup recovery errors.
- Frontend build check: run `cd frontend && npm run build`.
- Operations endpoint smoke check: call `GET /api/v1/operations/overview` and confirm broker accounts, deployments, kill state, and sync timestamps render.
- Global kill restart check: activate global kill, restart or rehydrate the backend, confirm `global_kill_active=true`, and confirm new opens are blocked.
- Account pause/resume check: pause one broker account, confirm only that account blocks new opens, then resume.
- Deployment pause/resume check: pause one deployment, confirm only that deployment blocks new opens, then resume.
- Credential replacement validation check: replace Alpaca paper credentials only while the account is paused; confirm masked values are rejected and secrets are never displayed.
- Account deletion safety check: confirm deletion is blocked for running deployments, open orders, open positions, stale sync, or unknown sync; historical accounts must archive.
- Order detail inspection check: open an order detail from account or deployment detail and verify internal truth, broker mapping truth, and fill truth are separated.
- Broker sync freshness check: confirm stale/unknown sync is visible and blocks runtime opens.
- Alpaca paper credential validation check: verify the account mode is `BROKER_PAPER`; any mode mismatch is stop-ship.
- Runtime `run_once` check: run a deterministic completed bar through the paper runtime and confirm no duplicate order submission on restart.

## Full Validation Commands

```powershell
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests/unit/runtime -q
python -m pytest backend/tests/unit/control_plane -q
python -m pytest backend/tests/unit/operations -q
python -m pytest backend/tests/unit/brokers -q
python -m pytest backend/tests/unit/orders -q
python -m pytest backend/tests -q
cd frontend
npm run build
npm test
```

## Rollback Procedure

1. Activate global kill.
2. Pause the affected broker account and deployments.
3. Stop the paper runtime process.
4. Preserve the runtime SQLite database and backend logs.
5. Revert the deployment to the last known-good commit.
6. Restart backend/frontend and verify Operations overview still reports global kill active before clearing it.

## Stop-Ship Conditions

- Global kill does not survive restart.
- Broker sync is stale, unknown, or missing.
- Account mode is not explicitly `BROKER_PAPER`.
- Credential replacement accepts masked secrets or silently changes active runtime credentials.
- Account deletion can orphan orders, trades, broker mappings, deployments, or audit history.
- Order detail shows broker state as safe when mapping or sync is unknown.
- Any backend or frontend validation command fails.
