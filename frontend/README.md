# Ultimate Trader Frontend (new-frontend)

This is the rebuilt operator UI for Ultimate Trader. The legacy
`frontend/` is being retired and will be deleted at the NF.5
cutover; until then the two coexist.

Authority docs:

- [../docs/ULTIMATE_TRADER_MANDATE.md](../docs/ULTIMATE_TRADER_MANDATE.md)
- [../docs/architecture/](../docs/architecture/)
- [../Operations_Production_Readiness/FRONTEND_STRUCTURE_DECISION.md](../Operations_Production_Readiness/FRONTEND_STRUCTURE_DECISION.md)
- [../Operations_Production_Readiness/PRODUCTION_READINESS_GUARDRAILS.md](../Operations_Production_Readiness/PRODUCTION_READINESS_GUARDRAILS.md)

## Stack

- Vite + React 18 + TypeScript (strict)
- Tailwind CSS, theme tokens via CSS variables (dark-first, light alternate)
- Radix UI primitives (Dialog, Popover, Tabs, Toast, Tooltip, DropdownMenu)
- TanStack Query (server state)
- React Router v6 (routing)
- Zustand (client-only state slices)
- Lucide React (icons)
- Zod (schema validation for every API response and WS payload)
- Vitest + React Testing Library (unit + component)
- ESLint + Prettier
- Custom banned-name lint (`scripts/lint-banned-names.mjs`)

## Scripts

```sh
npm install
npm run dev          # http://127.0.0.1:5173 (proxies /api and /ws to 127.0.0.1:8000)
npm run typecheck
npm run lint
npm run lint:names   # banned product-name lint
npm test             # vitest run + banned-name lint
npm run build
npm run preview
```

## Structure

```
src/
  api/            typed clients + Zod schemas; the only place fetch/WS lives
  components/     ui primitives (PulseDot, Card, Banner, Button, …)
  config/         env helpers, API base resolution
  lib/            small utilities (cn, format, idempotency keys)
  routes/         page-level components, one per top-nav surface
  store/          Zustand stores (per-page slices only — no global store)
  styles/         theme tokens + globals.css (Tailwind import + base layer)
  test/           Vitest setup
scripts/
  lint-banned-names.mjs  enforces the doctrine-banned product names
```

## Doctrine summary (read in full from the architecture docs)

- Strategy → Deployment → SignalPlan → Account Evaluation →
  RiskResolver → Governor → Order → BrokerAdapter → BrokerSync →
  Position.
- Paper and live are Account metadata. There is one runtime path.
- The frontend never calls a provider directly. AI, market-data,
  and broker traffic flows through `/api/v1/...` only.
- AI is advisory only.
- No silent failure. No silent success for mission-critical
  actions.
- Banned product names are enforced by lint and documented in the naming contract.
  Use "Ultimate Trader" as the brand.

## Coordination

This frontend is built under
`Operations_Production_Readiness/`. The backend doctrine spine is
owned by Operation Turtle Shell
(`../Operations_Turtle_Shell_Artifacts/`). When a frontend slice
needs a new server boundary, the request is routed through the
Turtle Shell Coordinator before any backend file is touched.
