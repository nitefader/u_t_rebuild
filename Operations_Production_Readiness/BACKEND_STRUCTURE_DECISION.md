# Backend Structure Decision

## Decision

**Refactor the runtime spine end-to-end. Preserve broker, persistence,
operations, market_data, ai, and broker_accounts foundations. Rebuild
only what is doctrine-banned (Program-centric runtime) and replace
what is missing (DeploymentPublisher, AccountSignalPlanEvaluator,
PositionLineage service).**

The domain contracts for SignalPlan / AccountSignalPlanEvaluation /
GovernorDecisionTrace / RiskResolverResult / PositionExplanationContext
are already correct. The work is to *produce* them in the production
path and to retire `ProgramVersion` / `ResolvedProgramComponents` /
`ExecutionIntent` from that path.

## Module-by-module call

| Module | Decision | Rationale |
|---|---|---|
| `domain/` (SignalPlan, RiskResolverResult, GovernorDecisionTrace, PositionExplanationContext, StrategyVersion, TradingMode) | Preserve | Already doctrine-correct |
| `domain/program.py`, `domain/risk_profile.py`, `domain/execution_style.py`, `features/ResolvedProgramComponents` | Quarantine then delete | Banned product entity; replace with Strategy + Deployment + AccountRiskConfig |
| `domain/strategy_controls.py`, `domain/universe.py` | Refactor | Repoint at Strategy and Watchlist instead of Program |
| `domain/research_evidence.py` | Preserve | Backtest / Sim Lab / Promotion contracts are clean |
| `decision/signal_engine.py` | Preserve | Internal evaluator; output remains `CandidateTradeIntent` for now |
| `decision/signal_plan_builder.py` | Preserve and wire | Already correct; needs to be called by DeploymentPublisher |
| `risk_resolver/service.py` | Refactor inputs | Replace Static/Lifecycle sizing placeholders with `AccountRiskConfig`-driven sizing |
| `governor/service.py` | Refactor | Accept `(SignalPlan, RiskResolverResult, AccountContext)`, emit `GovernorDecisionTrace` |
| `orders/manager.py` | Refactor entrypoint | Accept `(SignalPlan, RiskResolverResult, GovernorDecisionTrace, AccountContext)`; legacy `ExecutionIntent` path removed |
| `orders/ledger.py`, `orders/trade_ledger.py` | Preserve | Persistence / lineage columns already in schema |
| `runtime/engine.py` | Rebuild | Replace per-Deployment `RuntimeEngine` with a thin `DeploymentPublisher` runtime that emits SignalPlans |
| `runtime/account_trading_orchestrator.py`, `pipeline/orchestrator.py` | Consolidate | One supervisor + one publisher loop. Multi-Account fan-out happens in the publisher → AccountSignalPlanEvaluator chain |
| `runtime/recovery_orchestrator.py` | Refactor | Replay is now SignalPlan-aware (re-emit unfinished SignalPlans, re-evaluate on resume) |
| `runtime/runtime_context.py` (singletons, bootstrap) | Preserve | Already production-grade |
| `brokers/` (adapter, alpaca, fake, sync, stream, capabilities, preflight) | Preserve | Boundaries are correct |
| `broker_accounts/` (service, credential_store, runtime_service) | Preserve and extend | Add `AccountRiskConfig`, `AccountRestrictions`, `AccountKillSwitch` modelled per Account |
| `market_data/` | Preserve | Hub / resolver / catalog work; only operator labels change |
| `ai/` (catalog, providers, runtime, validation) | Preserve and extend | Add `explain_position` advisory call backed by `PositionExplanationContext` |
| `chart_lab/` | Preserve | Streaming preview is a drill-in for Strategy authoring |
| `simulation/` | Preserve | Sim Lab + Backtest engine; needs API surface |
| `promotion/` | Refactor | Re-key from Program-frozen to StrategyVersion-frozen + Deployment evidence |
| `operations/` | Refactor | Add SignalPlan timeline, AccountSignalPlanEvaluation timeline, GovernorDecisionTrace timeline, position explanation surface |
| `persistence/` | Extend schema | Add tables for strategies, watchlists, deployments, signal_plans, account_signal_plan_evaluations, governor_decision_traces, account_risk_configs, position_lineages |
| `api/routes/` | Extend | New routes per `API_AND_READ_MODEL_GAPS.md` |
| `tests/` | Extend | Per `TESTING_AND_ACCEPTANCE_PLAN.md` |

## Target runtime spine (production)

```
Strategy (config)
  → Watchlist (eligible-symbol source, possibly dynamic)
    → Deployment (publishes; runtime status; subscribed Accounts)
      ↓ on each evaluation tick
      DeploymentPublisher
        evaluate_entries(watchlist)  → SignalPlan(open, ...)
        evaluate_exits(positions_filtered_by_deployment_id)
                                     → SignalPlan(close|reduce|target|stop|trail|breakeven|runner|logical_exit, ...)
      ↓ for each subscribed Account
      AccountSignalPlanEvaluator
        ↓
        RiskResolver (Account-specific resolved quantity / leg allocations)
        ↓
        Governor (Account context, broker freshness, restrictions, exposure caps)
        → GovernorDecisionTrace
        ↓ if approved
        OrderManager (creates InternalOrder with full lineage)
          → BrokerAdapter (submit / cancel / replace)
            ← BrokerSync (broker truth: orders, fills, positions, account snapshots)
              → Position lineage updated and explainable
```

## DeploymentPublisher (new, replaces RuntimeEngine for production)

Responsibilities:

- Resolve current Watchlist symbols for a Deployment (static or
  dynamic).
- Resolve open Positions across all subscribed Accounts filtered by
  `deployment_id` (read from Account-owned position truth — never the
  Deployment's own state).
- For each eligible symbol in Watchlist, call the Strategy's signal
  engine; if a candidate fires, build an opening `SignalPlan`.
- For each open Position, call the Strategy's exit logic; if a
  position-management candidate fires, build a related `SignalPlan`
  with `opening_signal_plan_id` and `related_position_lineage_id`.
- Emit `SignalPlan` records to the persistence layer with status
  `CREATED` → `PUBLISHED`.
- The Deployment never tracks its own positions, never sizes, never
  decides Account participation. It is pure publisher.

Constraints:

- One Deployment, one publisher loop. No per-Account duplication.
- The publisher runs only when its Deployment is `ACTIVE` and not
  `PAUSED` / `BLOCKED` / `RECOVERING`.
- The publisher is idempotent per `(deployment_id, evaluation_tick,
  symbol, intent)` so re-runs from recovery do not duplicate
  SignalPlans.

## Deployment entry / exit model

Deployment must:

- Build entries from the **Watchlist** snapshot (the "what we can
  enter" set), evaluated through the Strategy's entry rules.
- Build exits from **Account-owned Positions** filtered by
  `deployment_id` (the "what we already own through this Deployment"
  set), evaluated through the Strategy's exit rules.

Deployment must not:

- Own positions or pretend to know broker truth.
- Track open trades internally.
- Generate exits from the Watchlist.
- Generate entries from positions.
- Be duplicated per Account.

If the same Deployment publishes one SignalPlan, multiple Accounts
each evaluate independently and decide for themselves. One can
participate, another can ignore, a third can defer.

## SignalPlan ownership

- SignalPlans are owned by `Deployment`, identified by
  `signal_plan_id`, carry `deployment_id`, `strategy_id`,
  `strategy_version_id`. Optional: `watchlist_snapshot_id`,
  `opening_signal_plan_id`, `related_position_lineage_id`.
- SignalPlans are stateless from the Account's perspective. Status
  (`CREATED`, `PUBLISHED`, `EXPIRED`, `EXECUTED`, `SUPERSEDED`,
  `CANCELED`, `FAILED`) is the publisher's view of its own emission
  lifecycle, not the Account's.
- Account decisions live in `AccountSignalPlanEvaluation`, separate
  record.

## Account Evaluation

`AccountSignalPlanEvaluator` is per-Account, per-SignalPlan:

1. Decide participation: `PARTICIPATE | IGNORE | REJECT | DEFER |
   REQUIRES_OPERATOR`.
2. If participating, call `RiskResolver` with this Account's
   `AccountRiskConfig`, current Position context (filtered by
   `deployment_id` and lineage), buying power, fractional capability,
   broker restrictions.
3. If RiskResolver returns `allowed`, call `Governor` with
   `(SignalPlan, RiskResolverResult, AccountContext, broker
   freshness)`.
4. If Governor approves, call `OrderManager.create_order` with the
   full lineage tuple.

The evaluator must:

- Persist `AccountSignalPlanEvaluation` for *every* SignalPlan it
  considers, including IGNORE and REJECT decisions, with full
  `rejection_reasons`.
- Be idempotent per `(account_id, signal_plan_id)` — re-running on
  recovery must not double-submit orders.

## RiskResolver

Inputs become Account-driven (replace `StaticSizingInput` /
`LifecycleSizingInput`):

- `AccountRiskConfig`: sizing method (fixed shares, fixed dollar,
  risk-percent equity), risk per trade, max position size, max
  concentration, fractional allowed, whole-share rounding policy.
- `AccountSnapshot`: equity, buying power, day P&L, current open
  positions count.
- `BrokerCapabilityProfile`: fractional supported, extended hours,
  market hours, asset support.

Outputs (already correct): `RiskResolverResult` with
`resolved_quantity`, `resolved_notional`, `leg_allocations`,
`buying_power_required`, `existing_position_context`, `violations`,
`warnings`.

## Governor

Inputs become canonical:

- `SignalPlan` (read-only).
- `RiskResolverResult`.
- `AccountContext` (paused, killed, restrictions, snapshot, sync
  freshness).
- `Deployment runtime status` (paused / blocked / active).
- `GovernorPolicy` (global kill, exposure caps, max positions,
  concentration caps, daily loss cap, drawdown cap).

Outputs:

- `GovernorDecisionTrace` with `governor_decision_id`,
  `account_id`, `signal_plan_id`, `status`, `approved`, `reasons`,
  `violations`, `warnings`, `evaluated_at`. The legacy
  `GovernorDecision` becomes an internal helper or is deleted.

Persistence: every governor decision is durable, queryable by
Account, Deployment, SignalPlan, and time.

## OrderManager

Single entrypoint for SignalPlan-driven orders:

```python
OrderManager.create_orders_from_evaluation(
    account_id,
    signal_plan,
    risk_result,
    governor_trace,
)  -> tuple[InternalOrder, ...]
```

For an opening SignalPlan with stop / targets / runner, this returns
the entry order plus the protective leg orders, all tied to the same
`opening_signal_plan_id`, `position_lineage_id`, and
`account_evaluation_id`.

The legacy `create_order(execution_intent=...)` path is deleted from
production. Manual-trade keeps its own simpler entrypoint
(`create_manual_order`) but the lineage columns are populated where
applicable.

## BrokerAdapter and BrokerSync

No structural change. Already doctrine-aligned. The only delta:

- BrokerSync writes broker truth to the `broker_*` tables and emits
  events that the Position lineage service consumes to update its
  view (`PositionLineage` record).
- The Account-owned position view, queryable by `(account_id,
  deployment_id, position_lineage_id)`, is the truth source for
  Deployment exit evaluation.

## Position Lineage service (new)

Responsibility:

- Maintain a per-Account `PositionLineage` record per opening
  SignalPlan that resulted in fills.
- Track current quantity, average entry, related SignalPlans
  received, governor decisions applied, orders, fills, active stop /
  targets / runner / logical-exit state, sync freshness.
- Build `PositionExplanationContext` on demand (already a domain
  contract).

Reads:

- BrokerSync state (positions, fills, sync freshness).
- OrderLedger and TradeLedger for fills.
- AccountSignalPlanEvaluation history for related SignalPlans.

Writes (only its own table):

- `position_lineages(position_lineage_id, account_id, deployment_id,
  strategy_id, opening_signal_plan_id, ...)`.

## Persistence additions

```sql
strategies(strategy_id, name, status, created_at, payload TEXT)
strategy_versions(strategy_version_id, strategy_id, version, status,
  frozen_at, payload TEXT)
watchlists(watchlist_id, name, kind, created_at, payload TEXT)
watchlist_snapshots(watchlist_snapshot_id, watchlist_id, taken_at,
  payload TEXT)
deployments(deployment_id, name, strategy_version_id,
  watchlist_id_set TEXT, subscribed_account_id_set TEXT,
  status, runtime_overrides TEXT, created_at)
signal_plans(signal_plan_id, deployment_id, strategy_id,
  strategy_version_id, symbol, side, intent, status,
  opening_signal_plan_id, related_position_lineage_id, created_at,
  payload TEXT)
account_signal_plan_evaluations(evaluation_id, account_id,
  signal_plan_id, deployment_id, status, participation_decision,
  rejection_reasons TEXT, created_at, evaluated_at, payload TEXT)
governor_decision_traces(governor_decision_id, account_id,
  signal_plan_id, status, approved INTEGER, reasons TEXT,
  violations TEXT, warnings TEXT, evaluated_at)
account_risk_configs(account_id, version, payload TEXT, updated_at)
account_restrictions(account_id, version, payload TEXT, updated_at)
position_lineages(position_lineage_id, account_id, deployment_id,
  strategy_id, opening_signal_plan_id, current_quantity,
  current_signal_plan_ids TEXT, payload TEXT, updated_at)
```

Indexes: by `account_id`, `deployment_id`, `signal_plan_id`,
`(account_id, deployment_id)`, `(account_id, position_lineage_id)`,
`evaluated_at`.

The existing `internal_orders` table already has the lineage columns
needed.

## Existing strengths to keep verbatim

- `runtime_context.py` boot-time stream / dispatcher / manual-trade
  composition.
- `BrokerCredentialStore` (AES-GCM encryption, stable
  fingerprinting).
- `BrokerSync.apply_result` and reconcile semantics.
- `OperationsCenterService` projection model — extend rather than
  rewrite.
- `ControlPlane` cancellation scopes, kill, pause, resume gating.
- `manual_trade` route idempotency, audit, preflight.

## Production gaps (full list)

1. Strategies CRUD service + persistence + API.
2. Watchlists CRUD service + persistence + API + dynamic-rule
   evaluator.
3. Deployments CRUD service + persistence + API + lifecycle
   (start/stop/pause/resume/subscribe Accounts).
4. DeploymentPublisher runtime that emits SignalPlans.
5. SignalPlan persistence and read-model (per-Deployment,
   per-Account, per-symbol, timeline).
6. AccountSignalPlanEvaluator service + persistence + read-model.
7. AccountRiskConfig + AccountRestrictions modelled per Account
   with API.
8. Governor that consumes SignalPlan and produces
   GovernorDecisionTrace; trace persistence; trace timeline read.
9. PositionLineage service + persistence + read-model + Explain API.
10. AI advisory `explain_position` endpoint backed by
    `PositionExplanationContext`.
11. Promotion gate re-keyed to StrategyVersion-frozen + Deployment
    evidence (the existing service can be refactored, not rebuilt).
12. Operations Center extensions: SignalPlan timeline, evaluation
    timeline, governor decision timeline, position explanation panel.
13. Lint guardrails: forbid Program-centric imports in production
    runtime path; forbid banned product names in API responses.
14. Migration: a one-time job that translates any persisted
    Program-style records into Strategy/Deployment records, or refuses
    to start with a clear operator error if migration is incomplete.

## Things explicitly *not* to do

- Do not introduce a Program migration shim that lives forever.
  Either migrate or fail to boot — production-grade only.
- Do not build a separate "paper" runtime. Paper and live are
  Account metadata, not separate runtimes.
- Do not give the Deployment any Account-specific knowledge beyond
  subscribed Account ids.
- Do not let Chart Lab, Sim Lab, Backtests, Optimization,
  Walk-Forward, or AI submit broker orders.
- Do not introduce a SignalPlan TTL/cache that hides expired plans.
  An expired SignalPlan is operator-visible, full stop.
