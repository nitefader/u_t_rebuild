# Feature Vocabulary Catalog

**Version:** 1.0  
**Status:** Canonical reference draft  
**Timestamp (ET):** 2026-04-22 12:08:00 PM ET  
**Scope:** Canonical feature names, meanings, scope rules, and causality notes

---

## Purpose

This document is the canonical vocabulary reference for Feature Engine names used across:

- Strategy Builder
- AI strategy generation
- backend validation
- backtest computation
- simulation
- paper/live runtime
- Portfolio Governor

It complements:

- [Feature_Engine_Spec.md](./Feature_Engine_Spec.md)
- [Feature_Engine_Spec_DRD.md](./Feature_Engine_Spec_DRD.md)
- [Canonical_Architecture.md](./Canonical_Architecture.md)

If a feature name appears in UI, AI prompts, validation, or runtime, it should be documented here.

---

## Naming Rules

### Rule 1: Prefer stable canonical names

Canonical names should be:

- machine-friendly
- predictable
- composable
- safe for AI to reuse

Examples:

- `ema_21`
- `rsi_14`
- `opening_range_high`
- `prev_day_high`
- `portfolio_open_risk_pct`

### Rule 2: Use internal canonical names first

UI labels may later be friendlier than internal names.

Examples:

- canonical: `prev_day_high`
- UI label: `Previous Day High`

### Rule 3: Timeframe matters

A feature name may be canonical, but it is only meaningful together with timeframe and scope.

Example:

- `ema_21` on `5m`
- `ema_21` on `1d`

These are different feature instances.

### Rule 4: Feature support is end-to-end only

A name belongs in this catalog only if it is intended to be supported consistently across the platform or is clearly marked as planned-only.

---

## Feature Status Labels

- `Supported`
  Intended to be usable end-to-end

- `Partially Supported`
  Exists in some surfaces but not fully generalized yet

- `Planned`
  Defined for the target architecture but not yet fully implemented

---

## Feature Classes

1. `Price / bar fields`
2. `Core technical features`
3. `Session / calendar features`
4. `Structure / derived context features`
5. `Portfolio / governor features`

---

## 1. Price / Bar Fields

These are not advanced features, but they are part of the vocabulary.

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `open` | price | symbol | yes | Supported | bar open price | causal on current bar |
| `high` | price | symbol | yes | Supported | bar high price | causal only after bar completion in backtest logic |
| `low` | price | symbol | yes | Supported | bar low price | causal only after bar completion in backtest logic |
| `close` | price | symbol | yes | Supported | bar close price | causal at bar close |
| `volume` | price | symbol | yes | Supported | bar volume | causal at bar close |

---

## 2. Core Technical Features

### Moving averages

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `sma_N` | technical | symbol | yes | Supported | simple moving average over `N` periods | causal if computed from completed bars only |
| `ema_N` | technical | symbol | yes | Supported | exponential moving average over `N` periods | causal if updated incrementally from prior state |
| `wma_N` | technical | symbol | yes | Partially Supported | weighted moving average | must match validator/runtime support |
| `vwma_N` | technical | symbol | yes | Partially Supported | volume-weighted moving average | must remain aligned to timeframe bars |
| `hull_ma` | technical | symbol | yes | Supported | default Hull moving average variant | period handling should remain explicit |
| `hull_ma_N` | technical | symbol | yes | Supported | Hull moving average with period `N` | causal with completed bars only |

### Momentum / oscillators

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `rsi_N` | technical | symbol | yes | Supported | RSI over `N` periods | causal if rolling window excludes future bars |
| `macd` | technical | symbol | yes | Supported | MACD main line | causal if EMA inputs are causal |
| `macd_signal` | technical | symbol | yes | Supported | MACD signal line | same as above |
| `macd_hist` | technical | symbol | yes | Supported | MACD histogram | same as above |
| `stoch_k` | technical | symbol | yes | Supported | stochastic %K | causal if based on completed bar windows |
| `stoch_d` | technical | symbol | yes | Supported | stochastic %D | same as above |
| `ibs` | technical | symbol | yes | Supported | Internal Bar Strength | causal at completed bar close |
| `zscore` | technical | symbol | yes | Supported | rolling z-score of close | causal if rolling window is backward-only |
| `zscore_10` | technical | symbol | yes | Supported | 10-bar z-score | same as above |
| `zscore_20` | technical | symbol | yes | Supported | 20-bar z-score | same as above |
| `bt_snipe` | technical | symbol | yes | Supported | z-score of deviation from EMA-style mean | must remain backward-looking |

### Volatility / trend strength

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `atr` | technical | symbol | yes | Supported | default ATR alias, usually ATR-14 | must be deterministic across runtime surfaces |
| `atr_N` | technical | symbol | yes | Supported | ATR over `N` periods | causal if based only on prior/current bars |
| `adx` | technical | symbol | yes | Supported | ADX trend-strength measure | causal with completed bars |
| `plus_di` | technical | symbol | yes | Supported | positive directional index | same as above |
| `minus_di` | technical | symbol | yes | Supported | negative directional index | same as above |

### Volume / price context

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `vwap` | technical | session | yes | Supported | session VWAP | resets by session; must not leak across sessions |
| `vwap_session` | technical | session | yes | Partially Supported | explicit session-scoped VWAP name | should unify with `vwap` semantics |
| `volume_sma_N` | technical | symbol | yes | Supported | rolling average of volume over `N` bars | causal if shifted/defined consistently |
| `volume_avg_N` | technical | symbol | yes | Supported | alternate volume rolling mean naming | should eventually converge with one canonical convention |
| `open_gap_pct` | session/context | session | yes | Supported | open vs prior close percent gap | must use prior completed close only |

### Bands / channels / levels

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `bb_upper` | technical | symbol | yes | Supported | upper Bollinger Band | causal if rolling basis is causal |
| `bb_mid` | technical | symbol | yes | Supported | Bollinger midline | same as above |
| `bb_lower` | technical | symbol | yes | Supported | lower Bollinger Band | same as above |
| `dc_upper` | technical | symbol | yes | Supported | Donchian upper channel | must use prior/completed bars consistently |
| `dc_mid` | technical | symbol | yes | Supported | Donchian midline | same as above |
| `dc_lower` | technical | symbol | yes | Supported | Donchian lower channel | same as above |
| `donchian_high` | technical | symbol | yes | Supported | Donchian breakout high reference | should stay backward-looking |
| `donchian_low` | technical | symbol | yes | Supported | Donchian breakout low reference | same as above |
| `pp` | technical | symbol | yes | Supported | pivot point | calendar/session definition must be stable |
| `r1` | technical | symbol | yes | Supported | resistance 1 | same as above |
| `r2` | technical | symbol | yes | Supported | resistance 2 | same as above |
| `r3` | technical | symbol | yes | Supported | resistance 3 | same as above |
| `s1` | technical | symbol | yes | Supported | support 1 | same as above |
| `s2` | technical | symbol | yes | Supported | support 2 | same as above |
| `s3` | technical | symbol | yes | Supported | support 3 | same as above |

### Stop-and-reverse / bar pattern context

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `sar` | technical | symbol | yes | Supported | parabolic SAR value | causal if updated from prior state only |
| `sar_trend` | technical | symbol | yes | Supported | SAR trend direction proxy | same as above |
| `strat_num` | derived context | symbol | yes | Supported | numeric TheStrat classification | causal from current and previous bars only |
| `strat_dir` | derived context | symbol | yes | Partially Supported | string TheStrat classification | should align with `strat_num` semantics |

---

## 3. Session / Calendar Features

These are especially important for intraday, ORB, and prior-period logic.

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `opening_range_high` | session/context | session | yes | Supported | high of the defined opening range window | must freeze only after opening window completes |
| `opening_range_low` | session/context | session | yes | Supported | low of the defined opening range window | same as above |
| `prev_day_high` | session/context | session | yes | Supported | prior completed session high | must never use current session high |
| `prev_day_low` | session/context | session | yes | Supported | prior completed session low | same as above |
| `prev_day_close` | session/context | session | yes | Supported | prior completed session close | same as above |
| `prev_week_high` | session/context | calendar | yes | Supported | prior completed trading week high | must use completed prior week only |
| `prev_week_low` | session/context | calendar | yes | Supported | prior completed trading week low | same as above |
| `prev_week_close` | session/context | calendar | yes | Supported | prior completed trading week close | same as above |
| `prev_month_high` | session/context | calendar | yes | Planned | prior completed month high | must be calendar-complete only |
| `prev_month_low` | session/context | calendar | yes | Planned | prior completed month low | same as above |
| `prev_month_close` | session/context | calendar | yes | Planned | prior completed month close | same as above |
| `session_state` | session/context | session | yes | Planned | premarket / regular / after-hours / closed | must come from market calendar logic |
| `market_day_type` | session/context | calendar | yes | Planned | regular / holiday / half-day | must come from authoritative calendar service |
| `premarket_high` | session/context | session | yes | Planned | premarket session high | requires clean premarket session partition |
| `premarket_low` | session/context | session | yes | Planned | premarket session low | same as above |

---

## 4. Structure / Derived Context Features

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `swing_high` | structure | symbol | yes | Supported | most recent detected swing high reference | must use causal swing detection only |
| `swing_low` | structure | symbol | yes | Supported | most recent detected swing low reference | same as above |
| `swing_highs_lows` | structure | symbol | yes | Partially Supported | grouped swing-detection family | output semantics should remain explicit |
| `fractals` | structure | symbol | yes | Partially Supported | fractal turning-point family | must be audited for lag/confirmation semantics |
| `high_N` | derived context | symbol | yes | Supported | highest high over last `N` bars | must be backward-looking |
| `low_N` | derived context | symbol | yes | Supported | lowest low over last `N` bars | same as above |
| `atr_avg_N` | derived context | symbol | yes | Supported | rolling average of ATR over `N` bars | must remain backward-looking |
| `spread_zscore` | derived context | symbol/pair | yes | Partially Supported | z-score of spread between pair assets | should be explicitly pair-scoped before broad exposure |
| `rolling_volatility` | derived context | symbol | yes | Planned | rolling realized volatility | window and annualization rules must be explicit |
| `relative_volume` | derived context | symbol | yes | Planned | current volume relative to normal volume baseline | baseline period and session rules must be explicit |
| `day_high_so_far` | session/context | session | yes | Planned | current session high up to now | causal only within-session |
| `day_low_so_far` | session/context | session | yes | Planned | current session low up to now | same as above |

---

## 5. Portfolio / Governor Features

These are not strategy indicators. They are inputs to the `Portfolio Governor`.

| Canonical Name | Class | Scope | Timeframe-Aware | Status | Meaning | Causality Notes |
|---|---|---|---|---|---|---|
| `portfolio_gross_exposure_pct` | portfolio | portfolio | n/a | Planned | total gross exposure as % of equity | must be computed from current broker/attribution truth |
| `portfolio_net_exposure_pct` | portfolio | portfolio | n/a | Planned | net exposure as % of equity | same as above |
| `portfolio_open_risk_pct` | portfolio | portfolio | n/a | Planned | stop-defined open risk as % of equity | must reflect attributed position/risk state |
| `portfolio_pending_open_risk_pct` | portfolio | portfolio | n/a | Planned | risk from resting opening orders | must exclude reducing/protective orders |
| `portfolio_symbol_concentration_pct` | portfolio | portfolio | n/a | Planned | single-symbol concentration | must use projected post-trade state when approving |
| `portfolio_sector_exposure_pct` | portfolio | portfolio | n/a | Planned | sector exposure share | requires stable symbol-to-sector metadata |
| `portfolio_cluster_exposure_pct` | portfolio | portfolio | n/a | Planned | correlation-cluster exposure | cluster definition must be versioned |
| `portfolio_intraday_loss_pct` | portfolio | portfolio | n/a | Planned | realized intraday loss as % of equity | must reset consistently by session |
| `portfolio_drawdown_pct` | portfolio | portfolio | n/a | Planned | current drawdown | source of equity series must be explicit |
| `portfolio_new_open_slots_remaining` | portfolio | portfolio | n/a | Planned | remaining capacity for new opens | must respect risk profile + pause states |
| `portfolio_pause_active` | portfolio | portfolio | n/a | Planned | whether account/portfolio scope is paused | must come from control-plane truth |
| `portfolio_global_kill_active` | portfolio | global | n/a | Planned | whether global stop-new-opens state is active | must come from control-plane truth |
| `portfolio_broker_sync_stale` | portfolio | portfolio | n/a | Planned | whether broker/account sync is stale | must fail closed in governor decisions |

---

## Alias Guidance

Aliases should be minimized.

Current examples that need discipline:

- `vwap` vs `vwap_session`
- `volume_avg_N` vs `volume_sma_N`
- `donchian_high` / `donchian_low` vs `dc_upper` / `dc_lower`

Recommended policy:

- keep old aliases only when necessary for backward compatibility
- prefer one canonical user-facing name over time
- document alias relationships explicitly during migration

---

## Causality Guidelines

Every feature in this catalog should be classifiable as one of:

- `bar-close causal`
- `session-complete causal`
- `prior-period causal`
- `projected-state governor feature`

Examples:

- `ema_21`: bar-close causal
- `opening_range_high`: session-window-complete causal
- `prev_day_high`: prior-period causal
- `portfolio_symbol_concentration_pct`: projected-state governor feature

No feature should be admitted without a clear causality model.

---

## Safe Initial Authoring Set

This is the recommended safe set for both manual and AI-assisted strategy generation:

- `ema_N`
- `sma_N`
- `rsi_N`
- `atr_N`
- `vwap`
- `adx`
- `macd`
- `macd_signal`
- `macd_hist`
- `opening_range_high`
- `opening_range_low`
- `prev_day_high`
- `prev_day_low`
- `prev_day_close`
- `prev_week_high`
- `prev_week_low`
- `prev_week_close`
- `open_gap_pct`
- `swing_high`
- `swing_low`
- `high_N`
- `low_N`
- `volume_sma_N`

This set is broad enough to support:

- ORB
- gap-and-go
- prior-day reclaim
- prior-week breakout/reject
- trend-following
- mean reversion
- volatility-aware entries

---

## Change Management Rules

Before a new feature name is added here:

1. define the canonical name
2. define scope and timeframe semantics
3. define causality model
4. verify validator support
5. verify runtime/backtest support
6. verify builder/AI prompt compatibility
7. document status as Supported / Partially Supported / Planned

---

## One-Sentence Reference Model

This catalog is the source of truth for what a feature name means everywhere in the platform.
