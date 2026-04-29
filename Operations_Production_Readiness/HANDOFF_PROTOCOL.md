# Operations Production Readiness Handoff Protocol

Purpose: allow any agent to continue this operation cold, without
confusion, repetition, or waiting for the previous agent to be
re-summoned.

This protocol mirrors the discipline of
`Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md`. The two
operations run in parallel and share the same hygiene rules.

## Operation scope

Operations_Production_Readiness owns the **complement** of Operation
Turtle Shell:

- Frontend full redesign (Operation Turtle Shell explicitly bans
  frontend work).
- User-facing CRUD entities the Turtle Shell runtime consumes but
  does not yet expose (Strategies, Watchlists, Deployments) —
  service + persistence + `/api/v1` routes; coordinated with the
  Turtle Shell Coordinator before touching backend files.
- AccountRiskConfig / AccountRestrictions modeled per Account
  (coordinated with Coordinator).
- Position Explain API + AI advisory `explain_position`
  (coordinated with Coordinator).
- Dashboard read-model (server) and dashboard surface (frontend).
- Operator runbook, cutover plan, release plan.
- Cross-doc consistency between the two operations.
- Day Zero rehearsal.

What this operation **does not own**:

- Anything in the backend doctrine spine: runtime, decision
  (SignalEngine, SignalPlanBuilder), orders (OrderManager), governor,
  risk_resolver, brokers, broker_sync, runtime persistence schema
  for already-existing tables, manual-trade route, Account Trade
  Sync runtime, Live Stock Market Data Stream.
- Any change to `backend/app/runtime/`, `backend/app/decision/`,
  `backend/app/orders/`, `backend/app/governor/`,
  `backend/app/risk_resolver/`, `backend/app/brokers/`,
  `backend/app/broker_accounts/` runtime composition,
  `backend/app/pipeline/`, `backend/app/control_plane/`,
  `backend/app/market_data/`, or `backend/app/operations/`
  service internals without Turtle Shell Coordinator approval.

If the slice crosses operations, the Turtle Shell Coordinator wins.
Raise the conflict as a blocker in *both* operations'
`OPERATION_STATUS.md` and wait for Coordinator scheduling.

## Required reading before any work in this operation

Read in this exact order, every time:

1. This file (`HANDOFF_PROTOCOL.md`).
2. `Operations_Production_Readiness/PRODUCTION_READINESS_GUARDRAILS.md`.
3. `Operations_Production_Readiness/OPERATION_STATUS.md`.
4. `Operations_Production_Readiness/README.md`.
5. `Operations_Production_Readiness/CURRENT_STATE_AUDIT.md`.
6. `Operations_Production_Readiness/FRONTEND_STRUCTURE_DECISION.md`.
7. `Operations_Production_Readiness/BACKEND_STRUCTURE_DECISION.md`.
8. `Operations_Production_Readiness/PRODUCTION_READINESS_EXECUTION_PLAN.md`.
9. `Operations_Production_Readiness/AGENT_TASK_MATRIX.md`.
10. `Operations_Production_Readiness/API_AND_READ_MODEL_GAPS.md`.
11. `Operations_Production_Readiness/TESTING_AND_ACCEPTANCE_PLAN.md`.
12. `Operations_Production_Readiness/CUTOVER_AND_RELEASE_PLAN.md`.

If a slice may touch backend code, also read:

- `Operations_Turtle_Shell_Artifacts/HANDOFF_PROTOCOL.md`
- `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
- `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`
- `Operations_Turtle_Shell_Artifacts/DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`
- `Operations_Turtle_Shell_Artifacts/NEXT_IMPLEMENTATION_SEQUENCE.md`

## Required date and time syntax

All timestamps must use explicit absolute date/time with UTC offset.

```text
YYYY-MM-DD HH:mm:ss -04:00
```

Date-only approvals:

```text
YYYY-MM-DD
```

Banned vague terms in artifacts:

- today, tomorrow, yesterday
- later, current, recent, now
- "in a few minutes", "shortly"

## Work session status vocabulary

Use exactly one of these in `OPERATION_STATUS.md`:

```text
not_started
in_progress
blocked
paused_by_operator
failed
completed
handoff_ready
approved
rejected
```

## Start update — required before touching files

Before opening, editing, creating, or running anything, append to
`OPERATION_STATUS.md`:

```text
Work session status: in_progress
Agent role: <Coordinator | Frontend Lead | Backend Coordination | Reviewer | Auditor>
Started at: YYYY-MM-DD HH:mm:ss -04:00
Current phase: <NF.x | S0.y | S1.z | ...>
Current task: <one-line description>
Expected next checkpoint: <one-line description>
```

No exceptions. An agent that begins silently has violated the
protocol.

## Heartbeat update — required during long work

For any session that creates / edits / runs more than once, update:

```text
Last heartbeat: YYYY-MM-DD HH:mm:ss -04:00
Latest completed action: <one-line description>
Next action: <one-line description>
```

When a subtask flips, update before flipping.

## End update — required before stopping

Before ending, append:

```text
Work session status: handoff_ready  (or completed | blocked | failed | paused_by_operator)
Ended at: YYYY-MM-DD HH:mm:ss -04:00
Latest completed action: <one-line description>
Next action: <one-line description>
Files touched: <bullet list of paths>
Tests run: <bullet list of "Command: ...  Result: passed | failed | skipped">
Blockers: <bullet list, or "none">
Decisions made: <bullet list, or "none">
Approval status: <approved | pending operator | pending Coordinator>
```

If credits or context run out mid-slice, the last heartbeat must
already contain enough information for a fresh agent to continue.
That is non-negotiable.

## Minimum final message

Every agent ending a session reports back to the operator with at
least:

```text
Started at:
Ended at:
Current phase:
Completed:
Next action:
Files changed:
Tests run:
Blockers:
Handoff status:
```

## Coordination rules with Operation Turtle Shell

1. If a planned slice touches a file under `backend/app/runtime/`,
   `backend/app/decision/`, `backend/app/orders/`,
   `backend/app/governor/`, `backend/app/risk_resolver/`,
   `backend/app/brokers/`, `backend/app/pipeline/`,
   `backend/app/control_plane/`, `backend/app/operations/service.py`,
   `backend/app/persistence/runtime_store.py` (existing tables),
   `backend/app/market_data/`, or
   `backend/app/broker_accounts/runtime_service.py`, **stop**.
2. Add a coordination note to
   `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md` describing
   the proposed change and the doctrine reason.
3. Wait for the Turtle Shell Coordinator to either schedule the
   slice, take it themselves, or approve it under their guardrails.
4. Do not violate `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`.
5. Frontend work, new top-level CRUD packages
   (`backend/app/strategies/`, `backend/app/watchlists/`,
   `backend/app/deployments/` if they do not yet exist), and new
   API routes that wrap existing runtime contracts may proceed
   under this operation, but the Coordinator must be notified
   before merging.

## Test discipline

After each non-trivial change, run the relevant test target and
record the command + result in `OPERATION_STATUS.md`:

```text
Test run: YYYY-MM-DD HH:mm:ss -04:00
Command: python -m pytest <path> -q
Result: passed
```

Frontend tests:

```text
Test run: YYYY-MM-DD HH:mm:ss -04:00
Command: npm test --prefix frontend  (or new-frontend)
Result: passed
```

Do not proceed if tests fail. Root-cause and fix or document the
failure as a blocker.

## Emergency recovery

If `OPERATION_STATUS.md` is missing, stale, or contradicts the
filesystem:

1. Re-read this protocol.
2. Re-read `README.md` and the decision artifacts.
3. Inspect `git status`, `git log -n 20`.
4. Check `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`
   for any cross-cutting backend changes that have landed since the
   last update.
5. Recreate `OPERATION_STATUS.md` with `Approval status: needs
   operator review` and one explicit blocker noting the recovery.
6. Do not guess silently. Do not delete history. Append.

## Agent end checklist

Before stopping, every agent verifies:

- [ ] OPERATION_STATUS.md start update was made.
- [ ] At least one heartbeat was made during meaningful work.
- [ ] OPERATION_STATUS.md end update is made.
- [ ] Files touched and tests run are listed.
- [ ] Blockers (if any) are listed.
- [ ] Approval status is set.
- [ ] If the slice produced an artifact that affects the other
      operation, a coordination note was added to that operation's
      `OPERATION_STATUS.md`.
- [ ] If banned-name lint or architecture guardrail tests exist
      for the touched area, they were run.
