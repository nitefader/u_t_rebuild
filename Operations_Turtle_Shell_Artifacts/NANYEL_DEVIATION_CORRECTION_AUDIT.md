# Nanyel Deviation Correction Audit

Operation: Turtle Shell

Reviewed at: 2026-04-27 00:43:37 -04:00

Decision: NANYEL APPROVES THE CURRENT RUNTIME-SPINE CORRECTION SLICE.

## Standard Applied

Source of truth:

- `AGENTS.md`
- `Operations_Turtle_Shell_Artifacts/TURTLE_SHELL_GUARDRAILS.md`

Required spine:

```text
Strategy
-> Deployment
-> SignalPlan
-> Account Evaluation
-> RiskResolver
-> Governor
-> Order
-> BrokerAdapter
-> BrokerSync
-> Position Truth
```

## Deviations Corrected

### 1. Active Legacy Runtime Path

Corrected.

- Removed legacy runtime engine implementation.
- Removed runtime export for the legacy pre-SignalPlan decision path.
- Updated paper dry-run tooling to use `RuntimeOrchestrator`.

### 2. ExecutionIntent Before RiskResolver

Corrected for the forward entry runtime path.

- Runtime no longer builds `ExecutionIntent` before RiskResolver for entries.
- Risk sizing from the Strategy risk profile now occurs behind RiskResolver.
- Runtime entry flow now uses:

```text
CandidateTradeIntent
-> SignalPlan
-> RiskResolver
-> Governor
-> OrderManager
```

Compatibility note:

- `ExecutionIntent` remains only as a compatibility contract for legacy
  protective/manual test paths. It is no longer the entry runtime authority.

### 3. Pending Exit Priority Was Advisory Only

Corrected.

- `OrderManager.request_superseded_position_management_cancels(...)` now
  intentionally cancels passive position-management orders when a higher
  priority close/logical_exit arrives.
- Runtime calls this before submitting the incoming close/logical_exit order.
- Cancel requests route through the BrokerAdapter boundary when a broker adapter
  is attached.

### 4. Preflight Rejection Was Written Through BrokerSync

Corrected for runtime and manual submit paths.

- Runtime preflight rejection updates the internal ledger directly as internal
  advisory truth.
- Manual preflight rejection updates the internal ledger directly as internal
  advisory truth.
- BrokerSync remains reserved for broker-originated truth.

### 5. Direct Broker Account Snapshot Reads In Runtime Preflight

Corrected.

- Runtime market-rule preflight now reads buying power from BrokerSyncService
  latest Account snapshot.
- Manual preflight now uses the frontend/configured Broker Account snapshot and
  fails closed with zero buying power if none exists.

### 6. Same Account / Same Symbol Multiple Lineage Ambiguity

Corrected.

- Deployment exit management now blocks an Account if more than one active
  matching Position lineage exists for that Account.
- Runtime no longer silently overwrites positions by `account_id`.

## Guardrails Preserved

- No second runtime root added.
- No broker submission outside BrokerAdapter.
- No broker truth writes outside BrokerSync for broker-originated truth.
- Deployment emits SignalPlans and does not mutate Position truth.
- Account-owned Positions determine exits.
- Watchlist determines entries only.
- Automatic lifecycle child-leg live submission remains gated until
  leg-specific broker order shapes and activation sequencing are safe.

## Remaining Known Migration Shims

These are not approved as permanent product concepts:

- `ProgramVersion`
- `ResolvedProgramComponents`
- `program_id`
- `ExecutionIntent` compatibility contract

They remain only because broader research, chart, simulation, promotion, and
operations modules still depend on them. Nanyel does not approve extending them.
Future work must shrink and remove them.

## Tests

```text
python -m pytest backend\tests\unit\risk_resolver backend\tests\unit\pipeline\test_runtime_orchestrator.py backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py -q
Result: 39 passed, 1 warning

python -m pytest backend\tests\unit\orders\test_order_manager.py backend\tests\unit\pipeline\test_runtime_orchestrator.py -q
Result: 76 passed, 1 warning

python -m pytest backend\tests\unit\api\test_manual_trade_preflight.py backend\tests\unit\api\test_broker_accounts_routes.py -q
Result: 8 passed, 1 warning

python -m pytest backend\tests\unit\runtime backend\tests\unit\pipeline backend\tests\unit\orders backend\tests\unit\api\test_manual_trade_preflight.py backend\tests\unit\lint\test_turtle_shell_architecture_guardrails.py -q
Result: 151 passed, 2 warnings

python -m pytest backend\tests\unit\tools\test_paper_operator_tools.py -q
Result: 18 passed, 1 warning

python -m pytest backend\tests\unit -q
Result: 1006 passed, 6 warnings

python -m pytest backend\tests\smoke -q
Result: 6 passed, 1 warning
```

## Approval

Nanyel approval: approved for this correction slice.

Full platform approval still requires later removal of Program/ExecutionIntent
migration shims across research, chart, simulation, promotion, operations, and
legacy compatibility surfaces.
