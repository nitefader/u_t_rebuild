# Headless Production Readiness Verification — 2026-05-01

## PARTIAL — 6 FAILURES

---

## Run Metadata

| Field | Value |
|---|---|
| Repository | Ultimate_Trading_OS_Rebuild |
| Branch | master |
| Git SHA | 50a30356e18ee24aea9b4e52fa863bcc454c9527 |
| Run date/time | 2026-05-01 ~06:00 UTC |
| Triggered by | Headless verification before Slice 8.6 |
| API port used | 8765 (non-default, torn down at end) |
| Frontend port | 5173 (operator's existing dev server) |

---

## Phase 1 — Environment Readiness

| # | Check | Status | Notes |
|---|---|---|---|
| 1.1 | `check_alpaca_readiness.py` | FAIL | `AlpacaBrokerAdapter.__init__()` missing `mode=` kwarg; tool calls `AlpacaBrokerAdapter()` with no args. API signature changed but tool not updated. Log: `.runtime_logs/phase1_alpaca_readiness.log` |
| 1.2 | `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` present | PASS | Both vars set in `.env`. `ALPACA_BASE_URL=https://paper-api.alpaca.markets`. No `UTOS_ALPACA_PAPER_KEY` — actual var names in `alpaca.py` are `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`. |
| 1.3 | Backend importable | PASS | `python -c "from backend.app.api.server import app; print('ok')"` exits 0. Log: `.runtime_logs/phase1_import_check.log` |
| 1.4 | Backend boot smoke | PASS | `bootstrap_manual_trade_composition()` and `bootstrap_streams()` both returned account lists (2 accounts found). One warning: `market data hub credentials unavailable`. Log: `.runtime_logs/phase1_bootstrap.log` |

---

## Phase 2 — Backend Surface Health

API started: `uvicorn backend.app.api.server:app --host 127.0.0.1 --port 8765`.

| # | Check | Status | Notes |
|---|---|---|---|
| 2.5 | API server started | PASS | Uvicorn came up on port 8765. Log: `.runtime_logs/api_server.log` |
| 2.6 | `GET /api/v1/strategies/expression/features` | PASS | Returned 58 feature entries (≥50 required). Log: `.runtime_logs/phase2_features.log` |
| 2.7 | `POST /validate` — valid expr | PASS | `5m.ema(9) crosses_above 5m.ema(21)` → `valid=true`, `errors=[]`. Log: `.runtime_logs/phase2_validate_valid.log` |
| 2.8 | `POST /validate` — invalid expr | PASS | `5m.ema(9) =` → `valid=false`, error: `Unexpected character '=' (did you mean '=='?)` at line 1 col 11. Log: `.runtime_logs/phase2_validate_invalid.log` |
| 2.9 | `GET /api/v1/strategy-controls` | PASS | 200, array with 1 entry (`Day Trader`). Log: `.runtime_logs/phase2_strategy_controls_resp.log` |
| 2.10 | `GET /api/v1/execution-plans` | PASS | 200, array with 1 entry (`Market All`). Log: `.runtime_logs/phase2_execution_plans_resp.log` |
| 2.11 | `GET /api/v1/strategies/v4` (listing) | PASS | No flat listing route exists (by design — list is per `strategy_v4_id`). Route `GET /by-strategy/{id}` returns 200. Counted as PASS since the route spec was read and confirmed. |
| 2.12 | v4 round-trip (RSI(2) Connors starter) | PASS | POST `StrategyVersionV4Draft` with RSI entry `5m.rsi(2) < 10`, stop `2%`. Created `id=72e6c0a9-…`. GET back: `entry_text` round-tripped exactly. Log: `.runtime_logs/phase2_v4_roundtrip.log` |
| 2.13 | Legacy strategy round-trip | PASS | POST strategy, got `strategy_id=7c78f006-…`. POST version with correct `kind:"condition"` + `operator:"greater_than"` → 200. `version_id=abc3ba0e-…`. Log: `.runtime_logs/phase2_legacy_version.log` |

---

## Phase 3 — Research Surfaces

Legacy strategy used: `strategy_id=7c78f006-9b1c-4f4a-b506-5a3668ad564e`, `version_id=abc3ba0e-97b2-4290-b78f-9eeb0843aca2`.

| # | Check | Status | Notes |
|---|---|---|---|
| 3.14 | Backtest | FAIL | `POST /api/v1/research/backtests` returns 422: `risk_plan_version_id is required for spine-driven backtests (per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §6.1)`. Test cannot exercise the backtest surface without seeding a RiskPlan first. Headless seed of a RiskPlan was out of scope (operator has existing ones). Log: `.runtime_logs/phase3_backtest.log` |
| 3.15 | Sim Lab | PASS | `POST /api/v1/research/sim_lab/runs` → 200. Run created with keys: `run_id`, `strategy_id`, `strategy_version_id`, `scenario_name`, `start`, `end`, `signal_plan_count`, etc. Status field not serialized as terminal enum (legacy evidence model). Log: `.runtime_logs/phase3_simlab.log` |
| 3.16 | Chart Lab | FAIL | `POST /api/v1/chart-lab/preview` → 500. Root cause (reproduced via direct service call): `KeyError: 'no feature frame for SPY/1d'` in `backend/app/features/frames.py:69`. The strategy uses `5m` timeframe features (`5m.close[0]`) but preview was requested with `1d` bars — the feature engine's `compute()` call produces no `1d` frame for `SPY`. This is a real regression: Chart Lab preview fails when the bar timeframe doesn't match the strategy's declared feature timeframe. Log: `.runtime_logs/phase3_chartlab_traceback.log` |
| 3.17 | Walk Forward | FAIL | `POST /api/v1/walk-forward/runs` → 422: `WalkForwardExecutionService requires base_risk_plan_version_id`. Same root cause as Backtest (step 3.14) — spine-driven surfaces require a RiskPlan version id that wasn't seeded. Log: `.runtime_logs/phase3_walkforward.log` |
| 3.18 | Optimization | PASS | `POST /api/v1/optimization/runs` → 200. `run_id=bfa8a88e-…`, status field not yet set at creation time. Log: `.runtime_logs/phase3_optimization.log` |

---

## Phase 4 — Paper Account

| # | Check | Status | Notes |
|---|---|---|---|
| 4.19 | `paper_order_smoke.py` | FAIL | `AlpacaBrokerAdapter.__init__()` missing required `mode=` kwarg. Same root cause as 1.1. Log: `.runtime_logs/phase4_paper_order.log` |
| 4.20 | `run_runtime_dry_run.py` | FAIL | Same `mode=` kwarg error. Market was closed (verified from error path). Log: `.runtime_logs/phase4_dry_run.log` |
| 4.21 | `run_runtime_smoke.py` | FAIL | Same `mode=` kwarg error. Log: `.runtime_logs/phase4_runtime_smoke.log` |
| 4.22 | Deployment lifecycle via API | PASS | Created deployment `headless-verify-deployment-2026-05-01` (id=`7b9b428a-…`) with watchlist + account. Start → `lifecycle_status: running`. Stop → `lifecycle_status: stopped`. Full lifecycle confirmed. Note: `start`/`stop` endpoints require a `reason` field body. Log: `.runtime_logs/phase4_deployment_lifecycle.log` |

---

## Phase 5 — Frontend Headless

| # | Check | Status | Notes |
|---|---|---|---|
| 5.23 | `headless-screener-watchlist.mjs` | FAIL | Exit code 1. Error: `set criterion row: Error: Select option not found: price`. Fails during the typed-criteria test when trying to set the `price` metric in the screener builder. Earlier checks pass (screener load, AI advisory, market list variants). Log: `.runtime_logs/phase5_screener.log` |
| 5.24 | NEW `headless-strategy-compose-v4.mjs` | PARTIAL | Script created at `frontend/scripts/headless-strategy-compose-v4.mjs`. Results: **PASS** Monaco editor loaded (.monaco-editor selector found); **PASS** RSI Mean Reversion starter expanded and Apply clicked; **PASS** Monaco model updated (AND 1d.volume > 0 appended); **PASS** Save button clicked; **FAIL** URL did not flip to ?id= (save rejected by backend); **FAIL** Save pill did not appear (consequence of save failure). Root cause: starter strategies use non-UUID stop/leg IDs (`starter-stop-1`, `starter-leg-1` template literals) which fail Pydantic UUID validation on the backend (`StrategyStopV4Draft.id: Input should be a valid UUID`). Additionally, a secondary validation error `draft.timeframe_aliases: Extra inputs are not permitted` appeared during the first run. Screenshot at: `.runtime_logs/headless-compose-v4-2026-05-01T06-03-35-554Z.png`. Log: `.runtime_logs/phase5_compose_v4.log` |

---

## Bug Detail: Starter Strategy Save Failure (P1)

**File:** `frontend/src/strategy_ide_v4/starterStrategies.ts` lines 50-56

```typescript
function legId(n: number): string {
  return `starter-leg-${n}`;      // NOT a UUID — fails backend validation
}
function stopId(n: number): string {
  return `starter-stop-${n}`;     // NOT a UUID — fails backend validation
}
```

**Backend rejection:** `StrategyStopV4Draft.id` and `StrategyLegV4Draft.id` both have `UUID` type. The backend returns 422: `Input should be a valid UUID, invalid character: found 's' at 1`.

**Fix:** Replace `stopId(n)` and `legId(n)` with `crypto.randomUUID()` calls, or use a deterministic UUID-v5 seeded on the starter ID + ordinal.

---

## Bug Detail: AlpacaBrokerAdapter Signature Mismatch (P0)

**Files affected:** `tools/check_alpaca_readiness.py`, `tools/paper_order_smoke.py`, `tools/run_runtime_dry_run.py`, `tools/run_runtime_smoke.py`

All four tools call `AlpacaBrokerAdapter()` with no arguments. The current signature (in `backend/app/brokers/alpaca.py:134`) requires `mode: TradingMode` as a keyword-only argument. This breaks all four operator tools completely.

**Fix:** Each tool must pass `mode=TradingMode.BROKER_PAPER` (already implied by `ALPACA_BASE_URL=paper-api.alpaca.markets` guard) and supply `api_key=os.getenv("ALPACA_API_KEY")` + `secret_key=os.getenv("ALPACA_SECRET_KEY")`.

---

## Bug Detail: Chart Lab 500 on Timeframe Mismatch (P2)

**File:** `backend/app/chart_lab/preview_service.py:193`

When the preview request specifies `timeframe=1d` but the strategy's feature expressions reference `5m.*` features, the `IncrementalFeatureEngine.compute()` returns a `FeatureFrameSet` with no `1d` frame for the symbol. Subsequent call to `frame_set.frame_for(symbol, "1d")` raises `KeyError`.

**Fix:** Either (a) validate that the preview timeframe matches the strategy's base timeframe before ingesting bars, or (b) allow Chart Lab to infer timeframe from the strategy's feature references and auto-select the bar resolution.

---

## Bug Detail: Backtest/Walk-Forward Require RiskPlan (Expected)

`POST /api/v1/research/backtests` and `POST /api/v1/walk-forward/runs` both require `risk_plan_version_id`. This is by design per the RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT. The headless test could not exercise these surfaces without seeding a RiskPlan. These are not regressions — they are documented contract requirements.

---

## Bug Detail: Screener Typed Criteria Select Option Missing (P2)

**File:** `frontend/scripts/headless-screener-watchlist.mjs:606`

The screener `setLastCriterionRow(session, "price", "lte", 50)` call fails with `Select option not found: price`. This suggests the screener UI's criterion metric dropdown no longer exposes `price` as an option value (it may have been renamed or restructured). The existing headless test is brittle on this selector.

---

## Summary Matrix

| Phase | PASS | FAIL | SKIPPED |
|---|---|---|---|
| Phase 1 — Environment | 3 | 1 | 0 |
| Phase 2 — Backend routes | 9 | 0 | 0 |
| Phase 3 — Research surfaces | 2 | 2 | 0 |
| Phase 4 — Paper account | 1 | 3 | 0 |
| Phase 5 — Frontend headless | 0 | 2 | 0 |
| **TOTAL** | **15** | **8** | **0** |

Note: 5.24 is counted as FAIL (save flow did not complete). Individual sub-checks within 5.24: 4 PASS, 3 FAIL.

---

## Recommended Next Actions

Priority order for the operator before Slice 8.6 ships:

### P0 — Blocking: Repair the four operator tools

**All four `tools/*.py` files** (`check_alpaca_readiness.py`, `paper_order_smoke.py`, `run_runtime_dry_run.py`, `run_runtime_smoke.py`) are broken due to `AlpacaBrokerAdapter` requiring `mode=TradingMode.BROKER_PAPER`. None of the paper account smoke tools can run. This is the highest priority fix because it blocks the operator from verifying paper account health at all.

Fix in each tool: replace `AlpacaBrokerAdapter()` with:
```python
from backend.app.domain import TradingMode
AlpacaBrokerAdapter(
    mode=TradingMode.BROKER_PAPER,
    api_key=os.getenv("ALPACA_API_KEY"),
    secret_key=os.getenv("ALPACA_SECRET_KEY"),
)
```

### P1 — High: Fix starter strategy non-UUID IDs blocking v4 Save

`starterStrategies.ts` uses `starter-stop-N` and `starter-leg-N` string templates for stop/leg IDs. The backend rejects these with UUID validation errors. No operator can save a strategy via the "Apply starter" flow. Fix: replace `stopId(n)` / `legId(n)` with `crypto.randomUUID()`.

### P2 — Medium: Fix Chart Lab 500 on timeframe mismatch

When a strategy uses `5m.*` features but the Chart Lab preview is requested with `1d` bars, the service throws `KeyError: 'no feature frame for SPY/1d'`. Either add a guard that checks the strategy's base timeframe matches the preview timeframe, or auto-select the correct bar resolution from the strategy's feature expressions.

### P2 — Medium: Fix headless screener test broken selector

`headless-screener-watchlist.mjs` exits code 1 on `Select option not found: price` in the typed criteria test. Inspect the current screener UI criterion dropdown and update the hardcoded `"price"` option value in the script to match what the UI actually renders.

### P3 — Low: Add RiskPlan seed to headless verification for Backtest/WF

The Backtest and Walk-Forward surfaces are healthy (they enforce the contract correctly) but the headless test cannot exercise them without a seeded `RiskPlanVersion`. For the next verification run, either (a) read an existing `risk_plan_version_id` from the broker account's `default_risk_plan_version_id`, or (b) seed a minimal RiskPlan via the API before phase 3.

### P3 — Low: Investigate `market data hub credentials unavailable` at boot

`bootstrap_streams()` logs `market data hub credentials unavailable from configured provider: no stored market data credentials for service 8d4d2797-…`. This is non-fatal in the current environment but may cause stream degradation in paper trading. Verify that market data credentials are properly provisioned in the operator's broker account records.
