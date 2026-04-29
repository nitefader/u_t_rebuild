# Feature Engine Spec

**Version:** 1.0  
**Status:** Target architecture  
**Timestamp (ET):** 2026-04-22 11:02:07 AM ET  
**Scope:** Research, simulation, paper trading, and live runtime feature generation

---

## Purpose

This document defines the target architecture for feature generation in Ultimate Trading Software 2026.

The goal is to replace ad hoc indicator computation with a disciplined, dependency-aware, cache-friendly
feature engine that:

- computes only what active Programs require
- reuses already-computed features across Programs
- supports multi-timeframe analysis cleanly
- supports both batch and incremental live updates
- separates feature generation from signal logic
- extends naturally to portfolio-level governance

This spec complements:

- [Canonical_Architecture.md](./Canonical_Architecture.md)
- [Control_Plane_Spec.md](./Control_Plane_Spec.md)

---

## Core Principle

Strategies should not compute indicators directly.

Instead:

- `Strategy` declares what features it needs
- `Feature Engine` computes and caches those features
- `Signal Engine` evaluates strategy logic against feature values
- `Portfolio Governor` consumes portfolio-level features before approving new exposure

The clean flow is:

`Program -> Feature Planner -> Feature Engine -> Signal Engine -> Portfolio Governor -> Broker Account`

---

## Why "Feature Engine" and not just "Indicator Engine"

Many important runtime inputs are not classical technical indicators.

Examples:

- `ema_20`
- `rsi_14`
- `atr_14`
- `opening_range_high`
- `prior_day_high`
- `gap_pct`
- `rolling_volatility`
- `session_state`
- `portfolio_open_risk_pct`

The system should treat all of these as features.

Feature classes:

1. `Raw-derived features`
   EMA, SMA, RSI, ATR, VWAP, MACD, Bollinger Bands

2. `Session/context-derived features`
   opening range high/low, prior day/week/month levels, gap %, session state, holiday / half-day state

3. `Composite/semantic features`
   trend regime, crossover state, volatility compression, breakout-ready state

4. `Portfolio/governor features`
   gross exposure, concentration, open risk, pending-open risk, correlation bucket exposure, kill/pause state

---

## Current Repo Alignment

This repo already contains the beginnings of the runtime feature stack:

- [backend/app/cerebro/registry.py](../backend/app/cerebro/registry.py)
  Program demand registry keyed by symbols, timeframes, and indicator requirements.

- [backend/app/cerebro/indicator_cache.py](../backend/app/cerebro/indicator_cache.py)
  Shared rolling in-memory cache for symbol/timeframe indicator frames.

- [backend/app/cerebro/engine.py](../backend/app/cerebro/engine.py)
  Central orchestration engine for warm-up, incremental bar ingestion, and callback dispatch.

This spec evolves those pieces rather than replacing them conceptually.

Recommended direction:

- `CerebroRegistry` becomes the runtime demand registry
- `IndicatorCache` evolves into a broader feature cache
- `CerebroEngine` evolves into the runtime feature orchestration engine

---

## Canonical Components

### 1. FeatureSpec

A normalized request for one feature.

Example:

```json
{
  "kind": "ema",
  "source": "close",
  "timeframe": "5m",
  "params": { "length": 20 }
}
```

Another:

```json
{
  "kind": "opening_range_high",
  "source": "session",
  "timeframe": "5m",
  "params": { "window_minutes": 15, "session": "regular" }
}
```

Required fields:

- `kind`
- `timeframe`
- `params`

Optional fields:

- `source`
- `scope`
- `session`
- `alignment`

Scope values:

- `symbol`
- `session`
- `portfolio`

---

### 2. FeatureKey

Every feature request must map to one canonical deterministic key.

Example algorithm:

```python
def feature_key(kind: str, source: str, timeframe: str, params: dict[str, object]) -> str:
    param_str = ",".join(f"{k}={params[k]}" for k in sorted(params))
    return f"{timeframe}:{kind}:{source}:{param_str}"
```

Examples:

- `5m:ema:close:length=20`
- `1d:rsi:close:length=14`
- `5m:opening_range_high:session:session=regular,window_minutes=15`

This is what allows:

- cache reuse across Programs
- deduplication of feature requests
- deterministic runtime planning

---

### 3. Feature Registry

One central definition table for supported features.

Each entry defines:

- name
- allowed parameters
- required inputs
- output columns
- warm-up rules
- dependency rules
- compute function
- incremental update support

Illustrative shape:

```python
FEATURE_REGISTRY = {
    "ema": {
        "inputs": ["close"],
        "params": ["length"],
        "outputs": ["value"],
        "warmup_fn": lambda p: p["length"] * 3,
        "incremental": True,
    },
    "atr": {
        "inputs": ["high", "low", "close"],
        "params": ["length"],
        "outputs": ["value"],
        "warmup_fn": lambda p: p["length"] * 3,
        "incremental": True,
    },
    "opening_range_high": {
        "inputs": ["open", "high", "low", "close", "volume"],
        "params": ["window_minutes", "session"],
        "outputs": ["value"],
        "warmup_fn": lambda p: 1,
        "incremental": True,
    },
}
```

Important rule:

The registry is the only place where feature semantics are defined.

---

### 4. Feature Planner

The Feature Planner is the missing orchestration layer.

Before a run begins, it inspects the full `Program` and builds the execution contract.

It must:

- inspect Strategy requirements
- inspect Strategy Controls requirements
- inspect Risk Profile requirements
- inspect Execution Style requirements
- inspect portfolio-level governance requirements if live or paper runtime is involved
- dedupe identical features
- resolve dependencies
- compute warm-up requirements
- generate the final execution plan

Example output:

```json
{
  "symbols": ["SPY", "QQQ"],
  "timeframes": ["5m", "1d"],
  "features": [
    "5m:ema:close:length=10",
    "5m:ema:close:length=20",
    "5m:rsi:close:length=14",
    "5m:atr:close:length=14",
    "1d:ema:close:length=50"
  ],
  "warmup_bars": {
    "5m": 100,
    "1d": 150
  }
}
```

The planner should operate on the `Program`, not on Strategy alone.

Why:

- Strategy may need EMA/ATR/VWAP
- Strategy Controls may need session state, regime, event blackout
- Risk Profile may need ATR or rolling volatility
- Execution Style may need VWAP or entry-offset context

---

### 5. Dependency Graph

Feature computation must be dependency-aware.

Examples:

- `ATR` depends on `high`, `low`, `close`
- `MACD` depends on multiple EMA series
- `opening_range_high` depends on intraday sessionized bars
- `prior_week_high` depends on calendar-aware aggregation
- `crossover` depends on two fully computed series
- a 5m strategy filtered by daily trend depends on 1d feature generation and correct alignment

The graph should support these layers:

1. raw bars
2. resampled bars
3. base features
4. derived features
5. signal inputs
6. portfolio/governor features

---

### 6. Feature Cache

Three cache layers are recommended.

#### Runtime cache

Fast in-memory cache for active Programs.

Use for:

- paper/live runtime
- websocket-driven updates
- repeated intra-session access

#### Research cache

Session or run-scoped cache for:

- backtests
- simulations
- parameter search

#### Persistent feature store

Selective durable storage for expensive or heavily reused features.

Persist selectively:

- expensive multi-timeframe features
- frequently reused research features
- ML-ready derived features

Do not persist everything blindly.

---

### 7. Feature Engine

The Feature Engine performs actual computation.

Modes:

- `batch mode`
  backtests, simulations, historical analysis

- `incremental mode`
  live and paper runtime updates

Responsibilities:

- compute missing features
- reuse cached features
- update incremental features in O(1) or near-O(1) where possible
- attach results to symbol/timeframe state
- expose latest feature values to signal evaluation

Examples of incremental candidates:

- EMA
- RSI
- ATR
- VWAP
- opening range high/low

Examples of session-aware features:

- VWAP resets by session
- opening range freezes after the opening window
- prior-day levels roll on session change

Not every feature is just a rolling window.

---

### 8. Signal Engine

The Signal Engine evaluates strategy logic against feature outputs.

Responsibilities:

- read feature values
- evaluate conditions
- emit candidate trade intents

Must not:

- compute features ad hoc
- own cache logic
- perform portfolio approval

This separation protects architecture boundaries.

---

## Symbol-Level Features

These are the primary features Strategies consume.

Recommended initial set:

- SMA
- EMA
- VWAP
- RSI
- ATR
- MACD
- Bollinger Bands
- highest / lowest
- opening range high / low
- volume SMA
- prior day high / low / close
- prior week high / low / close
- prior month high / low / close
- gap %
- IBS
- returns %
- rolling volatility
- ADX

Possible later additions:

- Supertrend
- anchored VWAP
- market internals-derived features
- advanced regime classifiers

---

## Multi-Timeframe Support

Multi-timeframe support must be a first-class concept.

Common examples:

- trade on `5m`
- filter by `1h` trend
- confirm with `1d` bias

Rules:

- every FeatureSpec includes timeframe
- higher-timeframe features are computed independently
- alignment back to execution timeframe must be explicit
- no ad hoc mixing of daily and intraday values in signal code

Recommended flow:

1. fetch base bars for required timeframes
2. resample when appropriate
3. compute features per timeframe
4. align higher-timeframe values onto execution bars
5. expose aligned features to Signal Engine

---

## Session, Calendar, and Market Context Features

These features are critical for intraday correctness and should be first-class.

Examples:

- `session_state`
  premarket, regular, after-hours, closed

- `market_day_type`
  regular, holiday, half-day

- `opening_range_high`
- `opening_range_low`
- `prior_day_high`
- `prior_week_high`
- `earnings_blackout_active`
- `macro_event_blackout_active`

These features depend on more than price bars.

They also require:

- session boundaries
- market calendar rules
- holiday / half-day logic
- event calendar data

---

## Portfolio-Level Features

The same philosophy extends to the `Portfolio Governor`.

Important distinction:

- Strategy features answer: `Should this trade be desired?`
- Portfolio features answer: `May this trade be admitted?`

Portfolio features are not classical indicators.
They are governor inputs.

Recommended categories:

### Exposure features

- `portfolio_gross_exposure_pct`
- `portfolio_net_exposure_pct`
- `portfolio_beta_weighted_exposure_pct`
- `portfolio_sector_exposure_pct`

### Concentration features

- `portfolio_symbol_concentration_pct`
- `portfolio_strategy_family_concentration_pct`
- `portfolio_cluster_exposure_pct`

### Risk features

- `portfolio_open_risk_pct`
- `portfolio_pending_open_risk_pct`
- `portfolio_intraday_loss_pct`
- `portfolio_drawdown_pct`
- `portfolio_new_open_slots_remaining`

### Conflict features

- `portfolio_duplicate_symbol_conflict`
- `portfolio_opposing_signal_conflict`
- `portfolio_correlation_cluster_conflict`

### Operational features

- `portfolio_pause_active`
- `portfolio_global_kill_active`
- `portfolio_broker_sync_stale`
- `portfolio_pending_order_count`

### Session / event features

- `portfolio_gap_risk_score`
- `portfolio_earnings_crowding_score`
- `portfolio_macro_event_crowding_score`

---

## Candidate-Order Evaluation

Portfolio-level approval should not inspect only the current portfolio state.

It must evaluate:

1. current state
2. proposed order delta
3. projected post-trade state

Example:

- current technology exposure = `22%`
- candidate trade adds `4%`
- projected exposure = `26%`
- if max allowed is `25%`, reject

This is the correct model for `Portfolio Governor` approval.

Recommended flow:

1. Signal Engine emits candidate trade
2. candidate order is normalized
3. Portfolio Governor computes post-trade portfolio feature deltas
4. constraints are checked
5. order is approved or rejected

---

## Recommended Runtime Flow

### Research / backtest flow

1. load Program
2. Feature Planner extracts requirements
3. dependency graph is built
4. batch features are computed
5. Signal Engine evaluates bars
6. results are persisted

### Live / paper runtime flow

1. load Deployment
2. Program demand registers with runtime registry
3. Feature Planner determines required symbol/timeframe/session features
4. warm-up loads historical bars
5. incremental bar updates refresh only affected features
6. Signal Engine evaluates candidate entries/exits
7. Portfolio Governor evaluates portfolio-level features and projected state
8. approved orders proceed to execution

---

## Mapping to Current Repo Components

### Existing

- `CerebroRegistry`
  runtime demand tracking for active Programs

- `IndicatorCache`
  current in-memory rolling frame store

- `CerebroEngine`
  orchestration for cold start, updates, dispatch

### Recommended evolution

- `IndicatorRequirement` -> `FeatureRequirement`
- `IndicatorCache` -> `FeatureCache`
- `IndicatorFrame` -> `FeatureFrame`
- `_compute_indicators()` -> registry-driven feature computation
- program subscription -> planner-derived feature plan

This is an architectural evolution, not a conceptual rewrite.

---

## Suggested Canonical Types

### FeatureSpec

```python
@dataclass(frozen=True)
class FeatureSpec:
    kind: str
    timeframe: str
    params: dict[str, object]
    source: str = "close"
    scope: str = "symbol"   # symbol | session | portfolio
```

### FeatureRequirement

```python
@dataclass
class FeatureRequirement:
    spec: FeatureSpec
    key: str
    warmup_bars: int
    dependencies: list[str]
```

### FeaturePlan

```python
@dataclass
class FeaturePlan:
    program_id: str
    symbols: set[str]
    timeframes: set[str]
    features: list[FeatureRequirement]
    warmup_by_timeframe: dict[str, int]
```

---

## What To Avoid

- precomputing every indicator for every symbol
- letting Strategies compute indicators on their own
- duplicating the same EMA/RSI/ATR series across Programs
- mixing portfolio approval logic into Strategy code
- hiding session-aware features inside generic rolling calculations
- recomputing full history on every live bar

---

## Recommended Delivery Phases

### Phase 1

- feature spec normalization
- feature registry
- planner for Strategy + Strategy Controls
- batch feature compute for backtests and simulations
- in-memory cache reuse
- multi-timeframe support

### Phase 2

- incremental runtime updates
- session-aware feature primitives
- selective persistent feature cache
- portfolio/governor feature layer
- candidate-order projected-state evaluation

### Phase 3

- explainability layer showing which features were built and why
- AI-assisted feature extraction from strategy descriptions
- ML-ready feature export and reuse

---

## Hard Rules

1. Strategies declare feature needs; they do not compute features directly.
2. Every feature request must normalize to a deterministic canonical key.
3. Multi-timeframe requirements must be explicit in the FeatureSpec.
4. Session-aware features must honor calendar/session boundaries.
5. Portfolio Governor consumes portfolio features but remains the final decision authority.
6. Candidate-order approval must evaluate projected post-trade state, not just current state.
7. Incremental live updates should not recompute full history unless recovery requires it.

---

## One-Sentence Mental Model

The platform should compute exactly the features active Programs and the Portfolio Governor require, exactly when they require them, and no more.
