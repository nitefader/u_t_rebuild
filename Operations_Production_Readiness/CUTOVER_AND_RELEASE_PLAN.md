# Cutover And Release Plan

This is how the rebuilt Ultimate Trader goes from local dev to paper
to live. It is rehearsed end-to-end on paper before any live Account
is enabled.

## Phases

1. **Local readiness** — full test suite green; banned-name lint
   clean; architecture guardrail clean; backend + frontend build
   clean.
2. **Paper readiness** — Day Zero Runbook executes on a paper-mode
   Account against Alpaca paper or fakepaca; Operations Center shows
   the full SignalPlan → Position lineage with explanations.
3. **Live cutover** — operator-driven; one Account at a time; one
   Deployment at a time; rollback is account-pause + global kill.

## Local readiness checklist

Run, in order:

```powershell
# from repo root
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests -q
npm.cmd run build --prefix frontend
npm.cmd test --prefix frontend
```

All four must pass with no warnings about banned imports / banned
names / missing migrations. If any fails, the build is not local-
ready.

Additional local checks:

- `python -m pytest backend/tests/unit/lint -q` — guardrails.
- `node frontend/scripts/lint-banned-names.mjs` — UI banned-name
  scan.
- `python -m pytest backend/tests/integration -q` — broker-safe
  with `UTOS_BROKER_SAFE_E2E=1` only when intentional.

## Paper readiness checklist

Run on a freshly initialized SQLite runtime DB pointed at a paper
Alpaca Account:

1. Backend boots with `UTOS_ENVIRONMENT=paper`. Logs show
   `stream bootstrap: started=N skipped=M seen=N`.
2. `GET /api/v1/system/streams` reports live stock market data hub
   `running=true`, no error; per-Account trade dispatcher
   `is_running=true`.
3. `GET /api/v1/system/status` reports Alpaca credentials present
   and the chosen feed.
4. Create a Strategy with a known-firing entry rule and a known
   stop. Freeze a version.
5. Create a Watchlist with one liquid symbol (`AAPL`). Snapshot it.
6. Create a Deployment subscribed to the paper Account. Start it.
7. Operations Center shows the running Deployment, recent SignalPlans
   (or empty with a clear "waiting" status), per-Account decisions,
   open orders, open positions, sync freshness.
8. Once the entry rule fires (or via a test trigger in CI):
   - SignalPlan persisted with full lineage.
   - AccountSignalPlanEvaluation persisted.
   - GovernorDecisionTrace persisted.
   - InternalOrder created with full lineage columns.
   - BrokerAdapter submits to Alpaca paper.
   - BrokerSync writes the fill back.
   - PositionLineage created and explainable.
9. `GET /api/v1/broker-accounts/{id}/positions/{lineage_id}/explain`
   returns a complete `PositionExplanationContext`.
10. AI advisory `Explain this position` returns a copyable summary;
    the response is clearly labeled "Advisory only".

If any of the ten steps fails, the slice that owns it is reopened.

## Production checklist (per live Account)

1. Confirm Account credentials are stored encrypted (not in `.env`).
2. Confirm Account is paused at the moment of cutover; the Account
   Trade Sync is connected.
3. Confirm Live Stock Market Data Stream is running.
4. Confirm the Strategy version is frozen.
5. Confirm the Promotion gate evaluates the Strategy version + paper
   Deployment evidence as `eligible=true`.
6. Confirm Governor policy is operator-reviewed (max open positions,
   exposure caps, daily loss cap, drawdown cap).
7. Confirm the Account risk config matches operator intent.
8. Confirm Account restrictions (symbol blocks, time-of-day blocks)
   are correct.
9. Subscribe the live Account to the live Deployment.
10. Start the live Deployment.
11. Resume the Account.
12. Watch the first SignalPlan all the way through Position lineage
    in Operations.
13. Stay attached for at least one full session window; do not leave
    the room while the first live position opens.

## Rollback

Order of preference, fastest first:

1. **Account pause** — blocks new opens for that Account; existing
   protective legs continue. `POST /api/v1/operations/accounts/{id}/pause`.
2. **Deployment pause** — blocks all new opens from that Deployment
   for all subscribed Accounts. `POST /api/v1/operations/deployments/{id}/pause`.
3. **Global kill** — blocks the whole platform. `POST /api/v1/operations/global/kill`.
4. **Flatten Account** — explicit operator action; sends close
   orders for all open positions on that Account.
   `POST /api/v1/operations/accounts/{id}/flatten`.
5. **Flatten Deployment** — close every position the Deployment
   originated, across all subscribed Accounts.
   `POST /api/v1/operations/deployments/{id}/flatten`.
6. **Code rollback** — git revert the offending PR; redeploy backend.
   Persistence stays untouched.

Pause does not flatten. Flatten is always explicit.

## Environment variables

Required:

- `UTOS_ENVIRONMENT` — `paper` | `live`. Controls dotenv override
  semantics and a few logging surfaces. Default: `paper`.
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` — only used for the
  fakepaca / dev-mode stream when no Account-level credential is
  set; in production every Account stores its own credential
  encrypted.
- `ALPACA_BASE_URL` — paper / live derived from broker mode at
  Account creation; this env var is dev-only.
- `UTOS_API_KEY` — optional; when set, all `/api/v1` requests must
  include `X-UTOS-API-Key`.
- `UTOS_RUNTIME_DB_PATH` — path to the SQLite runtime DB (must be
  writeable and on durable storage; not `tmp`).
- `UTOS_CREDENTIAL_KEY` — symmetric key for `BrokerCredentialStore`
  AES-GCM. Must be 32 bytes base64. Rotate via `BrokerCredentialStore`
  re-encrypt path.

Forbidden in production:

- `.env` overriding host environment when `UTOS_ENVIRONMENT` is
  `production` / `prod` / `live` (already enforced in
  `backend/app/api/server.py`).
- Any env var that names a runtime path (banned product term).

## Secrets

- Broker credentials live only in the encrypted
  `BrokerCredentialStore`.
- AI provider credentials live only in the AI runtime store.
- Market data credentials live only in the market-data services
  store.
- Logs must never write secrets, even on error. Add a redacting
  formatter if missing.
- Backups of the SQLite runtime DB include encrypted credentials —
  store backups in the same security tier as the live DB.

## Runtime startup order

1. Apply schema migrations (idempotent CREATE-IF-NOT-EXISTS).
2. Apply Program → Strategy/Deployment migration if needed; refuse
   to start if migration is required and not performed.
3. Boot `runtime_context`: hub registry, trade dispatcher registry,
   manual trade composition.
4. Eagerly start trade dispatchers per Account (existing behavior).
5. Eagerly start the live stock market data hub.
6. Start the Deployment supervisor — but only Deployments marked
   ACTIVE in the persisted state auto-resume.
7. Health-check loop begins.

## Monitoring

For V1, in-app monitoring lives in the Operations Center. External
monitoring is optional but recommended:

- **Process liveness** — backend `/api/v1/system/status` 200.
- **Stream liveness** — `is_running` for live stock market data
  hub; `is_running` per Account trade dispatcher.
- **Sync freshness** — broker_sync_freshness `is_stale=false` for
  every Account.
- **Order rejection rate** — count of internal orders with status
  REJECTED / FAILED in the last 15 minutes.
- **Governor reject rate by reason** — top reasons in the last
  hour.
- **SignalPlan emission rate** — sanity check.
- **Critical runtime errors** — last error per Deployment, per
  Account.

If a third-party monitor is wired in, it must read these from the
existing API; no parallel telemetry pipeline.

## Operator runbook (Day Zero alignment)

The Day Zero Runbook in `docs/operations/DAY_ZERO_RUNBOOK.md` is the
canonical operator playbook. The cutover plan above is consistent
with it. If any step here drifts from the runbook, update both.

Key operator actions during cutover:

- Verify status badge in nav reads `Alpaca · Paper · IEX` (or the
  intended feed).
- Open Operations and Accounts in two windows; do not close them
  while the first live position opens.
- Keep `Explain this position` open on the first opened position;
  copy the explanation context to a notebook for the post-cutover
  review.
- After the first live close, reconcile fills with the broker's
  trading log out-of-band.

## Stop-ship triggers

Per `docs/operations/RUNTIME_SHIP_GATE.md`, do not proceed with live
cutover if any of these are true:

- broker mode is ambiguous;
- Account Trade Sync is down without operator-visible error;
- Live Stock Market Data Stream is down without operator-visible
  error;
- broker sync is stale or unknown;
- order or position lineage is missing;
- Governor can be bypassed;
- BrokerSync can be bypassed for broker truth;
- Chart Lab / Sim Lab / Backtest / AI can submit real orders;
- partial close SignalPlans are treated as full flatten;
- UI hides a mission-critical failure.

This list is non-negotiable.
