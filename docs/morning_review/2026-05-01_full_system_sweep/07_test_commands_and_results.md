# 07 Test Commands And Results

Working directory: `c:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild`
Date: 2026-05-01
Mode: safe audit commands only.

## Command 1

```powershell
python -m pytest backend\tests\unit -q
```

Result: failed.

Summary:

- 8 failed
- 2121 passed
- 6 warnings
- duration: 94.21s

Failures:

- `backend/tests/unit/lint/test_no_banned_product_names.py::test_no_banned_product_phrases_in_backend_source`
  - offender: `simulation/historical_replay.py:1296 -- 'Live Runtime' is banned`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_successful_market_open_path_calls_order_manager_adapter_broker_sync`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_cli_refuses_when_market_closed`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_readiness_check_submits_no_orders`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_runtime_dry_run_submits_no_orders`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_runtime_dry_run_market_closed_exits_cleanly`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_runtime_dry_run_execute_uses_proper_order_path`
- `backend/tests/unit/tools/test_account_operator_tools.py::test_runtime_dry_run_execute_enforces_max_one_order`

Common tool-test error:

```text
TypeError: FakeSmokeAdapter.__init__() got an unexpected keyword argument 'mode'
TypeError: FakeRuntimeAdapter.__init__() got an unexpected keyword argument 'mode'
TypeError: FakeReadinessAdapter() takes no arguments
```

Warnings included FastAPI `on_event` deprecation warnings for `backend/app/api/server.py:55` and `backend/app/api/server.py:97`.

## Command 2

```powershell
npm.cmd run build
```

Result: passed.

Summary:

- root script delegated to `npm run build --prefix frontend`
- frontend typecheck passed
- Vite build passed
- warning: one JS chunk was 1,456.04 kB after minification, above Vite's 500 kB warning threshold

## Command 3

```powershell
npm.cmd run lint:names
```

Result: passed.

Summary:

```text
frontend banned-name lint: clean
```

## Command 4

```powershell
npm.cmd test
```

Result: failed.

Summary:

- full frontend Vitest run failed before two suites collected
- 2 failed test files
- 77 passed test files
- 594 passed tests
- duration: 45.78s

Failed suites:

- `src/routes/StrategyComposeV4.test.tsx`
- `src/strategy_ide_v4/StarterStrategyPanel.test.tsx`

Reported error:

```text
ReferenceError: legId is not defined
at src/strategy_ide_v4/starterStrategies.ts:89:15
```

Notes:

- The source currently shows `uid()` at `starterStrategies.ts:89`, not `legId`, and targeted reruns passed. Treat as test-order/global-state flakiness until reproduced deterministically.
- Warnings included React Router v7 future flag warnings and Radix/Dialog ref warnings.

## Command 5

```powershell
python -m pytest backend\tests\unit\api\test_frontend_api_contract.py backend\tests\unit\api\test_operations_routes.py backend\tests\unit\lint -q
```

Result: failed.

Summary:

- 1 failed
- 282 passed
- 5 warnings
- duration: 6.75s

Failure:

- `backend/tests/unit/lint/test_no_banned_product_names.py::test_no_banned_product_phrases_in_backend_source`
  - offender: `simulation/historical_replay.py:1296 -- 'Live Runtime' is banned`

## Command 6

```powershell
npm.cmd --prefix frontend exec vitest run src/strategy_ide_v4/StarterStrategyPanel.test.tsx -- --reporter verbose
```

Result: command failed for invocation/path reasons.

Summary:

- Vitest ran from repo root and failed to resolve `@/test/renderRoute`.
- This command was malformed for this repo layout. It is recorded because it was run.

## Command 7

```powershell
npm.cmd exec vitest run src/strategy_ide_v4/StarterStrategyPanel.test.tsx -- --reporter verbose
```

Working directory: `frontend`

Result: passed.

Summary:

- 1 test file passed
- 14 tests passed
- duration: 1.65s

## Command 8

```powershell
npm.cmd exec vitest run src/routes/StrategyComposeV4.test.tsx -- --reporter verbose
```

Working directory: `frontend`

Result: passed.

Summary:

- 1 test file passed
- 26 tests passed
- duration: 3.77s

Notes:

- Targeted run emitted connection refused warnings to `localhost:3000` in some tests and one React `act(...)` warning, but tests passed.

## Overall Test Interpretation

- Backend is not green.
- Frontend build is green.
- Frontend full test run is not green and appears order-sensitive because the suites that failed in the full run passed when run individually.
- Route/contract backend slice is almost green but blocked by the banned-name lint failure.
