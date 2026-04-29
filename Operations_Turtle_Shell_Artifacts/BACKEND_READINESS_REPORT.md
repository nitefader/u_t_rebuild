# Backend Readiness Report

Last updated: 2026-04-26 23:09:49 -04:00

Operation: Turtle Shell

Status: backend readiness pass completed

## Verdict

Backend Turtle Shell readiness gate passes for local backend validation.

No blocking backend test failures remain in the unit, smoke, or non-opt-in
integration/e2e suites.

Operator-requested steps 1 through 4 were run. Chart Lab and Sim Lab now emit
research evidence through a research evidence recorder boundary, Operations can
list/load detailed evidence, and day-zero backend checks are green.

## Verified Test Runs

```text
Test run: 2026-04-26 23:07:18 -04:00
Command: python -m pytest backend\tests\unit -q
Result: 963 passed, 6 warnings
```

```text
Test run: 2026-04-26 23:08:09 -04:00
Command: python -m pytest backend\tests\smoke -q
Result: 6 passed, 1 warning
```

```text
Test run: 2026-04-26 23:08:16 -04:00
Command: python -m pytest backend\tests\integration -q -rs
Result: 27 passed, 3 skipped, 1 warning
```

```text
Test run: 2026-04-26 23:08:44 -04:00
Command: RUN_ALPACA_FAKEPACA_STREAM=1 RUN_ALPACA_PAPER_INTEGRATION=1 RUN_ALPACA_PAPER_CRYPTO_STREAM=1 python -m pytest backend\tests\integration\test_alpaca_fakepaca_stream.py backend\tests\integration\test_alpaca_paper_integration.py backend\tests\integration\test_alpaca_paper_crypto_stream.py -q -rs
Result: 1 passed, 2 skipped, 2 warnings
```

Skipped integration checks in the standard integration run:

- `RUN_ALPACA_FAKEPACA_STREAM=1` required for Alpaca FAKEPACA stream test.
- `RUN_ALPACA_PAPER_CRYPTO_STREAM=1` required for real Alpaca paper
  trade-update stream test.
- `RUN_ALPACA_PAPER_INTEGRATION=1` required for real Alpaca paper integration
  checks.

These skips are intentional opt-in broker/network checks, not local backend
failures.

Opt-in Alpaca result:

- FAKEPACA stream check passed.
- Real Alpaca paper integration check skipped because `ALPACA_BASE_URL` must
  equal `https://paper-api.alpaca.markets`.
- Real Alpaca paper crypto stream check skipped because `ALPACA_BASE_URL` must
  equal `https://paper-api.alpaca.markets`.

## Backend Areas Covered

- Runtime spine:
  `SignalPlan -> Account Evaluation -> RiskResolver -> Governor -> Order`
- Multi-Account SignalPlan fan-out.
- Stable Account SignalPlan order idempotency.
- BrokerAdapter submit boundary.
- BrokerSync truth write boundary.
- Alpaca broker and market-rule preflight.
- Manual trade loop e2e.
- Broker truth money path e2e.
- Account Trade Sync routing through BrokerSync.
- One shared live stock market-data stream boundary.
- Chart Lab preview service.
- Simulation and historical replay.
- Research evidence contracts.
- Research evidence persistence and Operations summary.
- Chart Lab research evidence producer wiring.
- Sim Lab historical replay evidence producer wiring.
- Operations research evidence list/detail API.
- Promotion gate evidence checks.
- Operations Center projections.
- Turtle Shell architecture guardrail lint.

## Known Non-Blocking Warnings

- `websockets.legacy` deprecation from installed dependency.
- FastAPI `on_event` deprecation; should move to lifespan handlers later.
- Alpaca SDK `asyncio.iscoroutinefunction` deprecation warning.

These warnings do not block the backend readiness gate.

## Remaining Follow-Up Work

- Set `ALPACA_BASE_URL=https://paper-api.alpaca.markets` and rerun opt-in real
  Alpaca paper checks when the operator wants live broker-network validation.
- Wire Backtest, Optimization, and Walk-Forward producers into the research
  evidence recorder boundary.
- Continue later cleanup of legacy Program and ExecutionIntent shims after all
  consumers have migrated.

## Final Readiness Statement

Operation Turtle Shell backend foundation is coherent, tested, and ready for
the next execution phase.

The backend is not final production certification for real-money live trading
until opt-in real broker checks are run and the operator deliberately enables
live order submission.
