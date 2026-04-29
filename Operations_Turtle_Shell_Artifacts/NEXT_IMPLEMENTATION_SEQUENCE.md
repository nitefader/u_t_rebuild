# Next Implementation Sequence

Last updated: 2026-04-27 14:14:25 -04:00

Operation: Turtle Shell

Status: active implementation sequence

## Current Verified Baseline

Backend unit suite:

```text
Test run: 2026-04-27 03:36:00 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 1103 passed, 6 warnings
```

## Rule

Do not jump directly into live broker runtime rewiring.

Proceed in slices that preserve tests after each slice.

Broker-facing tests must use an already configured Broker Service or the
frontend-configured Broker Account. Intentional test order submission is allowed
when the test explicitly validates order submission, rejection, BrokerSync truth,
or operator advisory behavior; those tests must route through BrokerAdapter and
BrokerSync and identify the order as a test order.

Before implementation, every agent must read and obey:

1. `HANDOFF_PROTOCOL.md`
2. `OPERATION_STATUS.md`
3. `BACKEND_LOCKDOWN_AGENT_PLAN.md`
4. `BACKEND_REALITY_MAP.md`
5. `NEXT_IMPLEMENTATION_SEQUENCE.md`
6. `TURTLE_SHELL_GUARDRAILS.md`
7. `DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`

If a slice conflicts with `TURTLE_SHELL_GUARDRAILS.md`, stop and document the
conflict as a blocker.

Before coding a slice, identify the bounded context from
`DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`. If the slice crosses contexts, define
the command, event, contract, or service boundary.

## Slice 1: Contract Layer

Status: completed

Completed:

- `SignalPlan`
- `AccountSignalPlanEvaluation`
- `RiskResolverResult`
- `GovernorDecisionTrace`
- `PositionExplanationContext`
- `BrokerCapabilityMatrix`
- `BrokerOrderPreflightRequest`
- `BrokerOrderPreflightResult`
- `MarketRulePreflightRequest`
- `MarketRulePreflightResult`
- `LiveStockMarketDataStreamStatus`
- `AccountTradeSyncStatus`
- `SIGNAL_PLAN` order origin
- SignalPlan order lineage fields
- architecture guardrail lint tests
- `SignalPlanBuilder`

## Slice 2: Persistence-Ready Lineage

Status: completed

Goal:

Add nullable storage support for SignalPlan and Position lineage without
rewriting historical orders.

Tasks:

1. Add nullable SQLite columns for:
   - `strategy_id`
   - `strategy_version_id`
   - `signal_plan_id`
   - `opening_signal_plan_id`
   - `current_signal_plan_id`
   - `position_lineage_id`
   - `account_evaluation_id`
   - `governor_decision_id`
   - `leg_label`
   - `lifecycle_intent`
2. Add indexes for:
   - `signal_plan_id`
   - `opening_signal_plan_id`
   - `position_lineage_id`
3. Preserve legacy `program_id` columns as migration shims only.
4. Add tests for save/load of new lineage fields.

Exit test:

```text
python -m pytest backend\tests\unit\persistence backend\tests\unit\orders -q
```

## Slice 3: RiskResolver Boundary

Status: completed

Goal:

Create the first explicit quantity-producing boundary.

Tasks:

1. Add `backend/app/risk_resolver/service.py`.
2. Wrap current sizing logic from `ExecutionIntentBuilder._size_from_components`
   behind RiskResolver.
3. Return `RiskResolverResult`.
4. Add tests proving SignalPlan stays neutral and RiskResolver produces final
   Account size.

Exit test:

```text
python -m pytest backend\tests\unit\risk_resolver backend\tests\unit\runtime -q
```

## Slice 4: Governor Request Contract

Goal:

Replace opaque `execution_intent` dependency with canonical request fields.

Tasks:

1. Add canonical request model in `backend/app/governor/models.py`.
2. Preserve old `GovernorRequest` shim only if needed.
3. Make Governor evaluate SignalPlan intent, RiskResolverResult, sync freshness,
   Account pause, Deployment pause, global kill, restrictions, open orders, and
   duplicate key.
4. Add tests for open, close, reduce, target, stop, trail, breakeven, runner,
   and logical_exit intent handling.

Exit test:

```text
python -m pytest backend\tests\unit\governor -q
```

## Slice 5: OrderManager SignalPlan Path

Goal:

Create orders from approved Account Evaluation / Governor decision, not directly
from `ExecutionIntent`.

Tasks:

1. Add a new method such as `create_signal_plan_order`.
2. Require SignalPlan lineage fields.
3. Preserve manual operator order behavior.
4. Preserve BrokerSync stale gate.
5. Preserve old Program path as migration shim only.

Exit test:

```text
python -m pytest backend\tests\unit\orders backend\tests\integration\test_manual_trade_loop_e2e.py -q
```

## Slice 6: Broker Preflight Service

Status: completed

Goal:

Fail known-invalid Alpaca order shapes before broker submission.

Tasks:

1. Add provider-specific Alpaca capability profile.
2. Add preflight service for submit/replace/cancel.
3. Validate order type, TIF, order class, asset class, fractional/notional,
   extended-hours, and operation support.
4. Add market-rule preflight for session, asset tradability, shorting, ETB,
   halt state, buying power, and crypto/options differences.
5. Enforce broker and market-rule preflight before runtime Alpaca submit.
6. Enforce broker and market-rule preflight before manual Alpaca submit.

Exit test:

```text
python -m pytest backend\tests\unit\brokers -q
```

## Slice 7: Account Trade Sync Unification

Status: completed

Goal:

One Account Trade Sync per validated Alpaca Account routes through BrokerSync
before fan-out.

Tasks:

1. Update dispatcher pipeline: `completed`
   - normalize provider event
   - BrokerSync write/idempotency
   - persist freshness
   - fan-out to subscribers
2. Keep Account Trade Sync open when trading is paused. `completed`
3. Add explicit operator trade-sync pause state. `completed`
4. Remove separate runtime-only trading stream path or make it consume the same
   Account Trade Sync. `completed`

Completed so far:

- `TradeEventDispatcher.status()` now exposes canonical `AccountTradeSyncStatus`.
- `TradeEventDispatcherRegistry.statuses()` returns all Account Trade Sync statuses.
- Operator trade-sync pause/resume methods are explicit and visible.
- Subscribing while operator-paused does not silently restart the stream.
- Trade events route through `BrokerStreamRouter` and `BrokerSyncService`
  before fan-out.
- BrokerSync route failures are visible and block fan-out of unsynced broker
  truth.
- `broker_runtime_entrypoint` no longer creates a runtime-owned trade stream;
  Account Trade Sync is owned by `TradeEventDispatcherRegistry`.

Exit test:

```text
python -m pytest backend\tests\unit\brokers backend\tests\unit\runtime backend\tests\unit\api\test_operations_trade_stream_route.py -q
```

## Slice 8: Live Stock Market Data Stream Lock

Status: completed

Goal:

One shared Live Stock Market Data Stream for all stock consumers.

Tasks:

1. Remove trading mode from live stock stream identity. `completed`
2. Start stream envelope at backend app load when enabled. `completed`
3. Keep stream open with zero subscriptions. `completed`
4. Route all component subscriptions through the shared stream boundary. `completed`
5. Expose Operations status. `completed`

Completed:

- `HubKey` now identifies the live stock stream by provider and data feed only.
- `MarketDataStreamHub.start()` opens the stream envelope even with zero
  subscriptions.
- `MarketDataStreamHub.status()` projects canonical
  `LiveStockMarketDataStreamStatus`.
- `bootstrap_streams()` creates and starts the shared live stock market-data
  hub at app load.
- Chart Lab and broker runtime entrypoint route through the shared hub registry.
- `/api/v1/system/streams` projects mode-neutral live stock stream status,
  stream state, last error, and last message time.

Exit test:

```text
python -m pytest backend\tests\unit\market_data backend\tests\unit\runtime backend\tests\unit\api\test_system_streams_route.py -q
```

## Slice 9: Runtime Spine Rewire

Status: completed

Goal:

Move runtime flow to:

```text
SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> Order
```

Tasks:

1. Choose one runtime composition root. `completed`
2. Make SignalEngine output feed SignalPlanBuilder. `completed`
3. Fan one SignalPlan to many Accounts. `completed`
4. Evaluate Accounts independently. `completed`
5. Create orders only from approved Governor decisions. `completed for automated opening and protective paths`
6. Keep Program/ExecutionIntent as shims only until removed. `completed for Slice 9; removal remains a later cleanup`

Completed so far:

- Added `OrderManager.create_signal_plan_order(...)` as the canonical order
  creation handoff.
- SignalPlan orders require accepted Account Evaluation, allowed RiskResolver
  result, approved Governor trace, and full SignalPlan/Position lineage.
- Runtime pipeline now builds a neutral `SignalPlan` from each SignalEngine
  candidate.
- Runtime pipeline now creates Account-specific RiskResolver output and
  AccountSignalPlanEvaluation before order creation.
- Runtime pipeline now creates automated opening orders through
  `create_signal_plan_order(...)`.
- `ExecutionIntent` remains emitted as a compatibility shim for existing
  consumers while Program lineage is removed from new automated orders.
- Protective close/reduce/target/stop/trail/breakeven/runner/logical-exit
  orders now synthesize SignalPlan lifecycle records internally and create
  orders through `create_signal_plan_order(...)`.
- Runtime pipeline now supports one neutral SignalPlan fan-out to multiple
  subscribed Account ids.
- Each fanned-out Account gets its own RiskResolverResult,
  AccountSignalPlanEvaluation, Governor trace, and order decision.
- Account-specific broker freshness and portfolio snapshots are used for
  Governor evaluation.
- `BrokerRuntimeDeployment` can now carry multiple subscribed Account ids for
  one Deployment without creating a second runtime root.
- SignalPlan order client ids are now deterministic by Account, Deployment,
  SignalPlan, lifecycle intent, Position lineage, and leg label.
- `OrderManager.create_signal_plan_order(...)` returns the existing order when
  the same Account + SignalPlan lifecycle is reprocessed.
- SQLite-backed order ledgers now support the same client-order idempotency
  lookup as the in-memory ledger, so broker runtime restarts can avoid duplicate
  submission.
- Runtime skips broker submission when the idempotent SignalPlan order already
  exists and is no longer in `created` state.
- Automated live broker submission is default-denied unless the runtime
  composition root explicitly enables live order submission.
- A disabled live submission records a rejected broker result through
  BrokerSync with `live_submission_disabled`, preserving operator evidence
  without calling the broker.
- Broker runtime now treats paper/live as Account and Deployment metadata:
  the mode must match, but no second runtime root is introduced.
- `GovernorRequest` now accepts canonical request fields directly:
  `deployment_id`, `symbol`, optional `signal_plan_id`, optional
  `position_lineage_id`, `order_intent`, broker freshness, and portfolio.
- `PortfolioGovernor` evaluates canonical GovernorRequest fields instead of
  reading active decisions from `ExecutionIntent`.
- Runtime pipeline builds GovernorRequest from canonical fields; `ExecutionIntent`
  remains a compatibility output/shim for legacy consumers.
- Manual paths remain manual operator authority and do not carry SignalPlan
  lineage.

Remaining gates:

- None for Slice 9.
- Next operation slice: Research Evidence Contracts.

Exit test:

```text
python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\integration -q
```

## Slice 10: Research Evidence Contracts

Status: completed

Goal:

Make Chart Lab, Backtest, Sim Lab, Optimization, Walk-Forward, and Promotion
produce/query evidence instead of caller-supplied tuples.

Tasks:

1. Add `ChartLabPreviewEvidence`. `completed`
2. Add `BacktestRun`. `completed`
3. Add `SimulationRunEvidence`. `completed`
4. Add `OptimizationRun`. `completed`
5. Add `WalkForwardRun`. `completed`
6. Add `PromotionEvidenceBundle`. `completed`
7. Persist/query readiness evidence. `completed for storage, producer wiring, Operations summary, and Operations detail API`

Completed:

- Added research evidence domain contracts in `backend/app/domain/research_evidence.py`.
- Exported research evidence contracts from `backend/app/domain/__init__.py`.
- Evidence contracts reject broker/order/fill/position truth fields.
- Promotion evidence exposes readiness as evidence, not trading authority.
- Guardrail lint remains green.
- `SQLiteRuntimeStore` persists and queries research evidence by id, strategy,
  strategy version, and evidence type.
- `RuntimeOverview` exposes a research evidence summary for Operations.
- Chart Lab preview now emits and optionally records `ChartLabPreviewEvidence`
  through a research evidence recorder boundary.
- Sim Lab historical replay now emits and optionally records
  `SimulationRunEvidence` through a research evidence recorder boundary.
- Operations service now lists and loads detailed research evidence records.
- `/api/v1/operations/research-evidence` and
  `/api/v1/operations/research-evidence/{evidence_id}` expose read-only
  evidence queries without broker, order, or position authority.

Exit test:

```text
python -m pytest backend\tests\unit\chart_lab backend\tests\unit\simulation backend\tests\unit\promotion -q
```

## Coordinator Gate

After each slice:

1. Update `OPERATION_STATUS.md`.
2. Run the slice exit test.
3. Run `python -m pytest backend\tests\unit -q` when shared models changed.
4. Confirm the slice does not violate `TURTLE_SHELL_GUARDRAILS.md`.
5. Confirm the slice respects `DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`.
6. For any real broker order test, record the configured Account/Broker Service
   source, broker mode, command, and broker result in `OPERATION_STATUS.md`.
7. Do not proceed if tests fail.

## Slice 11: Account Trade Sync Reconciliation Scheduler

Status: queued

Goal:

Make Account Trade Sync explicitly event-driven but state-authoritative.
Alpaca trade streams emit events; they do not stream a complete Account state.
Ultimate Trader must own broker-derived truth through BrokerSync plus REST
reconciliation.

Doctrine:

```text
Alpaca Trade Stream + Alpaca REST
-> Account Trade Sync
-> BrokerSync
-> Persistence
-> Operations Center
```

Rules:

1. Account Trade Sync listens, reconnects, buffers, and reports freshness.
2. BrokerSync remains the only writer of broker-derived truth.
3. BrokerAdapter remains the only broker REST boundary.
4. REST reconciliation is required for:
   - full account snapshot, including equity and buying power
   - full position list
   - open orders
5. Operations must show stream state and reconciliation freshness separately.
6. A healthy WebSocket alone must not imply fresh Account, Position, or Order
   truth.

Tasks:

1. Add an adaptive per-Account sync scheduler around the existing Account Trade
   Sync registry.
2. On startup: run full REST reconciliation before or immediately after stream
   open.
3. On stream event: route provider event through BrokerSync immediately.
4. On reconnect or detected event gap: run full REST reconciliation.
5. On healthy stream: poll open orders every 30-60 seconds and
   account/positions every 60-120 seconds.
6. On degraded stream, active orders, or unknown external broker order events:
   shorten reconciliation cadence.
7. Off-hours: slow cadence without disabling truth visibility.
8. Add jitter and per-Account backoff for approximately 10 Accounts.
9. Persist/project sync profile, last REST reconcile timestamps, last stream
   event timestamp, stale reason, and reconnect/error counters to Operations.
10. Add tests proving stream-only freshness does not mask stale REST truth.

Exit test:

```text
python -m pytest backend\tests\unit\brokers backend\tests\unit\runtime backend\tests\unit\operations -q
```

## Backend Readiness Pass

Status: completed

Report:

```text
Operations_Turtle_Shell_Artifacts/BACKEND_READINESS_REPORT.md
```

Verified:

```text
Test run: 2026-04-26 23:07:18 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 963 passed, 6 warnings

Test run: 2026-04-26 23:08:09 -04:00
Command: python -m pytest backend\tests\smoke -q
Result: 6 passed, 1 warning

Test run: 2026-04-26 23:08:16 -04:00
Command: python -m pytest backend\tests\integration -q -rs
Result: 27 passed, 3 skipped, 1 warning

Test run: 2026-04-26 23:08:44 -04:00
Command: RUN_ALPACA_FAKEPACA_STREAM=1 RUN_ALPACA_PAPER_INTEGRATION=1 RUN_ALPACA_PAPER_CRYPTO_STREAM=1 python -m pytest backend\tests\integration\test_alpaca_fakepaca_stream.py backend\tests\integration\test_alpaca_paper_integration.py backend\tests\integration\test_alpaca_paper_crypto_stream.py -q -rs
Result: 1 passed, 2 skipped, 2 warnings
```
