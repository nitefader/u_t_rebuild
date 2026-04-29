# Nanyel Acceptance Gate — Research Stack Definition Of Done

This is the joint exit criteria for the Codex + Claude loop. Both agents
work toward this gate. The loop only ends when **every** item is checked
and Nanyel personally approves the row.

Last updated: 2026-04-27 15:42:00 -04:00

Format: each row is `[ ]` until evidenced; `[x]` when shipped + verified;
`[A]` when Nanyel has signed off (date in the Notes column).

Evidence column = path to test, screenshot, or LEDGER entry that proves
the row is real. Notes column = approval timestamp once `[A]`.

---

## A. Strategies (author + version + publish)

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| A1  | [x]    | Create strategy via UI; persists with display_name + capabilities                                                 | `frontend/src/routes/Strategies.tsx` `CreateStrategyDrawer` (display name + tags=capabilities); `Strategies.test.tsx` 3 tests; LEDGER 2026-04-27 14:15:00 -04:00 |       |
| A2  | [x]    | Add strategy version with code + parameter schema; immutable past versions                                        | `frontend/src/routes/StrategyDetail.tsx` `AddVersionDrawer` + frozen-row gating (no Edit button, "Frozen" badge, frozen versions skip the PATCH path); LEDGER 2026-04-27 14:15:00 -04:00 |       |
| A3  | [x]    | Edit current draft version; cannot edit a published version                                                       | `PATCH /api/v1/strategies/{strategy_id}/versions/{version_id}`; `backend/tests/unit/api/test_strategy_routes.py::test_strategy_routes_edit_draft_version_and_reject_frozen`; `python -m pytest backend/tests/unit -q` -> 1122 passed |       |
| A4  | [x]    | Publish version; lineage shows publisher + timestamp                                                              | `POST /api/v1/strategies/{strategy_id}/versions/{version_id}/freeze` now rejects until the StrategyVersion is attached to a Deployment; persists `X-Operator-Session-Id` as `frozen_by`; `backend/tests/unit/api/test_strategy_routes.py::test_strategy_routes_edit_draft_version_and_reject_frozen`; `python -m pytest backend/tests/unit -q` -> 1131 passed |       |
| A5  | [x]    | Strategy detail page renders versions, latest published, deployments using each version                           | `/strategies/:strategyId` route (`router.tsx`) → `StrategyDetail.tsx` Overview + Latest published + Versions table joined to `/api/v1/deployments`; `StrategyDetail.test.tsx` 3 tests; LEDGER 2026-04-27 14:15:00 -04:00 |       |
| A6  | [x]    | Banned-name lint clean across new strategy code paths                                                             | `npm run lint:names` -> `frontend banned-name lint: clean` (2026-04-27 13:59:20 -04:00); `python -m pytest backend/tests/unit/lint -q` -> 179 passed |       |

## B. Backtest (operator-grade quant)

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| B1  | [x]    | `POST /api/v1/research/backtests` accepts strategy_version_id + universe + date range + cost model + capital      | `backend/tests/unit/api/test_research_run_routes.py::test_research_backtest_create_status_results_metrics_and_cost_model`; LEDGER 2026-04-27 13:55:10 -04:00 |       |
| B2  | [x]    | Run is durable: `GET /api/v1/research/backtests/{id}` shows queued → running → completed/failed                   | `backend/tests/unit/api/test_research_run_routes.py::test_research_backtest_create_status_results_metrics_and_cost_model`; `python -m pytest backend/tests/unit -q` -> 1116 passed |       |
| B3  | [x]    | Results endpoint returns: equity curve, trade ledger, per-symbol breakdown, drawdown series                       | `GET /api/v1/research/backtests/{id}/results`; `backend/tests/unit/api/test_research_run_routes.py` |       |
| B4  | [x]    | Metrics: CAGR, Sharpe, Sortino, Calmar, max DD, hit rate, profit factor, expectancy, exposure, turnover, time-in-market | `GET /api/v1/research/backtests/{id}/metrics`; `backend/tests/unit/api/test_research_run_routes.py` |       |
| B5  | [x]    | Cost model: commissions, slippage (bps + spread), borrow cost for shorts, T+1 settlement                          | `backend/app/research/backtests/service.py`; `backend/tests/unit/api/test_research_run_routes.py` |       |
| B6  | [x]    | Regime tag stamped on every bar; per-regime metric breakdown (bull/bear/sideways/volatile/trending)               | `backend/tests/unit/research/test_regime_classifier.py`; `backend/tests/unit/api/test_research_run_routes.py::test_research_backtest_create_status_results_metrics_and_cost_model`; `python -m pytest backend/tests/unit -q` -> 1120 passed |       |
| B7  | [x]    | Backtest results page renders B3+B4+B6 with no UUIDs as primary labels                                            | `frontend/src/routes/Backtests.tsx` (list + detail), `Backtests.test.tsx` 4 tests; equity curve + drawdown sparklines, per-regime metric table, per-symbol breakdown, trade ledger; primary labels = strategy display name + ticker symbols; LEDGER 2026-04-27 14:30:00 -04:00 |       |
| B8  | [x]    | Frontend `BacktestRunResults` survives backend additive fields (`.passthrough()` zod)                             | `frontend/src/api/schemas/researchRuns.ts` — `BacktestRunSchema`, `BacktestRunListSchema`, `BacktestResultsResponseSchema`, `BacktestMetricsResponseSchema`, `EquityPointSchema`, `DrawdownPointSchema`, `TradeLedgerEntrySchema`, `PerSymbolBreakdownSchema`, `RegimeTagSchema`, `StatusHistoryEntrySchema` all `.passthrough()`; status enums loosened to `z.string()`; verified by `Backtests.test.tsx::opens detail and renders metrics + per-regime + trade ledger from passthrough payloads` (additive `sharpe_oos`, `settlement_days`, `generated_at`, `regime_summary` fields accepted) |       |

## C. Sim Lab (batch + stream)

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| C1  | [x]    | `POST /api/v1/research/sim_lab/runs` (batch) — synchronous-style run over fixed window                            | `backend/app/research/sim_lab/service.py`; `backend/tests/unit/api/test_research_run_routes.py::test_research_sim_lab_batch_run_executes_fixed_window_replay`; `python -m pytest backend/tests/unit -q` -> 1127 passed |       |
| C2  | [x]    | Stream mode — WebSocket emits bars + signal_plans + virtual fills as the simulator advances                       | `GET ws /api/v1/research/sim_lab/stream`; transient visualization telemetry, no session-row persistence; flattened virtual fill/position/equity payloads; `backend/tests/unit/api/test_research_run_routes.py::test_research_sim_lab_stream_emits_ordered_replay_artifacts`; live smoke sessions 157 -> 157; `python -m pytest backend/tests/unit -q` -> 1131 passed |       |
| C3  | [ ]    | Sim uses the **same** Strategy → Deployment → SignalPlan path as live; no duplicate runtime                       |          |       |
| C4  | [x]    | Per-tick equity, per-position state, virtual broker fills visible in the UI                                       | `frontend/src/routes/SimLab.tsx` `SimLabStreamView` + `frontend/src/components/charts/SimLabReplayChart.tsx` (new): WS `/api/v1/research/sim_lab/stream` consumer renders one candle chart per symbol with entry/exit triangle markers per virtual fill, equity curve overlaid on a separate price scale, KPI strip (Bars / SignalPlans / Fills / Last equity / Last update). Per operator feedback "see what is going on on charts not fill up my screen" — chart-first, tables retired. Schema additions: `SimLabStreamMessageSchema` (passthrough). LEDGER 2026-04-27 15:42:00 -04:00. |       |
| C5  | [ ]    | Operator can pause / step / resume a streaming sim                                                                | Awaits server-side control plane: Codex's current stream is a deterministic dump. Client-side replay throttle would be doctrinally dishonest ("never assert state without backing data"); ticking only when Codex ships pause/step/resume on the WS. |       |
| C6  | [x]    | Sim Lab page first-class route (not a drill-in); supports comparison of two configs side by side                  | `frontend/src/routes/SimLab.tsx` first-class route at `/sim-lab` with sessions table + side-by-side `CompareGrid`; `SimLab.test.tsx` 4 tests including the two-session diff path; LEDGER 2026-04-27 14:38:00 -04:00 |       |

## D. Chart Lab (indicator + strategy comparison, batch + stream)

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| D1  | [ ]    | Batch render: pick N symbols × M indicators × K timeframes → charts grid with shared cursor + zoom                |          |       |
| D2  | [ ]    | Stream render: live bars + indicator updates over `/ws/chart_lab/{session}`                                       |          |       |
| D3  | [ ]    | Indicator library: at least SMA, EMA, RSI, MACD, ATR, Bollinger, VWAP, ADX, Donchian, Z-score                     |          |       |
| D4  | [ ]    | Indicator comparison view: same chart, multiple indicators stacked or overlayed with legend                       |          |       |
| D5  | [ ]    | Strategy comparison view: same window, multiple strategies' SignalPlans rendered as shapes on the chart           |          |       |
| D6  | [ ]    | Regime overlay toggle: shaded background bands per regime classification                                          |          |       |
| D7  | [x]    | Pin a Chart Lab session as the home dashboard hub card; status pulse reflects stream health                       | `frontend/src/components/cards/ChartLabHubCard.tsx` (new) + `frontend/src/lib/chartLabPin.ts` (new) + Pin/Unpin in `ChartLab.tsx`; `PulseDot` tone+pulse driven by `useWS` status (open+bar=ok-pulse, open+no-bar=info-pulse, connecting=info, reconnecting=warn, error=danger, no-pin=muted); `ChartLabHubCard.test.tsx` 3 tests; LEDGER 2026-04-27 14:46:00 -04:00 |       |

## E. Walk-Forward Analysis

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| E1  | [ ]    | Anchored + rolling windows configurable; minimum 5 OOS folds                                                       |          |       |
| E2  | [ ]    | Per-fold IS metrics + OOS metrics + decay (Sharpe IS - Sharpe OOS, hit rate decay, expectancy decay)              |          |       |
| E3  | [ ]    | Parameter stability heatmap across folds                                                                          |          |       |
| E4  | [ ]    | OOS regime breakdown per fold (which regimes did this strategy actually see OOS?)                                 |          |       |
| E5  | [ ]    | Equity curve with IS / OOS shading                                                                                |          |       |
| E6  | [x]    | Walk-forward results page summarizes: median OOS Sharpe, OOS-vs-IS decay, regime fit score, recommend / reject     | `frontend/src/routes/WalkForward.tsx` (rewrite) + `WalkForward.test.tsx` 4 tests; Summary KpiCards (median OOS Sharpe / OOS-vs-IS decay / regime fit score / folds passed); recommend/reject badge tone-mapped; per-fold metrics, parameter stability heatmap, OOS regime breakdown, equity-with-IS/OOS-shading panels behind `AwaitingApiOrError` pinned to `/api/v1/walk-forward/runs/{run_id}/{folds,parameter-stability,oos-regime-breakdown,equity-curve}`; LEDGER 2026-04-27 14:54:00 -04:00 |       |

## F. Regime Mapping

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| F1  | [x]    | Regime classifier service at `backend/app/research/regimes/` — bull/bear/sideways/volatile/trending + confidence  | `backend/app/research/regimes/classifier.py`; `backend/tests/unit/research/test_regime_classifier.py` |       |
| F2  | [x]    | Classifier deterministic + cached per (symbol, timeframe, bar_window)                                             | `backend/tests/unit/research/test_regime_classifier.py::test_regime_classifier_is_deterministic_and_cached_per_symbol_timeframe_window` |       |
| F3  | [ ]    | Backtest, Sim Lab, Walk-Forward all join their bar series to the regime label                                     |          |       |
| F4  | [ ]    | Per-regime metric tables on the backtest + walk-forward result pages                                              |          |       |
| F5  | [ ]    | Per-strategy "regime fit score" (composite: weighted Sharpe by regime exposure, with confidence interval)         |          |       |

## G. Cross-Cutting

| #   | Status | Item                                                                                                              | Evidence | Notes |
| --- | ------ | ----------------------------------------------------------------------------------------------------------------- | -------- | ----- |
| G1  | [x]    | `frontend_api_contract` test green: every frontend research API call has a registered FastAPI route              | `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py -q` -> 2 passed, 5 warnings (2026-04-27 14:07:44 -04:00) |       |
| G2  | [ ]    | Vitest suite green for every research route page                                                                  |          |       |
| G3  | [x]    | Backend pytest green; coverage on research, regimes, walk_forward, sim_lab modules                                | `python -m pytest backend/tests/unit -q` -> 1131 passed, 6 warnings (2026-04-27 15:31:00 -04:00) |       |
| G4  | [x]    | Banned-name lint green                                                                                            | `python -m pytest backend/tests/unit/lint -q` -> 179 passed (2026-04-27 15:29:00 -04:00) |       |
| G5  | [ ]    | LEDGER entry per route + per schema; both inboxes drained or expired                                              |          |       |

---

## Approval Procedure

When all rows are `[x]`, both agents append a `request · gate` message to
the operator (via the operator's normal channel — chat, not inbox) with
a single-line "Ready for Nanyel approval — gate complete" plus a link to
this file. Nanyel personally toggles each row to `[A]` with the date in
the Notes column. The loop ends when every row is `[A]`.

Until then, **the loop continues**.
