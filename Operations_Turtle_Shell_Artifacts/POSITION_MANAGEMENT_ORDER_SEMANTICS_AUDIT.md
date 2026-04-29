# Position Management Order Semantics Audit

Last updated: 2026-04-26 23:43:59 -04:00

Operation: Turtle Shell

Decision: FIX REQUIRED, then corrected in this slice.

## Review Roles

- Coordinator: implementation owner and architectural gate.
- Alpaca Agent: broker-facing order direction and preflight review.
- Seasoned Quant Trader: position lifecycle semantics review.
- Full Backend Engineer: runtime/order lineage and shim review.
- Front End Experience / Fullstack Review: covered by coordinator locally due
  active agent thread limit.

## Current Behavior Found

- `SignalPlan.side` represents intended position bias, not broker action.
- `InternalOrder.side` is broker action encoded as:
  - `CandidateSide.LONG` -> Alpaca `buy`
  - `CandidateSide.SHORT` -> Alpaca `sell`
- `AlpacaBrokerAdapter` correctly stays a pure broker boundary mapper and does
  not inspect lifecycle intent.
- `OrderManager.create_signal_plan_order(...)` is the canonical SignalPlan order
  handoff.
- `RuntimeOrchestrator` now reads Account-owned Positions for deployment-scoped
  exits and passes Account-specific position lineage.

## Gaps Found

- Position-management orders were at risk of using `SignalPlan.side` directly,
  causing long exits to become broker buys and short exits to become broker
  sells.
- Legacy `OrderManager.create_order(...)` could still turn an
  `ExecutionIntent` exit into the entry-side broker action.
- `process_protective_intent(...)` minted synthetic position lineage instead of
  resolving a real active Account-owned Position.
- Account-specific opening SignalPlan lineage was not passed into order creation
  for multi-account exits.
- Governor protective bypass did not include all SignalPlan-native lifecycle
  intents.
- Market-rule preflight treated a sell-to-close long exit as a new short when
  checking shortability.

## Semantic Rules Locked

Broker-facing order side is derived from Account-owned Position truth:

| Position | Opening Order | Position-Management Order |
| --- | --- | --- |
| Long | buy | sell |
| Short | sell | buy |

`SignalPlan.side` remains neutral position bias. `InternalOrder.side` is broker
action.

Management intents:

- `close`
- `reduce`
- `target`
- `stop`
- `trail`
- `breakeven`
- `runner`
- `logical_exit`
- legacy `tp`
- legacy `sl`
- legacy `scale`

are not opens and must not be evaluated as new entries.

## Corrections Made

- `OrderManager.create_signal_plan_order(...)` now accepts:
  - `position_side`
  - `opening_signal_plan_id`
- Non-open SignalPlan orders invert the Account Position side:
  - long position -> broker sell
  - short position -> broker buy
- Position-management SignalPlan orders require real opening SignalPlan lineage.
- Legacy `OrderManager.create_order(...)` now also inverts side for non-open
  ExecutionIntent paths.
- `RuntimeOrchestrator` now passes Account-specific:
  - `position_lineage_id`
  - `opening_signal_plan_id`
  - `position_side`
- `process_protective_intent(...)` now resolves an active Account-owned Position
  and blocks without order creation when no active lineage is found.
- `PortfolioGovernor` now treats all position-management intents as protective
  exits for pause/global-kill purposes.
- Broker and market preflight now carry `is_position_management` so a sell to
  close a long position is not rejected as a new short.

## Files Inspected

- `backend/app/orders/manager.py`
- `backend/app/orders/models.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/preflight.py`
- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/sync.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/app/governor/service.py`
- `backend/app/domain/signal_plan.py`
- `backend/app/decision/signal_plan_builder.py`
- `backend/app/risk_resolver/service.py`
- `backend/app/api/routes/manual_trade.py`
- `backend/app/operations/models.py`

## Files Changed

- `backend/app/orders/manager.py`
- `backend/app/brokers/capabilities.py`
- `backend/app/brokers/preflight.py`
- `backend/app/governor/service.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `backend/tests/unit/brokers/test_alpaca_preflight_service.py`
- `backend/tests/unit/governor/test_portfolio_governor.py`
- `Operations_Turtle_Shell_Artifacts/POSITION_MANAGEMENT_ORDER_SEMANTICS_AUDIT.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`

## Tests Added

- Long position management orders sell.
- Short position management orders buy to cover.
- All SignalPlan-native management intents use exit-side semantics.
- Management orders require opening SignalPlan lineage.
- Legacy ExecutionIntent exits invert side.
- Alpaca adapter translates long exits to sell and short exits to buy.
- Market rules do not treat sell-to-close as a new short.
- Governor allows all position-management intents during kill/pause.
- Runtime preserves Account-specific opening lineage, position lineage, and side.
- Protective shim creates no order without active Account Position lineage.

## Architectural Review

Approved for this slice.

The correction keeps one runtime root, keeps SignalPlan neutral, keeps Account as
owner of Position truth, keeps BrokerAdapter as the submission boundary, and
keeps BrokerSync as the broker-truth writer.

## Remaining Risks

- Manual operator close/reduce still depends on the operator/API side meaning
  broker action. This needs a later operator-experience review so manual close
  can optionally derive side from selected Account Position.
- Quantity semantics for target/reduce/runner are still simple quantity inputs.
  A later RiskResolver slice should derive percent/scope quantities from
  lifecycle metadata and pending exit orders.
- Multiple active same-symbol lineages on one account can still require stronger
  lineage selection when a Strategy emits symbol-level exit conditions.
