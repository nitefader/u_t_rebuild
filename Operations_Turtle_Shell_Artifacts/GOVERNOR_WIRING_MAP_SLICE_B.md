# Slice B MAP — Account Multi-RiskPlan + Horizon Vocabulary + Deployment.risk_horizon + Frontend

Owner: Claude (operator override; both backend AND frontend per operator directive 2026-04-29 18:50ish).
Started: TBD (immediately after Slice A closes).
Operator basis: Nanyel — *"You own backend and frontend for this work. Slices. Slices. Slices. Get it done!"* + locked Risk Horizon doctrine (this doc).
Doctrine references: `HANDOFF_PROTOCOL.md`, `TURTLE_SHELL_GUARDRAILS.md`, `GOVERNOR_WIRING_MAP.md`, `RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT.md`, `MY_COMMAND_EXECUTION_PLAN_PERSISTENCE_AND_LABS.md`.

---

## 0 · Locked Risk Horizon Doctrine (operator-locked 2026-04-29)

> Deployment chooses horizon. Account chooses risk plan. Governor enforces.

- A Deployment declares its `risk_horizon` ∈ `{ scalping | intraday | swing | position | other }`.
- Each Account owns an `AccountRiskPlanMap`: `horizon → RiskPlanVersion`.
- When a Deployment publishes a SignalPlan, each subscribed Account independently resolves: `Account.risk_plan_for_horizon[Deployment.risk_horizon] → RiskResolver → Governor`.
- Two Accounts subscribed to the same Deployment can resolve different RiskPlans for the same horizon.
- If an Account has no RiskPlan for the Deployment's horizon and no fallback, the Account must reject the SignalPlan.
- The operator must see which RiskPlan each Account resolved for the Deployment.

---

## 1 · What Slice A left dangling (Slice B's mandate)

Slice A shipped the **Governor resolver** with a `(account_id, horizon)` lookup signature, but the lookup itself returns `None` for every input today. That's intentional — the **AccountRiskPlanMap entity does not exist yet**. Slice B brings it into existence and wires the production path so the resolver actually has data to consume.

Concretely Slice B must ship:

1. **Vocabulary**: extend `TradingHorizon` enum with `OTHER` so Deployments can declare horizons not yet codified. (Doctrine change to enum; treat as additive — `INTRADAY`/`SWING`/`POSITION`/`SCALPING` stay.)
2. **Persistence (NEW saved entity — Angry Architect approval gate)**: `account_risk_plan_map` table, `(account_id, horizon, risk_plan_version_id)`. UNIQUE index on `(account_id, horizon)`.
3. **Deployment field**: add `risk_horizon: TradingHorizon | None = None` to `Deployment` model. Default `None` so legacy deployments fall back to `StrategyControls.trading_horizon`.
4. **Lookup wiring**: composition root reads the map and constructs the `get_risk_plan_config_for_horizon` callable for the orchestrator. Account-side lookup wiring already lives in Slice A.
5. **Rejection rule**: when `(account_id, deployment.risk_horizon)` has no map entry AND no fallback, Governor must reject with `rule_id="account_missing_risk_plan_for_horizon"`. New rule added to `service.py`.
6. **Trace visibility**: `GovernorDecisionTrace.projected_state` must carry `resolved_risk_plan_id` / `resolved_risk_plan_version_id` so Operations can show "this Account used Plan X for this Deployment".
7. **Frontend Account Risk Card**: 5 per-horizon dropdowns (Scalping / Intraday / Swing / Position / Other), each loading from `RiskPlansApi.list()`. Save via new `PUT /api/v1/broker-accounts/{id}/risk-plan-map`.
8. **Frontend Deployment risk_horizon picker**: single `Select` on the Deployment create/edit drawer.
9. **Frontend Operations visibility**: AccountSignalPlanEvaluation row shows the resolved RiskPlan name (drill-down to plan detail).

---

## 2 · Decision Log (locked at slice start; updated as decisions land)

| # | Decision | Reasoning |
|---|---|---|
| D1 | `OTHER` horizon for catch-all | Operator listed Day Trading + Other in their original message; Day Trading = `intraday`, Other = catch-all for strategies that don't fit a horizon. |
| D2 | `account_risk_plan_map` is a separate table with `(account_id, horizon)` unique key | Mirrors `account_risk_configs` pattern. Avoids stuffing JSON into the BrokerAccount row. Enables single-row updates per horizon. |
| D3 | `Deployment.risk_horizon` is nullable; falls back to `StrategyControls.trading_horizon` | Backwards-compat. Existing deployments don't have to be migrated. |
| D4 | NEW Governor reject rule `account_missing_risk_plan_for_horizon` | Per locked doctrine. Cannot proceed without an explicit RiskPlan for the horizon. |
| D5 | No "default fallback RiskPlan" at the Account level | The contract's `Account.default_risk_plan_id` is the V1 escape hatch but the operator's locked doctrine says per-horizon mapping is the way. Fallback would erode safety. (TBD: revisit if operator wants a wildcard fallback.) |
| D6 | Trace adds `resolved_risk_plan_id` and `resolved_risk_plan_version_id` to `projected_state` (the existing `dict[str, object]` blob) | No new schema needed; the projected_state dict is already untyped. |
| D7 | Per-horizon save is atomic per row, not whole-map-replace | Operator can change Swing without touching Scalping. UI saves on blur per dropdown. |

---

## 3 · Parallel agent fanout

To minimize wall-clock + cost (operator directive), this slice runs as TWO parallel sub-agents, each receiving the full doctrine + a non-overlapping task scope.

### Agent B-Backend (sonnet)
**Files** (new): `backend/app/broker_accounts/risk_plan_map_models.py`, `backend/app/broker_accounts/risk_plan_map_persistence.py`, `backend/tests/unit/broker_accounts/test_risk_plan_map.py`.
**Files** (edit): `backend/app/persistence/runtime_store.py` (CREATE TABLE for `account_risk_plan_map`), `backend/app/api/routes/broker_accounts.py` (`GET/PUT /api/v1/broker-accounts/{id}/risk-plan-map`), `backend/app/domain/strategy_controls.py` (add `OTHER` to `TradingHorizon`), `backend/app/deployments/models.py` (add `risk_horizon` field), `backend/app/governor/service.py` (new rejection rule), `backend/app/pipeline/orchestrator.py` (wire production lookup callable).

**Acceptance**:
- New table exists, persists per-row by `(account_id, horizon)`
- Routes pass contract test
- New Governor rejection rule has unit test
- `OTHER` enum value works in Pydantic
- Composition-root wiring populates the lookup callable
- Full backend unit suite still green

### Agent B-Frontend (sonnet)
**Files** (edit): `frontend/src/api/risk.ts` + `frontend/src/api/schemas/risk.ts` (add `getRiskPlanMap` / `updateRiskPlanMap`), `frontend/src/routes/RiskCardPanel.tsx` (5 per-horizon dropdowns), `frontend/src/routes/Deployments.tsx` or the create/edit drawer (`risk_horizon` Select), `frontend/src/routes/Operations.tsx` (resolved-plan column on AccountSignalPlanEvaluation rows).
**Files** (new): `frontend/src/components/risk_plans/HorizonRiskPlanPicker.tsx` (reusable per-horizon dropdown).

**Acceptance**:
- Account Risk Card shows 5 dropdowns labelled Scalping / Intraday / Swing / Position / Other; each loads RiskPlans via existing `RiskPlansApi.list()`; each PUT saves on change
- Deployment drawer has a `Risk horizon` Select with the 5 enum values
- Operations evaluation row displays the resolved RiskPlan name when present
- Frontend typecheck clean; vitest passes; banned-name lint clean

### Agent B-Backend and Agent B-Frontend MUST coordinate on:
- The exact route paths and request/response shapes for `/api/v1/broker-accounts/{id}/risk-plan-map`. Backend agent SHIPS the route; frontend agent CONSUMES the route's existing shape (no new doctrine inventions on the frontend side).
- The horizon enum values and string serialization (`scalping | intraday | swing | position | other`). Backend agent OWNS the enum; frontend agent receives the literals.

---

## 4 · Acceptance Gates

Same shape as Slice A:
1. `pytest backend/tests/unit/broker_accounts backend/tests/unit/governor backend/tests/unit/pipeline -q` → all green
2. `pytest backend/tests/unit -q` → 1431+ passing (Slice A baseline) +N new tests
3. Frontend `npm run typecheck` clean; `npm test` passes; `lint:names` clean
4. Boundary suite `pytest backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/lint -q` green
5. Adversarial recursion #1 returns no BUG-severity findings (or all are fixed)
6. Adversarial recursion #2 returns no BUG-severity findings (or all are fixed)
7. LEDGER entries (`schema-added` for table; `route-added` for the new route; `frontend-consumed` for UI)
8. INBOX_CODEX heads-up updated with completion summary
9. LOCKS released
10. OPERATION_STATUS marked `handoff_ready`

---

## 5 · Out of scope (explicit non-goals for Slice B)

- ❌ Per-Deployment RiskPlan override (the contract's `AccountDeploymentRiskOverride`). Defer to Slice C.
- ❌ Wiring `max_daily_loss_pct` / `max_drawdown_pct` / `cooldown_after_loss_minutes` into the Governor. Those need a daily-state aggregator. Defer.
- ❌ The bracket-execution gap (`STRATEGY_TO_BROKER_BRACKET_PROGRAM`). Separate program.
- ❌ StrategyControls persistence. Separate program.
- ❌ Migrating existing Account default_risk_plan_id rows into the map. Operator can re-author from the UI; no data loss path needed for V1.
