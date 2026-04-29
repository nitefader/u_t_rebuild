# Operation Turtle Shell Handoff Protocol

Purpose: allow any agent to continue Operation Turtle Shell without confusion,
reiteration, or waiting for the previous agent.

If an agent loses context, runs out of time, or is replaced, the next agent must
read this file first, then `OPERATION_STATUS.md`, then
`BACKEND_LOCKDOWN_AGENT_PLAN.md`, then the remaining required control files
listed below.

## Start Order For Any New Agent

1. Read `HANDOFF_PROTOCOL.md`.
2. Read `OPERATION_STATUS.md`.
3. Read `BACKEND_LOCKDOWN_AGENT_PLAN.md`.
4. Read `BACKEND_REALITY_MAP.md`.
5. Read `NEXT_IMPLEMENTATION_SEQUENCE.md`.
6. Read `TURTLE_SHELL_GUARDRAILS.md`.
7. Read `DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`.
8. Read `COORDINATION/PROTOCOL.md`, `COORDINATION/LOCKS.md`, and
   `COORDINATION/INBOX_CODEX.md` (mandatory inter-agent layer; Claude
   parks requests for Codex there and vice versa).
9. Identify which bounded context owns the change.
10. Check the current phase and current task owner.
11. Continue the listed `next_action`.
12. Do not ask the operator to restate the mission.
13. Do not restart from Phase 0 unless the status file says Phase 0 is active.
14. Do not perform frontend work.
15. Do not violate `TURTLE_SHELL_GUARDRAILS.md`.
16. Before ending a turn, refresh leases in `COORDINATION/LOCKS.md`,
    append a line per cross-boundary change to `COORDINATION/LEDGER.md`,
    and answer or close out items in `INBOX_CODEX.md`.

## Required Status Discipline

`OPERATION_STATUS.md` is the executive briefing board.

Every agent must update `OPERATION_STATUS.md` when they start work, while they
work, and before handing off.

An agent may not begin task execution silently.

An agent may not end task execution silently.

If an agent dies halfway through, the status file must still show:

- who started
- what they started
- when they started
- what phase/task they were working on
- what file or module they intended to touch
- what the next expected checkpoint was

The update must include:

- agent name or role
- work session status
- started_at timestamp
- last_heartbeat timestamp
- expected_next_checkpoint
- current phase
- current task
- current owner
- latest completed action
- next action
- files touched
- tests run
- blockers
- decisions made
- approval status
- timestamp

## Work Session Status Values

Use exactly one of these:

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

## Start Update Required

Before touching files or running implementation commands, the agent must update
`OPERATION_STATUS.md`:

```text
Work session status: in_progress
Agent role: Full Stack Developer
Started at: 2026-04-26 19:44:37 -04:00
Current phase: Phase 0: Repo Reality Check
Current task: Backend Reality Map
Expected next checkpoint: backend module inventory draft
```

## Heartbeat Update Required

For longer work, update `last_heartbeat` whenever meaningful progress is made
or before moving to a new subtask.

```text
Last heartbeat: 2026-04-26 20:05:00 -04:00
Latest completed action: inventoried backend/app/brokers and backend/app/orders
Next action: map runtime and simulation modules
```

## End Update Required

Before ending, update:

```text
Work session status: handoff_ready
Ended at: 2026-04-26 20:25:00 -04:00
Latest completed action:
Next action:
Files touched:
Tests run:
Blockers:
Approval status:
```

## Required Date And Time Syntax

All Operation Turtle Shell artifacts must use explicit dates and times.

Do not use vague terms such as:

- today
- tomorrow
- yesterday
- later
- current
- recent
- now

Use these formats:

```text
Date: YYYY-MM-DD
Time: HH:mm:ss
Timezone: UTC offset, for example -04:00
DateTime: YYYY-MM-DD HH:mm:ss -04:00
```

Preferred full timestamp:

```text
2026-04-26 19:42:25 -04:00
```

For date-only approvals:

```text
Approved by Operator
Date: 2026-04-26
```

For handoff updates:

```text
Last updated: 2026-04-26 19:42:25 -04:00
```

For test logs:

```text
Test run: 2026-04-26 19:42:25 -04:00
Command: python -m pytest ...
Result: passed
```

## Handoff Rules

- Continue from the latest accepted phase.
- Do not duplicate work already marked complete.
- Do not rename concepts without Coordinator approval.
- Do not introduce new saved entities unless the Angry Architect approves.
- Do not bypass the final approval gates.
- Treat `TURTLE_SHELL_GUARDRAILS.md` as mandatory architecture law.
- Treat `DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md` as mandatory ownership law.
- Before coding, state which bounded context owns the change in `OPERATION_STATUS.md`
  or the agent work notes.
- If unsure, preserve the current doctrine and add a blocker note.

## Minimum Final Message For Any Agent

Every agent ending a work session must report:

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

## Emergency Recovery

If `OPERATION_STATUS.md` is missing or obviously stale:

1. Re-read `BACKEND_LOCKDOWN_AGENT_PLAN.md`.
2. Re-read `TURTLE_SHELL_GUARDRAILS.md`.
3. Re-read `DOMAIN_DRIVEN_DESIGN_CONSIDERATIONS.md`.
4. Inspect git status.
5. Inspect recent changed files.
6. Recreate `OPERATION_STATUS.md`.
7. Mark confidence as `needs Coordinator review`.

Do not guess silently.
