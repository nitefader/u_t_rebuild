# Operator Experience

Ultimate Trader must feel simple because the system does the hard work in the
background and explains itself when asked.

## Navigation

Keep navigation minimal:

- Dashboard
- Strategies
- Components
- Watchlists
- Accounts
- Deployments
- Operations
- Providers
- Settings

Optional deeper pages may exist behind details panels:

- Orders
- Trades
- Positions
- SignalPlans
- Chart Lab
- Backtests
- Optimizations
- Walk-Forward
- Sim Lab

## Accounts

The user creates an Account.

The Account form asks:

- display name
- broker provider, such as Alpaca
- broker mode, such as paper or live
- credentials
- risk config
- symbol restrictions

There is no separate create paper Account button and create live Account button.

## Providers

Providers has two buckets:

- Market Data Providers
- AI Providers

Do not call this Services Center.

Do not put broker Accounts into Providers.

## Settings

Settings should be small and operationally meaningful.

Settings may include:

- enable/disable Live Stock Market Data Stream startup
- selected default Market Data Provider
- AI Provider default
- global operator preferences
- logs/export/context options

Settings must not become a dumping ground for runtime controls. Runtime controls
belong in Operations.

## Operations

Operations must show:

- Live Stock Market Data Stream status
- Account Trade Sync status for every Account
- running Deployments
- Account pause/resume state
- global kill state
- stale sync states
- stream errors
- recent SignalPlans
- open orders
- open positions
- position explanation access

## Explanations

Every important page should have a compact explainer panel or help action.

Explainers should be plain language and copyable so the operator can paste them
into an LLM or notes.

Buttons that trigger risk, trading, sync, stream, or account actions should have
clear labels and accessible descriptions.

Nothing mission-critical should fail silently.

Nothing mission-critical should appear successful without visible evidence.
