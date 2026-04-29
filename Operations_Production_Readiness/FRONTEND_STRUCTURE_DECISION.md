# Frontend Structure Decision

## Decision

**Full redesign. Build a new frontend from scratch. The current
`frontend/` is rejected and will be deleted at cutover.**

The existing vanilla-JS Vite multi-page app is not preserved, not
refactored, not partially salvaged. The operator considers it
riddled with bad UX. Per the standing production-grade-only rule, a
patch-on-patch refactor is not the answer — a clean, modern SPA
ships in its final shape.

What carries over: the **`/api/v1/...` API contracts** and the
**doctrine** (naming, ownership, the nine mandated surfaces). What
does not carry over: HTML files, Vite multi-page config,
`frontend/src/*.js` modules, styles, per-page bespoke state,
component shapes, page wiring, frontend tests.

## Rationale

- The old frontend carried banned product names (`Broker Runtime -`r`n  Paper/Live`, `Trading OS`, `Brokers` nav). Active Account mode`r`n  labels must stay plain Paper / Live. The surface still exposes internal
  concepts (`pipelines`, `services`) on operator surfaces, and
  covers only five of the nine mandated surfaces. Fixing those
  in-place is more work than rebuilding.
- Operator memory: production-grade only, every slice ships final
  shape. The fresh build hits final shape in one trajectory; a
  refactor would force a long mid-state.
- Operator stated explicitly that the old frontend is bad UX and
  should not be kept. Continuing on it would override an operator
  veto.
- The backend rebuild lands the canonical doctrine in code
  (DeploymentPublisher, AccountSignalPlanEvaluator, GovernorDecisionTrace,
  PositionLineage). The new frontend should be designed around
  those concepts, not retrofitted to them.

## Stack (proposed — operator approval required)

Modern, boring, well-supported, dense. No experimental choices.

| Layer | Choice | Why |
|---|---|---|
| Build | **Vite 5+** with React plugin | Already in the repo's tooling family; instant HMR; one tool from dev to prod |
| Language | **TypeScript (strict)** | Catch API drift at compile time; doctrine names stay typed |
| UI framework | **React 18+** | Most operator/dev familiarity; deep ecosystem; long-lived |
| Routing | **TanStack Router** (preferred) or React Router v6 | Type-safe route params, file-based or code-based, no surprises |
| Server state | **TanStack Query (React Query)** | The right model for polling, websockets-as-cache-invalidator, retries, error states |
| Client state | **Zustand** (per-store) | Tiny, no providers, fits the "small bespoke state per page" mental model already in the repo |
| Forms | **React Hook Form** + **Zod** | Schema-validated forms; share Zod schemas with API client |
| Styling | **Tailwind CSS** + **CSS variables for theme tokens** | Dark-first, light alternate; tokens lift cleanly to OS-level skinning later |
| Component primitives | **Radix UI primitives** (or **shadcn/ui** sourcing the same) | Accessible by default; unstyled; no lock-in |
| Icons | **Lucide React** | Already named in `docs/architecture/UI_VISUAL_DIRECTION.md` |
| Charts | **lightweight-charts** (TradingView open) for price; **Recharts** for KPIs | Lightweight-charts is the operator-standard for trading; Recharts for everything else |
| Tables | **TanStack Table** | Dense tables for orders, fills, trades, positions, SignalPlans |
| Tests | **Vitest** for unit; **React Testing Library** for component; **Playwright** for E2E | Single test runner family; fits Vite |
| Lint | **ESLint** + **typescript-eslint** + **eslint-plugin-tailwindcss** + **a banned-name rule** | Banned product names fail the build |
| Format | **Prettier** | One source of truth on formatting |
| Date/time | **Temporal (polyfill)** or **date-fns** | Trading needs trustable time math |
| WebSockets | **native `WebSocket`** wrapped in a typed hook | No new dependency; predictable lifecycle |

If the operator wants a tighter scope: drop TanStack Router for
React Router v6; drop shadcn/ui and use Radix directly; drop
Recharts and ship trading charts only. The minimum viable stack is
React + TypeScript + Vite + Tailwind + Radix + TanStack Query +
Zustand + lightweight-charts + Vitest + Playwright.

If the operator prefers a different framework family — Svelte/SvelteKit,
Vue 3 + Pinia + Vite, or SolidJS — say the word; the architecture
in this doc is framework-agnostic and translates directly.

## Visual direction (from `docs/architecture/UI_VISUAL_DIRECTION.md`)

- Dark-first interface; clean light mode option.
- Quiet, professional trading-terminal aesthetic. No marketing
  hero sections, no decorative gradients, no dominant single-hue
  purple/blue.
- Compact cards (~6–8px radius), subtle borders, dense tables.
- Color semantics: green=healthy/profit/connected,
  red=danger/live/blocked/failure, amber=warning/stale/manual
  attention, blue/cyan=neutral platform action, purple=AI only and
  never the dominant theme.
- Right-side explainer drawer pattern on every major page.
- Lucide icons as the icon set.
- Theme tokens live in CSS variables consumed by Tailwind.

## Design language — concepts the new SPA implements

Concrete patterns the new build owes the operator. These are not
"reuse the old code"; they are the design language the new
components encode from day one.

### Badges (`components/badges/`)

Compact, factual, never decorative. Color follows the semantic
palette above. Banned: `Safe` or any badge that asserts safety
without backing data.

```
Active            Paused            Stopped
Sync Fresh        Sync Stale        Trade Sync Down
Credentials Valid Needs Credentials
Default           Advisory Only
Live              Paper             Alpaca
Connected         Authenticated     Reconnecting
```

### Status strips

A one-line band that sits at the top of long-running surfaces
(Operations, Account detail, Deployment detail). Shows: last
updated, connection state, stale state, halted state, active
state. Never a tooltip-only signal — always visible.

### KPI cards

Dense, drill-in-able tiles for the Dashboard.

```
Live Stock Data            Account Trade Sync
Accounts                   Deployments
Open Positions             Open Orders
Signals Today              Critical Warnings
```

Each card shows current state, last-updated when relevant, error
state when relevant, a primary operator action, and a link arrow
to the detail surface.

### Account card

The strongest pattern from `UI_VISUAL_DIRECTION.md`. One card per
Account on the Accounts list and embedded on the Dashboard.

Content:

- Account name
- Broker provider (e.g. Alpaca)
- Broker mode (Paper / Live)
- Credential / validation status
- Account Trade Sync status
- Broker sync freshness
- Pause / resume state
- Equity, cash, buying power, day P&L
- Open position count, open order count, subscribed deployment
  count
- Top warnings

Actions on the card itself (no separate page jump for routine
work):

```
View Account     Pause Account     Resume Account
Refresh Sync     Explain Account   Edit Credentials
Flatten Positions      (confirm)
Emergency Exit         (stronger confirm)
```

### Account position panel

For each open Position on an Account:

- Symbol, side, quantity, average entry, current price, market
  value
- Unrealized P&L, today P&L
- Linked opening SignalPlan
- Linked Deployment
- Active stop / target / runner / logical-exit status
- Related close / reduce SignalPlans received
- Sync freshness
- `Explain Position` action — opens the right-side explainer
  drawer with the canonical `PositionExplanationContext` plus AI
  advisory summary (advisory only, copyable).

### Provider cards

Market Data Providers tab: provider name, type, validation status,
default-live-stock-data flag, credentials present/missing,
supported historical/live capabilities, last validation time, last
error.

AI Providers tab: provider name, model / default model, validation
status, credentials present/missing, advisory-only badge, last
validation time, last error.

Provider actions inline on the card:

```
Add Provider     Validate     Set Default
Edit             Disable      Delete (when safe)
```

### Deployment card

For each Deployment on the Deployments list and embedded on the
Dashboard:

- Deployment name, Strategy version label
- Status (Active, Paused, Stopped, Blocked, Error)
- Subscribed Account count
- Recent SignalPlan count and timestamp
- Open positions originated by this Deployment
- Top warning / error
- Actions: View, Start, Pause, Resume, Flatten

### Risk card

Per Account, surfaces the operator's risk posture in one place
(see [API_AND_READ_MODEL_GAPS.md](./API_AND_READ_MODEL_GAPS.md)
"Risk Cards"):

- Sizing rules (method, risk per trade, fixed shares / dollar)
- Max position size, max concentration
- Max daily loss, max drawdown
- Symbol blocklist, asset blocks, time-of-day blocks
- Current exposure projection (gross, net, by symbol, open risk)
- Governor policy snapshot

### Danger confirmations

Type-name-to-confirm pattern for any action that creates or
removes broker risk:

- Live account creation → type the display name
- Flatten Account / Flatten Deployment → type the target name
- Emergency Exit → type the target name + check a danger
  acknowledgement
- Delete Account / Delete Deployment → type the target name
- Global Kill → single-step but a separate confirm dialog with the
  reason captured

The Danger primitive returns a Promise that resolves only when the
operator typed the exact name.

### Explainer drawer

A right-side drawer present on every major page, opened by an
`Info` button in the page header.

Drawer content per page:

- What this page does
- Where it fits in the Ultimate Trader flow
- Key actions
- Background logic
- What can fail here
- What the operator should check before trusting it
- Copyable context for LLM review

Drawer language uses current doctrine names only:

```
Strategy → Deployment → SignalPlan → Account Decision → Governor → Order → BrokerSync → Position
```

The drawer never references Program, Account Governor, Services
Center, or Paper Runtime as active concepts.

### Color semantics

| Color | Use |
|---|---|
| Green | Healthy / profit / connected |
| Red | Danger / live mode / blocked / failure |
| Amber | Warning / stale / manual attention |
| Blue / cyan | Neutral platform action |
| Purple | AI only — never the dominant theme |

### Icon mapping (Lucide)

| Concept | Icon |
|---|---|
| Dashboard | `Monitor` |
| Strategies | `Layers` |
| Watchlists | `List` |
| Accounts | `Shield` |
| Deployments | `Zap` |
| Operations | `Activity` or `Radio` |
| Providers | `Server` |
| Settings | `Settings` |
| Market Data | `Database` or `Radio` |
| AI Providers | `Brain` or `Sparkles` |
| Account Trade Sync | `Wifi` |
| Trade Sync Down | `WifiOff` |
| Warnings | `AlertTriangle` |
| Explain | `Info` or `MessageCircle` |
| Credentials | `Key` |
| Orders / Trades | `ListChecks` or `ReceiptText` |

### Card guidance

Every card surfaces:

- Current state
- Last updated timestamp when relevant
- Error state when relevant
- A drill-in action
- A primary operator action

Cards never hide the things that matter. No nested decorative
containers, no "click to reveal" patterns for mission-critical
state.

### Live indicators — pulsing lights (`components/ui/PulseDot.tsx`)

Small filled dots that *pulse* when the underlying signal is alive.
The pulse is a 1.4s ease-in-out scale + opacity animation. The dot
is matte (no glow) when paused, solid when error, animated when
live.

| Indicator | When | Color |
|---|---|---|
| Live Stock Data running | Hub `is_running=true` and `last_message_at < 10s ago` | Green pulse |
| Live Stock Data stale | `last_message_at` older than threshold | Amber pulse |
| Live Stock Data down | Hub not running | Red, no pulse |
| Account Trade Sync connected | Dispatcher `is_running=true` | Green pulse |
| Account Trade Sync down | Dispatcher not running | Red, no pulse |
| Trade Sync credentials invalid | `state == CREDENTIALS_INVALID` | Red, no pulse |
| Trade Sync paused by operator | `state == OPERATOR_PAUSED` | Amber, no pulse |
| Deployment running | `status == RUNNING` and last bar < 1 min | Green pulse |
| Deployment blocked | `status == BLOCKED` | Red, no pulse |
| New SignalPlan published in last 60s | per-row indicator on SignalPlans table | Cyan single-flash (one pulse) |
| Order in flight | Pending broker submission | Cyan pulse |
| Filling order | Partial fills landing | Green pulse |

Pulse animation respects `prefers-reduced-motion` (replaced by a
static dot with the same color semantics).

### Wifi-signal icons (`components/badges/SyncSignal.tsx`)

For Account Trade Sync, broker streams, and live market data, render
a wifi-style glyph (Lucide `Wifi`, `WifiOff`, `WifiHigh`, `WifiLow`)
that encodes connection state at a glance:

| State | Glyph | Color | Pulse |
|---|---|---|---|
| Connected, fresh events | `Wifi` (full) | Green | Yes |
| Connected, idle but ok | `Wifi` (full) | Green | No |
| Reconnecting | `WifiLow` | Amber | Yes |
| Stale | `Wifi` (full) | Amber | No |
| Down | `WifiOff` | Red | No |
| Credentials invalid | `WifiOff` | Red | No |
| Paused by operator | `WifiOff` | Slate | No |

Glyph and pulse must be in sync. A green pulsing wifi means the
operator can trust the stream; anything else is a flag.

### Dense cards (`components/cards/`)

Information density is a feature, not a bug. Each operator card
fits as much factual state as readable in one card without nested
sub-cards. Density rules:

- One row of badges across the top right (`Live`, `Paper`,
  `Alpaca`, `Active`, `Sync Fresh`, etc.).
- One block of KPIs in a 2- or 3-column grid (equity, cash, BP, day
  P&L; or equivalent).
- One block of counts (open positions, open orders, deployments).
- One row of pulsing indicators with wifi-state glyphs (Trade Sync,
  Live Stock Data, Deployment runtime).
- One row of action buttons inline on the card.
- One subtle line for "last updated" + the most important warning
  if any.

Cards do not get taller to make space — they get denser. Whitespace
is in the margins, not the content.

### Alerts (`components/ui/Alert.tsx`, `components/ui/Banner.tsx`, `components/ui/Toast.tsx`)

Three flavors, never silent:

- **Banner** — stays on the page for the lifetime of the condition.
  Used for Operations-wide states: global kill active, Live Stock
  Data down, all Account Trade Syncs down, system-recovery in
  progress. Color follows severity.
- **Alert** — stays on the section it owns. Used for per-card or
  per-section states: Account paused, Deployment blocked,
  credentials needed, broker sync stale.
- **Toast** — transient, action-acknowledgement only. Used for
  "manual order submitted", "settings saved", "account flattened".
  Toasts disappear after 6s or on click. Toasts never carry
  mission-critical state — that goes to a Banner or Alert.

Severity palette: `danger` (red), `warning` (amber), `info` (blue),
`success` (green). No `neutral` — every alert states why it
exists.

### Slideouts (`components/drawers/`)

Right-side panels that open over the current page without
navigating away. The operator stays in context.

| Slideout | Trigger |
|---|---|
| **ExplainerDrawer** | `Info` button in page header — page-level help, copyable for LLM review |
| **PositionExplainDrawer** | `Explain Position` from any position row — canonical `PositionExplanationContext` + AI advisory summary, copyable |
| **SignalPlanDrawer** | Click a SignalPlan row — full lineage, related plans, Account decisions across all subscribed Accounts |
| **AccountEvaluationDrawer** | Click an evaluation row — risk resolver result, governor decision trace, rejection reasons |
| **OrderDrawer** | Click an order row — internal lineage, broker mapping, fills timeline, cancel action when valid |
| **CredentialsDrawer** | `Edit Credentials` from a card — masked inline editor (per `feedback_credentials_inline_on_cards` memory) |
| **DangerConfirmDrawer** | Type-name-to-confirm flows that need more context than a modal |

Slideouts:

- Open with a 200ms slide-in transition; close with the same out.
- Trap focus while open; close on `Esc`.
- Are stateless — they read from TanStack Query, they don't store
  page-mutated state.
- Have a `Copy context` button on every explanation panel that
  drops a markdown blob to the clipboard for LLM review.

### What the design language explicitly bans

- Marketing hero sections, decorative gradients, bokeh effects
- Single-hue purple/blue dominance
- Hidden controls / overflow menus that bury mission-critical
  actions
- Vague labels (`Services`, `Live Monitor`, `Paper Runtime`)
- Cards nested inside larger decorative cards
- Badges that imply safety without backing data
- Long marketing copy on operator pages

## Target route map (V1)

The mandated nav (see `docs/architecture/OPERATOR_EXPERIENCE.md`)
maps to nine top-level routes plus drill-ins. SPA routes, no full
page reloads.

```
/                        Dashboard (operator home)
/strategies              Strategies list
/strategies/:id          Strategy editor (versions, rules, freeze)
/components              Components catalog
/watchlists              Watchlists list
/watchlists/:id          Watchlist editor (static + dynamic rules)
/accounts                Accounts list
/accounts/:id            Account detail (cards, risk config, positions, orders)
/deployments             Deployments list
/deployments/:id         Deployment detail (subscribed accounts, recent SignalPlans, runtime)
/operations              Operations Center (runtime panels, decisions, kill, pause)
/operations/positions/:lineage_id   Position explanation drawer (also a global modal)
/providers               Providers (Market Data + AI tabs)
/settings                Settings (platform preferences only)
/research/chart-lab      Chart Lab (drill-in)
/research/sim-lab        Sim Lab (drill-in)
/research/backtests      Backtests list + detail
/research/optimization   Optimization runs
/research/walk-forward   Walk-Forward runs
```

`Position Explain`, `SignalPlan detail`, `Order detail`, `Trade
detail`, `Account credentials editor`, `Provider validation` are
right-side drawers/modals — not separate routes — to stay in
operator context.

## Target component hierarchy

```
new-frontend/
  index.html
  vite.config.ts
  tsconfig.json
  tailwind.config.ts
  postcss.config.js
  .eslintrc.cjs
  src/
    main.tsx                    (root + router + query client + theme)
    routes/                     (TanStack/React-Router route tree)
      _layout.tsx               (top nav, status badge, explainer drawer slot)
      index.tsx                 (Dashboard)
      strategies/
      components/
      watchlists/
      accounts/
      deployments/
      operations/
      providers/
      settings/
      research/
        chart-lab/
        sim-lab/
        backtests/
        optimization/
        walk-forward/
    api/                        (typed clients per backend boundary)
      client.ts                 (fetch wrapper, X-UTOS-API-Key, error handling)
      ws.ts                     (typed WebSocket hook)
      schemas/                  (Zod schemas mirroring backend Pydantic models)
      strategies.ts
      watchlists.ts
      deployments.ts
      signalPlans.ts
      accounts.ts
      governor.ts
      positions.ts
      operations.ts
      providers.ts
      systemSettings.ts
      systemStreams.ts
      chartLab.ts
      simLab.ts
      backtests.ts
      optimization.ts
      walkForward.ts
      promotion.ts
      ai.ts
      dashboard.ts
    hooks/                      (TanStack Query wrappers; useAccount, useDeployment, useSignalPlanFeed, useTradeStream, ...)
    stores/                     (Zustand stores: useAppShell, useExplainerDrawer, useDangerConfirm)
    components/                 (presentational primitives)
      ui/                       (Radix wrappers — Button, Dialog, Drawer, Tabs, Toast, Tooltip, Popover, ...)
      badges/                   (StatusBadge, ModeBadge, SyncBadge, AdvisoryBadge)
      cards/                    (Card, KpiCard, AccountCard, DeploymentCard, ProviderCard, PositionCard, RiskCard)
      tables/                   (DenseTable, OrdersTable, FillsTable, PositionsTable, SignalPlansTable, EvaluationsTable, GovernorDecisionsTable)
      charts/                   (PriceChart, EquityChart, ExposureChart)
      forms/                    (FormField, MaskedSecret, ProviderModeSelect, RiskConfigForm, WatchlistEditor, StrategyEditor)
      drawers/                  (ExplainerDrawer, PositionExplainDrawer, SignalPlanDrawer, OrderDrawer)
      empty/                    (EmptyState, LoadingState, ErrorState)
    lib/                        (utilities — formatTimestamp, formatPnl, idempotencyKey, lineage links)
    styles/                     (globals.css, theme.css with CSS variables)
    config/                     (apiBase, wsBase, env helpers — same surface as old frontend's config.js)
    test/                       (vitest setup, RTL render helper)
  tests/
    unit/                       (Vitest)
    component/                  (RTL)
    e2e/                        (Playwright — broker-safe; gated behind env)
```

## State management plan

- **Server state** lives in TanStack Query. Every API call gets a
  query key matching its boundary (`["deployments", deploymentId]`,
  `["operations", "overview"]`, `["accounts", id, "positions"]`).
- **WebSocket events** invalidate query keys. The trade stream and
  the SignalPlan stream are sources of cache invalidation, not
  state. UI reads come from the cache.
- **Client state** is per-page Zustand stores plus a thin
  `useAppShell` for cross-page concerns (system status, explainer
  drawer slot, current Account selection if global).
- **No Redux**, no Context-as-state. Form state lives in React Hook
  Form. Theme/dark-mode lives in a Zustand store with localStorage
  persistence.
- **Idempotency keys** are generated client-side for every
  operator-initiated mutation that creates broker risk: manual
  trade, flatten, deployment-start, account-resume.
- **Optimistic updates** are off by default for mission-critical
  actions. The UI shows a pending state and waits for the server's
  durable acknowledgement.

## API integration plan

- Every endpoint has a typed Zod schema in `src/api/schemas/`.
  Mismatches between backend response and schema fail loudly in
  dev and warn in prod.
- A single `client.ts` injects `X-UTOS-API-Key` (when configured)
  and the JSON content-type, and surfaces operator-readable
  errors. No silent error swallowing.
- The frontend never calls a provider directly. All AI, market-data,
  and broker traffic flows through `/api/v1/...`.
- WebSockets live behind a `useWS<TPayload>(url, opts)` hook that
  manages reconnect, last-event-at, and exposes a Zod-decoded
  payload. Closing a tab does **not** drop the broker connection
  (the backend already owns that).
- Banned response field names (per
  [API_AND_READ_MODEL_GAPS.md](./API_AND_READ_MODEL_GAPS.md))
  fail Zod schema validation; the build fails if any new endpoint
  introduces them.

## Migration plan (old → new)

The new frontend is built in a separate folder and shipped as the
operator's frontend at cutover. The old `frontend/` continues to
run *only* during the build window so paper-runtime smoke stays
green; it is deleted on the day the new frontend reaches feature
parity on the nine mandated surfaces.

Phase NF.0 — scaffold (1 day):

1. Create `new-frontend/` next to `frontend/`. Pin stack versions.
2. Wire Vite + Vitest + Playwright + Tailwind + Radix + TanStack
   Query + Router + Zustand + Lucide + lightweight-charts.
3. Theme tokens (CSS variables); dark-first, light alternate.
4. App shell: top nav, system status badge, explainer drawer slot,
   right-side toast region.
5. Typed API `client.ts` and `ws.ts` skeleton.
6. CI pipeline runs unit + component + (broker-safe-gated) E2E.

Phase NF.1 — Operations parity (2 days):

7. Operations route + hooks against `/api/v1/operations/overview`,
   `/accounts/{id}`, `/deployments/{id}`, `/orders/{id}`.
8. System Streams panel against `/api/v1/system/streams`.
9. Trade Stream panel against `/ws/operations/trade-stream`.
10. Global kill / pause / resume / flatten actions with
    type-name-to-confirm Danger primitives.
11. Result: new Operations is on par with old Operations, plus the
    Position Explain drawer scaffold.

Phase NF.2 — Accounts and Providers (2 days):

12. Accounts list + detail with inline credential editor (per
    `feedback_credentials_inline_on_cards` memory).
13. Providers (Market Data + AI tabs) with provider cards, inline
    credential editor, validate / set-default / disable / delete.
14. Settings (platform preferences only — no runtime controls).

Phase NF.3 — Mandated new surfaces (3 days):

15. Strategies list + editor against new `/api/v1/strategies` API.
16. Watchlists list + editor against new `/api/v1/watchlists` API.
17. Deployments list + detail against new `/api/v1/deployments`
    API; subscribed Accounts; recent SignalPlans; runtime status.
18. Components catalog.
19. Dashboard (driven by `/api/v1/dashboard/summary`).

Phase NF.4 — Research surfaces (2 days):

20. Chart Lab (against existing chart-lab API).
21. Sim Lab, Backtests, Optimization, Walk-Forward (against new
    research APIs).

Phase NF.5 — Cutover (0.5 day):

22. Flip the operator's bookmark / static-host root to the new
    frontend.
23. Remove the old `frontend/` from the repo and the build. Update
    `vite.config.js` references in scripts, docs, and CI to point
    at `new-frontend/`. Rename `new-frontend/` → `frontend/` once
    the old one is gone.

Every phase is its own PR. Every phase ships in production-grade
shape (typed, tested, accessible, dark-first, banned-name-clean) —
no stub pages.

## What this does *not* do

- It does not introduce a separate paper-mode frontend.
- It does not call providers directly from the frontend.
- It does not add a backend-for-frontend proxy. The existing
  `/api/v1/...` is the contract.
- It does not rebuild the backend. Backend doctrine work proceeds
  per [BACKEND_STRUCTURE_DECISION.md](./BACKEND_STRUCTURE_DECISION.md);
  the new frontend consumes whatever surfaces are live and shows
  empty-states cleanly for the rest until they land.
- It does not preserve, archive, or fork any part of the existing
  `frontend/`. It is deleted at NF.5.

## Tests

- Vitest for utilities, hooks, Zod schemas, formatters.
- React Testing Library for components and pages — every page tests
  empty / happy / degraded server states.
- Playwright for broker-safe E2E flows; gated behind
  `UTOS_BROKER_SAFE_E2E=1`; runs against Alpaca paper or fakepaca.
- ESLint custom rule fails the build on banned product names in
  source files (Program, Account Governor, Services Center, Paper
  Runtime, Live Runtime, Trading OS as a brand, Brokers as a nav
  label, Broker Runtime · Paper/Live).
- Type-check (`tsc --noEmit`) is a CI gate.

## Operator approval required

Before NF.0 starts, the operator decides:

- [ ] Stack: React + TypeScript + Vite + Tailwind + Radix +
      TanStack Query + Router + Zustand + lightweight-charts +
      Lucide + Vitest + Playwright. **Approve / change / minimum-stack.**
- [ ] Old `frontend/` deletion: schedule deletion at NF.5 (when
      new frontend hits parity), not earlier. **Approve.**
- [ ] Folder convention: build in `new-frontend/` and rename to
      `frontend/` after deletion. **Approve / suggest different name.**
- [ ] Phase order: Operations parity first, then Accounts/Providers,
      then mandated new surfaces, then research. **Approve / reorder.**
- [ ] Cutover criterion: feature parity on the nine mandated
      surfaces is the gate, not "everything in the old app".
      **Approve.**
