# Naming Contract

Names must be boring, consistent, and unambiguous.

## Canonical Names

| Name | Meaning |
|---|---|
| Ultimate Trader | The whole platform |
| Strategy | Reusable trading logic and execution plan config |
| Watchlist | Saved source of eligible symbols |
| Deployment | Running Strategy publisher over Watchlists |
| SignalPlan | Neutral trade or position-management plan emitted by a Deployment |
| Account | Broker-connected trading account with mode/provider metadata and risk config |
| Governor | Final internal Account protection gate before broker submission |
| Order | Account-specific internal order created from an approved SignalPlan |
| Trade | Account-specific trade lifecycle derived from orders and fills |
| Position | Account-owned current exposure with signal lineage and explanation context |
| Market Data Provider | External provider config for market data |
| Market Data Stream | Platform live stock data stream selected from Market Data Providers |
| Account Trade Sync | Per-Account broker event/sync connection for orders, fills, positions, and account truth |
| AI Provider | External AI provider config for advisory generation/explanation |
| BrokerAdapter | Backend boundary that submits/cancels broker orders |
| BrokerSync | Backend truth writer for broker-derived order/fill/position/account state |
| Operations Center | Runtime visibility and control surface |

## Backend Class Names

The product label is `Account`.

The backend may use `BrokerAccount` where the code needs to distinguish this
from unrelated technical account concepts. `BrokerAccount` and product
`Account` refer to the same core domain object.

## Banned Product Names

Do not introduce these as active product concepts:

- Program
- Account Governor
- Services Center
- Paper Runtime as a separate product path
- Live Runtime as a separate product path
- Deployment per Account
- Strategy Account
- Broker Connection as a separate V1 entity
- Broker SubAccount
- Market Data Service Center

## Paper And Live

Paper and live are Account metadata:

```text
Account
  broker_provider: alpaca
  broker_mode: paper | live
```

Future providers fit the same Account model:

```text
Account
  broker_provider: thinkorswim | tradingview | robinhood | future
  broker_mode: provider-supported mode
```

The user creates an Account, then chooses the broker provider and mode. The
backend derives endpoints, streaming URLs, validation, and adapter behavior from
that metadata.
