---
name: Per-task validation and logging discipline
description: After every coding task, run the active validation commands and write an active implementation log entry
type: feedback
---

After every implementation task, in this order:

1. Run validation commands unless explicitly impossible:
   ```
   python -m compileall -q backend/app backend/tests
   python -m pytest backend/tests -q
   npm.cmd run build --prefix frontend
   npm.cmd test --prefix frontend
   ```
2. Append an implementation entry to:
   `docs/implementation/IMPLEMENTATION_LOG.md`
3. Use this format:
   ```
   ## YYYY-MM-DD HH:MM ET - <Task>

   Task:
   - <short factual description>

   Files changed:
   - <path>

   Implemented:
   - <bullet>

   Scope kept out:
   - <bullet>

   Validation performed:
   - <command>

   Result:
   - <pass/fail summary>

   Verification:
   - <boundary checks>

   Commit:
   - <hash or pending>
   ```
4. Before commit: inspect `git status`.
5. Commit only relevant files.
6. After commit: confirm working tree status.

Never use archived implementation logs as active authority.
