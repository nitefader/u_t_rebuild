# Alpaca Multi-Leg And Pending Exit Priority Audit

Operation: Turtle Shell

Reviewed at: 2026-04-27 00:16:34 -04:00

Decision: PASS FOR CONTRACT AND ORDER-LEDGER BOUNDARY; NOT APPROVED FOR AUTOMATIC MULTI-LEG LIVE SUBMISSION YET

## Current Behavior

Ultimate Trader now treats one SignalPlan as one lifecycle trade idea. Entry,
stop, target, runner, and logical-exit legs can be represented as child
Internal Orders linked to the same SignalPlan and Position lineage.

RiskResolver performs total Account-level sizing first, then allocates
quantities across lifecycle legs. Fractional and whole-share behavior is
captured in the resolved risk result so the Account/Broker capability can drive
quantity rounding.

OrderManager can create SignalPlan child orders from RiskResolver leg
allocations while preserving:

- account_id
- deployment_id
- strategy_id
- strategy_version_id
- signal_plan_id
- opening_signal_plan_id
- current_signal_plan_id
- position_lineage_id
- account_evaluation_id
- governor_decision_id
- leg_label
- lifecycle_intent

## Broker-Native Alpaca Boundary

Alpaca broker-native bracket/OCO/OTO support must not be assumed to cover the
full Ultimate Trader lifecycle model.

The current backend explicitly rejects broker-native multi-leg requests when the
request attempts to express:

- multiple take-profit targets inside one native bracket order
- multiple stops inside one native bracket order
- runner behavior as a native broker multi-leg concept

This keeps the core model honest:

- Multiple targets are first-class internally.
- Runner is first-class internally.
- A broker may still receive simple child orders through BrokerAdapter when the
  runtime submit/cancel workflow is ready.
- Broker-native multi-leg order classes remain behind capability preflight.

## Pending Exit Priority

The order ledger now exposes position-management priority helpers:

- `pending_position_management_orders(...)`
- `superseded_position_management_orders(...)`

Priority order:

```text
close / logical_exit: 100
stop / stop_loss / trail / breakeven: 80
target / take_profit / reduce / scale: 60
runner: 40
```

This means a strategy logical exit or close instruction can identify passive
position-management orders that should be cancelled or replaced before the
exit-now order is submitted.

## Files Inspected

- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/preflight.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/orders/manager.py`
- `backend/app/orders/models.py`
- `backend/app/risk_resolver/service.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
- `backend/tests/unit/orders/test_order_manager.py`

## Files Changed

- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/preflight.py`
- `backend/app/orders/manager.py`
- `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `Operations_Turtle_Shell_Artifacts/ALPACA_MULTILEG_AND_PENDING_EXIT_PRIORITY_AUDIT.md`

## Tests Added

- Reject broker-native multi-target bracket requests with a specific advisory.
- Reject runner as a broker-native multi-leg concept.
- Logical exit supersedes passive position-management orders.
- Target does not supersede higher-priority stop protection.

## Risks

- Automatic cancellation/replacement is not yet wired into runtime submission.
- Broker-native bracket/OCO support remains disabled until capability-specific
  adapter support is implemented.
- Same-symbol multiple active lineages on one Account still need ambiguity
  handling before automatic exit submission can be considered complete.
- Internal child-leg broker submission remains gated until BrokerSync
  reconciliation and cancel/replace ordering are fully wired.

## Specialist Review Findings

The Alpaca Agent, Angry Architect, and seasoned trader review all reached the
same practical conclusion:

```text
The domain and ledger contracts are acceptable.
Automatic live submission of lifecycle child legs is not yet acceptable.
```

Required before automatic multi-leg submission:

- Leg-specific order shapes must be translated. A stop leg cannot inherit the
  entry order type; target, stop, trail, and runner legs need their own broker
  order shape.
- Pending passive exits must be cancelled or confirmed inactive before a close
  or logical_exit order can be submitted.
- Cancel requests for superseded position-management orders need a path that is
  allowed to cancel protective orders intentionally.
- BrokerSync-confirmed position quantity must cap active pending exit quantity
  after partial fills, stale streams, rejects, and cancel failures.
- Same-symbol multiple active Position lineages on one Account need ambiguity
  blocking or explicit lineage selection.
- Runtime must not treat `ExecutionIntent` sizing as the real forward sizing
  boundary.
- Preflight rejection must remain operator-facing internal truth and must not be
  confused with broker-originated rejection truth.

These findings do not invalidate the contract slice. They define the next live
execution gate.

## Architectural Review

Approved for this slice:

- No second runtime root was created.
- BrokerAdapter remains the only broker submission boundary.
- BrokerSync remains the only broker truth writer.
- SignalPlan remains the lifecycle owner.
- Account-specific execution still passes through Account Evaluation,
  RiskResolver, Governor, and OrderManager.

## Next Action

Wire the pending-exit priority helper into the runtime order submission path:

1. Before submitting a close or logical_exit order, find superseded passive
   orders for that Account-owned Position lineage.
2. Request cancellation through BrokerAdapter only.
3. Let BrokerSync confirm cancellation truth.
4. Submit the exit-now order only through the approved OrderManager and
   BrokerAdapter path.
