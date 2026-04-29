# Screener And Watchlist User Journey

Last updated: 2026-04-29 04:05:53 -04:00

## Scope

This journey covers the Alpaca-first discovery flow from Screener discovery to
Watchlist entry universe to Deployment attachment. It also covers schedule
automation and the AAPL capability regression that previously made missing
provider evidence read like "Alpaca not tradeable."

This journey does not include broker submission, Account order approval,
BrokerSync writes, or Position exit handling. Those remain in the trading spine.

## Doctrine

- Strategy remains symbol-agnostic.
- Screeners are discovery only.
- Watchlists are entry-only symbol sources.
- Scheduled refresh creates Screener runs or Watchlist snapshots only.
- Deployment attaches Watchlists as entry universe and emits SignalPlans only.
- Exits come from Account-owned Positions scoped by `deployment_id`.
- Alpaca capability evidence is provider evidence for discovery, not execution truth.
- BrokerSync remains the only broker truth writer.

## User 1: Nanyel / Operator

Goal: confirm the platform explains the flow, avoids hidden mutations, and keeps
the trading spine clean.

1. Open Screeners.
2. Confirm Alpaca Market Lists, Templates, AI Composer, and entry-only doctrine are visible.
3. Open AI Composer.
4. Enter a natural-language discovery request.
5. Confirm AI is advisory only, compiles into visible typed rules, and unsupported clauses are listed.
6. Run a Screener.
7. Save matched results as a static Watchlist.
8. Create a dynamic Watchlist from the ScreenerVersion.
9. Refresh the dynamic Watchlist and confirm a new snapshot with source run and diff evidence.
10. Attach the Watchlist to a Deployment entry universe.
11. Confirm Deployment UI says entries come from Watchlists and exits come from Account Positions.
12. Try unsafe delete on a Screener with run history and confirm it is blocked with a readable reason.
13. Review audit/source evidence and screenshot capture.

Pass condition: no raw ids are required to understand the flow, no hidden broker
or Account mutation happens, and every destructive or automated action leaves
readable audit evidence.

## User 2: Expert Day Trader

Goal: quickly discover premarket/open-hour movers and most-active names using
Alpaca-first evidence.

1. Open Screeners before or during the session.
2. Run Alpaca Day Gainers.
3. Run Alpaca Day Losers.
4. Run Alpaca Most Active.
5. Confirm the result universe and run status are visible.
6. Confirm AAPL asset capability evidence is active/tradable when Alpaca returns that truth.
7. Add typed broker/price/volume criteria using metric/operator/value controls.
8. Schedule a Screener run for premarket review, such as 09:15 America/New_York.
9. Schedule a Watchlist refresh for open-hour repetition, such as every 15 minutes from 09:30 to 10:30 America/New_York.
10. Use Run now without disabling the schedule.
11. Pause, resume, and archive the schedule.

Pass condition: movers resolve through Alpaca provider evidence, unavailable
provider evidence is not displayed as false "not tradeable," and freshness,
next run, last run, and failure state are visible.

## User 3: Swing / Quant User

Goal: create a repeatable, versioned discovery process that can be rerun,
compared, scheduled, and audited.

1. Start from an Alpaca market-list Screener.
2. Add a new ScreenerVersion with a broker-capability criterion.
3. Run the edited version.
4. Rerun the pinned version and confirm parent run lineage.
5. Compare run to rerun and review added/removed/stayed symbols.
6. Save static and dynamic Watchlists from matched results.
7. Refresh the dynamic Watchlist and confirm snapshot evidence.
8. Create a daily Screener schedule pinned to the exact ScreenerVersion.
9. Confirm schedule execution creates a scheduled run.
10. Confirm schedule pause/resume/archive lifecycle leaves execution records.

Pass condition: history stays immutable, schedules target exact versions, compare
output is visible, and Watchlist snapshots never become exit logic.

## Headless Acceptance

Command:

```text
cd frontend
npm.cmd run headless:screener
```

The headless walkthrough must pass persona gates for:

- `operator`
- `day_trader`
- `swing_quant`

The verifier must also pass the AAPL capability regression:

- AAPL explicit Screener run returns `broker.tradable = true`.
- The row does not include a false "asset is not tradable at Alpaca" reason.

## Validation Checklist

- Strategy remains symbol-agnostic: yes.
- SignalPlan correctness: yes; Deployment still emits SignalPlans only.
- Feature Engine compatibility: yes; Screener discovery does not alter Strategy feature logic.
- No duplicate system introduced: yes; schedules call Screener/Watchlist services only.
- UI to Backend alignment: yes; headless checks route, UI, schedule, and audit behavior.
