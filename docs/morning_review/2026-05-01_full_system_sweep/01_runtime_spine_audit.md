# 01 Runtime Spine Audit

Canonical flow reviewed:
`Strategy -> Deployment -> SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> OrderManager -> BrokerAdapter -> BrokerSync -> Position Truth -> Operations`

Positive note: `backend/app/pipeline/orchestrator.py` contains a recognizable SignalPlan spine. It builds SignalPlans, records account evaluations, calls `create_signal_plan_order`, submits through BrokerAdapter, and applies results through BrokerSync. Deployment exits are also scoped through `DeploymentPositionManager.positions_for_deployment()`.

## Findings

### R01 - Legacy Program/ExecutionIntent order path remains active

- severity: critical
- file path: `backend/app/orders/manager.py:107`, `backend/app/orders/models.py:45`, `backend/app/orders/models.py:57`
- issue: `OrderManager.create_order()` still accepts `execution_intent`, checks `execution_intent.governor_approved`, derives `program_id`, builds a Program client order id, and creates `OrderOrigin.PROGRAM` orders. `InternalOrder.origin` defaults to `OrderOrigin.PROGRAM`.
- why it matters: This is a duplicate runtime order path beside SignalPlan. If any caller reaches it, orders can be created outside the required SignalPlan -> Account Evaluation -> Governor lineage.
- recommended fix: Remove or quarantine `create_order(execution_intent)` behind an explicit legacy-only test fixture. Make `origin` required with no Program default. Block `OrderOrigin.PROGRAM` in production modules.
- suggested agent prompt: "Audit and remove active Program/ExecutionIntent order creation from OrderManager. Preserve only SignalPlan and manual operator order creation. Update tests and lint guardrails so Program-origin orders cannot be created by backend/app runtime code."

### R02 - Broker position truth is read directly outside BrokerSync

- severity: critical
- file path: `backend/app/orders/manager.py:1063`, `backend/app/control_plane/service.py:173`
- issue: `_has_backing_position()` calls `self._broker_adapter.get_positions(order.account_id)`. `cancel_resting_open_orders_without_positions()` also calls `broker_adapter.get_positions(account_id)` directly.
- why it matters: BrokerSync is the only broker truth writer/source boundary. Direct broker reads can make cancellation decisions from truth that was not reconciled, persisted, or visible to Operations.
- recommended fix: Route cancellation preservation through BrokerSync/runtime-store position snapshots. OrderManager should not depend on a raw BrokerAdapter for position truth.
- suggested agent prompt: "Replace direct BrokerAdapter position reads in OrderManager and control-plane cancellation sweeps with BrokerSync/runtime-store position snapshots. Add guardrail tests that backend/app/orders and backend/app/control_plane do not call `get_positions()` directly."

### R03 - Governor still accepts ExecutionIntent and emits Program lineage

- severity: high
- file path: `backend/app/governor/models.py:46`, `backend/app/governor/models.py:113`, `backend/app/governor/service.py:176`, `backend/app/governor/service.py:231`
- issue: `PositionSummary` and `PendingOpenSummary` require `program_id`. `GovernorRequest` accepts `execution_intent` and derives `program_id`. `PortfolioGovernor._resolve_order_intent()` reads `execution_intent.intent_type`. Projected state still includes `program_id`.
- why it matters: Governor is the final pre-order gate. Accepting old intent shapes weakens traceability and keeps the old runtime vocabulary alive inside a safety-critical boundary.
- recommended fix: Require canonical request fields only: deployment, account, symbol, SignalPlan/account-evaluation/risk result/governor context. Move Program compatibility to explicit data migration, not the live Governor model.
- suggested agent prompt: "Remove ExecutionIntent/program_id from GovernorRequest and projected state. Update Governor tests to use SignalPlan/account-evaluation inputs and add a regression that ExecutionIntent input is rejected."

### R04 - Program paper-to-live promotion workflow is still active

- severity: high
- file path: `backend/app/promotion/service.py:11`, `backend/app/promotion/service.py:36`, `backend/app/promotion/service.py:49`, `backend/app/promotion/models.py:62`
- issue: `PromotionGateService` is described as `BROKER_PAPER to BROKER_LIVE promotion`, returns `program_id`, and blocks on `program_not_frozen`.
- why it matters: Doctrine says paper/live are Account metadata, not separate products or runtime paths, and Program is not an active V1 product concept.
- recommended fix: Retire this service from active runtime/API exports or rename/rebuild it around Strategy/Deployment readiness without paper/live product promotion semantics.
- suggested agent prompt: "Review backend/app/promotion and remove active Program/paper-to-live promotion semantics. Replace any still-needed readiness checks with Strategy/Deployment/Account metadata checks, no Program entity."

### R05 - Chart Lab still accepts Program lineage in active domain model

- severity: medium
- file path: `backend/app/domain/chart_lab.py:19`, `backend/app/domain/chart_lab.py:52`
- issue: `ChartLabSession` still has `program_version_id` and accepts either `strategy_version_id` or `program_version_id`.
- why it matters: Chart Lab is non-trading, so this is not an order-risk path, but it keeps an old active concept in a user-facing research surface.
- recommended fix: Migrate any historical sessions to `strategy_version_id`; reject new `program_version_id` input outside a one-time migration.
- suggested agent prompt: "Remove Program lineage from ChartLabSession creation. Add a migration-only loader path if historical rows need conversion, and update tests to require StrategyVersion."

### R06 - Architecture guardrail test allowlist is too broad

- severity: high
- file path: `backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py:17`
- issue: The Program lineage allowlist includes active modules such as `orders/manager.py`, `orders/models.py`, `governor/models.py`, `governor/service.py`, `persistence/runtime_store.py`, and `promotion/service.py`.
- why it matters: The guardrail passes while allowing the exact live surfaces that doctrine says should be gone.
- recommended fix: Shrink the allowlist to explicit migration loaders and tests. Runtime modules should fail the lint if they contain Program lineage.
- suggested agent prompt: "Tighten Program lineage lint allowlist to migration-only files. Move active runtime files out of the allowlist and repair the resulting offenders."

### R07 - Broker account credential update writes sync freshness outside BrokerSync

- severity: medium
- file path: `backend/app/broker_accounts/service.py:287`
- issue: Credential replacement saves a stale `BrokerSyncState` directly through `runtime_store.save_broker_sync_freshness()`.
- why it matters: Sync freshness gates runtime behavior. Writing it outside BrokerSync blurs the truth boundary, even if the intent is to mark state stale.
- recommended fix: Add a BrokerSync method for marking account sync stale after credential changes, or centralize this in a BrokerSync-owned service.
- suggested agent prompt: "Move broker sync freshness writes from BrokerAccountService into BrokerSync-owned API. Preserve credential replacement behavior and add a test that BrokerAccountService does not call runtime_store broker truth writers directly."

### R08 - Active code contains banned `Live Runtime` phrase

- severity: high
- file path: `backend/app/simulation/historical_replay.py:1296`
- issue: Backend lint fails because the comment says `live runtime`.
- why it matters: The naming contract bans separate paper/live runtime concepts. The lint failure blocks the backend suite and indicates doctrine language is leaking back into active source.
- recommended fix: Replace with neutral language like `production SignalPlan runtime`.
- suggested agent prompt: "Fix banned product-name lint in historical_replay without changing behavior. Use canonical runtime wording and rerun backend lint."

### R09 - Runtime startup uses deprecated FastAPI event hooks

- severity: medium
- file path: `backend/app/api/server.py:55`, `backend/app/api/server.py:97`
- issue: App startup/shutdown uses `@app.on_event`, and test output emits FastAPI deprecation warnings.
- why it matters: Startup owns market data and trade sync boot. Deprecated lifecycle hooks increase production drift risk and complicate Cloud Run shutdown handling.
- recommended fix: Move startup/shutdown into a FastAPI lifespan context with explicit cleanup on yield exit.
- suggested agent prompt: "Convert backend/app/api/server.py startup/shutdown event handlers to a FastAPI lifespan context. Preserve boot order: manual trade composition, streams, discovery poller; preserve shutdown order."

### R10 - Canonical runtime exists but old class names still describe authority

- severity: low
- file path: `backend/app/runtime/account_trading_orchestrator.py`, `backend/tests/unit/lint/test_turtle_shell_architecture_guardrails.py:50`
- issue: Runtime guardrail still allows `BrokerRuntimeOrchestrator` and `BrokerRuntimeSupervisor`.
- why it matters: The implementation may be canonical internally, but old names keep paper/live/runtime-root ambiguity alive for future agents.
- recommended fix: Rename when the current runtime slice is stable; do not mix with behavior fixes.
- suggested agent prompt: "Rename BrokerRuntime* shims to AccountTrading* names after runtime behavior is clean. Keep imports backward-compatible only in tests or migration notes."
