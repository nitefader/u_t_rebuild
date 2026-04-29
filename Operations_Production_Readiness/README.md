# Operations Production Readiness

Authority docs in this folder describe the work required to take the
Ultimate Trader rebuild from its current half-aligned state to full
production readiness against the locked doctrine in
[../AGENTS.md](../AGENTS.md), [../docs/ULTIMATE_TRADER_MANDATE.md](../docs/ULTIMATE_TRADER_MANDATE.md),
and the architecture set under [../docs/architecture/](../docs/architecture/).

This folder is operator-facing. It must remain readable, copyable, and
short.

## Purpose

One canonical place that answers, for any agent or operator:

- What the system is right now
- Where it diverges from doctrine
- What must be deleted, renamed, rebuilt, preserved
- Who does each piece of work
- What "ready to ship" means for each surface
- How readiness is verified end-to-end

## Sister operation

Operation Turtle Shell (folder
[../Operations_Turtle_Shell_Artifacts/](../Operations_Turtle_Shell_Artifacts/))
owns the backend doctrine spine — runtime, decision, orders,
governor, risk resolver, brokers, broker sync, runtime
persistence. That operation's Coordinator is actively driving the
backend; this operation is the **complement** (frontend full
redesign, user-facing CRUD layer, dashboard, operator runbook,
cutover plan, cross-doc consistency).

Any slice that touches files in the backend doctrine spine must
be coordinated with the Turtle Shell Coordinator before it
proceeds. See
[HANDOFF_PROTOCOL.md](./HANDOFF_PROTOCOL.md) for the rule.

## Read order

1. [README.md](./README.md) — this file
2. [HANDOFF_PROTOCOL.md](./HANDOFF_PROTOCOL.md) — discipline any agent must follow on this operation
3. [PRODUCTION_READINESS_GUARDRAILS.md](./PRODUCTION_READINESS_GUARDRAILS.md) — non-negotiable rules
4. [OPERATION_STATUS.md](./OPERATION_STATUS.md) — live status board, mandatory start/heartbeat/end updates
5. [CURRENT_STATE_AUDIT.md](./CURRENT_STATE_AUDIT.md) — what exists today (with coordination notes vs. Turtle Shell)
6. [FRONTEND_STRUCTURE_DECISION.md](./FRONTEND_STRUCTURE_DECISION.md) — full redesign call + design language
7. [BACKEND_STRUCTURE_DECISION.md](./BACKEND_STRUCTURE_DECISION.md) — preserve / refactor / rebuild calls; coordinate with Turtle Shell
8. [API_AND_READ_MODEL_GAPS.md](./API_AND_READ_MODEL_GAPS.md) — what every UI surface needs from the backend
9. [PRODUCTION_READINESS_EXECUTION_PLAN.md](./PRODUCTION_READINESS_EXECUTION_PLAN.md) — sliced execution plan (frontend + coordinated backend asks)
10. [AGENT_TASK_MATRIX.md](./AGENT_TASK_MATRIX.md) — Claude / Codex / Cursor / VS Code assignment
11. [TESTING_AND_ACCEPTANCE_PLAN.md](./TESTING_AND_ACCEPTANCE_PLAN.md) — proof of correctness
12. [CUTOVER_AND_RELEASE_PLAN.md](./CUTOVER_AND_RELEASE_PLAN.md) — local → paper → live

## Scope

In scope:

- Backend domain, runtime, decision, governor, risk resolver, orders,
  brokers, broker_accounts, market_data, ai, operations, persistence,
  api routes, server wiring, tests
- Frontend pages, modules, API client, state, routes, build, tests
- Docs alignment to current code reality

Out of scope:

- New broker providers beyond Alpaca paper/live (Alpaca-only for V1)
- New asset classes beyond US equities (V1)
- Mobile apps
- Replacing AI advisor with autonomous AI execution (doctrine forbids)
- Re-introducing the Program product entity in any V1 user-facing path

## Non-negotiables

These are inherited from `AGENTS.md` and the mandate. They are gates,
not preferences:

1. One platform. Paper and live are Account metadata only.
2. Ownership: Strategy → Deployment → SignalPlan → Account Evaluation →
   RiskResolver → Governor → OrderManager → BrokerAdapter → BrokerSync →
   Position. Anything that crosses these boundaries is rejected.
3. Deployment evaluates Watchlist for entries and Account-owned
   Positions (filtered by `deployment_id`) for exits. Deployment never
   tracks position state itself.
4. SignalPlans are emitted by Deployment. They are neutral, event-based,
   carry lineage (`deployment_id`, `strategy_id`, `position_lineage_id`
   when applicable), and never carry final Account quantity, broker
   identifiers, or Account approval flags.
5. RiskResolver is the first place where Account-specific quantity or
   notional exists. Governor is the final gate. OrderManager creates
   internal orders. BrokerAdapter is the only submission boundary.
   BrokerSync is the only broker truth writer.
6. AI is advisory. AI may explain. AI may not approve, reject, size,
   submit, cancel, or mutate Account truth.
7. No silent failure. No silent success for mission-critical actions.
8. No hidden runtime paths. One supervisor, one dispatcher, one hub
   registry, one live stock market data stream, one trade sync per
   Account.
9. No banned product names in active code or active UI: Program,
   Account Governor, Services Center, Paper Runtime / Live Runtime as
   separate products, Deployment per Account, Strategy Account, Broker
   SubAccount, Market Data Service Center.
10. Production-grade only. Every slice ships its final production shape.
    No temporary paths, no patching, no forking, no throwaway work
    (carried over from operator memory).

## Definition of done

Production readiness is reached only when every item below is true,
demonstrated, and persisted:

- Backend runtime spine is `Strategy → Deployment → SignalPlan →
  AccountSignalPlanEvaluation → RiskResolver → Governor → OrderManager
  → BrokerAdapter → BrokerSync → Position`. ExecutionIntent and
  ProgramVersion are removed from the production path.
- Each step writes its own decision/state record with full lineage:
  SignalPlan, AccountSignalPlanEvaluation, GovernorDecisionTrace,
  InternalOrder (with `signal_plan_id`, `opening_signal_plan_id`,
  `position_lineage_id`), Trade, BrokerSync truth, Position lineage.
- Every Account has Account Trade Sync that starts at boot regardless
  of pause / subscription state, and surfaces explicit health to
  Operations.
- The platform live stock market data stream starts at boot when
  enabled, and surfaces explicit health.
- Frontend exposes the nine mandated surfaces — Dashboard, Strategies,
  Components, Watchlists, Accounts, Deployments, Operations, Providers,
  Settings — and the deeper detail panels (Orders, Trades, Positions,
  SignalPlans, Chart Lab, Backtests, Optimizations, Walk-Forward, Sim
  Lab) behind drill-ins.
- Every Account-owned position has a working `Explain this position`
  action backed by the canonical `PositionExplanationContext`.
- Operator runbook (Day Zero) passes end-to-end on a paper Account
  without manual log fishing.
- Test pyramid: unit + integration + frontend + broker-safe E2E +
  simulation regression — all green. Lint guardrails for banned names
  and ownership boundaries pass.
- Cutover plan rehearsed locally and on paper before any live Account
  is enabled.

## How to use this folder

- Update [OPERATION_STATUS.md](./OPERATION_STATUS.md) at every meaningful
  state change (start, blocker, completion, approval).
- Treat the other docs as authority. If reality drifts, update the
  doc *and* note the change in the implementation log; do not let
  reality and doc diverge silently.
- Anything missing or ambiguous in this folder is escalated to Nanyel
  (the operator) before code is written. Do not invent doctrine.
