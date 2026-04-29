# Day Zero Runbook

Use this when starting Ultimate Trader in a broker-connected environment.

## Startup

1. Start backend with the intended runtime database.
2. Start frontend.
3. Open Operations.
4. Confirm Live Stock Market Data Stream status is visible.
5. Confirm every Account has Account Trade Sync status.
6. Confirm no stream or sync is silently failed.

## Account Readiness

For each Account:

- broker provider is explicit
- mode is explicit
- credentials validation is current
- Account Trade Sync is connected or shows a clear error
- broker sync freshness is current
- risk config is visible
- pause state is visible

## Deployment Readiness

For each Deployment:

- Strategy is valid
- Watchlists are resolved
- subscribed Accounts are visible
- runtime status is visible
- latest SignalPlans are visible

## During Operation

Watch:

- SignalPlans
- Account decisions
- Governor decisions
- orders
- fills
- positions
- related close/reduce SignalPlans
- stream freshness
- sync freshness

## Position Review

For every open position, the operator must be able to answer:

- why is this position open?
- what SignalPlan opened it?
- what Account accepted it?
- what size was chosen and why?
- what Governor rule approved it?
- what close/reduce plans are active?
- what orders and fills changed it?
- is sync fresh?

Use `Explain this position` for advisory context, not authority.

## Emergency

- Use global kill for platform-wide uncertainty.
- Use Account pause for Account-specific risk.
- Use Deployment pause for Strategy-publisher risk.
- Do not assume pause flattened positions.
- Flatten is a separate explicit action.
