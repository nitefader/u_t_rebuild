# Ultimate Trader Mandate

Approved direction: April 26, 2026

Ultimate Trader is one production trading platform.

There is no separate paper product, no test-mode fork, no hidden runtime path,
and no confusing duplicate model. Paper and live are Account metadata and
connection context, not separate user workflows.

## Operating Principles

- One platform: Ultimate Trader.
- One account concept: Account.
- One market data provider bucket.
- One AI provider bucket.
- One live stock market data stream for the platform while the app is running.
- One trade sync stream per Account while the app is running.
- No silent failure.
- No silent success for mission-critical runtime actions.
- No user-facing Program entity in V1.
- No duplicate Deployment per Account.
- No direct provider calls from frontend pages.
- No broker truth writes outside BrokerSync.
- No real broker execution from Chart Lab, Sim Lab, Backtests, or AI.

## Product Model

The user builds a Strategy.

The user selects Watchlists.

The user starts a Deployment.

The Deployment publishes SignalPlans.

Accounts subscribe to Deployments.

Each Account independently accepts, rejects, sizes, ignores, opens, reduces, or
closes based on its own risk config, broker state, restrictions, positions, and
Governor decision.

The Account owns the resulting position and must explain it.

## Production Standard

Everything is designed as production-grade from day zero:

- durable state where needed
- explicit operator-visible status
- clear failure messages
- account-isolated risk
- deterministic decisions
- explainable orders and positions
- background intelligence without hiding logic
- copyable context for human review or LLM review

If a stream, sync, resolver, provider, account, Deployment, or order path is
unhealthy, the operator must see it.
