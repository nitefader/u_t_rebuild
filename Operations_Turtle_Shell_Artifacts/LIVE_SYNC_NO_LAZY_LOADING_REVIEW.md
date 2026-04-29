# Live Sync No Lazy Loading Review

Operation: Turtle Shell

Reviewed at: 2026-04-27 03:51:04 -04:00

Status: completed

Purpose: ensure Account Trade Sync and BrokerSync are started by backend
lifecycle, not by frontend page load or browser WebSocket subscription.

## Rule

Live sync startup is allowed only from backend lifecycle paths:

- backend startup
- Account creation after credential validation
- Account credential replacement after validation
- explicit operator resume after pause

Live sync startup is not allowed from:

- Operations page load
- Brokers page load
- WebSocket subscription
- frontend polling
- first subscriber attachment

## Findings

- Backend startup calls `bootstrap_manual_trade_composition()` before
  `bootstrap_streams()`, so each stream has a BrokerSync truth writer before it
  opens.
- `bootstrap_streams()` starts one Account Trade Sync per configured,
  non-archived Alpaca Account with credentials.
- Broker Account create and credential replacement call
  `ensure_account_trade_sync_started(...)`.
- The Operations trade-stream WebSocket only calls `dispatcher.subscribe(...)`.

## Fixed

- Removed the lazy startup fallback from `TradeEventDispatcher.subscribe(...)`.
- A frontend subscription now registers a listener only. It cannot open the
  broker stream or start BrokerSync polling.
- Updated the runtime test to assert subscribing does not start the stream.

## Verification

```text
python -m pytest backend\tests\unit\runtime\test_runtime_context.py backend\tests\unit\api\test_server_startup.py backend\tests\unit\api\test_system_streams_route.py backend\tests\unit\api\test_operations_trade_stream_route.py -q
Result: 42 passed, 5 warnings

python -m pytest backend\tests\unit -q
Result: 1103 passed, 6 warnings

npm.cmd run typecheck
Result: passed
```

## Decision

Pass.

Live sync is no longer lazy-loaded by subscribers. If a dispatcher is not
running, the frontend can observe/report that state, but it cannot become the
startup trigger.
