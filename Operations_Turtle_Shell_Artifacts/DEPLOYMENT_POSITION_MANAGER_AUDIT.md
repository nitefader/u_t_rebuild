# Deployment Position Manager Audit

Last updated: 2026-04-26 23:30:33 -04:00

Operation: Turtle Shell

Decision: FIX REQUIRED, then corrected in this slice.

## Current Behavior Found

- Deployment runtime entry evaluation lives in `backend/app/pipeline/orchestrator.py`.
- Entries are evaluated from the existing `ResolvedProgramComponents.universe`
  through `build_feature_plan(...)`, `SignalEngine.evaluate(...)`, and
  `SignalPlanBuilder.build_from_candidate(...)`.
- SignalPlans are emitted by the runtime composition root with `deployment_id`,
  `strategy_id`, and `strategy_version_id`; Strategy does not own SignalPlans.
- Automated orders are created through `OrderManager.create_signal_plan_order(...)`
  after Account-specific RiskResolver and Governor evaluation.
- Broker submission remains behind BrokerAdapter, and broker result writes remain
  behind BrokerSync / BrokerSyncService.

## Gaps Found

- Exit candidates were not clearly separated from the Watchlist entry path.
- Position-management SignalPlans could be produced from a protective
  ExecutionIntent shim, but that path used synthetic position lineage rather
  than Account-owned Position lineage.
- Deployment runtime did not have an explicit read boundary for Positions scoped
  by `deployment_id`.
- `BrokerPositionSnapshot` did not carry nullable Deployment, Strategy,
  opening SignalPlan, or position lineage metadata.
- The feature plan originally rejected a bar for a symbol no longer in the
  Watchlist before position exit logic could evaluate it.

## Proposed Fix

- Add nullable lineage fields to broker Position snapshots.
- Add a position access method:
  `list_broker_position_snapshots_by_deployment(deployment_id)`.
- Add a runtime-only `DeploymentPositionManager`.
- Keep entries gated to Watchlist / Universe symbols.
- Let position symbols extend the runtime feature plan only for management.
- Build exit / logical-exit SignalPlans from Account-owned Positions where
  `position.deployment_id == deployment.deployment_id`.
- Fan the emitted SignalPlan to Accounts independently:
  - Account with active Position acts.
  - Account with closed Position ignores.
  - Account that never entered ignores.

## Files Inspected

- `backend/app/pipeline/orchestrator.py`
- `backend/app/decision/signal_engine.py`
- `backend/app/decision/signal_plan_builder.py`
- `backend/app/domain/signal_plan.py`
- `backend/app/brokers/models.py`
- `backend/app/persistence/runtime_store.py`
- `backend/app/orders/manager.py`
- `backend/app/risk_resolver/service.py`
- `backend/app/governor/models.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/persistence/test_sqlite_persistence.py`

## Files Changed

- `backend/app/brokers/models.py`
- `backend/app/persistence/runtime_store.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/persistence/test_sqlite_persistence.py`
- `Operations_Turtle_Shell_Artifacts/DEPLOYMENT_POSITION_MANAGER_AUDIT.md`

## Tests Added

- Entry from Watchlist emits Open SignalPlan.
- Exit from Account-owned Position emits Logical Exit SignalPlan.
- Watchlist removal does not prevent Position exit evaluation.
- Multi-Account exit handling acts / ignores independently.
- Cross-Deployment Positions are ignored.
- DeploymentPositionManager reads Positions without mutating broker truth.
- Account without Position ignores exit SignalPlan.
- SQLite runtime store queries broker Positions by `deployment_id`.

## Risks

- Protective `process_protective_intent(...)` remains a compatibility shim and
  still synthesizes SignalPlan lifecycle records from legacy ExecutionIntent.
- Exit order side semantics should receive a future broker-facing review so
  close/reduce orders map cleanly to broker buy/sell direction for long and
  short Positions.
- Position lineage depends on BrokerSync / order lineage correctly populating
  Position snapshots; this slice adds storage and read support but does not
  rewrite historical snapshots.

## Result

PASS after correction.

The runtime now supports:

```text
Watchlist / Universe -> Strategy entry rules -> Deployment -> Open SignalPlan
Account-owned Positions by deployment_id -> Strategy exit rules -> DeploymentPositionManager -> Exit SignalPlan
SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> OrderManager
```

Deployment does not own broker truth, does not mutate Account Positions, and
does not introduce a second runtime root.
