# Implementation Log

## 2026-04-24 - Task 1 Backend Domain Schema Skeletons

Implemented Task 1 from `docs/system_rebuild_outputs/09_engineering_task_breakdown.md`.

Created backend domain schemas as Pydantic-only contracts under `backend/app/domain/`:

- `strategy.py`
- `strategy_controls.py`
- `risk_profile.py`
- `execution_style.py`
- `universe.py`
- `program.py`
- `chart_lab.py`
- `simulation.py`
- `validation.py`
- `_base.py`
- `__init__.py`

Added targeted boundary tests:

- `backend/tests/unit/domain/test_domain_boundaries.py`

Scope kept out:

- No database models
- No API routes
- No Alpaca
- No frontend
- No migrations

Validation performed:

- `python -m compileall backend\app\domain`
- `python -m compileall backend\app\domain backend\tests\unit\domain`

Blocked validation:

- `python -m pytest backend\tests\unit\domain\test_domain_boundaries.py` could not run in the current environment because `pytest` is not installed.
- A direct dependency check also showed `pydantic` is not installed in the current Python environment.

## 2026-04-24 - Task 2 FeatureSpec / FeatureKey / FeatureRegistry v1

Implemented the feature identity and initial registry foundation from `docs/system_rebuild_outputs/09_engineering_task_breakdown.md`, including the user-requested registry v1 scope.

Created:

- `backend/app/features/__init__.py`
- `backend/app/features/spec.py`
- `backend/app/features/key.py`
- `backend/app/features/registry.py`
- `backend/tests/unit/features/test_feature_spec.py`
- `backend/tests/unit/features/test_feature_key.py`
- `backend/tests/unit/features/test_feature_registry.py`

Implemented:

- Immutable `FeatureSpec`
- Canonical timeframe validation
- Rejection of aliases such as `60m`
- Deterministic `FeatureKey`
- Canonical parameter ordering
- Integer/float equivalence for params such as `14` and `14.0`
- `FeatureRegistry` v1 with only approved initial features
- Unsupported feature rejection
- Unsupported parameter rejection
- Registry metadata catalog export

Scope kept out:

- No FeaturePlanner
- No FeatureEngine
- No API routes
- No frontend
- No Alpaca
- No database models or migrations

Validation performed:

- `python -m compileall backend\app\features backend\tests\unit\features`
- `python -m pytest backend\tests\unit\features`

Result:

- `50 passed`

## 2026-04-24 - Feature Identity Regression Tests

Added focused unit tests for the required feature identity contracts.

Created:

- `backend/tests/unit/features/test_feature_identity_contract.py`

Coverage added:

- FeatureKey determinism
- Invalid feature rejection
- Timeframe alias rejection for values like `60m`, `5min`, `day`, and `1D`

Validation performed:

- `python -m compileall backend\app\features backend\tests\unit\features`
- `python -m pytest backend\tests\unit\features`

Result:

- `56 passed`

## 2026-04-24 - Feature Expression Parser

Implemented canonical feature expression parsing into registry-validated `FeatureSpec` objects.

Created:

- `backend/app/features/parser.py`
- `backend/tests/unit/features/test_feature_parser.py`

Updated:

- `backend/app/features/__init__.py`

Implemented:

- Parsing for `5m.close[0]`
- Parsing for `5m.close[1]`
- Parsing for `1d.high[0]`
- Parsing for `5m.close` as equivalent to `5m.close[0]`
- Parsing for `5m.ema:length=20[0]`
- Parsing for `15m.opening_range_high:session=regular,window_minutes=15`
- Param parsing for strings, ints, floats, and booleans
- Strict canonical syntax rejection
- Unsupported feature rejection through the registry
- Invalid param rejection through the registry
- Invalid timeframe and alias rejection

Scope kept out:

- No FeaturePlanner
- No FeatureEngine
- No API routes
- No frontend
- No Alpaca
- No computation

Validation performed:

- `python -m compileall backend\app\features backend\tests\unit\features`
- `python -m pytest backend\tests\unit\features`

Result:

- `82 passed`

## 2026-04-24 - FeaturePlanner Contract

Implemented backend-only FeaturePlanner contract for resolved `ProgramVersion` components.

Created:

- `backend/app/features/planner.py`
- `backend/tests/unit/features/test_feature_planner.py`

Updated:

- `backend/app/features/__init__.py`
- `backend/app/domain/strategy_controls.py`
- `backend/app/domain/risk_profile.py`
- `backend/app/domain/execution_style.py`

Implemented:

- `ResolvedProgramComponents` wrapper around reference-only `ProgramVersion`
- Component reference validation against `ProgramVersion`
- Feature collection from Strategy, Strategy Controls, Risk Profile, and Execution Style
- Condition tree feature extraction from Strategy rules
- Feature parsing into `FeatureSpec`
- Registry validation for all feature refs
- Consumer support validation
- Deduplication by `FeatureKey`
- Symbol extraction from `UniverseSnapshot`
- Multi-timeframe extraction
- Warmup bars by timeframe
- All-or-nothing failure via `FeaturePlanError`

Scope kept out:

- No FeatureEngine
- No computation
- No API routes
- No frontend
- No Alpaca
- No database models or migrations

Validation performed:

- `python -m compileall backend\app\domain backend\app\features backend\tests\unit\features`
- `python -m pytest backend\tests\unit\features backend\tests\unit\domain`

Result:

- `119 passed`

## 2026-04-24 - Batch Feature Engine Skeleton

Implemented backend-only batch/replay Feature Engine skeleton.

Created:

- `backend/app/features/frames.py`
- `backend/app/features/batch.py`
- `backend/tests/unit/features/test_batch_feature_engine.py`

Updated:

- `backend/app/features/__init__.py`

Implemented:

- `NormalizedBar`
- `FeatureValue`
- `FeatureSnapshot`
- `FeatureFrame`
- `FeatureFrameSet`
- `BatchFeatureEngine`
- Batch passthrough computation for `open`, `high`, `low`, `close`, `volume`
- Batch `sma`
- Batch deterministic recursive `ema`
- Batch `highest`
- Batch `lowest`
- Warmup availability marking
- Lookback-safe indexing
- Unsupported batch feature failure for registry features not implemented in this skeleton

Scope kept out:

- No streaming
- No Alpaca
- No API routes
- No frontend
- No unsupported indicators
- No planner changes
- No database models or migrations

Validation performed:

- `python -m compileall backend\app\features backend\tests\unit\features`
- `python -m pytest backend\tests\unit\features`

Result:

- `94 passed`

## 2026-04-24 - Signal Engine Skeleton

Implemented deterministic Signal Engine skeleton.

Created:

- `backend/app/decision/__init__.py`
- `backend/app/decision/signal_engine.py`
- `backend/tests/unit/decision/test_signal_engine.py`

Updated:

- `backend/app/domain/strategy.py`
- `backend/app/domain/__init__.py`

Implemented:

- `SignalEngine`
- `SignalEvaluation`
- `SignalEvaluationError`
- Snapshot-only condition evaluation
- `greater_than`
- `less_than`
- `crosses_above`
- `crosses_below`
- `and` / `or` condition groups
- Candidate intent emission
- No-intent false-condition result
- Diagnostics with feature values
- Missing/unavailable feature rejection

Scope kept out:

- No feature computation
- No risk sizing
- No execution style handling
- No broker integration
- No API routes
- No frontend
- No Alpaca

Validation performed:

- `python -m compileall backend\app\decision backend\app\domain backend\tests\unit\decision`
- `python -m pytest backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain`

Result:

- `132 passed`

## 2026-04-24 - Chart Lab Backend Preview Contract

Implemented backend-only Chart Lab preview service contract.

Created:

- `backend/app/chart_lab/__init__.py`
- `backend/app/chart_lab/preview_service.py`
- `backend/tests/unit/chart_lab/test_chart_lab_preview_service.py`

Implemented:

- `ChartLabPreviewService`
- `ChartLabPreviewResponse`
- `ChartLabBarPreview`
- `ChartLabFeatureValue`
- `ChartLabSignalMarker`
- Program preview flow using `FeaturePlanner`
- Batch Feature Engine invocation for feature snapshots
- Higher-timeframe snapshot alignment into base timeframe previews
- Signal Engine evaluation from aligned `FeatureSnapshot`
- Condition truth diagnostics passthrough
- Non-fire reasons
- Signal markers
- Feature value exposure with source timeframe and source timestamp

Scope kept out:

- No API routes
- No frontend
- No fills
- No orders
- No positions
- No PnL
- No broker integration
- No Alpaca
- No feature computation outside `BatchFeatureEngine`

Validation performed:

- `python -m compileall backend\app\chart_lab backend\tests\unit\chart_lab`
- `python -m pytest backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain`

Result:

- `138 passed`

## 2026-04-24 - Sim Lab Historical Replay Engine

Implemented backend-only deterministic Sim Lab historical replay.

Created:

- `backend/app/simulation/__init__.py`
- `backend/app/simulation/models.py`
- `backend/app/simulation/historical_replay.py`
- `backend/tests/unit/simulation/test_historical_replay_engine.py`

Updated:

- `backend/app/simulation/engine.py`

Implemented:

- `SimulationReplayResult`
- simulated order lifecycle models
- simulated fills
- simulated position ledger
- simulated trade ledger
- simulated event log
- deterministic `HistoricalReplayEngine`
- integration with `FeaturePlanner`
- integration with `BatchFeatureEngine`
- integration with `SignalEngine`
- fixed-share, fixed-dollar, and risk-percent sizing paths
- market open order creation
- deterministic fill handling
- deterministic partial-fill handling
- protective stop orders
- protective target orders
- trailing stop updates
- realized PnL
- unrealized PnL
- equity curve
- max drawdown
- gross exposure

Scope kept out:

- No Alpaca
- No streaming
- No external services
- No API routes
- No frontend
- No database models or migrations
- No feature computation outside `BatchFeatureEngine`

Validation performed:

- `python -m compileall -q backend\app\simulation backend\tests\unit\simulation`
- `python -m pytest backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`

Result:

- `146 passed`

## 2026-04-24 - Incremental / Streaming Feature Engine

Implemented backend-only incremental Feature Engine support for live-style completed bar updates.

Created:

- `backend/app/features/incremental.py`
- `backend/tests/unit/features/test_incremental_feature_engine.py`

Updated:

- `backend/app/features/__init__.py`

Implemented:

- `FeatureCache`
- `IncrementalFeatureEngine`
- `IncrementalFeatureUpdate`
- `IncrementalFeatureEngineError`
- rolling per-symbol/per-timeframe state
- strict increasing timestamp validation for completed bars
- incremental passthrough updates for `open`, `high`, `low`, `close`, `volume`
- incremental `sma`
- incremental deterministic `ema`
- incremental `highest`
- incremental `lowest`
- feature-key/state reuse from `FeatureSpec`, `FeatureKey`, and `FeatureRegistry`
- warmup behavior matching batch mode
- latest-snapshot lookup for multi-timeframe alignment
- no-lookahead lookback handling

Scope kept out:

- No Alpaca
- No websocket layer
- No API routes
- No frontend
- No database models or migrations
- No unsupported indicators
- No full-history recomputation on incremental updates

Validation performed:

- `python -m pytest backend\tests\unit\features\test_incremental_feature_engine.py -q`
- `python -m pytest backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\features backend\tests\unit\features`

Result:

- Incremental feature tests: `6 passed`
- Targeted backend unit slice: `152 passed`

## 2026-04-24 - Internal Streaming Runtime Engine

Implemented backend-only internal runtime decision loop with simulated bar input.

Created:

- `backend/app/runtime/__init__.py`
- `backend/app/runtime/models.py`
- `backend/app/runtime/engine.py`
- `backend/tests/unit/runtime/test_runtime_engine.py`

Updated:

- `backend/app/features/registry.py`

Implemented:

- `DeploymentContext`
- `RuntimeState`
- `RuntimeStateStore`
- `RuntimeEvent`
- `RuntimeEventLog`
- `ExecutionIntent`
- `ExecutionIntentBuilder`
- minimal `PortfolioGovernor`
- `RuntimeEngine`
- bar-by-bar runtime processing
- per-symbol/per-timeframe incremental feature updates
- multi-symbol runtime handling
- runtime feature planning using the canonical registry
- aligned runtime `FeatureSnapshot` construction from `FeatureCache`
- Signal Engine evaluation in streaming mode
- Strategy Controls session blocking
- Risk Profile sizing for execution intents
- Execution Style order-shape projection
- Governor allow/block stamping on execution intents
- runtime decision events for bars, features, signals, execution intents, and state updates

Scope kept out:

- No Alpaca
- No websocket layer
- No broker calls
- No order submission
- No fills
- No position tracking
- No Sim Lab fill simulation
- No API routes
- No frontend
- No database models or migrations
- No full-history recomputation

Validation performed:

- `python -m pytest backend\tests\unit\runtime -q`
- `python -m pytest backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\runtime backend\tests\unit\runtime backend\app\features`

Result:

- Runtime tests: `6 passed`
- Targeted backend unit slice: `158 passed`

## 2026-04-24 - Order Manager and Internal Order Ledger Foundation

Implemented internal order lifecycle foundation before broker integration.

Created:

- `backend/app/orders/__init__.py`
- `backend/app/orders/models.py`
- `backend/app/orders/ledger.py`
- `backend/app/orders/manager.py`
- `backend/tests/unit/orders/test_order_manager.py`

Implemented:

- `InternalOrder`
- `InternalOrderIntent`
- `InternalOrderStatus`
- `OrderManager`
- `OrderLedger`
- `OrderManagerError`
- internal order creation from `ExecutionIntent`
- required attribution fields: account, deployment, program, symbol, side, quantity, order type, intent, status, created timestamp
- deterministic `client_order_id` format: `utos-{acct8}-{dep8}-{prog8}-{intent}-{seq}`
- invalid order intent rejection
- internal status updates
- in-memory lookup by account
- in-memory lookup by deployment
- in-memory lookup by program

Scope kept out:

- No Alpaca
- No broker adapter
- No broker submission
- No API routes
- No frontend
- No database models or migrations
- No external calls

Validation performed:

- `python -m pytest backend\tests\unit\orders -q`
- `python -m pytest backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\orders backend\tests\unit\orders`

Result:

- Order tests: `8 passed`
- Targeted backend unit slice: `166 passed`

## 2026-04-24 - Broker Adapter Boundary

Implemented broker adapter boundary and fake broker adapter foundation.

Created:

- `backend/app/brokers/__init__.py`
- `backend/app/brokers/adapter.py`
- `backend/app/brokers/models.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/sync.py`
- `backend/tests/unit/brokers/test_broker_adapter_boundary.py`

Updated:

- `backend/app/orders/models.py`

Implemented:

- `BrokerAdapter` protocol
- `BrokerOrderResult`
- `BrokerOrderStatus`
- `BrokerAdapterError`
- `FakeBrokerAdapter`
- `BrokerSync`
- adapter boundary that receives already-created `InternalOrder` objects only
- fake accepted/rejected/partial-fill/filled outcomes
- ledger status updates from broker results
- internal filled quantity updates
- broker result client-order-id validation
- attribution preservation through broker sync

Scope kept out:

- No real Alpaca calls
- No broker API client
- No API routes
- No frontend
- No database models or migrations
- No order creation inside broker adapter

Validation performed:

- `python -m pytest backend\tests\unit\brokers -q`
- `python -m pytest backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\brokers backend\tests\unit\brokers backend\app\orders backend\tests\unit\orders`

Result:

- Broker tests: `8 passed`
- Targeted backend unit slice: `174 passed`

## 2026-04-24 - Portfolio Governor Foundation

Implemented the Portfolio Governor as the final internal approval gate before internal order creation.

Created:

- `backend/app/governor/__init__.py`
- `backend/app/governor/models.py`
- `backend/app/governor/service.py`
- `backend/tests/unit/governor/test_portfolio_governor.py`

Updated:

- `backend/app/runtime/engine.py`
- `backend/app/runtime/__init__.py`
- `backend/app/orders/manager.py`

Implemented:

- `PortfolioGovernor`
- `GovernorPolicy`
- `GovernorRequest`
- `GovernorDecision`
- `BrokerSyncFreshness`
- `PortfolioSnapshot`
- `PositionSummary`
- global kill blocking new opens
- account pause blocking new opens for the paused account only
- deployment pause blocking new opens for the paused deployment only
- stale broker sync blocking new opens
- max open positions blocking new opens
- symbol concentration placeholder projected state
- protective close / take-profit / stop-loss approval during pause or kill
- runtime integration with the Governor package
- OrderManager rejection of unapproved execution intents

Scope kept out:

- No Alpaca
- No broker API client
- No API routes
- No frontend
- No database models or migrations
- No BrokerAccount policy ownership

Validation performed:

- `python -m pytest backend\tests\unit\governor -q`
- `python -m pytest backend\tests\unit\governor backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\governor backend\tests\unit\governor backend\app\runtime backend\app\orders`

Result:

- Governor tests: `9 passed`
- Targeted backend unit slice: `183 passed`

## 2026-04-24 - Execution Pipeline Integration

Implemented deterministic internal execution pipeline with no real broker integration.

Created:

- `backend/app/pipeline/__init__.py`
- `backend/app/pipeline/models.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`

Implemented:

- `RuntimeOrchestrator`
- `StrategyControlsGate`
- `RuntimePipelineEventLog`
- `PipelineEvent`
- `PipelineEventType`
- `PipelineResult`
- end-to-end internal chain:
  - incremental Feature Engine
  - Signal Engine
  - Strategy Controls gate
  - Risk sizing through `ExecutionIntentBuilder`
  - Execution Intent creation
  - Portfolio Governor decision
  - OrderManager internal order creation
  - FakeBrokerAdapter result
  - BrokerSync ledger update
- debug events for candidate trade intents, execution intents, governor decisions, order creation, broker results, and ledger updates
- protective close/tp/sl path through Governor under pause/kill

Scope kept out:

- No Alpaca
- No real broker API client
- No API routes
- No frontend
- No database models or migrations
- No feature computation outside Feature Engine
- No direct internal order creation outside OrderManager

Validation performed:

- `python -m pytest backend\tests\unit\pipeline -q`
- `python -m pytest backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\pipeline backend\tests\unit\pipeline`

Result:

- Pipeline tests: `8 passed`
- Targeted backend unit slice: `191 passed`

## 2026-04-24 - Broker Interface Expansion Before Alpaca

Expanded broker boundary interfaces for Alpaca readiness without adding Alpaca SDK, credentials, network calls, API routes, or frontend.

Created:

- `backend/tests/unit/brokers/test_broker_interface_expansion.py`

Updated:

- `backend/app/brokers/models.py`
- `backend/app/brokers/adapter.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/sync.py`
- `backend/app/brokers/__init__.py`

Implemented:

- expanded `BrokerOrderResult`
- `BrokerAccountSnapshot`
- `BrokerPositionSnapshot`
- `BrokerOrderMapping`
- `BrokerAccountMode`
- `BrokerPositionSide`
- expanded `BrokerAdapter` protocol:
  - `submit_order(order)`
  - `get_order(order)`
  - `list_open_orders(account_id)`
  - `get_account_snapshot(account_id)`
  - `get_positions(account_id)`
- expanded `FakeBrokerAdapter` protocol support
- `BrokerSync.sync_open_orders(account_id)`
- `BrokerSync.sync_positions(account_id)`
- `BrokerSync.sync_account(account_id)`
- broker status preservation without raw SDK payload storage
- broker order mapping separate from `InternalOrder`

Scope kept out:

- No Alpaca SDK
- No Alpaca imports
- No credentials
- No network calls
- No API routes
- No frontend
- No internal order creation inside broker adapter
- No Governor logic changes
- No Feature Engine changes

Validation performed:

- `python -m pytest backend\tests\unit\brokers -q`
- `python -m pytest backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\brokers backend\tests\unit\brokers`

Result:

- Broker tests: `16 passed`
- Targeted backend unit slice: `200 passed`

## 2026-04-24 - Alpaca Broker Adapter Skeleton

Implemented Alpaca broker adapter skeleton without Alpaca SDK, credentials, network calls, API routes, or frontend.

Created:

- `backend/app/brokers/alpaca.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`

Updated:

- `backend/app/brokers/adapter.py`
- `backend/app/brokers/__init__.py`
- `backend/app/orders/models.py`

Implemented:

- `AlpacaBrokerAdapter`
- `AlpacaBrokerCapabilities`
- `AlpacaBrokerError`
- `AlpacaBrokerErrorDetails`
- runtime-checkable `BrokerAdapter` protocol
- internal order to Alpaca request-shape translation
- market order translation
- limit order translation
- unsupported order type controlled rejection
- Alpaca status normalization
- unknown status controlled failure
- Alpaca order response shape to `BrokerOrderResult`
- Alpaca account response shape to `BrokerAccountSnapshot`
- Alpaca position response shape to `BrokerPositionSnapshot`
- optional internal order price/linkage fields for future limit/protective order translation

Scope kept out:

- No Alpaca SDK
- No credentials
- No network calls
- No real submit/cancel behavior
- No API routes
- No frontend
- No OrderManager changes
- No Governor changes
- No Feature Engine changes
- No Signal Engine changes

Validation performed:

- `python -m pytest backend\tests\unit\brokers -q`
- `python -m pytest backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\brokers backend\tests\unit\brokers backend\app\orders`

Result:

- Broker tests: `28 passed`
- Targeted backend unit slice: `212 passed`

## 2026-04-24 - Real Alpaca Adapter Paper-Only Execution

Wired `AlpacaBrokerAdapter` to the `alpaca-py` SDK boundary for paper-only market order execution while keeping tests mocked and network-free.

Updated:

- `backend/app/brokers/alpaca.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`

Implemented:

- dotenv credential loading for:
  - `ALPACA_API_KEY`
  - `ALPACA_SECRET_KEY`
  - `ALPACA_BASE_URL`
- paper-only `TradingClient` construction
- real `submit_order(order)` path using SDK request objects when a configured client exists
- `get_order(order)` by `client_order_id`
- `list_open_orders(account_id)`
- `get_account_snapshot(account_id)`
- `get_positions(account_id)`
- internal order to Alpaca market request translation
- internal order to Alpaca limit request translation helper
- mocked SDK submission test path
- Alpaca order response normalization to `BrokerOrderResult`
- Alpaca account response normalization to `BrokerAccountSnapshot`
- Alpaca position response normalization to `BrokerPositionSnapshot`
- structured `AlpacaBrokerError` handling for auth, validation, insufficient buying power, and network-style failures

Scope kept out:

- No live trading
- No streaming
- No bracket/OCO/trailing orders
- No replace/cancel
- No API routes
- No frontend
- No OrderManager changes
- No PortfolioGovernor changes
- No Feature Engine changes
- No Signal Engine changes
- No internal order creation inside Alpaca adapter

Validation performed:

- `python -m pytest backend\tests\unit\brokers -q`
- `python -m pytest backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\brokers backend\tests\unit\brokers backend\app\orders`

Result:

- Broker tests: `29 passed`
- Targeted backend unit slice: `213 passed`

## 2026-04-24 - Paper Trading Operator Commands

Replaced manual paper-trading smoke scripts with guarded operator CLI commands.

Created:

- `tools/paper_order_smoke.py`
- `tools/check_alpaca_readiness.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- paper-only order smoke command
- readiness check command with no order submission
- `.env` loading
- `ALPACA_BASE_URL == https://paper-api.alpaca.markets` guard
- `CONFIRM_PAPER_ORDER=yes` guard for order submission
- default smoke symbol `SPY`
- default smoke quantity `1`
- hard block for smoke `qty > 1`
- approved test `ExecutionIntent` creation through Portfolio Governor decision
- order smoke path:
  - `OrderManager`
  - `AlpacaBrokerAdapter`
  - `BrokerSync`
  - `OrderLedger`
- readiness path:
  - account snapshot
  - positions
  - open orders
  - no order submission
- normalized JSON output for operator inspection

Scope kept out:

- No runtime loop
- No API routes
- No frontend
- No streaming
- No direct Alpaca calls outside `AlpacaBrokerAdapter`
- No OrderManager bypass
- No Governor approval bypass
- No multi-order execution

Validation performed:

- `python -m pytest backend\tests\unit\tools -q`
- `python -m pytest backend\tests\unit\tools backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\brokers backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\tests\unit\tools`

Result:

- Operator tool tests: `6 passed`
- Targeted backend unit slice: `219 passed`

## 2026-04-24 - Paper Smoke Market Clock Guard

Added a market-clock guard to the paper order smoke command.

Updated:

- `tools/paper_order_smoke.py`
- `backend/app/brokers/alpaca.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- `AlpacaBrokerAdapter.get_market_clock()`
- paper smoke command checks Alpaca market clock before order creation
- closed-market output: `Market closed. No order submitted.`
- closed-market path exits cleanly with no order submission
- `CONFIRM_PAPER_ORDER=yes` remains required
- market orders remain blocked outside regular market hours

Scope kept out:

- No runtime loop
- No API routes
- No frontend
- No streaming
- No direct Alpaca SDK imports in the smoke command
- No OrderManager bypass
- No Governor bypass

Validation performed:

- `python -m pytest backend\tests\unit\tools -q`
- `python -m pytest backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\app\brokers backend\tests\unit\tools`

Result:

- Operator tool tests: `7 passed`
- Targeted backend unit slice: `220 passed`

## 2026-04-24 - Paper Smoke Operator Output and Closed-Market Safety

Tightened the paper order smoke command so operator-visible status is explicit and flushed, and closed-market behavior is tested as a no-submit path.

Updated:

- `tools/paper_order_smoke.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- every smoke-command step prints with `flush=True`
- environment guard failures print with `flush=True`
- closed-market message prints with `flush=True`
- closed-market path exits `0`
- closed-market path does not create an internal order
- closed-market path does not submit through `AlpacaBrokerAdapter`
- closed-market path does not apply `BrokerSync`
- successful market-open path is pinned to:
  - `OrderManager.create_order`
  - `AlpacaBrokerAdapter.submit_order`
  - `BrokerSync.apply_result`
- confirmation and paper-only URL failures are pinned as no-submit paths

Scope kept out:

- No runtime loop
- No API routes
- No frontend
- No streaming
- No extended-hours trading
- No direct Alpaca calls outside `AlpacaBrokerAdapter`
- No OrderManager bypass
- No Governor bypass

Validation performed:

- `python -m pytest backend\tests\unit\tools -q`
- `python -m pytest backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\tests\unit\tools`

Result:

- Operator tool tests: `7 passed`
- Targeted backend unit slice: `220 passed`

## 2026-04-24 - Controlled Paper Runtime Execution

Added a guarded paper-only runtime operator command that runs a bounded, non-continuous runtime pass through the existing execution pipeline.

Created:

- `tools/run_paper_runtime.py`

Updated:

- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- paper-only runtime command
- `.env` loading
- `ALPACA_BASE_URL == https://paper-api.alpaca.markets` guard
- `CONFIRM_PAPER_RUNTIME=yes` guard
- market-clock block before runtime execution
- closed-market path exits cleanly with no broker submission
- one-symbol runtime pass
- configurable completed-bar count with default `5`
- hard block for `bars > 20`
- hard block for `qty > 1`
- generated completed bars for a controlled non-streaming pass
- paper Deployment context creation
- runtime path through:
  - `RuntimeOrchestrator`
  - `PortfolioGovernor`
  - `OrderManager`
  - `AlpacaBrokerAdapter`
  - `BrokerSync`
  - `OrderLedger`
- account and position sync through `BrokerSync`
- max one order per run
- JSON event output for operator inspection

Scope kept out:

- No continuous runtime loop
- No websocket streaming
- No API routes
- No frontend
- No extended-hours trading
- No direct Alpaca calls outside `AlpacaBrokerAdapter`
- No OrderManager bypass
- No Governor bypass
- No BrokerSync bypass

Validation performed:

- `python -m pytest backend\tests\unit\tools -q`
- `python -m pytest backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\tests\unit\tools`

Result:

- Operator tool tests: `12 passed`
- Targeted backend unit slice: `225 passed`

## 2026-04-24 - Alpaca Market Data Adapter + Streaming Skeleton

Added a market-data-only Alpaca adapter that feeds normalized completed bars into the existing runtime/Feature Engine path without touching order execution.

Created:

- `backend/app/market_data/__init__.py`
- `backend/app/market_data/alpaca.py`
- `backend/tests/unit/market_data/test_alpaca_market_data_adapter.py`
- `tools/stream_market_data_check.py`

Implemented:

- `AlpacaMarketDataAdapter`
- `MarketDataSubscription`
- `AlpacaMarketDataError`
- Alpaca bar payload normalization into `NormalizedBar`
- one-symbol / one-timeframe subscription contract
- default timeframe `1m`
- bounded bar collection with injected source support for tests
- Alpaca `StockDataStream` skeleton behind the market-data adapter only
- reconnect/error-handling placeholder through controlled stream stop and timeout failure
- `tools/stream_market_data_check.py` to:
  - load `.env`
  - connect through `AlpacaMarketDataAdapter`
  - subscribe to one symbol
  - print the first normalized bars, default `5`
  - exit cleanly
  - submit no orders

Scope kept out:

- No automatic order execution
- No continuous unattended trading
- No OrderManager imports in market data
- No BrokerAdapter imports in market data
- No broker/order submission from the stream tool
- No feature computation inside market data
- No runtime pipeline mutation

Validation performed:

- `python -m pytest backend\tests\unit\market_data -q`
- `python -m pytest backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\market_data backend\tests\unit\market_data tools`

Result:

- Market-data tests: `7 passed`
- Targeted backend unit slice: `232 passed`

## 2026-04-24 - Stream Market Data Closed-Market Guard

Fixed the market data stream check so a closed market is treated as an expected no-bar condition instead of a tool failure.

Updated:

- `tools/stream_market_data_check.py`
- `backend/tests/unit/market_data/test_alpaca_market_data_adapter.py`

Implemented:

- stream check calls the existing `AlpacaBrokerAdapter.get_market_clock()` before subscribing
- closed-market output: `Market closed. No bars expected.`
- closed-market path exits `0`
- closed-market path does not subscribe or collect bars
- stream tool still submits no orders
- stream tool still does not import or call `OrderManager`
- runtime pipeline unchanged
- broker adapter unchanged

Scope kept out:

- No order submission
- No broker adapter changes
- No runtime pipeline changes
- No continuous unattended trading
- No feature computation in market data

Validation performed:

- `python -m pytest backend\tests\unit\market_data -q`
- `python -m pytest backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\tests\unit\market_data`

Result:

- Market-data tests: `8 passed`
- Targeted backend unit slice: `233 passed`

## 2026-04-24 - Controlled Paper Runtime Dry Run

Added a dry-run-first paper runtime tool that consumes Alpaca market data bars and runs the runtime decision chain without submitting orders by default.

Created:

- `tools/run_paper_runtime_dry_run.py`

Updated:

- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- `.env` loading
- paper environment validation
- market clock check before market data subscription
- default dry-run mode
- explicit `--execute` mode
- `CONFIRM_PAPER_RUNTIME=yes` required only when `--execute` is passed
- one-symbol market data subscription, default `SPY`
- one-timeframe market data subscription, default `1m`
- max `5` normalized bars per run
- dry-run path through:
  - Alpaca market data adapter
  - Feature Engine via `RuntimeEngine`
  - Signal Engine
  - Strategy Controls
  - Risk sizing
  - Execution Intent Builder
  - Portfolio Governor
- execute path through:
  - `RuntimeOrchestrator`
  - `PortfolioGovernor`
  - `OrderManager`
  - `AlpacaBrokerAdapter`
  - `BrokerSync`
  - `OrderLedger`
- candidate decision output
- governor decision output
- max one order in execute mode
- closed-market path exits cleanly

Scope kept out:

- No frontend
- No API routes
- No unattended loop
- No streaming order execution
- No order submission in dry-run mode
- No direct order creation outside `OrderManager`
- No broker submission outside `AlpacaBrokerAdapter`
- No ledger update outside `BrokerSync`

Validation performed:

- `python -m pytest backend\tests\unit\tools -q`
- `python -m pytest backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\tests\unit\tools`

Result:

- Operator tool tests: `17 passed`
- Targeted backend unit slice: `238 passed`

## 2026-04-24 - BrokerSync Reconciliation

Added passive broker reconciliation for comparing the internal `OrderLedger` with broker truth without canceling or mutating unknown external orders.

Created:

- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`

Updated:

- `backend/app/brokers/models.py`
- `backend/app/brokers/sync.py`
- `backend/app/brokers/__init__.py`

Implemented:

- `BrokerReconciliationIssueType`
- `BrokerReconciliationIssue`
- `BrokerReconciliationReport`
- `BrokerSync.reconcile(account_id, ...)`
- known local order reconciliation through `adapter.get_order(order)`
- filled order reconciliation into `OrderLedger`
- rejected order reconciliation into `OrderLedger`
- missing local broker order flagging
- missing broker order flagging
- unknown external order intent preservation and flagging
- broker position mismatch detection
- broker account snapshot staleness detection
- passive report output with no cancellation behavior
- stale reconciliation report support for Governor stale-sync blocking

Scope kept out:

- No frontend
- No API routes
- No strategy changes
- No Feature Engine changes
- No automatic order cancellation
- No unknown external order mutation
- No Governor policy changes

Validation performed:

- `python -m pytest backend\tests\unit\brokers -q`
- `python -m pytest backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\brokers backend\tests\unit\brokers`

Result:

- Broker tests: `36 passed`
- Targeted backend unit slice: `245 passed`
