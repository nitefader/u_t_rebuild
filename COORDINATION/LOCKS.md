# Active Path Leases

Both agents read this file at the start of every turn. Default TTL is 30 minutes.
See `COORDINATION/PROTOCOL.md` for full lock semantics.

Last updated: 2026-04-30 06:30:00 -04:00

(no active leases — T-6 leases released after commit; T-1..T-6 of the
Bracket Program are committed; T-7 leases will be acquired when T-7
starts)

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
