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

## 2026-04-24 - Alpaca Status Normalization Fix

Fixed `AlpacaBrokerAdapter.normalize_status()` so Alpaca SDK enum statuses normalize correctly instead of failing as unknown stringified enum names.

Updated:

- `backend/app/brokers/alpaca.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`

Implemented:

- status normalization accepts plain strings
- status normalization accepts SDK enum objects such as `OrderStatus.PENDING_NEW`
- status normalization accepts stringified enum names such as `OrderStatus.PENDING_NEW`
- status normalization extracts the final dotted token and lowercases it
- `pending_new`, `new`, `accepted`, and `done_for_day` map to internal accepted status
- `partially_filled`, `filled`, `canceled`, `expired`, `rejected`, `pending_cancel`, and `pending_replace` are supported
- unknown statuses still raise controlled `AlpacaBrokerError` with code `unknown_order_status`

Scope kept out:

- No OrderManager changes
- No Governor changes
- No pipeline ordering changes
- No broker submission behavior changes

Validation performed:

- `python -m pytest backend\tests\unit\brokers -q`
- `python -m pytest backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\brokers backend\tests\unit\brokers`

Result:

- Broker tests: `36 passed`
- Targeted backend unit slice: `245 passed`

## 2026-04-24 - Paper Runtime Dry-Run Confirmation Guard Ordering

Fixed the controlled paper runtime dry-run tool so execute-mode confirmation is validated before any market-clock check can produce a clean closed-market exit.

Updated:

- `tools/run_paper_runtime_dry_run.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- separated static paper environment validation from execute confirmation validation
- `CONFIRM_PAPER_RUNTIME=yes` is required when `--execute` is passed
- missing execute confirmation returns exit code `2`
- missing execute confirmation is checked before constructing `AlpacaBrokerAdapter`
- missing execute confirmation is checked before market clock access
- dry-run mode still does not require confirmation
- market closed still exits `0` only after safety guards pass

Scope kept out:

- No runtime pipeline changes
- No broker adapter changes
- No Governor changes
- No order path changes

Validation performed:

- `python -m pytest backend\tests\unit\tools -q`
- `python -m pytest backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q tools backend\tests\unit\tools`

Result:

- Operator tool tests: `18 passed`
- Targeted backend unit slice: `246 passed`

## 2026-04-24 - Persistence Layer for Orders, Trades, Broker Mappings, Governor State, and Deployment State

Added local SQLite persistence adapters for durable runtime state while preserving existing Pydantic domain models and execution behavior.

Created:

- `backend/app/persistence/__init__.py`
- `backend/app/persistence/sqlite.py`
- `backend/tests/unit/persistence/test_sqlite_persistence.py`

Implemented:

- `SQLiteOrderLedger`
- `SQLiteTradeLedger`
- `SQLiteBrokerOrderMappingStore`
- `SQLiteGovernorStateStore`
- `SQLiteDeploymentStateStore`
- SQLite schema initialization
- persistent order add/get/replace/update/status lookup behavior
- account/deployment/program order lookup behavior
- simulated trade persistence
- broker order mapping persistence
- Governor policy persistence
- deployment runtime state persistence
- restart-style tests using a fresh store instance over the same SQLite file

Notes:

- SQLModel and SQLAlchemy are not present in the repository or current environment.
- This implementation uses Python's standard `sqlite3` module to keep the local persistence layer dependency-free.

Scope kept out:

- No execution pipeline changes
- No Feature Engine changes
- No Signal Engine changes
- No API routes
- No frontend
- No database migrations

Validation performed:

- `python -m pytest backend\tests\unit\persistence -q`
- `python -m pytest backend\tests\unit\persistence backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\persistence backend\tests\unit\persistence`

Result:

- Persistence tests: `5 passed`
- Targeted backend unit slice: `251 passed`

## 2026-04-24 - Control Plane Hardening for Paper Runtime Safety

Added a hardened runtime control plane for kill, pause, deployment pause, and intent-aware cancellation safety before portfolio feature adapters are introduced.

Created:

- `backend/app/control_plane/__init__.py`
- `backend/app/control_plane/client_order_id.py`
- `backend/app/control_plane/service.py`
- `backend/tests/unit/control_plane/test_control_plane.py`

Updated:

- `backend/app/orders/manager.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/app/brokers/fake.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`

Implemented:

- `build_program_client_order_id(program_name, deployment_id, intent="open")`
- `parse_order_intent(client_order_id)`
- `parse_order_deployment_id(client_order_id)`
- new client order id format: `{program_abbrev}-{deployment8}-{intent}-{rand8}`
- legacy/unparseable client order ids return intent `unknown`
- `ControlPlane`
- startup hydration from:
  - latest `KillSwitchEvent`
  - `AccountControlState.is_killed`
  - `DeploymentControlState.status == "paused"`
- unified `can_open_new_position(account_id, deployment_id, symbol, side)` gate
- deprecated-compatible `can_trade(...)` alias
- global kill, account pause, and deployment pause precedence
- deployment-scoped pause/resume
- deployment pause does not use strategy id as scope
- intent-aware cancellation sweep
- structured `CancellationSweepResult`
- dry-run cancellation support
- unknown order intent skip-and-flag behavior
- protective `sl`, `tp`, `close`, and `scale` cancellation preservation
- open-intent cancellation only when no broker position exists
- deployment-scoped cancellation by deployment prefix parsed from client order id
- `RuntimeOrchestrator` final open gate through `ControlPlane.can_open_new_position`
- protective exits continue through existing Governor/OrderManager/BrokerSync path during kill/pause

Scope kept out:

- No Feature Engine changes
- No Signal Engine changes
- No Strategy Controls behavior changes
- No Risk behavior changes
- No portfolio feature adapters
- No live-trading behavior
- No flatten-on-pause/kill behavior
- No BrokerAdapter policy decisions
- No OrderManager bypass
- No PortfolioGovernor bypass

Validation performed:

- `python -m pytest backend\tests\unit\control_plane -q`
- `python -m pytest backend\tests\unit\orders backend\tests\unit\pipeline -q`
- `python -m pytest backend\tests\unit\control_plane backend\tests\unit\orders backend\tests\unit\pipeline -q`
- `python -m pytest backend\tests\unit\control_plane backend\tests\unit\persistence backend\tests\unit\market_data backend\tests\unit\tools backend\tests\unit\brokers backend\tests\unit\pipeline backend\tests\unit\governor backend\tests\unit\orders backend\tests\unit\runtime backend\tests\unit\simulation backend\tests\unit\chart_lab backend\tests\unit\decision backend\tests\unit\features backend\tests\unit\domain -q`
- `python -m compileall -q backend\app\control_plane backend\app\orders backend\app\pipeline backend\app\brokers backend\tests\unit\control_plane backend\tests\unit\orders backend\tests\unit\pipeline`

Result:

- Control-plane tests: `13 passed`
- Control/order/pipeline slice: `31 passed`
- Targeted backend unit slice: `266 passed`

## 2026-04-24 - Control Plane Hardening for Paper Runtime Safety

Closeout verification completed for the paper runtime control-plane hardening milestone.

Files created:

- `backend/app/control_plane/__init__.py`
- `backend/app/control_plane/client_order_id.py`
- `backend/app/control_plane/service.py`
- `backend/tests/unit/control_plane/test_control_plane.py`

Files modified:

- `backend/app/brokers/fake.py`
- `backend/app/orders/manager.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Exact scope verified:

- `client_order_id` intent encoding is present.
- `parse_order_intent()` is present and returns `unknown` for malformed or legacy ids.
- `parse_order_deployment_id()` is present.
- startup hydration covers global kill, killed accounts, and paused deployments.
- `can_open_new_position()` gates new opening orders.
- deployment-scoped pause/resume is implemented by deployment id, not strategy id.
- cancellation sweep is intent-aware.
- cancellation sweep returns structured `CancellationSweepResult`.
- runtime control action wiring calls the control-plane gate after PortfolioGovernor approval and before order creation.
- flatten remains separate from pause/kill.
- protective exits survive pause/kill.
- unknown intent orders are preserved and flagged.

Tests run:

- `python -m pytest backend/tests/unit/control_plane -q`
- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests/unit/orders -q`
- `python -m pytest backend/tests/unit/brokers -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Control-plane tests: `13 passed`
- Governor tests: `9 passed`
- Orders tests: `8 passed`
- Brokers tests: `36 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `266 passed`

Issues fixed during closeout:

- None. No task-related test failures were found during closeout.

Architecture confirmations:

- No core engines were modified: FeatureEngine, SignalEngine, StrategyControls logic, and Risk logic were untouched.
- No duplicate responsibility was introduced.
- BrokerAdapter still does not make policy decisions.
- OrderManager remains the creator of internal orders.
- PortfolioGovernor remains the final authority before order creation, with ControlPlane enforcing the existing runtime open gate after Governor approval and before OrderManager creation.
- No opening order can bypass `can_open_new_position()` through `RuntimeOrchestrator`.
- Pause/kill never flatten positions.
- Protective exits are not canceled by the control-plane cancellation sweep.
- Unknown broker orders are preserved and flagged, not canceled blindly.
- Docs were updated with this verification entry.

## 2026-04-24 - Broker Sync Truth Hardening

Implemented read-only broker truth normalization and reconciliation hardening for account state, positions, and open orders.

Files created:

- None

Files modified:

- `backend/app/brokers/__init__.py`
- `backend/app/brokers/adapter.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/models.py`
- `backend/app/brokers/sync.py`
- `backend/app/control_plane/service.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `backend/tests/unit/brokers/test_broker_interface_expansion.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- normalized `BrokerAccountSnapshot` with account equity, cash, buying power, daytrading buying power, PDT flag, trading block flag, status, and timestamp
- normalized `BrokerPositionSnapshot` with account, symbol, quantity, side, average entry, market value, unrealized P/L, and timestamp
- new normalized `BrokerOpenOrderSnapshot`
- read-only BrokerAdapter contract for account snapshot, positions, and open orders
- Alpaca paper adapter normalization for account, position, and open-order snapshots
- fake broker read-only snapshot support for tests
- explicit `BrokerSyncState` with configurable stale detection
- `BrokerSyncService` for read/reconcile-only broker truth flow
- reconciliation result fields for matched orders, unmatched broker orders, unmatched internal orders, position deltas, and sync status
- detection for missing broker orders, orphan broker orders, mismatched fills, stale sync, and position deltas
- broker-derived internal order updates still flow through `BrokerSync.apply_result`

Tests run:

- `python -m pytest backend/tests/unit/brokers -q`
- `python -m pytest backend/tests/unit/orders -q`
- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Brokers tests: `40 passed`
- Orders tests: `8 passed`
- Governor tests: `9 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `270 passed`

Issues fixed:

- Updated existing broker tests to assert normalized open-order snapshots instead of broker order results from `list_open_orders`.
- Routed reconciliation through `BrokerSyncService` while preserving `BrokerSync` as the writer for broker-derived order status updates.

Architecture confirmations:

- No core engines were modified.
- FeatureEngine, SignalEngine, StrategyControls, Risk, ExecutionStyle, PortfolioGovernor decision logic, and OrderManager behavior were not changed.
- No duplicate responsibility was introduced.
- BrokerAdapter remains policy-free and performs read/translation only.
- BrokerSyncService performs reconciliation only and does not submit orders, cancel orders, create internal orders, or modify Governor decisions.
- Execution pipeline behavior was not changed.
- Docs were updated with this implementation entry.

## 2026-04-24 - Broker Sync Truth Hardening Closeout

Closeout verification completed for the Broker Sync Truth Hardening milestone.

Files created:

- None during closeout.

Files modified:

- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Tests run:

- `python -m pytest backend/tests/unit/brokers -q`
- `python -m pytest backend/tests/unit/orders -q`
- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Brokers tests: `40 passed`
- Orders tests: `8 passed`
- Governor tests: `9 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `270 passed`

Issues fixed:

- None. No task-related failures were found during closeout.

Architecture confirmations:

- `BrokerAccountSnapshot`, `BrokerPositionSnapshot`, `BrokerOpenOrderSnapshot`, and `BrokerSyncState` are implemented.
- BrokerAdapter exposes read-only broker truth methods for account snapshots, positions, and open orders.
- `BrokerSyncService` performs reconciliation and returns structured results with matched orders, unmatched broker orders, unmatched internal orders, position deltas, and sync status.
- stale sync detection is explicit.
- Governor and OrderManager do not read directly from BrokerAdapter.
- FeatureEngine, SignalEngine, StrategyControls, Risk, PortfolioGovernor decision logic, and OrderManager behavior were not modified.
- BrokerAdapter remains policy-free.
- BrokerSyncService writes broker-derived order truth through BrokerSync.
- No execution behavior was changed.
- No duplicate responsibility was introduced.

## 2026-04-24 - Portfolio Governor Feature Admissibility

Implemented projected-state portfolio admissibility inside `PortfolioGovernor` using broker-truth portfolio snapshots and explicit candidate impact inputs.

Files created:

- None.

Files modified:

- `backend/app/governor/models.py`
- `backend/app/governor/service.py`
- `backend/app/governor/__init__.py`
- `backend/tests/unit/governor/test_portfolio_governor.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- Added read-only portfolio state inputs for equity, current positions, pending opens, current open risk, and pending open risk.
- Added projected portfolio feature outputs: `gross_exposure_pct`, `net_exposure_pct`, `open_risk_pct`, `pending_open_risk_pct`, `symbol_concentration_pct`, `new_open_slots_remaining`, and `broker_sync_stale`.
- Added deterministic projected-state gates for gross exposure, net exposure, symbol concentration, open risk, max open slots, and stale broker sync.
- Preserved protective exit approval ahead of kill, pause, stale-sync, exposure, concentration, and open-risk blocks.
- Kept broker truth as a read-only governor input; no broker mutation or order mutation was introduced.

Tests run:

- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests -q`

Test results:

- Governor tests: `14 passed`
- Full backend suite: `275 passed`

Issues fixed:

- Replaced the prior symbol-concentration placeholder with deterministic projected concentration enforcement.
- Added focused coverage for projected exposure rejection, symbol concentration rejection, open risk rejection, stale broker sync rejection, protective exit allowance, and boundary dependency checks.

Architecture confirmations:

- No core engines were modified.
- FeatureEngine, SignalEngine, StrategyControls, Risk logic, ExecutionStyle, OrderManager behavior, and execution pipeline behavior were not changed.
- PortfolioGovernor remains the final approval authority before order creation.
- BrokerAdapter remains policy-free and is not read by PortfolioGovernor.
- No duplicate responsibility was introduced.

## 2026-04-24 - Portfolio Governor Feature Admissibility Closeout

Verified the Portfolio Governor projected-state admissibility layer without adding features or refactoring unrelated code.

Files created:

- None.

Files modified:

- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Tests run:

- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests -q`

Test results:

- Governor tests: `14 passed`
- Full backend suite: `275 passed`

Issues fixed:

- None. No task-related failures were found during closeout.

Architecture confirmations:

- Portfolio feature inputs are read-only request/snapshot data.
- Projected post-trade state is computed in `PortfolioGovernor` and returned in the decision payload.
- Deterministic constraints are enforced for gross exposure, net exposure, open risk, symbol concentration, max open slots, and stale broker sync.
- `broker_sync_stale` blocks new opens.
- Protective exits remain allowed before kill, pause, stale-sync, exposure, concentration, open-risk, and open-slot checks.
- `PortfolioGovernor` does not mutate broker state, orders, runtime state, or portfolio snapshots.
- `PortfolioGovernor` does not compute strategy features or depend on `FeatureEngine`.
- FeatureEngine, SignalEngine, StrategyControls, Risk logic, ExecutionStyle, OrderManager behavior, BrokerAdapter policy behavior, and execution pipeline behavior were not modified.
- PortfolioGovernor remains the final approval authority before order creation.
- No duplicate responsibility was introduced.

## 2026-04-24 13:57 ET - Order Lifecycle Completion

Added internal and broker-safe order lifecycle handling for cancel, scoped cancel, replace, and protective order preservation while keeping broker-derived status writes routed through BrokerSync.

Files created:

- None.

Files modified:

- `backend/app/orders/models.py`
- `backend/app/orders/manager.py`
- `backend/app/brokers/adapter.py`
- `backend/app/brokers/models.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/sync.py`
- `backend/app/control_plane/service.py`
- `backend/tests/unit/orders/test_order_manager.py`
- `backend/tests/unit/brokers/test_broker_adapter_boundary.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- Extended `InternalOrder` with cancel and replacement lifecycle fields.
- Extended `BrokerAdapter` with `cancel_order`, `cancel_orders`, and `replace_order`.
- Added deterministic OrderManager lifecycle methods for single cancel, scoped cancel, and replace.
- Added global, account, and deployment scoped cancellation selection.
- Preserved protective `sl`, `tp`, `close`, and `scale` orders from automatic cancellation.
- Limited replacement to unfilled open orders unless protective replacement is explicitly allowed.
- Updated Fake and Alpaca adapter boundaries so cancel/replace use broker order ids and return normalized `BrokerOrderResult`.
- Updated BrokerSync to apply broker cancellation status and cancel timestamps.

Tests run:

- `python -m pytest backend/tests/unit/orders -q`
- `python -m pytest backend/tests/unit/brokers -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Order tests: `16 passed`
- Broker tests: `42 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `285 passed`

Issues fixed:

- Removed an adapter-side synthetic internal order helper from Alpaca so BrokerAdapter implementations do not create `InternalOrder`.
- Kept legacy control-plane test doubles compatible while routing real adapter cancellation through InternalOrder objects.
- Cleaned generated bytecode changes before commit.

Architecture confirmations:

- No core engines were modified.
- FeatureEngine, SignalEngine, StrategyControls, Risk logic, PortfolioGovernor decision logic, and execution pipeline behavior were not modified.
- OrderManager remains the only creator of InternalOrder.
- BrokerAdapter remains policy-free and only translates/submits/cancels/replaces.
- BrokerSync remains the writer for broker-derived order truth.
- ControlPlane remains the authority for kill/pause semantics.
- No duplicate responsibility was introduced.
- Protective order rules are enforced.

## 2026-04-24 13:57 ET - Implementation Log Timestamp Format Update

Updated the implementation log convention for all future entries.

Files modified:

- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- All new implementation, verification, closeout, blocker, and partial progress entries must use full Eastern Time timestamps.
- Required heading format: `## YYYY-MM-DD HH:MM ET - [Task Name]`.
- Date-only headings must not be used for future entries.
- Timezone must not be omitted for future entries.

Tests run:

- Not run. Documentation-only format update.

Issues fixed:

- Updated the latest Order Lifecycle Completion heading from date-only to full ET timestamp.

Architecture confirmations:

- No application code was modified.
- No core engines were modified.
- No duplicate responsibility was introduced.

## 2026-04-24 14:03 ET - Broker Streaming + Sync Freshness

Files created:

- `backend/app/brokers/stream.py`

Files modified:

- `backend/app/brokers/__init__.py`
- `backend/app/brokers/adapter.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/models.py`
- `backend/app/brokers/sync.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- Added `AlpacaAccountStreamAdapter` to subscribe to Alpaca account stream channels and normalize order, fill, position, and account payloads into internal broker sync events.
- Added broker stream event models for order and fill updates.
- Extended `BrokerSyncState` with `last_event_at`, `last_poll_sync_at`, `last_successful_sync_at`, explicit `is_stale`, and `stale_reason`.
- Extended `BrokerSyncService` with streaming ingestion methods for order, fill, position, and account updates.
- Routed streaming order updates through `BrokerSync.apply_result`.
- Added service-held latest account and position snapshots, fill capture, deterministic current freshness state, and stream-disconnect fallback polling.
- Marked sync state stale when stream disconnect fallback polling fails.
- Preserved the existing PortfolioGovernor stale broker sync gate and protective-exit allowance without changing governor decision logic.

Tests run:

- `python -m pytest backend/tests/unit/brokers -q`
- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Broker tests: `51 passed`
- Governor tests: `14 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `294 passed`

Issues fixed:

- Preserved stale broker snapshot detection during reconciliation so a poll call cannot make an old broker timestamp look fresh.
- Broke a package import cycle by importing `InternalOrder` directly from `backend.app.orders.models` inside broker boundary modules.

Architecture confirmations:

- No core engines modified.
- FeatureEngine, SignalEngine, StrategyControls, Risk logic, ExecutionStyle, OrderManager behavior, and execution pipeline behavior were not modified.
- PortfolioGovernor decision logic was not changed; it only continues reading broker sync freshness.
- BrokerAdapter remains policy-free and emits normalized events only.
- BrokerSync remains sole writer for broker-derived order truth.
- No BrokerSync bypass was introduced.
- No duplicate responsibility was introduced.

## 2026-04-24 14:15 ET - Broker Streaming + Sync Freshness Closeout

Tests run:

- `python -m pytest backend/tests/unit/brokers -q`
- `python -m pytest backend/tests/unit/governor -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Broker tests: `51 passed`
- Governor tests: `14 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `294 passed`

Issues fixed:

- None. Verification passed without code changes.

Architecture confirmations:

- `AlpacaAccountStreamAdapter` exists and normalizes order, fill, position, and account events.
- `BrokerSyncService` handles streaming order, fill, position, and account updates.
- `BrokerSyncState` tracks `last_event_at`, `last_poll_sync_at`, `last_successful_sync_at`, `is_stale`, and `stale_reason`.
- Stream disconnect fallback polling is implemented, and failed fallback marks sync stale.
- PortfolioGovernor blocks new opens when broker sync is stale and still allows protective exits.
- No FeatureEngine, SignalEngine, StrategyControls, Risk, ExecutionStyle, OrderManager behavior, or execution pipeline behavior changes were made during closeout.
- BrokerAdapter remains policy-free.
- BrokerSync remains the sole writer of broker-derived order truth.
- No duplicate responsibility was introduced.

Remaining blockers:

- None.

## 2026-04-24 14:35 ET - Paper-to-Live Promotion Gate

Files created/modified:

- Created `backend/app/promotion/__init__.py`
- Created `backend/app/promotion/models.py`
- Created `backend/app/promotion/service.py`
- Created `backend/tests/unit/promotion/test_promotion_gate.py`
- Modified `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- Added deterministic `PromotionGateService` for pre-runtime `BROKER_PAPER` to `BROKER_LIVE` eligibility evaluation.
- Added `PromotionResult` with `program_id`, `deployment_id`, `eligible`, `blocking_reasons`, `warnings`, and `evaluated_at`.
- Added explicit read-only evidence models for paper runs, simulation validation, governor readiness, broker sync, reconciliation, and control-plane state.
- Implemented P0 blockers for frozen program status, current paper mode, successful paper run evidence, broker sync freshness, global kill/account pause, PortfolioGovernor readiness, reconciliation mismatches, paper runtime errors, and required enforced Sim Lab evidence.
- Implemented P1 non-blocking warnings for limited paper trade count, short runtime duration, high rejection rate, high drawdown, and inconsistent broker sync events.

Tests run:

- `python -m pytest backend/tests/unit/promotion -q`
- `python -m pytest backend/tests -q`

Test results:

- Promotion tests: `12 passed`
- Full backend suite: `312 passed`

Issues fixed:

- None. New promotion tests and full backend verification passed on first run.

Architecture confirmations:

- No core engines modified.
- FeatureEngine was not modified and is not imported by the promotion gate.
- SignalEngine was not modified and is not imported by the promotion gate.
- StrategyControls, Risk logic, ExecutionStyle, OrderManager behavior, BrokerAdapter behavior, and the execution pipeline were not modified.
- PortfolioGovernor remains final authority at runtime; the promotion gate only validates pre-runtime evidence.
- No duplicate responsibility introduced.
- No live trading behavior changes.

## 2026-04-24 14:25 ET - Mode Naming Standardization

Files created:

- `backend/app/domain/trading_mode.py`

Files modified:

- `backend/app/brokers/__init__.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/fake.py`
- `backend/app/brokers/models.py`
- `backend/app/brokers/stream.py`
- `backend/app/chart_lab/preview_service.py`
- `backend/app/domain/__init__.py`
- `backend/app/domain/chart_lab.py`
- `backend/app/domain/simulation.py`
- `backend/app/simulation/historical_replay.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `backend/tests/unit/brokers/test_broker_interface_expansion.py`
- `backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `backend/tests/unit/control_plane/test_control_plane.py`
- `backend/tests/unit/domain/test_domain_boundaries.py`
- `backend/tests/unit/tools/test_paper_operator_tools.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Replacements performed:

- Replaced `ChartLabMode` usage with canonical `TradingMode.CHART_LAB_BATCH` for the existing batch preview path.
- Replaced `SimulationMode.HISTORICAL_REPLAY` usage with canonical `TradingMode.SIM_LAB_HISTORICAL`.
- Replaced `BrokerAccountMode.PAPER` usage with canonical `TradingMode.BROKER_PAPER`.
- Replaced broker capability and error wording that exposed ambiguous paper/live mode labels with BROKER_PAPER/BROKER_LIVE naming.

Validation rules added:

- Chart Lab modes reject BrokerAdapter access, order creation, OrderLedger mutation, and TradeLedger mutation.
- Sim Lab modes reject BrokerAdapter access and real broker data usage.
- Broker modes require both BrokerAdapter and BrokerSync.
- ChartLabSession now accepts only CHART_LAB modes.
- SimulationSession now accepts only SIM_LAB modes.
- BrokerAccountSnapshot now accepts only BROKER modes when a mode is present.

Tests added:

- Chart Lab cannot access BrokerAdapter.
- Chart Lab cannot create orders or mutate order/trade ledgers.
- Sim Lab cannot access BrokerAdapter or real broker data.
- Broker modes require BrokerAdapter and BrokerSync.
- Invalid canonical mode usage raises explicit validation errors.
- Ambiguous legacy mode enum/string usage is pinned out of backend app mode contracts.

Tests run:

- `python -m pytest backend/tests/unit/domain backend/tests/unit/brokers -q`
- `python -m pytest backend/tests -q`

Test results:

- Domain + broker tests: `88 passed`
- Full backend suite: `300 passed`

Architecture confirmations:

- No behavior changes.
- No core engines modified.
- FeatureEngine, SignalEngine, execution pipeline, PortfolioGovernor logic, and BrokerAdapter behavior were not modified.
- No new runtime paths were introduced.
- No duplicate responsibility was introduced.

## 2026-04-24 14:26 ET - Mode Naming Contract Added

Files created:

- `docs/system_rebuild_outputs/MODE_NAMING_CONTRACT.md`

Scope:

- Added a single source of truth document for canonical TradingMode values.
- Defined each Chart Lab, Sim Lab, and Broker Runtime mode.
- Documented allowed capabilities and explicit mode boundaries.
- Documented internal enum naming rules and user-facing label rules.
- Documented banned ambiguous mode terms.
- Added the BrokerAdapter anchor rule: if BrokerAdapter is not involved, it is not Broker Runtime.

Architecture confirmations:

- Documentation only.
- No code changes were made.
- No enums were renamed.
- No runtime behavior was changed.

## 2026-04-24 14:30 ET - Mode Naming Standardization Closeout

Files created/modified:

- Modified `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`
- No source code files were created or modified during closeout.

Tests run:

- `python -m pytest backend/tests/unit/chart_lab -q`
- `python -m pytest backend/tests/unit/simulation -q`
- `python -m pytest backend/tests/unit/runtime -q`
- `python -m pytest backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Chart Lab tests: `6 passed`
- Simulation tests: `9 passed`
- Runtime tests: `6 passed`
- Pipeline tests: `10 passed`
- Full backend suite: `300 passed`

Issues fixed:

- None. Verification passed without code changes.

Architecture confirmations:

- Canonical modes are defined in `TradingMode`.
- Ambiguous mode names are removed from backend app mode contracts or isolated to non-mode implementation details.
- Chart Lab supports `CHART_LAB_BATCH` and `CHART_LAB_LIVE_PREVIEW`.
- Sim Lab supports `SIM_LAB_HISTORICAL` and `SIM_LAB_LIVE_SIMULATION`.
- Broker Runtime supports `BROKER_PAPER` and `BROKER_LIVE`.
- Chart Lab modes cannot use BrokerAdapter.
- Sim Lab modes cannot use BrokerAdapter.
- Broker modes require BrokerAdapter and BrokerSync.
- No FeatureEngine changes.
- No SignalEngine changes.
- No PortfolioGovernor logic changes.
- No OrderManager behavior changes.
- No BrokerAdapter policy logic added.
- No duplicate responsibility introduced.
- No runtime behavior changes.

Remaining blockers:

- None.

## 2026-04-24 14:38 ET - Promotion Gate Precondition Clarification

Files modified:

- `backend/app/promotion/__init__.py`
- `backend/app/promotion/service.py`
- `backend/tests/unit/promotion/test_promotion_gate.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- Documented `PromotionGateService` as the required precondition service for any future `BROKER_LIVE` deployment creation flow.
- Clarified that the promotion gate evaluates eligibility only and does not create, start, promote, or mutate deployments.
- Added a deterministic no-mutation unit test that evaluates the same unsafe context twice and verifies stable blocking reasons plus unchanged supplied state.

Tests run:

- `python -m pytest backend/tests/unit/promotion -q`
- `python -m pytest backend/tests -q`

Test results:

- Promotion tests: `13 passed`
- Full backend suite: `313 passed`

Issues fixed:

- Clarified that no live deployment lifecycle is wired because no live deployment creation service exists yet.

Architecture confirmations:

- No deployment creation service was invented.
- No deployment start or live promotion orchestration was added.
- No execution pipeline changes.
- PromotionGateService remains read-only pre-runtime validation.

## 2026-04-24 14:43 ET - Account-Scoped Promotion Gate Clarification

Files modified:

- `backend/app/promotion/models.py`
- `backend/app/promotion/service.py`
- `backend/tests/unit/promotion/test_promotion_gate.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope implemented:

- Made promotion evaluation explicitly account-scoped with `source_broker_account_id`, `target_broker_account_id`, `source_mode`, and `target_mode`.
- Required source mode to be `BROKER_PAPER` and target mode to be `BROKER_LIVE`.
- Added `broker_account_id` to paper run evidence so promotion checks only the specific source paper account and deployment being promoted.
- Scoped paper run blockers, runtime error blockers, and warning calculations to matching source account/deployment evidence.
- Added tests proving evidence from another paper account or deployment does not satisfy promotion requirements or generate scoped warnings.

Tests run:

- `python -m pytest backend/tests/unit/promotion -q`
- `python -m pytest backend/tests -q`

Test results:

- Promotion tests: `16 passed`
- Full backend suite: `316 passed`

Issues fixed:

- Removed the implicit single-account assumption from the promotion context.
- Prevented unrelated paper account evidence from satisfying or warning on a specific promotion evaluation.

Architecture confirmations:

- Multiple `BROKER_PAPER` and `BROKER_LIVE` accounts are supported by the promotion gate contract.
- No deployment orchestration was introduced.
- No deployment lifecycle wiring was added.
- PromotionGateService remains read-only and deterministic.

## 2026-04-24 14:55 ET - Synthesis Blueprint Mode and Validation Clarification

Files modified:

- `docs/system_rebuild_outputs/08_synthesis_blueprint_output.md`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope:

- Clarified lifecycle mode names using Chart Lab, Sim Lab, Broker Runtime (Paper), Live Promotion Gate, and Broker Runtime (Live).
- Clarified that Broker Runtime (Paper) is the full runtime pipeline using Alpaca Paper broker endpoint/account, real BrokerAdapter, real BrokerSync, and fake money.
- Clarified that Broker Runtime (Paper) is not Sim Lab and not Backtest.
- Clarified that Broker Runtime (Live) is the full runtime pipeline using Alpaca Live broker endpoint/account, real BrokerAdapter, real BrokerSync, and real money.
- Added validation enforcement levels: Required, Strongly recommended, and Optional / advanced.
- Documented that Walk-Forward is not strictly required, missing Walk-Forward must create a high-severity PromotionGate warning, and missing Optimization must create a PromotionGate warning.
- Documented that missing Walk-Forward and missing Optimization warnings must not block promotion by default.

Architecture confirmations:

- Documentation-only update.
- No code changes were made in this step.
- No architecture changes were made.
- No lifecycle order changes were made except clarifying canonical mode names.

## 2026-04-24 14:59 ET - Promotion Gate Validation Warnings

Files modified:

- `backend/app/promotion/models.py`
- `backend/app/promotion/service.py`
- `backend/tests/unit/promotion/test_promotion_gate.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Scope:

- Added non-blocking PromotionGate warnings for missing strongly recommended validation evidence.
- Added `missing_optimization_evidence` warning with medium severity.
- Added `missing_walk_forward_evidence` warning with high severity.
- Added validation evidence inputs to promotion evaluation so existing Optimization and Walk-Forward evidence removes those warnings.
- Preserved P0 blocking logic and eligibility behavior.

Tests run:

- `python -m pytest backend/tests/unit/promotion -q`
- `python -m pytest backend/tests -q`

Test results:

- Promotion tests: `19 passed`
- Full backend suite: `319 passed`

Architecture confirmations:

- Optimization and Walk-Forward remain strongly recommended, not required.
- Warnings do not block promotion by default.
- No runtime behavior changes were made.
- No deployment orchestration or lifecycle wiring was added.

## 2026-04-24 15:12 ET - Persistent Runtime Store

Files created:

- `backend/app/persistence/models.py`
- `backend/app/persistence/session.py`
- `backend/app/persistence/runtime_store.py`

Files updated:

- `backend/app/persistence/__init__.py`
- `backend/app/persistence/sqlite.py`
- `backend/app/brokers/sync.py`
- `backend/app/control_plane/__init__.py`
- `backend/app/control_plane/service.py`
- `backend/app/governor/service.py`
- `backend/app/runtime/engine.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/persistence/test_sqlite_persistence.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

What was implemented:

- Added a durable SQLite runtime store boundary for internal orders, trades/fills, broker order mappings, broker account snapshots, broker sync freshness, deployment runtime state, portfolio governor state, and control-plane effective state.
- Kept compatibility wrappers for `SQLiteOrderLedger`, `SQLiteTradeLedger`, `SQLiteBrokerOrderMappingStore`, `SQLiteGovernorStateStore`, and `SQLiteDeploymentStateStore`.
- Added repository APIs for save/load/list order, save/load trades and fills by deployment, broker mapping lookup by internal and broker IDs, broker freshness save/load, account snapshot save/load, deployment runtime state save/load, governor policy save/load, and control-plane state save/load.
- Wired optional persistence hooks into BrokerSync/BrokerSyncService, PortfolioGovernor, RuntimeEngine, RuntimeOrchestrator, and ControlPlane while preserving in-memory defaults.
- Added restart and boundary tests covering order, fill, broker mapping, broker freshness including stale freshness, governor state, deployment runtime state, control-plane state, OrderManager order creation authority, BrokerSync broker truth persistence authority, BrokerAdapter limits, Sim Lab isolation, and Chart Lab isolation.

Scope kept out:

- No FeatureEngine changes.
- No SignalEngine changes.
- No frontend work.
- No real Alpaca calls.
- No API route expansion.
- No policy decisions moved into persistence.
- No BrokerAdapter direct writes to broker-derived truth or internal orders.
- No Sim Lab broker adapter or runtime persistence wiring.
- No Chart Lab order, trade, fill, or broker-state creation.

Validation commands run:

- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests/unit/persistence -q`
- `python -m pytest backend/tests/unit/orders backend/tests/unit/brokers backend/tests/unit/governor backend/tests/unit/pipeline -q`
- `python -m pytest backend/tests -q`

Test results:

- Compile: passed
- Persistence tests: `15 passed`
- Orders/brokers/governor/pipeline tests: `91 passed`
- Full backend suite: `329 passed`

Architecture confirmations:

- OrderManager remains the only creator of internal orders.
- BrokerSync and BrokerSyncService remain the only writers of broker-derived runtime truth.
- PortfolioGovernor still owns approval logic; persistence only stores/loads policy state.
- ControlPlane remains the authority for kill/pause state; persistence only stores/loads the effective state.
- BrokerAdapter cannot create or persist InternalOrder.
- Sim Lab does not use BrokerAdapter or runtime persistence.
- Chart Lab does not create orders, trades, fills, or broker state.
- No duplicate runtime authority or pipeline bypasses were introduced.

## 2026-04-24 15:27 ET - Runtime Startup Recovery Orchestrator

Files created:

- `backend/app/runtime/recovery_orchestrator.py`
- `backend/tests/unit/runtime/test_recovery_orchestrator.py`
- `backend/main.py`

Files updated:

- `backend/app/brokers/sync.py`
- `backend/app/control_plane/service.py`
- `backend/app/orders/manager.py`
- `backend/app/persistence/models.py`
- `backend/app/persistence/runtime_store.py`
- `backend/app/runtime/__init__.py`
- `backend/app/runtime/models.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Recovery sequence:

- Enters ControlPlane recovery mode before loading runtime state.
- Loads persisted deployments, orders, trades, broker mappings, broker snapshots, broker sync freshness, governor state, and control-plane state.
- Rehydrates global kill, account pauses, and deployment pauses while preserving recovery mode until the sequence exits.
- Reconciles each broker account through BrokerSync only: account snapshot, positions, open orders, order status convergence, missing broker order marking, unknown broker order ingestion, and broker sync freshness persistence.
- Rebuilds deployment runtime state from persisted runtime state only; no FeatureEngine or SignalEngine execution occurs.
- Runs fail-closed safety checks before resume eligibility and marks deployments `blocked_recovery` or `recovered_ready`.
- Exits ControlPlane recovery mode without auto-starting trading.

Reconciliation behavior:

- Open internal orders are converged from broker results through `BrokerSync.apply_result`.
- Missing broker orders are marked terminal through `BrokerSync.mark_missing_broker_order`.
- Unknown broker open orders are preserved and ingested as broker-derived open-order snapshots through BrokerSync; no internal orders are created.
- Broker sync freshness is recorded through BrokerSync and stale accounts produce `trading_blocked_reason=broker_sync_stale`.
- Recovery is idempotent; rerunning startup recovery leaves persisted order, mapping, snapshot, freshness, control, and deployment state unchanged for the same broker truth.

Safety guarantees:

- ControlPlane exposes and persists `system_recovery_active`.
- New order creation is blocked while recovery mode is active.
- Global kill and deployment/account pauses remain ControlPlane-owned and are preserved on restart.
- OrderManager remains the only creator of internal orders.
- BrokerAdapter still cannot write runtime state.
- BrokerSync remains the only writer of broker-derived truth.
- PortfolioGovernor is not bypassed and no approval logic moved into persistence or recovery.
- No execution engine, FeatureEngine, or SignalEngine path is invoked during recovery.
- Trading is never auto-started after recovery.

Tests run:

- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests/unit/runtime/test_recovery_orchestrator.py -q`
- `python -m pytest backend/tests/unit/orders backend/tests/unit/brokers backend/tests/unit/governor backend/tests/unit/pipeline backend/tests/unit/runtime -q`
- `python -m pytest backend/tests/unit/persistence -q`
- `python -m pytest backend/tests -q`

Test results:

- Compile: passed
- Recovery orchestrator tests: `10 passed`
- Runtime-adjacent targeted suites: `107 passed`
- Persistence tests: `15 passed`
- Full backend suite: `339 passed`

## 2026-04-24 15:41 ET - Alpaca Broker Adapter Live Integration (Paper Mode)

Files created:

- `backend/tests/unit/brokers/test_alpaca_live_adapter.py`

Files updated:

- `backend/app/brokers/alpaca.py`
- `backend/app/pipeline/orchestrator.py`
- `backend/tests/unit/brokers/test_alpaca_broker_adapter.py`
- `backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Tightened `AlpacaBrokerAdapter` to paper-only V1 submission through `alpaca-py`.
- Supported order submission is market-only: symbol, quantity, side, time-in-force, and deterministic `client_order_id`.
- Removed limit-order request construction from the Alpaca V1 safe submission path.
- Added broker-side idempotency: submit first checks `get_order_by_client_id`; existing broker orders are normalized and returned without duplicate submission.
- Preserved response normalization into `BrokerOrderResult` for accepted/new, partial fill, full fill, canceled, rejected, and expired states.
- Unknown Alpaca statuses fail closed with structured `AlpacaBrokerError`.
- Account snapshots, position snapshots, and open-order polling continue through adapter methods consumed by `BrokerSync`.
- Runtime submission remains `OrderManager.create_order` -> `BrokerAdapter.submit_order` -> `BrokerSync.apply_result`.
- Runtime adapter failures are converted into rejected broker results and applied through BrokerSync, so the pipeline records a terminal ledger update instead of crashing through the runtime.

Safety limitations:

- Paper trading only.
- Market orders only.
- No live trading.
- No bracket orders.
- No trailing stops.
- No adapter-side internal order creation.
- No adapter-side broker truth writes.
- No feature computation or signal logic in the adapter.

Error handling model:

- Retryable structured errors: network/connectivity/timeouts and Alpaca rate limits.
- Fatal structured errors: invalid order, insufficient buying power, symbol not tradable, auth, unknown broker errors, and unknown statuses.
- Missing broker order during idempotency lookup is treated as non-fatal and allows a single submit attempt.

Tests run:

- `python -m pytest backend/tests/unit/brokers/test_alpaca_broker_adapter.py backend/tests/unit/brokers/test_alpaca_live_adapter.py backend/tests/unit/pipeline/test_runtime_orchestrator.py`
- `python -m pytest backend/tests/unit/brokers/test_broker_adapter_boundary.py backend/tests/unit/brokers/test_broker_interface_expansion.py backend/tests/unit/brokers/test_broker_sync_reconciliation.py`
- `python -m pytest backend/tests/unit`

Test results:

- Focused Alpaca and pipeline tests: `36 passed`
- Broker boundary/reconciliation tests: `37 passed`
- Full unit suite: `351 passed`

Architecture confirmations:

- BrokerAdapter remains the only broker-trading layer that calls Alpaca.
- BrokerSync remains the only writer of broker-derived order truth.
- OrderManager remains the only creator of InternalOrder.
- PortfolioGovernor approval remains required before runtime open submission.
- No duplicate Alpaca submission occurs when the deterministic client order id already exists at the broker.

## 2026-04-24 16:06 ET - Operations Center Backend Runtime Visibility and Control Contract

Files created:

- `backend/app/operations/__init__.py`
- `backend/app/operations/models.py`
- `backend/app/operations/service.py`
- `backend/tests/unit/operations/test_operations_center_service.py`

Implementation:

- Added `OperationsCenterService` as the backend-only Operations Center contract for Broker Runtime - Paper visibility and control.
- Runtime overview surfaces system recovery, global kill state, broker account summaries, deployment summaries, stale sync accounts, blocked recovery deployments, open internal order count, open broker position count, latest governor decisions, latest broker sync timestamp, and latest runtime event timestamp.
- Account operations surfaces BrokerSync-owned account snapshot, sync freshness, open broker order snapshots, internal order ledger summary, BrokerSync positions, account deployments, and account pause/kill state.
- Deployment operations surfaces runtime status, program id/version, broker account id, governor id/state, market-data/sync/decision timestamps, open internal orders, trades/fills, latest pipeline events, and latest governor decisions.
- Pause/resume and global kill/resume methods delegate only to `ControlPlane`.
- Flatten request methods expose a backend contract and return explicit `unsupported_not_ready` when `ControlPlane` has no flatten implementation.

State surfaced:

- ControlPlane snapshot
- Broker account snapshots
- Broker sync freshness
- Broker open order snapshots
- BrokerSync read-only positions/fills
- Internal order ledger summaries
- Deployment runtime states, including `blocked_recovery` and `recovered_ready`
- Runtime/pipeline event timestamps
- PortfolioGovernor policy and latest decisions

Control delegation model:

- `OperationsCenterService` does not implement policy.
- `ControlPlane` remains the only authority for kill, pause, resume, and future flatten behavior.
- Flatten is delegated if the control-plane contract exists; otherwise it returns not-ready without broker calls.

Scope kept out:

- No frontend.
- No new trading logic.
- No FeatureEngine or SignalEngine changes.
- No Sim Lab or Chart Lab changes.
- No direct Alpaca or broker adapter calls from Operations Center.
- No order creation from Operations Center.
- No mutation of broker truth from Operations Center.

Tests run:

- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests/unit/operations -q`
- `python -m pytest backend/tests -q`

Test results:

- Compile: passed
- Operations Center tests: `8 passed`
- Full backend suite: `359 passed`

## 2026-04-24 16:13 ET - Operations Center API Routes

Files created:

- `backend/app/api/__init__.py`
- `backend/app/api/routes/__init__.py`
- `backend/app/api/routes/operations.py`
- `backend/tests/unit/api/test_operations_routes.py`

Files updated:

- `backend/app/control_plane/client_order_id.py`
- `backend/app/operations/__init__.py`
- `backend/app/operations/service.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Added backend API route contracts for Operations Center runtime visibility:
  - `GET /api/v1/operations/overview`
  - `GET /api/v1/operations/accounts/{account_id}`
  - `GET /api/v1/operations/deployments/{deployment_id}`
- Added backend API route contracts for Operations Center controls:
  - `POST /api/v1/operations/deployments/{deployment_id}/pause`
  - `POST /api/v1/operations/deployments/{deployment_id}/resume`
  - `POST /api/v1/operations/accounts/{account_id}/pause`
  - `POST /api/v1/operations/accounts/{account_id}/resume`
  - `POST /api/v1/operations/global/kill`
  - `POST /api/v1/operations/global/resume`
- Added backend API flatten contract routes:
  - `POST /api/v1/operations/accounts/{account_id}/flatten`
  - `POST /api/v1/operations/deployments/{deployment_id}/flatten`
- Added explicit response models for overview, account operations, deployment operations, control acknowledgements, operator-readable route errors, and flatten request responses.
- Kept the route module import-safe without requiring a web framework dependency in the current unit environment; if FastAPI is installed, the same module exposes a normal `APIRouter`.
- Made Operations package service export lazy and removed an eager enum import from `client_order_id` to prevent API route imports from triggering a control/order import cycle.

Control delegation model:

- API routes delegate read/control requests to `OperationsCenterService`.
- `OperationsCenterService` remains the only route-facing orchestration layer.
- `OperationsCenterService` delegates kill, pause, resume, and flatten readiness only to `ControlPlane`.
- Routes do not implement policy, trading behavior, broker reconciliation, or order lifecycle behavior.

Unsupported flatten behavior:

- Flatten routes return the `FlattenRequestResponse` from `OperationsCenterService`.
- With the current `ControlPlane` contract, flatten returns `accepted=false`, `status=unsupported_not_ready`, and `reason=flatten_not_implemented_in_control_plane`.
- No broker calls are made by API routes for flatten requests.

Scope kept out:

- No frontend.
- No new trading behavior.
- No direct Alpaca or broker adapter calls from API routes.
- No order creation from API routes.
- No broker truth mutation from API routes.
- No FeatureEngine or SignalEngine changes.

Tests run:

- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests/unit/api/test_operations_routes.py -q`
- `python -m pytest backend/tests -q`

Test results:

- Compile: passed
- Operations API route tests: `10 passed`
- Full backend suite: `369 passed`

## 2026-04-24 16:20 ET - Operations Center UI

Files created:

- `package.json`
- `frontend/index.html`
- `frontend/src/api/operations.js`
- `frontend/src/operationsCenter.js`
- `frontend/src/main.js`
- `frontend/src/styles.css`
- `frontend/scripts/check-frontend.mjs`
- `frontend/tests/operationsCenter.test.mjs`

Implementation:

- Added a dependency-free frontend Operations Center page and menu entry for runtime visibility and operator controls.
- Added Operations API client functions for overview, account detail, deployment detail, account pause/resume, deployment pause/resume, global kill/resume, and account/deployment flatten requests.
- Added overview UI for global recovery state, global kill state, broker account summaries, stale broker sync warnings, active deployments, blocked recovery deployments, recovered-ready deployments, open orders, open positions, latest broker sync timestamp, latest runtime event timestamp, and latest governor decisions.
- Added account and deployment detail panels sourced only from Operations API detail routes.
- Added destructive-control confirmation for global kill and flatten requests.
- Added operator-readable API error rendering that does not imply safety while state is unavailable.
- Added loading and empty states that keep controls unavailable or clearly state when no runtime objects are reported.

API routes consumed:

- `GET /api/v1/operations/overview`
- `GET /api/v1/operations/accounts/{account_id}`
- `GET /api/v1/operations/deployments/{deployment_id}`
- `POST /api/v1/operations/deployments/{deployment_id}/pause`
- `POST /api/v1/operations/deployments/{deployment_id}/resume`
- `POST /api/v1/operations/accounts/{account_id}/pause`
- `POST /api/v1/operations/accounts/{account_id}/resume`
- `POST /api/v1/operations/global/kill`
- `POST /api/v1/operations/global/resume`
- `POST /api/v1/operations/accounts/{account_id}/flatten`
- `POST /api/v1/operations/deployments/{deployment_id}/flatten`

Safety states displayed:

- `system_recovery_active`
- `global_kill_active`
- stale broker sync state and stale reason
- `blocked_recovery` as blocked and visually urgent
- `recovered_ready` as ready but explicitly not running
- flatten `unsupported_not_ready` responses as warning/not-ready operator feedback

Controls implemented:

- Pause deployment
- Resume deployment
- Pause account
- Resume account
- Global kill
- Global resume
- Flatten account/deployment request buttons with confirmation and safe unsupported/not-ready display

Tests run:

- `npm.cmd test`
- `python -m pytest backend/tests -q`
- `python -m compileall -q backend/app backend/tests`

Test results:

- Frontend tests/build: `10 passed`; architecture check passed
- Full backend suite: `369 passed`
- Compile: passed

## 2026-04-24 16:26 ET - Paper Runtime End-to-End Smoke Harness

Files created:

- `backend/tests/smoke/test_paper_runtime_smoke.py`

Implementation:

- Added a deterministic backend smoke harness for Broker Runtime - Paper using a mocked Alpaca trading client.
- Exercised the runtime path from feature computation and signal evaluation through strategy controls, risk sizing, portfolio governor approval, internal order creation, Alpaca adapter submission, BrokerSync ledger update, SQLite order persistence, broker mapping persistence, and Operations Center overview projection.
- Verified Alpaca adapter broker-side idempotency by submitting the same internal order twice and confirming the second call returns the existing `client_order_id` result without a duplicate submit.
- Verified startup recovery after a submitted order does not create a duplicate internal order or submit a duplicate broker order.
- Verified Operations overview reports recovered runtime state as `recovered_ready` and not running after recovery.
- Verified stale broker sync blocks new opens through governor freshness input.
- Verified global kill blocks new opens while preserving existing broker truth, broker mapping, and Operations visibility.

Safety scope:

- Backend smoke tests only.
- No frontend changes.
- No live trading.
- No real Alpaca credentials.
- No new trading logic.
- Alpaca behavior is mocked at the trading-client boundary.

Tests run:

- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests/smoke/test_paper_runtime_smoke.py -q`
- `python -m pytest backend/tests -q`

Test results:

- Compile: passed
- Paper runtime smoke harness: `6 passed`
- Full backend suite: `375 passed`

## 2026-04-24 16:29 ET - Alpaca Paper Integration Opt-In Guard

Files created:

- `backend/tests/integration/test_alpaca_paper_integration.py`
- `pytest.ini`

Implementation:

- Added an explicit opt-in Alpaca paper integration test marked `integration` and `alpaca_paper`.
- Real Alpaca paper checks are skipped unless `RUN_ALPACA_PAPER_INTEGRATION=1` is present.
- The integration test loads `.env` only after the opt-in flag passes.
- The integration test validates paper environment guardrails before constructing `AlpacaBrokerAdapter`.
- The integration test performs read-only polling only: market clock, account snapshot, positions, and open orders.
- No real paper order submission is performed by the integration test.
- Existing unit and smoke tests continue to use mocked Alpaca clients with `load_env=False` or injected trading clients.

Safety scope:

- Normal `pytest` runs do not submit real Alpaca paper orders.
- Real Alpaca credentials in `.env` are not enough to run integration checks.
- `ALPACA_BASE_URL` must be `https://paper-api.alpaca.markets` when the opt-in integration is enabled.
- Order placement remains reserved for manual tools with their own confirmation/market-open guards.

Tests run:

- `python -m pytest backend/tests/integration/test_alpaca_paper_integration.py -q`
- `python -m pytest backend/tests/smoke/test_paper_runtime_smoke.py -q`
- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests -q`

Test results:

- Alpaca paper integration default behavior: `1 skipped`
- Paper runtime smoke harness: `6 passed`
- Compile: passed
- Full backend suite: `375 passed, 1 skipped`

## 2026-04-24 17:12 ET - Vite Frontend Dev Server With Operations API Proxy

Files created:

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/vite.config.js`

Files updated:

- `.gitignore`
- `frontend/scripts/check-frontend.mjs`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Converted the frontend into a minimal Vite app runnable from `frontend` with `npm run dev`.
- Added Vite scripts for `dev`, `build`, `preview`, and `test`.
- Added Vite dev-server proxy routing `/api` to `http://127.0.0.1:8000`.
- Preserved the Operations Center Vite entry through `frontend/index.html` and `frontend/src/main.js`.
- Kept the Operations API client on relative `/api/v1/operations/...` paths; no backend host is hardcoded in application code.
- Tightened the frontend architecture scanner to ignore generated `dist` and dependency `node_modules` folders.
- Normalized `.gitignore` and ignored Vite-generated `frontend/dist/` and `frontend/node_modules/`.

Proxy behavior:

- Browser requests from `http://127.0.0.1:5173/api/v1/operations/overview` are proxied by Vite to `http://127.0.0.1:8000/api/v1/operations/overview`.
- Normal frontend dev does not require CORS because requests remain same-origin from the browser's perspective.

Architecture preserved:

- Frontend calls only Operations API routes.
- No frontend imports or calls to BrokerAdapter, Alpaca, OrderManager, BrokerSync internals, FeatureEngine, or SignalEngine.

Tests run:

- `cd frontend; npm install`
- `cd frontend; npm test`
- `cd frontend; npm run build`
- `cd frontend; npm run dev`
- `python -m pytest backend/tests -q`

Validation results:

- `npm install`: passed, no vulnerabilities
- `npm test`: `10 passed`; architecture check passed
- `npm run build`: Vite production build passed
- `npm run dev`: Vite started at `http://127.0.0.1:5173/`
- Vite page probe: `GET /` returned `200`
- Vite proxy probe: `GET /api/v1/operations/overview` returned `200` from the backend Operations API
- Full backend suite: `375 passed, 1 skipped`

## 2026-04-24 17:23 ET - Operations Center Detail View Navigation

Files updated:

- `frontend/src/operationsCenter.js`
- `frontend/src/styles.css`
- `frontend/tests/operationsCenter.test.mjs`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Added clickable Broker Account and Deployment cards with keyboard activation.
- Added selected card highlighting and a clear detail option.
- Added account/deployment detail panel state for empty, loading, loaded, and error views.
- Cleared previous detail data before each detail fetch so stale or partial data is not shown silently.
- Expanded Account Detail to show broker account snapshot, positions, open broker orders, sync freshness, and pause/resume controls.
- Expanded Deployment Detail to show runtime status, program id/version, governor state, open orders, trades, fills, market/sync/decision timestamps, and pause/resume controls.

Operations API usage:

- Account selection calls `GET /api/v1/operations/accounts/{account_id}`.
- Deployment selection calls `GET /api/v1/operations/deployments/{deployment_id}`.
- Existing pause/resume and flatten controls continue to call only Operations API routes.

Architecture preserved:

- Frontend calls only Operations API routes.
- No frontend imports or calls to BrokerAdapter, Alpaca, OrderManager, BrokerSync internals, FeatureEngine, or SignalEngine.

Validation results:

- `cd frontend; npm test`: `15 passed`; architecture check passed.
- `cd frontend; npm run build`: Vite production build passed; architecture check passed.
- `python -m pytest backend/tests/unit/api/test_operations_routes.py backend/tests/unit/operations/test_operations_center_service.py`: `18 passed`.

## 2026-04-24 17:34 ET - Local Operations Center Demo Seed

Files created:

- `backend/app/operations/demo_seed.py`
- `backend/app/operations/runtime_service.py`
- `backend/scripts/__init__.py`
- `backend/scripts/seed_operations_demo.py`
- `backend/tests/unit/operations/test_operations_demo_seed.py`

Files updated:

- `backend/app/api/routes/operations.py`
- `backend/app/operations/service.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Added explicit local/demo-only Operations Center seeding via `python -m backend.scripts.seed_operations_demo`.
- Added `SEED_OPERATIONS_DEMO=1` support for the Operations API dependency to seed and read the local demo SQLite store.
- Added optional `OPERATIONS_RUNTIME_DB_PATH` support for pointing the Operations API at an explicit local runtime store.
- Seeded one demo broker account snapshot, one broker sync freshness record, one `recovered_ready` deployment runtime state, and one demo governor state.
- Kept demo state at zero open orders and zero open positions.
- Added a projection-only deployment-to-account mapping so the demo deployment is associated with the demo account without creating orders.

Safety and architecture:

- Demo seeding is not enabled by default.
- The seed path writes only to a local SQLite runtime/demo store.
- No Alpaca imports, calls, credentials, or network broker access are used.
- No real or internal orders are created.
- Broker truth outside the local persistence/demo store is not mutated.

Validation results:

- `python -m pytest backend/tests/unit/operations/test_operations_demo_seed.py backend/tests/unit/operations/test_operations_center_service.py backend/tests/unit/api/test_operations_routes.py`: `22 passed`.
- `cd frontend; npm test`: `15 passed`; architecture check passed.
- `python -m pytest backend/tests -q`: `379 passed, 1 skipped`.
- `cd frontend; npm run build`: Vite production build passed; architecture check passed.
- `python -m backend.scripts.seed_operations_demo`: seeded the local temp demo store.
- In-process Operations API projection with `SEED_OPERATIONS_DEMO=1`: `1` account, `1` deployment, `0` open orders, `0` open positions; account and deployment detail projections loaded.
- `cd frontend; npm run dev`: Vite started and `GET /` returned `200`.
- Backend server start with `python -m uvicorn backend.app.api.server:app --host 127.0.0.1 --port 8000` could not be completed in this environment because `uvicorn` is not installed.

## 2026-04-24 17:50 ET - Real Alpaca Paper Broker Account Setup

Files created:

- `backend/app/broker_accounts/__init__.py`
- `backend/app/broker_accounts/models.py`
- `backend/app/broker_accounts/runtime_service.py`
- `backend/app/broker_accounts/service.py`
- `backend/app/api/routes/broker_accounts.py`
- `backend/tests/unit/api/test_broker_accounts_routes.py`
- `backend/tests/unit/broker_accounts/test_alpaca_paper_account_service.py`

Files removed:

- `backend/app/operations/demo_seed.py`
- `backend/scripts/__init__.py`
- `backend/scripts/seed_operations_demo.py`
- `backend/tests/unit/operations/test_operations_demo_seed.py`

Implementation:

- Removed the local Operations Center demo seed path and disabled demo account surfacing through Operations routes.
- Added canonical `BrokerAccount` metadata with `id`, `display_name`, `provider`, `mode`, `credentials_ref`, `validation_status`, latest account snapshot, broker sync freshness, and `created_at`.
- Added `POST /api/v1/broker-accounts/alpaca-paper` with input limited to `display_name`, `api_key`, and `api_secret`.
- Added an Operations Center account setup panel for Alpaca paper accounts only; the UI does not ask for base URL, API endpoint, or environment URL.
- Persisted broker accounts separately from broker truth so Operations Center only shows canonical real broker accounts.
- Added durable broker position snapshots so account detail can show positions synced through broker sync.

Endpoint and validation behavior:

- `AlpacaBrokerAdapter` now derives endpoints from mode: `BROKER_PAPER` uses `https://paper-api.alpaca.markets`; `BROKER_LIVE` maps to `https://api.alpaca.markets` for future support.
- External/custom base URL injection is rejected, and `ALPACA_BASE_URL` is ignored by the adapter.
- Account creation validates read-only through Alpaca account snapshot, positions, and open orders calls.
- Invalid validation returns an operator-readable error and does not persist a BrokerAccount.
- After validation, broker truth is written only through `BrokerSync.sync_account`, `BrokerSync.sync_positions`, `BrokerSync.sync_open_orders`, and sync freshness recording.

Safety constraints:

- Paper mode only; live account creation remains disabled.
- No order submission during account validation.
- No automatic deployment creation.
- No automatic trading.
- No fake or demo account injection into Operations Center.

Validation results:

- `python -m pytest backend/tests -q`: `385 passed, 1 skipped`.
- `cd frontend; npm test`: `17 passed`; architecture check passed.
- `cd frontend; npm run build`: Vite production build passed; architecture check passed.

## 2026-04-24 17:56 ET - Runtime DB Path Dev Fallback and Production Guard

Files changed:

- `backend/app/config/runtime_paths.py`
- `backend/app/api/routes/broker_accounts.py`
- `backend/app/api/routes/operations.py`
- `backend/app/broker_accounts/runtime_service.py`
- `backend/app/operations/runtime_service.py`
- `backend/tests/unit/config/test_runtime_paths.py`

Implementation:

- Added `get_runtime_db_path()` as the shared runtime database path source.
- When `OPERATIONS_RUNTIME_DB_PATH` is set, the configured path is used and its parent directory is created.
- When the variable is missing in local development, the backend falls back to `data/runtime.db`, creates `data/`, and logs `Using default runtime DB path for local development`.
- Broker account creation and Operations runtime service construction now use the same runtime DB path helper, keeping broker account validation, persistence projections, and recovery-facing runtime state aligned on one SQLite store.
- Preserved route-test compatibility under installed FastAPI by exposing the existing single-method route metadata and keeping direct operator route errors catchable.

Production safety:

- `ENV=production` or `ENV=prod` disables fallback and requires `OPERATIONS_RUNTIME_DB_PATH`.
- `OPERATIONS_REQUIRE_RUNTIME_DB_PATH=true` also disables fallback for explicit fail-closed deployments.
- Production mode without an explicit runtime DB path raises a clear `RuntimeError`.

Validation results:

- `python -m pytest backend/tests/unit/config/test_runtime_paths.py backend/tests/unit/broker_accounts/test_alpaca_paper_account_service.py backend/tests/unit/operations/test_operations_center_service.py backend/tests/unit/runtime/test_recovery_orchestrator.py -q`: `28 passed`.
- `.venv\Scripts\python.exe -m pytest backend/tests -q`: `390 passed, 1 skipped`, with one third-party `websockets.legacy` deprecation warning.

## 2026-04-24 18:55 ET - Duplicate Alpaca Paper Broker Account Prevention

Files changed:

- `.gitignore`
- `backend/app/broker_accounts/models.py`
- `backend/app/broker_accounts/service.py`
- `backend/app/brokers/alpaca.py`
- `backend/app/brokers/models.py`
- `backend/app/persistence/models.py`
- `backend/app/persistence/runtime_store.py`
- `frontend/src/operationsCenter.js`
- `frontend/tests/operationsCenter.test.mjs`

Implementation:

- Preserved Alpaca's external account id from account responses on broker account snapshots.
- Added `external_account_id` to canonical `BrokerAccount` records.
- Added SQLite uniqueness on `provider + mode + external_account_id` and migrated existing runtime stores to add the new column before creating the unique index.
- Made Alpaca paper account creation idempotent: credentials are validated read-only, the Alpaca account id is extracted, and an existing canonical account is returned instead of creating a duplicate.
- Duplicate attempts refresh validation, broker snapshots, positions, open orders, and sync freshness for the existing account id.
- Broker account API responses now include `already_exists`.
- Operations Center shows `This Alpaca paper account is already registered.`, refreshes the overview, and selects/highlights the existing account.

Safety:

- Invalid credentials still fail without persisting a BrokerAccount.
- Account validation remains read-only and does not submit orders.
- Duplicate prevention is enforced both in service logic and at the SQLite persistence layer.

Validation results:

- `.venv\Scripts\python.exe -m compileall -q backend/app backend/tests`: passed.
- `.venv\Scripts\python.exe -m pytest backend/tests -q`: `392 passed, 1 skipped`, with one third-party `websockets.legacy` deprecation warning.
- `npm.cmd test --prefix frontend`: `18 passed`; frontend check passed.
- `npm.cmd run build --prefix frontend`: Vite production build passed; frontend check passed.

## 2026-04-24 19:07 ET - Broker Runtime Trading Loop Orchestrator

Files changed:

- `backend/app/runtime/broker_runtime_orchestrator.py`
- `backend/app/runtime/models.py`
- `backend/app/runtime/__init__.py`
- `backend/app/operations/models.py`
- `backend/app/operations/service.py`
- `backend/tests/unit/runtime/test_broker_runtime_orchestrator.py`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Added a BROKER_PAPER runtime orchestrator service with deployment start/stop, deterministic `run_once`, completed-bar processing, and recovery resume lifecycle methods.
- The service loads active paper deployments, verifies paper broker account mode, recovery readiness, broker sync freshness, and ControlPlane kill/pause gates before opening risk.
- Completed bars are delegated through the existing runtime pipeline, preserving FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, and BrokerSync authority boundaries.
- Broker results are applied through BrokerSync, sync failures degrade the runtime and block subsequent opens, and duplicate restart processing is prevented by persisted last-bar timestamps.
- Runtime loop state now persists last bar, signal, governor decision, order id, broker sync timestamp, and last error.
- Operations Center deployment detail projection now exposes runtime loop state and timestamps without adding a duplicate monitor page.

Scope kept out:

- No FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, or BrokerSync core logic changes.
- No BROKER_LIVE execution path was enabled.
- No BrokerAdapter usage was added to Chart Lab or Sim Lab.
- No duplicate order authority, broker truth writer, or standalone monitor page was introduced.

Validation results:

- `python -m pytest backend/tests/unit/runtime -q`: `31 passed`.
- `python -m pytest backend/tests/unit/pipeline backend/tests/unit/governor backend/tests/unit/orders backend/tests/unit/brokers backend/tests/unit/runtime -q`: `136 passed`.
- `python -m pytest backend/tests -q`: `407 passed, 1 skipped`.
- `python -m compileall -q backend/app backend/tests`: passed.

## 2026-04-24 19:41 ET - Paper Operations Hardening and Runbook

Files changed:

- `backend/app/api/routes/broker_accounts.py`
- `backend/app/api/routes/operations.py`
- `backend/app/broker_accounts/__init__.py`
- `backend/app/broker_accounts/models.py`
- `backend/app/broker_accounts/service.py`
- `backend/app/operations/__init__.py`
- `backend/app/operations/models.py`
- `backend/app/operations/service.py`
- `backend/app/persistence/runtime_store.py`
- `backend/tests/unit/api/test_broker_accounts_routes.py`
- `backend/tests/unit/api/test_operations_routes.py`
- `backend/tests/unit/broker_accounts/test_alpaca_paper_account_service.py`
- `backend/tests/unit/operations/test_operations_center_service.py`
- `frontend/src/api/operations.js`
- `frontend/src/operationsCenter.js`
- `frontend/tests/operationsCenter.test.mjs`
- `docs/operations/PAPER_RUNTIME_SHIP_GATE.md`
- `docs/operations/DAY_1_PAPER_RUNBOOK.md`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Removed the broken/manual Alpaca smoke artifact from the active workspace; no `manual_alpaca_check.py` remains.
- Added restart-safe global kill coverage proving persisted ControlPlane state is rehydrated and new opens stay blocked after restart.
- Documented and tested the current paper-mode Operations API contract: local paper operations routes remain unauthenticated by design.
- Added Alpaca paper credential replacement for existing broker accounts with masked-secret rejection, mode mismatch handling, invalid credential handling, provider-unreachable status, active runtime blocking, and stale broker sync marking after replacement.
- Added safe broker account deletion/archive behavior with hard delete only for dependency-free accounts and archival for historical accounts.
- Added deletion blockers for running/degraded/blocked deployments, open internal orders, open broker orders, open positions, stale sync, and unknown sync.
- Added Operations order detail projection with internal order truth, broker mapping truth, broker status/freshness, and fill summary without raw Alpaca payloads or credentials.
- Updated Operations Center UI/API client for credential replacement, safe account deletion confirmation, order detail navigation, and separated internal/broker/fill truth panels.
- Added Paper Runtime Ship Gate and Day-1 Paper Trading Runbook.

Tests added:

- Broker account credential replacement, masked credential rejection, invalid credential rejection, mode mismatch rejection, stale sync marking, runtime open blocking after replacement, and active runtime replacement blocking.
- Broker account deletion blockers, archive-vs-hard-delete behavior, and preservation of historical references.
- Operations restart-safe global kill and order detail projection tests.
- API route tests for credential replacement, deletion, unauthenticated local paper order detail behavior, and order detail response models.
- Frontend tests for credential replacement/deletion API calls, order detail rendering, unknown broker state rendering, and order-detail navigation controls.

Scope kept out:

- No live trading path was added.
- No manual trade placement was added.
- No FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, or BrokerSync core logic was changed.
- BrokerSync remains the broker truth writer, OrderManager remains the internal order creator, and BrokerAdapter remains the only Alpaca caller.
- Frontend still never calls Alpaca directly.

Validation results:

- `python -m compileall -q backend/app backend/tests`: passed.
- `python -m pytest backend/tests/unit/runtime -q`: `31 passed`.
- `python -m pytest backend/tests/unit/control_plane -q`: `13 passed`.
- `python -m pytest backend/tests/unit/operations -q`: `11 passed`.
- `python -m pytest backend/tests/unit/brokers -q`: `63 passed`.
- `python -m pytest backend/tests/unit/orders -q`: `16 passed`.
- `python -m pytest backend/tests -q`: `425 passed, 1 skipped`.
- `cd frontend && npm.cmd run build`: Vite production build passed; frontend check passed.
- `cd frontend && npm.cmd test`: `21 passed`; frontend check passed.
## 2026-04-24 20:36 ET

- Implemented Data Intent and Market Data Service Resolver for Services Center routing.
- Created `backend/app/services/data_intent.py`, `backend/app/services/service_resolver.py`, and `backend/app/services/__init__.py`.
- Added capability models, provider defaults for Alpaca/Yahoo, auto/default/explicit selection modes, UI-ready resolver explanations, and rejected-candidate reasons.
- Added frontend Data Source resolver panel rendering in `frontend/src/operationsCenter.js` with supporting styles in `frontend/src/styles.css`.
- Created `docs/architecture/services_architecture.md` covering Data Intent, resolver behavior, capability model, stream separation, selection modes, and non-goals.
- Added backend tests in `backend/tests/unit/services/test_service_resolver.py` and `backend/tests/unit/runtime/test_data_intent_runtime_boundaries.py`.
- Added frontend test coverage for displaying detected intent, selected service, and rejected services.
- Scope kept out: real Alpaca streaming, provider fallback/A-B testing, per-account data-provider overrides, Broker Accounts-as-Services, frontend provider calls, and changes to FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, or BrokerSync.
- Validation commands run:
  - `python -m compileall -q backend/app backend/tests`
  - `python -m pytest backend/tests/unit/services -q`
  - `python -m pytest backend/tests/unit/runtime -q`
  - `python -m pytest backend/tests -q`
  - `cd frontend && npm run build` attempted; blocked by local PowerShell `npm.ps1` execution policy.
  - `cd frontend && npm.cmd run build`
  - `cd frontend && npm test` attempted; blocked by local PowerShell `npm.ps1` execution policy.
  - `cd frontend && npm.cmd test`
- Test results: compile passed; backend service tests passed `12 passed`; backend runtime tests passed `32 passed`; full backend tests passed `438 passed, 1 skipped`; frontend build passed; frontend tests passed `22 passed`.
## 2026-04-24 20:52 ET

- Implemented Services Center CRUD and provider validation for Market Data Services and AI Services.
- Created persistent Services Center models/service APIs with non-secret credential references, validation status fields, default enforcement, disable behavior, and persisted market data resolver integration.
- Added backend routes in `backend/app/api/routes/services.py` and registered them with the API server.
- Added frontend Services Center page, API client, renderer, summary cards, Market Data and AI tabs, provider-aware forms, service actions, validation history display, and resolver panel display.
- Files created/updated include `backend/app/services/models.py`, `backend/app/services/service.py`, `backend/app/services/validation.py`, `backend/app/services/runtime_service.py`, `backend/app/api/routes/services.py`, `frontend/src/api/services.js`, `frontend/src/servicesCenter.js`, `frontend/services.html`, `frontend/vite.config.js`, `frontend/scripts/check-frontend.mjs`, `frontend/tests/servicesCenter.test.mjs`, and architecture/log docs.
- Tests added for Market Data CRUD, masked credential rejection, validation outcomes, default rules, disabled resolver rejection, AI CRUD/default rules, persisted resolver behavior, Services API calls, Services Center rendering, provider-aware fields, actions, resolver display, and no raw secret rendering.
- Scope kept out: real market data streaming, runtime trading wiring to Services, Broker Accounts-as-Services, frontend provider calls, per-account data provider overrides, live trading behavior, and changes to FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, or BrokerSync.
- Validation commands run:
  - `python -m compileall -q backend/app backend/tests`
  - `python -m pytest backend/tests/unit/services -q`
  - `python -m pytest backend/tests/unit/runtime -q`
  - `python -m pytest backend/tests -q`
  - `cd frontend && npm.cmd run build`
  - `cd frontend && npm.cmd test`
- Test results: compile passed; backend service tests passed `17 passed`; backend runtime tests passed `32 passed`; full backend tests passed `443 passed, 1 skipped`; frontend build passed; frontend tests passed `27 passed`.

## 2026-04-24 22:42 ET

Implemented the next Services Center UX pass requested for resolver-first decision visibility and safer service management interaction patterns.

Files updated:
- `frontend/services.html`
- `frontend/src/api/services.js`
- `frontend/src/servicesCenter.js`
- `frontend/src/styles.css`
- `frontend/tests/servicesCenter.test.mjs`
- `docs/architecture/services_architecture.md` (no schema or backend routing changes in this pass)
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

Implementation:

- Added decision-oriented service mode labels:
  - `Auto (Recommended)`
  - `Default (system default)`
  - `Manual (explicit selection)`
- Added an explicit Data Intent panel showing:
  - consumer
  - timeframe
  - date range
  - streaming required
  - intraday required
- Added resolver result rendering with:
  - selected service summary
  - human-readable explanation
  - reason code
  - rejected candidates (collapsible with per-candidate reasons)
- Refined provider-aware service forms:
  - Alpaca form shows mode, key, secret
  - Yahoo form omits credential inputs and shows historical-only context
  - AI form shows key input plus capability label (where applicable)
- Added visible service decision context:
  - status and validation metadata in cards
  - last validated timestamp
  - capability summary chips
  - clear disabled-state styling and action prompts
- Strengthened action safety messaging:
  - confirmation for set-default replacement and default-disable warnings
  - explicit explanation for blank versus replacement credential behavior
- Updated resolver UX tests to cover selected/rejected display, mode labels, intent visibility, provider-aware field behavior, and no raw secret rendering.

Scope kept out:

- No live market-data streaming wiring.
- No runtime trading wiring from Services Center.
- No Broker Accounts merged into Services.
- No frontend provider direct calls.
- No FeatureEngine, SignalEngine, PortfolioGovernor, OrderManager, BrokerAdapter, or BrokerSync changes in this pass.
- No runtime provider fallback / A/B routing.
- No live trading behavior.

Validation commands run:
- `cd frontend && npm.cmd run build`
- `cd frontend && npm.cmd test`
- `python -m pytest backend/tests/unit/services -q`
- `python -m pytest backend/tests -q`
- `python -m compileall -q backend/app backend/tests`

Validation results:
- Frontend build: passed
- Frontend tests: `29 passed`
- Backend services tests: `17 passed`
- Backend full suite: `443 passed, 1 skipped`
- `python -m compileall -q backend/app backend/tests`: passed

## 2026-04-24 23:13 ET

Refined the Services Center UX against the redline contract so the page reflects persisted backend records, current Data Intent form state, and resolver API output instead of hardcoded selected-service recommendations.

Files updated:
- `frontend/src/servicesCenter.js`
- `frontend/tests/servicesCenter.test.mjs`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

What changed:
- Updated the page header copy to frame Services Center as external-provider configuration with Data Intent based service selection.
- Changed Market Data and AI creation to collapsed action-first panels opened by `+ Add Market Data Service` and `+ Add AI Service`.
- Made provider-specific form fields render only when applicable:
  - Alpaca shows mode, API key, and API secret.
  - Yahoo omits credential fields and shows historical-only provider context.
  - AI providers show API key and capability label when applicable.
- Added summary cards that use real configured services, default service records, backend capability summaries, and real status counts.
- Added service-card `Best For` sections derived from backend capability fields or AI capability labels, not service names.
- Reworked the resolver area:
  - mode labels are `Auto (Recommended)`, `Default`, and `Manual Selection`.
  - explanations clarify auto/default/manual behavior.
  - action label is `Preview Service Decision`.
  - selected-service and no-compatible-service states come from resolver output.
  - missing resolver explanations now surface as a backend contract issue instead of silent fallback text.
  - rejected services render only from resolver response candidates.
- Kept raw credentials out of rendered DOM and ensured masked placeholders are not submitted as replacement secrets.

Tests added/updated:
- Services page render and no raw secret checks.
- Collapsed Market Data creation panel by default.
- Expanded Market Data provider-aware form checks.
- Yahoo credential-field hiding.
- AI services render from backend fixture data.
- Resolver selected-service display from resolver response.
- No-compatible-service resolver state.
- Rejected candidates from resolver response.
- Source-level guard against hardcoded selected provider recommendations.

Scope kept out:
- No real streaming wiring.
- No broker account behavior.
- No live trading.
- No unrelated pages.
- No hardcoded Alpaca/Yahoo selected service recommendations.
- No Broker Accounts merged into Services.

Validation commands run:
- `cd frontend && npm.cmd run build`
- `cd frontend && npm.cmd test`
- `python -m pytest backend/tests/unit/services -q`
- `python -m pytest backend/tests -q`
- `python -m compileall -q backend/app backend/tests`

Validation results:
- Frontend build: passed.
- Frontend tests: `33 passed`.
- Backend services tests: `17 passed`.
- Backend full suite: `443 passed, 1 skipped`.
- Compileall: passed.

## 2026-04-24 23:27 ET

Implemented lightweight Services Resolver capability learning and capability metadata display.

Files created:
- `backend/app/services/capability_profiles.py`

Files updated:
- `backend/app/services/models.py`
- `backend/app/services/service.py`
- `backend/app/services/service_resolver.py`
- `backend/app/services/validation.py`
- `backend/tests/unit/services/test_service_resolver.py`
- `backend/tests/unit/services/test_services_center_service.py`
- `frontend/src/servicesCenter.js`
- `frontend/tests/servicesCenter.test.mjs`
- `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`

What changed:
- Added provider capability profiles as lightweight, docs-informed baselines instead of embedding provider selection rules in the resolver.
- Added persisted market-data capability metadata:
  - `capability_source`
  - `capability_notes`
  - `capability_updated_at`
  - `capability_manual_override`
- Validation can now update learned capabilities, source, and notes from validator responses.
- Manual capability override is supported through Market Data service create/update payloads via optional `capabilities` and `capability_notes`.
- Manual overrides persist across validation so operators can correct provider metadata without provider-specific code changes.
- Resolver hard filters still reject incompatible services for missing streaming, realtime, intraday, historical, daily, weekly, monthly, or long-range support.
- Auto selection no longer uses provider-name bonuses; ranking is based on compatibility, default status, cost class, latency class, and intent shape.
- Auto mode now prefers a compatible default service before best-fit scoring.
- Rejected candidates now include service names as UI-friendly metadata.
- Services Center cards now show capability source, capability updated timestamp, manual override state, and provider limitation notes in a collapsible details section.

Tests added/updated:
- Validation-learned capabilities are stored on service records.
- Learned lack of intraday support causes resolver hard rejection for intraday intent.
- Manual capability override can evolve a service from historical-only to intraday-capable.
- Auto resolver prefers a compatible default before best-fit scoring.
- Frontend renders provider capability notes/source and keeps raw secrets hidden.

Scope kept out:
- No real streaming.
- No multi-provider blending.
- No full scoring engine.
- No broker account behavior.
- No live trading behavior.
- No frontend direct provider calls.

Validation commands run:
- `python -m pytest backend/tests/unit/services -q`
- `cd frontend && npm.cmd test`
- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests -q`
- `cd frontend && npm.cmd run build`

Validation results:
- Backend services tests: `20 passed`.
- Frontend tests: `33 passed`.
- Compileall: passed.
- Backend full suite: `446 passed, 1 skipped`.
- Frontend build: passed.

## 2026-04-24 23:28 ET

Implemented a Services Resolver correction focused on capability-based compatibility.

Implemented:
- Resolver enforces intraday and streaming constraints before selecting a Market Data Service.
- Incompatible providers are rejected instead of ranked as candidates.
- Resolver output includes an explanation and rejected candidates with reason codes.
- Added capability metadata fields and validation-driven updates as a direction toward dynamic capability learning; this is not a full online learning or provider-discovery system.

Scope kept out:
- No real streaming.
- No multi-provider blending.
- No full scoring engine.
- No live trading behavior.
- No frontend direct provider calls.

Validation:
- `python -m pytest backend/tests/unit/services -q`
- `cd frontend && npm.cmd test`
- `python -m compileall -q backend/app backend/tests`
- `python -m pytest backend/tests -q`
- `cd frontend && npm.cmd run build`

Result:
- Backend services tests: `20 passed`.
- Frontend tests: `33 passed`.
- Compileall: passed.
- Backend full suite: `446 passed, 1 skipped`.
- Frontend build: passed.

## 2026-04-25 02:30 ET - Slice 1: Mode-naming-contract migration (plan_review §G Phase 1)

Task:
- Phase 1 from plan_review.md §G: add banned-name CI lint, migrate `backend/app/services/` into canonical `market_data/` and `ai/` buckets, eliminate `ServiceMode.PAPER/LIVE`, drop `mode` field from market-data records (per A1).

Files changed:
- backend/app/market_data/data_intent.py (new)
- backend/app/market_data/resolver.py (new — was services/service_resolver.py; ServiceMode + mode field removed)
- backend/app/market_data/capability_profiles.py (new)
- backend/app/market_data/models.py (new — MarketDataServiceRecord; no mode field; MarketDataValidationStatus enum)
- backend/app/market_data/validation.py (new — validator no longer takes mode)
- backend/app/market_data/catalog.py (new — MarketDataServiceCatalog replaces ServicesCenterService market half)
- backend/app/market_data/runtime.py (new)
- backend/app/market_data/__init__.py (updated: 40 exports incl. catalog/resolver/data_intent)
- backend/app/ai/__init__.py (new)
- backend/app/ai/providers.py (new — AIProvider records; AIValidationStatus enum; AIProviderStatus enum)
- backend/app/ai/validation.py (new — AIProviderValidator; no shared status with market-data)
- backend/app/ai/catalog.py (new — AIProviderCatalog)
- backend/app/ai/runtime.py (new)
- backend/app/api/routes/__init__.py (updated: ai_router + market_data_router; services_router removed)
- backend/app/api/routes/market_data.py (new — /api/v1/market-data/services{,/resolve,/{id}/...})
- backend/app/api/routes/ai.py (new — /api/v1/ai/providers{,/{id}/...})
- backend/app/api/routes/services.py (deleted)
- backend/app/services/__init__.py (deleted)
- backend/app/services/capability_profiles.py (deleted)
- backend/app/services/data_intent.py (deleted)
- backend/app/services/models.py (deleted)
- backend/app/services/runtime_service.py (deleted)
- backend/app/services/service.py (deleted)
- backend/app/services/service_resolver.py (deleted)
- backend/app/services/validation.py (deleted)
- backend/tests/unit/lint/test_no_banned_mode_enums.py (new — AST scan; allowlist domain/trading_mode.py)
- backend/tests/unit/market_data/test_resolver.py (new — was tests/unit/services/test_service_resolver.py)
- backend/tests/unit/market_data/test_market_data_catalog.py (new — was tests/unit/services/test_services_center_service.py market half)
- backend/tests/unit/ai/test_ai_catalog.py (new — was the AI half of test_services_center_service.py)
- backend/tests/unit/services/test_service_resolver.py (deleted)
- backend/tests/unit/services/test_services_center_service.py (deleted)
- backend/tests/unit/runtime/test_data_intent_runtime_boundaries.py (updated import: app.services -> app.market_data)
- frontend/src/api/services.js (updated: split into MARKET_DATA_PREFIX + AI_PREFIX; canonical paths)
- frontend/src/servicesCenter.js (updated: removed mode picker on Alpaca form, removed Mode <dt> in card, removed mode flag chip; serviceModeLabel -> serviceCredentialLabel; normalizeMarketDataForSubmit drops mode; edit/show form state drops mode; provider-select handler drops mode)
- frontend/tests/servicesCenter.test.mjs (updated: new test "Market data card no longer renders a Mode field"; new test "Market data create payload no longer carries a banned mode field"; assertions updated to canonical /api/v1/market-data/services and /api/v1/ai/providers paths)
- memory/MEMORY.md (new)
- memory/authority_docs.md (new)
- memory/validation_discipline.md (new)
- memory/decision_defaults.md (new)
- docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md (this entry)

Implemented:
- AST-based banned-name lint that fails CI when any `class *Mode*(*Enum*)` declares a member named exactly `PAPER` / `LIVE` or whose value is the bare string `"paper"`/`"live"`. Compound members like `LIVE_PREVIEW`/`LIVE_RUNTIME`/`BROKER_PAPER`/`BROKER_LIVE` are correctly skipped (verified via canary class).
- Full migration of `backend/app/services/` into canonical `market_data/` and `ai/` packages. `app/services/` directory deleted in entirety.
- `ServiceMode` enum removed; `mode` field removed from `MarketDataServiceRecord`, `MarketDataServiceConfig`, `MarketDataServiceWrite`. Market-data validators no longer accept a mode argument. Trading mode (`TradingMode`) is now owned exclusively by `BrokerAccount`.
- Two independent validation status enums (`MarketDataValidationStatus`, `AIValidationStatus`) — no shared types between market-data and AI buckets, per §I "AI Services and Market Data are separate systems."
- API split into two surfaces: `/api/v1/market-data/services{,/{id}{,/validate,/set-default,/disable},/resolve}` and `/api/v1/ai/providers{,/{id}{,/validate,/set-default,/disable}}`.
- Frontend client updated to canonical paths; `mode` removed from market-data form, card, payload, and state.
- Memory directory bootstrapped with authority-doc index, validation-discipline rule, and §16 decision defaults.

Scope kept out:
- Resolver `selection_mode` -> `selection_strategy` rename (defers to roadmap §11 Phase 1 work where the resolver becomes pipeline-aware).
- Standalone Services Center page deletion (UI restructure under Providers → Market Data Pipelines is part of Phase 1 Data Flow Lock).
- ProgramVersion `composition_hash` freeze and Evidence reproducibility extension (roadmap defers these to phases 4/5).
- Any FeatureEngine / streaming / broker-account behavior change.

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall: clean.
- Backend full suite: 542 passed, 1 skipped.
- Frontend tests: 35 passed.
- Frontend build: passed (10 source files).
- Lint canary verification: introduced a `class CanaryServiceMode(StrEnum): PAPER="paper"; LIVE="live"`; lint flagged both members with file/line/remediation; canary removed and lint re-ran clean.

Verification:
- Feature Engine did not call external providers.
- Resolver output was not hardcoded.
- No duplicate streaming path introduced.
- No architecture boundaries violated.
- Grep across backend/, frontend/src/, tools/ for `ServiceMode | backend.app.services | app/services | /api/v1/services` returns only history-marker docstrings — zero live code references to the deprecated bucket or path.

Commit:
- pending (working tree currently dirty with this slice; user has not yet requested commit).

## 2026-04-25 02:51 ET - Slice 1A: Resolver contract refresh (Phase 1 Data Flow Lock — final_roadmap §11)

Task:
- Lock resolver contract per §9 + §J: `selection_strategy` replaces `selection_mode`, per-symbol resolution rows, frozen-enum rejection codes (§12 stop 7), `resolver_input_hash` for replay equality, visibility fields.

Files changed:
- backend/app/market_data/resolver.py
- backend/app/market_data/catalog.py
- backend/app/market_data/__init__.py
- backend/tests/unit/market_data/test_resolver.py
- backend/tests/unit/market_data/test_market_data_catalog.py
- frontend/src/servicesCenter.js
- frontend/tests/servicesCenter.test.mjs

Implemented:
- `SelectionStrategy {AUTO, DEFAULT_PREFERRED, MANUAL_OVERRIDE}` (banned `mode` wording removed).
- `ResolverRejectionCode` 11-value frozen enum; `ResolverSelectionCode` 3-value enum; `InvocationContext` enum.
- `PerSymbolResolution` row type and `ResolverResult` with per-symbol rows + visibility fields (`resolver_version`, `resolver_input_hash`, `invocation_context`, `decided_at`).
- Deterministic `resolver_input_hash` over canonical JSON.

Scope kept out:
- `MarketDataPipeline` model (1B), `FeaturePlanner.data_requirements` (1C), SubscriptionManager (1D), real provider IO (Phase 2), Providers→Market Data Pipelines IA flip (1B).

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 551 passed, 1 skipped. Frontend: 36 passed. Build clean.

Verification:
- Feature Engine did not call external providers.
- Resolver output not hardcoded; `resolver_input_hash` deterministic.
- No duplicate streaming path introduced.
- No architecture boundaries violated (banned-name lint green).

Commit:
- pending (rolled into 1A-bis below before commit).

## 2026-04-25 03:10 ET - Slice 1A-bis: Architect-driven contract repairs

Task:
- Architect review of 1A surfaced four bugs/gaps + three new findings. Fix all before moving to 1B.

Files changed:
- backend/app/market_data/resolver.py
- backend/tests/unit/market_data/test_resolver.py
- backend/tests/unit/market_data/test_market_data_catalog.py
- frontend/src/servicesCenter.js
- frontend/tests/servicesCenter.test.mjs

Implemented:
- Dropped top-level result mirror; callers iterate `per_symbol_rows`. Added `ResolverDecision.PARTIAL` for honest aggregate.
- Added `ResolverRejectionCode.PROVIDER_NOT_VALIDATED` (12th code). Lossless `_VALIDATION_STATUS_TO_REJECTION` table covers all six `MarketDataValidationStatus` members; coverage guard test (`test_validation_status_to_rejection_table_covers_every_enum_member`) prevents drift.
- `resolver_input_hash` now projects services to identity-stable subset; cosmetic prose (`service_name`, `validation_message`, `credentials_ref`) excluded from hash.
- `MANUAL_OVERRIDE` with unknown service id now emits a synthetic `RejectedCandidate`.
- DISABLED precedence over validation_status documented + tested.
- Determinism contract documented in module docstring.
- Frontend renders per-symbol table; reads only from `per_symbol_rows`. PARTIAL aggregate shows yellow banner. Lint-style guard test asserts no top-level mirror reads remain in source.
- `RESOLVER_VERSION` bumped to `0.10.1`.

Scope kept out:
- `MarketDataPipeline` model (1B), Providers→Market Data Pipelines IA flip (1B), `FeaturePlanner.data_requirements` (1C), SubscriptionManager (1D).

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 567 passed, 1 skipped (+16 contract tests vs. 1A). Frontend: 38 passed (+2 contract tests). Build clean.

Verification:
- Feature Engine did not call external providers.
- Resolver `resolver_input_hash` is now identity-stable across cosmetic prose changes.
- No duplicate streaming path introduced.
- No architecture boundaries violated.

Commit:
- pending.

## 2026-04-25 03:44 ET - Slice 1B: MarketDataPipeline + Providers IA flip (Phase 1 §11)

Task:
- Phase 1 §11 deliverable 3-5: introduce first-class `MarketDataPipeline` model + registry; resolver populates real `pipeline_id`; flip IA from "Services Center" to "Providers → Market Data Pipelines" per §J. Single slice per architect verdict (no 1B-min split — dead code).

Files changed:
- backend/app/market_data/pipeline.py (new)
- backend/app/market_data/pipeline_registry.py (new)
- backend/app/market_data/runtime.py (factory)
- backend/app/market_data/__init__.py (exports)
- backend/app/market_data/resolver.py (pipeline_lookup parameter)
- backend/app/market_data/catalog.py (pipeline_registry kwarg on resolve)
- backend/app/api/routes/market_data.py (5 new pipeline endpoints + resolve wiring)
- backend/tests/unit/market_data/test_pipeline_registry.py (new)
- backend/tests/unit/market_data/test_resolver.py (4 new pipeline_id tests)
- backend/tests/integration/test_resolver_to_pipeline_id_e2e.py (new)
- frontend/providers.html (new)
- frontend/src/providers.js (new — replaces servicesCenter.js)
- frontend/src/api/pipelines.js (new)
- frontend/src/main.js (mount providers)
- frontend/index.html (nav: Services Center → Providers)
- frontend/vite.config.js (multi-page input: providers replaces services)
- frontend/scripts/check-frontend.mjs (import providers.js + api/pipelines.js)
- frontend/tests/marketDataPipelines.test.mjs (new)
- DELETED: frontend/services.html, frontend/src/servicesCenter.js, frontend/tests/servicesCenter.test.mjs

Implemented:
- `MarketDataPipeline` Pydantic model with `trading_mode: TradingMode | None` (BROKER_PAPER / BROKER_LIVE / None for vendor-only); validator rejects chart-lab/sim-lab modes.
- `MarketDataPipelineRegistry` with JSON persistence at `market_data_pipelines.json`. Default-per-provider invariant: `set_default_for_provider` un-sets siblings only within the same provider (Yahoo and Alpaca defaults coexist).
- `lookup_default_for_provider` returns the active default's id or None; disabled pipelines never resolve.
- Resolver accepts optional `pipeline_lookup` callable; populates `PerSymbolResolution.pipeline_id` for SELECTED rows only. REJECTED rows leave pipeline_id null. Lookup not invoked when no compatible service found.
- 5 new API endpoints: `GET/POST /pipelines`, `GET/PUT /pipelines/{id}`, `POST /pipelines/{id}/set-default`, `POST /pipelines/{id}/disable`. Resolve endpoint passes pipeline registry through.
- Bumped `RESOLVER_VERSION` to 0.11.0.
- Providers page hosts three tabs: Market Data Pipelines (default; carries Resolver Result Panel + debug), Market Data Services, AI Providers. Trading-mode dropdown offers only `BROKER_PAPER`/`BROKER_LIVE`/None — banned standalone `paper`/`live` strings never appear as form values. Resolver Result Panel reads only from `per_symbol_rows`.
- IA-flip enforcement test asserts `services.html`, `servicesCenter.js`, `servicesCenter.test.mjs` are absent and that no source still imports the deleted module.

Scope kept out:
- `FeaturePlanner.data_requirements` per-FeatureKey view (1C).
- FeatureEngine `SubscriptionManager` + FeatureKey-level dedup (1D).
- Real provider subscribe/unsubscribe wiring (Phase 2).
- SQLite migration of pipeline persistence (deferred until BarBuilder/streaming truth slice).

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 589 passed, 1 skipped (+22 vs slice 1A). Frontend: 37 passed (+15 new providers tests; legacy Services Center suite deleted). Build clean (providers.html replaces services.html).

Verification:
- Feature Engine did not call external providers.
- Resolver pipeline_lookup invoked exclusively for SELECTED rows.
- No duplicate streaming path introduced — pipelines are the canonical fan-out unit (§3 hard rule "one paid stream serves many accounts").
- No architecture boundaries violated (banned-name lint green; trading_mode validator rejects non-broker modes).

Commit:
- pending.

## 2026-04-25 04:29 ET - Slice 1C: FeaturePlan.data_requirements (Phase 1 §11.1)

Task:
- Add per-FeatureKey ``FeatureDataRequirement`` projection to ``FeaturePlan`` so the resolver / FeatureEngine subscription manager can pick a pipeline per FeatureKey (not per Deployment) — multiple keys in one plan may resolve to different pipelines.

Files changed:
- backend/app/features/registry.py (instrument_class field on FeatureRegistryEntry; portfolio features → "portfolio_state")
- backend/app/features/planner.py (FeatureDataRequirement model + _build_data_requirement; FeaturePlan.data_requirements tuple)
- backend/app/features/__init__.py (export FeatureDataRequirement)
- backend/tests/unit/features/test_feature_planner.py (10 new tests)

Implemented:
- ``FeatureDataRequirement`` per-FeatureKey: feature_key, timeframe, instrument_class, requires_streaming/realtime/intraday/historical/long_range_history, warmup_bars.
- Consumer-driven derivation: live consumers (live/runtime/paper/sim_stream) get streaming+realtime; backtest/sim_replay get historical; chart_lab gets historical; portfolio_governor uses internal portfolio state (no market-data demand).
- Daily/weekly/monthly + backtest → requires_long_range_history=True.
- Portfolio features (instrument_class="portfolio_state") never demand streaming or historical market data.
- data_requirements tuple is dedup-by-FeatureKey by construction (one row per unique key).

Scope kept out:
- SubscriptionManager wiring (1D).
- Pipeline-per-FeatureKey resolver lookup (1D will accept FeatureSpec, not just Provider).

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 599 passed, 1 skipped (+10 new planner tests). Frontend: 37 passed. Build clean.

Verification:
- Feature Engine still does not call external providers (no provider SDK imports added).
- data_requirements derived deterministically from (FeatureSpec, consumer, registry entry).
- No architecture boundaries violated.

Commit:
- pending.

## 2026-04-25 04:34 ET - Slice 1D: SubscriptionManager + Phase 1 exit gate

Task:
- Phase 1 §11.4-5 + exit gate: build the FeatureEngine ``SubscriptionManager`` so demand-dedup happens at the FeatureKey level, multiple Deployments share one subscription per key, and a single Deployment may resolve different keys to different pipelines.

Files changed:
- backend/app/features/subscription_manager.py (new)
- backend/app/features/__init__.py (exports)
- backend/tests/unit/features/test_subscription_manager.py (new — 12 tests)
- backend/tests/integration/test_feature_demand_to_pipeline_subscription_e2e.py (new — 3 acceptance tests)
- backend/tests/unit/lint/test_feature_engine_isolation.py (new — architecture lint per §12 stop 1)

Implemented:
- ``SubscriptionManager`` owns the canonical ``FeatureKey -> Subscription`` map. Methods: ``register_plan(deployment_id, plan, pipeline_resolver) -> SubscriptionDelta``, ``unregister_plan``, ``subscription_for``, ``all_subscriptions``, ``consumer_count``.
- ``SubscriptionDelta`` reports ``added``, ``removed``, ``unchanged`` (consumer-count change without subscription change), and ``unresolved`` (FeatureKeys whose pipeline_resolver returned None — graceful degradation).
- Re-registering the same plan is idempotent; re-registering a different plan removes orphaned keys.
- Pipeline resolution per FeatureKey is injected as ``Callable[[FeatureSpec, str], str | None]`` — SubscriptionManager has zero coupling to Provider, MarketDataPipeline, or any provider SDK.
- Architecture-isolation lint: parametrized AST scan over ``backend/app/features/`` and ``backend/app/decision/`` blocks any import of provider SDKs (alpaca, yfinance, polygon, openai, anthropic, groq) or internal broker/alpaca modules. Phase 1 §12 stop condition 1 mechanically defended.
- Acceptance e2e: full ``Plan -> Resolver -> SubscriptionManager`` chain. Two deployments with overlapping plans share subscriptions; one deployment with mixed timeframes resolves to different pipelines per FeatureKey; no provider call required.

Scope kept out:
- Real provider subscribe/unsubscribe wiring (caller wires the delta in Phase 2 alongside BarBuilder + streaming truth).
- Durable persistence of the subscription map (rebuilds at startup from registered plans).

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 627 passed, 1 skipped (+28 vs 1C: 12 SubscriptionManager + 3 acceptance + 13 architecture-lint parametrizations). Frontend: 37 passed. Build clean.

Verification:
- §12 stop 1 enforced: feature/decision modules cannot import any provider SDK.
- §I FINAL: dedup at FeatureKey level (not symbol); Deployment may mix Pipelines per FeatureKey (acceptance test pins this).
- §11 exit gate: a Deployment can declare feature demand, resolve a pipeline per FeatureKey, and attach data demand without any direct provider call.
- No architecture boundaries violated.

Phase 1 Data Flow Lock — exit gate satisfied.

Commit:
- pending.

## 2026-04-25 12:03 ET - Slice 2A: BarBuilder intra-day aggregation (Phase 2 §11.1-3)

Task:
- Phase 2 §11 deliverables 1-3: aggregate 1m NormalizedBar streams into completed higher-timeframe bars (3m/5m/15m/30m/1h) with bucket-cross emission. Pure data, no broker, no money path. Calendar-aware aggregation (4h/1d/1w) deferred to slice 2B.

Files changed:
- backend/app/features/bar_builder.py (new — BarBuilder, BarBuilderRegistry, _Accumulator)
- backend/app/features/__init__.py (exports)
- backend/tests/unit/features/test_bar_builder.py (new — 17 tests)

Implemented:
- ``BarBuilder``: per-symbol stateful 1m → {3m, 5m, 15m, 30m, 1h} aggregator. Bucket-cross emission only — forming bar never exposed publicly (no ``current()`` / ``forming()`` / ``pending()`` methods; lint-style test guards this).
- ``BarBuilderRegistry``: lazy multi-symbol fan-out. ``feed(bar)`` routes by symbol; per-symbol state isolation verified.
- Bucket alignment: UTC wall-clock floor. Hourly aligns to 09:00, 10:00, …; first NYSE RTH hour may emit a "complete" bar with only 30 minutes of data (calendar-aware first/last-bar handling lands in 2B).
- Strict input validation: rejects non-1m bars, symbol mismatch, non-strictly-increasing timestamps, unsupported timeframes (4h/1d/1w error message points to 2B).
- ``flush_at(ts)`` is a documented no-op stub for slice 2B's session-close emission.
- Naive timestamps explicitly normalized to UTC (no silent timezone surprise).

Scope kept out:
- 4h, 1d, 1w aggregation (slice 2B — calendar-aware).
- Calendar / holiday / half-day handling (slice 2B).
- Broker event stream integration, BrokerSync writes, TradeLedger (slice 2C — money path; review-gated).
- Wiring BarBuilder output into IncrementalFeatureEngine.update (deferred to integration slice).

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 646 passed, 1 skipped (+19 BarBuilder tests). Frontend: 37 passed. Build clean.

Verification:
- Feature Engine still does not call external providers (BarBuilder consumes already-normalized bars).
- §16 default "completed bars over forming bars" mechanically enforced.
- §11.3 "no incomplete higher timeframe bars leak into decisions" verified by tests.
- No architecture boundaries violated.
- Architecture-isolation lint (added in 1D) still green — BarBuilder imports nothing from market_data.alpaca or any provider SDK.

Commit:
- pending.

## 2026-04-25 12:58 ET - Slice 2B: Calendar-aware aggregation (Phase 2 §11.2)

Task:
- Phase 2 §11.2 calendar-aware aggregation: introduce a MarketCalendar Protocol with NYSECalendar and FixtureCalendar implementations; extend BarBuilder to support 4h, 1d, 1w with session-bounded bucketing; make flush_at active when calendar present.

Files changed:
- backend/app/features/calendar.py (new — MarketCalendar Protocol, NYSECalendar 2024-2026 holiday/half-day table, FixtureCalendar, regular_session/half_day_session helpers)
- backend/app/features/bar_builder.py (4h via UTC wall-clock; 1d session-bounded; 1w ISO-week bucketing; active flush_at; weekly bars persist across session close)
- backend/app/features/__init__.py (exports)
- backend/tests/unit/features/test_calendar.py (new — 12 calendar tests)
- backend/tests/unit/features/test_bar_builder.py (10 new 2B tests + adjusted 2A tests)

Implemented:
- MarketCalendar Protocol with is_session_day / session_window / previous_session / next_session.
- NYSECalendar: hand-rolled 2024-2026 NYSE holidays + half-days. DST handled via explicit transition table (no zoneinfo / tzdata dependency on Windows). EDT ⇄ EST switches applied per-session: 09:30 ET → 13:30 UTC (EDT) or 14:30 UTC (EST); half-days close 13:00 ET.
- FixtureCalendar: explicit date → SessionWindow map for unit-test determinism.
- BarBuilder accepts optional calendar. 4h is intra-day (UTC wall-clock); 1d / 1w require calendar. Session timeframes raise BarBuilderError when calendar omitted.
- 1d bucket = session_date; bar timestamp = session_open_utc. Daily volume = sum of in-session minutes (390 for full RTH, 210 for half-day).
- 1w bucket = (iso_year, iso_week) of the session date; bar timestamp = first session_open_utc of the week. Bucket spans 4-session weeks (Thanksgiving short week verified).
- flush_at(ts) emits forming intraday + 1d bars; weekly bars persist across session close and emit on bucket cross when next ISO week's first 1m bar arrives. Idempotent — second flush returns ().
- BarBuilderRegistry.flush_at returns per-symbol emitted bars dict.

Scope kept out:
- Broker event stream + BrokerSync TradeLedger (slice 2C — money-path; review-gated).
- Wiring BarBuilder output into IncrementalFeatureEngine.update (integration slice).
- Calendar coverage past 2026 — swap to pandas_market_calendars / exchange_calendars when needed; the Protocol seam keeps that swap one-file.

Validation performed:
- python -m compileall -q backend/app backend/tests
- python -m pytest backend/tests -q
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 672 passed, 1 skipped (+26 vs 2A). Frontend: 37 passed. Build clean.

Verification:
- Feature Engine still does not call external providers.
- Architecture-isolation lint stays green — calendar imports nothing from broker / market_data.alpaca / provider SDKs.
- §16 "completed bars over forming bars" still mechanically enforced (forming accumulator never exposed publicly).
- §11.2 calendar-aware aggregation: holiday skip, half-day handling, DST transitions, ISO-week boundaries all verified by tests.
- No architecture boundaries violated.

Commit:
- pending.

---

## 2026-04-25 17:30 ET - Slice 2C: Broker truth (money path) (Phase 2 §11.4-5)

Task:
- Phase 2 §11.4-5 money-path slice: introduce a canonical TradeLedger / Trade model; route broker stream events into BrokerSyncService via a BrokerStreamRouter; gate OrderManager.create_order on stale broker sync for OPEN intents; consolidate the duplicated record_sync_freshness math.

Files changed:
- backend/app/orders/trade_ledger.py (new — Trade model + TradeLedger; idempotent by broker_execution_id; lookups by account/symbol/client_order_id/order_id)
- backend/app/orders/__init__.py (exports Trade, TradeLedger)
- backend/app/orders/manager.py (broker_sync_service kwarg; _enforce_broker_sync_freshness gates OPEN intents only; CLOSE/protective bypass)
- backend/app/brokers/stream.py (new BrokerStreamRouter — single bridge from emit callback to BrokerSyncService.handle_*; AlpacaAccountStreamAdapter remains a pure normalizer)
- backend/app/brokers/__init__.py (exports BrokerStreamRouter)
- backend/app/brokers/sync.py (extract _snapshot_freshness_state and _persist_sync_freshness module helpers; BrokerSync.record_sync_freshness and BrokerSyncService._persist_sync_state share them)
- backend/tests/unit/orders/test_trade_ledger.py (new — 6 tests)
- backend/tests/unit/brokers/test_broker_stream_router.py (new — 5 tests)
- backend/tests/unit/orders/test_order_manager.py (5 stale-sync gating tests appended)
- backend/tests/unit/brokers/test_broker_sync_reconciliation.py (cumulative partial-fill test + per-execution trade ledger test appended)
- backend/tests/integration/test_broker_truth_money_path_e2e.py (new — 3 tests pinning the money-path contract end-to-end)
- backend/tests/unit/persistence/test_sqlite_persistence.py (test asserts on module source, not class source, since the persist call is now in a module helper)

Implemented:
- Trade is a frozen Pydantic model: trade_id, account_id, symbol, qty, price, side, client_order_id, broker_order_id, broker_execution_id, executed_at, optional internal order_id.
- TradeLedger.record_fill(BrokerFillUpdateEvent, *, order_id=None) → Trade. Idempotent: when broker_execution_id is present, re-delivered events return the existing Trade unchanged.
- BrokerStreamRouter.route(event) dispatches by event type to BrokerSyncService.handle_order_update / handle_fill_update / handle_position_update / handle_account_update; raises BrokerAdapterError on unsupported types. .attach(stream_adapter) subscribes the router as the stream's emit callback.
- OrderManager.create_order accepts a broker_sync_service. When set and the resolved intent is OPEN, the manager checks current_sync_state(account_id).is_stale and raises OrderManagerError("broker_sync_stale:<reason>") before any ledger write. CLOSE / TAKE_PROFIT / STOP_LOSS / SCALE intents bypass the gate so positions remain exitable under sync loss.
- Cumulative-fill semantics: PARTIAL_FILL stream events carry cumulative filled_quantity from the broker; BrokerSync.apply_result mirrors that progression onto the InternalOrder without double-counting.
- record_sync_freshness math is now in one place: _snapshot_freshness_state for snapshot-only freshness and _persist_sync_freshness for the optional runtime-store write. Both BrokerSync.record_sync_freshness (initial validation, recovery orchestrator) and BrokerSyncService._persist_sync_state delegate.

Scope kept out:
- Connecting a real Alpaca trade-update WebSocket to the router in production wiring (still gated behind broker_accounts onboarding work).
- Persisting trades through SQLiteTradeLedger in the broker stream path — that wiring lands when the runtime composition root migrates from the duck-typed slot.
- Linking trades back to InternalOrder via order_id automatically — record_fill accepts order_id but the stream path currently passes None; resolution via BrokerOrderMapping is a follow-up.

Validation performed:
- python -m compileall -q backend
- python -m pytest backend/
- cd frontend && npm.cmd run build
- cd frontend && npm.cmd test

Result:
- compileall clean. Backend: 694 passed, 1 skipped (+22 vs 2B). Frontend: 37 passed. Build clean.

Verification:
- AlpacaAccountStreamAdapter source still does not contain "OrderLedger", "TradeLedger", "BrokerSyncService", or "BrokerSync(" — stream adapter remains a pure normalizer (test_no_stream_adapter_direct_mutation_outside_broker_sync_service still green).
- OrderManager source still does not contain "submit_order" — gate sits on create_order (test_no_external_calls still green).
- §11.4 stale-sync block-gate: stale broker sync blocks new opens; CLOSE/protective intents pass through.
- §11.4 cumulative partial fills: 0 → 4 → 7 → 10 progression on InternalOrder.filled_quantity, one Trade per broker_execution_id.
- BrokerSync persistence-write authority preserved: only the brokers/sync.py module references save_broker_sync_freshness / save_broker_account_snapshot.

Commit:
- pending.
