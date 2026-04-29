# Agent Task Matrix

Maps each agent to the work it should lead. The aim is non-overlapping
ownership with clear hand-offs. All agents read AGENTS.md and are
bound by the Nanyel Coordinator standard.

## Agent profiles

- **Claude** — Doctrine evaluator, plan author, reviewer. Strong at
  long-context architecture review, refactor guidance, doctrine
  enforcement, repo-wide audits, writing artifacts. Average for
  high-throughput mechanical refactor.
- **Codex** — Backend implementer. Strong at multi-file Python
  refactor, schema design, FastAPI routes, pytest authoring, broker
  integration plumbing. The right agent for the runtime spine
  rebuild.
- **Cursor** — Frontend implementer + adjacent backend. Strong at
  vanilla-JS / Vite / DOM rendering and small server changes for
  page support. The right agent for new pages, primitives, and
  glue.
- **VS Code (operator)** — Local dev runs, manual verification, env
  bring-up, paper rehearsal, secrets handling, decision points. Not
  an autonomous agent; the operator drives.

## Ownership table

| Slice | Lead | Reviewer | Notes |
|---|---|---|---|
| S0.1 banned-name lint | Claude | Codex | Test-only, no production code change |
| S0.2 architecture guardrail | Codex | Claude | AST-walking pytest |
| S0.3 OPERATION_STATUS heartbeat | Claude | — | Doc only |
| S1.1 persistence schema additions | Codex | Claude | New tables + indexes |
| S1.2 Strategy / Watchlist services | Codex | Claude | Domain + service + tests |
| S1.3 Deployment service | Codex | Claude | No runtime loop yet |
| S2.1 DeploymentPublisher | Codex | Claude | Doctrine-critical; Plan agent recommended for design draft |
| S2.2 AccountSignalPlanEvaluator | Codex | Claude | Multi-Account fan-out semantics |
| S2.3 RiskResolver Account-driven | Codex | Claude | Replace temporary inputs |
| S2.4 Governor refactor | Codex | Claude | New decision trace shape |
| S2.5 OrderManager SignalPlan entrypoint | Codex | Claude | Legacy ExecutionIntent path removed |
| S3.1 PositionLineage service | Codex | Claude | Truth-source for explanation |
| S3.2 Operations extensions | Codex / Cursor | Claude | API-shaped read-model |
| S4.1 Strategies route | Cursor | Codex | API thin layer |
| S4.2 Watchlists route | Cursor | Codex | API thin layer |
| S4.3 Deployments route | Cursor | Codex | API thin layer |
| S5.1 Account risk-config / restrictions | Cursor | Codex | Reuses existing service patterns |
| S5.2 Position explain + AI advisory | Cursor | Codex | Frontend wiring matters here |
| NF.0 Scaffold new frontend | Cursor | Claude | Operator-approved stack; banned-name lint covers `new-frontend/` |
| NF.1 Operations parity (new frontend) | Cursor | Claude | Lands against existing operations API |
| NF.2 Accounts + Providers + Settings | Cursor | Claude | Inline credentials per memory |
| NF.3 Strategies / Watchlists / Deployments / Components / Dashboard | Cursor | Claude | Each surface gates on its backend read-model |
| NF.3a Dashboard read-model (server) | Codex | Claude | Composed read |
| NF.4 Research surfaces | Codex (APIs) / Cursor (pages) | Claude | Per-surface API gate |
| NF.5 Cutover + delete old `frontend/` | Cursor + Claude review | Operator | Feature parity on nine mandated surfaces; broker-safe E2E green |
| S9.1 Promotion gate refactor | Codex | Claude | Re-key from program_id |
| S9.2 Program → Strategy migration | Codex | Claude | Boot-time migration or refuse-to-start |
| S9.3 Retire Program | Claude (delete approval) + Codex (delete) | Operator | Final cleanup |
| S9.4 Day Zero rehearsal | Claude (audit) + VS Code (operator) | Operator | Paper-account run |

## Best-tool pairing

| Work type | Best tool |
|---|---|
| Repo-wide audit, doctrine review | Claude |
| Write Operations_Production_Readiness/* artifacts | Claude |
| Backend refactor, new services, schema, pytest | Codex |
| FastAPI route authoring, request/response models | Codex |
| Frontend page authoring, vanilla-JS modules, vite-config | Cursor |
| CSS / styles / design tokens | Cursor |
| Local dev bring-up, secrets, paper rehearsal | VS Code (operator) |
| Plan agent (architecture sketches before implementation) | Claude (subagent: Plan) |
| Explore agent (locate files / patterns) | Claude / Codex (subagent: Explore) |
| Lint / type-check enforcement | Codex |
| Frontend lint script | Cursor (author) + Codex (CI hook) |

## Parallelizable

- **Phase 0** slices are independent. Run S0.1, S0.2, S0.3 in
  parallel.
- **Phase 1** S1.2 Strategy and S1.2 Watchlist (treated as a single
  slice but two services) can be worked simultaneously on separate
  branches. They do not share files.
- **Phase 4** routes (S4.1, S4.2, S4.3) can run in parallel after
  Phase 1 lands.
- **Phase 6** frontend rebrand and primitives (S6.1, S6.2) is fully
  parallel to all of Phase 1–5. It only depends on S0.1.
- **Phase 7** pages each gate on their server read-model. Once a
  read-model lands, the page can be built independently of the next
  page.
- **Phase 8** research surfaces are parallel to each other.

## Must wait

- S2.1 DeploymentPublisher cannot start until S1.1, S1.2, S1.3 land.
- S2.2 AccountSignalPlanEvaluator cannot start until S2.1 lands and
  the SignalPlan persistence is real.
- S2.5 OrderManager SignalPlan entrypoint cannot land until S2.4
  Governor refactor lands.
- S3.1 PositionLineage cannot start until S2.5 lands (needs real
  fills tied to SignalPlans).
- S3.2 Operations extensions cannot start until S2.x and S3.1.
- Frontend pages (Phase 7) cannot land green until their server
  read-model exists.
- S9.3 retire Program cannot land until every other slice migrates
  off it.
- S9.4 Day Zero rehearsal is the last gate; it cannot run until
  every other slice is merged.

## What Codex should do first

1. S1.1 — extend persistence schema with the missing tables.
2. S1.2 — Strategy + Watchlist services with full unit-test coverage.
3. S1.3 — Deployment service (definition + lifecycle) without
   publisher yet.
4. Begin S2.1 design (Plan-agent draft ahead of code).

## What Cursor should do first

1. S6.1 — rebrand + rename "Brokers" → "Accounts" + remove "Broker
   Runtime" mode labels.
2. S6.2 — extract UI primitives (badges, cards, tables, drawers,
   forms, statusStrip) used by current pages, no visual regressions.
3. Stub `frontend/src/pages/dashboard.js` with empty-state UI bound
   to a not-yet-implemented dashboard API.

## What Claude should review first

1. Plan documents in this folder, end-to-end consistency.
2. S0.1 banned-name lint — make sure every banned name from
   `NAMING_CONTRACT.md` is enforced.
3. S2.1 DeploymentPublisher design draft — doctrine review before
   Codex writes code (use Plan subagent).
4. S2.4 Governor refactor — verify decision-trace shape matches
   `domain.signal_plan.GovernorDecisionTrace` exactly.
5. S2.5 OrderManager — verify legacy `ExecutionIntent` path is
   removed for non-manual-trade callers.
6. S9.3 Program retirement — final approval before deletion.

## What the operator should approve before implementation begins

1. The decision in [FRONTEND_STRUCTURE_DECISION.md](./FRONTEND_STRUCTURE_DECISION.md):
   refactor + targeted redesign (no SPA rewrite for V1).
2. The decision in [BACKEND_STRUCTURE_DECISION.md](./BACKEND_STRUCTURE_DECISION.md):
   rebuild Program-centric runtime spine; preserve broker / persistence
   / operations / market_data foundations.
3. The slice ordering in [PRODUCTION_READINESS_EXECUTION_PLAN.md](./PRODUCTION_READINESS_EXECUTION_PLAN.md).
4. The first-10 task list and the parallelization strategy in this
   document.
5. The migration policy: refuse-to-start vs migrate-on-boot for any
   persisted Program-style records.
6. The retirement schedule: delete `domain/program.py` and friends in
   S9.3, not before.

## Hand-off rules

- Every slice ends with `OPERATION_STATUS.md` updated by the lead
  agent.
- Every slice opens a PR with the test list run, the doctrine
  decisions made, and a tag of the reviewer.
- A reviewer flag of "doctrine-block" rejects the slice and sends it
  back to the lead with the specific doctrine clause cited.
- "Approval" by Claude requires evidence: tests run, lint passes,
  banned-name lint passes, no regression in any production-ready
  module.
