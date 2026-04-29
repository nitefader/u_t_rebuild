# Mode Naming Contract

This document is the single source of truth for Trading OS system mode names.
Mode names must identify the system boundary being used, not just whether data is
historical, streaming, paper-funded, or live-funded.

## Canonical Enum Values

- `CHART_LAB_BATCH`
- `CHART_LAB_LIVE_PREVIEW`
- `SIM_LAB_HISTORICAL`
- `SIM_LAB_LIVE_SIMULATION`
- `BROKER_PAPER`
- `BROKER_LIVE`

## Mode Definitions

### `CHART_LAB_BATCH`

Chart Lab inspection over a fixed historical bar set. This mode is for visual
chart inspection, feature display, and non-executing signal previews over
already-bounded input data.

Allowed capabilities:

- Read historical market bars supplied to Chart Lab.
- Compute feature views for display.
- Render signal markers or diagnostics.
- Create no orders.
- Mutate no order or trade ledger.
- Use no broker account, broker positions, broker orders, or broker balances.

### `CHART_LAB_LIVE_PREVIEW`

Chart Lab inspection over live-preview market data without broker runtime
authority. This mode may preview changing chart data, but it remains a chart
inspection surface.

Allowed capabilities:

- Read market-data-only updates for preview.
- Compute feature views for display.
- Render signal markers or diagnostics.
- Create no orders.
- Mutate no order or trade ledger.
- Use no broker account, broker positions, broker orders, or broker balances.

### `SIM_LAB_HISTORICAL`

Sim Lab replay over historical bars using simulated orders, fills, positions,
trades, equity, and P&L. This mode is a full simulation surface, but it is not
Broker Runtime.

Allowed capabilities:

- Read historical market bars supplied to Sim Lab.
- Create simulated orders.
- Create simulated fills, positions, trades, equity, and P&L.
- Use simulated ledgers owned by Sim Lab.
- Use no BrokerAdapter.
- Use no real broker account, broker positions, broker orders, or broker balances.

### `SIM_LAB_LIVE_SIMULATION`

Sim Lab simulation over live market-data input. This mode simulates what would
happen under changing market conditions, but it is still not Broker Runtime.

Allowed capabilities:

- Read market-data-only live updates.
- Create simulated orders.
- Create simulated fills, positions, trades, equity, and P&L.
- Use simulated ledgers owned by Sim Lab.
- Use no BrokerAdapter.
- Use no real broker account, broker positions, broker orders, or broker balances.

### `BROKER_PAPER`

Broker Runtime connected to a broker paper account. This mode uses real broker
infrastructure against broker paper endpoints or paper accounts.

Allowed capabilities:

- Use BrokerAdapter.
- Use BrokerSync.
- Read broker account snapshots, open orders, order status, positions, and fills.
- Submit, cancel, and reconcile orders only through the broker boundary.
- Mutate broker-derived order truth only through BrokerSync.

### `BROKER_LIVE`

Broker Runtime connected to a broker live account. This mode uses real broker
infrastructure against live funded accounts and must be treated as real-money
operation.

Allowed capabilities:

- Use BrokerAdapter.
- Use BrokerSync.
- Read broker account snapshots, open orders, order status, positions, and fills.
- Submit, cancel, and reconcile orders only through the broker boundary.
- Mutate broker-derived order truth only through BrokerSync.
- Apply the strictest operator confirmation, freshness, and control-plane gates.

## Explicit Boundaries

- Chart Lab modes must not use BrokerAdapter.
- Chart Lab modes must not create orders.
- Chart Lab modes must not mutate OrderLedger or TradeLedger.
- Sim Lab modes must not use BrokerAdapter.
- Sim Lab modes must not use real broker data.
- Broker modes must use BrokerAdapter.
- Broker modes must use BrokerSync.

## Naming Rules

Internal enum names must use the canonical enum values exactly:

- `TradingMode.CHART_LAB_BATCH`
- `TradingMode.CHART_LAB_LIVE_PREVIEW`
- `TradingMode.SIM_LAB_HISTORICAL`
- `TradingMode.SIM_LAB_LIVE_SIMULATION`
- `TradingMode.BROKER_PAPER`
- `TradingMode.BROKER_LIVE`

Internal logs, API contracts, persistence records, and test fixtures should use
the canonical enum names whenever they describe system mode. Helper labels may
derive from these names, but they must not replace the canonical value.

User-facing labels must include the system surface and the funding/runtime
meaning when relevant:

- Chart Lab Batch
- Chart Lab Live Preview
- Sim Lab Historical
- Sim Lab Live Simulation
- Broker Runtime - Paper
- Broker Runtime - Live

Do not show a standalone user-facing label of "Paper", "Live", "Simulation", or
"Streaming" when the label is intended to communicate system mode.

## Banned Terms

These terms are banned as standalone mode names because they are ambiguous:

- `paper`
- `live`
- `sim paper`
- `streaming mode`

The words may appear only as contextual prose or broker/vendor configuration
fields when they do not define Trading OS system mode. For example, an external
SDK parameter named `paper` may remain as an adapter implementation detail, but
it must not be used as the system mode name.

## Anchor Rule

If BrokerAdapter is not involved, it is not Broker Runtime.

Market-data streaming alone does not make a mode Broker Runtime. Simulated order
creation does not make a mode Broker Runtime. A live-preview chart does not make
a mode Broker Runtime. Broker Runtime begins only at the boundary where
BrokerAdapter and BrokerSync are required.
