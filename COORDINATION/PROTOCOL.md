# Inter-Agent Coordination Protocol

Two agents are working the Ultimate Trader rebuild in parallel:

- **Codex** — owns Operation Turtle Shell (backend doctrine spine).
  Status board: `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`.
- **Claude** — owns Operation Production Readiness (frontend + cross-cutting).
  Status board: `Operations_Production_Readiness/OPERATION_STATUS.md`.

Both agents already follow the Turtle Shell `HANDOFF_PROTOCOL.md` hygiene
(absolute timestamps, work-session-status vocabulary, start/heartbeat/end
updates). This protocol sits on top of that and adds an asynchronous
mailbox + lock layer so the two agents don't step on each other.

Last updated: 2026-04-27 13:35:00 -04:00

---

## Read-On-Every-Turn Files

Both agents must read these at the start of every turn before touching code:

1. `COORDINATION/LOCKS.md` — who has a lease on which path right now.
2. `COORDINATION/INBOX_<SELF>.md` — pending requests/answers from the other agent.
3. Their own `OPERATION_STATUS.md` (board of record for their operation).

Both agents must write to these at the end of every turn that touched
shared state:

1. `COORDINATION/LOCKS.md` — release any lease that is now done; refresh TTL on any still-held lease.
2. `COORDINATION/INBOX_<OTHER>.md` — append any new request, ack, or answer for the other agent.
3. `COORDINATION/LEDGER.md` — append a one-line entry for any change that crosses the operation boundary (frontend ↔ backend).
4. Their own `OPERATION_STATUS.md` heartbeat.

---

## Path Ownership Baseline

Default ownership — the owner is the only agent that may write without an explicit hand-off.

| Path                                                       | Owner   |
| ---------------------------------------------------------- | ------- |
| `backend/app/operations/`                                  | Codex   |
| `backend/app/runtime/`                                     | Codex   |
| `backend/app/strategies/`                                  | Codex   |
| `backend/app/deployments/`                                 | Codex   |
| `backend/app/signal_planner/`                              | Codex   |
| `backend/app/risk/`                                        | Codex   |
| `backend/app/governor/`                                    | Codex   |
| `backend/app/evaluator/`                                   | Codex   |
| `backend/app/brokers/`                                     | Codex   |
| `backend/app/orders/`                                      | Codex   |
| `backend/app/positions/`                                   | Codex   |
| `backend/app/position_lineage/`                            | Codex   |
| `backend/app/research/`                                    | Codex   |
| `backend/app/api/routes/` (route registration)             | Codex   |
| `backend/migrations/`                                      | Codex   |
| `backend/tests/unit/{operations,runtime,strategies,...}/`  | Codex   |
| `Operations_Turtle_Shell_Artifacts/`                       | Codex   |
| `frontend/`                                                | Claude  |
| `frontend/src/api/` (typed client + zod schemas)           | Claude  |
| `frontend/src/routes/`                                     | Claude  |
| `frontend/src/components/`                                 | Claude  |
| `frontend/tests/`                                          | Claude  |
| `Operations_Production_Readiness/`                         | Claude  |
| `backend/tests/unit/api/test_frontend_api_contract.py`     | Claude  |
| `backend/tests/unit/lint/test_no_banned_product_names.py`  | Claude  |
| `scripts/` (frontend tooling), `tools/` (cross-cutting)    | shared  |
| `AGENTS.md`                                                | shared  |
| `package.json`, root configs                               | shared  |

A `shared` path requires a lease in `LOCKS.md` before edit.

If an agent needs to edit a path it does not own, it must:

1. Open a `request` in the other agent's inbox.
2. Wait for an `ack` with a lease in `LOCKS.md`, OR proceed only if the
   request is unambiguously surgical (one-line backend bug fix that is
   blocking the operator) — and in that case must immediately log a
   `coordination` entry in `LEDGER.md` plus a heads-up in the other
   inbox.

---

## Lock Semantics

A lease in `LOCKS.md` is an advisory claim on a path or path glob. The
other agent must not write to a held path without a hand-off.

Lease entry format (table row):

```
| <iso8601 acquired> | <iso8601 expires> | <agent> | <path or glob>             | <one-line intent>                       |
```

Rules:

- Default TTL is **30 minutes** of wall-clock. Refresh by editing `expires`.
- Release by deleting the row. Releases are not announced separately —
  the LEDGER entry is the announcement.
- Stale leases (expired > 60 min with no LEDGER closure) may be reclaimed
  by the other agent after writing a `reclaim` note in the owner's inbox.
- One agent should not hold more than ~5 leases at once. If you need
  more, you are working too broadly — split the slice.

---

## Mailbox Message Schema

`INBOX_CLAUDE.md` and `INBOX_CODEX.md` are append-only queues. Newest
message at the top. Each message:

```markdown
### <iso8601> · <kind> · <subject>

- from: <agent>
- to: <agent>
- ref: <optional path / route / lease>
- needs: <ack | answer | route | schema | nothing>
- expires: <iso8601 — when this becomes stale>

<body — keep under ~10 lines; link to artifacts for detail>
```

`kind` is one of:

- `request` — please do X (route, schema, fix, lease).
- `ack` — accepted; lease/lease-ref attached.
- `nack` — declined; reason inline.
- `answer` — here is what you asked.
- `heads-up` — FYI, no action required.
- `handoff` — I am stopping; you take it.
- `escalate` — operator needed; both agents pause.

When you respond, **do not delete the original** — append the new message
on top. Resolved threads age out via the `expires` field; either agent
may garbage-collect entries past expiry by moving them to
`COORDINATION/INBOX_ARCHIVE.md`.

---

## Cross-Boundary Change Ledger

`LEDGER.md` is append-only, newest entry on top. One line per change
that crosses the operation boundary. Format:

```
- <iso8601> · <agent> · <kind> · <ref> — <one-line description>
```

`kind`:

- `route-added` — backend route now exists; frontend can consume.
- `route-changed` — request/response shape moved; frontend must adapt.
- `schema-added` — new pydantic / sqlalchemy / zod schema.
- `migration` — alembic migration shipped.
- `frontend-consumed` — frontend now depends on a backend artifact.
- `lint` — banned-name lint or contract test changed.
- `coordination` — meta-entry (lease taken, hand-off, etc.).

Any LEDGER entry with `route-added`, `route-changed`, or `schema-added`
implies the other agent should re-run their contract / typecheck
suites before their next push.

---

## Daily Operating Loop

Every turn each agent runs this loop:

1. **Read** `LOCKS.md` + own inbox. If a `request` blocks current work,
   answer it before opening anything new.
2. **Decide** the next slice. If it touches a path the other agent owns,
   open a `request` and **stop on that slice** — work elsewhere instead.
3. **Lease** any shared paths in `LOCKS.md` before editing.
4. **Work** the slice.
5. **Test** locally. Both agents run their own boundary suite:
   - Claude: `cd frontend && pnpm typecheck && pnpm test:run` plus
     `python -m pytest backend/tests/unit/api/test_frontend_api_contract.py backend/tests/unit/lint/`.
   - Codex: the test set documented in `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md`.
6. **Report** — append to LEDGER, release leases, update own status board,
   answer any inbox items unblocked by this slice.

---

## Decision Authority

- The operator (Nanyel) is the only approver for renames, doctrine
  changes, banned-name additions, and any destructive operation.
- The two agents may unilaterally fix bugs, ship slices, refactor
  internal code inside their own ownership zone.
- For surgical cross-boundary fixes (e.g. one-line backend filter that
  unblocks a frontend 503), the touching agent must:
  - keep the patch to the smallest possible diff,
  - log a `coordination` LEDGER entry plus a `heads-up` in the other inbox,
  - ping the operator if the change spans more than ~5 lines or touches
    an entity, route, or migration.

---

## What This Replaces

This protocol does not replace the per-operation status boards. Those
still hold the executive briefing. This protocol only adds the thin
async layer needed for two agents to share the codebase without
collisions.

If the protocol and an `OPERATION_STATUS.md` ever disagree on path
ownership, the status boards win for that operation; update this file.
