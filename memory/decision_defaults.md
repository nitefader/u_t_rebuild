---
name: Default architectural choices when unsure
description: Active Ultimate Trader tiebreakers
type: feedback
---

When unsure, choose:

- simple Account model over extra broker/account entity layers
- Account metadata over separate paper/live product paths
- shared Live Stock Market Data Stream over per-Account market data streams
- one Account Trade Sync per Account over hidden/on-demand trade streams
- visible failure over silent failure
- visible evidence over silent success for mission-critical actions
- feature-driven data demand over frontend/provider shortcuts
- deterministic resolver logic over smart/implicit magic
- explicit enum/status codes over free text
- completed bars over forming bars
- account-isolated risk over global risk
- separate simulated truth over mixed real/sim ledgers
- explanation context over hidden background decisions

Surface deviations only when a hard constraint forces them.
