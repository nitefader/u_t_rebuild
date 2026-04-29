# Testing And Acceptance Plan

## Test pyramid

1. **Unit** — domain contracts, single-service behavior, pure
   functions. Currently 82 backend test files; expand for new
   services.
2. **Integration** — multi-service flows inside the backend (e.g.
   DeploymentPublisher → AccountEvaluator → RiskResolver → Governor
   → OrderManager → BrokerSync). No real broker.
3. **Frontend** — Node test runner per page, plus banned-name lint.
4. **Broker-safe E2E** — Alpaca paper or fakepaca test stream only.
   No live Account in CI.
5. **Simulation regression** — historical replay against the rebuilt
   spine produces deterministic SignalPlans, evaluations, decisions,
   orders.
6. **Smoke** — runtime smoke on a paper Account (already present); extend with
   SignalPlan smoke.
7. **Production smoke** — Day Zero Runbook on a paper Account before
   any live cutover.

## Backend unit tests (additions required)

Per slice, in alignment with [PRODUCTION_READINESS_EXECUTION_PLAN.md](./PRODUCTION_READINESS_EXECUTION_PLAN.md):

- `backend/tests/unit/persistence/test_sqlite_persistence.py`:
  round-trip and indexes for new tables.
- `backend/tests/unit/strategies/test_strategy_service.py`,
  `test_watchlist_service.py`.
- `backend/tests/unit/deployments/test_deployment_service.py`.
- `backend/tests/unit/runtime/test_deployment_publisher.py`:
  - emits opening SignalPlan from Watchlist when entry rule fires;
  - emits position-management SignalPlan from Account-owned
    Positions filtered by `deployment_id`;
  - never emits exit from Watchlist or entry from Position;
  - idempotent per `(deployment_id, evaluation_tick, symbol,
    intent)`;
  - paused / blocked Deployments emit nothing.
- `backend/tests/unit/decision/test_account_evaluator.py`:
  - one SignalPlan, two Accounts, two distinct evaluations;
  - PARTICIPATE / IGNORE / REJECT / DEFER paths each persist;
  - idempotent per `(account_id, signal_plan_id)`;
  - re-evaluation on resume does not double-submit.
- `backend/tests/unit/risk_resolver/test_risk_resolver_contract.py`
  (extend): fixed-shares, fixed-dollar, risk-percent equity,
  fractional vs whole-share rounding, broker capability filter.
- `backend/tests/unit/governor/test_portfolio_governor.py` (rewrite):
  consumes SignalPlan + RiskResolverResult + AccountContext, emits
  GovernorDecisionTrace; every reject reason and every approve path
  has a test.
- `backend/tests/unit/orders/test_order_manager.py` (extend):
  `create_orders_from_evaluation` returns entry + protective legs
  with full lineage columns.
- `backend/tests/unit/positions/test_position_lineage.py`:
  open → partial close → full close lineage; PositionExplanationContext
  contains every required field.
- `backend/tests/unit/operations/test_operations_center_service.py`
  (extend): SignalPlan / Evaluation / Governor decision timelines;
  Position explain.
- `backend/tests/unit/lint/test_no_banned_product_names.py` (new):
  fails on banned names in production code.
- `backend/tests/unit/lint/test_response_shapes.py` (new): fails when
  any FastAPI response model contains banned field names.
- `backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py`
  (extend): forbid imports of `domain.program` from
  `backend/app/runtime/`, `backend/app/orders/`,
  `backend/app/operations/`, `backend/app/api/routes/` after
  S9.3.

## Backend integration tests (additions required)

- `backend/tests/integration/test_deployment_publisher_loop.py`: full
  publisher → evaluator → resolver → governor → order → broker (fake)
  → sync → position lineage; one SignalPlan, one Account, one fill,
  expected explanation context.
- `backend/tests/integration/test_multi_account_fan_out.py`: one
  SignalPlan, two Accounts, distinct decisions and resulting orders.
- `backend/tests/integration/test_position_management_signal_plans.py`:
  open → partial close (50%) → full close; lineage updated; orders
  carry correct `opening_signal_plan_id` / `current_signal_plan_id`.
- `backend/tests/integration/test_recovery_signal_plan.py`: kill
  mid-flight, resume — re-emission is idempotent, no duplicate
  orders.
- `backend/tests/integration/test_alpaca_paper_signal_plan_e2e.py`:
  end-to-end through Alpaca paper or fakepaca stream — opening fill
  + protective legs.
- Existing `test_broker_truth_money_path_e2e.py` and
  `test_manual_trade_loop_e2e.py` continue to pass unchanged.

## Frontend tests

- Add per-page tests for new pages (`dashboard`, `deployments`,
  `strategies`, `watchlists`, `simLab`, `backtests`, `optimization`,
  `walkForward`, `components`).
- Each page test asserts:
  - mounts with empty backend;
  - mounts with happy backend response;
  - mounts with degraded backend response (banner shown);
  - contains zero banned product names;
  - all API calls go through the API modules (no direct fetch).
- Add a banned-name lint script (`frontend/scripts/lint-banned-names.mjs`)
  invoked by `npm test`.

## Broker-safe E2E

- Use Alpaca paper-mode credentials only.
- Use `fakepaca` test stream for off-hours runs.
- E2E suite gated behind `UTOS_BROKER_SAFE_E2E=1` so it cannot run
  unless explicitly enabled.
- Suite covers:
  - Account create → trade dispatcher live → buying power read.
  - Deployment start → SignalPlan emit → Account evaluate → order
    submit → fill → position lineage → explanation context.
  - Pause Deployment → no new entries; existing protective legs
    remain.
  - Pause Account → all orders blocked across Deployments.
  - Global kill → no new orders.
  - Flatten Account → close positions, lineage updated.

## Simulation regression

- Replay a deterministic historical bar set through the new spine;
  assert exact list of emitted SignalPlans, AccountSignalPlanEvaluations,
  GovernorDecisionTraces, internal orders, fills, and position
  lineage.
- Snapshot tests: a snapshot file per scenario; PRs that change
  numbers must update the snapshot with reviewer approval.

## No-silent-failure tests

These exist as positive guards that *failure surfaces*. Every
mission-critical action gets one:

- Trade Sync down → API surfaces `is_stale=true`, `stale_reason`,
  `last_error` non-empty.
- Live Stock Market Data Stream down → System Streams shows error.
- BrokerSync stale → Governor rejects new opens with reason
  `broker_sync_stale`.
- Manual order rejected by adapter → idempotency record stores
  REJECTED, audit event written.
- Deployment start fails preflight → Operations shows reason.
- Promotion gate ineligible → API returns blocking reasons.

## No-silent-success tests

- Manual order submit return must show evidence of broker
  acceptance (broker_order_id), not just internal order_id.
- Deployment start must show running pipeline + first health beat
  before claiming RUNNING.
- Flatten request must report intent submitted *and* the resulting
  orders, not just `accepted=true`.

## Acceptance gates

| Gate | Required |
|---|---|
| All unit tests green | Yes (CI block) |
| All integration tests green | Yes (CI block) |
| All frontend tests green | Yes (CI block) |
| Banned-name lint clean | Yes (CI block) |
| Architecture import guardrail clean | Yes (CI block) |
| Broker-safe E2E green | Yes for cutover |
| Simulation regression snapshots reviewed | Yes when changed |
| Day Zero Runbook executed on paper | Yes for cutover |

## Production smoke checks (operator-runnable)

1. Backend boots with intended runtime database; no warnings about
   missing migrations.
2. `GET /api/v1/system/streams` shows live stock market data running
   and trade dispatchers running per Account.
3. `GET /api/v1/operations/overview` returns without 5xx.
4. `GET /api/v1/dashboard/summary` returns within 500ms.
5. Create a Strategy, freeze a version, create a Watchlist, create a
   Deployment subscribed to one paper Account, start the Deployment.
6. Operations Center shows recent SignalPlans within minutes (or the
   appropriate quiet-window if rules don't fire).
7. Manually publish a synthetic SignalPlan via a test endpoint (CI
   only) — confirm Account evaluation, governor approval, order,
   broker fill (fakepaca), position lineage, explain.
8. Pause Account; confirm no further submissions.
9. Resume; confirm no spurious recovery orders.
10. Kill globally; confirm everything halts; resume; confirm clean
    restart with no duplicate orders.

## Failure-mode rehearsal

Before cutover, rehearse each of these:

- Stop Alpaca trade stream mid-trade → operator-visible error,
  stale state, governor blocks new opens.
- Corrupt one persisted SignalPlan record → loader logs explicit
  parse error, blocks publisher; operator-visible.
- Delete a credential → trade dispatcher reports
  `credentials_invalid`; the rest of the system continues.
- Restart backend mid-deployment → recovery re-emits or supersedes
  pending SignalPlans without duplicates.
