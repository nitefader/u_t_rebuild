# Governor Wiring MAP — Operator-Edited Limits Reach the Final Gate

Owner: Claude (operator override into Codex-owned `backend/app/governor/`).
Started: 2026-04-29 18:42:51 -04:00.
Operator basis: Nanyel — *"Fix the governor and wire it properly end to end and recurse 2 times with two different agents to verify work. MAP style"*.
Doctrine references: `HANDOFF_PROTOCOL.md`, `TURTLE_SHELL_GUARDRAILS.md`, `COORDINATION/PROTOCOL.md`.

---

## T-6 Amendment (2026-04-30) — Resolver API consolidated for TOCTOU snapshot

The Bracket Program's T-6 (TOCTOU hardening) refactored the resolver's lookup contract from two independent callbacks (`get_account_risk_config` + `get_risk_plan_config_for_horizon`) to ONE composite callback (`get_policy_inputs(account_id, horizon) -> (AccountRiskConfig | None, RiskPlanConfig | None)`). Both halves of the snapshot now come from one call so the production `SQLiteRuntimeStore.load_governor_policy_inputs` can wrap both reads in a single connection + explicit read transaction (per `STRATEGY_TO_BROKER_BRACKET_PROGRAM.md` §7 D7).

The locked Risk Horizon doctrine in §0 below is unchanged. The Slice A wiring described in §3-§6 below still describes the *purpose* of each lookup correctly; only the *signature* moved. Anywhere this MAP says "two callbacks" or quotes `get_account_risk_config` / `get_risk_plan_config_for_horizon`, read it as the single composite `get_policy_inputs` callback. The per-source DB methods (`load_account_risk_config`, `load_risk_plan_config_for_horizon`) still exist on `SQLiteRuntimeStore`; they are kept for non-resolver callers (route handlers, diagnostics).

---

## 0 · Locked Risk Horizon Doctrine (operator-locked 2026-04-29)

> Deployment chooses horizon. Account chooses risk plan. Governor enforces.

- A Deployment declares its `risk_horizon` ∈ `{ scalping | intraday | swing | position | other }`.
- Each Account owns an `AccountRiskPlanMap`: `horizon → RiskPlanVersion`.
- When a Deployment publishes a SignalPlan, each subscribed Account independently resolves: `Account.risk_plan_for_horizon[Deployment.risk_horizon] → RiskResolver → Governor`.
- Two Accounts subscribed to the same Deployment can resolve different RiskPlans for the same horizon.
- If an Account has no RiskPlan for the Deployment's horizon and no fallback, the Account must reject the SignalPlan.
- The operator must see which RiskPlan each Account resolved for the Deployment.

**Slicing implication.** This MAP's Slice A (in-flight) ships the **Governor wiring with safe defaults** so AccountRiskConfig limits begin enforcing immediately. The per-horizon `AccountRiskPlanMap` is a **new saved entity** + a doctrine extension to `TradingHorizon` (adding `other`); it ships separately in Slice B (deferred — requires Angry Architect approval). Slice A's resolver signature already accepts `(account_id, horizon)` for the RiskPlanConfig lookup, so Slice B is a pure wiring add — no resolver refactor.

---

## 1 · Current State (today, with file:line proof)

### What works today
- **Pause / kill toggles** are correctly wired end-to-end:
  - Operator clicks `Operations.tsx:129-137` → `POST /api/v1/operations/global/kill` → `ControlPlane.activate_global_kill()` → `GovernorPolicy.global_kill_active=True` → `PortfolioGovernor.evaluate()` rejects with `global_kill_blocks_open`.
  - Same for `accounts/{id}/pause` and `deployments/{id}/pause` (`Operations.tsx:519-706` → `operations.py:184-211`).
- **Protective-exit bypass** is live: rule 1 in `governor/service.py:30-35` lets CLOSE/STOP/TARGET/etc. orders skip every other gate. This means stop/target follow-on orders will not be blocked by exposure caps.
- **Governor sits in the orchestrator path** — three call sites at `pipeline/orchestrator.py:343, 535, 741`, all routed through `_evaluate_governor_for_signal_plan()` at `orchestrator.py:942-962`.

### What is broken today
- **Six numeric checks are silent no-ops** because their thresholds are `None`:
  - `max_open_positions` (`governor/service.py:60`)
  - `max_gross_exposure_pct` (`governor/service.py:66`)
  - `max_net_exposure_pct` (`governor/service.py:72`)
  - `max_symbol_concentration_pct` (`governor/service.py:78`)
  - `max_open_risk_pct` (`governor/service.py:84`)
  - `broker_sync_stale` threshold (hardcoded 30s in `brokers/sync.py:270`, not policy-driven at all)
- **The configuration sources exist but are not read**:
  - `AccountRiskConfig` (`broker_accounts/models.py:138-172`) is editable from the Risk Card UI and persists via `account_risk_configs` table. **Never read by the Governor.**
  - `RiskPlanConfig` (`domain/risk_plan.py:57-100`) is editable from Risk Plans UI and persists via `risk_plan_versions` table. **Never read by the Governor.**
  - `GovernorPolicy` is loaded once at `PortfolioGovernor.__init__()` from `state_store.load_portfolio_governor_state()` and never updated thereafter. There is no API route or UI that writes a `GovernorPolicy` with non-`None` limits.
- **Net effect today**: the operator can edit RiskPlan caps and AccountRiskConfig caps, watch them save and round-trip on the screen, and **none of those numbers gate any order**. Decorative.

### Why this is not "introduce a new saved entity"
Both source tables (`account_risk_configs`, `risk_plan_versions`) already persist. This MAP introduces a **translation/read path** only. No new tables, no new records, no migrations. Per `HANDOFF_PROTOCOL.md:184` the Angry Architect approval gate does not apply to this slice.

---

## 2 · Target State (the slice's contract)

When this slice is shipped:

1. **The operator's edits become enforceable.** Setting `max_open_positions=3` on the Account's Risk Card OR on the deployment's active RiskPlan immediately gates the next entry signal at the Governor.
2. **Most-conservative wins (min-of-both).** When both `AccountRiskConfig` and `RiskPlanConfig` set the same field, the smaller value applies. Tightening either one tightens the gate; the operator cannot accidentally relax limits by choosing a more permissive RiskPlan.
3. **The persisted `GovernorPolicy` is the floor for `paused_*` and `global_kill_active`.** Per-evaluation policies cannot relax kill switches — they only contribute numeric limits.
4. **`broker_sync_stale` threshold becomes overrideable from `RiskPlanConfig`** (the field name is not in either config today; this slice ALSO does not extend either schema — see §5 Scope Limits — so this becomes a `TODO_FUTURE` not part of this slice).
5. **Pure-logic resolver, lookup-callable injected.** `GovernorPolicyResolver` does NOT own a runtime store; it accepts two callables (`get_account_risk_config`, `get_risk_plan_config_for_deployment`) so it stays unit-testable without DB stubs.
6. **No call-site signature break for non-orchestrator callers.** `PortfolioGovernor.evaluate(request, *, policy_override=None)` defaults `None`, preserving existing behavior. Only the orchestrator passes a non-None override.

---

## 3 · Field Map (canonical translation table)

| `GovernorPolicy` field | `AccountRiskConfig` field | `RiskPlanConfig` field | Combine rule |
|---|---|---|---|
| `max_open_positions` | `max_open_positions` (default 5) | `max_open_positions` (default None) | `min` of present values; None means "no limit from this source" |
| `max_gross_exposure_pct` | `max_gross_exposure_pct` | `max_gross_exposure_pct` | `min` of present values |
| `max_net_exposure_pct` | `max_net_exposure_pct` | `max_net_exposure_pct` | `min` of present values |
| `max_symbol_concentration_pct` | `max_symbol_concentration_pct` | `max_symbol_exposure_pct` ← **NAME DIFFERS** | `min` of present values; resolver maps the name |
| `max_open_risk_pct` | _(absent)_ | `max_open_risk_pct` | RiskPlan-only; AccountRiskConfig contributes None |
| `paused_account_ids` | _(N/A — comes from ControlPlane)_ | _(N/A)_ | Carried through unchanged from floor `GovernorPolicy` |
| `paused_deployment_ids` | _(N/A — comes from ControlPlane)_ | _(N/A)_ | Carried through unchanged from floor `GovernorPolicy` |
| `global_kill_active` | _(N/A — comes from ControlPlane)_ | _(N/A)_ | Carried through unchanged from floor `GovernorPolicy` |

**Combine semantics (`min` of present values):**
- both `None` → `None` (no gate)
- one `None`, one set → the set value
- both set → `min(a, b)`

This rule applies field-by-field, so an operator can have a tight `max_open_positions` from RiskPlan and a tight `max_gross_exposure_pct` from AccountRiskConfig, and both gate independently.

---

## 4 · Decision Log (locked at slice start)

| # | Decision | Reasoning |
|---|---|---|
| D1 | `min`-of-both for overlapping limits | Most conservative wins. Operator cannot accidentally loosen. Matches `feedback_production_grade_only.md` doctrine memory. |
| D2 | Resolver is pure logic, accepts lookup callables | Keeps it unit-testable. Orchestrator wires DB lookups at construction. |
| D3 | `evaluate(request, *, policy_override=None)` extended signature | Backwards compatible. Default `None` preserves existing single-policy behavior for non-orchestrator callers (research, sim_lab, backtests if they ever call it). |
| D4 | Floor `GovernorPolicy` preserves kill/pause; per-eval policy adds numeric limits | Avoids accidentally clearing a global_kill via per-eval resolution. The merge function takes the floor as base, then sets the numeric limits, then re-freezes. |
| D5 | Name translation `max_symbol_concentration_pct` ↔ `max_symbol_exposure_pct` happens in the resolver, not in either schema | Both source tables shipped with operator-visible labels; renaming would be a frontend doctrine break. The resolver eats the asymmetry. |
| D6 | `broker_sync_stale` 30s threshold stays hardcoded for this slice | Out of scope. Schema extension on `RiskPlanConfig` for staleness override would touch persistence; defer to a separate slice. |
| D7 | Resolver lookup failure modes default to "no per-eval policy" (graceful degrade to floor) | A missing AccountRiskConfig row should NOT block trading; it should fall back to the floor `GovernorPolicy` as if no per-account override existed. Logged but not fatal. |
| D8 | No new route, no new schema | Pure backend wiring slice. No `route-added`/`schema-added` LEDGER entries. |

---

## 5 · Scope Limits (explicit non-goals)

**OUT of scope for this slice (file separately if needed):**
- ❌ Wiring `max_daily_loss_pct`, `max_drawdown_pct`, `cooldown_after_loss_minutes`, `max_trades_per_day` — those need a daily-state aggregator the Governor doesn't have today.
- ❌ Adding `broker_sync_stale_seconds` to either config schema.
- ❌ Persisting a separate `GovernorPolicy` row per account or per deployment. (No new saved entity.)
- ❌ Touching the frontend. The Risk Card UI and Risk Plans UI already edit the source data; they do not change.
- ❌ Stop/target order placement (the bracket gap from the `STRATEGY_TO_BROKER_BRACKET_PROGRAM` discussion). Separate program.
- ❌ ControlPlane changes. Pause/kill paths already work.

---

## 6 · Slice Implementation Plan

### Slice G-1 · `GovernorPolicyResolver`
**Files** (new): `backend/app/governor/policy_resolver.py`.
**Files** (test, new): `backend/tests/unit/governor/test_policy_resolver.py`.

**Public surface** (signature locked to honor Risk Horizon doctrine §0):
```python
class GovernorPolicyResolver:
    def __init__(
        self,
        *,
        get_account_risk_config: Callable[[UUID], AccountRiskConfig | None],
        get_risk_plan_config_for_horizon: Callable[
            [UUID, TradingHorizon], RiskPlanConfig | None
        ],
    ) -> None: ...

    def resolve(
        self,
        *,
        floor: GovernorPolicy,
        account_id: UUID,
        deployment_id: UUID,
        risk_horizon: TradingHorizon,
    ) -> GovernorPolicy:
        """Return a new GovernorPolicy that:
           - keeps floor.global_kill_active, floor.paused_account_ids,
             floor.paused_deployment_ids verbatim
           - sets numeric limits to the min of (AccountRiskConfig field,
             RiskPlanConfig field for the deployment's horizon),
             treating None as "no contribution"
        """
```

`deployment_id` is accepted for future use (audit trail and the contract's `AccountDeploymentRiskOverride` hook) but not consumed today — the locked doctrine resolves by horizon, not by deployment.

The `get_risk_plan_config_for_horizon` callable returns `None` for every input until Slice B adds the `AccountRiskPlanMap` entity; until then the resolver contributes only AccountRiskConfig limits, which is still a strict improvement over today's all-`None`.

**Acceptance**: 10+ unit tests covering: no configs (floor passthrough), account-only, plan-only, both-set, name translation (concentration), missing field on one side, lookup raises (graceful degrade), kill switch preservation through resolution, every horizon value passes through to the lookup, deployment_id ignored verbatim.

### Slice G-2 · `PortfolioGovernor.evaluate(policy_override=None)`
**Files** (edit): `backend/app/governor/service.py` only.

**Change**: Add keyword-only `policy_override: GovernorPolicy | None = None` to `evaluate()`. When provided, use it instead of `self._policy` for the duration of that one call. Single-line conditional at the top of `evaluate()`. No mutation of `self._policy`.

**Acceptance**: existing governor tests still pass; one new test confirms override is honored without mutating `self._policy`.

### Slice G-3 · `RuntimeOrchestrator` wiring
**Files** (edit): `backend/app/pipeline/orchestrator.py`.

**Changes**:
1. Add `governor_policy_resolver: GovernorPolicyResolver | None = None` to `__init__`. Store as `self._governor_policy_resolver`.
2. Resolve the deployment's `risk_horizon` (Slice A interim: read it off the deployment object via `getattr(self._deployment, "risk_horizon", None)`; if None, fall back to the strategy controls' `trading_horizon`). Cache as `self._deployment_risk_horizon` on init.
3. In `_evaluate_governor_for_signal_plan()`, if the resolver is set AND a horizon is resolvable, call `resolver.resolve(floor=self._governor.policy, account_id=account_id, deployment_id=signal_plan.deployment_id, risk_horizon=self._deployment_risk_horizon)` and pass the result via `policy_override=...` to `evaluate()`.
4. If the resolver is not set, behavior is unchanged.

**Acceptance**: existing orchestrator tests still pass; new integration tests confirm:
- with resolver wired, an `AccountRiskConfig` setting `max_open_positions=1` blocks a second open
- with resolver wired and a stub horizon-keyed lookup returning a `RiskPlanConfig` with `max_gross_exposure_pct=10`, an exposure-blowing entry is blocked
- with resolver wired and both sources set, the tighter one wins
- with resolver `None`, behavior matches today

### Slice G-4 · Adversarial recursion ×2
After G-1 through G-3 are green:
- **Recursion #1** (Agent A, sonnet): "break the wiring"; categories: lookup failure modes, frozen-policy mutation attempts, kill-switch erosion via resolver, race between policy load and resolver, off-by-one on `max_open_positions`, name-translation edge cases, what happens when both `AccountRiskConfig` field is `None` AND `RiskPlanConfig` field is `None` AND floor field is set.
- **Recursion #2** (Agent B, sonnet, different angle): "audit the integration"; categories: every existing orchestrator test path that touches Governor, every test fixture that constructs PortfolioGovernor without a resolver (regression risk), broker_sync interaction, protective-exit bypass interaction with per-eval policy, what happens when account_id is unknown to the lookup callable.

Each finding triaged: BUG → fix in this slice; RISK → decide fix-now vs ledger-as-followup; NIT → ledger-as-followup.

---

## 7 · Acceptance Gates (the slice ships only when all green)

1. `pytest backend/tests/unit/governor -q` → all green
2. `pytest backend/tests/unit/pipeline -q` → all green
3. `pytest backend/tests/unit -q` → 1395+ passing (baseline as of LEDGER `2026-04-29 13:00:42`)
4. Adversarial recursion #1 returns no BUG-severity findings (or all are fixed)
5. Adversarial recursion #2 returns no BUG-severity findings (or all are fixed)
6. LEDGER entry filed (`backend-internal` kind — does not cross the operation boundary, so no `route-added`/`schema-added`)
7. INBOX_CODEX heads-up updated with completion summary
8. LOCKS released
9. OPERATION_STATUS marked `handoff_ready`

---

## 8 · Verification Commands

```bash
# Focused governor + pipeline tests:
python -m pytest backend/tests/unit/governor backend/tests/unit/pipeline -q

# Full backend unit suite:
python -m pytest backend/tests/unit -q

# Boundary suite (ensures no cross-boundary contract drift):
python -m pytest backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/lint -q
```

Frontend is untouched by this slice; no `npm` commands required.

---

## 9 · What This Slice Does NOT Promise

- The +10/-5 bracket exit problem from [STRATEGY_TO_BROKER_BRACKET_PROGRAM context]: NOT solved here. That requires `execution_style` persistence + SignalPlanBuilder bracket support + post-fill bracket placement in BrokerAdapter. Separate four-slice program.
- StrategyControls persistence (the bug-b problem): NOT solved here. That needs Angry Architect approval and a separate slice.
- The `max_daily_loss_pct` / `max_drawdown_pct` checks: NOT added. Out of scope per §5.
- This slice closes the silent-no-op hole in the existing five numeric Governor checks. It does not extend the Governor's check surface.
