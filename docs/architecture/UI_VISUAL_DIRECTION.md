# UI Visual Direction

Source review: `C:\Users\potij\OneDrive\Ultimate_Trading_Software_2026`

Purpose: capture the good UI ideas from the original repo without importing old
architecture names or workflows that conflict with Ultimate Trader.

This is recommendation-only. Do not treat old UI code as active product truth.

## What To Keep

The original UI had a clean, operator-friendly visual language worth carrying
forward:

- compact cards with clear borders and calm spacing
- badges for mode, provider, sync, status, default, and warnings
- icon-led buttons and navigation using familiar symbols
- dense but readable dashboard KPI cards
- Account cards that surface balances, positions, open orders, connection state,
  pause/halt controls, and danger actions in one place
- Providers layout with segmented tabs and provider cards
- inline credential validation feedback
- compact status strips such as last updated, connected, stale, halted, active
- right-side help/explainer drawer pattern
- theme tokens for consistent color, spacing, border, and shadow behavior

These ideas fit Ultimate Trader if renamed and simplified.

## What To Translate

| Old UI idea | Ultimate Trader translation |
|---|---|
| Broker Account cards | Account cards |
| Services page | Providers page |
| Data Services tab | Market Data Providers tab |
| AI Services tab | AI Providers tab |
| Live Monitor | Operations runtime panels |
| Paper/Live active deployment badges | Account mode/status badges |
| PageHelp drawer | Ultimate Trader explainer drawer |
| Security/Credentials page | Account credential section or provider credential section |
| Program/Portfolio Governor help text | Do not reuse; replace with SignalPlan and Account decision language |

## Visual Style

Use a quiet professional trading terminal style:

- dark-first interface with a clean light mode option
- small radius cards, around 6-8px
- subtle borders instead of heavy containers
- dense tables for orders, positions, fills, and SignalPlans
- compact stat cards for high-level health
- restrained accent colors
- green for healthy/profit/connected
- red for danger/live/blocked/failure
- amber for warning/stale/manual attention
- blue or cyan for neutral platform action
- purple only for AI, and not as the dominant app theme

Avoid:

- oversized marketing hero sections
- decorative gradients and bokeh effects
- single-hue purple/blue dominance
- hidden controls
- vague labels like Services, Live Monitor, or Paper Runtime
- UI cards nested inside larger decorative cards

## Dashboard Recommendations

The old Dashboard had useful patterns:

- top operator health banner
- KPI card grid
- account equity summary
- active runtime count
- recent results/activity table
- quick action cards
- link arrows on cards that drill into detail

Ultimate Trader Dashboard should show:

- Live Stock Market Data Stream status
- Account Trade Sync summary: connected, stale, down
- number of Accounts
- number of running Deployments
- recent SignalPlans
- open positions
- open orders
- blocked/stale/risk warnings
- global kill state
- latest critical runtime error

Good dashboard cards:

- `Live Stock Data`
- `Account Trade Sync`
- `Accounts`
- `Deployments`
- `Open Positions`
- `Open Orders`
- `Signals Today`
- `Critical Warnings`

Every dashboard card should have a direct drill-in target.

## Account Card Recommendations

Account cards were one of the strongest old UI patterns.

Keep the card density and badge style, but align content to the new Account
model.

Each Account card should show:

- Account name
- broker provider, such as Alpaca
- broker mode, such as paper or live
- credential/validation status
- Account Trade Sync status
- broker sync freshness
- pause/resume state
- equity
- cash
- buying power
- day P&L
- open position count
- open order count
- subscribed Deployment count
- top warnings

Useful badges:

- `Alpaca`
- `Paper`
- `Live`
- `Trade Sync Connected`
- `Trade Sync Down`
- `Sync Fresh`
- `Sync Stale`
- `Paused`
- `Active`
- `Credentials Valid`
- `Needs Credentials`

Account card actions:

- View Account
- Pause Account
- Resume Account
- Refresh Sync
- Explain Account
- Edit Credentials
- Flatten Positions, guarded by confirmation
- Emergency Exit, guarded by stronger confirmation

Danger actions must remain visually distinct and confirmation-gated.

## Account Position Panel Recommendations

The old position table was useful. Keep the density.

Each Account position panel should show:

- symbol
- side
- quantity
- average entry
- current price
- market value
- unrealized P&L
- today P&L
- linked opening SignalPlan
- linked Deployment
- active stop/target/runner/logical-exit status
- related close/reduce SignalPlans received
- sync freshness

Add an action:

- `Explain Position`

This opens an AI-assisted explanation using the canonical position explanation
context. AI is advisory only.

## Providers Page Recommendations

The old Services layout was visually clean: segmented tabs, provider cards,
default badges, key-present badges, validate/test buttons.

Use the same pattern with current names:

- Providers page
- Market Data Providers tab
- AI Providers tab

Do not include Accounts in Providers.

Market Data Provider cards should show:

- provider name
- provider type
- validation status
- default live stock data provider flag
- credentials present/missing
- supported historical/live capabilities
- last validation time
- last error

AI Provider cards should show:

- provider name
- model/default model
- validation status
- credentials present/missing
- advisory-only badge
- last validation time
- last error

Provider actions:

- Add Provider
- Validate
- Set Default
- Edit
- Disable
- Delete, when safe

## Settings Recommendations

The user called out Settings as confusing. Settings should be reduced to platform
preferences, not runtime operations.

Settings should include:

- start Live Stock Market Data Stream on backend startup
- selected default Market Data Provider for live stock data
- selected default AI Provider
- UI theme
- log/export preferences
- operator confirmation preferences

Settings should not include:

- Account pause/resume
- Deployment start/stop
- order actions
- position actions
- stream troubleshooting
- provider credential forms

Runtime controls and troubleshooting belong in Operations, Accounts, or
Providers.

## Operations Recommendations

Operations is where failures must be visible.

Operations should show:

- Live Stock Market Data Stream status
- Account Trade Sync status for every Account
- running Deployments
- recent SignalPlans
- Account decisions
- Governor decisions
- orders
- fills
- positions
- stale states
- stream errors
- broker sync errors

Use status cards and dense tables together:

- cards for current health
- tables for logs, decisions, orders, fills, and SignalPlans

Nothing mission-critical should disappear into console logs.

## Explainer Drawer Pattern

Keep the old `PageHelp` idea, but rewrite all content.

Every major page should have an explainer action that opens a right-side drawer.

The drawer should include:

- what this page does
- where it fits in the Ultimate Trader flow
- key actions
- background logic
- what can fail here
- what the operator should check before trusting it
- copyable context for LLM review

Use current doctrine language:

```text
Strategy -> Deployment -> SignalPlan -> Account Decision -> Governor -> Order -> BrokerSync -> Position
```

Do not mention Program, Account Governor, Services Center, or Paper Runtime as
active concepts.

## Icon Guidance

Prefer lucide icons.

Good icon mappings:

- Dashboard: `Monitor`
- Strategies: `Layers`
- Watchlists: `List`
- Accounts: `Shield`
- Deployments: `Zap`
- Operations: `Activity` or `Radio`
- Providers: `Server`
- Settings: `Settings`
- Market Data: `Database` or `Radio`
- AI Providers: `Brain` or `Sparkles`
- Account Trade Sync: `Wifi`
- Trade Sync Down: `WifiOff`
- Warnings: `AlertTriangle`
- Explain: `Info` or `MessageCircle`
- Credentials: `Key`
- Orders/Trades: `ListChecks` or `ReceiptText`

Buttons should use icons when the action is familiar, with tooltips for less
obvious actions.

## Badge Guidance

Badges should be compact and factual.

Badge examples:

- `Active`
- `Paused`
- `Sync Fresh`
- `Sync Stale`
- `Trade Sync Down`
- `Credentials Valid`
- `Needs Credentials`
- `Default`
- `Advisory Only`
- `Live`
- `Paper`
- `Alpaca`

Avoid badges that imply safety without data. For example, do not show `Safe`
unless the backend has fresh evidence.

## Card Guidance

Cards are appropriate for:

- Account summaries
- provider records
- dashboard KPIs
- Deployment summaries
- stream/sync health panels
- position summaries

Cards should not hide details. Each card should provide:

- current state
- last updated time when relevant
- error state when relevant
- drill-in action
- primary operator action

## Migration Guardrails

Borrow:

- visual rhythm
- cards
- badges
- icons
- compact data tables
- explainer drawer
- validation feedback
- responsive sidebar ideas

Do not borrow:

- Program-centered navigation
- Account Governor page concept
- Services Center naming
- separate paper/live product paths
- old help text
- any UI that implies Deployment executes directly for one Account
