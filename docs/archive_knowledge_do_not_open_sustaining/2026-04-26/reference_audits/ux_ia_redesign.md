# Information Architecture & UX Redesign — Ultimate Trading Software 2026
> Audit date: 2026-04-23 · Auditor: senior UX architect, complex financial systems

---

## 1. CURRENT UX PROBLEM ANALYSIS

### Navigation Structure

The current sidebar has **six named groups** plus an unlabeled root item:

```
(none)        Dashboard
Build         Strategies, Watchlists, Risk Profiles, Strategy Controls, Execution Styles
Test &        Sim Lab, Backtest, Run History, Chart Lab
  Validate
Optimize      Optim. Lab
Deploy &      Programs, Deployments, Live Monitor, Portfolio Governor, Broker Accounts
  Monitor
System        Services, Credentials, Data, Events, Backup, Logs
```

Total navigation items: **27** items across 6 groups. This is the first problem. A user who opens the app for the first time sees 27 navigation destinations before they have done anything. There is no hierarchy, no sequencing, and no pruning based on context.

**Structural problems in the current grouping:**

1. **"Test & Validate" and "Optimize" are one logical domain split across two groups.** Chart Lab, Sim Lab, Backtest, Run History, and Optim. Lab are all part of the same user intent (validate and refine a strategy before deploying it). Splitting them with a group break and giving Optim. Lab its own group creates a false separation. Users learn "Chart Lab is in Test & Validate but Optimization is in a different group" — which does not match any mental model.

2. **"Deploy & Monitor" contains five items that serve three different intents.** Programs belongs to Build (you compose a program before deploying it). Portfolio Governor belongs to Intervene/Operate. Broker Accounts belongs to Admin. They are grouped together only because they are all vaguely deployment-adjacent.

3. **"System" is a catch-all for admin concerns, but contains items of wildly different urgency.** Services (operational prerequisite) is grouped with Backup (rarely-used admin function) and Logs (developer/debug tool). The word "System" is meaningless to an end user.

4. **"Optimize" group contains one item.** A navigation group with a single item is a UI smell — it means the item didn't fit anywhere else. Optim. Lab should be in the Validate domain.

5. **Portfolio Governor is listed after Live Monitor in the "Deploy & Monitor" group.** In operational priority, the Portfolio Governor is the root control surface. It should appear before deployment details, not after.

6. **"Deployments" (link to AccountGovernorPage) appears in the sidebar as "Deployments" but the actual page is the Account Governor.** Three sidebar items route to the same page: `/deployments`, `/portfolio-governors`, `/governor`. Only `/deployments` appears in the sidebar as "Deployments" — but the page renders the full Account Governor UI. The sidebar label does not match the page heading. Users click "Deployments" expecting a deployment list, not a portfolio governor control panel.

7. **Route aliasing is invisible in the sidebar.** `/portfolio-governors`, `/governor`, and `/deployments` all render the same page. A user who bookmarks `/governor` and a colleague who bookmarks `/deployments` are on the same page with different browser tab titles and different URL bars. The URL is unreliable as a location indicator.

8. **"Broker Accounts" and "Credentials" are separate sidebar items** when they serve the same concern (Alpaca account setup). A new user must visit both to get an account working.

9. **The sidebar collapses to icons only.** The icons used are not distinctive enough to be used without labels. `ShieldCheck` is used for both **Risk Profiles** (in Build) and **Portfolio Governor** (in Deploy & Monitor). `Clock` is used for Strategy Controls. `Play` is used for Execution Styles. None of these are semantically obvious without labels.

---

### Page Grouping

The current domain groupings — even ignoring the sidebar split problems — have leakage:

- **TradingPrograms** is under "Deploy & Monitor" in the sidebar but acts as an assembly/composition page. It belongs in Build. You compose a program; you don't deploy from it.
- **Run History** is in "Test & Validate" but is really a subordinate page of Backtest (it shows results of backtest runs). It should not be a top-level sidebar item.
- **Chart Lab** is in "Test & Validate" but its only function is static OHLCV inspection — there is no signal evaluation, no backtest, no simulation. It is closer to a data exploration tool. Grouping it with Sim Lab implies they are comparable tools; they are not.
- **Event Calendar** is in "System" but the user intent is market-calendar awareness for strategy development. It belongs in Build or Validate.
- **Data Manager** is in "System" but is an operational prerequisite for every backtest and simulation. It belongs closer to Build.

---

### Naming Clarity

Every naming problem in the current sidebar:

| Current Label | Problem |
|---|---|
| Strategy Controls | The underlying entity is `StrategyGovernor` in the DB, `StrategyControls` in some routes, "Controls" in others. Three names for the same thing. |
| Portfolio Governor | Title of the page is "Account Governor." URL slugs are `/governor`, `/portfolio-governors`, `/deployments`. Four names. |
| Deployments | Routes to the Account Governor page, not a deployment list. |
| Broker Accounts | Shares `ShieldCheck` icon with Portfolio Governor. The word "broker" implies API plumbing, which scares non-technical users. |
| Credentials | URL is `/security`. The page is about Alpaca API keys, not security in any general sense. |
| Optim. Lab | Abbreviation of "Optimization Lab." The sidebar is wide enough to show "Optim. Lab" fully — this abbreviation is inconsistent with other labels (Sim Lab is not abbreviated, Chart Lab is not abbreviated). |
| Sim Lab | Internally the page is SimulationLab. URL is `/simulation`. Sidebar says "Sim Lab." Three names. |
| Run History | This is a subordinate page under Backtest. Giving it a top-level sidebar slot elevates a detail page to primary navigation. |
| Services | Contains data provider configuration AND AI service configuration. These are different concerns. |
| Data | Refers to Data Manager (OHLCV data caching). Single-word label matches nothing about the page's actual function. |
| Logs | The page is `LogsPanel` which contains: Kill Events, a Roadmap, User Journey Validations, Known Issues (hardcoded), and Feature Build Progress (hardcoded). "Logs" implies system logs; the page is actually a developer status dashboard. |

---

### Cognitive Load

Cognitive load is the number of things a user must hold in working memory to complete a task.

**Worst offenders by page:**

**Account Governor (1314 lines)** has seven distinct concerns on one page: global kill strip, per-account governor status panel, governor events log, portfolio snapshot, deployment table, trade viewer, and promotion wizard. A user arriving here to check deployment status must visually parse all seven sections to find the deployment table. A user arriving to halt all trading must find the GlobalKillStrip at the top of a page that has six other things competing for attention.

**TradingPrograms (1033 lines)** asks the user to understand the five-component architecture, compose a program, run validation, launch a backtest, manage allocations, and start/stop deployments — all from one page. The five GuidedCards are the right concept, but the page also inlines validation results, a backtest launch button, an allocations section with start/stop controls, and a progress bar. The cognitive split between "assembling a program" and "running/managing a program" on the same page is severe.

**OptimizationLab** has six tabs that span four different user intents: Results (review historical runs — same as RunHistory), Walk-Forward (analyze a single run), Comparison (compare two runs), Independence (signal correlation analysis), Paper→Live (operational promotion), Param Search (launch new optimization jobs). The page is a six-tab accordion of unrelated concerns wrapped in a shared URL.

**RunDetails** has six tabs and includes a "Promote" tab (an operational action) embedded inside an analysis page. The mixing of analysis and action creates a category error that confuses users about which page owns deployment.

**The confirmation pattern inventory** (by page) shows inconsistent patterns:
- ConfirmationModal (correct): Halt Account, Delete Account, Bulk Delete in AccountMonitor
- Type-to-confirm inline modal (correct for destructive): Flatten Account, Emergency Exit in AccountMonitor
- Type-to-confirm modal with HALT input: KillSwitch global halt
- `window.confirm()` (wrong — browser-native, inconsistent): LiveMonitor close position, LiveMonitor close all positions, WatchlistLibrary delete watchlist, WatchlistLibrary bulk remove symbols
- `alert()` (wrong): WatchlistLibrary delete mutation error
- Implicit (no confirmation at all): RunDetails "Suggest Risk Profile" (creates an entity silently)

**Three pages use `window.confirm()` or `alert()` for safety-critical actions.** In a dark-themed trading platform, the browser native dialog is jarring and visually inconsistent. For close-all-positions on a live account — executed via `window.confirm()` — this is a serious UX failure.

---

### Duplication of Functionality

The following functions are duplicated across multiple pages. Each duplication is a decision point for the user: "which page do I use?" Since the system does not explain, users use whichever they found first.

| Function | Pages Where It Appears |
|---|---|
| Deployment table with start/pause/stop | AccountGovernor, AccountMonitor, DeploymentManager |
| Paper → Live promotion wizard | RunDetails, AccountGovernor, OptimizationLab (Stress tab), DeploymentManager |
| Live positions + orders view | LiveMonitor, AccountMonitor, AccountGovernor (trade viewer), DeploymentManager |
| Close position action | LiveMonitor, DeploymentManager |
| Per-deployment pause/resume | AccountGovernor, DeploymentManager |
| Account halt/resume | AccountMonitor, AccountGovernor |
| Run list with sort/filter | RunHistory, OptimizationLab Results tab, Dashboard (recent runs) |
| Strategy + version selector | BacktestLauncher, SimulationLab, TradingPrograms, (OptimizationLab Param Search) |
| Watchlist selector | TradingPrograms (Watchlist card), BacktestLauncher (symbol sourcing) — different data sources |
| Governor bootstrap | AccountGovernor (buried in GovernorPanel), nowhere else explained |

---

### Where Mental Models Break

**Mental model break 1 — "Deployments" navigates to Account Governor.**
The sidebar item is "Deployments." Every other trading platform calls the screen that shows your running strategies "Deployments." Users click it expecting a deployment list with start/stop controls. They get the Account Governor — a page primarily about portfolio governance and kill switches. The deployment table is one of seven concerns on that page. The mental model "Deployments → deployment list" is violated immediately.

**Mental model break 2 — Strategy vs Strategy Controls.**
Users think of a strategy as everything that controls when they trade: the entry signal, the timeframe, the session window, the PDT rule. The platform splits this into Strategy (signals only) and Strategy Controls (timing/session). This split is architecturally correct but runs directly against the user's intuition. The naming reinforces the confusion: a "strategy control" sounds like you're controlling the strategy, not that you're defining when the strategy is allowed to run.

**Mental model break 3 — Two watchlist systems.**
WatchlistLibrary and DataManager both contain watchlists. They are different database tables. A user who creates a watchlist in DataManager cannot use it in TradingPrograms. The platform has no UI indicator that these are different systems. The user's mental model ("I made a watchlist, it should be available everywhere") is broken with no explanation.

**Mental model break 4 — "Validate" includes both static chart inspection and live engine simulation.**
Chart Lab and Sim Lab are both in "Test & Validate." Chart Lab shows a static OHLCV chart. Sim Lab runs the full BacktestEngine in real-time with live trade signals. These are not comparable tools — one is a visual reference, one is a validation environment. Grouping them suggests they serve the same purpose. Users arrive at Chart Lab expecting signals and are confused when none appear.

**Mental model break 5 — The kill switch badge does nothing.**
The `KillSwitch` component in the header is a red "HALT ALL" button that opens a confirmation modal. This is correct. But the Dashboard's KPI card #5 shows "Kill Switch" as a status indicator — it is not a button. Users who see the red Kill Switch KPI card and click it are taken to… nothing (it has no link). The same concept (kill switch status) is rendered as an actionable button in the header and as a dead display element on Dashboard. Users try to click the Dashboard card to trigger a halt and nothing happens.

---

## 2. CORE USER INTENTS

The five user intents and their definitions:

**Build** — Create and configure the components of a trading program. This is authoring work. The user is not running anything yet. Pages in this intent deal with entities that exist as templates and are reused across multiple programs/runs.

**Validate** — Verify that a program behaves as intended before deploying real capital. This includes visual chart inspection, real-time simulation, backtesting, optimization, and result analysis.

**Operate** — Manage deployed programs: start, stop, configure allocations, promote paper to live. The user is working with live or paper deployments. The fundamental question is "which programs are running and on which accounts."

**Monitor** — Observe running deployments in real time. Read-only or low-risk actions only (close a single position). The user is watching, not making structural decisions.

**Intervene** — Emergency and governance actions: pause a deployment, halt an account, trigger global kill, flatten positions. These actions are time-critical and must be accessible immediately from any context.

**Mapping every current page to ONE intent:**

| Page | Assigned Intent | Rationale |
|---|---|---|
| Dashboard | Monitor | Entry point for situational awareness; shows kill state, active deployments, recent runs |
| Strategies (library) | Build | Authoring entry point |
| Strategy Creator | Build | Authoring |
| Strategy Details | Build | Version inspection; the "vault" for a strategy |
| Strategy Editor | Build | Authoring |
| Strategy Controls | Build | Template creation for timing/session config |
| Risk Profiles | Build | Template creation for sizing/drawdown config |
| Execution Styles | Build | Template creation for order mechanics |
| Watchlist Library | Build | Symbol universe management |
| Trading Programs | Build | Component assembly (the composition step) |
| Chart Lab | Validate | Visual indicator inspection before testing |
| Simulation Lab | Validate | Real-time engine validation |
| Backtest Launcher | Validate | Historical test configuration and launch |
| Run History | Validate | Results inventory (subordinate to Backtest) |
| Run Details | Validate | Single-run deep analysis |
| Optimization Lab | Validate | Multi-run parameter search and analysis |
| Account Governor | Operate | Deployment lifecycle, allocation, promotion |
| Account Monitor | Operate | Broker account management and health |
| Credential Manager | Admin | One-time credential setup |
| Services | Admin | Data provider and AI provider configuration |
| Data Manager | Build | Data prerequisite (feeds both Validate tools and Build) |
| Live Monitor | Monitor | Real-time position and order observation |
| Deployment Manager | Operate | DUPLICATE of Account Governor — merge |
| Event Calendar | Build | Market event awareness during strategy design |
| Logs Panel | Admin | Developer/debug status panel |
| Backup / Restore | Admin | Operational maintenance |

**Note on Intervene:** Intervene is not a page — it is a capability that must be accessible from every page in the Monitor and Operate intents. The global kill strip, per-account halt, and per-deployment pause must be persistent UI elements, not buried inside specific pages.

---

## 3. PROPOSED NAVIGATION MODEL

### Design Principles

1. Maximum 5 navigation groups, each with a single-word label.
2. Maximum 5 items per group in primary navigation. Overflow moves to secondary nav or contextual links.
3. Admin items are collapsed behind a settings gear icon at the bottom of the sidebar, not in the main nav flow.
4. Intervene is a persistent global component (header strip), not a nav destination.
5. No route aliasing — every URL maps to exactly one page with a unique and descriptive slug.
6. Subordinate pages (Run Details, Strategy Details) are not in the sidebar — they are accessed via their parent page.

---

### Proposed Navigation Groups

---

#### GROUP: BUILD
*Create the components of your trading system.*

| Sidebar Label | Route | Replaces |
|---|---|---|
| Strategies | `/strategies` | Strategies |
| Programs | `/programs` | Trading Programs |
| Data Library | `/data` | Data Manager (renamed) |
| Components | `/components` | New hub — see below |

**Components Hub** is a new page (or expandable sidebar section) that groups the four template-type entities: Strategy Controls, Risk Profiles, Execution Styles, Watchlists. These four entities are exclusively referenced by Programs — they have no standalone operational function. Giving each its own top-level sidebar item (as currently) elevates template management to primary navigation, which inflates cognitive load for users who just want to assemble a program. The Components hub shows four cards, each linking to the full library for that component type.

**Data Library** is renamed from "Data" because "Data" is meaningless. "Data Library" conveys "this is where your downloaded price data lives."

**Event Calendar** moves into the Data Library page as a tab, since it provides contextual market data (earnings, holidays) that informs data decisions.

**Justification for removing Watchlists from top-level nav:** Watchlists are referenced by Programs. They are a component. A user who wants to manage watchlists navigates to Components → Watchlists — one extra click from the sidebar, but the mental model is correct: watchlists are a component, not a top-level concern.

---

#### GROUP: VALIDATE
*Test your strategies and programs rigorously before deploying capital.*

| Sidebar Label | Route | Replaces |
|---|---|---|
| Chart Lab | `/chart-lab` | `/charts` |
| Sim Lab | `/sim-lab` | `/simulation` |
| Backtest | `/backtest` | `/backtest` |
| Results | `/results` | `/runs` (Run History, renamed) |
| Optim. Lab | `/optimization` | `/lab` |

**Run History is renamed to Results** and its sidebar label changes from "Run History" to "Results." "History" implies a log. "Results" implies a queryable performance record. The mental model shift: users go to "Results" to find the best-performing runs, not to read a history log.

**Run Details** is not in the sidebar — it is accessed by clicking a run in Results. The route `/results/:runId` replaces `/runs/:runId`.

**Optim. Lab moves from its own group into Validate.** The single-item "Optimize" group is dissolved. Optimization is a validation activity — you run many backtests systematically to find robust parameters. It belongs in Validate.

---

#### GROUP: OPERATE
*Deploy programs, manage accounts, and control what is running.*

| Sidebar Label | Route | Replaces |
|---|---|---|
| Programs | — | Removed from here (it's in Build) |
| Governor | `/governor` | AccountGovernor (canonical URL) |
| Accounts | `/accounts` | AccountMonitor + CredentialManager (merged) |
| Deployments | `/deployments` | NEW — a dedicated deployment list page |

**The core change: split the Account Governor page into two distinct pages.**

The current Account Governor page tries to be both "the operational control room for portfolio governance" (kill strip, governor status, events, snapshot) and "the deployment management table" (start/stop/pause deployments, trade viewer, promotion). These are different concerns at different levels of urgency.

**Governor** (`/governor`) — Owns: global kill strip, per-account governor status, governor events log, portfolio snapshot (capital allocation, symbol collision warnings, overlap matrix). This is the portfolio-level view. It answers the question "how is my overall portfolio positioned?"

**Deployments** (`/deployments`) — Owns: the deployment table for all accounts, start/pause/stop controls, trade viewer per deployment, paper→live promotion wizard. This is the program-level view. It answers "which programs are running and what are they doing?"

This split directly resolves the current page's seven-concern overload and the confusion between "Deployments" (the sidebar label) and "Account Governor" (the page content).

**Accounts** (`/accounts`) — Merges AccountMonitor and CredentialManager into one page. Currently these are split: AccountMonitor handles operational account management (halt, flatten, emergency exit, position viewing) and CredentialManager handles credential CRUD. They operate on the same entity (Account) and a new user must visit both to get started. The merged Accounts page has two sections: Credentials & Setup (top, one-time) and Account Health (operational). A user never needs to split their mental model between "broker accounts" and "credentials."

**DeploymentManager** (`/portfolio-governors` and the duplicate at `/deployments`) is **eliminated**. Its unique capability (position-level actions: scale-out, replace-stop, move-stop-to-breakeven) moves into the new Deployments page as a drill-down panel. The duplicate promotion wizard is removed; promotion lives on Deployments only.

---

#### GROUP: MONITOR
*Watch what is running in real time.*

| Sidebar Label | Route | Replaces |
|---|---|---|
| Live Monitor | `/monitor` | LiveMonitor (no change) |

The Monitor group intentionally has only one page. Live Monitor is the real-time observation surface. Dashboard is intentionally not in this group — it is the entry point, not the monitoring tool. The Monitor group's single item signals to the user: this is the focused, real-time view; everything else is configuration and management.

**Dashboard** moves out of the nav groups entirely and becomes the root route `/` with a "home" icon above all groups. It is the entry point, not a domain-grouped page. This matches how users experience dashboards in professional tools (Bloomberg, Robinhood, Interactive Brokers) — the dashboard/overview is at the top, above the domain navigation.

---

#### ADMIN (Settings gear, bottom of sidebar — not in main nav flow)

Admin items are accessible via a gear icon at the bottom of the sidebar. They expand a secondary panel or navigate to:

| Label | Route | Replaces |
|---|---|---|
| Services | `/admin/services` | Services |
| Credentials | `/admin/credentials` | CredentialManager (partial — credential CRUD view only; merged into Accounts for primary flow) |
| Backup | `/admin/backup` | BackupRestore |
| Logs | `/admin/logs` | LogsPanel |

**Note:** Credential management for the primary flow (new user setup, day-to-day key management) is in **Accounts** (`/accounts`). The Admin → Credentials link is a secondary entry point for technical users who need to view credential status in isolation.

**Services** moves to Admin because data provider and AI provider configuration is a one-time setup concern, not a day-to-day navigation destination. It does not belong in primary navigation.

---

### Before/After Navigation Comparison

**Before:** 27 navigation items across 6 groups (+ unlabeled root)
**After:** 14 navigation items across 5 groups (+ home/dashboard) + 4 admin items behind gear

**Before:**
```
(root)     Dashboard
Build      Strategies, Watchlists, Risk Profiles, Strategy Controls,
           Execution Styles
Test &     Sim Lab, Backtest, Run History, Chart Lab
  Validate
Optimize   Optim. Lab
Deploy &   Programs, Deployments, Live Monitor, Portfolio Governor,
  Monitor  Broker Accounts
System     Services, Credentials, Data, Events, Backup, Logs
```

**After:**
```
(home)     Dashboard
Build      Strategies, Programs, Data Library, Components
Validate   Chart Lab, Sim Lab, Backtest, Results, Optim. Lab
Operate    Governor, Accounts, Deployments
Monitor    Live Monitor
⚙ Admin   Services, Credentials, Backup, Logs
```

---

## 4. PAGE BOUNDARY DEFINITIONS

### Chart Lab — Exact Responsibilities

**Chart Lab is a data exploration tool, not a validation tool.**

Owns:
- Static OHLCV chart rendering from the local data inventory
- Indicator overlay visualization (price pane + volume pane + oscillator pane)
- Zoom and bar-limit selection for visual inspection
- "Load from strategy" button: reads a selected strategy's indicator spec and pre-populates the indicator panel — this feature should be the primary entry into Chart Lab, not an optional add-on
- Bar type selection (candlestick vs line)

Does NOT own:
- Signal markers (entry/exit arrows) — that is Sim Lab
- Any equity curve — that is Sim Lab
- Any trade log — that is Sim Lab
- Any performance metrics — that is Backtest/Results
- Any live data — that is Live Monitor
- Any backtest launch — that is Backtest Launcher

**The page answers one question:** "Does this indicator combination look right on this symbol?"

**Entry criteria:** User must have cached data in the Data Library for the selected symbol+timeframe. If no data exists, the page shows a data-unavailable state with a direct CTA to Data Library — not a generic "no data" empty state.

**Disambiguation from Sim Lab:** Chart Lab has no "Run" button. If a user looks for a run button in Chart Lab, the empty state explains the boundary: "Chart Lab shows indicators. To see signals and trades, use Sim Lab." A banner at the top of Chart Lab (dismissible, shown once) reads: "This tool shows indicators only. For signal validation with entry/exit markers, open Sim Lab."

---

### Sim Lab — Exact Responsibilities

**Sim Lab is the real-time validation environment. It runs the full BacktestEngine on historical data at configurable speed.**

Owns:
- Bar-by-bar strategy or program simulation via WebSocket
- Entry/exit signal markers on the price chart
- Real-time equity strip
- Real-time trade log, positions list, and performance metrics (updating as bars advance)
- Playback controls: play/pause/step/speed selection
- Multi-pane chart: price (with overlays), volume, oscillator, equity strip
- Post-simulation results held in-session (until navigated away or reset)

Does NOT own:
- Historical batch analysis — that is Backtest
- Parameter search — that is Optim. Lab
- Optimization across multiple symbols simultaneously — that is Backtest
- Walk-forward or CPCV analysis — that is Backtest
- Promotion to paper trading — that is Deployments
- Persistent results storage — results are session-only

**The page answers one question:** "Does this strategy fire the right signals on this symbol in this period?"

**Modes** (see Section 9 for full definition).

**Entry criteria:** Data must be cached. If data is missing, the setup drawer shows a data-missing warning inline per symbol, with a "Fetch data →" link that opens the Data Library in a side drawer without leaving Sim Lab.

**Disambiguation from Backtest:** Sim Lab runs on one symbol at a time and is interactive (the user watches bars form). Backtest runs on multiple symbols in a batch and produces a statistical result set. A user who wants to see "how would this have done across 20 symbols over 5 years" uses Backtest. A user who wants to watch the strategy fire and check that it makes sense uses Sim Lab.

**Disambiguation from Chart Lab:** Sim Lab has a Run button. Chart Lab does not. Sim Lab shows trade markers. Chart Lab does not.

---

### Backtest — Exact Responsibilities

**Backtest is the quantitative test harness. It produces statistical evidence of a strategy's historical performance.**

Owns:
- Multi-symbol batch backtest execution
- Date range and provider configuration
- Walk-forward analysis configuration
- CPCV configuration
- Commission and slippage model configuration
- Launch and status monitoring
- Navigation to Results for completed runs

Does NOT own:
- Result analysis (deep metrics, charts) — that is Results (Run Details)
- Optimization / parameter search — that is Optim. Lab
- Real-time simulation — that is Sim Lab
- Promotion — that is Deployments

**The page answers one question:** "How did this program perform across this symbol universe over this historical period, with these validation settings?"

**Run History (renamed Results)** is a subordinate page of Backtest. It is NOT a top-level page. It is accessible via a tab or sub-navigation within Backtest, or via the "Results" sidebar item. The `RunDetails` page is accessible from Results only — it is never a top-level entry point.

---

### Optim. Lab — Exact Responsibilities

**Optim. Lab is the parameter robustness lab. It generates and analyzes multiple backtest runs to find configurations that survive out-of-sample testing.**

Owns:
- Parameter grid definition and optimization job launch
- Batch run results browser (replaces the duplicate of Run History/Results)
- Walk-forward fold analysis for a selected run
- Side-by-side run comparison
- Signal independence (correlation) analysis
- Paper → Live promotion decision surface

Does NOT own:
- Individual single-run deep analysis — that is Results (Run Details)
- Individual backtest launch — that is Backtest
- Real-time simulation — that is Sim Lab
- Chart inspection — that is Chart Lab
- Actual deployment management — that is Deployments (promotion creates a deployment; the deployment is then managed in Deployments)

**The disambiguation problem between Optim. Lab Results tab and Run History (Results page):**

These are currently duplicates. The fix:

- **Results (sidebar page)** shows ALL backtest runs regardless of origin (single-run launches from Backtest, optimization batch runs from Optim. Lab). It is the complete run inventory. It has a filter: `Source: All | Single Runs | Optimization Batches`.
- **Optim. Lab Results tab** shows ONLY runs that belong to the current optimization batch (those with a shared `batch_id`). When no batch is active, it prompts the user to start a Param Search. This is a scoped view, not a global view.

This eliminates the duplication while preserving context: Optim. Lab shows its own runs; Results shows everything.

---

## 5. ABOVE-THE-FOLD REQUIREMENTS

### Dashboard — Above the Fold

**User's question when landing:** "Is anything wrong? What is the state of the platform?"

Must be immediately visible (no scroll):
1. **Platform health strip** — one horizontal bar at the very top of the content area, always visible, showing:
   - Global kill switch state (green "All systems running" / red "PLATFORM HALTED — reason")
   - Count of active paper deployments (pill)
   - Count of active live deployments (pill, with live indicator)
   - Any governance alerts (daily loss lockout, drawdown lockout, symbol collision) as amber badges
2. **Account equity summary** — three numbers in large text: Total Paper Equity, Total Live Equity, Today's P&L (combined). No chart. Numbers only. Links to Accounts page.
3. **Quick status for each live deployment** — small cards, one per live deployment, showing: strategy name, current P&L, status badge. Empty state: "No live deployments."
4. **Recent backtest performance** — the last 5 completed backtest runs, showing only: strategy name, return %, Sharpe. Compact list, not a full table.

Must NOT be above the fold (move below scroll):
- Full backtest runs table with all columns
- Equity allocation bar chart
- Getting started checklist (move to a collapsible onboarding panel at the bottom)
- Quick Actions buttons (these duplicate the sidebar)

**Actions visible immediately:**
- "HALT ALL" button (this is in the persistent header — always visible)
- "Go to Live Monitor" link from each live deployment card

**What must NEVER be ambiguous on Dashboard:**
- Whether any trading halt is active (kill switch, account halt, governor halt) — must show all three levels
- Whether you are in paper-only mode vs. running live money — paper and live equity must be visually differentiated

---

### Sim Lab — Above the Fold

**User's question when landing:** "Get me running a simulation as fast as possible."

Must be immediately visible (no scroll):
1. **Setup panel** — the full simulation configuration (strategy/program selector, symbol, date range, timeframe, speed) must be visible without scrolling when the page loads. This is the entry state. The setup panel must not be hidden behind a "Configure" button.
2. **Chart area** — the multi-pane chart takes up the remaining horizontal space. On first load, it shows an empty/placeholder state with axes visible (not a blank screen).
3. **Playback controls** — Run / Pause / Step / Speed — must be in the same visual zone as the chart, not in a separate panel.
4. **Mode indicator** — the selected mode (Strategy / Program / Governor) must be visibly labeled.

Post-launch (setup collapses):
- Chart occupies the full width (or 70% with sidebar)
- Playback controls remain visible at all times (sticky control bar)
- Right sidebar (Metrics / Positions / Trade Log tabs) is always visible at ≥1280px viewport
- Equity strip is always visible at the bottom of the chart

**What must NEVER be ambiguous in Sim Lab:**
- Whether the simulation is running, paused, or complete
- The current bar timestamp (must be visible on the chart at all times while running)
- Whether data is missing for the selected symbol (must show a symbol-level data status indicator in the setup panel, not wait until launch to error)

---

### Backtest — Above the Fold

**User's question when landing:** "Configure a test and launch it."

Must be immediately visible (no scroll):
1. **Program selector** (if using program mode) — the program's five components should be visible as a compact summary (5 component chips) when a program is selected, not hidden behind the program name.
2. **Symbol input** — the symbol entry field must be immediately visible and focused by default.
3. **Date range selector** — start and end date fields must be visible.
4. **Launch button** — must be visible without scrolling. It should not require the user to scroll past advanced options to find the primary action.

Below the fold (accessible but not required for basic use):
- Walk-forward settings (collapsed by default, expandable)
- CPCV settings (collapsed by default, expandable)
- Provider recommendation (expandable)
- Commission/slippage model

**What must NEVER be ambiguous in Backtest:**
- The difference between Program mode (uses all five components) and Strategy mode (uses only the strategy). A toggle or tab must make this explicit with a label.
- Whether data exists for the selected symbols and date range — show per-symbol data availability icons in the symbol input before launch.
- Whether a backtest is currently running — the header's `BacktestRunningIndicator` handles this, but it should also be shown inline on the Backtest page while waiting for results.

---

### Live Monitor — Above the Fold

**User's question when landing:** "What is happening right now in my running deployments?"

Must be immediately visible (no scroll):
1. **Connection status** — a persistent banner showing WebSocket state (live/stale/disconnected) and the timestamp of the last update. This must be the FIRST thing visible, above all content. If the connection is stale, this is the most important information on the page.
2. **One card per active deployment** — always visible grid, not hidden behind a tab. Each card shows: strategy name, mode (paper/live), current equity, unrealized P&L, position count, status badge, last signal timestamp.
3. **Mode indicator for each deployment** — paper vs live must be unmistakably visually distinct. The current ModeIndicator component uses color (indigo for paper, red for live) — this is correct and must not be compromised.
4. **Emergency controls** — for live deployments, a "Close All Positions" button must be visible directly on the deployment card, not buried in a panel. It must use the same type-to-confirm pattern as Emergency Exit (not `window.confirm()`).

Below the fold (accessible via deployment card click or drill-down):
- Open orders table
- Position-level detail
- Trade log for this deployment

**What must NEVER be ambiguous in Live Monitor:**
- Whether the data is current or stale — every number on the page must have a "last updated N seconds ago" indicator
- Whether an account is paper or live — every deployment card must display this with the ModeIndicator, not just a text label
- Whether the WebSocket is connected — a disconnected monitor showing stale P&L numbers with no warning is a trading risk

---

### Portfolio Governor — Above the Fold

**User's question when landing:** "What is the governance state of my portfolio? Is anything blocked or at risk?"

Must be immediately visible (no scroll):
1. **Global kill switch strip** — same as header, but also shows the last kill event reason and timestamp. Always at the very top of the Governor page.
2. **Per-account governor status grid** — one card per account showing: account name, governor status (active/halted/paused), mode (paper/live), allocated capital, active deployment count, and any active governance events (collision, risk_blocked, daily_loss_lockout). This grid answers "which governors are healthy and which are not" at a glance.
3. **Active governance events** — if ANY events fired in the last 30 minutes, they must appear in a scrolling event ticker or an events panel above the main content. These are the signal that something needs attention.
4. **Halt / Resume controls** — per-account halt and global kill/resume must be immediately accessible from the Governor page without scrolling.

Below the fold:
- Portfolio snapshot (capital allocation chart, symbol collision matrix)
- Program allocation management (add/remove programs)
- Deployment table (this moves to the Deployments page in the redesign)

**What must NEVER be ambiguous on Governor:**
- Whether the kill switch applies globally or per-account — the scope must be labeled on every control
- Whether a governor halt and an account halt are the same thing or different (they call different endpoints) — the UI must use consistent terminology and distinguish them visually
- Whether a halted governor was halted manually or triggered by a risk rule — the halt reason must be shown inline

---

## 6. SYMBOL HANDLING DESIGN

### Single Symbol vs. Multi-Symbol

The platform operates in two fundamentally different symbol modes that require different UX treatments:

**Single-symbol context** (Chart Lab, Sim Lab): One symbol at a time. The symbol selector is a primary input. The chart shows that one symbol. No filtering needed.

**Multi-symbol context** (Backtest, Programs, Live Monitor): Many symbols, potentially 50+. The UX must handle the case where a watchlist contains 50 symbols and the user needs to understand what is happening across all of them.

---

### Symbol Input Design

**For Backtest Launcher and Program creation (multi-symbol input):**

Current: a free-text comma-separated input or "from watchlist" selector. Problem: no validation, no data availability check, no preview of how many symbols are selected.

Proposed: a **Symbol Picker component** with three modes:
1. **Manual entry** — type symbols, tab-complete from a suggestion list. Each symbol gets a chip with a data-available indicator (green dot if cached, amber dot if partial, red dot if missing).
2. **From watchlist** — select a watchlist and see the resolved symbol list with member states. Active symbols are pre-checked; candidate/suspended symbols are shown but unchecked.
3. **Filter mode** — when a watchlist has 50+ symbols, show a filter bar (sector, liquidity tier, member state) so the user can scope down before adding.

The Symbol Picker must show a **data availability summary** before any backtest is launched: "47 symbols have data for this date range. 3 symbols are missing data: AAPL (no 5m data), TSLA (partial range: only 2023–2024), NVDA (no data cached)." The user must decide whether to fetch missing data or exclude those symbols before launch.

---

### 50+ Symbol Programs

For a Program or Deployment with 50+ symbols, the following UI surfaces are affected:

**Sim Lab (50+ symbols):** Sim Lab runs one symbol at a time. For a 50-symbol program, the user selects one symbol from the program's watchlist to simulate. A dropdown shows all 50 symbols. The page does not attempt to run all 50 simultaneously.

**Live Monitor (50+ symbols, multi-deployment):** The deployment card for a 50-symbol program must NOT try to show 50 position rows in the card. The card shows aggregate metrics (total positions, total unrealized P&L, number of active signals today). The user drills down to the full position list by clicking the card. In the detail view:

- **Prioritization by status:** Active positions appear first (sorted by unrealized P&L, worst first). Pending signals appear second. Rejected/blocked symbols appear last in a collapsible "Blocked" section.
- **Triggered column:** When the strategy has fired a signal for a symbol, it gets a "SIGNAL" badge. This makes it easy to scan for what just happened.
- **Rejected column:** When the governor rejected a signal, the symbol shows a "BLOCKED" badge with the rejection reason (collision, risk_blocked, daily_loss_lockout). The reason must be shown — not just "blocked."
- **Search and filter:** A search input filters by symbol name. Filter chips: "Positions," "Signals," "Blocked," "All."

**Governor page (50+ symbol overlap matrix):** The current `collision_risk_symbols` list from the portfolio snapshot must be rendered as an actionable alert, not a JSON dump. For 50+ symbols, show only the symbols that have a collision or are at risk. Show other symbols only in a "View all symbols" expandable section.

---

### Symbol Prioritization Framework

Across all multi-symbol views, symbols should be sorted in this priority order:

1. **ERROR** — symbol has a broker error (position failed, order rejected) — shown first, red
2. **SIGNAL** — strategy just fired a signal for this symbol — shown second, amber
3. **POSITION** — open position exists — shown third, green
4. **BLOCKED** — signal was fired but governor/risk rejected it — shown fourth, orange
5. **WATCHING** — strategy is actively evaluating but no signal — shown fifth, gray
6. **INACTIVE** — symbol not trading (e.g., watchlist state = suspended, or outside session) — shown last, dim

This prioritization should be consistent across Sim Lab, Live Monitor, Deployments, and the Governor's portfolio snapshot.

---

## 7. ERROR AND STATE CLARITY

### Audit of Current Error/State Handling

**Loading states (current):**

| Page | Loading State |
|---|---|
| Dashboard | Skeleton pulse cards (correct) + animated pulse loader for runs (correct) |
| Chart Lab | "Loading chart data…" animated pulse text |
| AccountMonitor | "Loading accounts..." / "Loading deployments..." / "Loading live data..." plain text |
| LiveMonitor | `isFetching` RefreshCw spinner next to account stats (subtle, easy to miss) |
| RunDetails | Per-section spinners (no unified loading state) |
| SimulationLab | No explicit loading state during simulation startup |

**Error states (current):**

| Page | Error Handling |
|---|---|
| Dashboard | Falls through to empty state (no explicit error rendering for most queries) |
| AccountMonitor | Red card for accounts error; red card for deployments error; "Could not load live data" amber text for position errors |
| LiveMonitor | Red border box "Broker error: {message}" per deployment |
| WatchlistLibrary | Red border box with `(error as Error).message`; `alert()` for delete mutation errors |
| ChartLab | Red card with `error.response.data.detail` or `error.message` |
| RunDetails | No explicit error state on most secondary queries |

**Stale data states (current):**

| Page | Stale Handling |
|---|---|
| LiveMonitor | Amber banner "Realtime websocket is stale or disconnected. Polling is backing this {mode} run right now." |
| AccountMonitor | Per-account staleness ticker (green <30s, amber <60s, red ≥60s) — only visible when expanded |
| All polling pages | `usePollingGate()` pauses polling when inactive — no UI indicator that polling is paused |

**WebSocket disconnect states (current):**

| Page | Disconnect Handling |
|---|---|
| LiveMonitor | Amber banner with "Polling" WifiOff pill + age of last event |
| AccountGovernor | No WebSocket — polling only; no disconnect state |
| SimulationLab | No explicit disconnect state during active simulation |

---

### Required State Design

**Every async data load must have exactly three states with defined UI:**

**Loading state** — data is being fetched for the first time (no cached data exists):
- Show skeleton screens that match the shape of the loaded content (not a centered spinner, not a fullscreen loader)
- Skeleton must have the same grid/list structure as the real content
- Loading text (if any) must be specific: "Loading deployments…" not "Loading…"

**Refreshing state** — data exists but a background refresh is in progress:
- Show a subtle indicator only: a small spinner in the top-right of the section, or a "Refreshing…" text with timestamp of last refresh
- Do NOT replace content with a loading skeleton on refresh — content must remain visible
- Do NOT show a fullscreen loading overlay on refresh

**Error state** — fetch failed:
- Show an error card inline in the section that failed (not a page-level error that replaces all content)
- Show the specific error message (never show generic "Something went wrong")
- Show a retry button
- Show the timestamp of the last successful data

---

### What Must NEVER Be Ambiguous

**Stale data ambiguity (highest risk):** A user watching Live Monitor sees P&L numbers. If those numbers are from a WebSocket event 10 minutes ago and the connection is silently stale, the user may take an action based on outdated information. This is a trading risk.

**Required:** Every number on Live Monitor, Account Monitor, and Governor that comes from a live broker must have an explicit "as of [timestamp]" label. If the data is older than the polling interval, it must turn amber. If older than 2× the polling interval, it must turn red. There must be no configuration where stale numbers look the same as live numbers.

**Not-running ambiguity:** A deployment with status "running" in the database may not be executing trades if the governor was never bootstrapped. The deployment appears as "running" in the UI with green status. The user thinks trading is happening. It is not.

**Required:** A deployment can be in one of these states, all of which must be visually distinct:
- `RUNNING — ACTIVE`: green — governor is bootstrapped, strategy is evaluating signals
- `RUNNING — UNGOVERNED`: amber warning — deployment is "running" but governor not initialized; no trades will execute
- `RUNNING — HALTED`: red — deployment is running but governor is halted; no new orders
- `PAUSED`: amber — user manually paused; no new orders
- `STOPPED`: gray — deployment ended
- `FAILED`: red — deployment encountered an error

**Mode ambiguity:** At no point should a user be uncertain whether they are managing real money (live) or simulation money (paper). Mode indicators must be:
- Visible on every page that shows deployments, positions, or orders
- Using a consistent visual language: PAPER = indigo, LIVE = red + pulse animation
- Shown at the account level AND at the deployment level AND at the position level

---

## 8. CONTROL ACTION UX

### Design Principles for Dangerous Actions

1. **Scope must be labeled before the action is triggered.** Every halt/kill/flatten must display the scope (global / account / program) as part of the trigger button's label or an adjacent label — not discovered only in the confirmation modal.
2. **Consequences must be stated in plain language before confirmation.** "This will block all new orders on this live account. Open positions will NOT be closed." — not "Are you sure?"
3. **Confirmation pattern by severity:**
   - Low severity (pause a deployment, halt a paper account): ConfirmationModal with explicit consequence text — no type-to-confirm required.
   - Medium severity (halt a live account, global kill): ConfirmationModal with type-to-confirm input (type "HALT").
   - High severity (flatten all positions on live, emergency exit on live): Full-screen inline modal with type-to-confirm AND a 3-second countdown before the confirm button becomes active.
4. **Result must be explicitly shown.** After any control action completes, the UI must update visibly: the halt button changes to a resume button, the status badge changes, and a timestamped event is written to the governor events log visible on the same page.
5. **Never use `window.confirm()` or `alert()` for any action that affects broker orders or account state.** These are to be replaced immediately with the ConfirmationModal component.

---

### Pause (Deployment-Level)

**Scope:** One deployment. Other deployments on the same account continue to run.

**Trigger:** "Pause" button on the Deployments page, in the deployment row.

**Pre-trigger label:** Pause button shows `⏸ Pause [Strategy Name]` (not just "Pause").

**Confirmation:** ConfirmationModal (variant "warning").
- Title: `Pause "[Strategy Name]"?`
- Body: "No new positions will be opened. Open positions remain active and will continue to be managed. Resume at any time."
- Confirm label: "Pause Program"

**Post-action:** Deployment row status badge changes to PAUSED (amber). Resume button appears. A governor event is logged: `deployment_paused — [reason]`.

**Scope clarity:** The modal body shows which account and which mode (paper/live) this deployment is on.

---

### Kill (Global and Per-Deployment)

**Scope options:** Global (all accounts, all deployments) or Per-Deployment (one deployment).

**Trigger:** 
- Global: "HALT ALL" button in the persistent header. This is ALWAYS accessible regardless of current page.
- Per-deployment: "Kill" button in the Deployments page deployment row (distinct from Pause — Kill is permanent/harder to recover).

**Pre-trigger label (global):** Header button label "HALT ALL" is clear. Do not change it.

**Confirmation (global):** Current type-to-confirm ("HALT") pattern is correct. Add:
- Scope selector: "Global (all trading)" or "This deployment only" — default to Global
- If global: warn "No new orders will be placed on ANY account. Open positions on ALL accounts are NOT closed."
- Countdown: 3-second countdown before confirm button activates (too easy to trigger accidentally today)

**Confirmation (per-deployment):** ConfirmationModal variant "danger".
- Title: `Kill "[Strategy Name]"?`
- Body: "No new orders will be placed. Open positions on [PAPER/LIVE] account [account name] are NOT closed. This is a hard stop — the deployment must be restarted to resume. To pause temporarily, use Pause instead."
- Two CTAs: "Kill Program" (danger) and "Pause Instead" (secondary).

**Post-action (global):** Platform Halted banner appears on every page (above-fold strip). Header button changes to "RESUME ALL" with a pulse animation. Every deployment status badge shows HALTED.

**Post-action (per-deployment):** Deployment row shows STOPPED (gray). Cannot be resumed without creating a new deployment.

**Scope clarity rule:** The header kill button kills globally. If there is only one deployment and it is paper, killing globally still applies globally (in case a live deployment is created later). The scope is always stated in the confirmation modal.

---

### Flatten (Account-Level)

**Scope:** One account. Closes all open positions on that account via broker market orders. Trading status (halt/active) is not changed.

**Trigger:** "Flatten Account" in the Account's overflow menu (Accounts page, Governor page).

**Pre-trigger label:** "Flatten [Account Name] (N positions)" — position count must be included in the trigger label so the user knows what they are about to close.

**Confirmation:** Full-screen inline modal, type-to-confirm.
- Title: `Flatten [Account Name] — [PAPER / LIVE]`
- Body: "Sends market orders to close all N open position(s): [symbol list, max 10 shown, then "+N more"]. The account remains active after flatten — no halt is applied. Positions will be closed at current market prices."
- LIVE-specific warning (additional): "This is a LIVE account. Real orders will be submitted immediately."
- Type-to-confirm: type `flatten` — lowercase.
- 3-second countdown for live accounts. No countdown for paper accounts.
- Confirm button: "Flatten All Positions" (amber, not red — flatten is not as severe as emergency exit).

**Post-action:** Account positions section shows 0 positions. A log entry: `account_flatten — N positions closed — [reason if provided]`.

**Distinguish from Emergency Exit:** The UI must make clear that Flatten does NOT halt trading — after flatten, the strategy can immediately open new positions. If the user wants to halt AND flatten, they use Emergency Exit.

---

### Resume

**Scope variants:** Resume all (global kill cleared), Resume account governor, Resume deployment.

**Global resume:** In the header, when platform is halted, the "HALT ALL" button changes to "RESUME ALL" (green, with Play icon). No type-to-confirm required for resume — resuming is not destructive.

**Confirmation:** ConfirmationModal variant "default".
- Title: "Resume All Trading?"
- Body: "Removes the global halt. All previously-running deployments will resume evaluating signals. Deployments that were individually stopped or paused before the global halt will NOT resume automatically."
- Confirm label: "Resume All Trading"

**Per-account governor resume:** "Resume Trading" button on the Governor page per-account card.
- ConfirmationModal variant "default".
- Title: `Resume Trading — "[Account Name]"?`
- Body: "Removes the halt on this account's governor. Deployments on this account will resume. Global kill switch state is not affected."

**Per-deployment resume:** "Resume" button on the Deployments page in the deployment row (only shown when deployment is PAUSED).
- No confirmation required (resume is not destructive).
- Tooltip on hover: "Resume signal evaluation for [Strategy Name]."

**Scope clarity on resume:** The resume confirmation must always state what WAS halted and WHAT WILL resume. "Deployments that were individually stopped before the halt will NOT resume automatically" must be prominently shown — this is the current undocumented behavior that confuses users.

---

## 9. SIM LAB UX DEFINITION

### Three Modes

Sim Lab operates in three modes selected from a segmented control at the top of the setup drawer.

```
[ Strategy ]  [ Program ]  [ Governor ]
```

The mode selector is the first control in the setup drawer, before all other inputs.

---

### Strategy Mode

**What it is:** Run the signal engine for one strategy version, on one symbol, with default execution and risk assumptions.

**When to use:** When the user wants to answer "does this strategy fire the right signals?" — without worrying about sizing, stops, or session rules.

**What it shows:**
- Price chart with entry/exit markers (arrows or triangles) for every signal generated by the strategy's entry conditions
- Indicator overlays for all indicators referenced in the strategy's entry and exit conditions
- Volume pane
- Oscillator pane (for oscillator-type indicators)
- Equity strip (simplified: assumes fixed position size for visibility, labeled "Illustrative sizing")
- Right sidebar: Metrics (win rate, avg bars held, signal count, basic return), Positions (current open position if any), Trade Log

**What it hides:**
- Risk profile controls (no risk configuration available in this mode)
- Execution style controls (no order type or bracket configuration)
- Governor/session window effects (signals fire regardless of session window)
- Position sizing (uses a fixed illustrative size, clearly labeled as such)
- Governor event log

**Why hide these:** Strategy mode is about signal correctness, not deployment realism. Showing session windows and risk checks would prevent signals from firing during testing and mislead the user about whether the strategy logic is correct. The user needs to see ALL signals, even ones that would normally be filtered by a governor.

**Symbol handling:** One symbol at a time. TickerSearch component. Required: data must be cached.

**Labels and warnings:**
- Mode badge: "STRATEGY MODE — Signals only, illustrative sizing" (amber badge)
- Banner: "Session windows and risk rules are disabled in Strategy Mode. All strategy signals are shown."

---

### Program Mode

**What it is:** Run the full program — strategy + controls + risk profile + execution style — on one symbol from the program's watchlist.

**When to use:** When the user wants to answer "how would this full deployed program have behaved on this symbol?" — including session filtering, PDT enforcement, position sizing, and stop/target calculations.

**What it shows:**
- Price chart with entry/exit markers (only those that passed all governor and risk checks)
- All indicator overlays from the strategy's config
- Session window shading (gray overlay during non-session hours)
- Equity strip (using actual position sizing from the risk profile)
- Right sidebar: Metrics (full program metrics: return, Sharpe, max DD, SQN), Positions (with actual stop/target prices), Trade Log (with exit reasons including force_flat, governor_blocked)
- Governor event log in a collapsible panel at the bottom (shows which signals were blocked and why)

**What it hides:**
- Individual component configuration (the user selected a program; they see the outcome of the program, not a component editor)
- The underlying condition tree logic (signals appear as entry/exit markers; the raw conditions are not shown inline)

**Symbol handling:** One symbol at a time, selected from the program's watchlist. The symbol selector shows only symbols from the program's watchlist with data availability status. Symbols without cached data are shown as unavailable.

**Labels and warnings:**
- Mode badge: "PROGRAM MODE — [Program Name]"
- If a symbol does not have data: "No data cached for [SYMBOL] at [TIMEFRAME]. Fetch in Data Library first."
- If the program's watchlist is empty: "This program has no watchlist symbols. Add symbols in Components → Watchlists."

---

### Governor Mode

**What it is:** Run the full program AND show governor intervention events. This mode is for testing governance behavior: does the governor correctly block signals during cooldown? Does PDT enforcement work? Does the daily loss lockout trigger correctly?

**When to use:** When the user wants to answer "would the governor have blocked this trade, and why?"

**What it shows:**
- Everything in Program Mode
- **Governor event overlay on the chart:** When a signal was blocked by the governor, a different marker type appears (e.g., an X marker instead of an arrow) at the bar where the signal fired. The marker tooltip shows: `BLOCKED: [reason] — [detail]` (e.g., "BLOCKED: PDT limit — 3 day trades already used this week").
- **Governor events panel (always expanded, not collapsible):** Real-time log of every governor decision during playback: allowed signals, blocked signals, cooldown activations, session boundary events, regime filter rejections.
- **Session window visualization:** Shaded overlay AND a timeline at the bottom showing session open/close/force-flat times as vertical lines.
- PDT counter: Shows "N day trades used this week" in the metrics sidebar, updating as trades execute.

**What it hides:**
- None. Governor Mode is the most detailed mode and shows everything. It is the debugging mode.

**Symbol handling:** Same as Program Mode (one symbol from the watchlist at a time).

**Labels and warnings:**
- Mode badge: "GOVERNOR MODE — Full governance simulation"
- If no governor is assigned to the selected program: "This program has no Strategy Controls assigned. Assign Strategy Controls in Programs to use Governor Mode."

---

### Sim Lab Unified Behaviors (All Modes)

**Results persistence:** After a simulation completes, results remain on screen until the user clicks "Reset" or navigates away. A banner shows "Simulation complete — results from [date] at [speed]." Navigating away shows a warning: "This simulation's results will be lost. Continue?" (ConfirmationModal, dismissible with "Don't warn me again" for the session).

**Data missing inline:** If data is missing for a selected symbol+timeframe+date range, the symbol input shows a red dot and the tooltip text "No data for this range. Fetch in Data Library." The Run button is disabled until all required data is present. The user does not discover the error at launch time.

**Speed selector:** 1× / 5× / 25× / 100× / Max. At Max speed, the chart stops updating (too fast to render) and instead shows only the final state with a complete trade log. This prevents the browser from freezing. A label appears: "Running at max speed — chart updates paused. Results will appear on completion."

**Playback bar:** Always visible at the bottom of the chart area (above the equity strip):
- Current bar timestamp (formatted: "Jan 15, 2024 10:35")
- Progress: "Bar 234 / 1,847"
- Progress bar (visual)
- [◀◀ Back 10] [⏸ Pause] [▶ Play] [▶▶ Forward 10] [⏭ Skip to next trade] — these controls are visible in all modes

---

## FINAL UX VERDICT

### Top 5 UX Problems

**Problem 1 — The kill switch is not immediately accessible from the pages where it matters most.**

The "HALT ALL" button exists in the header (correct) but the header kill switch only becomes a type-to-confirm modal — requiring 4 clicks and a typed word when the user may be panicking. The `window.confirm()` close-all-positions in Live Monitor is a different kill mechanism entirely. The governor halt is on a separate page. There is no single, always-visible emergency control surface.

**Impact:** In a fast market event, the user navigates between three pages to understand which halt applies to their situation, while positions are still open. This is the highest-urgency UX failure in the system.

**Problem 2 — The two watchlist systems are invisible to users and silently break Program assembly.**

There is no indicator anywhere in the TradingPrograms watchlist selector that the watchlists it shows come from a different data source than the watchlists in DataManager. A user who builds a watchlist in DataManager and expects to use it in a Program will create the program with no symbols, deploy it, and watch it do nothing. The system will not tell them why.

**Impact:** This is the most common first-deployment failure. It breaks trust in the system at the most critical moment — the first live deployment.

**Problem 3 — The Account Governor page has seven unrelated concerns and no clear primary action.**

When a user opens Account Governor, they see: a global kill strip, per-account governor panels, a portfolio snapshot, a deployment table, trade viewers, and a promotion wizard. There is no visual hierarchy that tells the user "this is the most important thing on this page." In a time-sensitive operational moment, the user must scan all seven sections to find the control they need.

**Impact:** Operational latency in a crisis. The page is powerful but unusable under stress.

**Problem 4 — `window.confirm()` is used for safety-critical position actions in Live Monitor.**

"Close all positions" for a live deployment goes through a browser-native `window.confirm()` box. This is visually inconsistent, provides no contextual information (doesn't show the account name, mode, position count, or P&L), and cannot be customized or tested. For an action that closes real broker positions, this is the wrong confirmation pattern.

**Impact:** User error risk. The `window.confirm()` pattern on a live account is a regulatory and financial risk — no warning about live money, no type-to-confirm, no count of positions being closed.

**Problem 5 — EWM mismatch (documented in feature_engine_audit.md) creates a replay-vs-live signal difference that is invisible in the UI.**

This is partly a UX problem: the user has no way to know that the indicators shown in Sim Lab (batch mode, full history) will produce different values than the indicators used in live trading (rolling 250-bar window). There is no labeling, no warning, and no mode distinction in the indicator display. The user validates a strategy in Sim Lab, deploys it live, and sees different entry points than expected. They conclude the strategy is broken when it is not — the indicator values are just computed differently.

**Impact:** Loss of user confidence in the platform. Strategies appear to "not follow their backtest behavior" in live mode, which is the most damaging user perception for an algo trading platform.

---

### What Must Be Redesigned Immediately

In order of operational and financial risk:

**1. Replace `window.confirm()` and `alert()` with ConfirmationModal throughout.** This is a code change to LiveMonitor, WatchlistLibrary, and any other use site. All confirmation patterns involving broker actions must use ConfirmationModal or the type-to-confirm inline modal. Estimated effort: 1–2 days. Risk reduction: immediate.

**2. Add per-number "as of [timestamp]" labels to all live broker data.** Every equity number, P&L number, and position value that comes from a live broker must show when it was last updated. Stale data must visually differ from fresh data (color change at thresholds). This is the data trust issue that makes Live Monitor unreliable as a monitoring tool. Estimated effort: 2–3 days.

**3. Split Account Governor into Governor + Deployments.** Create a separate `/deployments` page that owns the deployment table, per-deployment controls, trade viewer, and promotion wizard. The Governor page retains only: kill strip, per-account governor status, governor events, and portfolio snapshot. This directly resolves the seven-concern overload and fixes the "Deployments sidebar item leads to Account Governor" naming problem. Estimated effort: 3–5 days.

**4. Add deployment status "UNGOVERNED" state.** A deployment that is "running" but whose governor is not bootstrapped must show a distinct amber "UNGOVERNED" status badge. This prevents the silent never-trades scenario that is the most common first-deployment failure after the watchlist problem. Estimated effort: 1 day (frontend status mapping + backend status endpoint update).

**5. Fix the watchlist system split.** Either: (a) unify the two watchlist database tables into one; or (b) surface both watchlist sources in the TradingPrograms watchlist selector with clear labels ("Data Library Watchlists" vs "Watchlist Library"). Option (b) is a frontend-only change and can be done in 1–2 days. Option (a) is a backend schema migration. Do option (b) immediately; plan option (a) as a V2 change.

---

### What Can Be Improved Later

**Navigation consolidation** (merge Accounts + Credentials, restructure sidebar groups, dissolve the one-item Optimize group) — important for new user experience but does not affect existing users who have already learned the navigation. Estimated effort: 2–3 days frontend, but requires route change coordination. Schedule for next sprint cycle.

**Above-the-fold redesign for Dashboard** (remove Quick Actions, condense to health strip + deployment cards + recent runs) — a UX improvement that reduces cognitive load on entry but does not affect the core trading workflow. Schedule after navigation consolidation.

**Components Hub page** (group Strategy Controls, Risk Profiles, Execution Styles, Watchlists under a single hub) — reduces sidebar item count and enforces the mental model that these are components, not standalone tools. Schedule for next sprint cycle.

**Sim Lab mode selector** (Strategy / Program / Governor) — important for making Sim Lab more useful but does not affect backtest correctness or live trading. Schedule for the sprint after navigation changes.

**Data availability pre-check on Backtest Launcher** (per-symbol data status before launch) — reduces friction in the validation workflow. Schedule after the critical fixes are done.

**Symbol prioritization framework** (ERROR → SIGNAL → POSITION → BLOCKED → WATCHING → INACTIVE) — creates a consistent scanning pattern across Live Monitor, Deployments, and Governor. Schedule as part of the Live Monitor redesign sprint.

---

### The Ideal Mental Model for the Entire Platform

The platform should feel like a **control room with clearly separated stations**, not a collection of pages.

**Station 1 — Build Station (left side of mental model):** Where you create. Strategies, components, programs, data. Nothing here has real-time state. Everything here is durable configuration. You come here when you are thinking and designing.

**Station 2 — Validate Station (middle):** Where you test. You take what you built and throw historical data at it. Chart Lab is a quick visual check. Sim Lab is a signal validator. Backtest is the full statistical test. Optim. Lab is the robustness lab. You leave this station when you have quantitative evidence that a program is worth deploying. Nothing here affects real capital.

**Station 3 — Control Room (right side of mental model):** Where you operate. Governor controls what is allowed to run. Deployments shows what is running. Live Monitor shows what is happening right now. You come here when you are managing active capital. Every action here has real or simulated financial consequences.

**Station 4 — Emergency Panel (always visible):** The kill switch in the header. Not a page. A persistent control. Always reachable. The mental model is: "I can always press this button no matter where I am." The current implementation is close to this (the header HALT ALL button) but is undermined by the `window.confirm()` close-all in Live Monitor and the duplicate halt controls on Account Governor and Account Monitor.

**The platform's single most important mental model rule:** Build is reversible. Validate is reversible. Operate is not reversible (you cannot un-fill a broker order). The visual design must reinforce this — Build and Validate pages feel calm and exploratory (lighter, more spacious). Operate and Monitor pages feel operational and precise (denser information, clear status hierarchy, persistent emergency controls). The current design treats all pages identically (same dark theme, same layout density, same component style) — there is no visual cue that you have crossed from "designing" into "operating."
