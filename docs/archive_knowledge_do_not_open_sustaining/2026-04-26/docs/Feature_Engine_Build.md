# Feature Engine Build

**Version:** 1.0  
**Status:** Implementation planning draft  
**Timestamp (ET):** 2026-04-22 12:18:00 PM ET  
**Scope:** Build plan, slice model, bounded contexts, and progress contract for the Feature Engine

---

## Purpose

This document turns the Feature Engine design set into an implementation-grade build plan.

It complements:

- [Feature_Engine_Spec.md](./Feature_Engine_Spec.md)
- [Feature_Engine_Spec_DRD.md](./Feature_Engine_Spec_DRD.md)
- [Feature_Vocabulary_Catalog.md](./Feature_Vocabulary_Catalog.md)
- [Feature_Engine_Implementation_Plan.md](./Feature_Engine_Implementation_Plan.md)
- [Canonical_Architecture.md](./Canonical_Architecture.md)
- [Control_Plane_Spec.md](./Control_Plane_Spec.md)

This is the document the UI progress tab should mirror at a high level.

---

## Core Build Thesis

The Feature Engine is not the broker layer, not the market data vendor, and not the strategy layer.

It sits between:

- data ingress
- strategy/program feature demand
- signal evaluation
- portfolio/governor approval

It should:

- ingest normalized bars and context from surrounding services
- compute only demanded features
- cache and update them efficiently
- expose them to strategies and the Portfolio Governor

---

## Bounded Contexts

The build should respect these bounded contexts.

### 1. Market Data Plane

Owns:

- raw bars
- bar aggregation
- provider routing
- stream subscription management
- market data freshness and replay

Current repo anchors:

- `backend/app/services/market_data_service.py`
- `backend/app/services/market_data_bus.py`
- `backend/app/services/alpaca_stream_manager.py`
- `backend/app/cerebro/bar_aggregator.py`

Must not own:

- feature semantics
- strategy evaluation
- portfolio approval

### 2. Feature Engine Core

Owns:

- `FeatureSpec`
- registry
- planner
- dependency graph
- feature cache
- incremental updates
- feature frames

Current repo anchors to evolve:

- `backend/app/cerebro/registry.py`
- `backend/app/cerebro/indicator_cache.py`
- `backend/app/cerebro/engine.py`

Must not own:

- signal logic
- broker submission
- UI-specific concerns

### 3. Strategy / Signal Context

Owns:

- declarative conditions
- feature references
- signal truth

Current repo anchors:

- `backend/app/api/routes/strategies.py`
- `frontend/src/components/StrategyBuilder/ConditionBuilder.tsx`
- `app/strategies/*`

Must not own:

- feature computation
- portfolio-level admissibility

### 4. Portfolio Governor Context

Owns:

- portfolio feature consumption
- projected post-trade evaluation
- conflict resolution
- concentration/exposure limits
- final approval/rejection of new opens

Must not own:

- raw feature generation for strategy studies
- broker storage

### 5. Broker Account Context

Owns:

- broker truth
- orders
- fills
- buying power
- account restrictions

Must not own:

- feature semantics
- strategy logic

---

## Surrounding Systems

The Feature Engine has explicit surrounding systems and data neighbors.

### Upstream surrounds

- `Historical Cache / Research Data`
  yfinance or Alpaca-fetched bars persisted through market data services

- `Alpaca Default Live Data Service`
  default live market-data source for paper/live runtime, including streaming bars and account-linked symbol subscriptions

- `Calendar / Event Services`
  holidays, half-days, earnings blackout, macro blackout, session state

- `Program Demand Registry`
  which symbols, timeframes, and features are currently required

### Downstream consumers

- `Signal Engine`
- `Simulation`
- `Backtest Engine`
- `Portfolio Governor`
- `Operator visibility / Logs progress UI`

---

## Alpaca Default Data Service

Alpaca should be treated as the **default live data service**, not as the Feature Engine itself.

### What Alpaca should provide

- live bars / stream updates
- account-linked symbol subscriptions
- broker account truth
- real-time order/fill context where needed by governor features

### What Alpaca should not provide

- feature semantics
- dependency planning
- strategy-level indicator naming
- cache-key policy

### Build implication

The Feature Engine should consume normalized data from a data-service boundary so the system can still:

- replay cached historical bars
- test with non-Alpaca historical providers
- keep feature semantics independent from one broker/vendor

Recommended rule:

- `Alpaca = default live ingress`
- `Market Data Plane = normalization and routing boundary`
- `Feature Engine = feature semantics and computation boundary`

Important current-state note:

- the repo still warms parts of runtime state from `yfinance` in places where live defaults conceptually belong to Alpaca-backed ingress
- this must be resolved in the ingress slice before runtime Feature Engine work is considered trustworthy

---

## Data Ingress Model

### Historical / research mode

Source order:

1. cached bars from local inventory
2. on-demand provider fetch through market data service
3. normalized frame returned to Feature Engine

Historical provider policy must be explicit:

- when Alpaca is preferred
- when yfinance is acceptable fallback
- how provenance is recorded on computed feature outputs

### Paper / live runtime mode

Source order:

1. warm-up load from cache/provider
2. live bar updates from Alpaca stream path
3. bar aggregation / timeframe fan-out
4. incremental feature updates

Runtime parity requirements:

- warm-up source and live continuation source must be explainable
- reconnect backfill rules must be explicit
- partial-session recovery behavior must be explicit

### Event / calendar context

Source order:

1. market calendar service
2. earnings / macro event services
3. session and blackout features emitted into Feature Engine context

This is a required context layer, not an optional enhancement.
Without it, features like `session_state`, `market_day_type`, `premarket_*`,
and event blackout features remain architecturally incomplete.

---

## Build Slices

Statuses:

- `Complete`
- `Active`
- `Planned`

### Slice 0 — Vocabulary and Contract Lock

**Status:** Complete  
**Goal:** Lock names and semantics before deeper implementation.

Deliverables:

- Feature Engine architecture spec
- DRD
- vocabulary catalog
- canonical naming rules

Exit gate:

- one canonical feature vocabulary exists for UI, AI, validation, and runtime planning

### Slice 1 — Build Plan and UI Progress Contract

**Status:** Active  
**Goal:** Turn architecture into an implementation plan and expose visible progress in the app.

Deliverables:

- this build plan document
- Logs tab for `Feature Engine Build`
- slice list, status, bounded contexts, and surrounding systems visible from UI

Exit gate:

- operator can open Logs and see Feature Engine build status without reading raw code

### Slice 2 — Registry and Planner Refactor

**Status:** Planned  
**Goal:** Evolve indicator demand into formal feature demand and execution planning.

Deliverables:

- `IndicatorRequirement` -> `FeatureRequirement`
- `FeatureSpec`
- `FeaturePlan`
- planner that reads Program/Strategy demand
- canonical source arbitration contract for requested feature provenance

Suggested file targets:

- `backend/app/cerebro/registry.py`
- `backend/app/features/planner.py`
- `backend/app/features/specs.py`

Exit gate:

- runtime can produce a deterministic feature plan from a Program without computing features ad hoc

### Slice 3 — Feature Registry and Canonical Cache Keys

**Status:** Planned  
**Goal:** Centralize feature definitions and stop scattered naming drift.

Deliverables:

- feature registry
- deterministic feature key builder
- warm-up rule definitions
- dependency declarations

Additional requirement:

- cache keys must include enough identity to prevent symbol/timeframe-only collisions when session or portfolio scope matters

Suggested file targets:

- `backend/app/features/registry.py`
- `backend/app/features/keys.py`

Exit gate:

- all new feature additions follow one canonical registration path

### Slice 4 — Session, Calendar, and Safe Symbol Feature Set

**Status:** Planned  
**Goal:** Move the core supported authoring set onto registry-driven computation with an explicit session/calendar layer.

Deliverables:

- EMA / SMA / RSI / ATR / VWAP
- opening range high / low
- prev day high / low / close
- prev week high / low / close
- open gap %
- market-session partitioning
- holiday / half-day aware roll rules
- event blackout context ingress

Suggested file targets:

- `backend/app/features/computations/core.py`
- `backend/app/features/computations/session.py`

Exit gate:

- safe authoring feature set is registry-backed and causally verified

### Slice 5 — Feature Cache and Incremental Runtime Frames

**Status:** Planned  
**Goal:** Evolve `IndicatorCache` into a true feature cache with incremental updates.

Deliverables:

- `FeatureFrame`
- cache by symbol/timeframe/feature-key
- incremental update path
- cold start and warm-up reconciliation

Suggested file targets:

- `backend/app/cerebro/indicator_cache.py` -> evolved or split
- `backend/app/features/cache.py`
- `backend/app/features/frame.py`

Exit gate:

- live runtime can update demanded features without full-history recomputation on every bar

### Slice 6 — Multi-Timeframe and Alignment Layer

**Status:** Planned  
**Goal:** Make multi-timeframe evaluation explicit and reliable.

Deliverables:

- timeframe-aware planning
- resample/alignment rules
- higher timeframe to execution timeframe mapping

Suggested file targets:

- `backend/app/features/alignment.py`
- `backend/app/features/timeframes.py`

Exit gate:

- a Program can safely demand `5m` execution with `1d` confirmation and receive deterministic aligned features

### Slice 7 — Portfolio Governor Feature Layer

**Status:** Planned  
**Goal:** Give the Portfolio Governor its own feature surface without polluting strategy features.

Deliverables:

- portfolio feature contracts
- projected post-trade state evaluation inputs
- exposure / concentration / pending-open risk features
- stale broker-sync feature inputs
- projected-state approval inputs

Suggested file targets:

- `backend/app/features/portfolio.py`
- `backend/app/services/portfolio_governor_service.py` or equivalent governor layer

Exit gate:

- portfolio admissibility checks consume a formal portfolio feature model

Scheduling rule:

- this slice must not proceed until control-plane truth for kill/pause/open gating is dependable enough to fail closed

### Slice 8 — AI and Builder Auto-Sync

**Status:** Planned  
**Goal:** Reduce duplicated feature lists and fake support.

Deliverables:

- builder feature list sourced from backend canonical list
- AI prompt surfaces generated from canonical supported set
- change-management path for new features

Exit gate:

- a newly supported feature appears consistently across UI, AI, validator, and runtime without manual drift

### Slice 9 — Explainability and Operator Diagnostics

**Status:** Planned  
**Goal:** Make feature build/debug state visible to operators and developers.

Deliverables:

- demand view by Program
- warm/cold/stale feature diagnostics
- cache hit/miss metrics
- failed feature computation visibility

Exit gate:

- operators and developers can explain why a Program does or does not have a given feature at runtime

---

## Slice Dependencies

Recommended order:

1. Slice 1
2. Slice 2
3. Slice 3
4. Slice 4
5. Slice 5
6. Slice 6
7. Slice 7
8. Slice 8
9. Slice 9

Key dependency rules:

- do not start broad runtime refactors before Slice 2 and Slice 3 are locked
- do not add lots of new features before the registry exists
- do not attempt portfolio/governor feature work before symbol/session feature foundations are stable

---

## Progress UI Contract

The `Feature Engine Build` Logs tab should show:

### Above the fold

- total slices
- completed slices
- active slices
- bounded context count
- surrounding systems count
- current default live data service

### Mid-page

- bounded context cards
- surrounding systems / data sources
- slice progress list with exit gates
- blocker-removal queue with owner slice, close proof, and next tasks

### Lower section

- planned file layout
- top risks / blockers
- reference docs in the feature-engine doc set

The screen should answer:

- what is the Feature Engine
- where it sits
- what slice we are in
- what is blocked
- what data source is default live

Autonomous update rule:

- if an agent starts, pauses, blocks, resumes, or completes a slice, the `Feature Engine Build` status surface must be updated in that same work session
- the screen is expected to reflect current execution state, not a later summary
- no retrospective bulk status updates after multiple slices have already moved

---

## Planned File Layout

Recommended target layout:

```text
backend/app/features/
  specs.py
  keys.py
  planner.py
  registry.py
  cache.py
  frame.py
  alignment.py
  timeframes.py
  portfolio.py
  computations/
    core.py
    session.py
    structure.py
    portfolio.py
```

Likely evolution points in current code:

```text
backend/app/cerebro/registry.py
backend/app/cerebro/indicator_cache.py
backend/app/cerebro/engine.py
backend/app/core/backtest.py
backend/app/api/routes/strategies.py
frontend/src/components/StrategyBuilder/ConditionBuilder.tsx
frontend/src/pages/LogsPanel.tsx
```

---

## Top Risks

1. `Vocabulary drift`
   builder, AI, validator, and runtime lists diverge again

2. `Cache semantics drift`
   multiple caches with unclear invalidation rules

3. `Multi-timeframe ambiguity`
   features exist without a stable alignment contract

4. `Session/calendar bugs`
   prior-day, ORB, holiday, and half-day behavior regress

5. `Broker coupling`
   Alpaca-specific assumptions leak into feature semantics

6. `Warm-up provenance drift`
   historical warm-up and live continuation come from different provider assumptions without explicit arbitration

---

## Review Notes

This plan should be reviewed through two lenses before deeper implementation:

- `Architecture review`
  validates bounded contexts, data ingress boundaries, and portfolio governor separation

- `UX/operator review`
  validates progress visibility, naming clarity, and above-the-fold monitoring value

---

## One-Sentence Build Framing

The Feature Engine Build is the staged effort to turn scattered indicator logic into a bounded, cache-aware, multi-timeframe, portfolio-compatible feature platform with visible operator progress.
