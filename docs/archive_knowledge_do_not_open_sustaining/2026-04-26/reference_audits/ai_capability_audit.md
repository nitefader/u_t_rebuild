# AI Leverage & Capability Audit — Ultimate Trading Software 2026
> Audit date: 2026-04-23 · Auditor: senior AI systems architect, applied AI for trading platforms

---

## 1. CURRENT AI CAPABILITY INVENTORY

The platform has two distinct AI subsystems that share a name but have nothing in common architecturally. They must be understood separately to be evaluated fairly.

---

### Subsystem A: LLM Features (5 active, via `ai_service.py`)

Single infrastructure layer: `ai_service.py` queries the DB for a `DataService` record with `is_default_ai=True`, then dispatches to Groq or Gemini via HTTP. Temperature is hardcoded at `0.2` for all calls. JSON mode is enforced at the API level for both providers. 30-second timeout.

There are exactly five LLM-powered features in the platform today.

---

#### Feature A1 — Generate Entry/Exit/Stop Conditions

**Location:** `POST /api/v1/strategies/generate-conditions`

**How it is triggered:** Not directly exposed in the sidebar navigation. Reached from the Strategies list page via a "Generate Strategy" modal that accepts a free-text prompt.

**Inputs to the LLM:**
- System prompt: `_CONDITION_SYSTEM_PROMPT` (54 lines) — defines ValueSpec schema, Condition schema, valid operators, full indicator list (48 indicators), valid logic values, output format rules
- User prompt: `"Generate {condition_type} conditions for this trading signal:\n\n{user_text}"` — no other context is injected. No current strategy state, no symbol, no timeframe, no regime.

**Outputs:**
- `{conditions: list[Condition], logic: str}`
- Validated: checks `conditions` is a list — that is the only structural check. Individual condition objects are not validated against the indicator allowlist. The `op` field is not validated. The `left`/`right` ValueSpec structure is not validated.

**Reliability assessment: Superficial.**

The prompt is well-structured and the indicator list is comprehensive. However:
1. No context is injected (no symbol, timeframe, or regime). The LLM generates conditions in a vacuum. An EMA crossover generated for a "trend following equity strategy" may be perfectly valid for a 1h chart but produce no trades on a 1m scalping strategy.
2. No downstream semantic validation. A generated condition like `{"left": {"indicator": "rsi_14"}, "op": "crosses_above", "right": {"indicator": "ema_21"}}` is structurally valid but semantically nonsensical — RSI is dimensionless (0–100) and EMA is price-scale. This will parse without error and reach the backtest engine where it will silently never fire or fire randomly.
3. Generated conditions reach the ConditionBuilder pre-populated but with no explanation of what each condition does or why it was chosen. The user has no signal that a condition is dimensionally mismatched.

---

#### Feature A2 — Generate Strategy Brief

**Location:** `POST /api/v1/strategies/generate-brief`

**How it is triggered:** Same modal entry point as A1. Takes the user's natural language strategy description and returns a full brief: name, hypothesis, description, entry conditions, short conditions, assumptions, warnings.

**Inputs to the LLM:**
- System prompt: `_BRIEF_SYSTEM_PROMPT` (62 lines) — enforces flat `type:single` only (no nesting), includes a WRONG/RIGHT example, restricts to a slightly smaller indicator list (no `hull_ma_50`, `rsi_8`, `dc_mid`, etc. compared to A1's list), valid operators subset (no `between`, `in`, `n_bars_back` cross-reference)
- User prompt: `"Generate a strategy brief for this idea:\n\n{user_text}"`

**Post-processing:** `_flatten_to_singles()` recursively extracts singles from any nested groups — this is a graceful degradation mechanism for when the LLM wraps conditions in an `all_of` group despite the instruction not to.

**Outputs:**
- Full brief: `{name, hypothesis, description, conditions, logic, short_conditions, short_logic, assumptions, warnings, partial_success}`
- `partial_success: true` returned (not an error) when conditions list is empty
- Frontend auto-populates form fields with name and hypothesis

**Reliability assessment: Moderate — best-designed of the five features.**

The fallback path (empty conditions + `partial_success: true`) prevents hard failures. The WRONG/RIGHT example in the prompt is a good practice. However:
1. The indicator list in `_BRIEF_SYSTEM_PROMPT` is different from `_CONDITION_SYSTEM_PROMPT` — `_BRIEF_SYSTEM_PROMPT` omits `hull_ma_50`, `rsi_8`, `rsi_3`, `adx`, `stoch_k`, `stoch_d`, `zscore_10`, `dc_mid`, `sar_trend`, `plus_di`, `minus_di`, `ibs`, `bt_snipe`, `strat_num`, `donchian_high`, `donchian_low`, `pp`, `r1-r3`, `s1-s3`, `open_gap_pct`. These are valid indicators in the engine but unavailable to the brief generator. A user describing an ADX-based trend strategy will receive a brief that silently ignores ADX or hallucinates a substitute.
2. No hypothesis validation. The LLM writes a hypothesis in natural language but there is no check that the conditions it generates actually test that hypothesis. A user can get a brief with hypothesis "buy when RSI is oversold in a trending market" and conditions that never check ADX, trend direction, or any momentum context.
3. The assumptions and warnings arrays are LLM-generated prose with no structured schema. They cannot be checked programmatically or acted upon by the system.

---

#### Feature A3 — Analyze Risk Profile

**Location:** `POST /api/v1/risk-profiles/analyze`

**How it is triggered:** "Analyze Profile" button (Sparkles icon) on the Risk Profiles page.

**Inputs to the LLM:**
- 11 numeric parameters: max_positions (long/short), portfolio_heat (long/short), correlated_exposure (long/short), max_position_size (long/short), daily_loss_limit, max_drawdown_lockout, max_leverage
- Formatted as human-readable text: `"Long: max 5 positions, 6.0% heat, 20.0% correlated exposure, 5.0% max position size.\n..."`

**No context about the strategy, timeframe, or trading style is injected.** The LLM analyzes the risk parameters in isolation, with no knowledge of whether this profile is for a mean-reversion intraday scalp or a multi-week swing strategy.

**Outputs:**
- `{health: 'good'|'caution'|'risky', summary, suggested_name (≤55 chars), suggested_description, insights: [{label, text, tone}], suggestions: [str]}`
- Frontend auto-applies name and description. Insight tones drive color-coded UI cards.

**Reliability assessment: Moderate for name/description; Superficial for health assessment.**

The name/description generation adds real value — it produces human-readable labels from numeric configs. The health assessment is problematic:
1. A `max_position_size=20%` with `max_leverage=4.0` might be appropriate for a low-frequency swing strategy but dangerous for a high-churn intraday strategy. The LLM has no basis to distinguish these because no strategy context is provided.
2. The `health` output directly drives a colored badge (emerald/amber/red) in the UI. A "good" badge gives a false sense of safety validation when the assessment was made on isolated numbers.
3. There are no hardcoded constraints checked against the LLM output. If the LLM rates a `max_drawdown_lockout=50%` as "good" (perhaps because the other parameters look conservative), the system accepts this — even though a 50% drawdown lockout means an account can lose half its value before triggering.

---

#### Feature A4 — Summarize Strategy Controls

**Location:** `POST /api/v1/strategy-controls/summarize`

**How it is triggered:** "AI Summarize" button on the Strategy Controls page.

**Inputs to the LLM:** Full controls configuration formatted as text: timeframe, duration_mode, session windows, force-flat time, session caps, cooldown rules count, earnings blackout flag, regime filter, PDT config, gap risk config.

**No strategy is provided.** The LLM assesses controls without knowing what strategy they govern.

**Outputs:**
- `{summary, suggested_name (45–65 chars), suggested_description, compatibility: {day_trading: bool, swing_trading: bool, position_trading: bool}, warnings: [str]}`
- Frontend auto-applies name/description, shows compatibility badges

**Reliability assessment: Good for naming; Superficial for compatibility.**

The compatibility assessment (day_trading/swing_trading/position_trading booleans) is useful UX sugar. However:
1. The compatibility flags are LLM-generated and not validated against the actual `duration_mode` field in the controls — which already encodes day/swing/position trading. A controls object with `duration_mode="day"` and `allow_overnight=True` could receive `compatibility.swing_trading=false` from the LLM even though the config allows overnight holds.
2. Warnings are prose strings with no structured action path.
3. Summary length constraint (2–3 sentences) is enforced by the prompt but not validated in code. A longer summary is accepted silently.

---

#### Feature A5 — Analyze Execution Style

**Location:** `POST /api/v1/execution-styles/analyze`

**How it is triggered:** "Analyze Style" button on the Execution Styles page.

**Inputs to the LLM:** Full execution style config formatted as text: entry order type, TIF, limit offset method/value, cancel-after-bars, bracket mode, stop order type, take-profit type, trailing stop config, scale-out levels, ATR source/length/timeframe, breakeven trigger, fill model, slippage/commission assumptions.

**Outputs:**
- `{suggested_name (35–55 chars), suggested_description, health: 'clean'|'caution'|'risky', insights: [str], suggestions: [str], warnings: [str]}`

**Reliability assessment: Superficial for health; useful for naming.**

1. The LLM assesses execution style health without knowing whether this style will be used with a market-order entry strategy or a limit-order pullback strategy. A trailing stop with `atr_multiple=3.0` might be appropriate for a wide-swinging swing strategy but ruinously wide for a 1m scalp.
2. `insights` and `suggestions` are unstructured strings with no action paths. A suggestion like "consider tightening the stop" has nowhere to go in the UI.
3. The `health` badge is displayed alongside the form — a "caution" badge provides no guidance on which specific field to change.

---

### Subsystem B: sklearn ML Features (6 endpoints, `/ml/*`)

These are traditional machine learning features using `RandomForestClassifier` from scikit-learn. They are not LLM-based and not conversational.

**Location:** `backend/app/api/routes/ml.py`

**What they do:**
- `POST /ml/prepare-dataset` — engineers features from OHLCV (returns, rolling vol, SMA ratios, RSI divergence, momentum ROC, overnight gap, Bollinger %B) and labels with forward return
- `POST /ml/train-model` — trains a 200-tree RandomForest with 5-fold TimeSeriesSplit CV, persists with joblib, returns accuracy, precision, recall, F1, ROC-AUC, top-15 feature importance
- `GET /ml/models` — lists persisted models by `.meta.json` scan
- `POST /ml/models/{model_id}/signals` — generates BUY/SELL/HOLD signals for last N bars with probability and regime label (low_vol/normal/high_vol using 21/63-bar realized vol comparison)
- `DELETE /ml/models/{model_id}` — removes model files
- `POST /ml/compare` — side-by-side metrics for two models with signal agreement rate

**Critical gap: No UI for the ML pipeline.** There is no frontend page that exposes these endpoints. A user cannot train a model, view trained models, generate signals, or use ML signals as strategy conditions through any UI in the platform. The ML subsystem is entirely backend-only.

**The ML signals are not connected to the strategy engine.** There is no mechanism to use an ML model's BUY/SELL signal as a condition in a StrategyConfig, as a filter in a StrategyGovernor, or as an input to a backtest. The signals endpoint generates signals in isolation — they cannot be acted upon by the platform.

---

### Subsystem C: Heuristic Features Mislabeled as AI

These features exist but involve no machine learning or LLM. They are rule-based algorithms:

**Promote Advice** (`POST /ml/promote-advice`): A checklist verification function. Checks whether specific string keys are present in a deployment's metadata. Returns `recommend=True` if all keys are present and the deployment is running/paused. The LLM is not called. The endpoint is in the `/ml` route prefix, which implies ML capability it does not have.

**Backtest Recommendations** (`GET /backtests/{run_id}/recommendations`): Five hardcoded threshold checks. `drawdown > 20%` → warning. `trades < 30` → warning. `IS/OOS Sharpe degradation > 50%` → danger. Avg hold vs duration_mode mismatch → warning. Best regime win rate > 60% → info. These are rules, not models.

**Suggest Risk Profile** (`POST /backtests/{run_id}/suggest-risk-profile`): Algorithmic derivation from backtest trade statistics. P95 position sizes, max concurrent positions, median portfolio heat, worst-day drawdown. All arithmetic. No model.

**Provider Recommendation** (`POST /backtests/provider-recommendation`): Rule-based routing by timeframe, date range, symbol count, credential availability. No model.

---

### Summary: What Is Actually AI

| Feature | Type | Connected to Engine | Validated | Contextual |
|---|---|---|---|---|
| Generate Conditions | LLM | Via manual user review | Structural only | No (no symbol/TF/regime) |
| Generate Brief | LLM | Via manual user review | Structural + flatten | No |
| Analyze Risk Profile | LLM | Name/desc auto-applied | None | No (no strategy context) |
| Summarize Controls | LLM | Name/desc auto-applied | None | No (no strategy context) |
| Analyze Execution Style | LLM | Name/desc auto-applied | None | No (no strategy context) |
| ML Train/Signals | sklearn RF | Not connected | Full CV metrics | Per-symbol, not per-program |
| Promote Advice | Heuristic | Checklist gate | N/A | Yes (deployment data) |
| Recommendations | Heuristic | Display only | N/A | Yes (run metrics) |
| Suggest Risk Profile | Algorithmic | Creates entity | N/A | Yes (trade statistics) |
| Provider Recommendation | Heuristic | Auto-applies | N/A | Yes (TF/date/credentials) |

---

## 2. HIGH-LEVERAGE AI OPPORTUNITIES

### Opportunity O1 — Trade Decision Trace ("Why did this trade fire?")

**Problem:** When a strategy fires an entry in Sim Lab or in a live deployment, the user sees a trade marker on the chart and a row in the trade log. They cannot see which specific conditions were true, what the indicator values were at that bar, or why the conditions evaluated the way they did.

**Current gap:** `EvalContext` captures all the data needed for a decision trace (bar, df, indicators, regime, FVGs), but nothing serializes this trace to a human-readable explanation. Trade records store exit reason but not entry justification.

**AI solution:** At each trade entry, serialize the active conditions, their left/right values, operator, and result (true/false). Pass this to an LLM with context: "Explain in plain English why this trade was entered, given these condition evaluations: [structured data]." The explanation is attached to the trade record and displayed in the Trade Journal as a collapsible "Why this trade?" section.

**No LLM is required for the condition evaluation trace** — the trace can be rendered as a structured display without AI. The LLM adds value by translating the structured trace into a plain-English narrative: "The strategy entered long because RSI(14) crossed above 30 while price was above the 21 EMA, indicating momentum recovery in an uptrending market."

**Expected impact: HIGH.** This is the single most-requested feature in algo trading platforms — "explain this trade." It directly reduces the learning curve and increases user confidence in the strategy engine.

---

### Opportunity O2 — Backtest Result Interpretation Narrative

**Problem:** Run Details shows 12+ metrics, a trade journal, equity curve, walk-forward folds, CPCV results, regime analysis, and Monte Carlo bands. A new or intermediate user cannot synthesize these into an actionable verdict: "Is this strategy worth deploying?"

**Current gap:** The "Strategy Diagnostics" feature (`GET /backtests/{run_id}/recommendations`) exists but is hardcoded rule-checks, not an integrated narrative.

**AI solution:** After a backtest completes, pass the full run metrics (return, Sharpe, Sortino, max DD, win rate, SQN, walk-forward OOS summary, CPCV pass/fail, regime breakdown, cost sensitivity curve) to an LLM with a structured prompt: "You are a quantitative risk analyst. Given these backtest results, provide: (1) a one-paragraph verdict on whether this strategy is ready for paper deployment, (2) the three biggest risks, (3) two specific improvements to test." The narrative appears in a new "AI Verdict" section on the Overview tab of Run Details.

**This is not a replacement for the metrics.** The metrics remain. The narrative is an interpretation layer for users who are not yet expert in reading Sharpe ratios and CPCV pass rates.

**Expected impact: HIGH.** Directly accelerates the validate → deploy decision. Reduces the friction that causes users to over-backtest without deploying.

---

### Opportunity O3 — Strategy Condition Semantic Validator

**Problem:** The current `POST /api/v1/strategies/validate` endpoint checks structural validity (valid operators, valid field names) but not semantic validity. A condition like `RSI(14) crosses_above EMA(21)` is structurally valid but dimensionally nonsensical.

**Current gap:** No semantic validation layer. The backtest engine silently evaluates nonsensical conditions and returns confusing results.

**AI solution:** After condition generation (A1, A2) and on manual save, pass the condition tree to an LLM with this context: "Review these trading conditions for semantic errors. Flag: (1) dimension mismatches (e.g., comparing a 0–100 indicator to a price), (2) logical contradictions (e.g., RSI < 30 AND RSI > 70), (3) conditions that will statistically never fire (e.g., volume == 100000 exactly), (4) missing context (e.g., a crossover condition with no trend filter)." Return structured findings: `{severity: 'error'|'warning'|'info', condition_index, explanation}`.

**This is validation, not generation.** It does not change conditions — it annotates them.

**Expected impact: HIGH.** Eliminates the silent-failure class of bugs where users run backtests on meaningless conditions and get zero trades with no explanation.

---

### Opportunity O4 — Optimization Run Pruning

**Problem:** Grid search in Optim. Lab runs up to 500 backtests (`max_combinations=500`). Many of these runs are redundant or predictably poor before they execute.

**Current gap:** `param_optimizer.py` runs all combinations sequentially with `ThreadPoolExecutor`. No pruning, no early stopping, no intelligent ordering.

**AI solution (two-stage):**
1. **Pre-run pruning:** Before launching the optimization batch, pass the parameter grid to an LLM with context about the strategy type and historical results (if any). The LLM ranks parameter combinations by estimated promise and eliminates extreme combinations (e.g., a stop multiplier of 0.1 ATR for a swing strategy is almost certainly too tight). This reduces the combination count before execution.
2. **Sequential Bayesian guidance:** After the first 10–20 runs complete, pass their results to an LLM/regression model. Identify which parameter regions look promising. Bias remaining runs toward the high-promise region. This is a lightweight Bayesian optimization loop without requiring a full BO library.

**Expected impact: MEDIUM.** Not all users run large optimization batches. But for those who do, this reduces compute cost and time by 30–60% while improving result quality.

---

### Opportunity O5 — Live Anomaly Detection

**Problem:** When a live deployment is running, there is no automated detection of unusual behavior: unexpected trade frequency, unusual fill prices, signal patterns inconsistent with backtest behavior, position sizes that diverge from the risk profile.

**Current gap:** Live Monitor shows current positions and orders but provides no baseline comparison. There is no alert when "this deployment is trading more than expected" or "fills are consistently worse than the backtest assumed."

**AI solution:**
1. **Baseline construction:** At deployment launch, compute expected ranges from the backtest run: expected trades/day (mean ± 2σ), expected position sizes, expected fill slippage (from fill_model + slippage_bps_assumption), expected drawdown range.
2. **Runtime comparison:** Every N minutes, compare live metrics to baseline. If any metric is >2σ outside expected: trigger an alert with an LLM-generated explanation: "Warning: This deployment has entered 3 positions in the last 30 minutes. Based on your backtest, the expected rate is 0.8 positions/day. Possible causes: (1) the session window is not filtering as expected, (2) market conditions are unusually volatile."

**Expected impact: HIGH.** This is the category of feature that prevents the silent runaway scenario — a strategy trading 10× its expected rate without the user noticing until significant losses have occurred.

---

### Opportunity O6 — Governor Rejection Explainer

**Problem:** When the Account Governor rejects a trade (collision, risk_blocked, daily_loss_lockout), the GovernorEvent log records the event type and a brief reason. Users who are new to the platform don't understand what "collision_suppressed" means or what to do about it.

**Current gap:** Governor events are stored with structured fields but displayed as raw event type strings with terse reasons.

**AI solution:** For each governor event, generate a plain-English explanation on demand: "A 'collision_suppressed' event means that two of your programs tried to open positions in the same symbol in opposing directions simultaneously. Program A wanted to go long AAPL while Program B wanted to go short AAPL. Because Alpaca does not allow conflicting long/short positions on the same account, one of these signals was suppressed. To fix this: (1) use symbol deny lists to prevent overlap, or (2) run these programs on separate accounts."

**Expected impact: MEDIUM.** Particularly valuable for new users who don't understand governor semantics. Reduces support burden and accelerates learning.

---

### Opportunity O7 — Portfolio Composition Advisor

**Problem:** The portfolio snapshot on the Governor page shows symbol collision warnings and overlap matrix, but does not provide actionable recommendations for how to resolve them.

**Current gap:** The `portfolioSnapshot` endpoint returns `collision_risk_symbols` and program overlap data, but this is displayed as raw data with no interpretation.

**AI solution:** Pass the full portfolio snapshot (programs, their watchlists, their correlations, their risk profiles, active deployment count) to an LLM. Return a structured recommendation: "Your portfolio has 3 programs trading SPY, QQQ, and IWM simultaneously. These are highly correlated (historical correlation > 0.85). Your correlated_exposure limit of 20% is likely being exceeded. Recommended action: (1) assign SPY to Program A only, (2) use QQQ for Program B, (3) give Program C a non-correlated asset universe."

**Expected impact: MEDIUM.** Addresses a real problem (correlated multi-program portfolios) that the platform's architecture addresses at the data level but not at the guidance level.

---

### Opportunity O8 — Drawdown Narrative

**Problem:** When a strategy enters a drawdown period, the equity curve shows the decline but provides no context. Users panic-stop strategies that are in normal drawdown ranges.

**Current gap:** Run Details shows the equity curve and max drawdown metric but no comparison to expected drawdown from Monte Carlo or walk-forward results.

**AI solution:** When live drawdown exceeds a threshold (e.g., 50% of max_drawdown_lockout), generate a contextual alert: "Your deployment is currently in a 7.3% drawdown. Your backtest showed a maximum drawdown of 12.4% over the same date range, and your Monte Carlo 95th percentile drawdown was 14.2%. Current drawdown is within normal historical parameters. The last three comparable drawdown events in backtest resolved within 8–12 trading days."

**Expected impact: HIGH.** Prevents the most common behavioral mistake in algorithmic trading — stopping a working strategy during normal drawdown.

---

## 3. FEATURE ENGINE + AI ALIGNMENT

### Does AI Use Canonical Feature Vocabulary?

**Partially.** The two LLM condition-generation prompts (`_CONDITION_SYSTEM_PROMPT` and `_BRIEF_SYSTEM_PROMPT`) define explicit indicator allowlists. This is the correct approach. However, the lists differ between the two prompts.

**Inconsistency between prompt indicator lists:**

| Indicator | `_CONDITION_SYSTEM_PROMPT` | `_BRIEF_SYSTEM_PROMPT` |
|---|---|---|
| `hull_ma_50` | ✓ | ✗ |
| `rsi_8`, `rsi_3`, `rsi_2` | ✓ | `rsi_2` only |
| `adx`, `plus_di`, `minus_di` | ✓ | ✗ |
| `stoch_k`, `stoch_d` | ✓ | ✗ |
| `zscore_10`, `zscore_20` | `zscore_10` only | `zscore_20` only |
| `dc_mid`, `donchian_high`, `donchian_low` | ✓ | `dc_upper`, `dc_lower` only |
| `sar_trend` | ✓ | ✗ |
| `ibs` | ✓ | ✗ |
| `bt_snipe` | ✓ | ✓ |
| `strat_num` | ✓ | ✗ |
| `pp`, `r1`, `r2`, `r3`, `s1`, `s2`, `s3` | ✓ | ✗ |
| `open_gap_pct` | ✓ | ✗ |
| `n_bars_back` construct | ✓ | ✗ |
| `between`, `in` operators | ✓ | ✗ |

The `_BRIEF_SYSTEM_PROMPT` is a restricted subset with no documented reason for the restriction. A user generating a strategy brief who wants ADX-based trend filtering will receive a brief that cannot include ADX. The LLM will either omit it (silently dropping the user's intent) or hallucinate an unsupported substitute.

**The indicator list in both prompts is also partially stale relative to `technical.py`.** The following indicators are computed by the engine but absent from both prompts:
- `hull_ma` (the generic form — only `hull_ma_20`, `hull_ma_50` are listed)
- `keltner_channel` upper/lower/mid (not in either prompt)
- `obv` (On-Balance Volume — not in either prompt)
- `swing_high`, `swing_low` (despite being major features with the lookahead bias documented in the feature engine audit)
- `volume_sma_N` (parameterized form — only `volume_sma_20` implied)

---

### Can AI Generate `FeatureSpec` Correctly?

**No.** The LLM generates indicator references as string names (e.g., `"indicator": "ema_21"`). The platform uses `FeatureSpec(kind="ema", timeframe="5m", source="close", params={"length": 21})` as the canonical identity type. There is no translation layer from the LLM's string-reference format to a canonical `FeatureSpec`.

The translation happens implicitly via `feature_spec_from_ref()` in `catalog.py` which parses string references like `"ema_21"` into `FeatureSpec`. This works for the parameterized patterns defined in `_PARAMETERIZED_REF_PATTERNS`. But if the LLM generates `"ema"` without a period suffix, or `"ema_021"` with a leading zero, the catalog parser will fail and the feature will not be computed.

**The LLM has no awareness of `FeatureSpec.timeframe`.** All generated conditions reference indicators without timeframe qualification. In a multi-timeframe strategy, `ema_21` might mean the 5m EMA(21) or the 1h EMA(21). The generation prompt provides no mechanism to specify which timeframe an indicator should be computed on.

---

### Does AI Respect Timeframe and Causality?

**Timeframe: No.** Neither condition-generation prompt includes timeframe as an input or as a constraint in the output schema. Generated conditions are timeframe-agnostic. This means the same generated conditions will be used regardless of whether the strategy runs on 1m, 1h, or 1d data — with no adjustment for what is appropriate at each timeframe.

**Causality: No explicit awareness, but incidentally safe.** The prompts do not mention causality. However, the indicator list in both prompts excludes swing high/low and fractals (which have the lookahead bias documented in the feature engine audit). This is probably coincidence, not intentional design — the causal problematic indicators happen to not be in the list. If someone added `swing_high` to the prompt's indicator list without understanding the lookahead issue, the LLM would generate conditions using it freely.

The `n_bars_back` construct in `_CONDITION_SYSTEM_PROMPT` — which references indicator values from N bars ago — is causally safe (looking backward), but the prompt does not warn the LLM that referencing `n_bars_back: -1` (the next bar) would be lookahead. The LLM might generate `n_bars_back: -1` thinking it means "one bar ahead," which would be a pure lookahead condition.

---

### Does AI Suggest Unsupported Features?

**Sometimes.** Despite the "Never invent indicators not in the list above" instruction, LLMs occasionally hallucinate indicator names. Testing shows that models may generate:
- `"indicator": "macd_histogram"` instead of `"macd_hist"` (close but wrong key)
- `"indicator": "rsi"` without a period suffix (will fail catalog parsing)
- `"indicator": "sma_100"` which is a valid pattern but not pre-computed unless the user's strategy config requests it
- `"indicator": "ema_21_slope"` (derived feature, not in the engine)

**Validation gap:** The only check on generated conditions is `isinstance(conditions, list)`. There is no per-condition indicator name validation against the actual catalog. A generated condition with an invalid indicator name will be inserted into the strategy config, reach the backtest engine, and cause a KeyError or silent NaN column during `_resolve_value()`.

---

### Drift and Hallucination Risks

**Drift risk 1 — Prompt indicator list out of sync with engine.** As new indicators are added to `technical.py`, the prompt lists must be manually updated. There is no automated sync. Over time the prompt lists will drift further behind the engine's actual capabilities.

**Drift risk 2 — Two diverging prompt lists.** `_CONDITION_SYSTEM_PROMPT` and `_BRIEF_SYSTEM_PROMPT` started as the same list and have already diverged. Every new indicator added to one must be manually added to the other.

**Hallucination risk 1 — Dimension mismatch.** LLMs frequently generate conditions comparing dimensionally incompatible values (RSI vs price, MACD histogram vs percentage). These are structurally valid and pass the `isinstance(conditions, list)` check.

**Hallucination risk 2 — Plausible but incorrect operator use.** `crosses_above` requires two time-series inputs. Using `crosses_above` with a literal number (e.g., `RSI crosses_above 30`) is handled by the engine only if `_resolve_value()` correctly handles a literal as a series. If it does, fine. If it wraps the literal in a scalar that doesn't broadcast over a series, this will silently produce no crossovers.

**Hallucination risk 3 — `n_bars_back` with zero or negative N.** Not validated.

---

## 4. SIM LAB + AI OPPORTUNITY

### Current State

Sim Lab has zero AI integration. It runs the BacktestEngine bar-by-bar via WebSocket and displays price data, indicators, equity curve, metrics, and trade log. The user watches this output and must interpret it entirely on their own.

### Where AI Adds Value

**S1 — Per-trade explanation in real time.**
As each trade fires during simulation playback, display a sidebar annotation: "Entered long at 10:32 — RSI(14) crossed above 30 while price was above EMA(21). ATR(14) was at $1.24, placing stop at $48.76 (2× ATR). Expected R = 2.1 based on target configuration." This is generated once per trade as a structured trace and formatted by an LLM into a readable sentence. No continuous LLM calls — one call per trade event, triggered by the WebSocket `trade_entry` event.

**S2 — Misconfiguration detection.**
After simulation completes (or during playback), analyze the trade pattern for obvious misconfiguration signs:
- Zero trades → analyze why: session window too restrictive? Indicator not computing (warmup too short for the date range)? All conditions requiring a specific regime that never occurred in the selected period?
- Too many trades → check cooldown, session caps, duplicate entry conditions
- All trades stopped out → check stop distance relative to ATR
- All trades profitable but unrealistically short hold time → check force-flat or exit conditions triggering prematurely

Currently the "no trades" banner shows three generic fix suggestions. AI should diagnose specifically: "The simulation produced 0 trades. The selected date range (Jan 2024 – Mar 2024) was a period of low RSI(14) readings rarely below 30. Your entry condition requires RSI < 30. Try: (1) extending the date range to include high-volatility periods, (2) raising the RSI threshold to 35–40."

**S3 — Expected vs actual indicator behavior explanation.**
When a user enables an indicator in Sim Lab that they haven't used before (e.g., `bt_snipe`), show a tooltip or sidebar explanation generated from the indicator's spec: "BT Snipe measures [description]. It fires a signal when [condition]. Typical thresholds for this indicator are [values]. In this simulation, it fired N times."

**S4 — Post-simulation verdict.**
When simulation ends, generate a one-paragraph verdict before the user decides whether to launch a full backtest: "This simulation shows a strategy that entered 7 trades over 30 days with a 71% win rate and 1.8 average R multiple. The equity curve shows consistent growth with a single 8% drawdown during the mid-period volatility spike. Recommendation: launch a multi-symbol backtest over a longer date range (2+ years) to validate this behavior is not specific to this symbol and period."

---

## 5. BACKTEST + AI OPPORTUNITY

### Current AI Coverage

The "Strategy Diagnostics" section (`GET /backtests/{run_id}/recommendations`) provides five rule-based checks. These are valuable but too narrow.

### Where AI Adds Value

**B1 — Synthesized result narrative (described in O2 above).**

**B2 — Overfitting detection beyond IS/OOS degradation.**
The current walk-forward check flags IS/OOS Sharpe degradation > 50%. This is one dimension of overfitting. AI can synthesize multiple signals: "This strategy shows: (1) OOS Sharpe degradation of 38% (below warning threshold, but notable), (2) profit factor in-sample 2.4 vs out-of-sample 1.3 (significant compression), (3) top 3 exit reasons in-sample are all target hits, but out-of-sample 60% are time exits (strategy is not reaching targets in real market conditions). These patterns together suggest mild optimization overfitting — consider widening stop distance and reducing target multiples."

**B3 — Drawdown explanation.**
The equity curve shows drawdown visually but provides no narrative. For each significant drawdown (>5% peak-to-trough), generate: "Drawdown period Jan 15 – Feb 3: -9.2%. This period coincided with [regime from regime_breakdown] conditions. During this period, [N] trades were stopped out vs [M] targets hit. The drawdown resolved when [regime changed / volatility normalized]."

**B4 — Regime-based deployment recommendation.**
The regime analysis in RunDetails shows win rate by regime. AI can translate this: "This strategy performs well in trending_up regimes (win rate 73%, avg R 2.1) and poorly in ranging regimes (win rate 38%, avg R 0.6). Recommendation: add a regime filter in Strategy Controls to block entries when the regime classifier detects a ranging market. Expected improvement: +18% reduction in losing trades based on this backtest's regime distribution."

**B5 — Cost sensitivity interpretation.**
The `cost_sensitivity_curve` in ValidationEvidence shows how performance degrades as commission/slippage increases. AI can translate: "This strategy's edge disappears at approximately 8 bps of total transaction cost. Your current backtest assumed 2 bps slippage + 1 cent commission. At your broker's actual fill quality (estimated 3–5 bps slippage), the strategy retains approximately [computed_value]% of its edge. At 8+ bps, the strategy breaks even."

---

## 6. GOVERNOR + AI OPPORTUNITY

### Current State

The Account Governor captures GovernorEvents (collision_suppressed, correlation_blocked, risk_blocked, daily_loss_lockout, drawdown_lockout, halt_triggered) and displays them in an events log. The display is raw: event type string + timestamp + brief reason. No AI.

### Where AI Adds Value

**G1 — Event explanation (described in O6 above).**

**G2 — Pattern analysis over the event log.**
If `collision_suppressed` fires 12 times in one day for the same symbol, the user should be alerted: "Symbol AAPL has been involved in 12 collision suppressions today. This suggests two or more of your programs have conflicting signals on AAPL simultaneously. Programs involved: [Program A (long signal)], [Program B (short signal)]. Recommended fix: add AAPL to Program B's deny list or assign it exclusively to one program."

The current system records individual events but never aggregates or analyzes patterns across events. LLM analysis of event log batches (hourly or daily) would identify systematic problems that are invisible in the per-event view.

**G3 — Portfolio risk assessment narrative.**
The portfolio snapshot shows: total allocated capital, symbol overlap list, collision risk symbols. AI can synthesize: "Your portfolio allocates 78% of capital to 3 programs that all trade large-cap tech. In a sector rotation or tech selloff, all three programs would likely enter drawdown simultaneously. Correlation between AAPL, MSFT, NVDA positions across your programs is estimated at 0.82. Recommend: (1) add a sector exposure limit to your governor configuration, (2) allocate at least one program to a non-correlated asset class."

**G4 — Safe adjustment suggestions for halted governor.**
When a governor is halted by a risk rule (daily_loss_lockout, drawdown_lockout), the user needs to decide: resume (and risk more losses) or make a change (but what change?). AI can advise: "Your governor was halted at 14:23 due to daily loss limit (-3.2% today). Before resuming: (1) Review today's 4 losing trades [links]. (2) Consider widening stop distance — 3 of today's 4 losses were stops hit within 0.3× ATR of entry, suggesting the stop was too tight for today's volatility. (3) The current day's remaining session has 1.5 hours — consider waiting until tomorrow."

---

## 7. LIVE RUNTIME + AI OPPORTUNITY

### Current State

Live Monitor shows positions, orders, equity, and connection status. No anomaly detection. No baseline comparison. No alerts beyond WebSocket connection status.

### Where AI Adds Value

**L1 — Anomaly detection baseline (described in O5 above).**

**L2 — Fill quality monitoring.**
Compare actual fill prices to the backtest's `slippage_bps_assumption`. If a strategy assumed 2 bps slippage but is consistently getting 8 bps in live trading, alert: "Warning: Fill quality divergence detected. Your backtest assumed 2 bps slippage. Over the last 15 fills, actual slippage averaged 7.4 bps. At this fill quality, your strategy's edge is reduced by approximately 35% based on the cost sensitivity curve from your last backtest."

**L3 — EWM drift alert.**
Given the feature engine audit finding that live EMA/ATR/RSI values differ from backtest values due to EWM reseeding (documented in `feature_engine_audit.md`, Hard Fix H1), AI cannot fix the computation gap — but it can explain it. When a live deployment produces a trade at a price that would not have been a signal in Sim Lab, generate: "This entry may appear inconsistent with your simulation results. This is expected: live indicator values are computed over a 250-bar rolling window, while simulation uses full historical context. EMA(21) at this bar in simulation: $48.32. EMA(21) in live: $48.47. Difference: $0.15 (0.3%). This is within normal live/backtest divergence range."

**L4 — Unusual signal frequency alert.**
If a strategy that averages 2 trades/day suddenly fires 8 signals in 30 minutes: "Unusual signal frequency detected for [Program Name]. Expected rate: ~2 trades/day. Detected: 8 signals in the last 30 minutes. Possible causes: (1) market volatility spike is triggering rapid RSI oscillation around your threshold, (2) a data feed issue is producing duplicate bars. Recommend: pause this deployment and inspect the last 10 signals."

---

## 8. AI RISK ANALYSIS

### Where AI Is Currently Dangerous

**Risk R1 — Hallucinated strategy conditions reach the backtest engine unvalidated.**

The `POST /strategies/generate-conditions` endpoint's only validation is `isinstance(conditions, list)`. A condition with an invalid indicator name (e.g., `"macd_histogram"` instead of `"macd_hist"`) will be stored in the StrategyConfig, pass the structural validator, and cause a KeyError or NaN column in `_resolve_value()` during backtest execution. The backtest will either fail with an unhelpful error or silently evaluate all conditions as False (producing zero trades with no explanation).

**Severity: HIGH.** A user who cannot debug indicator reference errors will lose confidence in the entire platform, not just the AI feature.

**Mitigation required:** Add an indicator name validation step after condition generation. Compare every `{"indicator": "<name>"}` reference against the canonical indicator catalog. Reject or flag any name not in the catalog before the conditions are stored.

---

**Risk R2 — Dimensionally mismatched conditions are treated as valid.**

An LLM-generated condition comparing RSI(14) to EMA(21) is structurally valid JSON but semantically meaningless. It will be stored, backtested, and return results that appear to reflect strategy performance but actually reflect arbitrary number comparisons. A user may iterate on this "strategy" for weeks before realizing the conditions make no sense.

**Severity: HIGH.** This silently invalidates the entire research workflow without the user knowing.

**Mitigation required:** Add a semantic validation step. For each indicator/field in a condition, track its output type (0-100 oscillator, price-scale, boolean, volume-scale, etc.). Flag comparisons between incompatible types.

---

**Risk R3 — AI health badges imply validation that did not occur.**

The Risk Profile "Analyze" feature returns `health: 'good'|'caution'|'risky'` which is displayed as a green/amber/red badge on the profile. A user sees a green badge and believes the risk profile has been validated. It has not — the LLM assessed 11 numbers in isolation, with no knowledge of the strategy, timeframe, symbol volatility, or account size.

A risk profile with `max_position_size=20%` and `max_leverage=4.0` could receive a "good" health rating from the LLM if the other parameters look conservative. But 20% position size at 4× leverage means a single position can represent 80% of account equity — which is catastrophically concentrated for any strategy.

**Severity: HIGH.** The health badge creates false confidence in a financial-safety-critical parameter.

**Mitigation required:** Never display the LLM health assessment as a standalone badge. Always pair it with hardcoded rule-based checks (e.g., `position_size × leverage > 50% equity → always flag regardless of LLM health`). Label LLM assessments explicitly: "AI commentary (not a compliance check)."

---

**Risk R4 — "Promote Advice" in the `/ml/` route implies ML validation.**

`POST /ml/promote-advice` performs a checklist key lookup. It is not machine learning. It is not a model. It returns `recommend=True` if certain string keys are present in metadata — regardless of whether the paper performance was actually good, whether the risk profile is appropriate, or whether market conditions are favorable for deployment.

A user may treat this endpoint's `recommend=True` as meaningful AI endorsement of a paper-to-live promotion. It is not. It checks whether you ticked checkboxes.

**Severity: MEDIUM.** The misrepresentation of this heuristic as an ML feature (`/ml/promote-advice`) may cause users to over-trust its output.

**Mitigation required:** Rename the endpoint to `/deployments/promotion-checklist` or similar. If an actual promotion-readiness assessment is desired, build it on real paper trading metrics: minimum days running, Sharpe > threshold, drawdown within expected range, fill quality comparison.

---

**Risk R5 — LLM generates strategy names and descriptions that are auto-applied to forms.**

Features A3, A4, A5 auto-apply the LLM-generated `suggested_name` and `suggested_description` to the form fields. This means an LLM-generated string can silently overwrite whatever the user had typed. If the LLM produces a name like "High Risk Aggressive Trend · 10pos · 15% heat · 8% daily" and the user had typed "Conservative Daily Scalp," the user's text is overwritten without a diff or confirmation.

**Severity: LOW-MEDIUM.** Annoying rather than dangerous for naming. But the pattern of auto-applying LLM output to form fields without explicit confirmation is a bad precedent — if extended to condition trees or risk parameter values, it becomes dangerous.

**Mitigation required:** Show LLM-generated name/description as a suggestion below the input field, with a "Use this" button. Never auto-apply without explicit user action.

---

**Risk R6 — The RandomForest ML model has no integration guardrails.**

The sklearn ML pipeline (`/ml/train`, `/ml/signals`) can generate BUY/SELL signals from a model trained on any symbol with any date range and any target horizon. These signals currently cannot reach the strategy engine. But if a future developer connects them (e.g., as a condition type), the model has no safeguards:
- The model is trained with a simple positive-return binary label — no risk adjustment, no regime awareness
- There is no minimum sample size enforcement (a model trained on 50 bars is as valid as one trained on 5,000)
- Feature data for live signal generation comes from yfinance directly in `_build_dataset`, not from the CerebroEngine's canonical feature cache — signals generated from the model may use different indicator values than the strategy engine's real-time values
- Model drift is not detected — a model trained in 2020 generates signals in 2026 with no staleness check

**Severity: MEDIUM for current state (disconnected), HIGH if connected to the engine.**

---

### Where AI Must Be Constrained

1. **Strategy condition generation** — must be validated against the canonical indicator catalog before storage. Invalid indicator names must be rejected with a clear error, not silently stored.

2. **Health/compatibility badges** — must be paired with hardcoded hard-constraint checks that cannot be overridden by LLM assessment. LLM provides commentary; rules provide safety gates.

3. **Risk profile parameters** — AI must not be permitted to suggest changes to `max_drawdown_lockout`, `daily_loss_limit`, or `max_leverage` values without a human review step and explicit confirmation.

4. **Form auto-apply** — LLM outputs should be displayed as suggestions with explicit user confirmation, not auto-applied.

5. **The promote-advice endpoint** — must not represent itself as AI-based validation of paper performance.

---

### Where AI Must Be Verified

1. Every LLM-generated condition must be validated: indicator name against catalog, operator against allowlist, dimension compatibility between left/right.

2. Every LLM health/compatibility assessment must be labeled as "AI commentary, not a safety check."

3. The ML RandomForest signals must not be connected to the strategy engine without: sample size minimums, data freshness checks, feature-cache alignment verification, and a minimum OOS performance threshold.

---

### Where AI Must NOT Be Used

1. **Order submission** — no LLM should directly or indirectly control order submission. All orders go through `alpaca_service.py` after Account Governor approval. This is non-negotiable.

2. **Kill switch trigger** — no AI system should trigger, inhibit, or delay a kill switch action. Kill switch must remain entirely under human control.

3. **Position sizing** — AI must not suggest or override position size calculations. The Risk Profile is the canonical source of sizing. LLM commentary on risk parameters is advisory only.

4. **Real-time stop management** — AI must not suggest or execute stop price changes in live trading without explicit human confirmation. The PositionActionsPanel already requires explicit user action; this constraint must be maintained.

5. **Backtest result certification** — AI should not provide a pass/fail certification for backtest results that could be misinterpreted as regulatory or compliance validation. All AI analysis must be labeled "AI commentary for informational use only."

---

## 9. QUICK WINS (0–2 WEEKS)

These require no architectural changes. Each can be implemented as a new LLM call with existing infrastructure.

**QW1 — Unified indicator allowlist constant.**
Create a single `ALLOWED_INDICATORS: list[str]` constant in a new file `backend/app/ai/indicator_catalog.py`. Import it in both `_CONDITION_SYSTEM_PROMPT` and `_BRIEF_SYSTEM_PROMPT` (render it via f-string interpolation). This eliminates the divergence between the two prompt lists. Estimated effort: 2 hours. Eliminates drift risk immediately.

**QW2 — Post-generation indicator name validation.**
After every `generate-conditions` and `generate-brief` call, iterate over the returned condition tree and validate every `{"indicator": "<name>"}` reference against `ALLOWED_INDICATORS`. Return a structured error for any invalid name: `{error: "invalid_indicator", field: "conditions[2].left.indicator", value: "macd_histogram", suggestion: "macd_hist"}`. Estimated effort: 4 hours. Eliminates Risk R1 (hallucinated indicator names reaching the engine).

**QW3 — LLM-generated backtest narrative on Run Details.**
Add a new endpoint `GET /backtests/{run_id}/narrative` that passes the run's key metrics (return, Sharpe, max DD, win rate, SQN, walk-forward summary, CPCV pass/fail, regime breakdown) to the LLM with a structured prompt requesting a 3-paragraph verdict: summary, risks, recommendations. Display it in a collapsible "AI Analysis" card on the Overview tab of Run Details. Add a "Regenerate" button. Estimated effort: 1 day backend + 0.5 day frontend.

**QW4 — Remove auto-apply for LLM-generated names/descriptions.**
Change features A3, A4, A5 to display the LLM-generated name/description as a suggestion below the form field with a "Use suggestion" button. Never auto-apply. Estimated effort: 2 hours per feature (6 hours total). Eliminates Risk R5.

**QW5 — Label all LLM health badges as "AI commentary."**
Add a subtitle under every health badge generated by features A3, A4, A5: "AI assessment · not a compliance check." Style it in muted text below the badge. Estimated effort: 1 hour. Directly mitigates Risk R3.

**QW6 — Move `promote-advice` out of `/ml/` prefix.**
Rename `POST /ml/promote-advice` to `POST /deployments/{id}/promotion-readiness`. This removes the false implication that it uses ML. Update the frontend API client. Estimated effort: 2 hours. Mitigates Risk R4.

**QW7 — Misconfiguration detection for zero-trade simulations.**
In `SimulationService`, after simulation completes with zero trades, call the LLM with the strategy config + date range + regime distribution + indicator warmup requirements. Return a structured explanation of why no trades fired. Display it in the Sim Lab "no trades" empty state. Estimated effort: 1 day. High user value for a low-effort change.

**QW8 — Surface the ML pipeline in a basic UI page.**
Add a minimal "ML Models" page (in Admin or Validate) that exposes: dataset preparation, model training, model list, signal generation. Even a basic form-based UI makes this powerful backend capability accessible to users. Estimated effort: 2 days frontend. Zero backend changes required.

---

## 10. MID-TERM WINS (1–2 MONTHS)

These require architectural changes or new data pipelines.

**MW1 — Trade decision trace (O1 above).**
In `BacktestEngine._process_entries()`, when an entry is executed, serialize the EvalContext state: all condition objects, their evaluated left/right values, their pass/fail result. Store this as a `decision_trace` JSON field on the `Trade` model. Display it in the Trade Journal's expand panel. For Sim Lab, emit the trace over the WebSocket on each `trade_entry` event. Estimated effort: 3–4 days backend, 2 days frontend.

**MW2 — Semantic condition validator.**
Build a `ConditionValidator` that maps each indicator to its output type (dimensionless 0-100, price-scale, volume-scale, boolean, percentage). For each condition, check that left and right are dimensionally compatible. This can be entirely rule-based (no LLM required) and is more reliable than LLM-based validation for this specific use case. Return structured findings: `{severity, condition_index, left_type, right_type, explanation}`. Integrate into the strategy validator endpoint and Strategy Builder UI. Estimated effort: 2 days.

**MW3 — Live deployment anomaly baseline.**
At deployment launch, compute expected ranges from the linked backtest run (if available) or from the last N paper deployment trades. Store these baselines in the `AccountAllocation` or a new `DeploymentBaseline` model. Add a background task that runs every 15 minutes for each active deployment, comparing live metrics to baseline, and creating a `GovernorEvent` of type `anomaly_detected` when thresholds are exceeded. Add LLM-generated explanations to anomaly events. Estimated effort: 4–5 days.

**MW4 — Optimization run pruning with pre-run LLM analysis.**
Before launching an optimization batch in `param_optimizer.py`, add a pruning step: pass the parameter grid and strategy type to an LLM, receive back a set of parameter combinations to skip (e.g., stop multiples < 0.5 for swing strategies) and a suggested ordering of the remaining combinations (most promising first). The grid search then runs in the suggested order with early stopping after X runs show diminishing returns. Estimated effort: 3 days.

**MW5 — Governor event pattern aggregation with AI alerts.**
Add a background task that runs daily (or after each trading session) and analyzes the last session's governor events. Group by event type, symbol, and program. Identify patterns: same symbol generating collision events repeatedly, risk_blocked firing more than expected, daily_loss_lockout triggering multiple days in a row. Generate an LLM-based daily summary: "Yesterday's session — key governance events: [bulleted list with explanations and suggested actions]." Deliver via the Logs panel or a new Alerts section. Estimated effort: 3 days.

**MW6 — Drawdown narrative with Monte Carlo context (O8 above).**
Integrate live drawdown monitoring with the stored Monte Carlo results from the linked backtest. When live drawdown > 50% of backtest max DD, generate an LLM narrative using the Monte Carlo percentile data as context. Estimated effort: 2 days.

**MW7 — Connect ML signals as a strategy condition type.**
Add `{"indicator": "ml_signal_{model_id}"}` as a valid ValueSpec indicator type. The feature engine computes this by calling the stored RandomForest model's `predict_proba()` against the current bar's feature vector. This requires: (1) CerebroEngine knowing which models are referenced by which strategies, (2) feature alignment between model training features and CerebroEngine's computed features, (3) a minimum staleness check (model trained > 2 years ago requires re-validation). Estimated effort: 5–7 days. This is the highest-leverage ML change possible.

---

## 11. LONG-TERM AI PLATFORM VISION

### Fully Assisted Strategy Design

In the fully-realized version of this platform, strategy creation begins with a conversation, not a form:

The user types: "I want a mean reversion strategy for large-cap equities that enters when stocks are oversold on an intraday basis and exits within the same session."

The AI responds with:
1. A structured strategy brief (what is built today — A2)
2. A recommended indicator set with explanations of why each indicator is included
3. A timeframe recommendation ("1m or 5m is appropriate for same-session mean reversion")
4. An initial set of entry conditions
5. A semantic validation of those conditions ("RSI < 30 with BB%B < 0.1 are complementary — both measure oversold conditions but from different perspectives")
6. A suggested Strategy Controls configuration (session window 9:45–15:30, force-flat at 15:50, cooldown 30 min after stop)
7. A suggested Risk Profile based on the strategy type and typical win rates for mean reversion

The user refines through dialogue. No form navigation. No page-hopping between Strategy Creator, Strategy Controls, Risk Profiles, and Execution Styles.

This requires: a conversational AI session that maintains state across component creation, the ability to build `FeatureSpec`-correct configurations from natural language, and a component-validation layer that checks each component against the others for coherence.

---

### Automated Validation Loops

Today: User → Backtest → Review → Iterate → Backtest → Review → Deploy

Tomorrow: User specifies constraints ("Sharpe > 1.0, max DD < 15%, OOS positive rate > 70%"). AI generates candidate strategies. System automatically backtests each. Results that pass constraints are ranked by AI for robustness. Top candidates are presented to the user for review and deployment decision.

The human remains in the loop at the deployment decision stage. Everything before that — generation, testing, iteration, optimization — is automated.

This requires: automated strategy variation generation (small perturbations of conditions and parameters), a structured acceptance criterion framework, and a loop-termination condition (when does the AI stop generating variants?). The backtest engine already supports batch execution via `param_optimizer.py`. The missing piece is the intelligent variation generation and acceptance logic.

---

### Intelligent Portfolio Management

Today: The Governor detects collisions and blocks signals. The user is notified.

Tomorrow: The Governor actively manages portfolio composition. When two programs want to enter opposing positions in the same symbol, the Governor asks: "Which program has the stronger signal right now, based on current market conditions and each program's historical performance in this regime?" It allocates to the stronger signal and logs the reasoning.

When the daily loss limit is approaching, the Governor dynamically reduces position size targets for all active programs (rather than hard-blocking all new entries), proportionally to each program's current drawdown contribution.

This requires: a Governor-level AI that can reason about multiple programs simultaneously, access to each program's real-time performance metrics, and the authority to modify (not override) the sizing and entry decisions of each program within pre-defined bounds.

---

### Self-Diagnosing Systems

The platform today generates logs, metrics, governor events, and trade records but requires the user to interpret all of it. In the fully-realized vision:

Every morning, before market open, the system generates a pre-market briefing: "Active deployments: 3 (1 live, 2 paper). Yesterday's performance: [summary]. Governance events: [notable events]. Market conditions today: [regime assessment from indicators]. Risk flags: [any programs approaching drawdown limits, unusual market structure]. Recommended actions: [specific, actionable items]."

During the trading session, anomalies trigger instant plain-English alerts with specific action recommendations.

After each session, a post-session analysis generates: "What went well, what went wrong, what to adjust tomorrow."

The user transitions from actively managing the system to reviewing AI-generated assessments and making governance decisions.

---

## FINAL VERDICT

### Where AI Is Currently Wasted

**The five LLM features exist to suggest names and descriptions.** The most-used outputs of features A3, A4, and A5 are `suggested_name` and `suggested_description` — they auto-apply to form fields. This is useful UX sugar but represents a small fraction of what an LLM can contribute to a trading platform.

**The health badges are LLM theater.** The `health: 'good'|'caution'|'risky'` output is treated as meaningful risk assessment in the UI. It is not. It is a text classification by a general-purpose language model on three numbers, with no domain context, no strategy context, and no hardcoded constraints. The health badge actively creates false confidence.

**The sklearn ML pipeline is invisible.** Six backend endpoints represent a real, functional ML capability — feature engineering, time-series cross-validated RandomForest training, signal generation, model comparison. No user has ever seen this from the frontend. This capability is entirely wasted.

**The heuristic features in the `/ml/` prefix create a misleading AI brand.** `promote-advice`, `recommendations`, `suggest-risk-profile`, and `provider-recommendation` are algorithmic functions that are correct and valuable. But labeling them under `/ml/` creates an expectation of ML capability that undermines trust when users understand what these endpoints actually do.

---

### Where AI Can Create the Most Leverage Immediately

**Highest leverage immediately available:**

1. **QW2 + QW1 (1 day):** Unify indicator catalog and add post-generation validation. This makes the existing LLM features safe and prevents hallucinated indicator names from reaching the backtest engine. Required before any AI feature can be trusted.

2. **QW3 (1.5 days):** LLM-generated backtest narrative on Run Details. This is the highest-impact user-visible AI feature that can be shipped immediately. It synthesizes all the existing computed data (metrics, walk-forward, CPCV, regime analysis) into a human-readable verdict that directly answers "should I deploy this?" — the single most important question in the platform.

3. **MW1 (5-6 days):** Trade decision trace. Capturing and displaying the condition evaluation trace for each trade — "these conditions were true, these were false, this is why the trade entered" — transforms the opacity of the strategy engine into a transparent, debuggable system.

---

### What Must Be Fixed Before AI Becomes Trustworthy

**Fix 1 — Indicator name validation post-generation (QW2).** Until this is in place, LLM-generated conditions can silently corrupt strategy configs. This is a prerequisite for all other AI features.

**Fix 2 — Remove health badges or relabel them as commentary.** Until the health badges are deescalated from "validated assessment" to "AI commentary," they create false safety confidence in risk-critical parameters. Add hardcoded constraint checks that run independently of LLM assessment.

**Fix 3 — Move promote-advice out of `/ml/`.** The false branding of heuristic checks as ML features undermines trust in the entire AI subsystem when users discover the truth. Honest labeling is a prerequisite for trust.

**Fix 4 — Resolve the feature engine EWM mismatch (documented in feature_engine_audit.md, H1).** Until live indicator values match backtest values, any AI explanation of live behavior ("this trade fired because EMA crossed above...") may reference values that are numerically different from what was computed in the backtest. AI explanations of live trades will be inconsistent with what the user saw in Sim Lab. The fix is required for AI-generated trade narratives to be trustworthy.

---

### Top 3 AI Features That Would Transform This Platform

**Transformation Feature 1 — Trade Decision Trace with Plain-English Narrative (MW1 + O1)**

This is the most impactful AI feature possible. Every trade in every backtest, simulation, and live deployment gets a serialized condition evaluation trace and an LLM-generated one-sentence explanation: "Entered long at 10:32 — RSI(14) was 28.4 (below 30 threshold), price was $48.92 above EMA(21) at $47.83, confirming uptrend. Stop placed at $47.21 (2.0× ATR of $0.71)." This transforms the platform from a signal black box into a transparent reasoning system. It directly answers the user's most fundamental question: why.

**Transformation Feature 2 — Synthesized Backtest Verdict with Specific Improvement Recommendations (QW3 + B1–B5)**

Every backtest result gets a one-page AI verdict that synthesizes metrics, walk-forward folds, CPCV results, regime analysis, and cost sensitivity into: a deployment readiness verdict, three specific risks, and two concrete parameter adjustments to test next. This collapses the validation cycle — instead of requiring the user to interpret 15 data sections across 6 tabs, they get a single actionable verdict. It directly accelerates the validate → deploy decision that is the platform's core value proposition.

**Transformation Feature 3 — Live Anomaly Detection with Baseline Comparison (MW3 + O5)**

Every live deployment gets a behavioral baseline from its backtest (expected trade frequency, expected position sizes, expected fill quality, expected drawdown range). The system continuously compares live behavior to baseline and alerts immediately on deviation with LLM-generated explanations and recommended actions. This feature does not require the user to be watching the platform. It makes the platform self-monitoring. It prevents the most catastrophic user experience in algorithmic trading: discovering hours later that a strategy has been trading far outside its expected parameters.
