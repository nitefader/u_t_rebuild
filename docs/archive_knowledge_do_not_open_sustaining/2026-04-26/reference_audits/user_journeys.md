# Complete User Journeys — Ultimate Trading Software 2026
> Audit date: 2026-04-23 · Auditor: senior product designer pass

---

## Journey 1: First-Time Setup

User goal: Get the platform to a usable state — broker connected, data fetching, at least one strategy ready to backtest.

Step-by-step flow:
1. User opens the app and lands on Dashboard. The getting-started checklist is visible but not gated — the user can navigate away at any time without completing any step.
2. The kill switch badge is red (unknown state) or shows a status the user doesn't understand. There is no explanation on Dashboard of what the kill switch is or why it matters.
3. User attempts to follow the checklist. Step 1 is typically "Add Account." They navigate to Credential Manager (URL: `/security`). The URL gives no hint that this is about Alpaca credentials.
4. On Credential Manager, the user must choose paper or live mode first. New users don't know they should start with paper. There is no recommendation or default selection.
5. User enters Alpaca paper API key and secret. They click "Validate" — the button fires `POST /api/v1/accounts/{id}/credentials/validate`. If validation passes, credentials are stored. If validation fails, the error message is a raw API error string from Alpaca, not a user-friendly message.
6. User must then navigate to Services page (`/services`) to configure data providers (Alpaca or yfinance). This page is separate from Credential Manager even though both deal with Alpaca credentials. The user often doesn't know to do this step without external documentation.
7. On Services, the user configures either yfinance (no credentials needed) or Alpaca data feed (requires the same API key they already entered, but in a separate credential field). They may enter keys twice.
8. User may optionally configure an AI service (Gemini or Groq) on the same Services page. This step is often skipped.
9. User navigates to Data Manager (`/data`) to fetch OHLCV data for a symbol. They go through the 5-step wizard: Provider → Symbol → Configure → Review → Done. Without cached data, backtesting and simulation will fail.
10. User navigates to Strategies (`/strategies`) to create their first strategy. They see an empty list and the option to create a new strategy or generate one with AI.
11. At this point, the user has visited 5 different pages (Dashboard, Credential Manager, Services, Data Manager, Strategies) before they can run a single backtest. There is no guided onboarding sequence that enforces or even recommends this order.

Pages involved:
- Dashboard
- Credential Manager (`/security`)
- Services (`/services`)
- Data Manager (`/data`)
- Strategies (`/strategies`)

Entities touched:
- Account (created, credentials added)
- DataService (Alpaca / yfinance config)
- AIService (optional)
- DataFetch / DataInventory

Where users get confused:
- The URL `/security` for Credential Manager is completely unintuitive. Users often bookmark it wrong or can't find it from the sidebar.
- There are two separate credential stores: Credential Manager (broker trading credentials) and Services (data feed credentials). Alpaca keys appear in both. New users enter the same keys twice without understanding why.
- The getting-started checklist on Dashboard does not link directly to the correct pages — it uses labels like "Configure Data Service" without hyperlinks.
- The platform accepts navigation to any page before setup is complete. A user can try to launch a backtest before any data is cached and receive a silent failure or a generic error.
- After entering credentials, there is no confirmation that the account is "ready" or "connected." The account card on Account Monitor shows a connectivity badge, but new users have not found Account Monitor yet.

Where the system is disjointed:
- Credentials for the same Alpaca account are entered in two different places (Credential Manager for order submission, Services for data feed). These are backed by different data models and are not synchronized.
- Account creation can happen on Credential Manager, Account Monitor, or Services — three different entry points for the same action with slightly different forms.
- The getting-started checklist state is not persisted server-side. On a new browser/device, the checklist resets to unchecked, even if all setup steps were completed.

Where duplication exists:
- Alpaca API key entry exists in Credential Manager AND Services.
- Account creation modal is duplicated across three pages.
- "Add data source" wizard in Data Manager and the data feed selector in Services both configure the same underlying data providers.

What should be simplified:
- A single unified onboarding wizard (5–7 steps, forced linear flow) that collects broker credentials, selects data provider, fetches initial data, and ends at Strategies ready to build.
- Merge broker credentials into a single credential store; expose both trading and data credentials from one page.
- Make the Dashboard checklist server-persisted and link each item to the exact page it requires.

---

## Journey 2: Strategy Creation

User goal: Define a new trading strategy from a hypothesis — entry conditions, stop logic, exit logic.

Step-by-step flow:
1. User navigates to Strategies (`/strategies`). They see the strategy library (empty if new, or showing existing strategies).
2. User clicks "New Strategy." This navigates to Strategy Creator (`/strategies/new`), a blank StrategyBuilderShell in create mode.
3. On Strategy Creator, there are four tab sections: Core (name, description, category, hypothesis, tags), Signals (condition builder), Stops (stop configuration), Exits (exit conditions).
4. User fills in Core metadata. The hypothesis field is free text with no character limit or guidance on what makes a good hypothesis.
5. User moves to Signals tab. The ConditionBuilder presents a tree-based condition editor. The user adds indicators (RSI, EMA, MACD, etc.) from a dropdown and configures threshold comparisons or crossover conditions. The UI is powerful but has no inline preview — the user cannot see whether their condition would have fired historically.
6. User adds stop configuration (ATR-based, fixed, or trailing candidates). The stop fields are labeled as "candidates" — the actual stop enforcement is done by the Execution Style, but this label is not explained.
7. User adds exit conditions (opposite signal, time-based). There is no "test this exit" action.
8. User clicks "Save Strategy." This creates a Strategy entity via `POST /api/v1/strategies`, then creates a StrategyVersion via `POST /api/v1/strategies/{id}/versions`.
9. If the user navigated via the AI generation modal (by entering a natural language prompt on the Strategies list page), they land on Strategy Creator pre-populated with AI-generated conditions. If they press Back from Strategy Creator, the pre-populated content is lost.
10. After save, the user is navigated to Strategy Details for the newly created strategy.
11. There is no autosave. Any browser crash or accidental navigation before step 8 loses all work.

Alternative path — AI generation:
1. User clicks "AI Generate Strategy" on Strategies list page.
2. Modal opens inline with a natural language input ("generate a mean reversion strategy using Bollinger Bands and RSI for equities").
3. User submits prompt → `POST /api/v1/strategies/generate-conditions` fires.
4. On success, the modal navigates the user to Strategy Creator pre-populated with the returned condition tree.
5. The user cannot review or edit the generated conditions in the modal before navigating — they land in Strategy Creator mid-flow.

Pages involved:
- Strategies (library and AI modal)
- Strategy Creator

Entities touched:
- Strategy (created)
- StrategyVersion (created)
- StrategyConfig (EntryConfig, StopConfig, ExitsConfig)
- IndicatorSpec

Where users get confused:
- The distinction between Strategy (signal logic) and Strategy Controls (timing, session) is not explained on Strategy Creator. Users try to add session windows, PDT rules, or regime filters here and cannot find where those fields live.
- "Stop candidates" terminology — users think stops are fully configured here. They are not. The Execution Style owns the actual stop order type and bracket configuration.
- The ConditionBuilder has a voice input feature (`useSpeechInput`) that is completely hidden — no button, no label, no documentation.
- After saving, the user lands on Strategy Details. If they want to immediately run a backtest, the path is: Strategy Details → click "Launch Backtest" → Backtest Launcher. This is not immediately obvious.
- Version notes field is at the bottom of the form. Most users don't notice it or skip it. Without notes, the version history becomes unnavigable.

Where the system is disjointed:
- The Strategy component (signal logic only per the architecture) has stop candidate fields that partially overlap with Execution Style's stop configuration. The split is architecturally correct but confusing to users who think of stops as part of the strategy.
- AI generation fires a different API endpoint (`generate-conditions`) than manual creation (`POST /api/v1/strategies`). The resulting condition tree is the same format but the path to get there is structurally different.
- There is no direct path from Strategy Creator → Backtest Launcher after save. The user must navigate via Strategy Details.

Where duplication exists:
- Strategy Creator and Strategy Editor share approximately 90% of their code (both use StrategyBuilderShell). They are the same form with different save targets. This creates two nearly identical pages in navigation.
- The indicator dropdown in ConditionBuilder uses the same indicator kind list as Simulation Lab and Chart Lab — but it is a different UI widget and is styled differently.

What should be simplified:
- Merge Strategy Creator and Strategy Editor into a single route with a mode parameter — the save behavior is the only difference.
- Add an inline "quick test on chart" link from ConditionBuilder that opens Chart Lab pre-loaded with the current indicator set.
- Implement autosave to local storage with a visible "unsaved draft" banner.
- Add prominent inline labels explaining the 6-component architecture split so users understand what belongs on Strategy vs Strategy Controls vs Execution Style.

---

## Journey 3: Strategy Validation (Chart Lab / Simulation Lab)

User goal: Visually validate that a strategy's indicators behave as expected before committing to a full backtest.

Step-by-step flow — Chart Lab path (static inspection):
1. User navigates to Chart Lab (`/chart-lab`).
2. User enters a symbol via TickerSearch, selects a timeframe, and picks a date range.
3. System attempts to load OHLCV data from the cached data inventory (`GET /api/v1/data/inventory`). If data is not cached for that symbol+timeframe+range, Chart Lab shows "No data found" with a link to Data Manager. The user must leave Chart Lab, fetch data, return, and re-enter their parameters.
4. User enables indicators from the grouped indicator panel (Moving Averages, Oscillators, Volatility, Volume). Indicators render on price pane or oscillator pane automatically.
5. There is no strategy selector in Chart Lab. The user cannot load their strategy's indicator set with a single click — they must manually re-add every indicator from memory.
6. Chart Lab shows no entry/exit signals, no trade markers, no equity curve. It is a pure visual inspection tool only.
7. User inspects the chart visually and decides whether the indicator combination looks promising.

Step-by-step flow — Simulation Lab path (real-time validation):
1. User navigates to Simulation Lab (`/simulation-lab`).
2. Setup drawer is expanded by default. User selects a strategy from the dropdown (populated from `GET /api/v1/strategies` with version selector), a symbol, date range, timeframe, and initial capital.
3. User optionally selects a Program (which fills strategy, governor, risk, and execution style from the program's configuration).
4. User selects playback speed (1×, 5×, 25×, 100×, Max).
5. User clicks "Run Simulation." This POSTs to `POST /api/v1/simulations/create`, which creates a simulation record. A WebSocket connection is then established at `/ws/simulation/{id}`.
6. The system plays bars one at a time through the BacktestEngine. Each bar update pushes price data, indicator values, and any signal/trade events over the WebSocket.
7. The user can pause, resume, or skip-forward during playback. The setup drawer auto-collapses after launch.
8. Right sidebar shows three tabs: Metrics (return, Sharpe, drawdown, SQN — updating live), Positions (current open positions), Trade Log (all trades so far).
9. Multi-pane chart updates in real time: price pane (candlesticks + overlays), volume pane, oscillator pane, and an equity strip at the bottom.
10. When simulation completes (or is stopped), results remain on screen. There is no "save simulation results" action — results exist only in memory for the current session.

Pages involved:
- Chart Lab
- Simulation Lab
- Data Manager (prerequisite for data fetching)

Entities touched:
- DataInventory (reads cached OHLCV)
- Strategy / StrategyVersion
- Simulation (created, streamed, not persisted after close)
- Program (optional, reads components)

Where users get confused:
- Chart Lab and Simulation Lab have visually identical indicator catalogues (INDICATOR_GROUPS is copy-pasted) but are completely separate tools with different purposes. Users often start in Chart Lab expecting to see signals, discover it doesn't show signals, then don't know about Simulation Lab.
- In Simulation Lab, selecting a Program vs selecting a Strategy directly produces different behavior: Program mode uses all five components (including risk and execution style) which changes how trades are sized and stopped. Strategy-only mode uses defaults. This distinction is not explained.
- If data is not cached for the symbol+range the user selects in Simulation Lab, the simulation creation fails with a generic error. The user must know to go to Data Manager first.
- Simulation Lab results are in-memory only. After the user navigates away (even to pause for lunch), results are gone. There is no "this run will be lost" warning on navigation.
- The "skip forward" button in Simulation Lab advances by a fixed number of bars but there is no indicator of how many bars are in the full dataset — the user can't gauge progress.

Where the system is disjointed:
- Chart Lab has no concept of a strategy — it is purely a chart viewer. Simulation Lab runs the BacktestEngine. These are two fundamentally different levels of capability in the same "validation" domain, with no bridge between them.
- The indicator catalogue in Chart Lab and Simulation Lab is copy-pasted code, not a shared component. If an indicator is added to one, it must be manually added to the other.
- Simulation Lab can accept a Program as input (which exercises all five components) but its output is not connected to the backtest system. Promising simulation runs cannot be promoted to a full backtest from within Simulation Lab.

Where duplication exists:
- INDICATOR_GROUPS constant is duplicated verbatim between ChartLab.tsx and SimulationLab.tsx.
- The symbol + timeframe + date range selector pattern is duplicated across Chart Lab, Simulation Lab, and Backtest Launcher. Each implements it slightly differently.
- Speed controls exist in Simulation Lab and also in TradeReplayPanel on Run Details — two separate implementations of the same concept.

What should be simplified:
- Add a "Load strategy indicators" button to Chart Lab that reads the current strategy's indicator spec and pre-populates the indicator panel.
- Add a "Promote to full backtest" button in Simulation Lab that pre-fills Backtest Launcher with the current simulation parameters.
- Persist simulation results to a lightweight session store so navigating away and back restores the last run.
- Extract INDICATOR_GROUPS to a shared constant file and import it in both Chart Lab and Simulation Lab.

---

## Journey 4: Backtesting

User goal: Run a historical backtest of a strategy over a date range and symbol list, then analyze the results.

Step-by-step flow:
1. User navigates to Backtest Launcher (`/backtest`). Alternatively, they click "Launch Backtest" from Strategy Details or from TradingPrograms — both pre-fill some parameters.
2. User selects a Program OR manually selects strategy + version. If using Program mode, all five component selections are hidden inside the program card. The user cannot see what risk profile or execution style will be used without going to TradingPrograms.
3. User enters or selects symbols. Can be a manual comma-separated list or sourced from a watchlist. If sourcing from a watchlist, the user must know which watchlist contains the desired symbols — there is no watchlist preview here.
4. User selects data provider (yfinance or Alpaca). User may click "Get Recommendation" to fire `POST /api/v1/backtests/provider-recommendation` for AI advice on provider choice.
5. User sets date range (start and end). There is no warning if the selected date range has gaps in the cached data inventory.
6. User optionally enables walk-forward analysis. If enabled, inputs for fold count and IS/OOS split ratio appear. These are numeric inputs with no guidance on sensible values.
7. User optionally enables CPCV. No tooltip or inline explanation of what CPCV is.
8. User sets initial capital and commission model.
9. User clicks "Launch Backtest." The system fires `POST /api/v1/backtests/launch`. A status overlay appears showing "running" status.
10. The launcher polls `GET /api/v1/backtests/{runId}` every 5 seconds. When status changes from "running" to "completed" or "failed," the overlay updates.
11. On completion, the overlay shows a "View Results" button. There is no automatic redirect. If the user closes the overlay or navigates away, they must find the run in Run History manually.
12. User navigates to Run History (`/backtest/history`), finds their run, and clicks through to Run Details.
13. On Run Details, the user sees overview metrics, equity and drawdown charts, trade journal, monthly returns heatmap, Monte Carlo results, and anti-bias evidence (walk-forward, CPCV).
14. User inspects results, reads trade-by-trade in the Trade Journal. Can expand individual trades to see MAE, MFE, conditions fired, and bar-by-bar replay.
15. User may click "Suggest Risk Profile" which calls `POST /api/v1/backtests/{runId}/suggest-risk-profile`. A risk profile entity is created silently — there is no notification, no navigation to RiskProfiles, and no indication of what was created.
16. User may click "Promote to Paper" which opens the paper promotion wizard. This creates a Deployment entity and navigates (or not — it's unclear) to Account Governor.

Pages involved:
- Backtest Launcher
- Run History
- Run Details
- (TradingPrograms or StrategyDetails — entry points)
- (RiskProfiles — destination of "Suggest Risk Profile")

Entities touched:
- BacktestRun (created, polled)
- RunMetrics (read)
- Trade (read, replayed)
- WalkForwardResult (read)
- MonteCarloResult (read)
- CpcvResult (read)
- RiskProfile (optionally created via suggest)
- Deployment (optionally created via promote)

Where users get confused:
- When using Program mode on Backtest Launcher, the five component IDs are submitted but not shown to the user. If the program has a high-risk profile or a restrictive execution style, the user doesn't know this is affecting results until they dig into Run Details.
- Walk-forward parameters (fold count, IS/OOS ratio) have no defaults explained. A fold count of 3 on a 1-year dataset is very different from 10 on a 5-year dataset. New users use defaults blindly.
- After backtest launches, there is no ETA or progress bar. For large symbol lists or long date ranges, the user stares at "running..." for minutes with no feedback.
- "Suggest Risk Profile" creates an entity silently. Users who don't check Risk Profiles page will never find it. Over time this creates orphaned, unlabeled risk profiles in the system.
- Run Details intermingles analysis tools (equity curve, trade journal) with operational actions (Promote to Paper, Delete). Users in analysis mode accidentally trigger actions.

Where the system is disjointed:
- Backtest Launcher and Optimization Lab's "Param Search" tab both launch backtests via `POST /api/v1/backtests/launch` but are completely separate UIs. Results from both end up in Run History, making it hard to know which runs were from single launches vs optimizer batches.
- Simulation Lab also uses the BacktestEngine but is entirely disconnected from the backtest system. There is no way to convert a simulation session into a formal backtest run.
- The TradeReplayPanel in Run Details runs the engine in replay mode but is a cramped inline panel. This is a significantly degraded version of the full Simulation Lab experience.

Where duplication exists:
- Run History and OptimizationLab's "Results" tab both show the same backtest run list with nearly identical columns and sort controls. Users who only use OptimizationLab may not know Run History exists, and vice versa.
- Dashboard also shows a "recent runs" table — three places show backtest run lists.
- Promote-to-paper wizard on Run Details uses the same LIVE_SAFETY_CHECKS concept as DeploymentManager and AccountGovernor, but with different key names and different check items.

What should be simplified:
- After backtest launch, automatically redirect to a live status page for that run, then auto-redirect to Run Details on completion — eliminate the "find it in Run History" step.
- Add a progress percentage and ETA to the backtest status overlay.
- Make "Suggest Risk Profile" navigable: show a toast with a link to the newly created profile.
- Move the promotion panel off Run Details onto a dedicated step in the Programs workflow or onto Account Governor only — not on the analysis page.

---

## Journey 5: Optimization

User goal: Find the best parameters for a strategy by running many backtests systematically, then analyze results to pick the most robust configuration.

Step-by-step flow:
1. User navigates to Optimization Lab (`/optimization`). The page opens to the "Results" tab showing all prior backtest runs.
2. To launch a new optimization, the user clicks the "Param Search" tab (tab 6 of 6).
3. On Param Search tab, user selects a strategy, specifies a parameter grid (which parameters to vary, min/max/step for each), selects symbols, date range, and provider.
4. User clicks "Run Optimization" which fires `POST /api/v1/backtests/optimize`. This creates a batch of backtest runs.
5. The user cannot monitor progress in Optimization Lab — they must go to Run History to see individual runs completing. There is no batch progress indicator in Optimization Lab.
6. When runs complete, user returns to "Results" tab. The results table now includes the optimization batch runs. User sorts by Sharpe, SQN, return, or drawdown to find promising configurations.
7. User selects two runs in the Results table and clicks "Compare" to open the Comparison tab (tab 3). Side-by-side delta metrics are shown.
8. User examines the Walk-Forward tab (tab 2) for fold waterfall charts showing IS vs OOS performance across each fold.
9. User checks the Independence tab (tab 4) for signal overlap analysis — whether two strategies from the same run have correlated signals.
10. User goes to Stress tab (tab 5) which shows a paper-to-live monitor and a promotion pathway. This is the third promotion surface in the system.
11. User promotes the best-performing, most robust run to paper via the Stress tab or navigates to Run Details and uses the promotion panel there.
12. There is no "save optimization session" concept. The parameter grid the user entered in Param Search is lost after leaving the page.

Pages involved:
- Optimization Lab (all 6 tabs)
- Run History (to monitor individual run progress)
- Run Details (alternative analysis and promotion path)
- Backtest Launcher (alternative launch path for individual runs within the optimization session)

Entities touched:
- BacktestRun (many created)
- RunMetrics (read across many runs)
- WalkForwardResult (read per fold)
- MonteCarloResult (read)
- Deployment (created via Stress tab promotion)

Where users get confused:
- Optimization Lab's Results tab is visually identical to Run History. Users don't understand why there are two places showing the same table.
- There is no "this is an optimization batch" concept in the UI. All individual optimization runs appear in the same global run history alongside single-run backtests. After running 50 optimization variants, the run history is polluted.
- Walk-Forward analysis is configured on the Backtest Launcher when launching individual runs, and also available as an Optimization Lab tab — the connection between them is not clear. Users run walk-forward once in the launcher and expect to see the results in the Walk-Forward tab, but the tab shows a different visualization.
- Param Search only supports grid search. There is no Bayesian or random search option. For large parameter spaces, grid search becomes computationally impractical, but there is no warning.
- The Stress tab contains a paper→live monitor with different UI elements than AccountGovernor's promotion wizard. Users who have been through promotion once on AccountGovernor are confused to find a different UI for the same action here.

Where the system is disjointed:
- Optimization batch launch (Param Search tab) and single run launch (Backtest Launcher) are separate pages with different UIs but submit to the same backend endpoint.
- Progress monitoring for optimization batches must be done on Run History, not within Optimization Lab. The user has to context-switch pages.
- The Stress tab's paper→live promotion wizard is a third independent copy of the promotion flow. The key names in the safety checklist differ from AccountGovernor and DeploymentManager.
- Independence tab (signal overlap analysis) and Run Details' regime analysis tab serve overlapping purposes from different data perspectives.

Where duplication exists:
- Results tab is a duplicate of Run History.
- Promotion wizard is duplicated three times: Run Details, AccountGovernor, Optimization Lab Stress tab — all with slightly different safety check lists.
- Comparison tab in Optimization Lab duplicates the compare functionality accessible from Run History by selecting two runs.

What should be simplified:
- Tag optimization batch runs with a batch_id and give them a grouped view separate from single-run backtests in the history.
- Add a progress indicator in Optimization Lab showing how many runs in the current batch have completed.
- Consolidate promotion to a single location (Account Governor only). Remove promotion panels from Run Details and Optimization Lab.
- Save the Param Search configuration to a session so the user can return and adjust parameters without re-entering everything.

---

## Journey 6: Program Creation

User goal: Assemble all five components (Strategy, Controls, Risk Profile, Execution Style, Watchlist) into a deployable Program.

Step-by-step flow:
1. User navigates to Trading Programs (`/programs`). They see a list of existing programs or an empty state.
2. User clicks "New Program." A CreateProgramModal opens asking for program name and description only. Clicking confirm creates an empty Program entity via `POST /api/v1/programs`.
3. User is taken to (or stays on) the Programs page with the new program now in the list. They click on it to open ProgramDetail, which shows five GuidedCard sections in a vertical stack: Strategy, Strategy Controls, Risk Profile, Execution Style, Watchlist.
4. Each GuidedCard has a selector dropdown and a "Create or Manage [Component]" link. The dropdown shows all available entities of that type.
5. For Strategy card: user selects a strategy. A second version dropdown appears. User selects the version. The strategy selector fires `GET /api/v1/strategies` and versions come from the strategy's versions list. The card shows a brief summary.
6. For Strategy Controls card: user selects an existing controls template. If none exist, they must navigate away to Strategy Controls (`/strategy-controls`), create one, then come back and re-open the program. State is preserved in the URL.
7. Same flow for Risk Profile: if none exists, navigate to Risk Profiles (`/risk-profiles`), create one, return.
8. Same flow for Execution Style: navigate to Execution Styles (`/execution-styles`) if needed, create, return.
9. For Watchlist card: user selects from watchlists. **Critical issue**: this page's watchlist dropdown is populated from the `GET /api/v1/watchlists` endpoint (the WatchlistLibrary system). Data Manager's watchlists use `GET /api/v1/data/watchlists` — a completely different database table. Symbols downloaded through Data Manager's watchlist tool will NOT appear here unless they were added through WatchlistLibrary specifically.
10. ProgramProgressBar at the top updates from 0/5 to 5/5 as each card is filled.
11. Once all five cards are filled (5/5), the sticky footer "Save & Validate" button becomes available. User clicks it to fire `POST /api/v1/programs/{id}/validate`.
12. ValidationPanel slides in showing validation results: component compatibility checks, config warnings, and an overall pass/fail.
13. If validation passes, the program status changes to a deployable state. User can then click "Launch Backtest" or navigate to Account Governor to deploy.
14. If validation fails, errors are shown per component with links to fix them. The user must navigate to the relevant component page, fix the issue, return, and re-validate.

Pages involved:
- Trading Programs (list and detail)
- Strategy Controls (`/strategy-controls`) — often required mid-flow
- Risk Profiles (`/risk-profiles`) — often required mid-flow
- Execution Styles (`/execution-styles`) — often required mid-flow
- Watchlist Library (`/watchlists`) — if watchlist doesn't exist
- Data Manager (`/data`) — source of confusion for watchlist mismatch

Entities touched:
- TradingProgram (created, updated)
- Strategy / StrategyVersion (read)
- StrategyGovernor (read)
- RiskProfile (read)
- ExecutionStyle (read)
- Watchlist (read — from WatchlistLibrary system only)
- ProgramValidation (created via validate)
- AccountAllocation (optionally created)

Where users get confused:
- The five-card composition model is the right UX concept but users don't understand the architectural reasons for splitting the components. They think "why do I need 5 separate things to define a strategy?" The in-card descriptions are short and don't explain the rationale.
- The most common confusion: a user creates a watchlist in Data Manager and expects it to appear in the Watchlist card on TradingPrograms. It does not. These are two completely different watchlist systems pointing to different database tables.
- Users must leave TradingPrograms mid-flow to create missing components. There is no inline component creation. After navigating away and back, the program selection is often preserved via URL params, but users don't trust this and re-open the program from scratch.
- The "Strategy Controls" label in the program is derived from a component called "StrategyGovernor" in the backend. Users see "Strategy Controls" in the program, "Strategy Governor" in the code, and "Controls" in some API routes — three names for the same concept.
- ProgramProgressBar shows completion as a fraction (2/5) but does not indicate which cards are empty when the user first opens a program — the user must scroll down to find which cards need filling.
- Validation errors reference component names in technical terms that don't match what the user sees in the UI labels.

Where the system is disjointed:
- Two watchlist systems (WatchlistLibrary and DataManager) with no merge, no sync, and no warning that they are different.
- Component creation flows are entirely separate pages — TradingPrograms is an assembly page only, with no ability to create components inline.
- After Program validation passes, there is no one-click path to deploy. The user must navigate to Account Governor, find the program, and allocate it to an account. This multi-hop is not documented in the UI.
- The "Launch Backtest" button on TradingPrograms detail pre-fills the Backtest Launcher with the program, but the Backtest Launcher hides the component details under the program card — the user loses visibility of what they configured.

Where duplication exists:
- Strategy selection with version dropdown is duplicated on TradingPrograms, Backtest Launcher, and Simulation Lab — three separate implementations of the same "pick a strategy version" control.
- Validation logic exists both as a backend endpoint (`POST /api/v1/programs/{id}/validate`) and as inline field-level hinting in the ConditionBuilder — these can produce conflicting signals.

What should be simplified:
- Resolve the two-watchlist-system inconsistency. Either merge them or display a clear bridge ("Create in Data Manager" watchlists appear under a "Data Manager Watchlists" section in the Program builder).
- Add inline component quick-creation without leaving the page (modal-based create for each component type).
- Make ProgramProgressBar highlight incomplete cards rather than just showing a count.
- Standardize the naming: pick "Strategy Controls" or "Strategy Governor" and use it everywhere.

---

## Journey 7: Deployment (Paper and Live)

User goal: Deploy a validated program to paper trading, monitor it, then promote it to live trading when confident.

Step-by-step flow — Deploy to Paper:
1. User has a validated program (5/5 components, validation passed, backtest results reviewed).
2. There are three paths to deploy to paper:
   - Path A: From Run Details, the user clicks "Promote to Paper" in the promotion panel at the bottom of the page. This opens a safety checklist wizard. After completing the checklist, `POST /api/v1/deployments/promote-to-paper` is called.
   - Path B: From Account Governor (`/governor`), the user opens "Add Program" modal on a paper account's governor. The program is allocated and a deployment is created.
   - Path C: From TradingPrograms, the user clicks the "Start" button in the Allocations section. This creates a deployment directly.
3. All three paths create a Deployment entity, but the parameters passed differ: Path A attaches backtest run context; Path B goes through the governor's allocation flow; Path C goes through a simpler start endpoint.
4. After paper deployment is created, it appears in the deployment table on Account Governor. The user must navigate there to see it — Paths A and C don't auto-redirect to Account Governor.
5. User verifies the deployment is active on Account Governor: governor status should be "active," deployment status should be "running."
6. The governor must have been bootstrapped (`POST /api/v1/governor/{accountId}/bootstrap`) before any deployment can run under it. If the governor was never bootstrapped, the deployment is created but immediately blocked. There is no UI warning that the governor is uninitiated — the user sees a deployment that appears to exist but never trades.

Step-by-step flow — Monitor and Promote to Live:
1. After a paper deployment has been running (recommended minimum: 30 days per the LIVE_SAFETY_CHECKS checklist), user is ready to promote to live.
2. Again, three promotion surfaces exist for paper→live:
   - Run Details (paper run tab)
   - Account Governor (promote button on deployment row)
   - DeploymentManager (promote wizard — duplicate)
3. User chooses one of these surfaces (likely Account Governor as it's the most operational page).
4. On Account Governor, user clicks "Promote to Live" on the paper deployment row. A full-screen modal opens with the LIVE_SAFETY_CHECKS wizard.
5. The checklist includes: paper performance reviewed (30 days), risk limits confirmed, live account verified and funded, broker connection tested, compliance acknowledged, market conditions assessed. User must manually check all items.
6. After all items are checked, the "Promote to Live" button becomes active. User clicks it → `POST /api/v1/deployments/promote-to-live` fires.
7. Optionally, user can click "Get AI Advice" before promoting → `POST /api/v1/ml/promote-advice` returns a qualitative assessment.
8. The live deployment is created. It appears in the deployment table alongside the paper deployment. There is no automatic pause or archive of the paper deployment after live promotion — both run simultaneously by default.
9. The live governor must also be bootstrapped for the live account. If the user promoted to a live account that has never had its governor bootstrapped, the same silent-blocking problem occurs as in paper.

Pages involved:
- Run Details (paper promotion)
- Account Governor (paper deployment creation, paper→live promotion)
- TradingPrograms (alternative deployment start)
- DeploymentManager (duplicate promotion surface)
- Account Monitor (prerequisite: governor must be bootstrapped)

Entities touched:
- Deployment (created: paper, then live)
- DeploymentTradeRow (created at trade time)
- PortfolioGovernor (must be bootstrapped)
- AccountAllocation
- Account

Where users get confused:
- Three separate paper deployment paths with different parameters. A user who deploys from Run Details gets a deployment with a backtest_run_id attached; one who deploys from TradingPrograms gets a deployment without that context. Reports and audit trails differ depending on which path was used.
- The governor bootstrap step is undocumented in the UI. If a user creates a deployment without a bootstrapped governor, the deployment exists in the database but never executes. The deployment status shows as "created" or "pending," not "blocked by governor."
- The "Promote to Live" button is styled `btn-danger` (red styling) on Account Governor even though the intent is an affirmative action (launch live trading). Red signals danger/stop in UI conventions but here it means "go."
- After live promotion, both paper and live deployments are running simultaneously. The user may not realize this and end up with double-position exposure (paper + live) in the same symbols.
- LIVE_SAFETY_CHECKS checklist items are purely advisory (the user self-attests). The system does not validate whether 30 days of paper data actually exists, whether the live account is actually funded, or whether the broker connection is actually active.

Where the system is disjointed:
- Three promotion paths exist because the promotion feature was implemented incrementally on different pages as the system grew. There is no single canonical deployment workflow.
- Account Governor is the page that owns deployments operationally, but the paper deployment is most naturally created from Run Details (where the user just finished analyzing results). These two pages are at opposite ends of the workflow.
- After deployment, the user's operational home is split across Account Governor (halt/resume/stop controls), DeploymentManager (position-level actions), and LiveMonitor (real-time data).

Where duplication exists:
- LIVE_SAFETY_CHECKS array is copy-pasted in AccountGovernor.tsx and DeploymentManager.tsx with different key names. These will diverge.
- Paper-to-live promotion modal is implemented three times across three separate page files.
- Deployment table (with start/stop controls) is duplicated on Account Governor and Account Monitor.

What should be simplified:
- Consolidate deployment creation to a single flow: from the Program detail page, one "Deploy to Paper" button that routes through Account Governor automatically.
- Consolidate promotion to a single surface: Account Governor only.
- Enforce governor bootstrap as a prerequisite before any deployment can be created — block deployment creation and show a clear error linking to the bootstrap action.
- After live promotion, auto-pause the paper deployment and prompt the user to confirm whether to keep it running or archive it.
- Change the "Promote to Live" button to positive/action styling (green or primary blue), not danger red.

---

## Journey 8: Live Monitoring

User goal: Watch active deployments in real time — see positions, P&L, orders, and equity movement as trading happens.

Step-by-step flow:
1. User navigates to Live Monitor (`/live-monitor`). The page shows one tab per active deployment. If there are no active deployments, the page shows an empty state.
2. Each deployment tab shows: current open positions (symbol, side, quantity, unrealized P&L), recent orders (status, fill price, order type), equity chart (live updating), time since last WebSocket event.
3. Live Monitor connects to the WebSocket at `/ws` with polling fallback. The "age of last WebSocket event" indicator tells the user whether the connection is fresh or stale.
4. User watches a position go against them. They want to close it. The "Close" button on each position row fires a close-position action. A "Close All" button closes all positions for that deployment.
5. User wants to adjust the stop on a position. There is no stop management on Live Monitor. They must navigate to Deployment Manager, find the position, open the PositionActionsPanel, enter the Alpaca stop order ID manually, and update the stop there.
6. User sees an unexpected fill or order. They want to understand which program caused it. Live Monitor shows orders by deployment but does not show the condition logic that triggered the trade.
7. User wants to see the governor's event log (e.g., was a trade suppressed due to a symbol collision?). Live Monitor does not show governor events. User must navigate to Account Governor and expand the events panel.
8. User wants to halt all trading immediately. There is no kill switch on Live Monitor. They must navigate to Account Governor to trigger a global kill or per-governor halt.

Pages involved:
- Live Monitor
- Account Governor (for halt/events)
- Deployment Manager (for position adjustments)

Entities touched:
- Deployment (read)
- DeploymentTradeRow (read)
- Account (read via positions/orders from broker)
- PortfolioGovernor / GovernorEvent (read, on Account Governor)

Where users get confused:
- Live Monitor, Account Governor, Account Monitor, and Deployment Manager all show live broker data (positions, orders) in different views. The user cannot determine which page is "the right one" to watch during trading hours.
- On Live Monitor, the "age of last WebSocket event" indicator is a raw timestamp. Users don't know what staleness threshold should concern them — there is no yellow/red alert for stale connections.
- Close position from Live Monitor sends an order directly. For paper deployments, this fires through the paper broker. For live deployments, this fires a live order. There is no paper/live mode indicator on the close button itself.
- After clicking "Close All," there is no confirmation modal. The action fires immediately. For live accounts, this is a high-risk UX pattern.
- Users who want to know why a trade happened (what signal fired) cannot get that information from Live Monitor. The page shows outcomes (positions, orders) but not causes (signals, conditions).

Where the system is disjointed:
- Live Monitor is read-optimized (watching) but action capabilities are minimal (only close position/all). All meaningful actions are on other pages. During a fast market move, the user must navigate across pages to take action — an unacceptable latency risk.
- Governor events (collision_suppressed, risk_blocked, daily_loss_lockout) are only visible on Account Governor. If the system suppressed a trade, the user watching Live Monitor would see no activity and not know why.
- WebSocket connection status is shown per-deployment on Live Monitor but there is no global connection health indicator in the app header.

Where duplication exists:
- Position list with P&L display is on Live Monitor, Account Monitor (broker status cards), Account Governor (deployment trades panel), and Deployment Manager (trade table) — four separate renderings of the same broker position data.
- "Close position" action is on Live Monitor and Deployment Manager.

What should be simplified:
- Make Live Monitor the single operational hub: add governor event feed, halt controls, and stop management directly on the page. Eliminate the need to navigate to three other pages during active monitoring.
- Add a global WebSocket health indicator in the app header.
- Add a mode indicator (PAPER/LIVE) as a persistent label on every position row and on the close button.
- Add a confirmation modal before "Close All" for live deployments.

---

## Journey 9: Risk/Governor Intervention (Pause, Kill, Flatten)

User goal: Halt trading immediately — either for one program, one account, or all accounts simultaneously — often in response to a fast-moving market event.

Step-by-step flow — Global Kill (all programs, all accounts):
1. User spots a problem. They need to stop all trading immediately.
2. The global kill strip is on Account Governor (`/governor`). There is also a kill switch badge in the app header (Dashboard-linked badge), but the badge is READ-ONLY on Dashboard — clicking it does not trigger a kill.
3. User navigates to Account Governor. The GlobalKillStrip is at the top of the page.
4. User clicks "Kill All Trading." A confirmation appears (inline, not a modal — easy to miss). User confirms.
5. `POST /api/v1/control/kill-all` fires. All deployments are paused. The global kill status badge updates.
6. To resume after the kill: user must click "Resume All Trading" on the same GlobalKillStrip. `POST /api/v1/control/resume-all` fires.
7. Individual deployments that were paused before the kill remain paused after resume — only deployments that were running when kill was triggered are resumed. This behavior is not documented in the UI.

Step-by-step flow — Account-Level Halt (one account, all programs on it):
1. User needs to halt a specific account (e.g., paper account overdrawn, live account near daily loss limit).
2. Three pages offer account-level halt:
   - Account Monitor (`/accounts`): "Halt" button per account card.
   - Account Governor (`/governor`): GovernorPanel "Halt Governor" button per account.
   - These are different backend calls: Account Monitor calls `POST /api/v1/accounts/{id}/halt`; Account Governor calls `POST /api/v1/governor/{accountId}/halt`. These may have different effects on deployments.
3. User clicks halt on one of these surfaces. The account's governor status changes to "halted."
4. To resume: "Resume" button on the same page. Account Monitor calls `POST /api/v1/accounts/{id}/resume`; Account Governor calls `POST /api/v1/governor/{accountId}/resume`.

Step-by-step flow — Per-Deployment Pause:
1. User needs to pause one program without affecting others.
2. From Account Governor: deployment row has Start / Pause / Stop buttons. Pause calls `POST /api/v1/control/pause-deployment/{id}`.
3. From Deployment Manager: same deployment table, same actions duplicated.
4. Pause suspends signal evaluation. The deployment is still "active" but won't enter new positions.
5. Resume: Resume button on same row. `POST /api/v1/control/resume-deployment/{id}`.
6. There is no audit trail of who paused a deployment or when — the governor event log captures halt events but not individual deployment pauses.

Step-by-step flow — Flatten (close all positions for an account):
1. User wants to exit all open positions for an account, not just pause.
2. From Account Monitor: "Flatten" button per account card calls `POST /api/v1/accounts/{id}/flatten`.
3. For paper accounts, this route calls through the paper broker. For live accounts, this calls Alpaca's close-all-positions API.
4. The confirmation dialog for flatten uses `window.confirm()` — a browser-native confirm box that is visually inconsistent with the rest of the UI.
5. There is no "flatten one program" action — flatten is account-wide only.

Pages involved:
- Account Governor (global kill, per-account halt, per-deployment pause)
- Account Monitor (per-account halt, flatten, emergency exit)
- Dashboard (kill status badge — read-only only)
- Live Monitor (close position — not a halt, not a flatten)
- Deployment Manager (per-deployment pause — duplicate)

Entities touched:
- KillSwitchEvent (created)
- PortfolioGovernor (state change: halted/active)
- Deployment (state change: paused/running/stopped)
- DeploymentTradeRow (may be closed by flatten)

Where users get confused:
- There are three levels of halt (global kill, account halt, deployment pause) spread across three different pages, with no single unified "stop trading" interface. Under stress, users don't know which control to use.
- The kill switch badge on Dashboard and the header is READ-ONLY. In a crisis, clicking the badge does nothing. Users expect it to be actionable.
- Account Monitor's "Halt" and Account Governor's "Halt Governor" call different endpoints. The relationship between them is unclear. Do both need to be called? Does one supersede the other?
- "Flatten" uses `window.confirm()` while "Emergency Exit" (halt + flatten atomically) also uses `window.confirm()`. These are the most critical operations in the system and they use the least robust confirmation pattern.
- After a global kill, individual deployments that were already paused are NOT resumed by "Resume All." This creates a state management problem: the user must manually track which deployments were paused before the kill.

Where the system is disjointed:
- Three separate halt APIs (`/api/v1/control/kill-all`, `/api/v1/accounts/{id}/halt`, `/api/v1/governor/{accountId}/halt`) with different scopes, different state effects, and different resume paths — none of which is clearly documented in the UI.
- The flatten action is on Account Monitor but is most naturally needed during a monitoring session on Live Monitor. The user must context-switch pages during a time-critical action.
- Governor event log captures some halt events but not all control-level events. There is no single audit log of all halt/kill/flatten actions across the system.

Where duplication exists:
- Deployment pause/resume controls are on Account Governor and Deployment Manager — two tables, two sets of buttons, one backend.
- Account halt is accessible from Account Monitor and Account Governor with different API calls.

What should be simplified:
- A persistent emergency control bar: visible on all pages, shows current kill/halt state for all accounts, and provides one-click global kill from anywhere in the app.
- Unify the halt hierarchy: Global Kill → Account Halt → Deployment Pause — show all three levels on one page with clear visual nesting.
- Replace `window.confirm()` with a styled ConfirmationModal for flatten and emergency exit — these are the most destructive operations and deserve the best UX treatment.
- Add an immutable audit log page: every kill, halt, flatten, and resume event, who triggered it, what state the system was in, and what state it moved to.

---

## Journey 10: Iteration Loop (Refine Strategy)

User goal: Take a strategy that has a backtest result, identify its weaknesses, modify it, and run a new backtest to compare.

Step-by-step flow:
1. User reviews Run Details for their current strategy version. They identify a weakness: for example, the strategy has too many trades in choppy markets (low win rate in range-bound conditions).
2. User decides the fix might be: (A) tighten the entry conditions in the strategy, (B) add a regime filter in Strategy Controls, or (C) adjust stop distance in Execution Style. The system does not guide this decision — the user must know which component owns each concern.
3. Path A — Tighten entry conditions:
   a. User navigates to Strategies list, finds their strategy, clicks through to Strategy Details.
   b. User clicks "New Version" which navigates to Strategy Editor in new_version mode.
   c. User modifies the entry conditions in ConditionBuilder — e.g., adds an RSI threshold to filter out low-momentum entries.
   d. User enters version notes (often skipped), saves. New StrategyVersion is created.
   e. User navigates back to Backtest Launcher (4 navigations: Strategy Details → Backtest Launcher → fill parameters again → launch).
   f. Results appear in Run History. User navigates there, finds both runs, selects them both, clicks Compare, navigates to Run Details compare mode.
   g. Side-by-side comparison shows delta metrics. If the new version is better, user proceeds. If not, user repeats from step 3a.
4. Path B — Add regime filter:
   a. User navigates to Strategy Controls, finds or creates the controls template used by their program.
   b. Enables regime filter checkboxes for allowed regimes.
   c. Saves the updated controls.
   d. **Problem**: the Program still references the old controls by ID — or the same ID, and the controls entity was updated in place. If updated in place, the previous backtest results (which were run with the old controls) are now historically inaccurate because the controls they reference have been mutated.
5. Path C — Adjust stop distance:
   a. User navigates to Execution Styles, finds or creates the execution style used by their program.
   b. Adjusts stop distance multiplier or bracket configuration.
   c. Same in-place mutation problem as Path B: historical backtest results remain linked to this execution style ID, but the execution style config has changed.
6. After any change, the user must re-run the backtest. There is no "re-run with same parameters" button on Run Details or Run History — the user must go back to Backtest Launcher and re-enter the date range, symbols, and settings.
7. The compare flow requires finding both runs in Run History, selecting both, and navigating to compare mode. With many runs in history, finding the right two runs is non-trivial.
8. If the iteration improves the strategy, the user may want to update their Program to point to the new strategy version. They navigate to TradingPrograms, open the program detail, change the version selector. This requires another validation pass.

Pages involved:
- Run Details (identify weakness)
- Strategies / Strategy Details / Strategy Editor (modify strategy)
- Strategy Controls (modify controls)
- Execution Styles (modify execution style)
- Backtest Launcher (re-run)
- Run History (find the new run)
- Run Details compare mode (compare old vs new)
- Trading Programs (update program to new version)

Entities touched:
- StrategyVersion (new version created or existing version mutated)
- StrategyGovernor (potentially mutated in place — historical integrity risk)
- ExecutionStyle (potentially mutated in place — historical integrity risk)
- BacktestRun (new run created)
- TradingProgram (version reference updated)

Where users get confused:
- The biggest confusion: there is no "re-run" button. Every backtest iteration requires going back to Backtest Launcher and re-entering all parameters from scratch.
- For Strategy modification, a new version is created (good — immutable history). But for Controls and Execution Style modification, the entity is updated in place. Users don't realize this means historical backtest results are now linked to a configuration that no longer matches what was tested.
- After creating a new strategy version, the Program still points to the old version. The user must remember to update the program. There is no notification or prompt.
- The compare flow requires navigating Run History, manually identifying the two runs by name/date, selecting them, and then triggering compare. With many runs, this is error-prone — users frequently compare wrong runs.
- Iteration cycles are not tracked. After 5–10 iterations, the user has no clear record of what changed between versions, what was tried, what was abandoned, and why. Version notes are the only mechanism and they are rarely filled in.

Where the system is disjointed:
- Strategy uses immutable versioning (each edit creates a new StrategyVersion). Controls and Execution Style use mutable entities (edit in place). The inconsistency means iterating on a Strategy produces clean audit trails while iterating on Controls or Execution Style silently corrupts history.
- Backtest Launcher pre-fills from a Program but the Program's strategy_version_id may be stale if the user just created a new version. The launcher does not warn that the program's version is not the latest.
- After any component change, the Program's validation status is not automatically cleared. A program that was validated with old components will still show as "validated" even if a component was modified after validation.

Where duplication exists:
- Each iteration requires repeating the full Backtest Launcher form — symbol list, date range, provider, walk-forward settings — even when nothing changed except the strategy version. There is no "re-run last" shortcut.
- Run Details compare is only accessible via Run History (selecting two runs). A "compare with previous version" button on Run Details itself would eliminate a full navigation detour.
- Strategy version selection is repeated on Backtest Launcher even when the user just created the new version on Strategy Editor — the new version should be pre-selected by default.

What should be simplified:
- Add a "Re-run with same parameters" button on Run Details that pre-fills Backtest Launcher with the exact same settings, pointing to the latest version of the same strategy.
- Enforce immutable versioning on Controls and Execution Style — edits should create new versions, not mutate in place. (Or: treat mutation as a new "effective date" and link historical backtests to the configuration snapshot at the time of the run.)
- When a new StrategyVersion is created, prompt the user: "This version is not yet used by any Program. Update your Program to use it?" with a direct link.
- Add a "Compare with run" button directly on Run Details that opens a run picker, eliminating the detour through Run History.
- Display the Program's component versions as a snapshot on each BacktestRun record — show exactly what config was tested, frozen at launch time.

---

## JOURNEY BREAKPOINTS

Top 10 places where users will get lost or make mistakes:

1. **First-time setup: two Alpaca credential stores**
   Users enter Alpaca keys in Credential Manager for order submission and must enter them again in Services for data feeds. Most users discover this only when data fetching fails silently. The system has no indication that two separate stores exist. Estimated impact: every new user hits this on first setup.

2. **Two watchlist systems that don't communicate**
   Data Manager (`/api/v1/data/watchlists`) and Watchlist Library (`/api/v1/watchlists`) are different tables. Symbols fetched through Data Manager's watchlist do not appear in the TradingPrograms watchlist selector. Users build a full watchlist in Data Manager, then find an empty selector in Programs. This is the most common first-deployment failure mode.

3. **Governor bootstrap is required but invisible**
   A Deployment can be created and will appear in the UI as "running" even if the account's PortfolioGovernor was never bootstrapped via `POST /api/v1/governor/{accountId}/bootstrap`. In this state, the deployment never executes any orders. There is no warning in the UI. Users wait for trades that will never come.

4. **Kill switch badge is read-only on Dashboard and the app header**
   The kill switch badge is the most prominent control indicator in the platform. Users click it expecting to trigger a kill. It does nothing — it is display-only. The actual kill control is buried inside Account Governor. During an emergency, navigating to Account Governor is a 3–5 second delay that matters.

5. **Controls and Execution Style are mutated in place — history is corrupted silently**
   When a user edits a Strategy Controls or Execution Style entity, all historical backtest runs that referenced that entity now reflect the new (changed) configuration, not the configuration used at test time. There is no versioning for these entity types. Users who iterate on controls and re-analyze old backtests are comparing apples to oranges without knowing it.

6. **No "re-run last backtest" shortcut — full form re-entry every iteration**
   Every backtesting iteration requires navigating to Backtest Launcher and re-entering the full form: symbols, date range, provider, walk-forward settings. For quants running 10+ iterations per day, this is the single biggest friction point in the entire workflow.

7. **Three promotion surfaces with diverging safety checklists**
   Paper-to-live promotion exists on Run Details, Account Governor, and Optimization Lab (Stress tab). The LIVE_SAFETY_CHECKS arrays in AccountGovernor.tsx and DeploymentManager.tsx have different key names and will diverge over time. A user who has completed the checklist on one surface and then tries another will see a different checklist with different items — eroding trust in the safety process.

8. **After live promotion, paper deployment keeps running alongside live**
   When a paper deployment is promoted to live, both deployments run simultaneously. The paper deployment is not automatically paused or archived. If both programs are watching the same symbols, the user has double-exposure: real money trades from the live deployment and simulated trades from the paper deployment that may interfere with position tracking in the Account Governor.

9. **Strategy version created but Program not updated automatically**
   When a user creates a new strategy version (the correct way to iterate on a strategy), the TradingProgram still references the old version. The user must manually navigate to TradingPrograms, update the version selector, and re-validate. There is no notification, no prompt, and no warning that the Program is now using a stale version. Users often backtest with the new version but deploy the old one.

10. **Compare mode requires finding two runs in Run History — no direct compare from Run Details**
    To compare two backtest runs, the user must: go to Run History, locate both runs (often searching through many results), check both checkboxes, click Compare. There is no "compare this run with the previous version of the same strategy" shortcut from Run Details. After 10+ iterations, locating the right two runs becomes genuinely difficult, especially since run names default to strategy name + timestamp with no version label.
