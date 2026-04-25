---
name: Per-task validation and logging discipline
description: After every coding task, run §13 validation commands and write an §14 IMPLEMENTATION_LOG entry — these are binding per the roadmap doc, not optional
type: feedback
---

After every implementation task, in this order:

1. Validation commands (§13) — run all four, even if frontend was not touched (unless explicitly impossible):
   ```
   python -m compileall -q backend/app backend/tests
   python -m pytest backend/tests -q
   cd frontend && npm.cmd run build
   cd frontend && npm.cmd test
   ```
2. Append an `IMPLEMENTATION_LOG.md` entry at `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md` using the §14 format exactly: `## YYYY-MM-DD HH:MM ET - <Task>` + Task / Files changed / Implemented / Scope kept out / Validation performed / Result / Verification / Commit.
3. Git contract (§15): `git status`; `git add .`; `git commit -m "..."`; `git status` — working tree clean afterward.

**Why:** the roadmap doc treats these as binding execution contract, not suggestions. Slice 1 (Mode-naming-contract migration, 2026-04-25) shipped without compileall, without an IMPLEMENTATION_LOG entry, and without the explicit `npm run build` step (it ran chained inside `npm test`, but the doc lists them separately). User flagged the misalignment, then reaffirmed: **"Always update Implementation Log"** — treat the §14 entry as a hard rule, not a nice-to-have.

**How to apply:** at the end of every coding slice — not just "big" ones. Never skip the IMPLEMENTATION_LOG entry. If the user accepts a slice without these, still backfill before doing anything else.
