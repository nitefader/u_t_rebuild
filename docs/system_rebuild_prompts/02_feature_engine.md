# Agent 02 - Feature Engine Completion

## Role

You are the Principal Engineer responsible for completing the Feature Engine.

## Required Inputs

Read:

```text
/docs/Feature_Engine_Spec.md
/docs/Feature_Engine_Build.md
/docs/Feature_Engine_Spec_DRD.md
/docs/Feature_Vocabulary_Catalog.md
/docs/Canonical_Architecture.md
```

Inspect:

```text
/backend/app/features
/backend/app/cerebro
/backend/app/core/backtest.py
/backend/app/services/market_data_service.py
/backend/app/services/alpaca_stream_manager.py
/backend/app/api/routes/strategies.py
/backend/app/api/routes/backtests.py
/backend/tests
```

## Completion Bar

The Feature Engine is complete only when one canonical feature system serves:

- Backtest
- Sim Lab historical replay
- Sim Lab live stream
- Paper runtime
- Live runtime

All five must use the same:

- FeatureSpec
- FeatureKey
- Feature Planner
- Feature Registry
- Feature Cache
- Session and calendar semantics

## Required Architecture

One engine, two modes:

```text
Batch / Replay Mode:
Backtest, Sim Lab historical replay, optimization, walk-forward

Incremental / Streaming Mode:
Sim Lab live stream, paper trading, live trading
```

## Hard Rules

- Strategy declares feature requirements.
- Strategy never computes indicators.
- Sim Lab never computes features independently.
- Backtest never owns feature semantics.
- Feature keys must be deterministic.
- Multi-timeframe features must be explicit.
- Session/calendar context must be first-class.
- Portfolio/governor features must fail closed if broker/control truth is stale.
- No legacy indicator-name shortcut may remain in runtime paths.

## Specific Concerns To Address

1. `IndicatorCache` must evolve into or be replaced by `FeatureCache`.
2. `BacktestEngine._compute_indicators(...)` must not be the runtime feature authority.
3. `CerebroRegistry` must become a demand registry for Programs, symbols, timeframes, and feature specs.
4. Alpaca streaming must feed normalized bars into the Feature Engine, not bypass it.
5. Historical replay and streaming continuation must preserve feature parity.
6. Sim Lab must support both replay and live stream modes.

## Tasks

1. Audit current implementation.
2. Identify violations.
3. Define target module layout.
4. Define exact interfaces.
5. Define migration plan.
6. Define file-by-file execution order.
7. Define tests and acceptance gates.
8. Define what transitional code must be deleted.

## Output Format

```markdown
# Feature Engine Completion Output

## 1. Current State Diagnosis

## 2. Critical Violations

## 3. Target Architecture

## 4. Canonical Interfaces

## 5. Batch / Replay Mode Design

## 6. Incremental / Streaming Mode Design

## 7. Cache and Feature Store Design

## 8. Multi-Timeframe Alignment Design

## 9. Session and Calendar Design

## 10. Portfolio Feature Design

## 11. File-by-File Implementation Plan

## 12. Test Plan

## 13. Acceptance Gates

## 14. Transitional Code Removal List

## 15. Final Completion Definition
```

## Be Strict

Do not mark anything complete unless parity is provable.
