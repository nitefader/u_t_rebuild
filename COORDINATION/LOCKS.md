# Active Path Leases

Both agents read this file at the start of every turn. Default TTL is 30 minutes.
See `COORDINATION/PROTOCOL.md` for full lock semantics.

Last updated: 2026-05-02 16:36:00 -04:00

| acquired | expires | agent | path | intent |
| --- | --- | --- | --- | --- |
| 2026-05-02 12:45:00 -04:00 | 2026-05-02 17:06:00 -04:00 | Codex | `backend/app/{research,simulation,chart_lab}/**`, `backend/app/domain/research_evidence.py`, `backend/app/api/routes/{research_runs,research_jobs,chart_lab}.py`, `backend/tests/unit/{research,simulation,api}/**` | Research Evidence Contract + Shared Research Spine using immutable DeploymentSnapshot artifact; ChartLab verification contract refreshed. |
| 2026-05-02 12:45:00 -04:00 | 2026-05-02 17:06:00 -04:00 | Codex | `backend/app/domain/risk_plan.py`, `backend/app/api/routes/risk_plans.py`, `backend/app/persistence/{models.py,runtime_store.py}`, `backend/tests/unit/{domain,api,persistence}/**` | Enforce promoted RiskPlan source_run_id/evidence lineage for research-derived plans. |
| 2026-05-02 12:45:00 -04:00 | 2026-05-02 17:06:00 -04:00 | Codex | `frontend/src/api/{researchRuns,researchJobs,chartLab}.ts`, `frontend/src/api/schemas/{researchRuns,researchJobs,chartLab}.ts`, `frontend/src/routes/{ChartLab,SimLab,Backtests,WalkForward,Optimization}.tsx`, `frontend/src/components/{backtests,charts,jobs,optimization,risk_plans,walkforward}/**` | Research lab frontend contract/UI alignment; ChartLab pure signal/feature verification surface refreshed. |
| 2026-05-02 12:45:00 -04:00 | 2026-05-02 16:20:00 -04:00 | Codex | `Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md` | Turtle Shell heartbeat for research evidence/spine slice. |

(Claude lease 2026-05-02 05:17 → 12:35 RELEASED — HARD.MD remediation closed. See LEDGER 2026-05-02 12:30.)
(Claude lease 2026-05-02 13:00 → 13:35 RELEASED — Strategy IDE v4 Slice 11 closeout. See LEDGER 2026-05-02 13:30.)

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
