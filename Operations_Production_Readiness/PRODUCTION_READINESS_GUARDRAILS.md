# Production Readiness Guardrails

Operation: Operations Production Readiness
Purpose: prevent drift while agents implement the frontend full
redesign and the user-facing CRUD layer that wraps the Operation
Turtle Shell backend doctrine spine.

## Prime Directive

Ship Ultimate Trader to production-grade operator readiness on the
nine mandated surfaces:

```text
Dashboard
Strategies
Components
Watchlists
Accounts
Deployments
Operations
Providers
Settings
```

If a change does not strengthen one of those surfaces or the
cross-cutting operator runbook, stop and document it as a blocker.

## Non-Negotiable Rules

1. No silent start. No silent end. Update
   [OPERATION_STATUS.md](./OPERATION_STATUS.md) at start, heartbeat,
   and handoff using the discipline in
   [HANDOFF_PROTOCOL.md](./HANDOFF_PROTOCOL.md).
2. No vague timestamps. Use `YYYY-MM-DD HH:mm:ss -04:00`.
3. No backend doctrine spine work. Operation Turtle Shell owns
   `backend/app/runtime/`, `backend/app/decision/`,
   `backend/app/orders/`, `backend/app/governor/`,
   `backend/app/risk_resolver/`, `backend/app/brokers/`,
   `backend/app/pipeline/`, `backend/app/control_plane/`,
   `backend/app/operations/service.py`,
   `backend/app/market_data/`,
   `backend/app/persistence/runtime_store.py`,
   `backend/app/broker_accounts/runtime_service.py`. Coordinate
   any change there with the Turtle Shell Coordinator first.
4. No preserve / refactor of the old `frontend/`. The redesign
   ships in `new-frontend/` and the old one is deleted at NF.5
   per [FRONTEND_STRUCTURE_DECISION.md](./FRONTEND_STRUCTURE_DECISION.md).
5. No banned product names in any active source under
   `backend/app/` or `new-frontend/`: Program, Account Governor,
   Services Center, Paper Runtime, Live Runtime, Strategy Account,
   Broker SubAccount, Market Data Service Center, Trading OS
   (as user-visible brand). Banned-name lints
   (`backend/tests/unit/lint/test_no_banned_product_names.py` and
   the to-be-added frontend lint script) enforce this.
6. No direct provider call from the frontend. AI, market-data,
   and broker traffic always flows through `/api/v1/...`.
7. No AI mutation of broker, order, trade, or position truth. AI
   is advisory only; the only AI surface is `Explain this
   position` and similar advisory copy.
8. No silent failure on mission-critical actions. Trade Sync
   down, Live Stock Market Data Stream down, BrokerSync stale,
   manual order rejected, deployment start failed — all must be
   operator-visible via Banner / Alert / Toast per the design
   language.
9. No silent success on mission-critical actions. A manual order
   submit, a flatten, a deployment start, an account resume must
   all show evidence of broker / system acceptance, not just an
   internal "accepted=true".
10. No new top-level CRUD package in `backend/app/` (e.g.
    `backend/app/strategies/`, `backend/app/watchlists/`,
    `backend/app/deployments/`) without explicit Turtle Shell
    Coordinator approval, even though those entities are this
    operation's territory. The runtime spine consumes their
    shapes; the Coordinator must confirm the timing.
11. No new persistence table without Turtle Shell Coordinator
    approval. Persistence schema is shared.
12. No new API route under `/api/v1/` without coordinating with
    the Coordinator first.
13. No second runtime root, no separate paper / live runtime
    path, no per-Deployment runtime composition root.

## Frontend Build Rules

1. Stack as approved in
   [FRONTEND_STRUCTURE_DECISION.md](./FRONTEND_STRUCTURE_DECISION.md).
   Pin versions in `new-frontend/package.json`.
2. TypeScript strict. `tsc --noEmit` is a CI gate.
3. Tailwind + Radix + Lucide. No competing design systems.
4. Server state in TanStack Query. Client state in Zustand. No
   Redux. No Context-as-state.
5. Idempotency keys generated client-side for every operator
   mutation that creates broker risk.
6. No direct fetch in components. Every API call goes through
   `src/api/client.ts` so `X-UTOS-API-Key`, error handling, and
   schema validation are centralized.
7. WebSockets close on unmount; the backend keeps the broker
   connection open.
8. Dark-first interface. Light alternate via theme tokens.
9. Accessibility: keyboard navigation, focus traps in slideouts,
   `prefers-reduced-motion` respected by pulse animations,
   semantic HTML, ARIA where Radix doesn't cover it.
10. Banned-name lint runs in `npm test`.

## Coordination Rules

1. Read
   [HANDOFF_PROTOCOL.md](./HANDOFF_PROTOCOL.md) before any work.
2. If the slice may touch backend code under the doctrine spine,
   also read
   [../Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md](../Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md),
   [OPERATION_STATUS.md](../Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md),
   and
   [TURTLE_SHELL_GUARDRAILS.md](../Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md).
3. Identify the bounded context that owns the change before
   coding.
4. If ownership is ambiguous, stop and document as a blocker in
   `OPERATION_STATUS.md`.
5. The Turtle Shell Coordinator wins on backend doctrine
   disputes.

## Test Discipline

After each non-trivial change:

- Backend lint: `python -m pytest backend/tests/unit/lint -q`
- Backend full unit (when shared models changed):
  `python -m pytest backend/tests/unit -q`
- Frontend (new-frontend, when it exists):
  `npm test --prefix new-frontend`
- Type-check: `npm run typecheck --prefix new-frontend`
- Banned-name lint frontend (when added):
  `node new-frontend/scripts/lint-banned-names.mjs`

Record the command and result in `OPERATION_STATUS.md` per
HANDOFF_PROTOCOL discipline.

Do not proceed if any test fails. Root-cause and fix or document
as a blocker.

## Banned User-Visible Strings

The new frontend must not emit any of these strings to the
operator or to any HTTP response payload it consumes:

```text
Trading OS              (brand)
Brokers                 (nav label — use "Accounts")
Broker Runtime · Paper  (mode label — use "Paper")
Broker Runtime · Live   (mode label — use "Live")
Account Governor
Services Center
Paper Runtime
Live Runtime
Deployment per Account
Strategy Account
Broker SubAccount
Market Data Service Center
```

The frontend banned-name lint enforces this. Any matching string
fails the build.

## Visual Bans

- Marketing hero sections, decorative gradients, bokeh
- Single-hue purple/blue dominance
- Hidden controls / overflow menus burying mission-critical
  actions
- Cards nested inside larger decorative cards
- Badges that imply safety without backing data (no `Safe`)
- Long marketing copy on operator pages

## Slice Quality Bar (every PR)

- Banned-name lint clean
- Architecture import guardrail clean
- Type-check clean (TS) and pytest clean (Python)
- Frontend tests cover empty / happy / degraded states for any
  new page
- API integration: response models validated by Zod schemas in
  `new-frontend/src/api/schemas/`
- OPERATION_STATUS.md updated with start, heartbeat, end,
  files touched, tests run, blockers, decisions, approval status
- If the slice touches backend, a coordination note is added to
  `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md` (when
  the Coordinator opens that loop) or a coordination ask is
  raised in this operation's `OPERATION_STATUS.md` and the slice
  pauses

## Final Warning

Do not start silently.

Do not end silently.

Do not modify the backend doctrine spine without Turtle Shell
Coordinator approval.

Do not preserve or partially salvage the old `frontend/`.

Do not introduce banned product names anywhere user-visible.

Do not let mission-critical failures hide.

Build the operator surface that the Turtle Shell backend deserves.
