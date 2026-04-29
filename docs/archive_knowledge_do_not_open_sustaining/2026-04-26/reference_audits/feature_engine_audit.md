# Feature Engine Architecture Audit — Ultimate Trading Software 2026
> Audit date: 2026-04-23 · Auditor: senior quant systems architect

---

## Overview

The feature engine spans six subsystems: identity (`FeatureSpec`/`FeatureKey`), planning (`FeaturePlan`), runtime caching (`IndicatorCache`/`FeatureCache`), computation (BacktestEngine + `technical.py`), live aggregation (`CerebroEngine`/`BarAggregator`), and session/calendar handling (`MarketCalendarService`/`SessionContext`). The architecture is structurally sound at the individual-component level but has systemic gaps at the boundaries between those components — specifically at the replay-vs-live boundary, the warmup estimation layer, the mutable-entity versioning gap, and the multi-timeframe alignment seam. These gaps do not prevent the system from running; they prevent it from being deterministic and auditable.

---

## FeatureSpec

`FeatureSpec` is a frozen dataclass with four fields: `kind`, `timeframe`, `source`, and `params` (a dict). The frozen constraint correctly prevents mutation after construction.

**What it gets right:**
- Immutability via `frozen=True`.
- `params` is captured as a dict, which means all parameterization is explicit and inspectable.
- The `source` field separates price-source semantics (close, high, open, typical) from kind semantics.

**Problems:**

1. **`params` dict equality is shallow.** If `params` contains a mutable value (e.g., a list of levels for a custom indicator), two `FeatureSpec` instances with identical fields will not be considered equal by Python's default frozen-dataclass equality if the list contents are equal but the objects are different references. However, the actual `make_feature_key()` function in `keys.py` serializes params to JSON for key generation — so the key is correct, but `FeatureSpec.__eq__` (used in deduplication in `planner.py`) may not be. This creates a split: key-based deduplication works; set-based deduplication (if anyone uses `set[FeatureSpec]`) is broken for list-valued params.

2. **`timeframe` is a free string with no enum constraint.** `FeatureSpec(kind="ema", timeframe="1min", ...)` and `FeatureSpec(kind="ema", timeframe="1m", ...)` are different specs and will generate different keys. `BarAggregator` uses `"1m"`, `"5m"` etc.; `_COLD_START_DAYS` uses `"1m"`, `"1d"`; `YF_INTRADAY_MAX_DAYS` uses `"1m"`, `"5m"`. If any call site normalizes timeframe differently (e.g., `"60m"` vs `"1h"`, `"day"` vs `"1d"`), the feature is recomputed rather than cache-hit, silently.

3. **No version field on `FeatureSpec`.** The computational definition of an indicator can change (e.g., ATR switching from Wilder EWM to simple average, or RSI computation changing ddof). When that happens, all cached frames referencing the old spec are stale but share the same key. There is no mechanism to invalidate them.

4. **`source` field is unused in most indicators.** `technical.py` uses `close`, `high`, `low`, `open` as hardcoded column names. The `source` field on `FeatureSpec` is not passed into indicator computation. It is present in the identity key but does not affect computation. This means two specs that differ only in `source` will generate different keys but produce identical computed values — wasted compute — and conversely, if source was ever intended to route computation to a different price series, it does not.

---

## FeatureKey

`make_feature_key(spec)` serializes `FeatureSpec` to a JSON string: `json.dumps({"kind": spec.kind, "timeframe": spec.timeframe, "source": spec.source, "params": normalized_params}, sort_keys=True)`.

`normalize_feature_params(params)` sorts dict keys and normalizes strings to lowercase.

**What it gets right:**
- `sort_keys=True` makes key generation order-independent.
- `normalize_feature_params` prevents `"EMA"` vs `"ema"` drift.
- The key is deterministic for any given spec.

**Problems:**

1. **Float normalization is absent.** `params={"length": 14}` and `params={"length": 14.0}` produce different JSON: `"14"` vs `"14.0"`. Integer vs float params for the same logical indicator will miss cache. This can happen when: params are parsed from YAML (returns floats), from StrategyConfig JSON (may return int or float depending on JSON serializer), or from the AI generation endpoint (returns Python numeric).

2. **No canonical form for equivalent parameterizations.** `params={"fast": 12, "slow": 26}` and `params={"fast": 12, "slow": 26, "signal": 9}` for MACD produce different keys even if `signal=9` is the default. A call site that omits `signal` and one that explicitly passes `signal=9` will compute MACD twice. `normalize_feature_params` does not inject defaults.

3. **`make_runtime_identity_key`** hashes `(symbol, timeframe, sorted_feature_keys_tuple)`. The tuple sort is lexicographic on the key strings. This is deterministic for a fixed set of specs, but: if the feature set for a symbol+TF changes between two live sessions (e.g., a new program subscribes and adds a feature), the runtime identity key changes. The old `IndicatorFrame` in `_frames_by_runtime_identity` becomes an orphan that is never evicted — it accumulates in memory until process restart. There is no eviction policy on `_frames_by_runtime_identity`.

4. **Keys are opaque strings.** Debugging which features are in a cache miss requires round-tripping the JSON string back to a spec. There is no helper to deserialize a key back to a FeatureSpec for logging or alerting.

---

## FeaturePlan

`FeaturePlan` is a frozen dataclass built by `build_feature_plan()`. It deduplicates `FeatureSpec`s by key, collects unique timeframes, and estimates warmup bars per timeframe.

**What it gets right:**
- Deduplication by key prevents redundant computation.
- Warmup estimation is per-timeframe, which is correct (a 1-hour EMA(20) needs more 1-min bars than a 1-min EMA(20)).
- Freezing prevents mutation after build.

**Problems:**

1. **Warmup estimation is structurally wrong for composite indicators.** `estimate_feature_warmup_bars(spec)` returns `max(max_numeric_param * 3, 50)` for all indicators. For MACD with `slow=26, signal=9`, this returns `max(26 * 3, 50) = 78`. The actual MACD warmup requires `slow + signal - 1 = 34` bars minimum, or more precisely `slow * 3` bars for EWM stability. For Ichimoku with `senkou_b_period=52`, the formula returns `156` but Ichimoku also shifts forward by `displacement=26` — the actual required lookback is `52 + 26 = 78`, not `156`. Over-estimation wastes data (minor). Under-estimation causes silent NaN injection at bar boundaries.

2. **The factor of 3 is a heuristic with no mathematical basis.** EWM-based indicators (ATR, RSI, EMA) with alpha = 2/(N+1) require approximately `3 * N` bars to converge to 99% of their asymptotic value. SMA requires exactly `N` bars. WMA requires exactly `N` bars. The same `* 3` factor is applied to all, which is correct for EWM but over-estimates for SMA/WMA. More critically, there is no distinction between SMA warmup (exact) and EWM warmup (approximate). An SMA(200) with `* 3 = 600` bars warmup is requesting 3× more data than needed. On an intraday TF, this is a real cost.

3. **Warmup bars are per-timeframe, not per-spec.** The plan stores `warmup_bars_by_timeframe: dict[str, int]` as the max warmup across all specs for that TF. This means the warmup for a 1h bar series is determined by the most expensive indicator at 1h, and all other indicators on 1h get that same warmup window. This is correct for data fetching but means that an indicator that requires only 20 bars of warmup will receive 600 bars of warm-up data if one other indicator on the same TF needs 600. The excess data is not harmful, but means `IndicatorCache.WINDOW_SIZE = 250` may be too small for some combinations (e.g., a 1d SMA(200) with ATR(14) on 1d: warmup_bars = max(200*3, 14*3) = 600 but WINDOW_SIZE = 250 — the cache holds only 250 bars, less than the warmup requirement).

4. **`FeaturePlan` does not capture the data source.** The plan knows what features to compute but not where to get the underlying bars. Source resolution happens in `source_contracts.py` at a different layer. This means the plan is not self-contained — you cannot reproduce a feature computation from the plan alone. For audit trail and replay determinism, the plan should include `FrameProvenance` at build time.

5. **No mechanism to diff two `FeaturePlan`s.** When a program is updated (new strategy version, changed execution style adding a new indicator), a new plan is built. The old plan is discarded. There is no diffing or incremental update — the entire cache for that program's symbol+TF combination is invalidated and warmed up from scratch. For live programs, this means a cold-start re-warm on every program update, which at `_COLD_START_DAYS["1h"] = 80` days of data is a significant API call.

---

## Registry

`CerebroRegistry` maps `(symbol, timeframe)` pairs to `SymbolTimeframeDemand` objects, which track which programs demand features on that symbol+TF and what features they need.

**What it gets right:**
- Program registration/deregistration is explicit.
- Demand is computed as the union of all programs' feature requirements — any program can cache-hit features needed by another program.
- `get_required_feature_plan()` builds a deterministic `FeaturePlan` from the demand union.

**Problems:**

1. **No locking on concurrent program registration.** `CerebroRegistry` is not thread-safe. `subscribe_program()` in `CerebroEngine` calls `registry.register_program()` and then `_cold_start_symbols()`. If two programs are registered concurrently (two async `subscribe_program` calls overlapping), both read the registry state before either writes, and the cold-start is triggered twice for the same symbols — wasting API calls. `asyncio` cooperative multitasking makes this unlikely but not impossible given `await` points inside `subscribe_program`.

2. **Feature union is not re-evaluated on unregister.** When a program is unregistered (`unregister_program()`), the demand for that program's features is removed from `SymbolTimeframeDemand`. But the `IndicatorCache` continues to compute those features on every new bar — it caches the full feature set that was ever registered, not the current demand set. There is no "GC pass" to stop computing features that no program currently needs.

3. **No persistence.** `CerebroRegistry` state is in-memory only. On process restart, all program demand must be re-registered from scratch. The `CerebroEngine.subscribe_program()` is called at deployment start but there is no guarantee that all currently active deployments call `subscribe_program()` on startup — this depends on deployment lifecycle management in `deployment_service.py`. If a deployment is "running" in the DB but the process restarted, it will not be in the registry and its features will not be computed.

4. **`ProgramDemand.indicators` uses `IndicatorRequirement` objects, not `FeatureSpec` objects directly.** `IndicatorRequirement.to_feature_spec(timeframe)` is called to convert, but this means the timeframe is injected at demand-union time, not at program-registration time. If a program registers with a `timeframe=None` indicator (e.g., a raw price condition), `to_feature_spec(timeframe)` receives the symbol+TF loop's timeframe — which may not be what the strategy intends if the strategy uses a multi-timeframe indicator.

---

## Cache

`IndicatorCache` stores `IndicatorFrame` objects keyed by `(symbol, timeframe)` and by `runtime_identity_key`. Each frame holds a rolling deque of raw bars (`WINDOW_SIZE = 250`) and a computed indicators DataFrame.

**What it gets right:**
- Rolling deque correctly evicts old bars — memory is bounded.
- `is_warm` flag prevents signal evaluation before warmup is complete.
- `FrameProvenance` tracks which provider fetched data and at what time.
- `annotate_feature_specs()` rebuilds the frame's feature column metadata without recomputing indicators.

**Problems:**

1. **`WINDOW_SIZE = 250` is a hardcoded constant and may be insufficient.** As noted above, `estimate_feature_warmup_bars()` can return up to `max_param * 3`. For a daily SMA(200), warmup = 600. But `WINDOW_SIZE = 250` means the cache holds at most 250 bars. The first 350 bars of warmup data are consumed and discarded by the deque before it fills. When `is_warm` is set based on `bar_count >= warmup_bars`, and `warmup_bars = 600` but `bar_count` can never exceed 250 (the deque max), `is_warm` will never become `True`. This is a **silent permanent not-warm state** — the system will never compute features for that symbol+TF combination. There is no warning or error.

   Specific case: `ExecutionStyle.atr_timeframe` can be `"1d"` with `atr_length` up to 50. Warmup = `50 * 3 = 150`. This fits in 250. But if a user creates a SMA(200) on daily or a rolling Kelly lookback of 100 on daily, the cache silently breaks.

2. **`warm_up()` and `update()` both call `_compute_indicators()` which calls `BacktestEngine._compute_indicators()`.** This means the live cerebro path re-enters the BacktestEngine's indicator computation on every bar update. The BacktestEngine's `_compute_indicators` is designed for batch computation over a full historical DataFrame. When called on a rolling 250-bar window in a live context, it recomputes the full DataFrame on every bar. For an EWM indicator, this means the EWM state is reseeded from the beginning of the window on every bar — not continued from the previous computation state. This is correct mathematically (EWM over last 250 bars converges) but is O(WINDOW_SIZE) per bar per feature, not O(1).

3. **No write-through to disk.** The cache is in-memory only. Process restart requires full cold start from the data provider. At `_COLD_START_DAYS["1d"] = 400`, a daily SMA(200) cold start fetches 400 days of daily bars from yfinance or Alpaca. This is a significant startup latency and API load for live deployments.

4. **`_frames_by_runtime_identity` grows unboundedly.** When a program's feature set changes (new version registered), a new runtime identity key is created. The old frame in `_frames_by_runtime_identity` is orphaned. There is no TTL, no LRU, and no max-size constraint on this dict. On long-running processes with frequent program updates, this leaks memory.

5. **Cache invalidation on data correction is absent.** If a historical bar is revised (e.g., a split adjustment from Alpaca), the cached bars in the deque are stale. There is no mechanism to receive or propagate bar corrections to the cache. In live operation, this means that a post-split indicator computation will use a mix of pre-split and post-split bars in the rolling window until the pre-split bars age out of the deque.

---

## Batch vs Incremental Modes

The system has two distinct execution paths for indicator computation:

**Batch mode** (BacktestEngine, SimulationService):
- Fetches full historical DataFrame for each symbol+TF.
- Calls `_compute_indicators()` once over the entire DataFrame.
- Each indicator is computed as a vectorized Pandas operation across all rows.
- Session features, regime maps, FVG detection, and S/R zones are precomputed before the bar loop.

**Incremental mode** (CerebroEngine/IndicatorCache):
- Receives 1-minute bars from a live feed.
- Aggregates to higher TFs via `BarAggregator`.
- On each completed higher-TF bar, appends to the rolling deque and recomputes the full indicator DataFrame over the window.
- This is batch computation over a rolling window, not true incremental computation.

**Problems:**

1. **EWM state is not preserved between incremental updates.** In batch mode, Pandas `ewm()` processes all rows in one pass — the decay state is continuous. In incremental mode, `_compute_indicators()` is called on a 250-bar window each update. The EWM is reseeded from bar 0 of the window on each call. For an EMA(200) on a 250-bar window, the first 200+ bars of the window are in the "convergence zone" — the EMA value at bar 250 will differ from the batch-mode value because batch mode had 400+ bars of history to establish the EWM state. This is the **primary replay-vs-live mismatch source**.

   Quantified: EWM with alpha = 2/(N+1) has weight for the oldest of W window bars of `(1-alpha)^(W-1)`. For EMA(200), alpha ≈ 0.01, and with W=250, the oldest bar has weight `0.99^249 ≈ 0.082` — 8.2% of the final value comes from bar 1 of the 250-bar window, not from the infinite history. In batch mode with 400 bars, that contribution is `0.99^399 ≈ 0.018`. The two modes will produce different EMA values by the difference of those contributions × their price. On a $100 stock with high EWM weight, this difference is on the order of $0.60–$1.50 per bar.

2. **Session features are recomputed differently in batch vs incremental.** In batch mode, `compute_session_state_features()` uses `SessionContext` built from a complete date index and `MarketCalendarService`. In incremental mode (live), `IndicatorCache` calls `BacktestEngine._compute_indicators()` which also builds a `SessionContext` — but it rebuilds it from scratch on every bar update, over the rolling 250-bar window. The resulting `session_date` and `session_bar_number` values may differ from batch mode if the 250-bar window begins mid-session (e.g., a partial trading day at the window boundary).

3. **`BarAggregator` uses a fixed bar count per timeframe** (`_TF_BAR_COUNTS = {"5m":5,"15m":15,...,"1d":390}`). The daily bar count of `390` assumes a full regular session (6.5 hours × 60 minutes). On half-days (early close), a day bar will never complete because the 390th minute bar never arrives. Half-days are in `MarketCalendarService` but `BarAggregator` does not consult it. The incomplete day bar is never emitted. **Any indicator that depends on a completed daily bar will be one day behind on half-days.**

4. **No mechanism to test that batch and incremental modes produce the same result for a given history.** There are tests for feature plan determinism, cache identity, and ingress contracts, but no round-trip test that feeds the same bars through batch mode and incremental mode and compares feature values.

---

## Session / Calendar Handling

`MarketCalendarService` is a frozen dataclass with hardcoded US market holidays and half-days for 2024–2026. `SessionContext` wraps the resulting series for use by feature computations.

**What it gets right:**
- Half-days are tracked (`is_half_day` in `market_day_types`).
- `in_regular_session_series()` correctly filters out pre/post-market bars.
- `earnings_blackout_active` uses `EarningsCalendar` which can refresh from Alpaca.

**Problems:**

1. **Holidays and half-days are hardcoded through 2026 only.** There is no mechanism to extend the calendar without a code change. In 2027, all calendar-dependent features (`session_date_series`, `market_day_type_series`, `in_regular_session_series`) will silently fall back to treating all bars as regular session bars. This affects: session_bar_number, prev_day_levels, prev_week_levels, session liquidation timing, gap risk filter, earnings blackout, opening range computation, and PDT day-trade counting. **Every session-aware feature breaks after December 31, 2026 with no warning.**

2. **`MarketCalendarService` is a module-level singleton.** It is constructed once at import time. If the calendar data is wrong for a specific date (e.g., an ad-hoc market closure like a national emergency), there is no way to update it at runtime without restarting the process. For a live trading system, this is a meaningful operational risk.

3. **`SessionWindowConfig.can_enter()` uses `datetime.now()` for live and compares against hardcoded session time strings.** In backtesting, the session window is checked against the bar timestamp (correct). In live mode, there is a race condition: the bar is received at `bar.time`, but `can_enter()` evaluates `datetime.now()` which may be slightly later. For bars near the session boundary (e.g., a bar arriving at 09:29:58 when the session opens at 09:30:00), the entry could be incorrectly blocked. In backtesting, this race does not exist because the bar timestamp is used. This is another replay-vs-live divergence source.

4. **Timezone handling is implicit.** `MarketCalendarService` computes session dates from a DatetimeIndex. Whether that index is UTC, US/Eastern, or naive depends on the data provider. `yfinance` returns UTC timestamps; Alpaca returns UTC timestamps. The `session_date` grouping in `compute_prev_day_levels()` uses `.dt.date` which, on a UTC-indexed series, will put bars between midnight UTC and 4:00 AM ET into the "wrong" calendar day relative to NYSE sessions. This creates prev_day_levels that are one day off for the first hours of each UTC day (00:00–04:00 UTC = 19:00–23:00 ET prior day). This is not an issue for RTH-only data but will corrupt prev_day features if pre-market data is ever included in the bar series.

5. **`EarningsCalendar` uses a module-level singleton `_calendar` with `days_before=3, days_after=1` hardcoded.** If a program has `earnings_blackout_enabled=True` in its StrategyControls and the earnings calendar has not been refreshed recently (stale), the blackout will fail to fire for upcoming earnings events — no warning is emitted. The `refresh_from_alpaca()` is `async` but there is no scheduled periodic refresh. The calendar is only populated when `refresh_from_alpaca()` is called explicitly.

---

## Multi-Timeframe Alignment

Multi-timeframe features appear in two contexts: (1) the `ExecutionStyle.atr_timeframe` field which allows ATR to be computed on a different timeframe than the primary signal timeframe; (2) `extra_tf_data` passed to BacktestEngine for strategy conditions that reference higher-TF indicators (e.g., a 1h EMA used as a regime filter in a 5m strategy).

**What it gets right:**
- `BacktestEngine._resolve_atr_for_config()` has an explicit priority order for ATR source selection: config-specified TF data → global ATR override → None.
- `_extra_tf_data` is a dict passed at engine init, keyed by timeframe string.
- `EvalContext.extra_bars` and `extra_bar_index` expose the higher-TF bar to condition evaluation.

**Problems:**

1. **Alignment is by timestamp comparison, not by calendar alignment.** When a 5m strategy bar has timestamp `2024-01-15 10:30:00` and the condition evaluates against a 1h bar, the system looks for the most recent 1h bar with timestamp ≤ the 5m bar timestamp. This is correct in theory but depends on the 1h bar having a timestamp that matches the Alpaca/yfinance 1h bar close time convention. Alpaca 1h bars have timestamps at the bar open (e.g., `10:00:00` for the 10:00–11:00 bar). A 5m bar at `10:30:00` should use the `10:00:00` 1h bar — and the `≤` comparison does find it. However, if the 1h data has even a 1-second timestamp offset due to exchange delay or data normalization, the `≤` comparison picks the wrong bar. There is no tolerance window and no logging when alignment falls back.

2. **`extra_tf_data` is not available in incremental/live mode.** `BacktestEngine` accepts `_extra_tf_data` in its `__init__`. `CerebroEngine` does not pass multi-TF bars to the indicator computation — the `IndicatorCache._compute_indicators()` call only receives the symbol's own bars at its own timeframe. If a live strategy references a 1h indicator while running on 5m bars, **the indicator is silently unavailable in live mode**. `EvalContext.extra_bars` will be empty, and any condition that references a higher-TF indicator will evaluate to `False` (or may throw a KeyError, depending on the `_resolve_value()` fallback).

3. **There is no validation that `extra_tf_data` is provided at launch time when the strategy requires it.** `build_feature_plan_preview()` in `preview.py` collects multi-TF specs from the strategy config, but the BacktestLauncher does not check whether `_extra_tf_data` was actually fetched for all required TFs before launching the engine. If a required TF is missing, the engine runs silently using only the primary TF data.

4. **Multi-TF warmup is not coordinated.** `FeaturePlan.warmup_bars_by_timeframe` gives the warmup requirement per TF, but the BacktestEngine's warm-up for `_extra_tf_data` is not controlled by the `FeaturePlan` — it is whatever date range was fetched by `launch_backtest()`. If the extra TF data is shorter than the warmup requirement (e.g., the user selected a short backtest date range), the first N bars of the higher-TF features will be NaN and conditions will silently fail.

5. **`BarAggregator` does not emit a higher-TF bar on the first bar after cold start.** On the first 1m bar of a live session, the 5m partial bar begins accumulating. Until the 5th minute bar is received, no 5m bar is emitted. The first completed 5m bar arrives at bar 5. Any strategy condition that needs a 5m indicator value will evaluate against a `None` or missing `extra_bars` entry for the first 4 minutes of live operation. This is not a warmup issue — it is a structural gap in the aggregation startup path.

---

## 1. Where Could Feature Drift Occur?

Feature drift is the condition where a feature value computed today for a historical bar differs from the value computed at the time of the original backtest — or where the same feature produces different values in backtest vs live operation for the same bar.

**Drift source A — EWM reseeding on every incremental update.** Every call to `IndicatorCache.update()` re-executes `_compute_indicators()` over the full 250-bar rolling window. EWM state is not carried forward; it restarts from bar 0. For a long-period EMA (e.g., EMA(200)), the value computed live over a 250-bar window will differ from the batch-mode value computed over 400+ bars by a non-negligible amount that varies with price volatility. The drift is systematic and predictable in direction (live EMA lags less than batch EMA in uptrend, lags more in downtrend) but its magnitude is not bounded.

**Drift source B — Mutable StrategyControls and ExecutionStyle entities.** Historical `BacktestRun` records link to `strategy_governor_id` and `execution_style_id` by foreign key, but those entities are mutable (no versioning). If a user edits a `StrategyControls` entity after a backtest has been run, the stored `strategy_governor_id` now points to a different configuration than was in use during the backtest. Any re-analysis, re-run, or comparison that loads the controls by ID will silently use the mutated config. This is a **systematic audit trail corruption** — not feature computation drift per se, but drift in the config that determines which features are computed and how they gate signals.

**Drift source C — `normalize_feature_params` does not canonicalize numeric types.** An `int` param serializes differently than a `float` param with the same value. Over time, if the config loader changes (e.g., YAML → JSON → Pydantic), numeric types may shift, causing cache misses and recomputation from a cold start with potentially different warmup data.

**Drift source D — `MarketCalendarService` hardcoded through 2026.** After January 2027, session-based features (prev_day_levels, session_bar_number, opening range, earnings_blackout) will compute incorrectly. Features that were previously bounded to regular session bars will be computed over all bars including pre/post-market. A backtest run in 2027 will produce different feature values than an identical run in 2026.

**Drift source E — Swing high/low indicator has a symmetric lookback that causes retroactive updates.** `detect_swing_points()` uses a symmetric lookback window — a swing high at bar `i` is confirmed only when `lookback` subsequent bars have been observed. In batch mode over a completed DataFrame, this is fine (all bars are known). In incremental live mode, the swing point at `i` cannot be confirmed until `lookback` more bars arrive. If the implementation in `technical.py` uses the batch version directly on the rolling window (detecting swings that include the last `lookback` unconfirmed bars), swing features in live mode will differ from batch mode because batch mode assigns confirmation to an earlier bar timestamp.

**Drift source F — S/R zone `_merge_zones()` is not deterministic for zones at exactly `zone_merge_pct * 0.2%` distance.** Zones at the merge boundary may or may not be merged depending on floating-point precision and sort order. Batch mode over a full history produces a stable zone set. Live mode recomputes S/R zones over the rolling 250-bar window — zones that were merged in batch mode may not be merged in live mode if the boundary bars are not in the window.

---

## 2. Where Could Replay vs Live Mismatch Occur?

Replay refers to bar-by-bar re-execution of the BacktestEngine (via `BacktestStepper`) or Simulation Lab. Live refers to `CerebroEngine` processing real-time bars from Alpaca.

**Mismatch A — EWM state (see Drift source A above).** EMA, ATR (Wilder EWM), and RSI (Wilder EWM) values will differ between replay/backtest (computed over full history) and live (computed over 250-bar rolling window) for the same bar timestamp. The mismatch is largest at the beginning of a live deployment and decreases as the live session extends (more bars reduce the relative weight of the EWM seed). It never fully vanishes.

**Mismatch B — `SessionWindowConfig.can_enter()` uses `datetime.now()` in live mode.** In replay mode, `can_enter()` uses the bar's timestamp. In live mode, `can_enter()` uses `datetime.now()`. Bars at session boundaries will be handled differently depending on the wall-clock latency of bar delivery.

**Mismatch C — `BarAggregator` VWAP uses running `price * vol / total_vol` within a partial bar.** The VWAP for a 5m bar in live mode is the running VWAP of the constituent 1m bars as they arrive. In replay mode (if the replay uses 5m bars directly), the VWAP is the VWAP of the complete 5m bar as provided by the data feed. If the data provider rounds VWAP differently than the `BarAggregator`'s running computation, the 5m bar VWAP used in a live condition will differ from the 5m bar VWAP in the backtest.

**Mismatch D — `extra_tf_data` is not present in live mode** (see Multi-Timeframe Alignment Problem 2). Any strategy that uses a higher-TF indicator in a live deployment will produce different condition evaluation results than in backtest — the higher-TF condition silently evaluates to `False` in live mode.

**Mismatch E — FVG detection is a 3-bar pattern** (`bar[i-1].high < bar[i+1].low`). In batch mode, this is detected at bar `i+1` (correct, no lookahead). In live mode, `compute_fair_value_gaps()` is called on the rolling window — the detection logic in `fvg.py` requires knowing `bar[i+1]` to confirm the gap at `bar[i]`. On the most recent bar of the rolling window, `bar[i+1]` does not yet exist. The implementation must handle this boundary — if it doesn't skip the last two bars, it either throws an IndexError or computes a false FVG using a zero-padded future bar. This needs explicit verification in the live code path.

**Mismatch F — ATR source priority differs between backtest and live.** In BacktestEngine, `_resolve_atr_for_config()` has a three-tier priority: config-TF data from `_extra_tf_data` → `_atr_override_data` → None. In live mode via `IndicatorCache`, ATR is computed from whatever is in the rolling window for the symbol's own TF. There is no `_extra_tf_data` path in live mode. If the strategy's execution style specifies `atr_timeframe="1d"` but the strategy runs on `"5m"` bars, the backtest uses 1d ATR while live uses 5m ATR. Stop distances and position sizes will differ.

**Mismatch G — `BacktestStepper.prepare()` patches `BacktestEngine` methods using `types.MethodType`.** This works correctly in isolation. However, if `BacktestStepper` is used concurrently (two simulations sharing a `BacktestEngine` instance), the patched methods would conflict. The `SimulationService` creates a new `BacktestEngine` per simulation, so this is currently safe — but the safety is implicit and not enforced.

---

## 3. Where Could Cache Inconsistency Occur?

**Inconsistency A — `_frames_by_runtime_identity` and `_frames` can be out of sync.** `warm_up()` writes to both `_frames[symbol][tf]` and `_frames_by_runtime_identity[key]`. `update()` writes to both. `annotate_feature_specs()` writes to `_frames` only — it does not update `_frames_by_runtime_identity` with the re-annotated frame. If `get_feature_frame_by_identity()` is called after `annotate_feature_specs()`, it returns a frame with stale column annotations.

**Inconsistency B — Concurrent `warm_up()` and `update()` on the same symbol+TF.** Both are `async` functions and both write to `_frames` and `_windows`. If `CerebroEngine` receives a live bar while a cold start `warm_up()` is in progress for the same symbol+TF, the `update()` call appends to `_windows[symbol][tf]` while `warm_up()` may be in the middle of constructing the initial deque. There is no lock. The resulting deque may have duplicated or interleaved bars. In Python's GIL, true data races on dict assignment are prevented, but the logical sequence `warm_up → clear deque → extend deque → set frame` is not atomic.

**Inconsistency C — `IndicatorCache._windows` and `IndicatorCache._frames` can diverge.** `warm_up()` writes both. `update()` writes both. But `annotate_feature_specs()` rebuilds `_frames[symbol][tf]` from the existing `IndicatorFrame` without using `_windows`. If a bar was added to `_windows` between the last `update()` and `annotate_feature_specs()`, `_frames[symbol][tf]` will have stale indicators that do not include the most recent bar's contribution.

**Inconsistency D — `IndicatorFrame.is_warm` flag is set by `warm_up()` and never re-evaluated.** If `warm_up()` is called with insufficient bars (e.g., the data provider returned fewer bars than `warmup_bars` due to a market holiday gap or a rate-limited API response), `is_warm` may be set to `True` based on `bar_count >= warmup_bars` even though the effective warmup was shorter than expected. There is no validation that the bars span the required date range, only that the count meets the threshold.

**Inconsistency E — Split adjustments create permanently stale cache entries.** When a stock undergoes a split after the warm-up was performed, all prices in `_windows[symbol][tf]` are at pre-split prices. New bars arriving post-split are at post-split prices. The resulting 250-bar window contains a mix of price scales. EMA, ATR, Bollinger Bands, and all price-based indicators will compute nonsensical values for bars around the split date and for approximately `warmup_bars` bars afterward. There is no mechanism to detect a split and trigger cache invalidation.

---

## 4. Where Is Causality at Risk?

Causality violations (lookahead bias) occur when the value of a feature at bar `t` uses information from bars `t+1, t+2, ...`.

**Risk A — `detect_swing_points()` in `technical.py` uses symmetric lookback.** A swing high at bar `i` is confirmed only after `lookback` subsequent bars show lower highs. In batch mode, the full DataFrame is available, so bar `i+lookback` is known when evaluating bar `i`. The swing high value is correctly assigned to bar `i`'s timestamp. However, during the backtest bar loop in `BacktestEngine.run_backtest()`, if `swing_highs` are precomputed before the loop (which they are — `_compute_indicators()` runs before the main loop), a strategy at bar `i` can see the swing high at bar `i` even though that swing high could not have been confirmed until bar `i+lookback`. **This is a lookahead bias.** The swing high should only be available at bar `i+lookback`, not at bar `i`.

**Risk B — `pivot_points()` in `technical.py` uses `shift(1)`.** Pivot points are computed from the previous bar's OHLC using `shift(1)`. This is correctly causal — the value at bar `t` uses bar `t-1` data. This is one of the few explicitly causal implementations in `technical.py`.

**Risk C — `donchian_channel()` uses `shift(1)` before rolling.** Correctly causal — the channel at bar `t` is the high/low of the previous `period` bars excluding the current bar. This is the right implementation.

**Risk D — `fractals()` in `technical.py` detects a fractal at bar `i` confirmed at bar `i+n`.** The comment says "causal confirm at i+n." The fractal value is assigned to bar `i` in the DataFrame but is computed using bars `i+1` through `i+n`. In the backtest loop, bar `i` is processed before bar `i+n` is reached — but since indicators are precomputed before the loop, the strategy at bar `i` can see the fractal value. Same lookahead bias as swing points.

**Risk E — `vwap_session()` resets daily but uses the session's full day of bars for the computation of early-session VWAP.** In a vectorized batch implementation, the VWAP for bar `t` within a session is computed over all bars `[session_start, t]`. This is causal. But if the session groupby ever includes bars beyond `t` in the VWAP sum (e.g., using the full-day sum rather than a cumulative sum), it becomes causal. This requires verification against the `vwap_session()` implementation.

**Risk F — Regime classification uses a lookback window.** ADX, ATR percentile, and EMA direction are computed over a rolling window ending at bar `t`. This is causal. However, the regime assigned to bar `t` is the regime computed at bar `t` — but the regime at entry time should be the regime computed at bar `t-1` (the last known regime before the current bar opens). Using bar `t`'s regime to gate bar `t`'s entry means the regime filter evaluates on the bar it controls, not on the prior bar. This is a subtle but meaningful lookahead for intraday bars where regime may flip within the candle's open-to-close move.

**Risk G — S/R zones are computed from the full rolling window including the current bar.** `SupportResistanceEngine.compute()` uses the full available history. If the current bar's high establishes a new resistance zone and the strategy immediately uses that zone as a target — computed at bar `t` from bar `t`'s price — the entry condition and the target are derived from the same bar. This is a same-bar causality issue: the target was not knowable before the bar closed.

**Risk H — Opening range uses the first N minutes of the session.** `compute_opening_range()` computes the high and low of the first `N` minutes. For a strategy running on 5m bars, the opening range is not fully known until minute `N`. A strategy entry at minute 3 of a 5-minute opening range would use the opening range's high/low from minutes 1–5, but minute 5 has not yet occurred. If the batch precomputation includes the future opening range minutes in the current bar's features, this is lookahead.

---

## 5. What Is Missing for Full Determinism?

Full determinism requires: the same input data + same program config → always produces the same signals, the same trades, and the same metrics, regardless of when the run is executed or whether it runs in batch or live mode.

**Missing D1 — Immutable versioning for StrategyControls and ExecutionStyle entities.** These entities are mutable. Editing a StrategyControls entity changes the config for all historical backtests that reference it. Without version snapshots frozen at backtest-launch time, two runs of the same BacktestRun ID on different dates may produce different results.

**Missing D2 — Configuration snapshot attached to each BacktestRun.** `BacktestRun` stores `program_id` (or `strategy_version_id` etc.) but does not store the resolved, frozen configuration that was actually passed to the engine at launch time. If any referenced entity changes after the run, the run's config is effectively different from what was tested. A `run_config_snapshot` JSON field on `BacktestRun` would close this gap.

**Missing D3 — Deterministic random seed for Monte Carlo.** `_compute_monte_carlo()` in `backtest_service.py` generates random paths. Without a stored seed, two requests for the same run's Monte Carlo results will produce different band values. The stored `monte_carlo` JSON in `RunMetrics` captures a snapshot, but if the snapshot is ever regenerated, it produces different values. The seed used for the run should be stored in `RunMetrics`.

**Missing D4 — Stable floating-point for EWM across Python/Pandas versions.** EWM computation results are sensitive to floating-point arithmetic. Different Pandas versions may produce slightly different EWM values due to changes in the `ewm()` implementation. The Pandas version used during a run is not stored in `BacktestRun`. Over time (Pandas upgrades), identical runs may produce different metrics by rounding error.

**Missing D5 — Bar timestamp normalization standard.** There is no enforced normalization of bar timestamps to a canonical timezone and precision before they enter the engine. yfinance may return UTC timestamps; Alpaca may return UTC with microsecond precision; a data correction replay may have East Coast timestamps. The `BacktestEngine` does not normalize before processing. `pd.to_datetime()` handles most cases, but if a symbol has bars from yfinance and another from Alpaca in the same multi-symbol run, timezone mixing in the aligned DataFrame will cause incorrect indicator computations.

**Missing D6 — Bar revision handling.** Data providers periodically issue revised bars (especially for the most recent bar as it forms). There is no concept of a "revised bar" in the cache or in the backtest data path. A live run that experiences a bar revision mid-session will process the original bar and then the revised bar as two separate bar events — computing indicators and potentially triggering entries or exits on the original bar's (incorrect) data.

**Missing D7 — Deterministic order of condition evaluation for `n_of_m` groups.** `n_of_m` condition groups evaluate `n` out of `m` sub-conditions. If conditions are stored as a list, their order in the list determines which `n` are selected when `n < m` conditions are true. But `n_of_m` semantics require only that at least `n` are true — the identity of the true conditions should not matter. However, if the list order is not preserved through JSON serialization/deserialization (e.g., if a dict-keyed structure is used anywhere in the condition tree), the evaluation order may change between runs.

**Missing D8 — `FeatureCache` persistence across restarts.** When the process restarts, all computed features are lost. Cold-start re-warms from the data provider. If the provider returns slightly different data on the second fetch (e.g., a revised close price, an added bar, or a missing bar due to API pagination), the recomputed features will differ from the pre-restart features. A persistent feature cache (disk-backed or database-backed) with a content-addressed invalidation scheme would close this gap.

---

## HARD FIXES REQUIRED

These are critical defects that directly affect trade correctness, audit integrity, or live system stability. Each represents a condition where the system produces wrong results silently.

**H1 — Fix EWM mismatch between batch and live computation.**
`IndicatorCache.update()` must carry EWM state forward rather than reseeding on every call. Options: (a) store Pandas EWM `com`/`alpha` decay state between updates and apply it incrementally; (b) use a purpose-built online EWM formula `y_t = alpha * x_t + (1-alpha) * y_{t-1}` that maintains state between bar updates; (c) extend `WINDOW_SIZE` to `max(warmup_bars) * 5` to minimize convergence error. Option (b) is the correct fix. Any live signal derived from EMA, ATR (Wilder), or RSI is currently systematically offset from its backtest value.

**H2 — Fix `WINDOW_SIZE = 250` vs warmup requirement mismatch.**
`WINDOW_SIZE` must be at least as large as the maximum warmup bars across all registered feature plans. Either: (a) make `WINDOW_SIZE` dynamic, computed as `max(warmup_bars) + buffer` when programs are registered; or (b) validate at program registration time that no feature's warmup requirement exceeds `WINDOW_SIZE`, and reject registration with a clear error. Currently, a daily SMA(200) silently enters a permanent not-warm state and never computes.

**H3 — Fix swing high/low and fractals lookahead bias.**
`detect_swing_points()` and `fractals()` assign confirmed values to bar `i` but use information from bars `i+1..i+lookback`. In the backtest bar loop, this is only valid if bar `i`'s signal is not evaluated until bar `i+lookback`. Currently the bar loop processes bar `i` and uses the precomputed swing high at `i` — which was confirmed using future data. Either: (a) shift the swing/fractal columns forward by `lookback` bars so that the confirmed value is visible only at bar `i+lookback`; or (b) add a `_confirmed_at` offset to the feature spec and apply it in `_resolve_value()`. This is a lookahead bias that inflates backtest performance.

**H4 — Fix multi-TF indicator absence in live mode.**
`CerebroEngine`/`IndicatorCache` must support multi-TF feature plans. The `IndicatorCache` must hold separate frames per timeframe per symbol and aggregate them correctly. When a 5m strategy requires a 1h indicator, the most recent completed 1h bar's indicator value must be available to the 5m condition evaluator. Currently, multi-TF indicators in live mode silently evaluate to `False`, causing live behavior to diverge completely from backtest behavior for any strategy using cross-TF conditions.

**H5 — Fix `BarAggregator` half-day handling.**
`BarAggregator` uses a fixed bar count of 390 for daily completion. On half-days (early close at 13:00 ET = 210 minutes), the daily bar never completes. `MarketCalendarService` is already available as a singleton — `BarAggregator` must consult it to set the correct expected bar count per session day. On a half-day, it should emit the daily bar after 210 minutes, not wait for 390.

**H6 — Fix `SessionWindowConfig.can_enter()` wall-clock vs bar-timestamp divergence.**
In live mode, `can_enter()` must use the bar's timestamp, not `datetime.now()`. The live execution path must pass the bar timestamp through the session window check rather than using system time. Using `datetime.now()` introduces a race condition at session boundaries that does not exist in backtesting, producing divergent entry decisions.

**H7 — Fix hardcoded calendar expiry.**
`MarketCalendarService` must either: (a) load holidays from a configuration file or database that can be updated without a code deploy; or (b) integrate a real-time market calendar API (e.g., NYSE's official calendar via Alpaca's calendar endpoint). The hardcoded 2024–2026 data will cause all session-aware features to silently corrupt after December 31, 2026. A warning should be emitted at startup if the current date is within 60 days of the last configured calendar entry.

**H8 — Fix float vs int param normalization in `make_feature_key()`.**
`normalize_feature_params()` must coerce all numeric param values to a canonical type before JSON serialization. The simplest fix: `if isinstance(v, float) and v.is_integer(): v = int(v)`. This prevents `14` and `14.0` from generating different keys and causing redundant recomputation and cache misses.

**H9 — Fix `_frames_by_runtime_identity` memory leak.**
`IndicatorCache._frames_by_runtime_identity` must have a bounded size. Implement an LRU eviction policy (e.g., `cachetools.LRUCache` with a max size of 500 entries). Orphaned identity frames from unregistered programs currently accumulate indefinitely.

**H10 — Fix `StrategyControls` and `ExecutionStyle` mutable-entity audit corruption.**
Introduce immutable versioning for both entities, matching the `StrategyVersion` pattern. Each edit creates a new version; the parent entity gains a `current_version_id` pointer. `BacktestRun` must store the `strategy_controls_version_id` and `execution_style_version_id` (not just the parent entity IDs) that were resolved at launch time. This is a schema change but is required for any meaningful reproducibility of results.

---

## NICE TO HAVE IMPROVEMENTS

These improve robustness, debuggability, and operational safety but do not represent silent correctness failures.

**N1 — Persist warm feature cache to disk.**
Store `IndicatorFrame` data to a local SQLite or parquet store, keyed by `(symbol, timeframe, runtime_identity_key, as_of_date)`. On restart, reload the frame and verify the identity key still matches the registered programs. This eliminates cold-start API calls on process restarts and ensures consistent indicator values across restarts.

**N2 — Add a batch/live parity test.**
Create an integration test that: (a) runs a backtest over a 60-bar window for a given symbol+strategy; (b) feeds the same 60 bars through `IndicatorCache.warm_up()` + `update()` one bar at a time; (c) compares the final indicator values between batch and live modes. This test should be part of CI. It would immediately detect EWM divergence (H1) and any future regressions in the incremental path.

**N3 — Add a `TimeframeEnum` and enforce it throughout.**
Replace bare string timeframe values (`"1m"`, `"1h"`, `"1d"`) with a `Literal` or `Enum` type. Enforce normalization at all entry points (`FeatureSpec.__post_init__`, `BarAggregator.ingest()`, `IndicatorCache.warm_up()`). This eliminates `"1h"` vs `"60m"` key divergence.

**N4 — Add param canonicalization / default injection to `normalize_feature_params()`.**
For each known indicator kind, define a `INDICATOR_DEFAULTS` dict (e.g., `{"macd": {"signal": 9}}`). `normalize_feature_params()` should merge in defaults before serializing. This prevents two users specifying the same MACD with and without the default signal period from generating different keys.

**N5 — Add a feature key deserializer.**
`feature_spec_from_key(key: str) -> FeatureSpec` — the reverse of `make_feature_key()`. Used in logging, alerting, and cache debugging. Without this, cache misses are reported as opaque JSON strings.

**N6 — Add `FeaturePlan` diffing.**
`diff_feature_plans(old: FeaturePlan, new: FeaturePlan) -> FeaturePlanDiff` — returns added specs, removed specs, changed warmup requirements. Used by `CerebroEngine` when a program is updated: if only one new feature is added, only that feature needs to be computed from scratch; existing features can be served from the existing cache.

**N7 — Emit a structured warning when `is_warm` is False at evaluation time.**
Currently, if an `IndicatorFrame` is not warm and a strategy tries to evaluate a condition, the condition receives NaN-valued feature columns. Condition evaluation silently returns False. Add an explicit warning log: `logger.warning("Feature frame not warm for %s/%s — skipping condition evaluation", symbol, tf)`. Include the current `bar_count` and required `warmup_bars` in the warning.

**N8 — Add a Monte Carlo seed to `RunMetrics`.**
Store the random seed used for Monte Carlo path generation in the `RunMetrics.monte_carlo` JSON payload. When Monte Carlo results are displayed, show the seed so they are exactly reproducible.

**N9 — Validate multi-TF data availability before backtest launch.**
In `backtest_service.launch_backtest()`, before calling `BacktestEngine.__init__()`, verify that `_extra_tf_data` contains all timeframes required by the `FeaturePlan`. If a required TF is missing, raise a descriptive error: `MissingTimeframeDataError("Strategy requires 1h ATR but no 1h data was fetched")`. Do not silently run with missing TFs.

**N10 — Add provenance capture to `FeaturePlan`.**
`FeaturePlan` should include a `data_provenance: dict[str, FrameProvenance]` field mapping each (symbol, tf) to the `FrameProvenance` (provider, fetch time, bar count) used to compute features. This makes the plan self-contained and auditable — a plan and its provenance together fully describe how features were computed.

**N11 — Add an explicit causality annotation to indicator definitions.**
Each indicator in `technical.py` should carry a `causal: bool` annotation and, where applicable, a `lookahead_bars: int` annotation. This allows `build_feature_plan_preview()` to warn users when their strategy config includes a non-causal indicator. It also creates a machine-checkable invariant that the test suite can enforce.

**N12 — Handle timezone normalization at the data ingress boundary.**
Add a `normalize_bar_timestamps(df: pd.DataFrame, target_tz: str = "UTC") -> pd.DataFrame` function called at every data ingestion point (yfinance fetch, Alpaca fetch, bar aggregation). This eliminates mixed-timezone DataFrames from entering the indicator computation path.

**N13 — Add CerebroRegistry state recovery on restart.**
On startup, `CerebroEngine.bootstrap()` should query `deployment_service.get_active_deployments()` and re-register all active programs. This closes the gap where a process restart leaves active deployments unregistered in the in-memory registry.

**N14 — Implement incremental S/R zone update.**
Currently, S/R zones are recomputed from scratch on every bar over the full rolling window. This is O(N) per bar where N = WINDOW_SIZE. For live deployments with many symbols, this is a meaningful CPU cost. Implement an incremental update that only recomputes zones affected by the most recent bar (new swing point, new pivot, new consolidation zone) and updates the zone set partially.

**N15 — Document and test `source` field semantics on `FeatureSpec`.**
Either: (a) implement routing in `_compute_indicators()` so that `source="high"` for an EMA computes EMA over the high price series; or (b) remove the `source` field from `FeatureSpec` and document that all indicators compute over close price by default. The current state (field present, ignored in computation, included in key) is the worst of all worlds: it inflates key space, causes phantom cache misses, and provides no actual functionality.
