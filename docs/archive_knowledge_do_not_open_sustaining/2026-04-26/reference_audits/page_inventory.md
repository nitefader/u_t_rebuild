# Complete Page Inventory — Ultimate Trading Software 2026
> Audit date: 2026-04-23 · Auditor: senior product architect pass

---

## Dashboard

Purpose: Platform entry point. Shows system health, kill switch state, equity allocation by account, recent backtest runs, and a getting-started checklist. Acts as an orientation hub, not a task hub.

Primary user: Any logged-in operator on first login or returning after absence.

Creates: Nothing directly. Quick-action buttons navigate to other pages.
Reads: `/api/v1/control/status`, `/api/v1/accounts`, `/api/v1/backtests`, deployment counts.
Updates: Nothing.
Deletes: Nothing.

Key actions:
- View global kill switch state (badge only — no control here)
- View account equity allocation chart (pie/bar by account)
- View last N backtest runs (table with basic metrics)
- Navigate via "Quick Actions" to Strategies, Backtest, Programs
- Check getting-started checklist completion steps

Related entities:
- Account
- BacktestRun
- KillSwitchEvent (read status only)
- Deployment (count badge)

Key API routes:
- `GET /api/v1/control/status`
- `GET /api/v1/accounts`
- `GET /api/v1/backtests`

Realtime streams:
- None (polling, 30s interval)

Overlaps or conflicts with other pages:
- Kill switch status duplicated in AccountGovernor (GlobalKillStrip) and AccountMonitor
- Recent runs table duplicates RunHistory data but with fewer columns
- Account equity widget duplicates AccountMonitor cards
- Getting started checklist references every page — creates implicit ordering that isn't enforced

Current UX problems:
- Kill switch is READ-ONLY on dashboard but the user's first instinct is to act on a red kill switch badge — it should either be actionable here or the badge should link directly to the control
- Getting started checklist does not track completion state server-side; if reloaded from a different browser the state resets
- "Quick Actions" buttons are redundant with the sidebar navigation — double navigation surface
- Account equity chart is static (no click-through to account detail)
- No prominent indicator of whether the platform is in paper vs live mode globally
- Dashboard is useful for power users but overwhelming for first-time users who haven't yet created a strategy

Recommended domain grouping: Operate

---

## Strategies (Library)

Purpose: Browse, search, filter, export, import, and AI-generate strategies. Entry point for strategy authoring lifecycle.

Primary user: Strategy developer / quant.

Creates: Strategy (via "New Strategy" button → StrategyCreator page) or AI-generated strategy (NewStrategyModal within this page).
Reads: `GET /api/v1/strategies` (list with versions count, tags, category, status).
Updates: Nothing directly (edits happen on StrategyEditor).
Deletes: Nothing directly (deletes happen on StrategyDetails).

Key actions:
- Search strategies by name, description, tag
- Filter by category (trend, mean_reversion, breakout, volatility, multi-factor)
- Export strategy as JSON
- Import strategy from JSON file
- Open AI generation modal (enter natural language prompt → POST /strategies/generate-conditions)
- Navigate to StrategyCreator (new blank strategy)
- Navigate to StrategyDetails (click existing strategy)

Related entities:
- Strategy
- StrategyVersion (count shown)

Key API routes:
- `GET /api/v1/strategies`
- `POST /api/v1/strategies/generate-conditions` (AI modal)
- `GET /api/v1/strategies/{id}/export`
- `POST /api/v1/strategies/import`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- AI generation in this modal produces a partial strategy that auto-navigates to StrategyCreator — the split feels abrupt; user isn't sure if the strategy was saved
- The "New Strategy" flow splits across three pages (Strategies list → StrategyCreator → StrategyDetails) creating unclear save semantics
- RunHistory also shows strategy name; no direct link back to this library from there

Current UX problems:
- Modal for AI generation injects state into StrategyCreator via navigation — if the user presses back the generated content is lost
- No bulk operations (bulk tag, bulk delete, bulk export)
- Category filter chips require exact match — no fuzzy match
- No sort control (only default sort order, likely by created_at desc)
- Strategy status field ("active", "archived") exists in the model but is never surfaced as a filter
- Import silently overwrites conflicts with no preview diff

Recommended domain grouping: Build

---

## Strategy Creator

Purpose: Form-based wizard to create a new strategy version from scratch. Wraps StrategyBuilderShell in "create" mode.

Primary user: Strategy developer.

Creates: Strategy + initial StrategyVersion via `POST /api/v1/strategies` then `POST /api/v1/strategies/{id}/versions`.
Reads: `GET /api/v1/strategies/indicator-kinds` (to populate indicator dropdowns).
Updates: Nothing (this is create-only).
Deletes: Nothing.

Key actions:
- Enter strategy metadata (name, description, category, hypothesis, tags)
- Build entry conditions using ConditionBuilder (indicator crossovers, threshold comparisons, n-of-m logic)
- Configure stops (ATR-based, fixed, trailing candidates)
- Configure target/exit conditions
- Submit to create strategy + version

Related entities:
- Strategy
- StrategyVersion
- StrategyConfig (EntryConfig, StopConfig, ExitsConfig)
- Condition (tree of signal nodes)
- IndicatorSpec

Key API routes:
- `POST /api/v1/strategies`
- `POST /api/v1/strategies/{id}/versions`
- `GET /api/v1/strategies/indicator-kinds`
- `POST /api/v1/strategies/validate` (live validation during build)

Realtime streams:
- None

Overlaps or conflicts with other pages:
- StrategyEditor has a "new version" mode that uses the same StrategyBuilderShell — the two paths are nearly identical except one creates a new strategy and the other creates a new version on an existing one
- AI-generated strategies from the Strategies page land here pre-populated — but only if navigated from there; the component also works standalone

Current UX problems:
- No autosave — a browser crash loses all work
- The tab structure (Core → Signals → Stops → Exits) doesn't indicate which tabs have validation errors until the user tries to submit
- IndicatorBuilder is powerful but has no "test indicator" feature — user must run a backtest to see if the indicator fires
- No direct "test this condition on chart" action
- StrategyBuilderShell is a deeply nested component tree — the scroll position resets when switching tabs
- The voice input feature (`useSpeechInput`) is present but completely undiscoverable — no affordance in the UI

Recommended domain grouping: Build

---

## Strategy Details

Purpose: Read-only view of a strategy and all its versions. Version selector, diff comparison, raw JSON inspector, delete version controls, and navigation to editor or backtest launcher.

Primary user: Strategy developer reviewing historical versions.

Creates: Nothing. Navigation links to StrategyEditor for new version creation.
Reads: `GET /api/v1/strategies/{id}` (strategy with all versions), `GET /api/v1/strategies/{id}/versions/{v1Id}/diff/{v2Id}` (when comparing).
Updates: Nothing (read-only viewer).
Deletes: `DELETE /api/v1/strategies/{id}/versions/{versionId}` (delete specific version), `DELETE /api/v1/strategies/{id}` (delete whole strategy).

Key actions:
- Select active version from version list
- Toggle raw JSON view vs formatted config inspector
- Compare two versions side-by-side (VersionDiffPanel)
- Navigate to StrategyEditor in "edit" mode
- Navigate to StrategyEditor in "new version" mode
- Navigate to BacktestLauncher pre-filled with this strategy
- Delete a version (with confirmation)
- Delete the strategy entirely (with confirmation)

Related entities:
- Strategy
- StrategyVersion
- StrategyConfig

Key API routes:
- `GET /api/v1/strategies/{id}`
- `GET /api/v1/strategies/{id}/versions/{v1Id}/diff/{v2Id}`
- `DELETE /api/v1/strategies/{id}/versions/{versionId}`
- `DELETE /api/v1/strategies/{id}`
- `GET /api/v1/strategies/{id}/export`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- StrategyEditor in "edit" mode overlaps with this page's intent — some users want to edit inline here, not navigate away
- BacktestLauncher has its own strategy/version selector; pre-filling from StrategyDetails creates duplicate state

Current UX problems:
- Delete strategy is a top-level action on the same page as viewing it — high risk of accidental destructive action
- Version list shows creation timestamps but not what changed (no changelog / commit message field per version)
- Diff viewer shows structural JSON diff but not a semantic plain-language diff ("entry condition changed from RSI > 70 to RSI > 65")
- "Promote to backtest" link goes to a different URL; the transition loses the version context unless the link passes a query param (it does, but this is fragile)
- No breadcrumb to navigate back to the Strategies list from deep inside a version comparison

Recommended domain grouping: Build

---

## Strategy Editor

Purpose: Dual-mode editor for modifying an existing strategy version (in-place edit) or creating a new version on an existing strategy. Wraps StrategyBuilderShell with a version notes input and mode flag.

Primary user: Strategy developer iterating on a strategy.

Creates: `POST /api/v1/strategies/{id}/versions` (in "new_version" mode), or `PATCH /api/v1/strategies/{id}/versions/{versionId}` (in "edit" mode).
Reads: `GET /api/v1/strategies/{id}/versions/{versionId}` (to pre-populate form), `GET /api/v1/strategies/indicator-kinds`.
Updates: Existing version config (edit mode).
Deletes: Nothing.

Key actions:
- All ConditionBuilder actions (same as StrategyCreator)
- Enter version notes (new_version mode only)
- Save as new version vs overwrite existing
- Validate in real-time via `POST /api/v1/strategies/validate`

Related entities:
- Strategy
- StrategyVersion
- StrategyConfig

Key API routes:
- `GET /api/v1/strategies/{id}/versions/{versionId}`
- `POST /api/v1/strategies/{id}/versions`
- `PATCH /api/v1/strategies/{id}/versions/{versionId}`
- `POST /api/v1/strategies/validate`
- `GET /api/v1/strategies/indicator-kinds`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- StrategyCreator and StrategyEditor share ~90% of their code (both use StrategyBuilderShell) — they are nearly the same page with different save targets
- Strategy Details already has a "new version" link that leads here — this creates a confusing hub-and-spoke where details and editing are separate pages but visually identical

Current UX problems:
- Mode ("edit" vs "new_version") is passed via route state or query param — if the user navigates directly to the edit URL without the state, mode defaults silently
- No way to discard changes and go back to the last saved state without navigating away
- In-place edit mode can overwrite a version that has already been backtested or deployed — there is no safeguard against editing "in-production" versions
- Version notes field is buried at the bottom of the form; users frequently forget to fill it in

Recommended domain grouping: Build

---

## Backtest Launcher

Purpose: Configure and launch a new backtest run. Accepts a Program or direct strategy/version selection, symbol list, provider, date range, walk-forward settings, and advanced execution parameters.

Primary user: Strategy developer / quant running backtests.

Creates: `POST /api/v1/backtests/launch` (BacktestRun record, triggers async execution).
Reads: `GET /api/v1/strategies`, `GET /api/v1/programs`, `GET /api/v1/data/providers`, `POST /api/v1/backtests/provider-recommendation`.
Updates: Nothing.
Deletes: Nothing.

Key actions:
- Select a Program (pre-fills all five components) OR select individual strategy/version
- Select symbols (manual list or from watchlist)
- Choose data provider (yfinance / Alpaca)
- Get AI provider recommendation
- Configure date range (start/end)
- Toggle walk-forward analysis (fold count, IS/OOS ratio)
- Toggle CPCV (combinatorial purged cross-validation)
- Set initial capital and commission assumptions
- Launch backtest (shows live status overlay while pending)
- Navigate to Run Details on completion

Related entities:
- BacktestRun
- Strategy / StrategyVersion
- Program
- Watchlist (for symbol sourcing)
- DataProvider

Key API routes:
- `POST /api/v1/backtests/launch`
- `GET /api/v1/strategies`
- `GET /api/v1/programs`
- `GET /api/v1/data/providers`
- `POST /api/v1/backtests/provider-recommendation`

Realtime streams:
- Polls `GET /api/v1/backtests/{runId}` every 5 seconds while status is "running"

Overlaps or conflicts with other pages:
- TradingPrograms has "Launch Backtest" button that navigates here pre-filled — but if the user changes the program selection here, the Programs page data is stale
- OptimizationLab has a `param_search` tab that also launches multiple backtests — two different launch paths exist
- SimulationLab also runs the BacktestEngine (real-time mode) — the line between "backtest" and "simulation" is conceptually blurry to users

Current UX problems:
- When using Program mode, the five component selections are hidden (collapsed under the program) — users don't know what they're actually backtesting unless they go to the Programs page
- Walk-forward fold count and IS/OOS ratio are numeric inputs with no explanation of what values are sensible — no inline guidance
- CPCV toggle has no tooltip explaining what CPCV is
- There is no dry-run or cost estimate before launching — large symbol lists × long date ranges silently queue
- BacktestLaunchOverlay shows basic status but no ETA or progress percentage
- After launch, navigation to RunDetails requires the user to know to go to RunHistory — there's no automatic redirect on completion

Recommended domain grouping: Validate

---

## Run History

Purpose: Tabular history of all backtest runs. Multi-column sort, status filter, search, multi-select for comparison or deletion.

Primary user: Strategy developer reviewing historical results.

Creates: Nothing (launch is on BacktestLauncher).
Reads: `GET /api/v1/backtests` (full list with metrics).
Updates: Nothing.
Deletes: `DELETE /api/v1/backtests/{runId}` (single or bulk).

Key actions:
- Sort by date, return, Sharpe, drawdown, win rate, trades, OOS return, strategy name
- Filter by run status (completed / failed / running / cancelled)
- Search by strategy name
- Select multiple runs (checkboxes) → Compare (navigates to RunDetails compare mode)
- Select multiple runs → Delete (bulk delete with confirmation)
- Click run row → navigate to RunDetails

Related entities:
- BacktestRun
- RunMetrics
- Strategy

Key API routes:
- `GET /api/v1/backtests`
- `DELETE /api/v1/backtests/{runId}` (bulk)

Realtime streams:
- Polls every 15s (for in-progress runs)

Overlaps or conflicts with other pages:
- OptimizationLab "Results" tab shows the same backtest runs list with almost identical columns and sort controls — this is a direct duplication
- Dashboard shows "recent runs" in a minimal table — three places now show runs lists

Current UX problems:
- Bulk delete has no undo — permanently destroys runs with their trades and validation evidence
- Compare action requires exactly 2 selected runs but the UI allows selecting 1–N and only fails at launch time
- No filter by strategy (only text search) — hard to see all runs for a specific strategy
- No filter by date range — the history gets very long
- "Cancelled" runs show in the list with no way to relaunch — users don't know if a cancel was intentional
- Failed runs show but the error message is not visible in the list — must click through to see why it failed
- Column widths are fixed and cause horizontal scroll on smaller screens

Recommended domain grouping: Validate

---

## Run Details

Purpose: Deep single-run analysis page. Tabs for Overview (metrics, anti-bias, feature plan), Equity & Drawdown charts, Trade Journal (expandable rows with MAE/MFE/conditions), Monthly Returns heatmap, Monte Carlo, and Promotion panel.

Primary user: Strategy developer evaluating a specific backtest result.

Creates: `POST /api/v1/backtests/{runId}/suggest-risk-profile` (suggests a Risk Profile from run stats), `POST /api/v1/deployments/promote-to-paper` (promotion panel).
Reads: `GET /api/v1/backtests/{runId}`, `GET /api/v1/backtests/{runId}/equity-curve`, `GET /api/v1/backtests/{runId}/trades`, `GET /api/v1/backtests/{runId}/regime-analysis`, `GET /api/v1/backtests/{runId}/recommendations`, `GET /api/v1/backtests/{runId}/trades/{tradeId}/replay`.
Updates: `PUT /api/v1/backtests/{runId}` (update run notes/metadata).
Deletes: `DELETE /api/v1/backtests/{runId}`.

Key actions:
- View IS vs OOS metrics (return, Sharpe, Sortino, max drawdown, win rate, profit factor, SQN)
- View anti-bias evidence (CPCV, walk-forward fold summary)
- View feature plan (indicators, signals, stops as evidence this strategy is not coincidence-fitted)
- Toggle equity / drawdown chart modes (absolute / %)
- View trade journal with expandable rows (MAE, MFE, exit reason, conditions fired per trade)
- Step through bar-by-bar trade replay (TradeReplayPanel)
- View monthly returns heatmap
- Run Monte Carlo simulation on results
- Compare with another run (delta metrics, side-by-side)
- Promote to paper trading (creates Deployment)
- Suggest risk profile from run statistics

Related entities:
- BacktestRun
- RunMetrics
- Trade
- ValidationEvidence
- WalkForwardResult
- MonteCarloResult
- CpcvResult
- Deployment (via promote)
- RiskProfile (via suggest)

Key API routes:
- `GET /api/v1/backtests/{runId}`
- `GET /api/v1/backtests/{runId}/equity-curve`
- `GET /api/v1/backtests/{runId}/trades`
- `GET /api/v1/backtests/{runId}/trades/{tradeId}/replay`
- `GET /api/v1/backtests/{runId}/regime-analysis`
- `GET /api/v1/backtests/{runId}/recommendations`
- `POST /api/v1/backtests/{runId}/compare`
- `POST /api/v1/deployments/promote-to-paper`
- `POST /api/v1/backtests/{runId}/suggest-risk-profile`

Realtime streams:
- TradeReplayPanel streams bars at configured speed

Overlaps or conflicts with other pages:
- Promotion panel here (`promote-to-paper`) overlaps with AccountGovernor which also has promotion controls (including promote-to-live) — two different places to deploy
- OptimizationLab's "Stress" tab also handles promotion flow — three places to promote a run
- Regime analysis here vs OptimizationLab "Independence" tab both analyze trade behavior — different framing, same data

Current UX problems:
- The promotion panel is on a validation page (RunDetails) but it should be on an operational page (Governor) — mixing analyze and deploy creates responsibility confusion
- Trade Journal tab with hundreds of trades becomes very slow — no virtualization
- TradeReplayPanel opens inline as a panel within the trade journal row — very cramped on standard monitors
- "Suggest Risk Profile" creates a risk profile entity but doesn't navigate the user to RiskProfiles to review it — the profile is created silently
- Compare mode is only accessible by navigating back to RunHistory, selecting two runs, and clicking Compare — no "compare with another run" button directly on this page
- Monte Carlo results are shown but there is no explanation of what the percentile bands mean
- Delete button is on this detail page alongside the analysis — risk of accidental deletion while reading results

Recommended domain grouping: Validate

---

## Account Monitor

Purpose: Broker account management dashboard. Shows paper and live account cards with equity/P&L/cash, live positions and orders fetched directly from Alpaca, active deployment monitor, account creation, editing, halt/resume/flatten/emergency-exit controls.

Primary user: Operator managing broker account connections.

Creates: `POST /api/v1/accounts` (CreateAccountModal).
Reads: `GET /api/v1/accounts`, `GET /api/v1/accounts/{id}/broker/status`, `GET /api/v1/accounts/{id}/broker/orders`, `GET /api/v1/deployments`.
Updates: `PUT /api/v1/accounts/{id}` (EditAccountModal), `POST /api/v1/accounts/{id}/sync-from-broker`.
Deletes: `DELETE /api/v1/accounts/{id}`, `DELETE /api/v1/accounts/cleanup/no-credentials`.

Key actions:
- View account equity, buying power, cash (refreshed from Alpaca)
- View open positions per account (from live broker API)
- View resting orders per account
- View active deployments per account
- Edit account settings (EditAccountModal)
- Halt trading for an account
- Resume trading for an account
- Flatten (close all positions) for an account
- Emergency exit (halt + flatten atomically)
- Create new account (paper or live)
- Delete account
- Bulk delete unconfigured paper accounts
- Sync leverage from broker

Related entities:
- Account
- Deployment
- AccountActivity
- (live broker data: positions, orders — not persisted entities)

Key API routes:
- `GET /api/v1/accounts`
- `POST /api/v1/accounts`
- `PUT /api/v1/accounts/{id}`
- `DELETE /api/v1/accounts/{id}`
- `GET /api/v1/accounts/{id}/broker/status`
- `GET /api/v1/accounts/{id}/broker/orders`
- `POST /api/v1/accounts/{id}/halt`
- `POST /api/v1/accounts/{id}/resume`
- `POST /api/v1/accounts/{id}/flatten`
- `POST /api/v1/accounts/{id}/emergency-exit`
- `POST /api/v1/accounts/{id}/sync-from-broker`
- `DELETE /api/v1/accounts/cleanup/no-credentials`

Realtime streams:
- Polls `broker/status` and `broker/orders` every 10s when account cards are expanded

Overlaps or conflicts with other pages:
- AccountGovernor ALSO shows deployments table for all accounts with halt/start/stop controls — duplicated deployment management surface
- LiveMonitor ALSO shows positions and orders from the broker — third view of the same live data
- CredentialManager handles credential CRUD for the same accounts — operations are split across two pages
- Halt/resume controls exist here AND in AccountGovernor AND in control panel (GlobalKillStrip)

Current UX problems:
- Three separate halt mechanisms (Account halt, Global kill, Governor halt) are on three different pages with no unified view of which is active where
- Account cards do not show which accounts are currently running deployments vs idle — the status badge only shows broker connectivity
- Emergency exit confirmation uses a browser `window.confirm()` dialog — inconsistent with the rest of the UI which uses ConfirmationModal
- Position data comes from Alpaca directly and is not reconciled against the internal deployment_trades table — if the paper broker has a position but Alpaca doesn't (due to simulation), the card shows nothing
- The "flatten" confirmation says "close all positions" but it calls a broker API — paper accounts can't actually flatten this way

Recommended domain grouping: Operate

---

## Credential Manager

Purpose: Manage Alpaca API key/secret credentials per account and per mode (paper/live). Validate credentials against Alpaca. Create new accounts from this page.

Primary user: Administrator / platform owner setting up broker connections.

Creates: Account (via CreateAccountModal embedded here).
Reads: `GET /api/v1/accounts`, `GET /api/v1/accounts/{id}/credentials`.
Updates: `PUT /api/v1/accounts/{id}/credentials`.
Deletes: Nothing.

Key actions:
- Select an account from list
- Toggle paper vs live mode
- View masked API key and secret key for selected account+mode
- Enter/update API key and secret key
- Toggle key visibility (show/hide)
- Validate credentials against Alpaca API (`POST /api/v1/accounts/{id}/credentials/validate`)
- Create new broker account
- Navigate to AccountMonitor for operational controls

Related entities:
- Account
- Credentials (broker_config sub-object)

Key API routes:
- `GET /api/v1/accounts`
- `GET /api/v1/accounts/{id}/credentials`
- `PUT /api/v1/accounts/{id}/credentials`
- `POST /api/v1/accounts/{id}/credentials/validate`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- AccountMonitor has an "Edit Account" modal that also updates account settings — some credential fields are accessible from both
- Services page also stores API keys (for data providers and AI providers) — two separate credential storage surfaces

Current UX problems:
- Credential page is at `/security` in the router — the URL slug gives no hint of what the page does
- There is no indication on the account list of which accounts have valid vs missing vs invalid credentials — the user must click each account to check
- Paper and live credentials are separate tabs — if the user saves paper credentials then switches to live without saving, the live credentials are reset silently
- Validation only fires on explicit button click — no warning if keys are expired or invalid when the user navigates away
- The page does not show when credentials were last validated or their current validity status in the account list

Recommended domain grouping: Admin

---

## Account Governor (Portfolio Governor)

Purpose: Account-level portfolio governance control. Shows global kill strip, per-account governor status (active/halted/paused), governor event log, portfolio snapshot (capital allocation, symbol collision warnings, program overlap), deployment table with trade viewer, and paper-to-live promotion wizard.

Primary user: Operator managing live/paper trading in real time.

Creates: `POST /api/v1/governor/{accountId}/bootstrap` (initialize governor), `POST /api/v1/governor/{accountId}/allocate` (add program allocation), `POST /api/v1/deployments/promote-to-live`.
Reads: `GET /api/v1/deployments`, `GET /api/v1/accounts`, `GET /api/v1/governor/list`, `GET /api/v1/governor/{accountId}`, `GET /api/v1/governor/{accountId}/events`, `GET /api/v1/governor/{accountId}/portfolio-snapshot`, `GET /api/v1/programs`.
Updates: `POST /api/v1/governor/{accountId}/halt`, `POST /api/v1/governor/{accountId}/resume`, `POST /api/v1/deployments/{id}/start`, `POST /api/v1/deployments/{id}/stop`.
Deletes: Nothing.

Key actions:
- Global kill all trading (GlobalKillStrip)
- Resume all trading after global kill
- Initialize governor for an account
- Select account to view its governor
- Halt governor for account (account-level, not global)
- Resume halted governor
- View governor events log (collision_suppressed, risk_blocked, daily_loss_lockout, etc.)
- View portfolio snapshot (allocated capital, symbol collisions, program overlap matrix)
- Add program to governor allocation (AddProgramModal)
- View all deployments across all accounts (table)
- Start / pause / stop individual deployments
- View paper trades for a deployment (inline trade table)
- Promote paper deployment to live trading (full safety checklist wizard)
- Get AI promotion advice (`POST /api/v1/ml/promote-advice`)

Related entities:
- PortfolioGovernor
- GovernorEvent
- Deployment
- DeploymentTradeRow
- Account
- Program
- AccountAllocation

Key API routes:
- `GET /api/v1/governor/list`
- `GET /api/v1/governor/{accountId}`
- `GET /api/v1/governor/{accountId}/events`
- `GET /api/v1/governor/{accountId}/portfolio-snapshot`
- `POST /api/v1/governor/{accountId}/bootstrap`
- `POST /api/v1/governor/{accountId}/halt`
- `POST /api/v1/governor/{accountId}/resume`
- `POST /api/v1/governor/{accountId}/allocate`
- `GET /api/v1/deployments`
- `POST /api/v1/deployments/{id}/start`
- `POST /api/v1/deployments/{id}/stop`
- `POST /api/v1/control/pause-deployment/{id}`
- `POST /api/v1/control/resume-deployment/{id}`
- `POST /api/v1/deployments/promote-to-live`
- `POST /api/v1/ml/promote-advice`
- `GET /api/v1/deployments/{id}/trades`

Realtime streams:
- Polls governor state every 15s
- Polls deployment trades every 60s

Overlaps or conflicts with other pages:
- AccountMonitor shows the same deployment table — two pages manage deployments
- DeploymentManager page ALSO shows the same deployments with position-level controls
- Run Details has a promote-to-paper panel — promotion is split across three pages (RunDetails, AccountGovernor, OptimizationLab)
- Control page (GlobalKillStrip) logic is embedded here and also accessible via `/api/v1/control/kill-all` from the header kill switch button
- LiveMonitor also shows positions and orders for running deployments — fourth view of live broker data

Current UX problems:
- This is the most overloaded page in the system: it manages 7 distinct concerns (global kill, account governor status, portfolio snapshot, deployment list, trades viewer, promotion wizard, and program allocation)
- The "Promote to Live" button is styled `btn-danger` (red) even when the intent is to launch live trading — this is confusing (danger vs positive action)
- The safety checklist on promotion (LIVE_SAFETY_CHECKS) has identical check items to the DeploymentManager's checklist — copied code, risk of divergence
- "Add Program" modal requires the user to know the program is deployable (all 5 components complete) — but it shows the error only after selecting — should filter the list upfront
- Governor event log only loads on expansion (lazy), but real-time events during a halt are not pushed — can miss events between polling cycles
- The deployment table shows all deployments for all accounts — no filter by account — gets unwieldy with multiple accounts and programs

Recommended domain grouping: Operate

---

## Deployment Manager

Purpose: Legacy/alternate deployment lifecycle management. Shows all deployments with position-level actions (scale-out, replace stop, move stop to breakeven), paper-to-live promotion wizard (duplicate of AccountGovernor's), and AI position advice.

Primary user: Operator managing active positions.

Creates: `POST /api/v1/deployments/promote-to-live`.
Reads: `GET /api/v1/deployments`, `GET /api/v1/accounts`, `GET /api/v1/strategies`, `GET /api/v1/deployments/{id}/trades`.
Updates: `POST /api/v1/deployments/{id}/positions/{symbol}/scale-out`, `POST /api/v1/deployments/{id}/positions/{symbol}/replace-stop`, `POST /api/v1/deployments/{id}/positions/{symbol}/move-stop-be`.
Deletes: Nothing.

Key actions:
- View all deployments (table)
- View trades per deployment (expandable inline table)
- Open position actions panel per trade: scale-out partial exit, replace stop price, move stop to breakeven
- Get AI advice on a position (`POST /api/v1/ml/position-advice`)
- Promote paper to live (same wizard as AccountGovernor)

Related entities:
- Deployment
- DeploymentTradeRow
- Account
- Strategy

Key API routes:
- `GET /api/v1/deployments`
- `GET /api/v1/deployments/{id}/trades`
- `POST /api/v1/deployments/{id}/positions/{symbol}/scale-out`
- `POST /api/v1/deployments/{id}/positions/{symbol}/replace-stop`
- `POST /api/v1/deployments/{id}/positions/{symbol}/move-stop-be`
- `POST /api/v1/deployments/promote-to-live`
- `POST /api/v1/ml/position-advice` (inferred)

Realtime streams:
- Polls deployment list and trades every 15-60s

Overlaps or conflicts with other pages:
- This page and AccountGovernor share the deployment table, the trade viewer, and the promotion wizard — they are 80% the same page
- LiveMonitor ALSO shows positions with close actions — three places to act on positions
- Position actions (scale-out, stop replace) are here but account-level halt/flatten are on AccountMonitor and AccountGovernor — split controls

Current UX problems:
- This page is at `/deployments` (aliased to `/portfolio-governors` and `/governor`) — the URL aliasing is confusing; three different URL slugs lead to different but overlapping pages
- The LIVE_SAFETY_CHECKS array in this file is a copy-paste from AccountGovernor — these will diverge
- Position actions panel (`PositionActionsPanel`) requires entering `stopOrderId` manually — the user must know the internal Alpaca order ID
- Scale-out only works by specifying a manual percentage with no suggestion of sensible values based on the execution style
- AI position advice requires a paper deployment and the ML service to be running — if either is unavailable, the panel silently fails

Recommended domain grouping: Operate

---

## Risk Profiles

Purpose: Create, view, edit, duplicate, and delete risk profile templates. Inline AI analysis to suggest name/description and flag dangerous parameter combinations. Linked accounts display per profile.

Primary user: Risk manager / strategy developer configuring sizing and drawdown limits.

Creates: `POST /api/v1/risk-profiles`.
Reads: `GET /api/v1/risk-profiles`, `GET /api/v1/risk-profiles/{id}`.
Updates: `PUT /api/v1/risk-profiles/{id}`.
Deletes: `DELETE /api/v1/risk-profiles/{id}`, `POST /api/v1/risk-profiles/{id}/detach-from-account` (detach).

Key actions:
- View list of risk profiles (golden templates + user profiles)
- Create new profile (inline form, no modal)
- Edit profile (inline form within detail view)
- Duplicate profile
- Delete profile (with confirmation)
- Analyze profile with AI (`POST /api/v1/risk-profiles/analyze`) — suggests name, description, flags dangerous ratios
- Detach profile from an account
- View linked accounts per profile

Related entities:
- RiskProfile
- Account (linked_accounts)

Key API routes:
- `GET /api/v1/risk-profiles`
- `POST /api/v1/risk-profiles`
- `PUT /api/v1/risk-profiles/{id}`
- `DELETE /api/v1/risk-profiles/{id}`
- `GET /api/v1/risk-profiles/{id}`
- `POST /api/v1/risk-profiles/analyze`
- `POST /api/v1/risk-profiles/{id}/duplicate`
- `POST /api/v1/risk-profiles/detach-from-account/{accountId}`

Realtime streams:
- None (30s polling)

Overlaps or conflicts with other pages:
- TradingPrograms embeds a risk profile selector inline — user can navigate here from that page but the link says "Create or Manage Risk Profiles" which adds friction
- RunDetails can auto-generate a risk profile ("suggest-risk-profile") — the created profile appears here but the user isn't notified or navigated here after creation

Current UX problems:
- The inline validation rules panel (ValidationInfoPanel) is well-designed but its toggle button is tiny and easy to miss
- "Linked accounts" shows accounts but doesn't show programs or deployments that use this profile — risk of deleting a profile that's in active use in a program
- Deleting a profile that is linked to an active program silently fails or returns an error — no pre-delete impact warning
- The `source_type` field (manual / backtest / optimizer) is editable by the user — a "backtest" profile can be manually changed to "manual", destroying provenance info
- Golden templates (is_golden) are read-only but there's no "copy golden template to new profile" shortcut — only a generic duplicate button

Recommended domain grouping: Build

---

## Strategy Controls (Strategy Governors)

Purpose: Create, view, edit, duplicate, and delete strategy controls templates. Controls define timing gates: timeframe, duration mode, session windows, force-flat time, session caps, PDT enforcement, gap risk, regime filters, and cooldown rules.

Primary user: Strategy developer / risk manager configuring execution timing.

Creates: `POST /api/v1/strategy-governors`.
Reads: `GET /api/v1/strategy-governors`, `GET /api/v1/strategy-governors/{id}`.
Updates: `PUT /api/v1/strategy-governors/{id}`.
Deletes: `DELETE /api/v1/strategy-governors/{id}`.

Key actions:
- View list of strategy controls (golden templates + user controls)
- Filter by duration mode (day / swing / position)
- Create new controls (inline form)
- Edit controls (inline form within detail view)
- Duplicate controls
- Delete controls
- AI summarize (`POST /api/v1/strategy-governors/{id}/summarize`) — suggests name, description, checks compatibility with day/swing/position
- Configure session windows (start/end HH:MM pairs)
- Configure force-flat time
- Configure session caps (max trades/session, max trades/day, min minutes between entries)
- Configure cooldown rules (trigger: stop_hit / consecutive_losses / daily_loss_limit; duration in minutes or bars)
- Configure PDT rules (enforce flag, max day trades, equity threshold, action on limit)
- Configure gap risk (max gap %, earnings blackout)
- Configure regime filter (allowed regimes)

Related entities:
- StrategyControls
- MarketHoursConfig
- PDTConfig
- GapRiskConfig
- CooldownRule

Key API routes:
- `GET /api/v1/strategy-governors`
- `POST /api/v1/strategy-governors`
- `PUT /api/v1/strategy-governors/{id}`
- `DELETE /api/v1/strategy-governors/{id}`
- `POST /api/v1/strategy-governors/analyze`
- `POST /api/v1/strategy-governors/{id}/duplicate`

Realtime streams:
- None (30s polling)

Overlaps or conflicts with other pages:
- Page is at route `/strategy-controls` but also aliased to `/governors` — confusing slug; "governors" suggests AccountGovernor, not strategy-level timing
- TradingPrograms refers to this component as "Strategy Controls" but the database column is `strategy_governor_id` — naming inconsistency across the stack
- Regime filter here can contradict what the strategy's condition tree does if the user doesn't know the strategy's indicator set

Current UX problems:
- Session windows are entered as raw HH:MM strings — no clock picker, no timezone-aware display; times are implicitly ET but there's no label confirming this
- Cooldown rules use either "minutes" or "bars" as units — the unit toggle is ambiguous without context of what the strategy's timeframe is; the form shows the timeframe (from the controls), but cooldown rules are configured separately from the timeframe selection
- PDT section is collapsed by default — new users who are subject to PDT rules won't know it needs to be configured
- Regime filter allows selecting multiple regimes but there's no explanation of how regimes are detected — the platform's regime detection mechanism is invisible to the user
- The AI summarize feature auto-updates the name and description fields without explicit user approval — silent mutation is surprising

Recommended domain grouping: Build

---

## Execution Styles

Purpose: Create, view, edit, duplicate, and delete execution style templates. Controls Alpaca order mechanics: entry order type, time-in-force, limit offset, exit bracket mode (bracket/OCO/trailing/none), scale-out levels with stop progression, breakeven moves, final runner exits, and backtest fill assumptions.

Primary user: Quant / strategy developer configuring order expression.

Creates: `POST /api/v1/execution-styles`.
Reads: `GET /api/v1/execution-styles`, `GET /api/v1/execution-styles/{id}`.
Updates: `PUT /api/v1/execution-styles/{id}`.
Deletes: `DELETE /api/v1/execution-styles/{id}`.

Key actions:
- View list of execution styles (golden templates + user styles)
- Select from 4 quick-start templates (Market+Bracket, Limit Pullback, Stop-Limit Breakout, Trailing Exit)
- Create new style (inline form)
- Edit style (inline form within detail view)
- Duplicate style
- Delete style
- AI analyze (`POST /api/v1/execution-styles/analyze`) — suggests name, description, checks for dangerous combos
- Configure entry order type (market/limit/stop/stop_limit) + TIF (day/gtc/ioc/opg/cls)
- Configure limit offset method (ATR/pct/fixed) and value
- Configure cancel-after-bars for unfilled limit orders
- Configure bracket mode (bracket/oco/trailing_stop/none)
- Configure stop order type and take-profit order type
- Configure trailing stop type and value
- Configure scale-out levels (% per level with stop progression multipliers)
- Configure ATR source (strategy ATR or custom length/timeframe)
- Configure breakeven trigger level and ATR offset
- Configure final runner exit mode (internal vs Alpaca trailing)
- Configure backtest fill model (next_open / bar_close / VWAP proxy), slippage bps, commission per share
- Real-time execution preview rail (shows broker behavior and backtest behavior as plain English sentences)

Related entities:
- ExecutionStyle
- ScaleOutLevel
- StopProgressionTarget

Key API routes:
- `GET /api/v1/execution-styles`
- `POST /api/v1/execution-styles`
- `PUT /api/v1/execution-styles/{id}`
- `DELETE /api/v1/execution-styles/{id}`
- `POST /api/v1/execution-styles/analyze`
- `POST /api/v1/execution-styles/{id}/duplicate`

Realtime streams:
- None (30s polling)

Overlaps or conflicts with other pages:
- TradingPrograms embeds an execution style selector — the link to create styles sends user here, breaking the program composition flow
- Strategy stops configuration (in StrategyBuilderShell) overlaps conceptually with execution style stop/bracket config — stop price is set by Strategy but the order mechanics are set by Execution Style; this boundary is not obvious to users

Current UX problems:
- The execution preview rail (right sidebar) only shows on large screens (hidden below `lg`) — on typical laptop screens the user loses the most valuable feedback while editing
- Scale-out level table editing is complex: each row has 3 inputs (%, stop multiplier) plus a delete button; there's no drag-to-reorder and no preview of what the stop progression looks like geometrically
- Stop progression targets array is index-coupled with scale_out levels — if a level is deleted, the progression indexes shift silently; the UI handles this but the model is fragile
- IOC + bracket is flagged as a Danger warning (because Alpaca rejects it) but the user can still save the style — the validation is advisory only, not enforced
- The "ATR source: custom" option requires entering both length and timeframe — if either is missing it shows a danger hint but still allows saving

Recommended domain grouping: Build

---

## Watchlist Library

Purpose: Create, view, edit, and manage symbol watchlists. Supports manual lists, scanners, index composition, sector rotation, and earnings calendar types. Per-symbol membership state management (active/candidate/pending_removal/inactive/suspended).

Primary user: Strategy developer / portfolio manager managing trading universes.

Creates: `POST /api/v1/watchlists`.
Reads: `GET /api/v1/watchlists`, `GET /api/v1/watchlists/{id}`.
Updates: `PUT /api/v1/watchlists/{id}`, `POST /api/v1/watchlists/{id}/refresh`, `POST /api/v1/watchlists/{id}/memberships/{symbol}/state`.
Deletes: `DELETE /api/v1/watchlists/{id}`.

Key actions:
- View list of watchlists (golden templates + user lists) with type badges and active symbol count
- Create new watchlist (inline form)
- Edit watchlist metadata (name, description, type)
- Duplicate watchlist
- Delete watchlist
- Add symbols to watchlist (TickerSearch component)
- Remove symbols from watchlist
- Change symbol membership state (active → candidate → pending_removal → inactive → suspended)
- Refresh watchlist (trigger re-evaluation of scanner/index type lists)
- Search symbols within a watchlist
- View watchlist in detail (symbol grid with state, last refresh time)

Related entities:
- Watchlist
- WatchlistMembership

Key API routes:
- `GET /api/v1/watchlists`
- `POST /api/v1/watchlists`
- `PUT /api/v1/watchlists/{id}`
- `DELETE /api/v1/watchlists/{id}`
- `GET /api/v1/watchlists/{id}`
- `POST /api/v1/watchlists/{id}/refresh`
- `POST /api/v1/watchlists/{id}/memberships/{symbol}/state`
- `POST /api/v1/watchlists/{id}/duplicate`

Realtime streams:
- None (30s polling)

Overlaps or conflicts with other pages:
- DataManager also shows watchlists from the `/api/v1/data/watchlists` endpoint — there are TWO separate watchlist CRUD systems (one under `/data/watchlists`, one under `/watchlists`) with unclear ownership
- TradingPrograms embeds a multi-watchlist selector and combination-rule picker — the user creates watchlists here but assembles them in Programs
- BacktestLauncher can source symbols from watchlists — adds a third consumer of watchlist data

Current UX problems:
- The two-watchlist-API confusion (data router vs watchlists router) is the biggest problem: the DataManager uses `POST /data/watchlists` while WatchlistLibrary uses `POST /watchlists` — it's unclear if these are the same entities or separate systems
- Membership state machine (active/candidate/pending_removal/inactive/suspended) is powerful but undocumented in the UI — users don't know what state transitions are valid or what each state means operationally
- Symbol search uses the TickerSearch component which queries the data service — if no data service is configured, adding symbols fails silently
- No bulk state change — changing 50 symbols from "candidate" to "active" requires 50 individual clicks
- Scanner and index watchlist types imply automatic symbol population but the refresh mechanism is manual (button-triggered) — users expect auto-refresh

Recommended domain grouping: Build

---

## Trading Programs

Purpose: Assemble the five-component program (Strategy + Controls + Risk Profile + Execution Style + Watchlists). Guided composition with per-card status (complete/missing), readiness panel, program validation, and account allocation management.

Primary user: Quant assembling a deployable trading unit.

Creates: `POST /api/v1/programs` (CreateProgramModal).
Reads: `GET /api/v1/programs`, `GET /api/v1/programs/{id}`, `GET /api/v1/programs/{id}/allocations`, plus lazy loads of all five component types.
Updates: `PATCH /api/v1/programs/{id}` (component links, name, description, notes), `POST /api/v1/programs/{id}/validate`.
Deletes: Nothing (deprecate/freeze only via separate endpoints).

Key actions:
- View program list (with completion indicator, status badge, duration mode)
- Create new program (CreateProgramModal — name, description, duration mode, optional initial strategy version)
- Select strategy version for program
- Select strategy controls for program
- Select risk profile for program
- Select execution style for program
- Select watchlists + combination rule (union/intersection)
- Save program details
- Validate program (checks all 5 components, returns expected behavior description)
- View account allocations for program (with status badges, capital, conflict resolution)
- Start / stop allocations
- Navigate to Simulation Lab with program pre-filled
- Navigate to Backtest Launcher with program pre-filled
- Navigate to AccountGovernor to deploy

Related entities:
- TradingProgram
- Strategy / StrategyVersion
- StrategyControls
- RiskProfile
- ExecutionStyle
- Watchlist
- AccountAllocation

Key API routes:
- `GET /api/v1/programs`
- `POST /api/v1/programs`
- `PATCH /api/v1/programs/{id}`
- `POST /api/v1/programs/{id}/validate`
- `GET /api/v1/programs/{id}/allocations`
- `POST /api/v1/programs/{id}/allocations/{id}/start`
- `POST /api/v1/programs/{id}/allocations/{id}/stop`

Realtime streams:
- Polls every 30s

Overlaps or conflicts with other pages:
- AccountGovernor has an "Add Program" modal that also creates allocations for a program — two places to manage program-to-account binding
- AccountGovernor shows allocation status badges that match what's shown in the allocations section here — synchronized state but separate views
- Each of the five component selectors has a "browse" link that navigates away from the program — the user loses their in-progress program composition and must navigate back

Current UX problems:
- Navigating to a component library (e.g., Risk Profiles) to create one breaks the program composition flow — there is no inline creation for components; the user must leave and return
- Programs lock automatically when they have active allocations ("frozen" status) — but the lock message is small and users frequently try to edit and wonder why changes don't stick
- The five-component progress bar shows 0/5 to 5/5 but there's no visual indication of which card is currently expanded
- The readiness panel on the right sidebar is sticky on xl screens but collapses to a scrolled section on smaller screens — the validation state is invisible while editing cards on mobile
- Program validation does not check that the selected strategy version's timeframe matches the strategy controls' timeframe — a mismatch will cause a silent runtime failure
- Allocation status badges (paper/promoted_to_live/paused/killed) don't show the account name — the user can't tell which account is which by looking at the list

Recommended domain grouping: Build

---

## Optimization Lab

Purpose: Multi-tab post-backtest analysis workspace. Tabs: Results (sortable run grid with multi-select), Walk-Forward Analysis (fold waterfall), Comparison (side-by-side delta metrics), Independence (signal overlap gauge and heatmap), Paper→Live Stress Monitor (active deployment stats + promotion flow), and Param Search (grid-search parameter optimization launcher).

Primary user: Quant evaluating a strategy portfolio before deploying.

Creates: `POST /api/v1/backtests/optimize` (Param Search tab), `POST /api/v1/deployments/promote-to-paper` (Stress tab).
Reads: `GET /api/v1/backtests`, `GET /api/v1/strategies`, `GET /api/v1/accounts`, `GET /api/v1/deployments`, plus individual run details for comparison.
Updates: Nothing.
Deletes: `DELETE /api/v1/backtests/{runId}` (in Results tab).

Key actions:
- Filter results by strategy, status, date range, symbol
- Sort results by IS/OOS Sharpe, return, max drawdown, SQN, degradation, overfit score
- Multi-select runs for comparison or promotion
- View walk-forward fold waterfall for selected runs
- Side-by-side metric comparison with delta coloring
- View signal independence scores and overlap heatmap
- Monitor paper deployments (equity, positions, P&L) in Stress tab
- Promote selected paper deployment to live from Stress tab
- Launch parameter grid search (param_search tab) — configure param grid, objective metric, max combinations, launch optimization run

Related entities:
- BacktestRun
- RunMetrics
- WalkForwardResult
- Deployment
- Strategy

Key API routes:
- `GET /api/v1/backtests`
- `GET /api/v1/backtests/{runId}` (detail fetches)
- `POST /api/v1/backtests/{runId}/compare`
- `POST /api/v1/backtests/optimize`
- `GET /api/v1/deployments`
- `POST /api/v1/deployments/promote-to-paper`
- `POST /api/v1/deployments/promote-to-live`

Realtime streams:
- Polls active deployments every 30s in Stress tab

Overlaps or conflicts with other pages:
- Results tab is a superset of RunHistory — both show the same backtest runs list with nearly identical columns and sort controls
- Comparison tab's functionality also lives in RunDetails compare mode — identical delta metric view, two locations
- Paper→Live promotion in Stress tab is the third place to promote (after RunDetails and AccountGovernor)
- Param Search duplicates the optimization launcher that could be integrated into BacktestLauncher

Current UX problems:
- Six tabs with very different purposes in a single page creates cognitive overload — the "lab" metaphor doesn't help users navigate
- Results tab loads ALL backtest runs — no pagination — becomes very slow with 100+ runs
- Walk-forward tab shows a "fold waterfall" but there's no explanation of what it means for a strategy to pass or fail walk-forward
- Independence tab's overlap heatmap is only useful with 3+ strategies selected — but the multi-select interaction isn't obvious to first-time users
- Stress tab (Paper→Live) has a duplicate safety checklist with different key names from AccountGovernor's checklist — the two will diverge
- Param Search tab launches optimization but results come back as regular backtest runs — there's no way to see which runs are "optimization runs" vs regular runs in RunHistory

Recommended domain grouping: Validate

---

## Simulation Lab

Purpose: Real-time forward simulation using the full BacktestEngine, bar-by-bar over historical data with a live chart. Play/pause/step/fast-forward controls, configurable speed (1×–500×), multi-pane chart (price + volume + oscillator + equity strip), indicator panel, right sidebar with Metrics/Positions/Trade Log tabs. Can pre-fill from a Program.

Primary user: Strategy developer validating signal behavior before committing to a backtest.

Creates: `POST /api/v1/simulations` (create simulation run).
Reads: `GET /api/v1/strategies`, `GET /api/v1/programs`, `GET /api/v1/services`, strategy indicator kinds.
Updates: Nothing (simulation is ephemeral).
Deletes: `DELETE /api/v1/simulations/{id}` (cleanup on exit).

Key actions:
- Configure simulation: select strategy or program, symbol, timeframe, date range, provider, initial capital
- Launch simulation (creates simulation session)
- Play / pause bar-by-bar replay
- Step forward one bar
- Fast-forward to configured speed
- Toggle indicator overlays (EMA, SMA, HMA, VWMA, DEMA, Bollinger, Keltner, Donchian, Parabolic SAR, Ichimoku, RSI, MACD, Stochastic, ADX, ATR, IBS, Z-score, BT_Snipe, OBV, BOP)
- View live equity strip below price chart
- View metrics panel (running Sharpe, return, drawdown, win rate)
- View open positions (symbol, entry, P&L)
- View trade log (all trades with entry/exit/reason)

Related entities:
- Simulation (ephemeral session)
- Strategy / StrategyVersion
- Program
- BarSnapshotData (streamed)
- TradeEvent (streamed)
- SimulationMetadata

Key API routes:
- `POST /api/v1/simulations`
- `POST /api/v1/simulations/{id}/start`
- `POST /api/v1/simulations/{id}/pause`
- `POST /api/v1/simulations/{id}/step`
- `DELETE /api/v1/simulations/{id}`
- `GET /api/v1/services` (to check if data service is available)

Realtime streams:
- WebSocket `/ws/simulation/{simulationId}` — receives bar snapshots, trade events, metrics updates at configured speed

Overlaps or conflicts with other pages:
- Chart indicator catalogue is an exact copy-paste from ChartLab (INDICATOR_GROUPS array appears in both SimulationLab and ChartLab) — duplication and divergence risk
- SimulationLab also has a setup drawer that looks similar to BacktestLauncher's configuration form — visual overlap confuses users about when to use each
- BacktestLauncher also generates trades and equity curves — the conceptual distinction between "simulation" (real-time, bar-by-bar) and "backtest" (completed, statistical analysis) isn't communicated in the UI

Current UX problems:
- WebSocket reconnection on network interruption is not handled — if the WS drops mid-simulation, the user must restart
- The setup drawer auto-collapses after launch — good UX — but the re-open button is small and easy to miss
- No ability to save a simulation result as a backtest run for persistence — ephemeral results are lost when the user navigates away
- At 500× speed, the chart rerenders every few ms — this causes visible lag on slower machines; no frame-limiting
- Indicator toggles are organized in a grouped panel but take up screen real estate from the chart — no way to collapse the indicator panel
- Program selection bypasses individual component configuration — user can't override a single component (e.g., test a different symbol) without leaving the Program

Recommended domain grouping: Validate

---

## Chart Lab

Purpose: Static indicator visualization tool for cached OHLCV data. Multi-pane chart: price (candlestick + overlays), volume, and oscillator. No simulation, no signals — purely for visual inspection of indicator behavior on a symbol.

Primary user: Strategy developer analyzing indicator behavior before encoding conditions.

Creates: Nothing.
Reads: `GET /api/v1/data/inventory` (available cached datasets), `GET /api/v1/data/indicators/{symbol}/{timeframe}` (bars + computed indicators).
Updates: Nothing.
Deletes: Nothing.

Key actions:
- Select symbol from cached data inventory
- Select timeframe from cached data inventory
- Toggle indicator overlays on price pane (EMA 9/20/50/200, SMA 20/50/200, HMA 20, VWMA 20, DEMA 9/21, BB 20, Keltner 20, Donchian 20, Parabolic SAR, Ichimoku)
- Toggle oscillator indicators (RSI 14, MACD, Stochastic 14, ADX 14, ATR 14, IBS, Z-score 20, BT_Snipe, OBV)
- Zoom in / zoom out (last N bars)
- Scroll chart

Related entities:
- DataInventoryItem (cached OHLCV datasets)
- Bar (OHLCV)
- IndicatorSeries (computed series)

Key API routes:
- `GET /api/v1/data/inventory`
- `GET /api/v1/data/indicators/{symbol}/{timeframe}`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- SimulationLab contains the exact same indicator catalogue — INDICATOR_GROUPS is copy-pasted
- DataManager also shows the data inventory — two views of the same inventory
- RunDetails has a TradeReplayPanel that shows a price chart with entry/exit markers — a fourth chart surface with different data but similar rendering

Current UX problems:
- Chart Lab requires data to be pre-cached in DataManager before symbols appear — if data isn't cached, the inventory is empty with no actionable prompt to fetch it
- No date range selector — always shows all cached bars for the symbol; long histories make the chart unreadable at default zoom
- No crosshair / OHLC tooltip on hover — users can't read exact values from the chart
- Candlestick rendering uses a custom Recharts workaround (Customized component) because Recharts doesn't support native candlesticks — this is fragile and slow
- No ability to draw trendlines, horizontal levels, or annotations
- Indicator parameter values are hardcoded (EMA 9, EMA 20, etc.) — the user cannot change the period without modifying the code

Recommended domain grouping: Validate

---

## Data Manager

Purpose: 5-step wizard to fetch and cache OHLCV market data. Provider selection (yfinance vs Alpaca), symbol search, timeframe/date range configuration, review summary, and batch fetch with progress. Shows existing data inventory. Also manages watchlists (separate from WatchlistLibrary).

Primary user: Anyone who needs to download historical data before backtesting or charting.

Creates: `POST /api/v1/data/fetch` (single symbol), `POST /api/v1/data/fetch-many` (batch).
Reads: `GET /api/v1/data/inventory`, `GET /api/v1/data/inventory/{symbol}/{timeframe}`, `GET /api/v1/data/providers`, `GET /api/v1/accounts` (for Alpaca provider auth).
Updates: Nothing.
Deletes: `DELETE /api/v1/data/cache/{symbol}/{timeframe}`.

Key actions:
- Step 1: Select provider (yfinance or Alpaca); shows provider capabilities, limits, and rate info
- Step 2: Search and select symbols (TickerSearch)
- Step 3: Configure timeframe (yfinance: 1m/5m/15m/30m/1h/1d/1wk/1mo; Alpaca: all + 4h), date range (respects provider max lookback per timeframe)
- Step 4: Review summary (symbols × timeframes × estimated bar count)
- Step 5: Execute fetch with progress indicator; shows BatchFetchResult
- View data inventory (existing cached datasets with source, bar count, date range)
- Delete a cached dataset
- Navigate to ChartLab for a cached dataset

Related entities:
- DataInventoryItem
- DataProvider (yfinance / Alpaca)
- Watchlist (via `POST /data/watchlists` — SEPARATE from WatchlistLibrary watchlists)

Key API routes:
- `GET /api/v1/data/providers`
- `GET /api/v1/data/inventory`
- `GET /api/v1/data/inventory/{symbol}/{timeframe}`
- `POST /api/v1/data/fetch`
- `POST /api/v1/data/fetch-many`
- `DELETE /api/v1/data/cache/{symbol}/{timeframe}`
- `GET /api/v1/data/search`

Realtime streams:
- None (polling for batch fetch progress)

Overlaps or conflicts with other pages:
- WatchlistLibrary manages watchlists at `POST /api/v1/watchlists` — DataManager has its own watchlist endpoints at `POST /api/v1/data/watchlists` — THESE ARE DIFFERENT ENTITIES and this is a critical architectural inconsistency
- ChartLab inventory view shows the same cached datasets — DataManager is the create/delete side of the same view
- BacktestLauncher has a provider recommendation feature that overlaps with this page's provider selection guidance

Current UX problems:
- The 5-step wizard is good UX for first-time use but is slow for repeat users who know what they want — no "quick fetch" shortcut
- yfinance intraday lookback limits (1m = 7 days, 5m–30m = 60 days) are enforced by the component but the error messages when the date is out of range are not always clear
- Alpaca data download requires an Alpaca data subscription — if the account has only the free tier, requests for 1m bars will fail silently (Alpaca returns an error that the service may not surface clearly)
- Batch fetch result shows success/failure per symbol but there's no way to retry only the failed symbols
- The watchlist management section inside DataManager manages DIFFERENT watchlists than WatchlistLibrary — this is confusing and should be consolidated

Recommended domain grouping: Build

---

## Event Calendar

Purpose: Weekly calendar view of market events (macro economic events, earnings, FDA dates, Fed meetings, etc.). Filter by impact (high/medium/low), symbol, category. Navigate week-by-week. Event creation and filter management.

Primary user: Operator reviewing upcoming market risk events before entering trades.

Creates: `POST /api/v1/events` (create market event), `POST /api/v1/events/seed-sample` (seed example events), `POST /api/v1/events/filters` (create event filter).
Reads: `GET /api/v1/events` (with date range, symbol, category filters), `GET /api/v1/events/filters`.
Updates: Nothing (events are append-only).
Deletes: Nothing visible in UI.

Key actions:
- Navigate to previous/next week
- Jump to today
- Filter by impact level (all / high / medium / low)
- Search events by name or symbol
- View events in weekly calendar grid (days as columns, events as cards)
- Expand event cards to view details
- Create new market event (category, symbol, event_time, impact, source)
- Seed sample events (for testing)
- View event filters list
- Create event filter

Related entities:
- MarketEvent
- EventFilter

Key API routes:
- `GET /api/v1/events`
- `POST /api/v1/events`
- `POST /api/v1/events/seed-sample`
- `GET /api/v1/events/filters`
- `POST /api/v1/events/filters`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- Strategy Controls has "earnings blackout" configuration — users need to correlate event calendar data with strategy controls but there's no link between them
- The events calendar is standalone — there's no integration with the backtest engine to exclude events, despite the gap risk config in Strategy Controls referencing earnings blackouts

Current UX problems:
- Manual event creation is not practical — in production, events should come from a data feed (e.g., Benzinga, Yahoo Finance events API) — the manual creation UI exists but the feed integration is missing
- "Seed sample" button is visible in production — it should be admin/dev only
- No edit or delete actions on existing events
- Event filters exist as a concept but there's no visible effect of filter application anywhere in the system — it's unclear what an EventFilter does operationally
- The calendar has no timezone display — events created in UTC vs ET are ambiguous
- No visual distinction between past and future events (both styled the same)

Recommended domain grouping: Operate

---

## Live Monitor

Purpose: Real-time monitoring of active paper and live deployments. Tab-per-deployment interface with live positions, orders, equity, P&L, WebSocket push for real-time updates, and single-position close controls.

Primary user: Operator watching active trades in real time.

Creates: Nothing.
Reads: `GET /api/v1/monitor/runs` (active deployments), `GET /api/v1/monitor/runs/{id}` (detail + live Alpaca data), `GET /api/v1/monitor/runs/{id}/positions`, `GET /api/v1/monitor/runs/{id}/orders`, `GET /api/v1/monitor/accounts`.
Updates: `POST /api/v1/monitor/runs/{id}/close-position` (close one position), `POST /api/v1/monitor/runs/{id}/close-all` (emergency close all).
Deletes: Nothing.

Key actions:
- View all active deployments as tabs (tab bar with equity/P&L summary)
- Select deployment tab to view detail
- View open positions per deployment (symbol, direction, quantity, entry price, current price, unrealized P&L, stop)
- View resting orders per deployment
- View equity and cash balances
- View WebSocket connection status (Wifi icon, shows "last event N seconds ago")
- Close a single position
- Emergency close all positions

Related entities:
- LiveRun (deployment + live broker state)
- LivePosition
- LiveOrder
- Account (for equity data)

Key API routes:
- `GET /api/v1/monitor/runs`
- `GET /api/v1/monitor/runs/{id}`
- `GET /api/v1/monitor/runs/{id}/positions`
- `GET /api/v1/monitor/runs/{id}/orders`
- `GET /api/v1/monitor/accounts`
- `POST /api/v1/monitor/runs/{id}/close-position`
- `POST /api/v1/monitor/runs/{id}/close-all`

Realtime streams:
- WebSocket `/ws` (main platform broadcast channel) for live updates
- Falls back to polling when WebSocket is disconnected

Overlaps or conflicts with other pages:
- AccountMonitor shows the same positions and orders from the broker — two live position views
- AccountGovernor shows paper trades per deployment — three views of running trade data
- DeploymentManager has position action panel (scale-out, stop move) — the same actions that should be here for the "active monitoring" use case

Current UX problems:
- "Close position" requires the symbol name — but there are no symbol selectors; the user must know the symbol string exactly (the UI likely uses the symbol from the position row)
- WebSocket connection shows age of last event but doesn't reconnect automatically — if disconnected, the user sees stale data without a prominent warning
- Tab-per-deployment design breaks down with many deployments — 10 deployments creates a very wide tab bar
- P&L display shows raw dollar amounts but not % of allocated capital — context is lost
- No alarm or notification when a stop is hit or a target is reached — the user must keep watching

Recommended domain grouping: Operate

---

## Services

Purpose: Configure external service connections — data providers (Alpaca, yfinance) and AI providers (Google Gemini, Groq). CRUD for DataService records. Test connectivity. Mark a service as default/active.

Primary user: Administrator / platform owner setting up external integrations.

Creates: `POST /api/v1/services`.
Reads: `GET /api/v1/services`.
Updates: `PUT /api/v1/services/{id}` (edit), `POST /api/v1/services/{id}/test` (test connection), `POST /api/v1/services/{id}/set-default`.
Deletes: `DELETE /api/v1/services/{id}`.

Key actions:
- View list of configured data services (with type badges, connection status, default flag)
- Create new data service (name, provider, API key, secret, environment paper/live)
- Create new AI service (name, provider Gemini/Groq, API key, model selection)
- Edit service credentials
- Test service connectivity (validates API key, shows success/error)
- Set a service as default for its type
- Delete service
- Toggle API key visibility (show/hide masked values)

Related entities:
- DataServiceRecord (data_services table)

Key API routes:
- `GET /api/v1/services`
- `POST /api/v1/services`
- `PUT /api/v1/services/{id}`
- `DELETE /api/v1/services/{id}`
- `POST /api/v1/services/{id}/test`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- CredentialManager ALSO stores Alpaca API credentials (per account) — services stores Alpaca credentials for data access while CredentialManager stores them for trading access — two separate stores for the same credentials
- Data Manager references data services to determine which provider to use — but the Services page and DataManager are not visually connected

Current UX problems:
- Two separate credential stores (Services and CredentialManager) for Alpaca credentials is a maintenance problem — the user may configure different keys in each and not understand why data works but trading doesn't or vice versa
- Service "test" button tests connectivity but doesn't indicate what the test actually does (e.g., "fetched 1 bar of AAPL successfully" vs just "connected")
- No indication of last test timestamp — a service that tested green last week may have expired keys
- AI service model selection shows Gemini 2.0 Flash "Experimental" — no guidance on which model is appropriate for the platform's use cases
- There is no automatic fallback if the default service becomes unavailable — strategies that depend on a specific data provider will silently fail

Recommended domain grouping: Admin

---

## Logs Panel

Purpose: Multi-tab operational monitoring dashboard containing: Events (kill/pause event audit log), Roadmap (platform development phase tracker with step-level status), User Journey Validations (structured end-to-end journey checklist), Known Issues (severity-tagged issue tracker), and Feature Build Progress (feature implementation status).

Primary user: Platform administrator / developer tracking system state and development progress.

Creates: Nothing directly.
Reads: `GET /api/v1/control/kill-events`, `GET /api/v1/admin/journey-validations`, platform-internal roadmap/issues hardcoded in the component.
Updates: Nothing.
Deletes: Nothing.

Key actions:
- View kill/pause event audit log (Events tab)
- View structured development roadmap (phases, subphases, steps with status icons)
- View user journey validation checklists (structured journey test status)
- View known issues list with severity badges
- View feature build progress checklist

Related entities:
- KillSwitchEvent (audit log)
- UserJourneyValidation
- (Roadmap and Issues are hardcoded in-component)

Key API routes:
- `GET /api/v1/control/kill-events`
- `GET /api/v1/admin/journey-validations`

Realtime streams:
- Polls kill events every 30s

Overlaps or conflicts with other pages:
- Kill events also viewable in AccountGovernor's event log — duplication
- The roadmap/issues/feature-build tabs are development artifacts — they should not be visible in a production deployment

Current UX problems:
- The route for this page is `/logs` — but the page contains a roadmap, journey validations, and a known issues tracker in addition to logs — the page name and URL are deeply misleading
- Roadmap data is hardcoded inside the React component — it will become stale immediately and requires a code deploy to update
- Known Issues list is hardcoded — a list of issues inside the UI of the application being audited creates a circular dependency (the tool that has bugs shows its own bugs)
- User Journey Validations come from an admin API endpoint but the format couples to a specific response shape that must be maintained separately
- "Feature Build Progress" tab is a development checklist — it has no place in a production product

Recommended domain grouping: Admin

---

## Backup & Restore

Purpose: Download a full platform backup (all database state as a file) and restore from a backup file. Simple two-action interface.

Primary user: Platform administrator.

Creates: Nothing (backup is a download, not a created entity).
Reads: `GET /api/v1/admin/backup` (triggers file download).
Updates: `POST /api/v1/admin/restore` (destructive — replaces all database state with the uploaded file).
Deletes: Implicitly deletes all existing data when restoring.

Key actions:
- Click "Download Backup" to download current database as a file
- Select a backup file from the filesystem
- Confirm restore (ConfirmationModal-style inline confirm)
- Execute restore

Related entities:
- All database entities (backup is a full dump)

Key API routes:
- `GET /api/v1/admin/backup`
- `POST /api/v1/admin/restore`

Realtime streams:
- None

Overlaps or conflicts with other pages:
- No overlaps — this is the only backup interface

Current UX problems:
- The restore action is irreversible (drops and replaces all data) but the confirmation is a simple inline checkbox pattern — this should require typing a confirmation phrase or at minimum presenting an extremely prominent danger warning
- There is no backup history — the user downloads a single snapshot with no metadata about when it was taken or what schema version it was from
- No automatic scheduled backups — the user must remember to manually download
- The restore result shows `{ status, bytes, message }` but doesn't show a summary of what was restored (how many strategies, runs, accounts, etc.)
- If the restore file is from an incompatible schema version, the error message may be cryptic

Recommended domain grouping: Admin

---

## Modals Acting as Pages

The following modals are significant enough to document:

---

### New Strategy Modal (within Strategies page)

Purpose: AI-powered strategy generation. User enters a natural-language prompt; the backend returns a generated StrategyConfig that is injected into StrategyCreator.

Key actions: Enter natural language prompt → `POST /api/v1/strategies/generate-conditions` → navigate to StrategyCreator with generated state.

Current UX problems:
- No loading indicator while generation is in progress — the modal appears frozen
- If generation fails, error message is generic
- Generated strategy is injected via navigation state — if the user refreshes StrategyCreator, the pre-filled data is lost

---

### Create Account Modal (CreateAccountModal component)

Purpose: Create a new broker account record. Appears on AccountMonitor and CredentialManager.

Key actions: Enter name, mode (paper/live), initial balance, base URL → `POST /api/v1/accounts`.

Current UX problems:
- Modal requires entering a base URL manually — most users don't know the Alpaca base URL and it's prefilled with the paper URL default, which is wrong if creating a live account
- The modal does not offer to fill in credentials after creation — user must navigate to CredentialManager separately

---

### Add Program Modal (within AccountGovernor)

Purpose: Assign a deployable program to an account's governor with a capital allocation.

Key actions: Select program, enter allocated capital USD, select broker mode (paper/live) → `POST /api/v1/governor/{accountId}/allocate`.

Current UX problems:
- Program list only shows programs that pass `isDeployableProgram()` check (all 5 components filled) — but the user may not know why their program doesn't appear
- No link from this modal to the Programs page to complete a partial program

---

### Create Program Modal (within TradingPrograms)

Purpose: Create a new program with name, description, duration mode, and optional initial strategy version.

Key actions: Enter metadata → `POST /api/v1/programs`.

Current UX problems:
- Loads all strategy versions to populate the optional selector — slow with many strategies

---

## PAGE SUMMARY

Total pages: 21 (routed pages) + 4 notable modals = 25 distinct surfaces

Build pages: 9
- Strategies (Library)
- Strategy Creator
- Strategy Details
- Strategy Editor
- Risk Profiles
- Strategy Controls
- Execution Styles
- Watchlist Library
- Trading Programs

Validate pages: 6
- Backtest Launcher
- Run History
- Run Details
- Optimization Lab
- Simulation Lab
- Chart Lab

Operate pages: 6
- Dashboard
- Account Monitor
- Account Governor
- Deployment Manager
- Live Monitor
- Event Calendar

Admin pages: 4
- Credential Manager
- Services
- Logs Panel
- Backup & Restore

---

Top 5 most overlapping/confusing pages:

1. **Account Governor vs Deployment Manager vs Live Monitor** — All three pages show deployment status, paper trade tables, and position-level controls. AccountGovernor and DeploymentManager have duplicated safety checklists (different key names, will diverge), duplicated deployment tables, and duplicated promotion wizards. A user managing live trades must decide which of these three pages to watch. There is no authoritative single "operations center."

2. **Run History vs Optimization Lab (Results tab)** — These are the same page. Both show a sortable, filterable table of backtest runs with identical columns (Sharpe, return, drawdown, SQN, etc.). OptimizationLab adds tabs on top but the core table is duplicated. Every change to the runs list format must be made in two places.

3. **Run Details vs Optimization Lab (Comparison/WalkForward tabs) vs Optimization Lab (Stress tab)** — Run Details has a compare mode, promote-to-paper button, and walk-forward summary. OptimizationLab has a dedicated Comparison tab (same delta metrics), a Walk-Forward tab (same fold summary), and a Stress/Paper→Live tab (same promotion wizard). There are three distinct surfaces for the same post-analysis workflow.

4. **Credential Manager vs Services** — Both store Alpaca API credentials but for different purposes (broker trading auth vs data market data access). The user with one Alpaca account must configure keys in two places and is not warned when they differ. If a key is rotated, it must be updated in both places.

5. **Watchlist Library vs Data Manager (watchlist section)** — Two entirely separate watchlist CRUD systems backed by two different database tables (`watchlists` managed by the watchlists router and `data_watchlists` managed by the data router). Programs reference watchlist IDs from one system; DataManager creates watchlists in a different system. A user creating a watchlist in DataManager cannot use it in a Program, and vice versa, with no error or explanation.
