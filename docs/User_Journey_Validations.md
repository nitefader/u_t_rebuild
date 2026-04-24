# User Journey Validations

This document is the operating checklist for validating end-to-end product behavior.
It expands coverage from 100 to 150 journeys and explicitly includes:

- happy-path task completion
- partial-fill and order-state edge cases
- websocket/realtime paths
- market-hours, holiday, and calendar behavior
- above-the-fold UX expectations
- menu naming, tooltips, dropdowns, and context-help expectations
- logs, alerts, symbol streams, and news streams

The goal is not just API coverage. The goal is to ensure operators, traders, and reviewers
do not miss critical steps or get misled by partial, stale, or ambiguous UI state.

**Status legend**
- `[ ]` Not yet validated by an automated or structured manual test
- `[x]` Covered by existing automated validation
- `[~]` Partially covered, but missing edge cases, UI, or realtime verification

**Priority legend**
- `P0` Mission-critical, stop-ship if wrong
- `P1` High-value workflow or safety check
- `P2` Important but not immediate stop-ship

---

## ONBOARDING & SETUP (1–10)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 1 | First-time platform setup | Services, AccountMonitor, CredentialManager | `POST /api/v1/services`; `POST /api/v1/accounts`; `PUT /api/v1/accounts/:id/credentials`; `POST /api/v1/accounts/:id/credentials/validate` | Create broker/data services; create broker account; save credentials; validate; confirm account appears above the fold with readable status text | Validation errors must be explicit; no silent success with masked credentials; page copy must say paper vs live clearly | `P0` | `[ ]` |
| 2 | Adding a live Alpaca account | AccountMonitor, CredentialManager | `POST /api/v1/accounts`; `PUT /api/v1/accounts/:id/credentials`; `POST /api/v1/accounts/:id/credentials/validate`; `GET /api/v1/accounts/:id/broker/status` | Create live broker account; store live credentials; validate live connection; verify balances and restrictions load | Saving without validation must be visually discouraged; account mode mismatch must be obvious; buying power and PDT info must not render as placeholders | `P0` | `[ ]` |
| 3 | Connecting an AI service | Services | `POST /api/v1/services`; `POST /api/v1/services/:id/test`; `POST /api/v1/services/:id/set-default-ai` | Add AI provider; test connection; set as default AI | Error details must survive API failures; default badge must update immediately; disabled state must prevent duplicate submits | `P1` | `[ ]` |
| 4 | Configuring a second Alpaca data service | Services | `POST /api/v1/services`; `POST /api/v1/services/:id/test`; `POST /api/v1/services/:id/set-default` | Add second data provider; test connection; set as default data service | Masked credentials must not be re-sent as real secrets; switching default must update all data-dependent dropdowns | `P1` | `[ ]` |
| 5 | Backing up the database | BackupRestore | `GET /api/v1/admin/backup` | Trigger backup; receive downloadable SQLite backup; confirm status messaging | Large backups must still produce a readable completion state; filename must contain timestamp | `P1` | `[ ]` |
| 6 | Restoring from a backup | BackupRestore | `POST /api/v1/admin/restore` | Upload valid backup; restore; surface restart requirement; verify operator sees explicit success copy | Invalid files must fail clearly; partial restore must not claim success; no ambiguous “done” state | `P0` | `[ ]` |
| 7 | Reviewing system health via logs and alerts | LogsPanel | `GET /api/v1/control/kill-events`; `GET /api/v1/admin/user-journey-validations` | Open Logs & Alerts; review risk events; switch to Journey Validation Hub; refresh manually | Failed log query must not display “no events”; stale data must be distinguishable from healthy state | `P0` | `[ ]` |
| 8 | Setting up event calendar awareness | EventCalendar, StrategyControls | `GET /api/v1/events`; `POST /api/v1/events/seed-sample` | Review event calendar; confirm context help explains use; configure blackout-aware controls | Empty calendar must show next action; event times must be readable and timezone-safe | `P1` | `[ ]` |
| 9 | Verifying menu names and context help on first login | Layout, PageHelp, Tooltips | N/A (UI contract) | Confirm menu names are readable; open help icons on key pages; verify tooltips explain critical controls | Help must not obstruct primary actions; tooltips must use plain language; no icon-only meaning without label | `P1` | `[ ]` |
| 10 | Verifying above-the-fold first impression | Dashboard, AccountMonitor, Services | `GET /api/v1/platform/info`; page-level queries | Confirm first screen shows big numbers, clear status text, readable charts, and obvious next actions | Unknown backend state must not render as “Safe”; top metrics must not be blank or microscopic | `P0` | `[ ]` |

---

## WATCHLIST & UNIVERSE (11–20)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 11 | Creating a manual watchlist | WatchlistLibrary | `POST /api/v1/watchlists` | Create manual watchlist with clear name and description | Empty names rejected; success state visible immediately in library | `P1` | `[ ]` |
| 12 | Refreshing a watchlist membership set | WatchlistLibrary | `POST /api/v1/watchlists/:id/refresh` | Trigger refresh; confirm membership table updates | Refresh spinner and completion state must be obvious; stale rows must not linger without timestamp | `P1` | `[ ]` |
| 13 | Promoting a candidate symbol to active | WatchlistLibrary | `PATCH /api/v1/watchlists/:id/members/:symbol` | Change membership state to active; verify table state and badges | Promotion must handle cooldown/dwell rules gracefully; rejected transitions need explicit copy | `P1` | `[ ]` |
| 14 | Suspending a symbol after a bad event | WatchlistLibrary | `PATCH /api/v1/watchlists/:id/members/:symbol` | Suspend symbol; verify state change and reason visibility | Suspension must be visually distinct from inactive; recovery path must be clear | `P1` | `[ ]` |
| 15 | Deleting a stale watchlist | WatchlistLibrary | `DELETE /api/v1/watchlists/:id` | Delete watchlist from library | Destructive confirmation must name the watchlist; delete blockers must be readable | `P1` | `[ ]` |
| 16 | Combining watchlists into a tradable universe | TradingPrograms, WatchlistLibrary | `PUT /api/v1/programs/:id` | Link multiple watchlists or subscriptions; verify resulting universe summary | Union/intersection rules must be readable; duplicate symbols must dedupe safely | `P1` | `[ ]` |
| 17 | Reviewing resolved watchlist states over time | WatchlistLibrary | `GET /api/v1/watchlists`; `GET /api/v1/watchlists/:id` | Inspect memberships with timestamps and lifecycle states | Candidate, active, pending removal, inactive, suspended must be distinguishable | `P2` | `[ ]` |
| 18 | Verifying watchlist dropdown usability | WatchlistLibrary, TradingPrograms | N/A (UI contract) | Confirm dropdown labels, menu text, and tooltips explain watchlist selection clearly | Long names must truncate safely; keyboard selection must remain usable | `P2` | `[ ]` |
| 19 | Handling empty watchlist results | WatchlistLibrary | `GET /api/v1/watchlists/:id` | Open an empty watchlist and review empty-state messaging | Empty state must suggest next action rather than show a blank table | `P1` | `[ ]` |
| 20 | Validating live-feed universe refresh timing | Portfolio Governor, Program runtime | `POST /api/v1/watchlists/:id/refresh`; governor/runtime loop | Confirm live-feed universe changes propagate into active programs | Refresh near market open, holidays, or rapid updates must not thrash or duplicate symbols | `P0` | `[ ]` |

---

## STRATEGY AUTHORING (21–30)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 21 | Building a momentum breakout strategy | StrategyCreator | `POST /api/v1/strategies`; `POST /api/v1/strategies/validate` | Configure entry/exit logic; validate; save strategy | Validation must reject misplaced risk/session fields; indicator names must be readable | `P1` | `[ ]` |
| 22 | Building a mean reversion strategy | StrategyCreator | `POST /api/v1/strategies`; `POST /api/v1/strategies/validate` | Configure reversal logic and exits; validate and save | Strategy must not absorb watchlist or execution-style concerns | `P1` | `[ ]` |
| 23 | Using the condition builder for complex logic | StrategyBuilder/ConditionBuilder | `POST /api/v1/strategies/validate` | Build nested conditions; verify summary text; validate | Invalid nesting must fail precisely; UI must remain readable for long trees | `P1` | `[ ]` |
| 24 | Setting ATR-based stop candidates | StrategyCreator | `POST /api/v1/strategies/validate` | Add ATR stop candidate in strategy | Stop candidate must remain informational, not position-sizing logic | `P1` | `[ ]` |
| 25 | Defining target candidates and staged exits | StrategyCreator | `POST /api/v1/strategies/validate` | Add target candidates and exit logic | Strategy must not own actual order-leg mechanics; those belong to Execution Style | `P1` | `[ ]` |
| 26 | Creating a new strategy version | StrategyDetails | `POST /api/v1/strategies/:id/versions` | Fork a new version from existing strategy | Version numbers must increment clearly; immutable history must remain visible | `P1` | `[ ]` |
| 27 | Comparing two strategy versions | StrategyDetails, VersionDiffPanel | `GET /api/v1/strategies/:id`; `GET /api/v1/strategies/:id/versions/:v1/diff/:v2` | Open diff view and inspect changes | Long diffs must stay readable; no truncation of critical fields | `P2` | `[ ]` |
| 28 | Exporting a strategy | StrategyDetails | `GET /api/v1/strategies/:id/export` | Export strategy definition | Export must be deterministic and include human-readable metadata | `P2` | `[ ]` |
| 29 | Validating strategy schema boundaries | StrategyCreator | `POST /api/v1/strategies/validate` | Confirm strategy validation rejects risk, execution, and controls leakage | Errors must say which component owns the forbidden field | `P0` | `[ ]` |
| 30 | Reviewing strategy readability above the fold | Strategies, StrategyDetails | `GET /api/v1/strategies`; `GET /api/v1/strategies/:id` | Confirm list cards and details show names, tags, logic summaries, and help affordances clearly | Long strategy names and notes must not destroy layout; no dense unreadable JSON above the fold | `P2` | `[ ]` |

---

## STRATEGY CONTROLS (31–40)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 31 | Creating day-trading controls | StrategyControls page / editor | `POST /api/v1/strategy-governors` | Create control set with timeframe, sessions, and trade caps | Must validate time windows and max trades/session cleanly | `P1` | `[ ]` |
| 32 | Configuring session windows | StrategyControls | `PUT /api/v1/strategy-governors/:id` | Add one or more valid entry windows | Overlapping or inverted windows must fail explicitly; timezone must be clear | `P1` | `[ ]` |
| 33 | Configuring cooldown logic | StrategyControls | `PUT /api/v1/strategy-governors/:id` | Add cooldown between entries | Cooldown visibility must be understandable in minutes or bars | `P1` | `[ ]` |
| 34 | Configuring max trades per session | StrategyControls | `PUT /api/v1/strategy-governors/:id` | Set trade cap | UI must explain whether cap is per symbol or global | `P1` | `[ ]` |
| 35 | Setting earnings blackout | StrategyControls | `PUT /api/v1/strategy-governors/:id` | Enable blackout around events | Holiday or no-calendar days must not falsely block; copy must explain behavior | `P1` | `[ ]` |
| 36 | Configuring regime filters | StrategyControls | `PUT /api/v1/strategy-governors/:id` | Add regime filter or gate | Regime block must be reported clearly to operator and logs | `P1` | `[ ]` |
| 37 | Handling market-open and near-close restrictions | StrategyControls | `PUT /api/v1/strategy-governors/:id` | Configure first-bar skip or last-entry window | Early close and half-day rules must be respected | `P0` | `[ ]` |
| 38 | Validating holiday and market-hours behavior | StrategyControls, calendar service | `GET /api/v1/events`; runtime calendar checks | Confirm controls react correctly on holidays, weekends, and half days | Must fail closed on unknown calendar state for new opens | `P0` | `[ ]` |
| 39 | Reviewing controls help text and dropdowns | StrategyControls UI | N/A (UI contract) | Verify menu names, labels, tooltips, and dropdown text are unambiguous | No hidden abbreviations without help text; keyboard selection remains usable | `P2` | `[ ]` |
| 40 | Cloning controls for another duration mode | StrategyControls | `POST /api/v1/strategy-governors/:id/duplicate` | Duplicate and adapt for swing or position use | Duplicate must not silently inherit day-only restrictions without clear review | `P2` | `[ ]` |

---

## RISK PROFILES (41–50)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 41 | Creating a conservative risk profile | RiskProfiles | `POST /api/v1/risk-profiles` | Create profile with low leverage and tight heat limits | Invalid negative values or impossible caps must fail precisely | `P1` | `[ ]` |
| 42 | Creating an aggressive sub-account profile | RiskProfiles | `POST /api/v1/risk-profiles` | Create higher-risk variant for separate account context | UI must make leverage and drawdown implications obvious | `P1` | `[ ]` |
| 43 | Cloning and adjusting a risk profile | RiskProfiles | `POST /api/v1/risk-profiles/:id/duplicate`; `PUT /api/v1/risk-profiles/:id` | Duplicate and tune values | Duplicate must retain provenance and clear naming | `P2` | `[ ]` |
| 44 | Reviewing linked programs and accounts | RiskProfiles | `GET /api/v1/risk-profiles/:id` | Open detail view and inspect associations | Missing association data must not render as “unused” silently | `P1` | `[ ]` |
| 45 | Generating a risk profile from a backtest | RunDetails / RiskProfiles | `POST /api/v1/backtests/:id/suggest-risk-profile` | Generate profile from completed run | Must be gated on sufficient evidence and not zero-fill weak metrics silently | `P0` | `[ ]` |
| 46 | Validating max daily loss behavior | RiskProfiles, Portfolio Governor | risk checks at runtime | Ensure daily-loss caps actually block new opens when breached | Daily-loss lockout must survive restart and be operator-visible | `P0` | `[ ]` |
| 47 | Validating drawdown lockout behavior | RiskProfiles, Portfolio Governor | runtime checks | Ensure drawdown lockout blocks new opens | Lockout state must be distinguishable from manual pause/kill | `P0` | `[ ]` |
| 48 | Verifying fallback stop policy ownership | RiskProfiles, ExecutionStyles | runtime model contract | Confirm fallback risk stop policy is not confused with execution-leg mechanics | Ownership must remain clear between risk and execution domains | `P1` | `[ ]` |
| 49 | Reviewing above-the-fold risk numbers | RiskProfiles | `GET /api/v1/risk-profiles`; `GET /api/v1/risk-profiles/:id` | Confirm big clear numbers for leverage, daily loss, drawdown, positions | No dense unreadable config blobs at the top of the page | `P2` | `[ ]` |
| 50 | Verifying risk-profile dropdown and help text | RiskProfiles, TradingPrograms | N/A (UI contract) | Ensure selectors, labels, and tooltips explain risk implications clearly | Similar names must be distinguishable by description or tag | `P2` | `[ ]` |

---

## EXECUTION STYLES (51–60)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 51 | Creating a bracket execution style | ExecutionStyles | `POST /api/v1/execution-styles` | Create native bracket style | Must align with Alpaca-native bracket rules; no simulated leg ambiguity | `P0` | `[ ]` |
| 52 | Creating a trailing-stop execution style | ExecutionStyles | `POST /api/v1/execution-styles` | Create trailing-stop style | Trailing settings must not imply unsupported broker semantics | `P1` | `[ ]` |
| 53 | Configuring time-in-force and cancel rules | ExecutionStyles | `PUT /api/v1/execution-styles/:id` | Set TIF and cancel-after-bars rules | TIF labels must be human-readable; invalid combinations must fail clearly | `P1` | `[ ]` |
| 54 | Configuring stop-limit breakout entry | ExecutionStyles | `POST /api/v1/execution-styles` | Define stop-limit entry offsets | UI must explain offset units and failure cases | `P1` | `[ ]` |
| 55 | Configuring scale-out tiers | ExecutionStyles | `PUT /api/v1/execution-styles/:id` | Add scale-out levels | Percent totals must be validated; partial percentages must add up sensibly | `P1` | `[ ]` |
| 56 | Cloning an execution style | ExecutionStyles | `POST /api/v1/execution-styles/:id/duplicate` | Duplicate and rename style | Duplicate must not silently alter fill model assumptions | `P2` | `[ ]` |
| 57 | Reviewing execution-style readability | ExecutionStyles | `GET /api/v1/execution-styles` | Confirm order-type summaries are visible without drilling into JSON | Primary order behavior must be understandable above the fold | `P2` | `[ ]` |
| 58 | Validating partial-fill behavior assumptions | ExecutionStyles, broker integration | order/fill runtime path | Confirm style behavior under partial fill, cancel/reduce, and bracket remains coherent | Partial fills must not orphan protective logic or mislead UI state | `P0` | `[ ]` |
| 59 | Verifying cancel-on-pause behavior ownership | ExecutionStyles, Portfolio Governor | runtime policy | Confirm resting opening orders can be canceled on pause/kill while protective orders survive | Must classify opening vs reducing orders safely | `P0` | `[ ]` |
| 60 | Verifying help text for order-expression choices | ExecutionStyles UI, Tooltips | N/A (UI contract) | Tooltips explain market, limit, stop-limit, bracket, trailing-stop, TIF, cancel rules | No unexplained broker jargon in dropdowns or labels | `P2` | `[ ]` |

---

## PROGRAM COMPOSITION (61–70)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 61 | Composing a complete program | TradingPrograms | `POST /api/v1/programs` | Select all five components; save program; review resulting composition | Program page must truly allow composition, not just display cards | `P0` | `[ ]` |
| 62 | Editing program component bindings | TradingPrograms | `PUT /api/v1/programs/:id` | Change one component binding and save | Frozen programs must not allow silent mutation; blockers must be explicit | `P1` | `[ ]` |
| 63 | Freezing a program for paper deployment | TradingPrograms | `POST /api/v1/programs/:id/freeze` | Freeze program and confirm read-only state | Freeze action must explain irreversible consequences clearly | `P1` | `[ ]` |
| 64 | Allocating a program to a broker account | TradingPrograms | `POST /api/v1/programs/:id/allocations` | Allocate frozen program to paper account | Account and mode must be explicit; override bounds must validate | `P1` | `[ ]` |
| 65 | Reviewing promotion eligibility | TradingPrograms | `POST /api/v1/programs/:id/allocations/:alloc_id/promotion-review` | Run promotion review and inspect checklist | Failures must preserve structured blocker details | `P1` | `[ ]` |
| 66 | Executing paper-to-live promotion | TradingPrograms | `POST /api/v1/programs/:id/allocations/:alloc_id/promote` | Execute promotion with checklist approval | Promotion should fail closed on missing review or unresolved blockers | `P0` | `[ ]` |
| 67 | Deprecating an old program | TradingPrograms | `POST /api/v1/programs/:id/deprecate` | Deprecate superseded program | Deprecation must not delete runtime history or allocations silently | `P2` | `[ ]` |
| 68 | Verifying program page above-the-fold clarity | TradingPrograms, ProgramSwimlane | N/A (UI contract) | Confirm selected components, status, and next action are visible immediately | Must not rely on scrolling to understand whether program is deployable | `P1` | `[ ]` |
| 69 | Verifying program start/stop safety controls | TradingPrograms | allocation start/stop endpoints | Confirm live-affecting start/stop actions require proper confirmation and result messaging | One-click runtime mutation without feedback is unsafe | `P0` | `[ ]` |
| 70 | Verifying component ownership boundaries in program UX | TradingPrograms | N/A (UI contract) | Ensure Strategy, Controls, Risk, Execution, Watchlist remain distinct in UI copy and tooltips | Program must not invite inline leakage of cross-component logic | `P1` | `[ ]` |

---

## PORTFOLIO GOVERNOR (71–80)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 71 | Opening Portfolio Governor overview | AccountGovernor / Portfolio Governor page | `GET /api/v1/governor`; `GET /api/v1/governor/:account_id` | Open overview and inspect account-scoped control state | Unknown governor state must not appear healthy; scope wording must be explicit | `P0` | `[ ]` |
| 72 | Hot-adding a program to a governed portfolio | AccountGovernor | `POST /api/v1/governor/:account_id/allocate` | Add program allocation to governed portfolio | Conflicts must return readable structured blocker details | `P1` | `[ ]` |
| 73 | Reviewing portfolio overlap and collision risk | AccountGovernor | `GET /api/v1/governor/:account_id/portfolio-snapshot` | Inspect overlapping symbols and collision warnings | Shared-symbol logic must be correct even with multiple watchlists/programs | `P0` | `[ ]` |
| 74 | Monitoring governor event log | AccountGovernor | `GET /api/v1/governor/:account_id/events` | Open event log and inspect recent events | Event ordering and timestamps must remain readable and scoped | `P1` | `[ ]` |
| 75 | Pausing the governed portfolio in an emergency | AccountGovernor | `POST /api/v1/governor/:account_id/halt` | Pause new opens for that portfolio scope | Must stop new opens, cancel resting opening orders without positions, and preserve protective exits | `P0` | `[ ]` |
| 76 | Resuming the governed portfolio | AccountGovernor | `POST /api/v1/governor/:account_id/resume` | Resume governed portfolio after halt | Resume must require clear operator intent and restore only allowed behavior | `P0` | `[ ]` |
| 77 | Reviewing governor metrics by program | AccountGovernor | `GET /api/v1/governor/:account_id/portfolio-snapshot` plus future metrics | Inspect concentration, symbol overlap, and program-level load | Missing metrics must not render as “all clear” | `P1` | `[ ]` |
| 78 | Resolving daily-loss lockout | AccountGovernor, RiskProfiles | governor events and runtime gates | Verify daily-loss breach blocks new opens and is explainable to operator | Lockout must survive restart and not confuse with manual pause | `P0` | `[ ]` |
| 79 | Attaching a new risk profile to governed scope | AccountGovernor | `PUT /api/v1/accounts/:account_id/risk-profile` | Attach or update account risk profile | Assignment must not silently overwrite stricter active protections | `P1` | `[ ]` |
| 80 | Checking correlation and concentration logic | AccountGovernor | portfolio snapshot and runtime risk checks | Review correlation and concentration warnings | False negatives around shared symbols are unacceptable; stale data must be labeled | `P0` | `[ ]` |

---

## BROKER ACCOUNTS & SAFETY (81–90)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 81 | Reviewing broker account balances and status | AccountMonitor | `GET /api/v1/accounts`; `GET /api/v1/accounts/:id`; `GET /api/v1/accounts/:id/broker/status` | Inspect balances, equity, mode, and risk status | Unknown broker state must not show “Active”; status badges must be explicit | `P0` | `[ ]` |
| 82 | Refreshing broker account equity | AccountMonitor | `POST /api/v1/accounts/:id/refresh`; `POST /api/v1/accounts/:id/sync-from-broker` | Refresh account data from broker | Refresh failure must not silently leave stale data looking fresh | `P1` | `[ ]` |
| 83 | Halting a broker account | AccountMonitor | `POST /api/v1/accounts/:id/halt` | Pause new opens for a specific broker account | Must cancel resting opening orders in scope without flattening positions | `P0` | `[ ]` |
| 84 | Resuming a broker account | AccountMonitor | `POST /api/v1/accounts/:id/resume` | Resume account after halt | Resume must not be one-click ambiguous in a live environment | `P1` | `[ ]` |
| 85 | Flattening a broker account | AccountMonitor | `POST /api/v1/accounts/:id/flatten` | Explicitly liquidate existing positions | Partial flatten must be surfaced item-by-item; success cannot hide failures | `P0` | `[ ]` |
| 86 | Emergency exit on a broker account | AccountMonitor | `POST /api/v1/accounts/:id/emergency-exit` | Halt new opens and flatten positions in one deliberate action | Partial failure must be shown; action text must distinguish from pause-only controls | `P0` | `[ ]` |
| 87 | Reviewing open broker orders | AccountMonitor | `GET /api/v1/accounts/:id/broker/orders` | Inspect open broker orders and statuses | Must differentiate opening vs reducing/protective orders where possible | `P1` | `[ ]` |
| 88 | Reviewing PDT and broker restrictions | AccountMonitor | `GET /api/v1/accounts/:id/broker/status` | Inspect PDT, multiplier, and account restrictions | Missing PDT values must not be displayed as safe defaults | `P1` | `[ ]` |
| 89 | Validating paper vs live wording | AccountMonitor, CredentialManager | account queries and UI contract | Confirm paper/live labels are always visible in menus, badges, and confirmations | Generic “account” wording is unacceptable for destructive actions | `P0` | `[ ]` |
| 90 | Verifying account action tooltips and menu labels | AccountMonitor | N/A (UI contract) | Ensure tooltips explain Halt, Resume, Flatten, Emergency Exit | Tooltips must match actual behavior exactly; no “kill” wording for flatten-only actions | `P1` | `[ ]` |

---

## BACKTESTING & VALIDATION (91–100)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 91 | Launching a basic backtest | BacktestLauncher | `POST /api/v1/backtests/launch` | Choose strategy/program, date range, and launch run | Must reject invalid ranges and unsupported timeframe/provider combos | `P1` | `[x]` |
| 92 | Backtesting with yFinance data | BacktestLauncher | `POST /api/v1/backtests/launch` | Launch with yfinance provider | Provider recommendation and data source labeling must remain explicit | `P1` | `[x]` |
| 93 | Running walk-forward validation | BacktestLauncher | `POST /api/v1/backtests/launch` with walk-forward config | Configure walk-forward and review result | UI must consume actual backend payload fields, not synthetic stand-ins | `P0` | `[~]` |
| 94 | Reviewing a completed backtest in detail | RunDetails | `GET /api/v1/backtests/:id`; `GET /api/v1/backtests/:id/trades` | Open run details, inspect metrics, trades, and validation evidence | Undefined metrics must not masquerade as confident numbers | `P0` | `[x]` |
| 95 | Reading monthly heatmap and diagnostics | RunDetails | `GET /api/v1/backtests/:id` | Review monthly returns and recommendation panels | Missing evidence must be shown as missing, not zero or fake Sharpe | `P1` | `[ ]` |
| 96 | Deleting a failed backtest run | RunHistory | `DELETE /api/v1/backtests/:id` | Delete failed run from history | Delete should be blocked or explained for running runs | `P1` | `[ ]` |
| 97 | Running CPCV validation | BacktestLauncher, RunDetails | `POST /api/v1/backtests/launch` with CPCV config | Configure CPCV and inspect anti-bias evidence | CPCV must not be hidden default only; user must be able to inspect assumptions | `P0` | `[~]` |
| 98 | Requesting provider recommendation | BacktestLauncher | `POST /api/v1/backtests/provider-recommendation` | Ask for provider recommendation before launch | Recommendation reasoning must be readable and not misleadingly certain | `P2` | `[ ]` |
| 99 | Reviewing partial result states during long runs | RunHistory, RunDetails | `GET /api/v1/backtests`; `GET /api/v1/backtests/:id` | Observe queued/running/failed/completed states | Running state must not allow impossible actions like hidden cancel or stale “completed” view | `P1` | `[ ]` |
| 100 | Verifying no-lookahead and terminal-bar realism | Backtest engine / reporting | backtest engine internals | Confirm last-bar fill logic and zero-trade metric handling are realistic | Same-bar impossible fills and fake OOS metrics are unacceptable | `P0` | `[ ]` |

---

## SIMULATION & REPLAY (101–110)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 101 | Creating a simulation session | SimulationLab | `POST /api/v1/simulations/create`; `WS /ws/simulation/:id` | Configure symbols/timeframe/provider and create simulation | Saved-service credentials must work; masked secrets must not be forwarded as real | `P0` | `[ ]` |
| 102 | Stepping through trades manually | SimulationLab | `POST /api/v1/simulations/:id/step` | Step simulation bar by bar | Step state must remain authoritative after reconnects | `P1` | `[ ]` |
| 103 | Playing a simulation at speed | SimulationLab | `WS /ws/simulation/:id` | Start play mode and observe updates | Play/pause must not silently change local state when websocket is closed | `P1` | `[ ]` |
| 104 | Reviewing simulation metrics panel | SimulationLab | `GET /api/v1/simulations/:id`; `WS /ws/simulation/:id` | Inspect metrics and equity panel during playback | Metrics must be clearly labeled as simulation, not live P&L | `P1` | `[ ]` |
| 105 | Reviewing candlestick trade markers | SimulationLab | `WS /ws/simulation/:id` | Watch trade markers update on chart | Marker order must remain correct under skips or reconnects | `P2` | `[ ]` |
| 106 | Resetting local replay state safely | SimulationLab | local UI reset | Reset local state and confirm explicit restart path | Reset must not pretend the backend session was reset if it was only local UI cleanup | `P1` | `[ ]` |
| 107 | Handling simulation websocket disconnect | SimulationLab | `WS /ws/simulation/:id` | Disconnect stream and review reconnect/error messaging | UI must not claim paused/playing certainty after disconnect without confirmation | `P0` | `[ ]` |
| 108 | Running two simulation tabs safely | SimulationLab | shared sim backend state | Open same simulation in two tabs | Multi-tab control races must be handled or blocked clearly | `P0` | `[ ]` |
| 109 | Reviewing partial-fill replay logic | SimulationLab, TradeReplayPanel | sim/replay data | Verify fills, partial fills, and remaining quantity are shown truthfully | Partial fills must not appear as full exits/entries | `P0` | `[ ]` |
| 110 | Using context help on simulation controls | SimulationLab, PageHelp, tooltips | N/A (UI contract) | Confirm play/step/skip controls explain behavior clearly | Control text must reduce operator ambiguity under fast-moving replay | `P2` | `[ ]` |

---

## OPTIMIZATION & QUANT REVIEW (111–120)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 111 | Running a parameter sweep | OptimizationLab | `POST /api/v1/backtests/optimize` | Launch optimization run with parameter grid | Parameter grid size must be bounded and clearly described | `P1` | `[ ]` |
| 112 | Reviewing optimization results | OptimizationLab | optimization responses plus run list | Inspect ranked runs and heatmaps | Rankings must not use fabricated OOS metrics | `P0` | `[ ]` |
| 113 | Analyzing walk-forward fold performance | OptimizationLab | `GET /api/v1/backtests/:id` | Review fold-by-fold OOS behavior | UI must read actual `metrics.walk_forward` and evidence fields | `P0` | `[ ]` |
| 114 | Detecting overfit strategies | OptimizationLab | backtest list/details/evidence | Review overfit indicators and warnings | Overfit flags must be based on real evidence, not heuristics dressed as facts | `P0` | `[ ]` |
| 115 | Comparing two optimization candidates | OptimizationLab | compare payloads and run metrics | Compare IS vs OOS, drawdown, and trade count | Missing evidence must stay explicit, not silently zero-filled | `P1` | `[ ]` |
| 116 | Reviewing independence analysis | OptimizationLab | local analysis / future ML endpoint | Review signal independence or overlap screen | Heuristic-only analysis must be labeled as heuristic | `P2` | `[ ]` |
| 117 | Reviewing cost sensitivity | RunDetails, OptimizationLab | validation evidence | Inspect slippage/commission sensitivity | Infinite or undefined metrics must not be serialized as confident numbers | `P0` | `[ ]` |
| 118 | Reviewing Monte Carlo output | RunDetails | Monte Carlo within metrics/evidence | Inspect robustness analysis | If Monte Carlo is absent, UI must not imply it exists via labels or route names | `P2` | `[ ]` |
| 119 | Promoting best run to paper from optimization | OptimizationLab | `POST /api/v1/deployments/promote-to-paper` | Promote selected validated run | Promotion should require real evidence, not fabricated OOS ranking | `P0` | `[ ]` |
| 120 | Reviewing quant charts above the fold | OptimizationLab, RunDetails, Dashboard | chart-heavy UI contract | Confirm charts are readable, labels are large enough, and legends make sense | No tiny unreadable annotations or unlabeled axes in primary decision surfaces | `P1` | `[ ]` |

---

## DEPLOYMENTS & LIVE MONITORING (121–130)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 121 | Starting a paper deployment | DeploymentManager / TradingPrograms | `POST /api/v1/deployments/:id/start` or allocation start path | Start paper deployment and confirm runtime status | Start action must not be hidden behind wrong page routing | `P1` | `[ ]` |
| 122 | Pausing a deployment | DeploymentManager | `POST /api/v1/deployments/:id/pause` | Pause deployment mid-session | Pause semantics must be explicit: stop new opens vs flatten | `P1` | `[ ]` |
| 123 | Stopping and archiving a deployment | DeploymentManager | `POST /api/v1/deployments/:id/stop` | Stop deployment and archive | Stop must not silently leave live orders working | `P0` | `[ ]` |
| 124 | Reviewing deployment trades | DeploymentManager | `GET /api/v1/deployments/:id/trades` | Open trades panel and inspect history | Trade attribution must remain correct for partial fills and scale-outs | `P0` | `[ ]` |
| 125 | Monitoring real-time positions | LiveMonitor | `GET /api/v1/monitor/runs`; `GET /api/v1/monitor/runs/:id`; `WS /ws` | Open live monitor, view positions, watch updates | UI must not mix snapshots from different polls; unknown WS state must be explicit | `P0` | `[ ]` |
| 126 | Manually closing one position | LiveMonitor | `POST /api/v1/monitor/runs/:id/close-position` | Close a single position from monitor | Confirmation must state live vs paper; result must show success/partial failure clearly | `P0` | `[ ]` |
| 127 | Using Close All for account liquidation | LiveMonitor | `POST /api/v1/monitor/runs/:id/close-all` | Close all positions in scope | Scope must be explicit to avoid deployment-vs-account confusion | `P0` | `[ ]` |
| 128 | Reviewing open orders in live monitor | LiveMonitor | `GET /api/v1/monitor/runs/:id/orders` | Inspect open orders alongside positions | Opening vs protective orders must be distinguishable where possible | `P1` | `[ ]` |
| 129 | Monitoring websocket freshness and fallback | LiveMonitor | `WS /ws` plus polling | Verify live indicator, stale indicator, and polling fallback states | Slow or dropped sockets must not present stale data as “Live” | `P0` | `[ ]` |
| 130 | Reviewing monitor layout above the fold | LiveMonitor | N/A (UI contract) | Confirm top cards show equity, cash, exposure, P&L with big readable numbers | Critical actions and status must be visible without scrolling | `P1` | `[ ]` |

---

## DATA, CHART LAB & REALTIME FEEDS (131–140)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 131 | Fetching historical data for a new symbol | DataManager | `POST /api/v1/data/fetch`; `GET /api/v1/data/inventory` | Fetch symbol data and confirm inventory row appears | Invalid symbol/provider credentials must fail with useful detail | `P1` | `[ ]` |
| 132 | Batch-fetching data for a sector | DataManager | `POST /api/v1/data/fetch-many` | Fetch multiple symbols in one action | Partial success must list failed symbols, not just generic failure | `P1` | `[ ]` |
| 133 | Loading Alpaca keys from a broker account | DataManager | account list + data fetch flows | Use shortcut to load broker credentials into data manager flow | Shortcut must actually work and not depend on fields omitted by account list payload | `P1` | `[ ]` |
| 134 | Exploring indicators in Chart Lab | ChartLab | `GET /api/v1/data/inventory`; `GET /api/v1/data/inventory/:symbol/:timeframe`; `GET /api/v1/data/bars/:symbol/:timeframe` | Open chart, choose symbol/timeframe, enable indicators | Provider selection must match cached provider correctly | `P1` | `[ ]` |
| 135 | Visually validating a strategy signal | ChartLab | cached bar/indicator paths | Overlay indicators and visually inspect signal conditions | Missing indicator series must show as computation failure, not implied flat values | `P0` | `[ ]` |
| 136 | Deleting stale cached data | DataManager | `DELETE /api/v1/data/cache/:symbol/:timeframe` | Delete cache row and verify inventory refresh | Delete confirmation must name symbol and timeframe clearly | `P1` | `[ ]` |
| 137 | Reviewing symbol search UX | DataManager | `GET /api/v1/data/search` | Search symbols and select one for fetch or charting | Empty, loading, and error states must be explicit and readable | `P2` | `[ ]` |
| 138 | Reviewing realtime symbol stream requirements | LiveMonitor, ChartLab, future symbol stream | `WS /ws` plus future symbol/news channels | Verify UI stories for symbol stream, bar updates, and event annotations | Realtime states must be scoped and not broadcast globally without context | `P1` | `[ ]` |
| 139 | Reviewing news stream requirements | future News panel / EventCalendar / LogsPanel | future news websocket / event feed | Verify news-driven awareness flow for symbols and portfolios | News must be timestamped, symbol-scoped, and clearly separated from market data | `P2` | `[ ]` |
| 140 | Reviewing chart tooltips and readable text | ChartLab | chart UI contract | Ensure tooltips, legends, dropdowns, and labels stay readable with dense indicator sets | No tiny fonts or unlabeled overlays in critical decision views | `P1` | `[ ]` |

---

## LOGS, REPORTING & OPERATOR UX (141–150)

| # | Journey | Pages / Components | API Routes / Streams | Required Steps | Edge Cases / Acceptance | Priority | Test Status |
|---|---|---|---|---|---|---|---|
| 141 | Reviewing kill-switch event history | LogsPanel | `GET /api/v1/control/kill-events` | Open Risk Events tab and inspect kill/pause/resume history | Failed queries must not render reassuring empty-state copy | `P0` | `[ ]` |
| 142 | Refreshing the Journey Validation Hub | LogsPanel | `GET /api/v1/admin/user-journey-validations` | Refresh hub and verify summary cards, filters, and domain bars update | Refresh failure must show explicit operator action, not stale success copy | `P1` | `[ ]` |
| 143 | Filtering journeys by domain, priority, and status | LogsPanel | journey validation payload | Use dropdown filters and text search to isolate critical journeys | Filters must remain fast and readable with 150 rows | `P2` | `[ ]` |
| 144 | Reviewing required steps for a journey | LogsPanel | journey validation payload | Expand a journey and inspect step checklist | Checklist must make missing steps obvious; no dense unreadable prose blocks | `P1` | `[ ]` |
| 145 | Reviewing edge-case checklist for partial fills | LogsPanel | journey validation payload | Expand partial-fill-sensitive journeys and review acceptance conditions | Partial-fill cases must exist for execution, monitor, and replay flows | `P0` | `[ ]` |
| 146 | Verifying above-the-fold expectations across pages | Dashboard, LiveMonitor, AccountMonitor, RiskProfiles, OptimizationLab | N/A (UI contract) | Review journey entries for above-the-fold critical information | Big numbers, readable charts, and clear next actions must be documented and testable | `P1` | `[ ]` |
| 147 | Verifying menu names and tooltips across critical pages | Layout, Tooltips, PageHelp | N/A (UI contract) | Confirm menu labels and help affordances are covered by journeys | Operator-critical controls must not rely on unexplained shorthand | `P1` | `[ ]` |
| 148 | Reviewing dashboard performance summary | Dashboard | page queries and top-level summaries | Inspect top metrics and summary charts | Unknown backend state must not render as “All systems go” | `P0` | `[ ]` |
| 149 | Reviewing deployment, account, and portfolio wording | AccountMonitor, LiveMonitor, AccountGovernor, TradingPrograms | N/A (UI contract) | Confirm scope names are explicit in text, badges, buttons, and confirmations | Deployment/account/portfolio confusion is unacceptable in destructive flows | `P0` | `[ ]` |
| 150 | Reviewing realtime logs, symbol streams, and news streams in operator UX | LogsPanel, LiveMonitor, future symbol/news panels | risk events; `WS /ws`; future symbol/news channels | Confirm operator can distinguish risk events, order events, symbol updates, and news updates | Stream state, freshness, and scope must be visible; no global undifferentiated firehose | `P1` | `[ ]` |

---

## Coverage Summary

| Domain | Total | Covered | Partial | Not Covered |
|---|---:|---:|---:|---:|
| Onboarding & Setup | 10 | 0 | 0 | 10 |
| Watchlist & Universe | 10 | 0 | 0 | 10 |
| Strategy Authoring | 10 | 0 | 0 | 10 |
| Strategy Controls | 10 | 0 | 0 | 10 |
| Risk Profiles | 10 | 0 | 0 | 10 |
| Execution Styles | 10 | 0 | 0 | 10 |
| Program Composition | 10 | 0 | 0 | 10 |
| Portfolio Governor | 10 | 0 | 0 | 10 |
| Broker Accounts & Safety | 10 | 0 | 0 | 10 |
| Backtesting & Validation | 10 | 3 | 2 | 5 |
| Simulation & Replay | 10 | 0 | 0 | 10 |
| Optimization & Quant Review | 10 | 0 | 0 | 10 |
| Deployments & Live Monitoring | 10 | 0 | 0 | 10 |
| Data, Chart Lab & Realtime Feeds | 10 | 0 | 0 | 10 |
| Logs, Reporting & Operator UX | 10 | 0 | 0 | 10 |
| **TOTAL** | **150** | **3** | **2** | **145** |

---

## Validation Notes

- Existing automated coverage is still concentrated in basic backtest launch and result retrieval.
- This expanded matrix intentionally includes target-state journeys around realtime symbol streams, news streams, partial fills, above-the-fold operator UX, and control-plane semantics because those are mission-critical gaps.
- Journey definitions should evolve with the product, but they should remain explicit enough that an engineer, tester, or operator can tell exactly what must happen and what must not happen.
- For stop-ship reviews, start with all `P0` journeys and any journey mentioning `partial fill`, `websocket`, `kill`, `pause`, `flatten`, `holiday`, `market close`, `restart`, or `above-the-fold`.
