# COMPLETE ENTITY MODEL INVENTORY

This document is a live system audit of the entity model currently expressed across backend models, services, API routes, frontend pages, and architecture docs.

It is intentionally exhaustive.

It treats the current codebase as partially canonical and partially inconsistent.

It calls out the actual model surface, not only the intended surface.

## Strategy

Purpose:
The design-time container for a named trading idea and its lifecycle shell.

Owns (fields/responsibilities):
- `id`, `name`, `description`, `category`, `status`, `tags`
- Top-level identity for the strategy family
- Relationship to many `StrategyVersion` rows
- High-level archival/activation state for the strategy as a whole
- Human-facing grouping used by strategy pages and strategy lists

Must NOT own:
- Version-specific signal logic payload
- Runtime deployment state
- Risk sizing rules
- Strategy Controls / session gating
- Execution mechanics
- Portfolio-level approval
- Broker truth

Lifecycle states:
- `draft`
- `active`
- `archived`

Created by pages:
- `frontend/src/pages/StrategyCreator.tsx`
- `frontend/src/pages/Strategies.tsx`

Viewed by pages:
- `frontend/src/pages/Strategies.tsx`
- `frontend/src/pages/StrategyDetails.tsx`
- `frontend/src/pages/StrategyEditor.tsx`
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/BacktestLauncher.tsx`
- `frontend/src/pages/SimulationLab.tsx`

Edited by pages:
- `frontend/src/pages/StrategyEditor.tsx`
- `frontend/src/pages/StrategyCreator.tsx`

Backend owner (service/module if known):
- `backend/app/models/strategy.py`
- `backend/app/api/routes/strategies.py`

Related APIs:
- `GET /strategies`
- `POST /strategies`
- `GET /strategies/{id}`
- `PATCH /strategies/{id}` if supported through route update flow
- Strategy generation/import/validation helpers under `/strategies/*`

Relationships to other entities:
- One `Strategy` has many `StrategyVersion`
- One `Strategy` is referenced by many `Deployment`
- One `Strategy` is indirectly used by `BacktestRun`, `TradingProgram`, and `SimulationSession` through `StrategyVersion`

Known confusion points:
- The true signal logic lives on `StrategyVersion.config`, not on `Strategy`
- The UI and docs often speak about "a strategy" when they actually mean a specific strategy version
- Some legacy language still loads strategy-level identity into places that really require version-level immutability

---

## Strategy Version

Purpose:
The portable, versioned signal-definition artifact that actually carries strategy logic.

Owns (fields/responsibilities):
- `strategy_id`, `version`, `config`, `notes`, `created_by`, `created_at`
- `duration_mode`
- `promoted_from_run_id`
- `promotion_status`
- Full strategy definition JSON
- Immutable strategy logic snapshot used by backtests, programs, and simulations

Must NOT own:
- Account-specific risk overrides
- Broker-account-specific execution settings
- Runtime health or deployment status
- Portfolio conflict resolution
- Global kill state

Lifecycle states:
- Promotion chain states: `backtest_only`, `paper_approved`, `live_approved`
- Practical authoring states: new version created, validated, used in backtest, promoted

Created by pages:
- `frontend/src/pages/StrategyCreator.tsx`
- `frontend/src/pages/StrategyEditor.tsx`

Viewed by pages:
- `frontend/src/pages/StrategyDetails.tsx`
- `frontend/src/pages/Strategies.tsx`
- `frontend/src/pages/BacktestLauncher.tsx`
- `frontend/src/pages/SimulationLab.tsx`
- `frontend/src/pages/TradingPrograms.tsx`

Edited by pages:
- `frontend/src/pages/StrategyEditor.tsx`

Backend owner (service/module if known):
- `backend/app/models/strategy.py`
- `backend/app/api/routes/strategies.py`
- `backend/app/services/backtest_service.py`

Related APIs:
- `POST /strategies/{id}/versions`
- `GET /strategies/{id}`
- `POST /strategies/validate`
- Strategy import/generation endpoints under `backend/app/api/routes/strategies.py`

Relationships to other entities:
- Many versions belong to one `Strategy`
- One version has many `BacktestRun`
- One version can be attached to many `TradingProgram`
- One version can be used by many `Deployment`
- One version is used by `SimulationSession`
- One version may have associated `EventFilter`

Known confusion points:
- `StrategyVersion` is the real portable artifact, but several docs still describe portability at the `Strategy` level
- `duration_mode` exists both here and elsewhere through denormalized copies
- Current program resolution overlays non-strategy concerns back into strategy config, which weakens the purity of the versioned artifact

---

## Strategy Controls

Purpose:
The reusable rule set that decides when a strategy is allowed to act.

Owns (fields/responsibilities):
- `timeframe`
- `duration_mode`
- `market_hours`
- `pdt`
- `gap_risk`
- `regime_filter`
- `cooldown_rules`
- `max_trades_per_session`
- `max_trades_per_day`
- `min_time_between_entries_min`
- `earnings_blackout_enabled`
- Template provenance fields like `is_golden`, `tags`, `source_type`

Must NOT own:
- Signal generation logic
- Position sizing
- Order type mechanics
- Broker connectivity
- Final portfolio approval

Lifecycle states:
- Reusable template lifecycle rather than a strict state machine
- Manual vs template provenance
- Active usage through attachment to programs

Created by pages:
- `frontend/src/pages/StrategyGovernors.tsx`

Viewed by pages:
- `frontend/src/pages/StrategyGovernors.tsx`
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/StrategyDetails.tsx` when composed indirectly

Edited by pages:
- `frontend/src/pages/StrategyGovernors.tsx`

Backend owner (service/module if known):
- `backend/app/models/strategy_governor.py`
- `backend/app/api/routes/strategy_governors.py`

Related APIs:
- `GET /strategy-controls`
- `POST /strategy-controls`
- `GET /strategy-controls/{id}`
- `PATCH /strategy-controls/{id}`
- `DELETE /strategy-controls/{id}`
- Summary/analyze routes in `strategy_governors.py`

Relationships to other entities:
- Attached to `TradingProgram` through `strategy_governor_id`
- Overlaid into resolved runtime config by `backtest_service.resolve_program_to_config`

Known confusion points:
- Database/model naming uses `StrategyControls`, route naming uses `/strategy-controls`, UI file name is `StrategyGovernors.tsx`, and older docs call it `Governor`
- `duration_mode` appears here even though it also appears on `StrategyVersion` and `TradingProgram`
- Current overlay code writes some controls-derived limits into `config["risk"]`, which blurs domain boundaries

---

## Risk Profile

Purpose:
Reusable account/program risk budget definition for exposure and loss limits.

Owns (fields/responsibilities):
- Directional limits for long and short
- `max_daily_loss_pct`
- `max_drawdown_lockout_pct`
- `max_leverage`
- Provenance fields `source_type`, `source_run_id`, `source_optimization_id`
- Template metadata `is_golden`, `tags`

Must NOT own:
- Entry or exit signal logic
- Session windows
- Order form
- Broker execution details
- Portfolio conflict resolution logic

Lifecycle states:
- Manual profile
- Backtest-derived profile
- Optimizer-derived profile
- Attached vs unattached to accounts/programs

Created by pages:
- `frontend/src/pages/RiskProfiles.tsx`

Viewed by pages:
- `frontend/src/pages/RiskProfiles.tsx`
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/AccountGovernor.tsx`
- `frontend/src/pages/AccountMonitor.tsx`

Edited by pages:
- `frontend/src/pages/RiskProfiles.tsx`
- Risk attachment flows from `frontend/src/pages/AccountGovernor.tsx`

Backend owner (service/module if known):
- `backend/app/models/risk_profile.py`
- `backend/app/api/routes/risk_profiles.py`
- `backend/app/services/risk_profile_generator.py`

Related APIs:
- `GET /risk-profiles`
- `POST /risk-profiles`
- `GET /risk-profiles/{id}`
- `PATCH /risk-profiles/{id}`
- `DELETE /risk-profiles/{id}`
- `PUT /accounts/{account_id}/risk-profile`
- `DELETE /accounts/{account_id}/risk-profile`
- `GET /accounts/{account_id}/risk-profile`

Relationships to other entities:
- One `RiskProfile` can attach to many `Account`
- One `RiskProfile` can attach to many `TradingProgram`
- A `Deployment` may carry `risk_profile_id` as runtime link
- Provenance may point back to `BacktestRun` or `OptimizationProfile`

Known confusion points:
- Accounts still carry inline risk columns, so risk ownership is duplicated
- Program resolution converts risk profile data back into strategy config fields, which partially collapses separation of concerns
- Runtime governor records also store risk-related fields, creating multiple places where "effective risk state" appears

---

## Execution Style

Purpose:
Reusable order-expression template for how approved trades are expressed.

Owns (fields/responsibilities):
- Entry order type and time-in-force
- Entry offset method/value
- Entry cancel-after-bars
- `bracket_mode`
- Stop/take-profit order types
- Trailing stop settings
- `scale_out`
- `stop_progression_targets`
- ATR source override settings
- Breakeven settings
- Final runner exit settings
- Backtest fill assumptions: `fill_model`, `slippage_bps_assumption`, `commission_per_share`
- Template metadata

Must NOT own:
- Trade thesis or signal truth
- Session/regime permission
- Position sizing budget
- Portfolio authority
- Broker account truth

Lifecycle states:
- Manual vs template provenance
- Reused or unattached

Created by pages:
- `frontend/src/pages/ExecutionStyles.tsx`

Viewed by pages:
- `frontend/src/pages/ExecutionStyles.tsx`
- `frontend/src/pages/TradingPrograms.tsx`

Edited by pages:
- `frontend/src/pages/ExecutionStyles.tsx`

Backend owner (service/module if known):
- `backend/app/models/execution_style.py`
- `backend/app/api/routes/execution_styles.py`

Related APIs:
- `GET /execution-styles`
- `POST /execution-styles`
- `GET /execution-styles/{id}`
- `PATCH /execution-styles/{id}`
- `DELETE /execution-styles/{id}`
- Analyze/helper routes in `execution_styles.py`

Relationships to other entities:
- Attached to `TradingProgram` through `execution_style_id`
- Overlaid into resolved runtime config by `backtest_service.resolve_program_to_config`
- Influences `Trade`, `DeploymentTrade`, broker orders, and simulation behavior indirectly

Known confusion points:
- `TradingProgram.execution_policy` duplicates part of this responsibility
- Strategy config still contains `entry_module`, trailing stop, and target/stop constructs, so ownership is not clean
- Fill assumptions serve both research and live-order-expression discussions, which should be separated more sharply

---

## Watchlist

Purpose:
The reusable symbol-source entity that defines where strategies can hunt.

Owns (fields/responsibilities):
- `name`
- `watchlist_type`
- `refresh_cron`
- `min_refresh_interval_minutes`
- `config`
- Template metadata
- Parent relationship to `WatchlistMembership`

Must NOT own:
- Signal logic
- Position sizing
- Order mechanics
- Portfolio-level approval

Lifecycle states:
- Created
- Refreshed
- Used as manual or scanner-derived list
- Golden template or ordinary list

Created by pages:
- `frontend/src/pages/WatchlistLibrary.tsx`

Viewed by pages:
- `frontend/src/pages/WatchlistLibrary.tsx`
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/SimulationLab.tsx` indirectly when a program resolves symbols

Edited by pages:
- `frontend/src/pages/WatchlistLibrary.tsx`

Backend owner (service/module if known):
- `backend/app/models/watchlist.py`
- `backend/app/services/watchlist_service.py`
- `backend/app/services/watchlist_scheduler.py`
- `backend/app/api/routes/watchlists.py`

Related APIs:
- `GET /watchlists`
- `POST /watchlists`
- `GET /watchlists/{id}`
- `PATCH /watchlists/{id}` or rename endpoint
- `DELETE /watchlists/{id}`
- Membership mutation endpoints in `/watchlists/*`
- Refresh endpoints in `/watchlists/*`

Relationships to other entities:
- One `Watchlist` has many `WatchlistMembership`
- `TradingProgram.watchlist_subscriptions` references watchlists by id
- `SymbolUniverseSnapshot` may derive from one primary and several overlay watchlists

Known confusion points:
- Watchlists are currently both design-time symbol libraries and runtime-resolved universe feeds
- Program code uses watchlist ids directly rather than a cleaner dedicated universe abstraction in all cases
- Some docs speak as if a watchlist directly owns symbols; current implementation actually spreads that across `Watchlist` and `WatchlistMembership`

---

## Watchlist Membership

Purpose:
The resolved symbol membership record inside a watchlist, including lifecycle state.

Owns (fields/responsibilities):
- `watchlist_id`
- `symbol`
- `state`
- `resolved_at`
- state timestamps like `candidate_since`, `active_since`, `pending_removal_since`, `inactive_until`, `suspended_at`
- `metadata`

Must NOT own:
- Global symbol metadata
- Trade state
- Strategy logic
- Account-specific allocations

Lifecycle states:
- `candidate`
- `active`
- `pending_removal`
- inactive/suspended variants implied by timestamps and state field

Created by pages:
- `frontend/src/pages/WatchlistLibrary.tsx`

Viewed by pages:
- `frontend/src/pages/WatchlistLibrary.tsx`
- `frontend/src/pages/TradingPrograms.tsx` indirectly through resolved symbol sets

Edited by pages:
- `frontend/src/pages/WatchlistLibrary.tsx`

Backend owner (service/module if known):
- `backend/app/models/watchlist.py`
- `backend/app/services/watchlist_service.py`

Related APIs:
- Symbol add/remove endpoints under `/watchlists/{id}/*`
- Membership-state endpoint under `/watchlists/{id}/*`

Relationships to other entities:
- Belongs to `Watchlist`
- Feeds `TradingProgram` live universe resolution
- Feeds `SymbolUniverseSnapshot` creation

Known confusion points:
- The codebase uses watchlist membership state as both scanner output state and portfolio candidate state
- There is no separate first-class "universe constituent" entity, so this membership record is overloaded

---

## Trading Program

Purpose:
The deployable design-time package that binds strategy and supporting components into one artifact.

Owns (fields/responsibilities):
- Human identity: `name`, `version`, `description`, `notes`
- Lineage fields to `StrategyVersion`, `OptimizationProfile`, `WeightProfile`, `SymbolUniverseSnapshot`
- `execution_policy`
- Denormalized `duration_mode`
- Universe fields: `universe_mode`, `watchlist_subscriptions`, `watchlist_combination_rule`, `live_universe_*`
- Lifecycle fields: `status`, `frozen_at`, `frozen_by`, `deprecation_reason`
- Component references to `StrategyControls`, `ExecutionStyle`, `RiskProfile`
- Parent/child promotion lineage via `parent_program_id`

Must NOT own:
- Runtime health
- Live broker balances
- Final approval authority
- Ad hoc inline logic that belongs in attached components

Lifecycle states:
- `draft`
- `frozen`
- `deprecated`

Created by pages:
- `frontend/src/pages/TradingPrograms.tsx`

Viewed by pages:
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/AccountGovernor.tsx`
- `frontend/src/pages/SimulationLab.tsx`
- `frontend/src/pages/OptimizationLab.tsx`

Edited by pages:
- `frontend/src/pages/TradingPrograms.tsx`

Backend owner (service/module if known):
- `backend/app/models/trading_program.py`
- `backend/app/api/routes/programs.py`
- `backend/app/services/trading_program_service.py`
- `backend/app/services/backtest_service.py`

Related APIs:
- `GET /programs`
- `POST /programs`
- `GET /programs/{id}`
- `PATCH /programs/{id}`
- `POST /programs/{id}/validate`
- `POST /programs/{id}/deprecate`
- Allocation and promotion endpoints under `/programs/{id}/allocations/*`

Relationships to other entities:
- References one `StrategyVersion`
- May reference one `OptimizationProfile`
- May reference one `WeightProfile`
- May reference one `SymbolUniverseSnapshot`
- May reference one `StrategyControls`
- May reference one `ExecutionStyle`
- May reference one `RiskProfile`
- Has many `AccountAllocation`
- May have a parent `TradingProgram`

Known confusion points:
- The program model still contains `execution_policy` even though the canonical architecture says execution belongs in `Execution Style`
- Program currently owns some universe resolution fields and live-universe cache fields that feel partly runtime
- Program resolution overlays multiple component domains into one flat strategy config, which hides true ownership boundaries

---

## Account Allocation

Purpose:
The account-specific binding of a program to a broker account with bounded overrides.

Owns (fields/responsibilities):
- `trading_program_id`
- `account_id`
- Optional bounded overrides like `position_size_scale_pct`, `session_window_shift_min`, `drawdown_threshold_pct`
- `allocated_capital_usd`
- `conflict_resolution`
- `broker_mode`
- Runtime-ish status and timestamps
- Promotion review payload and notes

Must NOT own:
- The canonical program definition itself
- Broker truth
- Full deployment audit history
- Strategy logic

Lifecycle states:
- `pending`
- `paper`
- `promoted_to_live`
- `paused`
- `stopped`
- `killed`

Created by pages:
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/AccountGovernor.tsx`

Viewed by pages:
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/AccountGovernor.tsx`

Edited by pages:
- `frontend/src/pages/TradingPrograms.tsx`
- `frontend/src/pages/AccountGovernor.tsx`

Backend owner (service/module if known):
- `backend/app/models/trading_program.py`
- `backend/app/api/routes/programs.py`
- `backend/app/api/routes/governor.py`

Related APIs:
- `GET /programs/{program_id}/allocations`
- `POST /programs/{program_id}/allocations`
- `POST /programs/{program_id}/allocations/{allocation_id}/start`
- `POST /programs/{program_id}/allocations/{allocation_id}/stop`
- `POST /programs/{program_id}/allocations/{allocation_id}/promotion-review`
- `POST /programs/{program_id}/allocations/{allocation_id}/promote`
- `POST /programs/{program_id}/allocations/{allocation_id}/revert`
- `POST /governor/{account_id}/allocate`

Relationships to other entities:
- Belongs to one `TradingProgram`
- Belongs to one `Account`
- Is logged in `GovernorEvent`
- Is conceptually adjacent to `Deployment`, but not modeled as the same thing

Known confusion points:
- `AccountAllocation` and `Deployment` both model runtime deployment concepts and overlap heavily
- Allocation status partly duplicates deployment lifecycle
- The system is not fully clear on whether the primary runtime unit is allocation or deployment

---

## Broker Account

Purpose:
The internal representation of a broker-facing account and broker-scoped settings.

Owns (fields/responsibilities):
- Identity: `id`, `name`, `mode`, `broker`
- Encrypted broker credentials/config
- Balances and equity fields
- Inline account risk fields
- `risk_profile_id`
- `account_mode`
- Connectivity flags and kill flags
- Allowed/blocked symbol lists
- Optional `data_service_id`

Must NOT own:
- Strategy logic
- Program composition
- Cross-program conflict resolution
- Backtest result history

Lifecycle states:
- `paper` vs `live` mode
- `cash` vs `margin` account mode
- connected/disconnected
- enabled/disabled
- killed/resumed

Created by pages:
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/components/CreateAccountModal.tsx`

Viewed by pages:
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/CredentialManager.tsx`
- `frontend/src/pages/AccountGovernor.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/LiveMonitor.tsx`

Edited by pages:
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/CredentialManager.tsx`
- `frontend/src/pages/AccountGovernor.tsx` for risk profile attachment

Backend owner (service/module if known):
- `backend/app/models/account.py`
- `backend/app/api/routes/accounts.py`
- `backend/app/api/routes/governor.py`

Related APIs:
- `GET /accounts`
- `POST /accounts`
- `GET /accounts/{id}`
- `PUT /accounts/{id}`
- `DELETE /accounts/{id}`
- Credential endpoints under `/accounts/{id}/credentials`
- Validation endpoints under `/accounts/{id}/validate-credentials`
- Kill/resume/flatten/emergency actions under account/control routes

Relationships to other entities:
- Has many `Deployment`
- Has many `AccountAllocation`
- May attach one `RiskProfile`
- May point to one `DataService`
- Is governed by a `Portfolio Governor`

Known confusion points:
- Account contains inline risk fields even when a `RiskProfile` is attached
- Account is the broker-facing truth source, but some runtime UI fields derive from deployments and not directly from broker state
- The model name is `Account` while the canonical architecture wants `Broker Account`

---

## Portfolio Governor

Purpose:
The final internal approval authority for a broker-account scope before broker execution.

Owns (fields/responsibilities):
- Effective governor identity and label
- Governor status such as `initializing`, `active`, `paused`, `halted`
- Link to `risk_profile_id`
- Poll configuration
- Session realized PnL
- Daily loss lockout flags
- Halt trigger metadata
- Last tick timestamp
- Program allocation view and portfolio snapshot generation
- Final account-scope gate semantics

Must NOT own:
- Strategy signal generation
- Broker order submission implementation
- Technical indicator computation
- Durable strategy/component definitions

Lifecycle states:
- `initializing`
- `active`
- `paused`
- `halted`

Created by pages:
- `frontend/src/pages/AccountGovernor.tsx` through bootstrap flow
- Also auto-created by backend bootstrap path

Viewed by pages:
- `frontend/src/pages/AccountGovernor.tsx`

Edited by pages:
- `frontend/src/pages/AccountGovernor.tsx`

Backend owner (service/module if known):
- `backend/app/api/routes/governor.py`
- `backend/app/services/governor_service.py`
- `backend/app/services/account_governor_loop.py`

Related APIs:
- `GET /governor`
- `GET /governor/{account_id}`
- `POST /governor/{account_id}/bootstrap`
- `POST /governor/{account_id}/halt`
- `POST /governor/{account_id}/resume`
- `POST /governor/{account_id}/allocate`
- `GET /governor/{account_id}/events`
- `GET /governor/{account_id}/portfolio-snapshot`

Relationships to other entities:
- One governor is effectively tied to one `Account`
- Persisted using a `Deployment` row in current implementation
- Emits many `GovernorEvent`
- Works across many `AccountAllocation`

Known confusion points:
- The portfolio governor is not a first-class ORM model; it is currently serialized from `Deployment`
- This is the single biggest model mismatch in the system
- The canonical architecture treats governor as separate from deployment, but current persistence conflates them

---

## Deployment

Purpose:
The runtime instance of a strategy/program on an account and mode.

Owns (fields/responsibilities):
- `strategy_id`, `strategy_version_id`, `account_id`
- `mode`
- `status`
- `config_overrides`
- Lifecycle timestamps and stop reason
- Promotion lineage
- Governor label/status fields
- `risk_profile_id`
- Poll configuration
- Collision/correlation UI snapshot
- Session PnL and halt state
- Observability fields

Must NOT own:
- Canonical portfolio-governor identity
- Reusable design-time component definitions
- Broker truth itself

Lifecycle states:
- `pending`
- `running`
- `paused`
- `stopped`
- `failed`

Created by pages:
- `frontend/src/pages/DeploymentManager.tsx`
- `frontend/src/pages/BacktestLauncher.tsx` through promotion flows
- `frontend/src/pages/OptimizationLab.tsx`

Viewed by pages:
- `frontend/src/pages/DeploymentManager.tsx`
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/LiveMonitor.tsx`
- `frontend/src/pages/AccountGovernor.tsx`
- `frontend/src/pages/Dashboard.tsx`

Edited by pages:
- `frontend/src/pages/DeploymentManager.tsx`
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/AccountGovernor.tsx`

Backend owner (service/module if known):
- `backend/app/models/deployment.py`
- `backend/app/api/routes/deployments.py`
- `backend/app/services/deployment_service.py`
- `backend/app/services/deployment_runner.py`

Related APIs:
- `GET /deployments`
- `POST /deployments`
- `POST /deployments/{id}/pause`
- `POST /deployments/{id}/stop`
- Promotion endpoints under `/deployments/*`
- Control endpoints for pause/resume at `/control/pause-deployment/{id}` and `/control/resume-deployment/{id}`

Relationships to other entities:
- Belongs to one `Account`
- Belongs to one `Strategy`
- References one `StrategyVersion`
- Has many `DeploymentApproval`
- Has many `DeploymentTrade`

Known confusion points:
- Deployment is being used as both deployment runtime state and governor persistence substrate
- Deployments are strategy-centric, while programs/allocations are newer architecture-centric runtime entities
- The system currently has both `Deployment` and `AccountAllocation` as competing runtime control surfaces

---

## Deployment Approval

Purpose:
Explicit audit record for promotion between modes.

Owns (fields/responsibilities):
- `deployment_id`
- `from_mode`
- `to_mode`
- `approved_by`
- `approved_at`
- `notes`
- `safety_checklist`

Must NOT own:
- Runtime deployment state
- Broker truth
- Full compliance workflow outside promotion snapshot

Lifecycle states:
- Created on approval event
- Historical immutable audit record

Created by pages:
- `frontend/src/pages/DeploymentManager.tsx`
- `frontend/src/pages/RunDetails.tsx`
- `frontend/src/pages/OptimizationLab.tsx`

Viewed by pages:
- `frontend/src/pages/DeploymentManager.tsx`
- `frontend/src/pages/RunDetails.tsx`

Edited by pages:
- No meaningful edit flow after creation

Backend owner (service/module if known):
- `backend/app/models/deployment.py`
- `backend/app/services/promotion_service.py`

Related APIs:
- Promotion and approval endpoints under `/deployments/*`
- Program allocation promotion endpoints under `/programs/{id}/allocations/*`

Relationships to other entities:
- Belongs to one `Deployment`

Known confusion points:
- There are two promotion systems now: deployment-level approvals and allocation-level promotion review payloads
- Promotion audit semantics are split between `DeploymentApproval` and `AccountAllocation.promotion_review_payload`

---

## Deployment Trade

Purpose:
The runtime trade ledger row for paper/live deployment execution.

Owns (fields/responsibilities):
- `deployment_id`
- `strategy_version_id`
- Symbol, direction
- Entry/exit details
- Initial risk and current stop data
- Open/closed state
- Unrealized runtime fields
- Stop ownership and Alpaca stop order id
- Regime/context metadata

Must NOT own:
- Backtest-only analytics
- Cross-deployment portfolio state
- Raw broker order book truth in full detail

Lifecycle states:
- Open
- Closed
- Internal-stop-managed
- Broker-stop-managed

Created by pages:
- Not directly created in UI; created by paper/live execution services

Viewed by pages:
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/LiveMonitor.tsx`
- `frontend/src/pages/AccountGovernor.tsx`

Edited by pages:
- Not directly edited; mutated by runtime services

Backend owner (service/module if known):
- `backend/app/models/deployment_trade.py`
- `backend/app/services/paper_broker.py`
- `backend/app/services/position_ledger.py`
- `backend/app/services/deployment_service.py`

Related APIs:
- `GET /monitor/runs/{id}`
- `GET /monitor/runs/{id}/positions`
- `POST /monitor/runs/{id}/close-position`
- `POST /monitor/runs/{id}/close-all`
- Deployment trade viewing endpoints where available

Relationships to other entities:
- Belongs to one `Deployment`
- Runtime analog of `Trade`
- Associated with broker orders through `client_order_id` and stop-leg tracking

Known confusion points:
- The system has both `Trade` and `DeploymentTrade` with overlapping semantics
- Position views often derive from broker APIs rather than directly from `DeploymentTrade`, so source-of-truth is mixed

---

## Backtest Run

Purpose:
The persisted record of one historical strategy execution attempt.

Owns (fields/responsibilities):
- `strategy_version_id`
- `mode`
- `status`
- Symbols, timeframe, date range, capital, commission, slippage
- `parameters`
- Run timing
- `error_message`
- Relationship to trades, metrics, and validation evidence

Must NOT own:
- Reusable strategy logic
- Live deployment status
- Broker credentials
- Portfolio governor state

Lifecycle states:
- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

Created by pages:
- `frontend/src/pages/BacktestLauncher.tsx`
- `frontend/src/pages/OptimizationLab.tsx` indirectly

Viewed by pages:
- `frontend/src/pages/RunHistory.tsx`
- `frontend/src/pages/RunDetails.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/OptimizationLab.tsx`

Edited by pages:
- Limited metadata/update flows only

Backend owner (service/module if known):
- `backend/app/models/run.py`
- `backend/app/api/routes/backtests.py`
- `backend/app/services/backtest_service.py`

Related APIs:
- `GET /backtests`
- `POST /backtests/launch`
- `GET /backtests/{id}`
- `PATCH /backtests/{id}`
- `POST /backtests/{id}/compare`
- Provider recommendation and optimization helper routes in `backtests.py`

Relationships to other entities:
- Belongs to one `StrategyVersion`
- Has many `Trade`
- Has one `RunMetrics`
- Has one `ValidationEvidence`
- May be provenance source for `StrategyVersion` promotion and `RiskProfile`

Known confusion points:
- `mode` exists on backtest runs even though these rows are fundamentally research runs
- Some promotion flows still reference runs while newer architecture centers programs and allocations

---

## Run Metrics

Purpose:
The persisted analytics payload for a completed backtest run.

Owns (fields/responsibilities):
- Return, drawdown, Sharpe, Sortino, Calmar, SQN
- Trade stats
- Exposure stats
- `monthly_returns`
- `equity_curve`
- `exit_reason_breakdown`
- `regime_breakdown`
- `monte_carlo`
- `walk_forward`

Must NOT own:
- Raw trade ledger
- Strategy definition
- Runtime position state

Lifecycle states:
- Created when run completes
- Exists as one-to-one immutable analytics snapshot

Created by pages:
- Not created directly by UI; persisted by backtest engine workflow

Viewed by pages:
- `frontend/src/pages/RunDetails.tsx`
- `frontend/src/pages/RunHistory.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/OptimizationLab.tsx`

Edited by pages:
- No direct edit flow

Backend owner (service/module if known):
- `backend/app/models/run.py`
- `backend/app/services/backtest_service.py`
- `backend/app/services/reporting.py`

Related APIs:
- `GET /backtests/{id}`
- `GET /backtests/{id}/equity-curve`
- `POST /backtests/{id}/compare`

Relationships to other entities:
- One-to-one with `BacktestRun`
- Supports downstream `ValidationEvidence`, optimization ranking, and promotion decisions

Known confusion points:
- `RunMetrics.walk_forward` overlaps with separate `ValidationEvidence.walk_forward`
- There is analytics duplication between metrics and validation evidence

---

## Trade

Purpose:
The historical trade ledger row for a backtest run.

Owns (fields/responsibilities):
- `run_id`
- `strategy_version_id`
- Symbol and direction
- Entry/exit details
- PnL, slippage, commission, return, `r_multiple`
- Open/closed flags
- MAE/MFE
- Regime and entry-condition context
- Metadata

Must NOT own:
- Runtime live order management
- Portfolio-level exposure state
- Broker order book truth

Lifecycle states:
- Open during engine execution
- Closed after simulated exit

Created by pages:
- Not directly created by UI; created by backtest persistence flow

Viewed by pages:
- `frontend/src/pages/RunDetails.tsx`
- `frontend/src/components/TradeReplayPanel.tsx`
- `frontend/src/pages/OptimizationLab.tsx`

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/models/trade.py`
- `backend/app/services/backtest_service.py`

Related APIs:
- `GET /backtests/{id}/trades`
- `GET /backtests/{id}`

Relationships to other entities:
- Belongs to `BacktestRun`
- Has many `ScaleEvent`

Known confusion points:
- `Trade` and `DeploymentTrade` represent the same conceptual object in different execution domains but are modeled separately with drift

---

## Scale Event

Purpose:
The per-trade event record for scale-in or scale-out actions.

Owns (fields/responsibilities):
- `trade_id`
- `event_type`
- `time`
- `price`
- `quantity`
- `quantity_pct`
- `reason`
- `new_stop`
- `realized_pnl`

Must NOT own:
- Parent trade definition
- Portfolio-level exposure context
- Broker order lifecycle

Lifecycle states:
- `scale_in`
- `scale_out`

Created by pages:
- Not directly created by UI

Viewed by pages:
- `frontend/src/pages/RunDetails.tsx`
- Trade replay/detail surfaces

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/models/trade.py`
- `backend/app/services/backtest_service.py`
- `backend/app/services/scale_out_service.py`

Related APIs:
- Returned inside trade payloads from backtest detail endpoints

Relationships to other entities:
- Belongs to `Trade`

Known confusion points:
- Backtest scale events are persisted, but runtime scale events are represented differently and not equally first-class

---

## Validation Evidence

Purpose:
The robustness and anti-bias evidence package attached to a backtest run.

Owns (fields/responsibilities):
- `method`
- `cpcv`
- `walk_forward`
- `anti_bias`
- `regime_performance`
- `per_symbol_oos_sharpe`
- `cost_sensitivity_curve`
- `warnings`
- `is_oos_degradation_ratio`
- `stability_score`

Must NOT own:
- Primary return metrics already covered by `RunMetrics`
- Strategy definition
- Promotion approval state

Lifecycle states:
- Created on completed run
- Historical research evidence snapshot

Created by pages:
- Not directly created by UI

Viewed by pages:
- `frontend/src/pages/RunDetails.tsx`
- `frontend/src/pages/OptimizationLab.tsx`

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/models/validation_evidence.py`
- `backend/app/services/backtest_service.py`

Related APIs:
- `GET /backtests/{id}`
- Compare and optimization APIs using validation-derived fields

Relationships to other entities:
- One-to-one with `BacktestRun`
- May feed `OptimizationProfile`

Known confusion points:
- Evidence overlaps semantically with parts of `RunMetrics`
- Some of this should arguably be a separate validation domain aggregate rather than a sidecar JSON blob

---

## Simulation Session

Purpose:
The in-memory step-through runtime used by Simulation Lab.

Owns (fields/responsibilities):
- `simulation_id`
- `BacktestStepper`
- session metadata
- `status`
- `speed`
- created timestamp
- play task and websocket callback

Must NOT own:
- Durable research history
- Canonical strategy definition
- Live broker interaction
- Portfolio governor authority

Lifecycle states:
- `ready`
- `playing`
- `paused`
- `completed`

Created by pages:
- `frontend/src/pages/SimulationLab.tsx`

Viewed by pages:
- `frontend/src/pages/SimulationLab.tsx`

Edited by pages:
- `frontend/src/pages/SimulationLab.tsx` through play/pause/step/skip controls

Backend owner (service/module if known):
- `backend/app/services/simulation_service.py`
- `backend/app/api/routes/simulations.py`

Related APIs:
- `POST /simulations/create`
- `GET /simulations`
- `GET /simulations/{id}`
- `POST /simulations/{id}/step`
- `POST /simulations/{id}/skip`
- `POST /simulations/{id}/skip-to-trade`
- `POST /simulations/{id}/finalize`
- `GET /simulations/{id}/equity-curve`
- `GET /simulations/{id}/trades`
- `DELETE /simulations/{id}`
- WebSocket `/ws/simulation/{id}`

Relationships to other entities:
- Uses one `StrategyVersion` or one `TradingProgram` resolved into a config
- Produces simulated trades and equity curve views
- Includes `FeaturePlan` preview in metadata

Known confusion points:
- Simulation is a major core workflow but has no persistent ORM entity
- Simulation metadata partially duplicates backtest request shape and run shape

---

## Feature Spec

Purpose:
The canonical identity for one required computed feature.

Owns (fields/responsibilities):
- `kind`
- `timeframe`
- `source`
- `params`

Must NOT own:
- Strategy business rules
- Cache state
- Program identity
- Computed values themselves

Lifecycle states:
- Parsed
- Planned
- Computed
- Reused

Created by pages:
- No direct page; created indirectly by strategy builder, validation, simulation, and runtime planning

Viewed by pages:
- `frontend/src/pages/StrategyCreator.tsx` indirectly through feature references
- `frontend/src/pages/RunDetails.tsx` via feature plan preview
- `frontend/src/pages/SimulationLab.tsx` via preview metadata

Edited by pages:
- No direct edit page; generated from strategy conditions

Backend owner (service/module if known):
- `backend/app/features/specs.py`
- `backend/app/features/catalog.py`

Related APIs:
- Feature preview/validation data returned from strategy validation and backtest/simulation responses

Relationships to other entities:
- Used inside `FeatureRequirement`
- Used inside `FeaturePlan`
- Derived from strategy condition/value specs

Known confusion points:
- This is a core canonical domain object but is not persisted
- Feature refs also exist as raw strings in strategy config and UI types, so there are multiple feature representations

---

## Feature Requirement

Purpose:
A concrete request for a feature emitted by a program or runtime consumer.

Owns (fields/responsibilities):
- `spec`
- `requested_by`

Must NOT own:
- Feature computation output
- Program cache state
- Full strategy config

Lifecycle states:
- Requested
- Planned
- Satisfied

Created by pages:
- No direct page

Viewed by pages:
- Not directly surfaced; only indirectly through previews/debugging

Edited by pages:
- No direct edit flow

Backend owner (service/module if known):
- `backend/app/features/specs.py`

Related APIs:
- Indirect through strategy validation and simulation/backtest feature previews

Relationships to other entities:
- Wraps one `FeatureSpec`
- Feeds `FeaturePlan`

Known confusion points:
- This is architecturally important but mostly invisible in the product today

---

## Feature Plan

Purpose:
The deterministic plan for what features a program/runtime needs and how much warmup they require.

Owns (fields/responsibilities):
- `program_id`
- `account_id`
- `symbols`
- `timeframes`
- `feature_specs`
- `feature_keys`
- `warmup_bars_by_timeframe`

Must NOT own:
- Computed feature values
- Strategy signals
- Cache invalidation logic
- Portfolio-governor decisions

Lifecycle states:
- Built
- Previewed
- Warmed
- Consumed

Created by pages:
- No direct page; preview surfaced through strategy/backtest/simulation flows

Viewed by pages:
- `frontend/src/pages/RunDetails.tsx`
- `frontend/src/pages/SimulationLab.tsx`
- Strategy validation surfaces

Edited by pages:
- No direct edit flow

Backend owner (service/module if known):
- `backend/app/features/planner.py`
- `backend/app/features/preview.py`

Related APIs:
- Feature plan preview returned by strategy validation
- Feature plan preview embedded in backtest and simulation payloads

Relationships to other entities:
- Built from many `FeatureSpec`
- Uses program/account identity
- Supports runtime startup and simulation/backtest previews

Known confusion points:
- Plan assumes `program_id` and `account_id`, but preview flows often build plans before those runtime identities truly exist
- There is no durable `FeaturePlan` entity even though the system increasingly treats it like one

---

## Symbol Universe Snapshot

Purpose:
The persisted resolved symbol set used for optimizer and program lineage.

Owns (fields/responsibilities):
- `source_watchlist_id`
- `overlay_watchlist_ids`
- `deny_list`
- `top_n`
- `effective_date`
- `resolved_symbols`
- `resolved_symbol_count`
- `metadata_version_id`
- `resolution_notes`
- `source`

Must NOT own:
- Live watchlist refresh logic
- Strategy logic
- Portfolio exposure state

Lifecycle states:
- Created per effective date / universe resolution
- Reused by optimization/program lineage

Created by pages:
- No dedicated page today
- Indirectly created through universe/program workflows

Viewed by pages:
- `frontend/src/pages/TradingPrograms.tsx`
- Universe-related internal flows

Edited by pages:
- No direct edit flow; typically regenerate instead

Backend owner (service/module if known):
- `backend/app/models/symbol_universe.py`
- `backend/app/services/universe_service.py`
- `backend/app/api/routes/universes.py`

Related APIs:
- Universe endpoints in `/universes`

Relationships to other entities:
- Can derive from `Watchlist`
- Can link to `MarketMetadataSnapshot`
- Can attach to `TradingProgram`
- Can attach to `OptimizationProfile` and `WeightProfile`

Known confusion points:
- The system has both live watchlist subscriptions and frozen universe snapshots
- Universe is a first-class concept in the newer architecture, but still partly embedded in program/watchlist fields elsewhere

---

## Optimization Profile

Purpose:
The optimizer configuration and lineage record for portfolio construction.

Owns (fields/responsibilities):
- Links to `StrategyVersion`, `ValidationEvidence`, `SymbolUniverseSnapshot`
- `name`, `engine_id`, `engine_version`, `status`
- `objective_config`
- `covariance_model`
- `constraints`
- `notes`

Must NOT own:
- Final program deployment status
- Strategy signal logic
- Runtime account state

Lifecycle states:
- `draft`
- Active/completed states depending on route workflow

Created by pages:
- `frontend/src/pages/OptimizationLab.tsx`

Viewed by pages:
- `frontend/src/pages/OptimizationLab.tsx`
- `frontend/src/pages/TradingPrograms.tsx`

Edited by pages:
- `frontend/src/pages/OptimizationLab.tsx`

Backend owner (service/module if known):
- `backend/app/models/optimization.py`
- `backend/app/services/optimization_service.py`
- `backend/app/api/routes/optimizations.py`

Related APIs:
- Optimization routes under `/optimizations`

Relationships to other entities:
- May reference one `StrategyVersion`
- May reference one `ValidationEvidence`
- May reference one `SymbolUniverseSnapshot`
- Has many `WeightProfile`
- Can attach to `TradingProgram`

Known confusion points:
- Optimization is a newer portfolio-construction domain that does not yet fit cleanly into the older strategy/deployment UI

---

## Weight Profile

Purpose:
The concrete optimizer output or allocation-weight artifact produced from an optimization profile.

Owns (fields/responsibilities):
- `optimization_profile_id`
- `parent_weight_profile_id`
- engine metadata
- evidence/universe/metadata lineage
- objective/constraint/covariance snapshots used
- input universe snapshot
- `output_weights`
- explainability payload

Must NOT own:
- Runtime fill state
- Strategy logic
- Broker truth

Lifecycle states:
- Created from optimization run
- Possibly cloned/refined from parent profile

Created by pages:
- `frontend/src/pages/OptimizationLab.tsx`

Viewed by pages:
- `frontend/src/pages/OptimizationLab.tsx`
- `frontend/src/pages/TradingPrograms.tsx`

Edited by pages:
- No strong direct edit flow; usually regenerated

Backend owner (service/module if known):
- `backend/app/models/optimization.py`
- `backend/app/services/optimization_service.py`

Related APIs:
- Optimization routes under `/optimizations`

Relationships to other entities:
- Belongs to `OptimizationProfile`
- May have parent `WeightProfile`
- Can attach to `TradingProgram`

Known confusion points:
- Weight profiles are core for portfolio-construction lineage but are not yet prominent in the operator UI

---

## Market Event

Purpose:
The calendar event record that strategy controls and event filters can react to.

Owns (fields/responsibilities):
- `name`
- `category`
- optional `symbol`
- `event_time`
- `impact`
- `source`
- `metadata`

Must NOT own:
- Per-strategy policy response
- Runtime kill behavior
- Signal logic

Lifecycle states:
- Upcoming
- Past
- Sample/manual/imported source variants

Created by pages:
- `frontend/src/pages/EventCalendar.tsx` via sample-seed and management flows

Viewed by pages:
- `frontend/src/pages/EventCalendar.tsx`
- Strategy authoring surfaces indirectly

Edited by pages:
- `frontend/src/pages/EventCalendar.tsx` depending on route support

Backend owner (service/module if known):
- `backend/app/models/event.py`
- `backend/app/api/routes/events.py`
- `backend/app/services/earnings_calendar.py`

Related APIs:
- `GET /events`
- `POST /events/seed-sample`

Relationships to other entities:
- Consumed by `EventFilter`
- Consumed by `StrategyControls` blackout logic

Known confusion points:
- Event gating is split between `StrategyControls` blackout fields and separate `EventFilter` entity

---

## Event Filter

Purpose:
The per-strategy-version policy for how market events should affect trading.

Owns (fields/responsibilities):
- `strategy_version_id`
- `categories`
- `impact_levels`
- `minutes_before`
- `minutes_after`
- `close_positions_before`
- `minutes_before_close`
- `reduce_size_pct`
- `disable_entries`
- `is_active`

Must NOT own:
- Market events themselves
- Strategy signal logic
- Portfolio governor decisions

Lifecycle states:
- Active
- Inactive

Created by pages:
- No dedicated page today; likely embedded in strategy authoring flow

Viewed by pages:
- `frontend/src/pages/StrategyCreator.tsx`
- `frontend/src/pages/StrategyDetails.tsx` indirectly

Edited by pages:
- `frontend/src/pages/StrategyCreator.tsx` indirectly if surfaced

Backend owner (service/module if known):
- `backend/app/models/event.py`
- Strategy-related routes/services

Related APIs:
- Strategy save/validate flows if event filter payload is included
- Event routes for calendar lookup

Relationships to other entities:
- Belongs conceptually to one `StrategyVersion`
- Consumes many `MarketEvent`

Known confusion points:
- The platform has both explicit `EventFilter` entity and blackout settings inside `StrategyControls.gap_risk` and `earnings_blackout_enabled`

---

## Data Service

Purpose:
Shared credential/config record for market data or AI services.

Owns (fields/responsibilities):
- `name`
- `provider`
- `environment`
- encrypted API credentials
- optional `model`
- default/active flags

Must NOT own:
- Broker account positions
- Strategy logic
- Backtest results

Lifecycle states:
- active/inactive
- default/non-default
- data-service or AI-service variant

Created by pages:
- `frontend/src/pages/Services.tsx`

Viewed by pages:
- `frontend/src/pages/Services.tsx`
- `frontend/src/pages/DataManager.tsx`
- `frontend/src/pages/CredentialManager.tsx` indirectly

Edited by pages:
- `frontend/src/pages/Services.tsx`

Backend owner (service/module if known):
- `backend/app/models/data_service.py`
- `backend/app/api/routes/services.py`

Related APIs:
- `GET /services`
- `POST /services`
- `PATCH /services/{id}`
- service test routes in `services.py`

Relationships to other entities:
- `Account.data_service_id` may point to a `DataService`
- Backtest/simulation/data manager may resolve credentials from data services

Known confusion points:
- Data services mix market data providers and AI providers in one model
- Credential ownership is split across `Account` and `DataService`

---

## Data Inventory

Purpose:
The index of downloaded/cached historical datasets.

Owns (fields/responsibilities):
- `symbol`
- `timeframe`
- `source`
- `adjusted`
- coverage dates and bar count
- freshness timestamps
- `is_complete`
- `file_path`

Must NOT own:
- Individual bar payload for large datasets
- Strategy logic
- Broker truth

Lifecycle states:
- Downloaded
- Refreshed
- Incomplete/complete
- Deleted

Created by pages:
- `frontend/src/pages/DataManager.tsx`

Viewed by pages:
- `frontend/src/pages/DataManager.tsx`
- `frontend/src/pages/ChartLab.tsx` indirectly

Edited by pages:
- `frontend/src/pages/DataManager.tsx`

Backend owner (service/module if known):
- `backend/app/models/market_data.py`
- `backend/app/api/routes/data.py`
- `backend/app/services/market_data_service.py`

Related APIs:
- Data fetch/list/delete routes under `/data`

Relationships to other entities:
- Companion to `CachedBar`
- Used by backtest/simulation/data download workflows

Known confusion points:
- Some datasets live in parquet and some as rows in `CachedBar`, so the actual cache layer is hybrid

---

## Cached Bar

Purpose:
The row-level OHLCV store for smaller cached datasets.

Owns (fields/responsibilities):
- `symbol`
- `timeframe`
- `timestamp`
- OHLCV values

Must NOT own:
- Dataset-level freshness metadata
- Strategy features
- Runtime positions

Lifecycle states:
- Inserted
- Replaced/refreshed
- Deleted

Created by pages:
- `frontend/src/pages/DataManager.tsx` indirectly

Viewed by pages:
- `frontend/src/pages/DataManager.tsx` indirectly
- `frontend/src/pages/ChartLab.tsx` indirectly

Edited by pages:
- No direct edit flow

Backend owner (service/module if known):
- `backend/app/models/market_data.py`
- `backend/app/services/market_data_service.py`

Related APIs:
- Data routes under `/data`

Relationships to other entities:
- Complements `DataInventory`

Known confusion points:
- The platform uses both file-based and row-based caches; there is no single uniform market-data storage abstraction

---

## Market Metadata Snapshot

Purpose:
The versioned metadata snapshot used by universe and optimization workflows.

Owns (fields/responsibilities):
- `metadata_version_id`
- `as_of_date`
- provider info
- fetch date range
- symbol count
- correlation window

Must NOT own:
- Symbol-level rows directly
- Strategy logic
- Runtime risk decisions

Lifecycle states:
- Created per metadata run/version

Created by pages:
- No dedicated page today

Viewed by pages:
- `frontend/src/pages/OptimizationLab.tsx` indirectly
- `frontend/src/pages/LogsPanel.tsx` indirectly

Edited by pages:
- No direct edit flow

Backend owner (service/module if known):
- `backend/app/models/market_metadata.py`
- `backend/app/services/market_metadata_service.py`

Related APIs:
- Market metadata and optimization-related APIs

Relationships to other entities:
- Has many `MarketMetadataSymbol`
- Can be referenced by `SymbolUniverseSnapshot` and `WeightProfile`

Known confusion points:
- Market metadata is operationally important but underexposed in UI terminology

---

## Market Metadata Symbol

Purpose:
The per-symbol metadata row within a metadata snapshot.

Owns (fields/responsibilities):
- `snapshot_id`
- `symbol`
- `sector_tag`
- `benchmark_symbol`
- realized vol, average correlation, ADV, spread proxy, regime tag

Must NOT own:
- Portfolio allocations
- Strategy logic
- Runtime positions

Lifecycle states:
- Created with snapshot

Created by pages:
- No direct page

Viewed by pages:
- Optimization/universe internals

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/models/market_metadata.py`
- `backend/app/services/market_metadata_service.py`

Related APIs:
- Metadata/universe/optimization APIs where exposed

Relationships to other entities:
- Belongs to `MarketMetadataSnapshot`

Known confusion points:
- This is a foundational quant-support entity, but it is invisible to most operator workflows

---

## Kill Switch Event

Purpose:
The durable audit log for kill, pause, flatten, and resume control actions.

Owns (fields/responsibilities):
- `scope`
- `scope_id`
- `action`
- `reason`
- `triggered_by`
- `triggered_at`

Must NOT own:
- Current in-memory kill state itself
- Portfolio-governor analytics
- Broker order details beyond control action audit

Lifecycle states:
- `kill`
- `pause`
- `flatten`
- `resume`

Created by pages:
- `frontend/src/components/KillSwitch.tsx`
- `frontend/src/pages/AccountMonitor.tsx`
- `frontend/src/pages/AccountGovernor.tsx`
- Any emergency control surface

Viewed by pages:
- `frontend/src/pages/LogsPanel.tsx`
- Header kill switch/status surfaces

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/models/kill_switch.py`
- `backend/app/api/routes/control.py`
- `backend/app/core/kill_switch.py`

Related APIs:
- `GET /control/status`
- `POST /control/kill-all`
- `POST /control/resume-all`
- `POST /control/kill-strategy/{strategy_id}`
- `POST /control/pause-strategy/{strategy_id}`
- `POST /control/resume-strategy/{strategy_id}`
- `POST /control/pause-deployment/{deployment_id}`
- `POST /control/resume-deployment/{deployment_id}`
- `GET /control/kill-events`

Relationships to other entities:
- Applies to `Account`, `Strategy`, `Deployment`, and global platform scope

Known confusion points:
- In-memory kill state is separate from durable audit state
- Kill/pause semantics overlap with portfolio-governor halt semantics

---

## Governor Event

Purpose:
The audit/event log for portfolio-governor decisions and runtime portfolio control activity.

Owns (fields/responsibilities):
- `governor_id`
- `allocation_id`
- `event_type`
- optional `symbol`
- `detail`
- `emitted_at`

Must NOT own:
- Governor identity model itself
- Primary order ledger
- Strategy logic

Lifecycle states:
- Event-type driven: `collision_suppressed`, `correlation_blocked`, `risk_blocked`, `universe_updated`, `halt_triggered`, `program_paused`, `fill_confirmed`, `program_added`, etc.

Created by pages:
- Not directly created by UI; emitted by governor flows

Viewed by pages:
- `frontend/src/pages/AccountGovernor.tsx`

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/models/governor_event.py`
- `backend/app/api/routes/governor.py`
- `backend/app/services/governor_service.py`

Related APIs:
- `GET /governor/{account_id}/events`

Relationships to other entities:
- Belongs to a persisted governor id currently backed by `Deployment`
- May reference an `AccountAllocation`

Known confusion points:
- Because governor ids are deployment ids in current code, event ownership is structurally confusing

---

## Program Backlog Item

Purpose:
The persisted planning/oversight item for thin-slice execution and delivery sequencing.

Owns (fields/responsibilities):
- `title`
- `objective`
- `scope`
- `business_impact`
- `order_index`
- `blocked_by_ids`
- `status`
- `review`
- `verification`
- `next_gate`

Must NOT own:
- Runtime trading state
- Program definition
- Portfolio state

Lifecycle states:
- `queued`
- review/verification substates as text fields

Created by pages:
- Internal backlog UIs and workflows

Viewed by pages:
- Backlog/roadmap panels and internal delivery tooling
- `frontend/src/pages/LogsPanel.tsx` indirectly

Edited by pages:
- Backlog management flows

Backend owner (service/module if known):
- `backend/app/models/program_backlog.py`
- `backend/app/api/routes/backlog.py`

Related APIs:
- `/backlog` routes

Relationships to other entities:
- Dependency references to other backlog items through `blocked_by_ids`

Known confusion points:
- Despite the name, this is a delivery-management entity, not a trading-domain program entity
- The word "Program" collides with `TradingProgram`

---

## Order Intent / Broker Order

Purpose:
The broker-facing order instruction and order-response domain currently represented through service dataclasses and live API payloads rather than a first-class ORM model.

Owns (fields/responsibilities):
- `AlpacaOrderRequest` fields like symbol, qty, side, order type, TIF, prices, `client_order_id`
- `client_order_id` encoding for program/deployment attribution and intent
- Open/close/tp/sl/scale intent parsing
- Live order payloads returned to monitor pages

Must NOT own:
- Strategy approval logic
- Portfolio conflict resolution
- Long-term trade PnL ledger

Lifecycle states:
- New/open
- Filled/partially filled
- Canceled
- Held/protective
- Unknown attribution cases

Created by pages:
- Indirectly from deployment start and runtime execution
- Manual close flows from `frontend/src/pages/LiveMonitor.tsx`
- Manual close/flatten actions from `frontend/src/pages/AccountMonitor.tsx`

Viewed by pages:
- `frontend/src/pages/LiveMonitor.tsx`
- `frontend/src/pages/AccountMonitor.tsx`

Edited by pages:
- Not edited; replaced/canceled by runtime flows

Backend owner (service/module if known):
- `backend/app/services/alpaca_service.py`
- `backend/app/api/routes/monitor.py`
- `backend/app/api/routes/control.py`

Related APIs:
- `GET /monitor/runs/{id}/orders`
- Runtime order submission through `alpaca_service.submit_order()` and helper wrappers

Relationships to other entities:
- Produced after approval from `Portfolio Governor`
- Attributed back to `Deployment` and program intent through `client_order_id`
- Related to `DeploymentTrade`

Known confusion points:
- Orders are absolutely core, but there is no first-class persistent `Order` entity in the current domain model
- The system relies on broker responses and audit dataclasses instead of a unified internal order ledger

---

## Order Audit Entry

Purpose:
The structured audit object used during cancellation sweeps and control operations.

Owns (fields/responsibilities):
- `order_id`
- `client_order_id`
- `symbol`
- `side`
- `qty`
- `intent`
- `reason`
- `deployment_id`

Must NOT own:
- Current broker truth beyond snapshot at sweep time
- Trade ledger state

Lifecycle states:
- Canceled
- Skipped as protective
- Skipped because position exists
- Skipped as unknown

Created by pages:
- No direct page; created during control sweeps

Viewed by pages:
- Control responses surfaced to kill/pause UIs and debugging output

Edited by pages:
- No edit flow

Backend owner (service/module if known):
- `backend/app/services/alpaca_service.py`
- `backend/app/api/routes/control.py`

Related APIs:
- Returned in kill/pause/resume control responses

Relationships to other entities:
- Child audit unit inside `CancellationResult`
- References broker orders and deployment attribution

Known confusion points:
- Another essential execution entity exists only as a service dataclass, not a durable domain model

---

## ENTITY PROBLEMS

List:
- `Portfolio Governor` is not a first-class persistent entity; current code stores it in `Deployment`, which is a major canonical-model violation
- `Deployment` and `AccountAllocation` overlap heavily as runtime deployment entities and split ownership of start/stop/promotion state
- `ExecutionStyle` and `TradingProgram.execution_policy` duplicate execution ownership
- `RiskProfile` and `Account` both own risk limits, causing duplicated responsibilities and ambiguity about effective risk source
- `StrategyVersion`, `StrategyControls`, and `TradingProgram` all carry `duration_mode`, which is duplicated state
- `StrategyControls` blackout/event gating overlaps with `EventFilter`, creating unclear ownership for event-based trade suppression
- `Watchlist`, `WatchlistMembership`, live program watchlist subscriptions, and `SymbolUniverseSnapshot` overlap as universe-definition layers without a single enforced canonical path
- `RunMetrics` and `ValidationEvidence` both carry walk-forward and robustness information, so analytics are split across overlapping sidecars
- `Trade` and `DeploymentTrade` duplicate core trade concepts across research and runtime with drift in fields and semantics
- `Order` is a core business entity but is not modeled as a first-class persistent domain object; order state is fragmented across broker responses, service dataclasses, and monitor payloads
- `DataService` mixes data-provider credentials and AI-service credentials, which are separate concerns
- `ProgramBacklogItem` uses the word `Program` for delivery planning, which collides with `TradingProgram`
- Program-resolution overlay in `backtest_service.resolve_program_to_config()` flattens Strategy Controls, Risk Profile, and Execution Style back into strategy config, which hides domain ownership and makes entity boundaries porous
- The frontend and backend naming are still inconsistent across `Strategy Controls` vs `Strategy Governor`, `Portfolio Governor` vs `Account Governor`, and `Broker Account` vs `Account`
- Simulation is a core entity/workflow but has no durable persistent model, which makes auditability and lineage weaker than backtest/deployment flows
