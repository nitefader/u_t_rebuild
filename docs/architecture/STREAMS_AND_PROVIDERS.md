# Streams And Providers

Ultimate Trader has two provider buckets:

- Market Data Providers
- AI Providers

Accounts carry broker provider metadata such as Alpaca paper/live. Broker
provider metadata belongs to Account creation/editing, not a separate confusing
provider bucket.

## Market Data Providers

Market Data Providers configure external market data access.

Examples:

- Alpaca market data
- Yahoo historical data
- future market data vendor

Market Data Providers own:

- provider name
- credentials or credential absence
- validation status
- supported assets
- supported timeframes
- live data capability
- historical data capability
- default live stock data selection

They do not own:

- orders
- trades
- positions
- Account risk
- broker sync
- feature computation

## Live Stock Market Data Stream

Ultimate Trader has one live stock market data stream while the app is running.

The stream starts during system startup when enabled in Settings. It should
remain running morning, afternoon, night, and weekends while the app process is
up.

The stream may have zero or many symbol subscriptions. The connection and health
status are still visible even when no Strategy currently needs a symbol.

The stream must show:

- selected Market Data Provider
- connection state
- authenticated state
- subscribed symbols
- last message time
- last bar time by symbol
- stale/fresh status
- reconnect count
- last error

Failures are operator-visible. Do not fail silently.

## Account Trade Sync

Each configured Account has one Account Trade Sync.

Account Trade Sync starts during system startup for every configured Account,
regardless of whether the Account is paused, resumed, subscribed to a Deployment,
or currently trading.

Reason:

The operator still needs to see what is happening in the Account.

Account Trade Sync watches:

- order updates
- fills
- cancels
- rejects
- positions
- Account snapshots
- broker restrictions
- sync freshness

If Account Trade Sync fails, the UI must show a clear state such as:

```text
Account Trade Sync Down
```

or a more specific provider error:

```text
Alpaca trade stream disconnected: authentication failed
```

Do not label this as Market Data Pipeline down. Market data and Account trade
sync are different things.

## AI Providers

AI Providers configure advisory AI access.

AI may:

- explain positions
- explain pages and controls
- summarize runtime state
- help draft Strategies
- analyze logs
- produce copyable context

AI may not:

- approve trades
- reject trades
- override Governor
- submit orders
- cancel orders
- mutate Account truth
