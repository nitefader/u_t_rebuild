# Research Create-Run API Handoff

Operation: Turtle Shell

Timestamp: 2026-04-27 04:05:00 -04:00

Owner: Coordinator

Purpose: unblock the frontend functionality team from read-only research pages to create-run controls.

## Decision

PASS.

The backend has V1 research create-run APIs for Backtests, Sim Lab, Optimization, and Walk-Forward. They persist/query research evidence only. They do not create orders, mutate broker truth, or introduce a second runtime.

## Ready Endpoints

Backtests:

- `GET /api/v1/backtests`
- `POST /api/v1/backtests`
- `GET /api/v1/backtests/{run_id}`
- `POST /api/v1/backtests/{run_id}/cancel`

Sim Lab:

- `GET /api/v1/sim-lab/sessions`
- `POST /api/v1/sim-lab/sessions`
- `GET /api/v1/sim-lab/sessions/{session_id}`
- `DELETE /api/v1/sim-lab/sessions/{session_id}`
- `POST /api/v1/sim-lab/sessions/{session_id}/run`
- `GET /api/v1/sim-lab/sessions/{session_id}/results`

Optimization:

- `GET /api/v1/optimization/runs`
- `POST /api/v1/optimization/runs`
- `GET /api/v1/optimization/runs/{run_id}`
- `DELETE /api/v1/optimization/runs/{run_id}`

Walk-Forward:

- `GET /api/v1/walk-forward/runs`
- `POST /api/v1/walk-forward/runs`
- `GET /api/v1/walk-forward/runs/{run_id}`
- `DELETE /api/v1/walk-forward/runs/{run_id}`

## Frontend Clients

Use the existing clients in:

- `frontend/src/api/researchRuns.ts`
- `frontend/src/api/schemas/researchRuns.ts`

Current route pages still use `ResearchEvidencePage` as the read-only surface:

- `frontend/src/routes/Backtests.tsx`
- `frontend/src/routes/SimLab.tsx`
- `frontend/src/routes/Optimization.tsx`
- `frontend/src/routes/WalkForward.tsx`

The page copy has been updated so it no longer claims the APIs are unwired.

## Guardrails

- Research systems produce evidence only.
- Research systems do not trade.
- Research APIs must not accept Account, broker order, fill, or position truth fields in evidence payloads.
- BrokerAdapter remains the only broker submission boundary.
- BrokerSync remains the only broker truth writer.
- No paper runtime or live runtime split is introduced.

## Verification Added

Added HTTP-level contract tests proving frontend-shaped JSON requests and responses work through FastAPI routing:

- Backtest create/list/cancel
- Sim Lab create/run
- Optimization create
- Walk-Forward create

## Next Frontend Slice

Claude/front-end team can safely add guarded create-run controls using the existing API clients.

Recommended first UI scope:

1. Add create-run drawer for Backtests using `BacktestsApi.create`.
2. Add create-session and run-session controls for Sim Lab using `SimLabApi`.
3. Add create-run drawers for Optimization and Walk-Forward.
4. Keep the current evidence table as the shared results surface.

## Remaining Backend Risk

These V1 endpoints record research evidence. They do not yet execute full historical engines. When those engines are wired, they must use the shared Feature Engine, Signal Engine, RiskResolver, Governor, and Order creation logic without becoming alternate live runtimes.
