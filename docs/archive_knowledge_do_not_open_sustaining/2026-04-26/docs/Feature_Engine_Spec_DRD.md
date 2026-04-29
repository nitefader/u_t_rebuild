# Feature Engine Spec DRD

**Version:** 1.0  
**Status:** Design requirements draft  
**Timestamp (ET):** 2026-04-22 12:00:00 PM ET  
**Scope:** Product and engineering design requirements for the Feature Engine

---

## Purpose

This document defines the design requirements for the Feature Engine as a product-critical subsystem.

It complements:

- [Feature_Engine_Spec.md](./Feature_Engine_Spec.md)
- [Canonical_Architecture.md](./Canonical_Architecture.md)
- [Control_Plane_Spec.md](./Control_Plane_Spec.md)

Where `Feature_Engine_Spec.md` describes the target architecture, this DRD defines:

- what the Feature Engine must do
- who depends on it
- which workflows it must support
- what constraints it must satisfy
- how success should be measured

---

## Problem Statement

The current platform has strategy conditions, runtime indicator caching, and backtest-time indicator computation, but it does not yet have one unified, canonical feature system.

Without a true Feature Engine:

- strategies can drift from runtime capabilities
- AI-generated strategies can reference unsupported or inconsistently computed studies
- the same feature may be recomputed multiple times across Programs
- multi-timeframe logic becomes ad hoc
- portfolio-level approval logic cannot consume a clean feature model
- research, simulation, paper, and live execution risk diverging from one another

The Feature Engine exists to eliminate that drift and provide one authoritative feature layer across the platform.

---

## Goals

The Feature Engine must:

1. let strategies declare feature requirements instead of computing indicators directly
2. compute only the features actually required by active Programs
3. reuse feature computation across Programs, symbols, and timeframes
4. support batch mode for backtests and simulations
5. support incremental updates for paper and live runtime
6. support multi-timeframe feature requirements cleanly
7. support session-aware and calendar-aware features
8. support portfolio-level governor features
9. remain causal and safe for trading decisions
10. integrate cleanly with AI-assisted strategy generation

---

## Non-Goals

The Feature Engine is not intended to:

- become a general-purpose analytics warehouse
- precompute every feature for every symbol indefinitely
- replace the Portfolio Governor as the final decision authority
- allow strategies to bypass runtime controls
- become a broker execution layer
- act as a loose plugin system for arbitrary, unvalidated feature code

---

## Users and Stakeholders

### Primary users

- `Quant / Strategy Designer`
  needs reliable feature availability for strategy logic

- `Trader / Operator`
  needs consistent behavior between backtest, simulation, paper, and live

- `AI Strategy Authoring Flow`
  needs a canonical list of valid features to reference

- `Portfolio Governor`
  needs portfolio-level features for approval and rejection decisions

### Internal stakeholders

- `Strategy Builder UI`
- `Backtest Engine`
- `Simulation Lab`
- `Paper runtime`
- `Live runtime`
- `Portfolio Governor`
- `Future ML / research pipelines`

---

## Product Requirements

### PR-1: Canonical feature vocabulary

The system must expose one canonical set of supported features.

Requirements:

- every supported feature has a unique canonical name
- every feature has a deterministic normalized definition
- every feature name used by AI, the builder, validators, and runtime maps to the same semantics

Examples:

- `ema_21`
- `opening_range_high`
- `prev_day_high`
- `prev_week_close`
- `portfolio_open_risk_pct`

---

### PR-2: End-to-end compatibility

A feature must not be exposed to strategy authoring unless it is supported end-to-end.

A feature is considered supported only if:

1. it is accepted by validation
2. it is computable in the backtest engine
3. it is computable in simulation
4. it is computable or plannable in paper/live runtime
5. AI prompt surfaces know it by the same name

No “fake support” is allowed.

---

### PR-3: Declarative strategy requirements

Strategies must declare what features they require.

The strategy layer must not:

- compute indicators directly
- own cache invalidation
- own dependency resolution

The Feature Engine must resolve the required features on behalf of the strategy.

---

### PR-4: Multi-timeframe support

The engine must support multi-timeframe feature requirements as a first-class capability.

Examples:

- trade on `5m`, filter on `1h`, confirm on `1d`
- ORB on `5m`, broader trend on `1d`
- swing entry on `1d`, regime filter on `1wk`

Requirements:

- timeframe is explicit in the feature definition
- higher-timeframe alignment is deterministic
- strategies cannot rely on ambiguous timeframe mixing

---

### PR-5: Session-aware and calendar-aware features

The engine must support features whose correctness depends on market session and calendar rules.

Examples:

- `opening_range_high`
- `opening_range_low`
- `prev_day_high`
- `prev_week_low`
- `session_state`
- `market_day_type`

Requirements:

- holiday handling
- half-day handling
- regular-session awareness
- clear session reset behavior

---

### PR-6: Incremental runtime updates

For live and paper trading, the engine must support incremental updates.

Requirements:

- avoid full-history recomputation on each bar when incremental update is possible
- maintain warm state per symbol/timeframe
- support cold start + warm-up
- support runtime refresh when Program demand changes

---

### PR-7: Shared caching

The system must reuse feature computation across Programs whenever requests are identical.

Requirements:

- deterministic cache keys
- shared in-memory runtime cache
- research cache for repeated backtests/simulations
- optional selective persistent cache for expensive features

---

### PR-8: Portfolio-level features

The Feature Engine must support portfolio/governor feature generation.

Examples:

- portfolio gross exposure
- symbol concentration
- pending open risk
- sector concentration
- kill/pause state

Requirements:

- these features must be distinguishable from symbol-level features
- they must be consumable by the `Portfolio Governor`
- they must support projected post-trade state evaluation

---

### PR-9: AI strategy generation compatibility

The Feature Engine must be usable by AI-assisted strategy generation.

Requirements:

- AI prompt surfaces must reference the canonical feature vocabulary
- unsupported features must not be suggested
- newly added safe features should be available to AI automatically or with minimal duplication

This is important because the platform increasingly uses AI to generate strategy condition trees.

---

### PR-10: Causality and anti-bias safety

Features used for trading decisions must remain causal.

Requirements:

- no lookahead or future leakage
- session and prior-period features must use completed prior information only
- anti-bias checks must remain compatible with the feature vocabulary
- feature design must not silently weaken backtest integrity

---

## Core User Flows

### Flow 1: Manual strategy authoring

1. user opens Strategy Builder
2. user selects or types condition features
3. builder validates feature names against canonical supported list
4. strategy is saved with declarative feature references
5. backtest/simulation/runtime resolves those features via the Feature Engine

Success condition:

- the same feature name behaves identically across builder, validator, and execution

---

### Flow 2: AI-generated strategy

1. user prompts AI to create a strategy
2. AI uses canonical supported features only
3. backend validates the condition tree
4. user can run backtest or simulation immediately

Success condition:

- AI-generated features do not create false capability or unsupported runtime behavior

---

### Flow 3: Live/paper deployment startup

1. Program is loaded
2. Feature Planner extracts required features
3. runtime cache warms symbol/timeframe requirements
4. incremental updates begin
5. Signal Engine consumes feature outputs
6. Portfolio Governor consumes portfolio features and approves or rejects new opens

Success condition:

- runtime starts with deterministic feature coverage and no missing-study drift

---

### Flow 4: Program demand changes

1. a Program is added, removed, paused, or changed
2. runtime registry updates demanded features
3. cache and subscriptions reconcile
4. no duplicated work is introduced unnecessarily

Success condition:

- new feature demand is absorbed without recomputing unrelated features

---

## Functional Scope by Phase

### Phase 1: Safe foundation

Must include:

- canonical feature vocabulary
- feature validation contract
- builder + AI compatibility
- batch computation for backtests/simulations
- shared in-memory caching
- safe symbol/session feature set

Examples:

- EMA, SMA, RSI, ATR, VWAP
- opening range high/low
- prev day high/low/close
- prev week high/low/close
- open gap %

---

### Phase 2: Runtime expansion

Must include:

- runtime Feature Planner
- incremental updates
- multi-timeframe planning
- session/calendar-aware primitives
- richer runtime cache behavior

---

### Phase 3: Portfolio/governor integration

Must include:

- portfolio feature model
- projected post-trade state evaluation support
- governor-level feature interfaces

---

### Phase 4: Research/ML expansion

May include:

- persistent feature store for selected features
- explainability layer
- ML-oriented feature export

---

## Design Constraints

### DC-1: Compatibility with current repo direction

The design must align with:

- `CerebroRegistry`
- `IndicatorCache`
- `CerebroEngine`
- current strategy validation flow
- current builder UX

It should evolve existing architecture, not fight it.

### DC-2: Clear architecture boundaries

The design must preserve:

- `Strategy` decides what to trade and why
- `Feature Engine` computes features
- `Signal Engine` evaluates conditions
- `Portfolio Governor` decides whether a trade is admissible

### DC-3: Safe growth

The feature vocabulary should grow in curated layers.

Do not add dozens of speculative features just because AI can name them.

### DC-4: Operational seriousness

The design must be appropriate for:

- intraday strategies
- swing strategies
- paper/live runtime use
- mission-critical control flows

---

## UX Requirements

The strategy-building surface should feel declarative and trustworthy.

Requirements:

- supported features should be searchable and readable
- naming should be operator-friendly
- prior session/calendar features should be obvious and not cryptic
- AI-generated conditions should use the same vocabulary users see in the builder
- advanced features should not overwhelm the basic authoring experience

Examples:

- `prev_day_high` is acceptable as an internal canonical name
- UI may later present a friendlier label like `Previous Day High`

---

## Acceptance Criteria

The DRD is satisfied when:

1. the platform has one canonical feature vocabulary
2. builder, AI prompts, validator, and runtime agree on feature names
3. feature additions are made end-to-end, not cosmetically
4. session-aware features remain causal
5. multi-timeframe requirements are represented explicitly
6. shared computation avoids obvious duplicate work
7. portfolio/governor features have a defined role and contract

---

## Initial Safe Feature Set

The following set is the recommended “safe expansion” baseline for AI and manual strategy authoring:

- `opening_range_high`
- `opening_range_low`
- `prev_day_high`
- `prev_day_low`
- `prev_day_close`
- `prev_week_high`
- `prev_week_low`
- `prev_week_close`
- `open_gap_pct`
- `ema_*`
- `sma_*`
- `rsi_*`
- `atr_*`
- `vwap`
- `adx`
- `macd`

This set covers many common strategies without overextending runtime complexity.

---

## Risks

### Risk 1: Vocabulary drift

AI, UI, and runtime may diverge if feature names are duplicated manually in too many places.

### Risk 2: False support

A feature may appear in the builder or AI prompt before the runtime computes it correctly.

### Risk 3: Multi-timeframe ambiguity

Feature names may exist without a reliable alignment model.

### Risk 4: Session/calendar bugs

Prior-day, prior-week, and opening-range features can be wrong around holidays and half-days if not handled explicitly.

### Risk 5: Cache bloat

Overeager persistence or precomputation can create unnecessary memory or storage pressure.

---

## Recommended Next Deliverables

After this DRD, the next practical documents should be:

1. `Feature_Engine_Spec v2`
   exact interfaces, planners, cache model, dependency graph

2. `Feature Vocabulary Catalog`
   canonical names, definitions, scope, timeframe rules, causality notes

3. `Feature Engine Implementation Plan`
   file-by-file rollout plan aligned to current repo structure

---

## One-Sentence Product Framing

The Feature Engine is the platform subsystem that makes strategy features trustworthy, reusable, causal, and consistent across research, simulation, paper, live, and portfolio governance.
