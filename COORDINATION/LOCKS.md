# Active Path Leases

Both agents read this file at the start of every turn. Default TTL is 30 minutes.
See `COORDINATION/PROTOCOL.md` for full lock semantics.

Last updated: 2026-04-29 21:53:00 -04:00

| Acquired                  | Expires                   | Agent  | Path or glob                                  | Intent                                              |
| ------------------------- | ------------------------- | ------ | --------------------------------------------- | --------------------------------------------------- |
| 2026-04-29 21:53:00 -04:00 | 2026-04-29 23:53:00 -04:00 | Claude | `backend/app/persistence/`                    | T-1 Bracket Program — strategy_controls + execution_plan version persistence |
| 2026-04-29 21:53:00 -04:00 | 2026-04-29 23:53:00 -04:00 | Claude | `backend/app/strategy_composer/service.py`    | T-1 Bracket Program — wire save_draft to persist controls + plan |
| 2026-04-29 21:53:00 -04:00 | 2026-04-29 23:53:00 -04:00 | Claude | `backend/app/domain/execution_style.py`       | T-1 Bracket Program — rename ExecutionStyleVersion → ExecutionPlanVersion |
| 2026-04-29 21:53:00 -04:00 | 2026-04-29 23:53:00 -04:00 | Claude | `backend/app/domain/strategy_controls.py`     | T-1 Bracket Program — versioned StrategyControls payload |
| 2026-04-29 21:53:00 -04:00 | 2026-04-29 23:53:00 -04:00 | Claude | `backend/app/deployments/`                    | T-1/T-3 Bracket Program — deployment binds execution_plan_version_id + risk_plan_version_id |
| 2026-04-29 21:53:00 -04:00 | 2026-04-29 23:53:00 -04:00 | Claude | `backend/tests/unit/{persistence,strategy_composer,strategies,deployments}/` | T-1 tests |

---

## How To Add A Lease

1. Insert a new row above this section with:
   - `acquired` â€” iso8601 with `-04:00` offset.
   - `expires` â€” `acquired + TTL` (default 30 min, max 2 h without re-justification).
   - `agent` â€” `Codex` or `Claude`.
   - `path` â€” single path or glob (e.g. `backend/app/operations/`).
   - `intent` â€” one short line explaining the slice.
2. Edit only inside that path until the lease is released.
3. Release by deleting the row + appending a `LEDGER.md` entry that closes the slice.

## When To Reclaim A Stale Lease

A lease is stale if `expires` is more than 60 minutes in the past and no
LEDGER entry has closed it. To reclaim:

1. Open a `reclaim` message in the holder's inbox.
2. Wait one turn for them to refresh, hand off, or release.
3. If no response, delete the row, log a `coordination` LEDGER entry,
   and proceed with the work.
