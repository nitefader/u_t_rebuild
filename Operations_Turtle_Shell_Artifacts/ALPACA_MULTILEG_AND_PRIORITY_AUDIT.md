# Alpaca Multi-Leg And Priority Audit

Last updated: 2026-04-27 00:15:17 -04:00

Operation: Turtle Shell

Decision: FIX REQUIRED, then corrected for backend capability and priority
contracts in this slice.

## Operator Doctrine Incorporated

One SignalPlan can have many lifecycle legs, but it remains one trade idea.

Alpaca broker-native support must be explicit:

- Internal SignalPlan lifecycle may support multiple targets, stop, runner, and
  logical exits.
- Alpaca broker-native bracket/OCO/OTO submission must not be assumed.
- If Alpaca cannot submit the full lifecycle as one broker-native order, the
  system must keep lifecycle truth internally and use ledger-managed child legs.

Priority rule:

```text
manual emergency close / recovery
> strategy close / logical_exit
> stop / trail / breakeven
> target / reduce
> runner management
```

## Current Behavior Found

- Internal lifecycle allocation now exists through `RiskResolvedLegAllocation`.
- `OrderManager.create_signal_plan_leg_orders(...)` can create child lifecycle
  orders under one SignalPlan lineage.
- Alpaca adapter currently submits simple orders only.
- Alpaca preflight previously rejected all non-simple order classes with a
  generic message.
- OrderManager did not expose a priority helper to identify passive exits that
  should be superseded by a higher-priority close/logical exit.

## Corrections Made

- Added explicit broker-native multi-leg request metadata to
  `BrokerOrderPreflightRequest`:
  - `native_multileg_requested`
  - `target_leg_count`
  - `stop_leg_count`
  - `runner_leg_count`
- Added `BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED`.
- Alpaca preflight now specifically rejects unsupported broker-native
  multi-target brackets and runner-as-native-order requests.
- Alpaca preflight keeps the operator advisory pointed at internal
  SignalPlan leg allocation and ledger-managed child orders.
- `build_broker_order_preflight_request(...)` now preserves `order.order_class`
  when present instead of always coercing to simple.
- `OrderManager` now classifies all position-management intents as protective.
- Added `pending_position_management_orders(...)`.
- Added `superseded_position_management_orders(...)`.

## Alpaca Capability Decision

Current adapter boundary remains:

```text
simple orders only
```

Reason:

- The current adapter does not build Alpaca bracket/OCO/OTO request payloads.
- Alpaca broker-native bracket order shape is not equivalent to Ultimate
  Trader's four-target-plus-runner lifecycle model.
- Multi-target lifecycle management remains first-class internally.
- Broker-native multi-leg submission requires a later adapter-specific
  implementation and paper-broker verification.

## Priority Semantics

Given an active Position with passive orders:

```text
stop order
target order
```

Incoming:

```text
logical_exit
```

OrderManager now identifies both passive orders as superseded.

Given an active Position with:

```text
stop order
```

Incoming:

```text
target
```

The target does not supersede the higher-priority stop.

## Files Inspected

- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/preflight.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/orders/manager.py`
- `backend/app/orders/models.py`
- `backend/app/orders/ledger.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
- `backend/tests/unit/orders/test_order_manager.py`

## Files Changed

- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/preflight.py`
- `backend/app/orders/manager.py`
- `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `Operations_Turtle_Shell_Artifacts/ALPACA_MULTILEG_AND_PRIORITY_AUDIT.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

## Tests Added

- Alpaca preflight rejects broker-native multi-target brackets with a specific
  advisory.
- Alpaca preflight rejects runner management as a broker-native multi-leg
  concept.
- Logical exit supersedes passive stop/target management orders.
- Target does not supersede a higher-priority stop.

## Architectural Review

Approved for this slice.

This keeps:

- one SignalPlan lifecycle
- one runtime root
- BrokerAdapter as submit boundary
- BrokerSync as truth writer
- Alpaca-specific constraints behind anti-corruption/preflight boundaries

## Remaining Risks

- Automatic cancellation/replacement of superseded passive exits is not yet
  wired into runtime order submission.
- Broker-native bracket/OCO payload construction remains disabled and needs
  Alpaca paper-account verification before use.
- Same-symbol multiple active lineages still need ambiguity handling before
  automatic multi-leg submission.
