# Engineering Task Breakdown

## Phase 1 Scope

This phase creates the backend-only foundation for the Trading OS.

Hard exclusions:

- No Alpaca integration
- No frontend implementation
- No database migrations
- No broker accounts
- No deployments
- No order submission
- No live streaming
- No AI generation
- No Backtest, Optimization, or Walk-Forward implementation

The phase stops at deterministic backend contracts for:

- domain schemas
- FeatureSpec / FeatureKey / FeatureRegistry
- FeaturePlanner
- SignalEngine
- Chart Lab backend preview
- Sim Lab historical replay backend contract

## Task 1. Backend Domain Schema Skeletons

### Goal

Create backend domain schemas as plain application models/dataclasses/Pydantic schemas only. These are not ORM migrations yet. The goal is to lock names, ownership, and allowed fields before persistence exists.

### Files to Create

- `backend/app/domain/strategy.py`
- `backend/app/domain/strategy_controls.py`
- `backend/app/domain/risk_profile.py`
- `backend/app/domain/execution_style.py`
- `backend/app/domain/universe.py`
- `backend/app/domain/program.py`
- `backend/app/domain/chart_lab.py`
- `backend/app/domain/simulation.py`
- `backend/app/domain/validation.py`
- `backend/app/domain/__init__.py`
- `backend/tests/unit/domain/test_domain_boundaries.py`

### Files Not to Touch

- `backend/app/models/*`
- `backend/app/database.py`
- `backend/app/api/routes/*`
- `frontend/*`
- `backend/app/services/alpaca*`
- `backend/app/broker*`
- any migration or Alembic directory

### Acceptance Criteria

- `ProgramVersion` contains component version references only.
- `ProgramVersion` has no inline strategy logic, feature logic, risk fields, execution policy, broker account id, deployment state, or runtime state.
- `StrategyVersion` contains signal definition and feature references only.
- `StrategyControlsVersion`, `RiskProfileVersion`, `ExecutionStyleVersion`, and `UniverseSnapshot` are separate schemas.
- `ChartLabSession` has no order, fill, position, PnL, equity, drawdown, or account-state fields.
- `SimulationSession` may include simulated orders/fills/positions fields, but no real broker or Alpaca fields.
- Banned names do not appear in new domain files: `StrategyGovernor`, `AccountGovernor`, `AccountAllocation`.

### Tests to Add

- Boundary test proving `ProgramVersion` rejects inline behavior fields.
- Boundary test proving `ChartLabSession` rejects simulated execution state.
- Boundary test proving `SimulationSession` does not include broker submission fields.
- Naming test scanning new domain modules for banned names.

### Stop Condition

Stop when the schemas compile/import and boundary tests pass. Do not add persistence or API routes in this task.

## Task 2. FeatureSpec and FeatureKey

### Goal

Implement the immutable feature identity layer. This is the foundation for every later Feature Engine consumer.

### Files to Create

- `backend/app/features/spec.py`
- `backend/app/features/key.py`
- `backend/app/features/__init__.py`
- `backend/tests/unit/features/test_feature_spec.py`
- `backend/tests/unit/features/test_feature_key.py`

### Files Not to Touch

- `backend/app/indicators/*`
- `backend/app/cerebro/*`
- `backend/app/core/backtest.py`
- `backend/app/services/*`
- `frontend/*`
- database or migration files

### Acceptance Criteria

- `FeatureSpec` is immutable.
- `FeatureSpec` supports: `kind`, `namespace`, `timeframe`, `source`, `params`, `lookback`, `shift`, `scope`, `version`.
- Supported timeframes are fixed to canonical values only: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`, `1mo`.
- `FeatureKey` is deterministic and includes feature version, scope, timeframe, namespace, kind, source, canonical params, lookback, and shift.
- `14` and `14.0` produce the same canonical param representation.
- Param ordering does not affect the key.
- Unsupported timeframe aliases such as `60m` are rejected, not silently normalized.

### Tests to Add

- `5m.close[0]` equivalent spec produces stable key.
- Param order does not change key.
- Integer/float equivalent params do not change key.
- Feature version change changes key.
- Invalid timeframe raises a precise validation error.
- Negative lookback is rejected.

### Stop Condition

Stop when feature identity is stable. Do not build parser, registry, planner, or computation here.

## Task 3. Feature Registry v1

### Goal

Create the single allowed feature vocabulary for phase 1. Registry entries define feature availability and validation metadata only; no computation implementation is required yet.

### Files to Create

- `backend/app/features/registry.py`
- `backend/tests/unit/features/test_feature_registry.py`

### Files Not to Touch

- `backend/app/indicators/*`
- `backend/app/cerebro/*`
- `backend/app/core/backtest.py`
- `backend/app/services/*`
- `frontend/*`
- migrations

### Acceptance Criteria

- Registry contains only the approved v1 feature set.
- Registry defines namespace, allowed timeframes, allowed params, default params, source requirements, warmup rule, consumer support, and mode support.
- Consumer support includes at minimum: `chart_lab`, `sim_replay`, `backtest`.
- Paper/live/streaming support may exist as metadata but must not be implemented in this phase.
- Unsupported features are rejected with precise errors.
- Unsupported params are rejected with precise errors.
- Default params are injected by registry metadata.
- Registry can output an AI/UX-safe feature catalog data structure without calling AI.

### Tests to Add

- Registry accepts `close`, `ema`, `rsi`, `atr`, `vwap`, `opening_range_high`, and `prior_day_high`.
- Registry rejects `supertrend` unless explicitly added later.
- Registry rejects invalid param names such as `period` for `ema` when only `length` is allowed.
- Registry injects default params consistently.
- Registry reports consumer support correctly for Chart Lab and Sim Lab replay.

### Stop Condition

Stop when registry validation and catalog export work. Do not compute feature values yet.

## Task 4. Feature Reference Parser

### Goal

Parse canonical feature syntax into `FeatureSpec` using the registry. The parser is the only accepted input path for string feature references.

### Files to Create

- `backend/app/features/parser.py`
- `backend/tests/unit/features/test_feature_parser.py`

### Files Not to Touch

- `backend/app/indicators/*`
- `backend/app/cerebro/*`
- `backend/app/core/backtest.py`
- `backend/app/api/routes/*`
- `frontend/*`
- migrations

### Acceptance Criteria

- Parser supports:
  - `5m.close[0]`
  - `5m.close`
  - `5m.close[1]`
  - `1d.high[0]`
  - `15m.opening_range_high:session=regular,window_minutes=15`
  - `5m.ema:length=20[0]`
  - `1h.rsi:length=14[0]`
- Omitted lookback defaults to `[0]`.
- Parser uses registry defaults and validation.
- Parser rejects unsupported features.
- Parser rejects unsupported params.
- Parser rejects future/negative lookbacks.
- Parser rejects current-forming-bar syntax.
- Parser rejects timeframe aliases such as `60m`.

### Tests to Add

- Parse each accepted syntax example into the expected `FeatureSpec`.
- `5m.close` equals `5m.close[0]`.
- `60m.close[0]` fails.
- `5m.ema:period=20[0]` fails.
- `5m.close[-1]` fails.
- `5m.foo[0]` fails.

### Stop Condition

Stop when parser produces registry-validated `FeatureSpec` objects. Do not build planner or engine behavior here.

## Task 5. Feature Planner Contract

### Goal

Build the backend planner that resolves feature requirements for a `ProgramVersion` and consumer. It validates feature support, deduplicates specs, resolves timeframes, and calculates warmup requirements.

### Files to Create

- `backend/app/features/planner.py`
- `backend/app/features/provenance.py`
- `backend/tests/unit/features/test_feature_planner.py`

### Files Not to Touch

- `backend/app/services/*`
- `backend/app/api/routes/*`
- `backend/app/core/backtest.py`
- `backend/app/indicators/*`
- `backend/app/cerebro/*`
- `frontend/*`
- migrations

### Acceptance Criteria

- Planner accepts a `ProgramVersion` plus consumer name such as `chart_lab` or `sim_replay`.
- Planner collects feature references from Strategy and any component preview requirements.
- Planner deduplicates identical FeatureKeys.
- Planner rejects features unsupported for the requested consumer.
- Planner returns explicit unsupported-feature errors and does not partially pass.
- Planner returns required symbols/timeframes from the Program's UniverseSnapshot.
- Planner returns warmup requirements by timeframe.
- Planner identifies multi-timeframe requirements explicitly.
- Planner output is immutable enough to be stored as evidence later.

### Tests to Add

- Valid Program with `5m.close[0]` and `5m.ema:length=20[0]` produces a plan.
- Duplicate feature references produce one FeatureKey.
- Program requiring unsupported feature fails planning.
- Program requiring unsupported consumer feature fails planning.
- Multi-timeframe Program using `5m.close[0]` and `1d.high[0]` produces both timeframes.
- Warmup requirement for `ema:length=20` exceeds price-only warmup.

### Stop Condition

Stop when the planner can validate Chart Lab and Sim Lab replay requirements. Do not add data fetching or feature computation.

## Task 6. FeatureFrame and FeatureSnapshot Contract

### Goal

Define the data contracts that later Feature Engine implementations, Signal Engine, Chart Lab, and Sim Lab will share. This task creates contracts only, not computation.

### Files to Create

- `backend/app/features/frames.py`
- `backend/tests/unit/features/test_feature_snapshot_contract.py`

### Files Not to Touch

- `backend/app/indicators/*`
- `backend/app/cerebro/*`
- `backend/app/services/*`
- `backend/app/api/routes/*`
- `frontend/*`
- migrations

### Acceptance Criteria

- `FeatureSnapshot` includes timestamp, symbol, base timeframe, feature values, availability flags, warm state, alignment info, and provenance refs.
- Availability can represent at least: `available`, `warmup`, `missing`, `unsupported`, `stale`.
- Higher-timeframe alignment info can show source timeframe and source timestamp for each aligned feature.
- Snapshot contract does not expose raw provider messages.
- Snapshot contract is sufficient for Signal Engine without raw bars.

### Tests to Add

- Snapshot can represent available feature value.
- Snapshot can represent warmup/unavailable value without coercing to false.
- Snapshot can represent `1h` source timestamp on a `5m` decision timestamp.
- Signal-facing snapshot fixture contains no raw OHLCV dependency beyond registered feature values.

### Stop Condition

Stop when downstream code can type against the snapshot contract. Do not implement calculation.

## Task 7. Signal Engine Core

### Goal

Implement the deterministic Signal Engine contract. It consumes `FeatureSnapshot` and a Strategy signal definition, then emits `CandidateTradeIntent` or a no-signal diagnostic. It must not size, approve, build, or submit orders.

### Files to Create

- `backend/app/decision/signal_engine.py`
- `backend/app/decision/__init__.py`
- `backend/tests/unit/decision/test_signal_engine.py`

### Files Not to Touch

- `backend/app/services/*`
- `backend/app/broker/*`
- `backend/app/api/routes/*`
- `backend/app/indicators/*`
- `frontend/*`
- migrations

### Acceptance Criteria

- Signal Engine reads only `FeatureSnapshot`.
- Signal Engine supports basic condition comparisons for phase 1: greater than, less than, greater/equal, less/equal, equals, crosses above, crosses below if required by Strategy schema.
- Signal Engine returns condition truth diagnostics for every node.
- Signal Engine emits `CandidateTradeIntent` for passing entry/exit logic.
- Signal Engine emits no-signal diagnostics when conditions fail.
- Signal Engine returns feature-unavailable diagnostics when required features are unavailable.
- Signal Engine does not call Feature Engine, Alpaca, broker code, risk code, controls code, or execution code.
- `CandidateTradeIntent` contains symbol, timestamp, side, intent type, signal name, feature values used, stop candidate, target candidate, and diagnostics.

### Tests to Add

- Passing condition emits `CandidateTradeIntent`.
- Failing condition emits no-signal diagnostic.
- Missing/warmup feature blocks signal and reports feature unavailable.
- Nested conditions report node-level truth.
- Signal Engine does not mutate input snapshot.
- Signal Engine output contains no quantity, order type, broker account, or approval status.

### Stop Condition

Stop when Signal Engine can support Chart Lab condition truth and Sim Lab replay entry candidate generation. Do not implement controls, risk, or execution here.

## Task 8. Chart Lab Backend Preview Contract

### Goal

Create backend-only Chart Lab preview services and route contracts that validate signal and component previews without orders, fills, positions, PnL, or account evolution.

### Files to Create

- `backend/app/chart_lab/session_service.py`
- `backend/app/chart_lab/preview_service.py`
- `backend/app/chart_lab/evidence_export.py`
- `backend/app/chart_lab/__init__.py`
- `backend/app/api/routes/chart_lab.py`
- `backend/tests/unit/chart_lab/test_chart_lab_preview_contract.py`
- `backend/tests/integration/chart_lab/test_chart_lab_routes_contract.py`

### Files Not to Touch

- `frontend/*`
- `backend/app/broker/*`
- `backend/app/services/alpaca*`
- `backend/app/simulation/*`
- database or migration files
- old chart page files

### Acceptance Criteria

- Chart Lab session can be created from Strategy Preview or Program Preview input contracts.
- Session creation calls Feature Planner for `chart_lab`.
- Snapshot preview accepts a provided or fixture `FeatureSnapshot`.
- Condition truth comes from Signal Engine.
- Component preview can return placeholder-shaped contracts for controls/risk/execution/governor previews, but must stop before order creation.
- Chart Lab responses contain no simulated orders, fills, positions, PnL, equity curve, drawdown, broker account state, or Alpaca fields.
- Evidence export includes chart context, FeatureSnapshot refs, condition truth, component preview results, and provenance refs only.

### Tests to Add

- Chart Lab route contract rejects unsupported feature plan.
- Chart Lab condition truth matches Signal Engine output.
- Chart Lab response schema contains no forbidden execution fields.
- Program Preview includes component preview sections.
- Strategy Preview excludes risk, execution, and governor preview sections.
- Evidence export contains no PnL/fill/order/position data.

### Stop Condition

Stop when backend Chart Lab contracts are stable and boundary tests pass. Do not build UI or feature computation.

## Task 9. Sim Lab Historical Replay Contract

### Goal

Create backend-only Sim Lab historical replay contracts and event model. This task defines replay orchestration around FeatureSnapshots and Signal Engine, with simulated execution contracts stubbed but not broker-integrated.

### Files to Create

- `backend/app/simulation/engine.py`
- `backend/app/simulation/event_log.py`
- `backend/app/simulation/fill_models.py`
- `backend/app/simulation/simulated_broker.py`
- `backend/app/simulation/metrics.py`
- `backend/app/simulation/__init__.py`
- `backend/app/api/routes/sim_lab.py`
- `backend/tests/unit/simulation/test_sim_replay_contract.py`
- `backend/tests/integration/simulation/test_sim_lab_routes_contract.py`

### Files Not to Touch

- `frontend/*`
- `backend/app/broker/*`
- `backend/app/services/alpaca*`
- `backend/app/market_data/adapters/*`
- database or migration files
- old simulation page files

### Acceptance Criteria

- Sim Lab session supports `historical_replay` mode only in phase 1.
- Session creation calls Feature Planner for `sim_replay`.
- Replay engine consumes ordered FeatureSnapshots.
- Replay engine calls Signal Engine and records candidate/no-signal events.
- Event log supports at minimum: `feature_unavailable`, `signal_candidate`, `signal_blocked`, `order_created`, `order_filled`, `position_opened`, `position_closed`.
- Simulated broker contracts exist, but no Alpaca or real broker dependency exists.
- Sim Lab API response labels all execution as simulated.
- Sim Lab has no live stream mode implementation in this phase.
- Sim Lab never imports or calls Alpaca adapters.

### Tests to Add

- Historical replay rejects invalid FeaturePlan.
- Replay over same FeatureSnapshots produces deterministic event order.
- Passing signal creates a simulated event chain using simulated contracts.
- Feature unavailable snapshot records `feature_unavailable` and does not create entry.
- Sim Lab imports do not depend on Alpaca or real broker modules.
- Sim Lab route response never includes real broker ids.

### Stop Condition

Stop when historical replay can consume FeatureSnapshots and produce deterministic simulated event logs. Do not add live stream, real broker integration, or frontend.

## Task 10. Phase 1 Boundary and Parity Test Harness

### Goal

Add cross-module tests that prove the phase 1 contracts are aligned and that forbidden architecture paths are absent.

### Files to Create

- `backend/tests/acceptance/test_phase1_architecture_boundaries.py`
- `backend/tests/parity/test_chart_sim_signal_parity.py`
- `backend/tests/fixtures/programs.py`
- `backend/tests/fixtures/features.py`
- `backend/tests/fixtures/snapshots.py`

### Files Not to Touch

- `frontend/*`
- `backend/app/services/alpaca*`
- `backend/app/broker/*`
- database or migration files
- old repo files

### Acceptance Criteria

- Same Program, symbol, timestamp, and FeatureSnapshot produce the same Signal Engine result in Chart Lab and Sim Lab.
- Chart Lab stops before order/fill/position/PnL.
- Sim Lab uses simulated execution contracts only.
- No phase 1 module imports Alpaca.
- No phase 1 module imports old indicator computation directly.
- Feature references in fixtures must pass parser and registry validation.
- Program fixture contains references only.
- Unsupported feature fixture fails before Signal Engine runs.

### Tests to Add

- Chart Lab and Sim Lab signal parity test.
- Architecture import scan blocking Alpaca imports in Feature, Decision, Chart Lab, and Simulation phase 1 modules.
- Architecture import scan blocking `backend/app/indicators` and `backend/app/cerebro` usage in new modules.
- Program boundary fixture test.
- Unsupported feature blocks planning before replay/preview.

### Stop Condition

Stop when phase 1 has a clean backend contract baseline and all boundary/parity tests pass. The next phase may begin only after this task is green.
