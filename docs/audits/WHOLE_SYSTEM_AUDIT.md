# Whole System Audit — Ultimate Trader

**Date:** 2026-04-30  
**Scope:** Read-only review of repository state (no code changes in this audit).  
**Doctrine anchor:** `AGENTS.md` (locked chain: Strategy → Deployment → SignalPlan → Account Evaluation → RiskResolver → Governor → Order → BrokerAdapter → BrokerSync → Position Truth).

---

## Executive summary

The backend implements a substantial portion of the doctrine chain inside `RuntimeOrchestrator` (`backend/app/pipeline/orchestrator.py`): feature/signal evaluation, `SignalPlan` construction, per-account risk resolution, governor gating, order creation, broker submission, and `BrokerSync.apply_result` for ledger updates. `GovernorPolicyResolver` (`backend/app/governor/policy_resolver.py`) and `SQLiteRuntimeStore.load_risk_plan_config_for_horizon` (`backend/app/persistence/runtime_store.py`) implement horizon-based risk-plan lookup when wired through `BrokerRuntimeOrchestrator` (`backend/app/runtime/account_trading_orchestrator.py`).

**Highest-impact confirmed gaps:** (1) operator-facing risk limits such as `max_daily_loss_pct` on `AccountRiskConfig` and equivalent fields on `RiskPlanConfig` are **not** merged into `GovernorPolicy` and **not** enforced by `PortfolioGovernor.evaluate` (`backend/app/governor/models.py`, `backend/app/governor/service.py`); (2) `GovernorRequest` is built **without** `candidate_market_value` / `candidate_open_risk`, so exposure and open-risk percentage gates can silently evaluate against **zero** incremental exposure (`backend/app/pipeline/orchestrator.py` vs defaults in `backend/app/governor/models.py`); (3) research historical replay never runs `PortfolioGovernor` and uses a different order path than production (`backend/app/simulation/historical_replay.py`); (4) `OperationsCenterService.list_account_signal_plan_evaluations` only reconstructs evaluations from **orders**, so PARTICIPATE/REJECT/IGNORE decisions without an order are invisible (`backend/app/operations/service.py`); (5) persisted `Deployment` records omit `risk_horizon` while runtime `DeploymentContext` carries it (`backend/app/deployments/models.py`, `backend/app/runtime/models.py`), creating configuration/runtime drift unless composition always sets context from elsewhere.

---

## Confirmed working areas

### Doctrine-aligned domain boundaries (partial)

- **SignalPlan neutrality:** `SignalPlan` rejects account execution fields at validation time (`backend/app/domain/signal_plan.py` L127–148).
- **Deployment-scoped read-only positions for exits:** `DeploymentPositionManager` documents read-only, Account-owned position truth (`backend/app/pipeline/orchestrator.py` L110–127); exit candidates pair with positions filtered per account with explicit handling when lineage is missing or ambiguous (`backend/app/pipeline/orchestrator.py` L468–552).
- **BrokerSync as ledger truth writer for adapter results:** `BrokerSync.apply_result` updates the internal ledger from `BrokerOrderResult` (`backend/app/brokers/sync.py` L28–67); orchestrator applies results through `_broker_sync.apply_result` (`backend/app/pipeline/orchestrator.py` L870).
- **Governor policy resolution wiring (when runtime store present):** `BrokerRuntimeOrchestrator._build_governor_policy_resolver` connects account risk config and per-horizon risk plan config (`backend/app/runtime/account_trading_orchestrator.py` L274–305); `GovernorPolicyResolver.resolve` documents Deployment-declared horizon enforcement via `enforce_plan_required` (`backend/app/governor/policy_resolver.py` L96–127).
- **Horizon → RiskPlan persistence:** `SQLiteRuntimeStore.load_risk_plan_config_for_horizon` joins `account_risk_plan_map` to `risk_plan_versions` and drops deprecated plans (`backend/app/persistence/runtime_store.py` L753–788).
- **StrategyControls persistence (composer path):** `StrategyComposerService._persist_strategy_controls` persists when a `StrategyControlsRepository` is wired (`backend/app/strategy_composer/service.py` L654–676); API composition wires the repository (`backend/app/api/routes/strategies.py` L57–62).
- **Bracket / post-fill protective path (production orchestrator):** Post-fill protection placement is implemented with explicit naked-position alarms and interaction with native bracket mode (`backend/app/pipeline/orchestrator.py` L886–1016, L979–1146).
- **Frontend ↔ API route registration guard:** `test_current_frontend_http_api_contract_is_registered` locks the set of HTTP routes the frontend expects (`backend/tests/unit/api/test_frontend_api_contract.py` L35–41).

---

## Confirmed gaps

### 1) Strategy → Deployment → SignalPlan → Account → RiskResolver → Governor → Order → BrokerSync → Position

| Gap | Evidence |
|-----|----------|
| **Account evaluation not persisted as first-class records** | `RuntimeOrchestrator` builds `AccountSignalPlanEvaluation` in memory (`backend/app/pipeline/orchestrator.py` L314–384, L575–587). No store write in this module. |
| **Operations “evaluations” are projections from orders only** | `list_account_signal_plan_evaluations` iterates `_all_orders()` and skips orders without `signal_plan_id` (`backend/app/operations/service.py` L270–301). Rejected/blocked/ignored evaluations without orders **do not appear**. |
| **Research replay skips Governor and production order stack** | Historical replay documents RiskDecisionCard spine (`backend/app/simulation/historical_replay.py` L733–739, L1039–1118); there is no `PortfolioGovernor` in this path. Production uses `RuntimeOrchestrator` + `PortfolioGovernor` (`backend/app/pipeline/orchestrator.py` L1252–1286). |
| **No standalone `DeploymentPublisher` module** | Grep shows no `DeploymentPublisher` / `deployment_publisher` implementation under `backend/`; emission is inlined in `RuntimeOrchestrator.process_bar` (`backend/app/pipeline/orchestrator.py` L271–446). |

### 2) ExecutionPlan + bracket execution

| Gap | Evidence |
|-----|----------|
| **Native bracket reference price vs fill price drift** | `_native_bracket_reference_price` uses limit or bar close; comment states real fill arrives later via BrokerSync (`backend/app/pipeline/orchestrator.py` L948–962). |
| **ExecutionPlan / execution_style cached at orchestrator construction** | Comment in `_maybe_attach_native_bracket_to_entry`: orchestrator caches components at construction; mid-run execution mode change can leave stale snapshot (`backend/app/pipeline/orchestrator.py` L1004–1011). |
| **Opposite-side flip while open** | Replay blocks with `opposite_side_position_open` (`backend/app/simulation/historical_replay.py` L1018–1028); production path should be verified for the same invariant end-to-end (suspected parity — see below). |

### 3) StrategyControls persistence

| Gap | Evidence |
|-----|----------|
| **Persistence is conditional on repository injection** | `_persist_strategy_controls` returns unsaved controls when repository is `None` (`backend/app/strategy_composer/service.py` L654–667). API wiring passes repository (`backend/app/api/routes/strategies.py` L57–62); other composition roots must be checked per deployment. |

### 4) Deployment-owned position lineage

| Gap | Evidence |
|-----|----------|
| **Multiple active lineages for same symbol/account** | Orchestrator emits `multiple_active_position_lineages_for_account` and blocks (`backend/app/pipeline/orchestrator.py` L512–520). |
| **Ambiguous lineage when multiple active lineage IDs on bar** | `related_position_lineage_id` is taken only if exactly one active lineage ID (`backend/app/pipeline/orchestrator.py` L488–494); otherwise `None`, affecting downstream `SignalPlan` linkage. |
| **Persisted `Deployment` vs runtime `DeploymentContext` mismatch on horizon** | `Deployment` model has no `risk_horizon` (`backend/app/deployments/models.py` L21–47). `DeploymentContext` includes optional `risk_horizon` (`backend/app/runtime/models.py` L40–48). |

### 5) RiskPlan horizon mapping

| Gap | Evidence |
|-----|----------|
| **`deployment_id` ignored in resolver** | `GovernorPolicyResolver.resolve` deletes `deployment_id` as unused (`backend/app/governor/policy_resolver.py` L110–114). Doctrine says Deployment chooses horizon; mapping is by horizon only — acceptable if deployments cannot diverge on same account, otherwise ambiguous. |
| **Floor policy numeric fields often `None`** | Resolver documents steady-state: per-horizon `RiskPlanConfig` lookup often returns `None` until map is populated (`backend/app/governor/policy_resolver.py` L37–40). |

### 6) TOCTOU risks

| Gap | Evidence |
|-----|----------|
| **Governor incremental exposure fields default to zero** | `GovernorRequest` defines `candidate_market_value` and `candidate_open_risk` (`backend/app/governor/models.py` L113–114). `_evaluate_governor_for_signal_plan` constructs the request without setting them (`backend/app/pipeline/orchestrator.py` L1260–1269), so `_projected_state` uses **0** incremental candidate exposure/risk (`backend/app/governor/service.py` L145–164). |
| **Portfolio snapshot factory may be empty** | Default `PortfolioSnapshot()` has `equity: float | None = None` (`backend/app/governor/models.py` L65–70); `_pct` treats falsy equity as 0 (`backend/app/governor/service.py` L190–191), collapsing exposure percentages. |
| **Broker preflight uses latest cached snapshot** | `_buying_power_for_preflight` reads `latest_account_snapshot` (`backend/app/pipeline/orchestrator.py` L1196–1200); timing vs live broker state is inherently stale (TOCTOU class). |

### 7) Daily loss / cooldown gaps

| Gap | Evidence |
|-----|----------|
| **`GovernorPolicy` has no daily-loss or cooldown fields** | Model lists kill switches, pauses, position count, exposure, concentration, open risk, `requires_risk_plan` (`backend/app/governor/models.py` L13–29). No `max_daily_loss_pct`, no drawdown, no cooldown. |
| **`PortfolioGovernor.evaluate` has no daily-loss branch** | Checks end at `max_open_risk_pct` (`backend/app/governor/service.py` L47–112). |
| **`GovernorPolicyResolver` does not map `max_daily_loss_pct` from `AccountRiskConfig` or `RiskPlanConfig`** | Resolver merges a fixed set of numeric fields only (`backend/app/governor/policy_resolver.py` L128–165). `AccountRiskConfig` **does** define `max_daily_loss_pct` (`backend/app/broker_accounts/models.py` L158–159). `RiskPlanConfig` defines `max_daily_loss_pct` and `cooldown_after_loss_minutes` (`backend/app/domain/risk_plan.py` L76–79). |

### 8) BrokerSync truth boundary

| Working | `BrokerSync.apply_result` is the structured path for adapter `BrokerOrderResult` → ledger (`backend/app/brokers/sync.py` L28–67). |
| Gap | `record_position_snapshot` / account snapshots persist **through** `BrokerSync` when `runtime_store` supports them (`backend/app/brokers/sync.py` L165–178). Any other writer calling `save_broker_position_snapshot` outside `BrokerSync` would violate doctrine — **not exhaustively audited here** (suspected: search callers outside `sync.py`). |

### 9) Research / lab parity

| Gap | Evidence |
|-----|----------|
| **Governor absent in replay** | See §1 research replay row. |
| **Deterministic deployment/account IDs in replay** | `uuid5`-derived deployment and account IDs (`backend/app/simulation/historical_replay.py` L789–792) differ from live deployment/account binding. |
| **Control-plane / multi-account** | Replay uses a single simulated broker path; production orchestrator loops `_account_ids` (`backend/app/pipeline/orchestrator.py` L350+). |

### 10) UI / backend drift

| Gap | Evidence |
|-----|----------|
| **Contract test scope** | Test states it tracks **current** frontend client surface only (`backend/tests/unit/api/test_frontend_api_contract.py` L35–41); future research APIs called out as gaps there. |
| **Operator-visible IDs** | `AGENTS.md` requires human-readable primary UX; audit did not trace every React route — **partially suspected** (see below). |

---

## Silent failure risks

| Risk | Type | Evidence |
|------|------|----------|
| Exposure / open-risk governor limits ineffective for opening orders | **Confirmed** | Missing `candidate_market_value` / `candidate_open_risk` on `GovernorRequest` (`backend/app/pipeline/orchestrator.py` L1260–1269; `backend/app/governor/service.py` L145–164). |
| Operator-set daily loss and cooldown never enforced at Governor | **Confirmed** | `GovernorPolicy` / `PortfolioGovernor` / `GovernorPolicyResolver` omit those dimensions (`backend/app/governor/models.py` L13–29; `backend/app/governor/service.py` L47–112; `backend/app/governor/policy_resolver.py` L128–165). |
| Rejected signal evaluations invisible in Operations API | **Confirmed** | Evaluations list tied to orders (`backend/app/operations/service.py` L270–301). |
| Resolver lookup failure → graceful degrade (no plan enforcement) | **Confirmed by design** | Resolver logs and falls back to floor on lookup exception (`backend/app/governor/policy_resolver.py` L42–45, L180–201); `requires_risk_plan` not set when lookup raises (`backend/app/governor/policy_resolver.py` L124–126). |
| Native bracket / post-fill double-placement | **Mitigated in code** | Skips post-fill when `order_class == "bracket"` (`backend/app/pipeline/orchestrator.py` L1004–1013). |
| `enforce_plan_required` false when Deployment lacks explicit horizon | **Confirmed** | Orchestrator only sets `True` when `deployment.risk_horizon` is set (`backend/app/pipeline/orchestrator.py` L186–194). |

---

## Suspected issues (needs targeted verification)

- **Other writers to broker snapshot tables** besides `BrokerSync` / `BrokerSyncService` (doctrine violation if present).
- **Whether production live loop always supplies non-empty `PortfolioSnapshot` with equity** for governor percentage gates (`BrokerRuntimeOrchestrator` passes `portfolio_snapshot_factory` — verify each composition site).
- **Full parity** between `RuntimeOrchestrator` entry/exit rules and `HistoricalReplayEngine` for edge cases (e.g. opposite-side open, multi-account).
- **Frontend** surfaces still showing raw UUIDs as primary labels — requires UI pass against `AGENTS.md` Human-Readable Frontend Data Rule (not exhaustively verified in this audit).

---

## P0 / P1 / P2 priorities

### P0 — Safety / correctness relative to stated doctrine

1. Populate `GovernorRequest.candidate_market_value` and `candidate_open_risk` (or remove reliance on exposure limits until populated). (`backend/app/pipeline/orchestrator.py` L1260–1269; `backend/app/governor/service.py` L145–164.)
2. Wire **daily loss** (and, if required by doctrine, **drawdown** and **loss cooldown**) from `AccountRiskConfig` / `RiskPlanConfig` into a Governor-enforceable policy surface, or stop exposing them as enforcement knobs in the UI until wired. (`backend/app/broker_accounts/models.py` L158–159; `backend/app/domain/risk_plan.py` L76–79; `backend/app/governor/models.py` L13–29.)
3. Persist or otherwise durably emit **all** `AccountSignalPlanEvaluation` outcomes (not only those resulting in orders). (`backend/app/operations/service.py` L270–301 vs doctrine in `AGENTS.md`.)

### P1 — Parity and configuration integrity

4. Align persisted `Deployment` with runtime horizon selection (`backend/app/deployments/models.py` L21–47 vs `backend/app/runtime/models.py` L40–48).
5. Research / lab path: document and reduce divergence — Governor + multi-account + control-plane analogs vs `HistoricalReplayEngine` (`backend/app/simulation/historical_replay.py` L1039–1118 vs `backend/app/pipeline/orchestrator.py`).
6. Resolve **ambiguous lineage** behavior when multiple active lineages exist for one symbol (`backend/app/pipeline/orchestrator.py` L488–494).

### P2 — Operational polish

7. Native bracket reference vs actual fill drift — operator visibility / optional repricing (`backend/app/pipeline/orchestrator.py` L948–962).
8. Expand automated UI/API contract coverage as new pages call new endpoints (`backend/tests/unit/api/test_frontend_api_contract.py` L35–41).

---

## Hardening sequence (non-speculative)

Order respects dependencies and doctrine (no new architectural layers implied):

1. **Instrument Governor inputs:** Ensure portfolio equity, candidate market value, and candidate open risk reflect the proposed OPEN before `PortfolioGovernor.evaluate` (`backend/app/pipeline/orchestrator.py` L1252–1286; `backend/app/governor/service.py` L145–164).
2. **Extend Governor policy + resolver minimally** to carry enforceable daily-loss / drawdown / cooldown semantics already present on domain models (`backend/app/governor/models.py`; `backend/app/governor/policy_resolver.py`; `backend/app/broker_accounts/models.py`; `backend/app/domain/risk_plan.py`).
3. **Persist evaluations** or stream them to Operations storage so reject/ignore paths are auditable (`backend/app/operations/service.py` L270–301).
4. **Unify Deployment persistence** with `DeploymentContext.risk_horizon` (`backend/app/deployments/models.py`; `backend/app/runtime/models.py`).
5. **Research parity passes:** add comparative tests that assert the same blocking reasons for key scenarios (open, exit, flip, multi-account) between replay and orchestrator **without** inventing new runtime architecture.
6. **BrokerSync boundary audit:** static search for `save_broker_position_snapshot` / ledger mutation sites outside `backend/app/brokers/sync.py`.

---

## Slice plan (implementation-sized, doctrine-preserving)

| Slice | Outcome | Touches (indicative) |
|-------|---------|----------------------|
| S1 | Governor OPEN evaluation uses populated candidate exposure/risk | `orchestrator.py`, tests for `_projected_state` |
| S2 | Daily loss / drawdown / cooldown enforced at Governor (policy + snapshot inputs) | `governor/models.py`, `governor/service.py`, `policy_resolver.py`, account snapshot sourcing |
| S3 | Durable AccountSignalPlanEvaluation store + Operations reads | `operations/service.py`, persistence layer |
| S4 | Deployment record + API carry `risk_horizon` (or explicit mapping) | `deployments/models.py`, deployment services/routes |
| S5 | Replay parity tests vs orchestrator for documented edge cases | `historical_replay.py`, `orchestrator.py` tests |

---

## Test requirements

1. **Governor math:** Unit tests that fail if `candidate_market_value=0` when a non-zero OPEN is evaluated (guard regression on `backend/app/pipeline/orchestrator.py` L1260–1269).
2. **Daily loss:** Scenarios where intraday P&L breaches `max_daily_loss_pct` must yield Governor reject — once fields exist on `GovernorPolicy`.
3. **Evaluation completeness:** Tests proving REJECT/IGNORE evaluations appear in storage/API, not only order-backed projections (`backend/app/operations/service.py` L270–301).
4. **Horizon enforcement:** `enforce_plan_required` paths — account missing plan for explicit deployment horizon → reject (`backend/app/governor/service.py` L71–80; `backend/app/governor/policy_resolver.py` L118–126).
5. **Bracket:** Post-fill placer not invoked when native bracket (`backend/app/pipeline/orchestrator.py` L1004–1016) — existing tests referenced in `test_runtime_orchestrator_post_fill_bracket*.py`.
6. **Contract:** Extend `test_frontend_api_contract.py` when frontend adds endpoints (`backend/tests/unit/api/test_frontend_api_contract.py` L35–41).

---

## Doctrine preservation note

This audit does **not** propose moving SignalPlans onto Strategy, merging Deployment state with Account positions, or splitting paper/live into separate systems. Recommended changes stay within the locked ownership model in `AGENTS.md` (Deployment emits SignalPlans; Account evaluates; BrokerSync writes broker-derived truth).
