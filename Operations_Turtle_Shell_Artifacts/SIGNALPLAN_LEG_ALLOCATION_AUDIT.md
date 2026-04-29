# SignalPlan Leg Allocation Audit

Last updated: 2026-04-27 00:03:00 -04:00

Operation: Turtle Shell

Decision: FIX REQUIRED, then corrected for backend contracts and RiskResolver
allocation semantics in this slice.

## Operator Doctrine Incorporated

One SignalPlan is one trade lifecycle.

If the Strategy says:

```text
Open one position with multiple targets, a stop, and a runner.
```

the backend must not treat that as four unrelated trade ideas.

The correct model is:

```text
SignalPlan
-> Account Evaluation
-> RiskResolver evaluates total Account risk
-> RiskResolver allocates quantities to lifecycle legs
-> Governor evaluates the lifecycle risk
-> OrderManager can create child orders/legs under the same SignalPlan lineage
```

## Current Behavior Found

- `SignalPlan` already supports:
  - entry
  - stop
  - targets
  - runner
  - logical exit
- `SignalPlanTarget.quantity_pct` and `SignalPlanRunner.quantity_pct` already
  express lifecycle percentages.
- `InternalOrder` already has:
  - `leg_label`
  - `lifecycle_intent`
  - `parent_order_id`
  - SignalPlan lineage fields
- `OrderManager.create_signal_plan_order(...)` can already create one Account
  order tied to SignalPlan lineage.
- RiskResolver previously returned only one final Account quantity and did not
  allocate that quantity to lifecycle legs.

## Gaps Found

- No structured resolved leg allocation existed.
- RiskResolver did not distinguish fractional-share accounts from whole-share
  accounts.
- Whole-share target math had no policy for remainders.
- Runtime Account evaluations did not expose lifecycle allocation evidence.
- OrderManager could create one SignalPlan order but did not have a first-class
  helper to create multiple child orders/legs from one approved lifecycle plan.

## Corrections Made

- Added `RiskResolvedLegAllocation`.
- Added `RiskResolverResult.leg_allocations`.
- Added `RiskResolverResult.fractional_quantity_allowed`.
- Added `RiskResolverResult.quantity_rounding_policy`.
- Added `LifecycleSizingInput`.
- Added `RiskResolver.resolve_lifecycle(...)`.
- Runtime opening SignalPlans now use lifecycle risk resolution.
- Added `OrderManager.create_signal_plan_leg_orders(...)`.

## Allocation Semantics

RiskResolver evaluates total quantity first.

Example:

```text
Total Account quantity: 100
T1: 25%
T2: 30%
T3: 15%
Runner: 30%
Stop: required full-position protection
```

Resolved lifecycle allocation:

```text
entry: 100
stop: 100
T1: 25
T2: 30
T3: 15
runner: 30
```

The stop is protective coverage. It does not count as a separate profit-taking
allocation.

## Fractional Vs Whole Shares

Fractional allowed:

```text
37 shares * 25% = 9.25
37 shares * 30% = 11.1
37 shares * 15% = 5.55
runner = 11.1
```

Whole shares:

```text
37 shares * 25% = 9
37 shares * 30% = 11
37 shares * 15% = 5
runner receives remainder = 12
```

Whole-share safety rule:

```text
floor target quantities
assign leftover to runner when runner exists
never exceed total resolved quantity
```

## Files Inspected

- `backend/app/domain/signal_plan.py`
- `backend/app/risk_resolver/service.py`
- `backend/app/orders/manager.py`
- `backend/app/orders/models.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/preflight.py`
- `backend/tests/unit/risk_resolver/test_risk_resolver_contract.py`
- `backend/tests/unit/domain/test_signal_plan_contracts.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`

## Files Changed

- `backend/app/domain/signal_plan.py`
- `backend/app/domain/__init__.py`
- `backend/app/risk_resolver/service.py`
- `backend/app/risk_resolver/__init__.py`
- `backend/app/orders/manager.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/risk_resolver/test_risk_resolver_contract.py`
- `backend/tests/unit/domain/test_signal_plan_contracts.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `Operations_Turtle_Shell_Artifacts/SIGNALPLAN_LEG_ALLOCATION_AUDIT.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

## Tests Added

- RiskResolver resolves exact fractional lifecycle leg quantities.
- RiskResolver floors target quantities and assigns remainder to runner for
  whole-share Accounts.
- RiskResolverResult carries structured leg allocations.
- Runtime Account Evaluation exposes leg allocation evidence.
- OrderManager can create multiple child lifecycle orders under one SignalPlan.

## Architectural Review

Approved for this slice.

This keeps:

- one runtime root
- one SignalPlan lifecycle
- Account-specific RiskResolver quantity ownership
- Governor as the approval gate
- BrokerAdapter as the submission boundary
- BrokerSync as broker truth writer

## Deliberate Boundary

This slice creates first-class backend allocation and internal child-order
creation support.

It does **not** yet convert Alpaca execution into broker-native OCO/bracket
orders because the current Alpaca boundary is intentionally simple-order first
and broker-managed bracket/OCO remains disabled by preflight.

## Remaining Risks

- Pending exit exposure must still be reconciled before child leg submission so
  active stop/target/trail orders cannot exceed current Account Position after
  priority rules.
- Broker-native bracket/OCO support needs a dedicated Alpaca capability slice.
- Same-symbol multiple active lineages on one Account need stronger lineage
  selection or ambiguity blocking before fully automatic multi-leg submission.
- Runtime currently records lifecycle allocations in Account Evaluation, while
  automatic child-leg submission should remain gated until pending-exit priority
  and broker bracket/OCO semantics are finalized.
