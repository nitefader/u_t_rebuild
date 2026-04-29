# API And Read-Model Gaps

Last updated: 2026-04-27 02:36:00 -04:00

This is the contract every UI surface needs from the backend in order
to be production-grade. Each surface lists the read model and the
mutation endpoints it requires. Each entry is **MISSING**, **PARTIAL**,
or **EXISTS**. Versioning is `/api/v1`.

Current active frontend contract status:

```text
PASS for every endpoint currently called by frontend/src/api.

Locked by:
backend/tests/unit/api/test_frontend_api_contract.py
```

The remaining MISSING rows below are product-completion gaps, not current
frontend boot blockers, unless the page already calls that route.

## Dashboard

Read model: `/api/v1/dashboard/summary` (MISSING)

```json
{
  "live_stock_data": { "provider": "alpaca", "feed": "iex",
                       "running": true, "last_message_at": "...",
                       "last_error": null },
  "trade_sync": { "connected": 2, "stale": 0, "down": 0,
                  "by_account": [...] },
  "account_count": 2,
  "running_deployment_count": 1,
  "recent_signal_plans": [...top N...],
  "open_positions_count": 4,
  "open_orders_count": 2,
  "signals_today_count": 12,
  "critical_warnings": [...],
  "global_kill_active": false,
  "latest_critical_runtime_error": null,
  "snapshot_at": "..."
}
```

Notes: assemble from existing system_streams + operations overview +
new SignalPlan persistence. No new computation server-side beyond a
single read.

## Strategies

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/strategies` | GET, POST | EXISTS |
| `/api/v1/strategies/{id}` | GET, PATCH | EXISTS |
| `/api/v1/strategies/{id}/delete` | POST | EXISTS |
| `/api/v1/strategies/{id}/versions` | GET, POST | EXISTS |
| `/api/v1/strategies/{id}/versions/{version_id}` | GET | EXISTS |
| `/api/v1/strategies/{id}/versions/{version_id}/freeze` | POST | EXISTS |
| `/api/v1/strategies/{id}/validate` | POST | MISSING |

Read model: list of strategies (`{strategy_id, name, status,
latest_version_id, frozen_versions[], created_at}`), per-strategy
versions with rules, controls, execution config, validation status.

## Components (catalog)

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/components/signal-rules` | GET | MISSING |
| `/api/v1/components/exit-rules` | GET | MISSING |
| `/api/v1/components/conditions` | GET | MISSING |
| `/api/v1/components/feature-specs` | GET | PARTIAL (lives inside features module; expose) |

## Watchlists

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/watchlists` | GET, POST | EXISTS |
| `/api/v1/watchlists/{id}` | GET, PATCH | EXISTS |
| `/api/v1/watchlists/{id}/delete` | POST | EXISTS |
| `/api/v1/watchlists/{id}/snapshot` | POST | EXISTS |
| `/api/v1/watchlists/{id}/preview` | POST | MISSING |

Watchlist resource:

```json
{ "watchlist_id": "...", "name": "Liquid US large caps",
  "kind": "static" | "dynamic",
  "static_symbols": ["AAPL", "MSFT", ...],
  "dynamic_rules": { "universe": "us_equities",
                     "filters": [...] },
  "snapshot": { "watchlist_snapshot_id": "...", "taken_at": "...",
                "symbols": [...] } }
```

## Chart Lab

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/chart-lab/health` | GET | EXISTS |
| `/api/v1/chart-lab/preview` | POST | EXISTS (preview service) |
| `/api/v1/chart-lab/stream/{symbol}` | WS | EXISTS |

PARTIAL: ensure preview returns `ChartLabPreviewEvidence` already
modelled in `domain.research_evidence`.

## Sim Lab

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/sim-lab/sessions` | GET, POST | EXISTS (evidence-backed V1) |
| `/api/v1/sim-lab/sessions/{id}` | GET, DELETE | EXISTS (archive-on-delete V1) |
| `/api/v1/sim-lab/sessions/{id}/run` | POST | EXISTS (evidence-backed V1) |
| `/api/v1/sim-lab/sessions/{id}/results` | GET | EXISTS |

Backed by `simulation/historical_replay.py` and
`simulation/engine.py`. Results returned as `SimulationRunEvidence`.

## Backtests

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/backtests` | GET, POST | EXISTS (evidence-backed V1) |
| `/api/v1/backtests/{id}` | GET | EXISTS |
| `/api/v1/backtests/{id}/cancel` | POST | EXISTS |

Results: `BacktestRun` (already modelled).

## Optimization

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/optimization/runs` | GET, POST | EXISTS (evidence-backed V1) |
| `/api/v1/optimization/runs/{id}` | GET, DELETE | EXISTS (archive-on-delete V1) |

Results: `OptimizationRun`.

## Walk-Forward

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/walk-forward/runs` | GET, POST | EXISTS (evidence-backed V1) |
| `/api/v1/walk-forward/runs/{id}` | GET, DELETE | EXISTS (archive-on-delete V1) |

Results: `WalkForwardRun`.

## Promotion

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/promotion/evaluate` | POST | MISSING |

Re-key from `program_id` to `strategy_version_id` + paper deployment
evidence.

## Deployments

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/deployments` | GET, POST | EXISTS |
| `/api/v1/deployments/{id}` | GET, PATCH | EXISTS |
| `/api/v1/deployments/{id}/delete` | POST | EXISTS |
| `/api/v1/deployments/{id}/start` | POST | EXISTS |
| `/api/v1/deployments/{id}/stop` | POST | EXISTS |
| `/api/v1/deployments/{id}/pause` | POST | EXISTS (under `/operations`) |
| `/api/v1/deployments/{id}/resume` | POST | EXISTS (under `/operations`) |
| `/api/v1/deployments/{id}/flatten` | POST | EXISTS (under `/operations`) |
| `/api/v1/deployments/{id}/subscribe` | POST | EXISTS |
| `/api/v1/deployments/{id}/unsubscribe` | POST | EXISTS |
| `/api/v1/deployments/{id}/signal-plans` | GET | MISSING |
| `/api/v1/deployments/{id}/runtime` | GET | PARTIAL (state lives in `deployment_runtime_states`) |

Resource:

```json
{ "deployment_id": "...", "name": "...", "strategy_version_id": "...",
  "watchlist_ids": [...], "subscribed_account_ids": [...],
  "status": "draft|active|paused|stopped|blocked|error",
  "runtime_overrides": {...}, "created_at": "...", "started_at": "..." }
```

## Accounts

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/broker-accounts` | GET, POST | EXISTS |
| `/api/v1/broker-accounts/{id}` | PATCH | EXISTS |
| `/api/v1/broker-accounts/{id}/credentials` | PUT | EXISTS |
| `/api/v1/broker-accounts/{id}/delete` | POST | EXISTS |
| `/api/v1/broker-accounts/{id}/risk-config` | GET, PUT | MISSING |
| `/api/v1/broker-accounts/{id}/restrictions` | GET, PUT | MISSING |
| `/api/v1/broker-accounts/{id}/positions` | GET | PARTIAL (under `/operations/accounts/{id}`) |
| `/api/v1/broker-accounts/{id}/positions/{position_lineage_id}` | GET | MISSING |
| `/api/v1/broker-accounts/{id}/positions/{position_lineage_id}/explain` | GET | MISSING |
| `/api/v1/broker-accounts/{id}/orders` | GET | EXISTS (manual-trade list) |
| `/api/v1/broker-accounts/{id}/orders/{order_id}/cancel` | POST | EXISTS |
| `/api/v1/broker-accounts/{id}/orders` | POST | EXISTS (manual orders) |
| `/api/v1/broker-accounts/{id}/evaluations` | GET | MISSING |
| `/api/v1/broker-accounts/{id}/governor-decisions` | GET | MISSING |
| `/api/v1/broker-accounts/{id}/trade-stream/health` | GET | EXISTS |

The `/broker-accounts` URL prefix is acceptable per
[docs/architecture/NAMING_CONTRACT.md:28](../docs/architecture/NAMING_CONTRACT.md#L28).

## Operations Center

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/operations/overview` | GET | EXISTS |
| `/api/v1/operations/accounts/{id}` | GET | EXISTS |
| `/api/v1/operations/deployments/{id}` | GET | EXISTS |
| `/api/v1/operations/orders/{id}` | GET | EXISTS |
| `/api/v1/operations/research-evidence` | GET | EXISTS |
| `/api/v1/operations/research-evidence/{id}` | GET | EXISTS |
| `/api/v1/operations/signal-plans` | GET | MISSING |
| `/api/v1/operations/signal-plans/{id}` | GET | MISSING |
| `/api/v1/operations/evaluations` | GET | MISSING |
| `/api/v1/operations/evaluations/{id}` | GET | MISSING |
| `/api/v1/operations/governor-decisions` | GET | MISSING |
| `/api/v1/operations/governor-decisions/{id}` | GET | MISSING |
| `/api/v1/operations/positions` | GET | MISSING (cross-account view) |
| `/api/v1/operations/positions/{position_lineage_id}/explain` | GET | MISSING |
| `/api/v1/operations/global/kill` | POST | EXISTS |
| `/api/v1/operations/global/resume` | POST | EXISTS |
| `/api/v1/operations/accounts/{id}/pause` | POST | EXISTS |
| `/api/v1/operations/accounts/{id}/resume` | POST | EXISTS |
| `/api/v1/operations/accounts/{id}/flatten` | POST | EXISTS |
| `/api/v1/operations/deployments/{id}/pause` | POST | EXISTS |
| `/api/v1/operations/deployments/{id}/resume` | POST | EXISTS |
| `/api/v1/operations/deployments/{id}/flatten` | POST | EXISTS |

## Providers

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/market-data/services` (list/create) | GET, POST | EXISTS |
| `/api/v1/market-data/services/{id}` | GET, PUT | EXISTS |
| `/api/v1/market-data/services/{id}/validate` | POST | EXISTS |
| `/api/v1/market-data/services/{id}/set-default` | POST | EXISTS |
| `/api/v1/market-data/services/{id}/default-for` | POST | EXISTS |
| `/api/v1/market-data/services/{id}/disable` | POST | EXISTS |
| `/api/v1/market-data/services/{id}/delete` | POST | EXISTS |
| `/api/v1/market-data/services/resolve` | POST | EXISTS |
| `/api/v1/market-data/pipelines` | GET, POST | EXISTS |
| `/api/v1/ai/providers` | full CRUD + validate + set-default + delete | EXISTS |

PARTIAL: relabel responses with operator-friendly names. The
underlying records may keep `pipelines` / `services`.

## Settings

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/system/status` | GET | EXISTS |
| `/api/v1/system/settings` | GET, PUT | EXISTS |
| `/api/v1/system/streams` | GET | EXISTS |
| `/api/v1/system/migrate-legacy-catalog` | GET, POST | EXISTS |
| `/api/v1/system/migrate-program-to-strategy` | GET, POST | MISSING |

## Risk Cards

A "Risk Card" is the operator's view of:

- Account risk config (sizing rules, max position, max concentration,
  max daily loss, max drawdown).
- Active restrictions (symbol blocklist, asset blocks, time-of-day
  blocks).
- Current exposure projection (gross, net, by symbol, open risk).
- Governor policy snapshot.

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/broker-accounts/{id}/risk-config` | GET, PUT | MISSING |
| `/api/v1/broker-accounts/{id}/restrictions` | GET, PUT | MISSING |
| `/api/v1/broker-accounts/{id}/risk-card` | GET | MISSING (composed read) |
| `/api/v1/governor/policy` | GET, PUT | PARTIAL (state is persisted, no route) |

## Position Explanation

Backed by `PositionExplanationContext` (already modelled).

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/broker-accounts/{id}/positions/{position_lineage_id}/explain` | GET | MISSING |
| `/api/v1/operations/positions/{position_lineage_id}/explain` | GET | MISSING (cross-Account view) |
| `/api/v1/ai/explain-position` | POST | MISSING (advisory only) |

The advisory call accepts a `PositionExplanationContext` produced by
the backend; the AI provider receives it via the AI runtime — no
direct provider call from the frontend.

## Streams

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/system/streams` | GET | EXISTS |
| `/api/v1/operations/trade-stream/health` | GET | EXISTS |
| `/ws/operations/trade-stream` | WS | EXISTS |
| `/ws/chart-lab/{symbol}` | WS | EXISTS |
| `/ws/operations/signal-plans` | WS | MISSING (live SignalPlan emission) |
| `/ws/operations/evaluations` | WS | MISSING (live Account decisions) |
| `/ws/operations/governor-decisions` | WS | MISSING (live governor trace) |

WebSockets stay tab-detached at the broker boundary (already correct
in `runtime_context.py`).

## Orders / Fills

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/operations/orders/{order_id}` | GET | EXISTS |
| `/api/v1/broker-accounts/{id}/orders` | GET | EXISTS |
| `/api/v1/broker-accounts/{id}/orders/{order_id}/cancel` | POST | EXISTS |
| `/api/v1/broker-accounts/{id}/fills` | GET | MISSING |

## Broker sync

| Endpoint | Method | Status |
|---|---|---|
| `/api/v1/broker-accounts/{id}/sync-state` | GET | PARTIAL (lives in operations/account view) |
| `/api/v1/broker-accounts/{id}/sync-now` | POST | MISSING (operator-triggered reconcile, gated) |
| `/api/v1/broker-accounts/{id}/reconcile` | POST | MISSING (full reconciliation report) |

## SignalPlans cross-cutting

A SignalPlan resource (read-only):

```json
{ "signal_plan_id": "...", "deployment_id": "...",
  "strategy_id": "...", "strategy_version_id": "...",
  "watchlist_snapshot_id": null,
  "symbol": "AAPL", "side": "long", "intent": "open",
  "status": "published",
  "entry": {...}, "stop": {...}, "targets": [...],
  "runner": null, "logical_exit": null,
  "opening_signal_plan_id": null,
  "related_position_lineage_id": null,
  "expires_at": null,
  "created_at": "...", "published_at": "...",
  "reason": "...", "warnings": [...] }
```

A SignalPlan timeline must be queryable by `(deployment_id)`,
`(account_id)`, `(strategy_id)`, `(symbol)`, time range.

## Account Evaluation cross-cutting

```json
{ "evaluation_id": "...", "account_id": "...",
  "signal_plan_id": "...", "deployment_id": "...",
  "strategy_id": "...",
  "status": "accepted|rejected|blocked|needs_operator_attention|deferred|stale",
  "participation_decision": "participate|ignore|reject|defer|requires_operator",
  "risk_resolver_result": {...},
  "governor_decision": {...},
  "rejection_reasons": [...],
  "warnings": [...],
  "created_at": "...", "evaluated_at": "..." }
```

## Banned response shapes

API responses must not contain:

- `program`, `program_id`, `program_version_id` (in operator-facing
  surfaces; internal IDs allowed for one migration window).
- `runtime_path` / `runtime_smoke` / `live_trading` distinguishing
  paper vs live as separate runtimes.
- `services_center`.
- Any field that implies AI approval / rejection / sizing of trades.

A response-shape lint test should fail the build on these names
appearing in route response models.
