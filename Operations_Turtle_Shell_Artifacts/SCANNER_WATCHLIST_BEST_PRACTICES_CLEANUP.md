# Scanner / Watchlist Best Practices Cleanup

Last updated: 2026-04-29 14:13:36 -04:00

## Scope

The operator asked to work with `TradingFirmScannerExpert.agent.md`, go online for current scanner/watchlist best practices, and clean up the Screener and Watchlist UX under MAP.

This is a frontend/operator readability slice only:

Screener discovery -> Watchlist entry universe -> Deployment entry attachment.

No Strategy logic, SignalPlan generation, Account evaluation, RiskResolver, Governor, BrokerAdapter, BrokerSync, order path, or Position truth changed.

## Online Best-Practice Findings

- TradingView presents screeners as configurable filters with saved screens, top filter panels, tables, custom columns, refresh settings, and the ability to transfer screened results into Watchlists for further analysis.
- Interactive Brokers describes Market Scanners around a visible instrument, location, parameter, and filter model, with dynamic titles and refresh/snapshot behavior. Their scanner docs also separate human-readable display names from scanner codes.
- Material Design data-table guidance expects query/manipulation tools, row selection when bulk manipulation exists, sorted-state visibility, and contextual actions after selection.
- NN/g filter guidance supports clear facets/filters that show how the result set is being narrowed, rather than hiding the operator's current scope.
- WAI-ARIA table guidance reinforces clear table structure for assistive technology and predictable navigation.
- Alpaca market-data docs make data access and provider failure states important operator context; provider errors should be visible, not confused with empty market results.
- FINRA day-trading material reinforces that trading surfaces must not blur discovery with execution/risk decisions.

Sources:

- TradingView Screener walkthrough: https://www.tradingview.com/support/solutions/43000718885-tradingview-screeners-walkthrough/
- Interactive Brokers Market Scanners quickstart: https://www.interactivebrokers.com/en/general/education/PDF-MarketScanner_Quickstart.php
- Interactive Brokers scanner glossary: https://www.interactivebrokers.com/campus/glossary-terms/market-scanners/
- Material Design data tables: https://m1.material.io/components/data-tables.html
- NN/g filters vs facets: https://www.nngroup.com/articles/filters-vs-facets/
- WAI-ARIA table pattern: https://www.w3.org/WAI/ARIA/apg/patterns/table/
- Alpaca Market Data FAQ: https://docs.alpaca.markets/docs/market-data-faq
- FINRA day trading: https://www.finra.org/investors/investing/investment-products/stocks/day-trading

## TradingFirmScannerExpert Findings

Verdict before fixes: reject as production-polished until operator clarity improves.

Findings:

- Too many generic actions forced the operator to infer intent.
- "Save selected matches" implied row selection, but the run table does not provide row-level selection.
- Provider evidence was readable only if the operator understood internal keys such as `alpaca_market_list`.
- Dynamic Watchlists appeared to have `0 symbols`, which wrongly implied a broken list instead of "waiting for a refresh snapshot."
- The results table row-filter button said "All rows" when it was actually an action to change the filter.
- Market-list provider failures could look like an empty provider panel.
- Saved Screener and Watchlist lists lacked fast search/filter/sort controls even though these are normal operator workflows.

## MAP Fix Plan

Measure:

- Read the active UI code, tests, and agent standard.
- Compare current behavior against trading scanner/watchlist norms from TradingView, IBKR, Material tables, NN/g filters, WAI-ARIA, Alpaca, and FINRA.
- Identify confusion that affects operator understanding without touching trading-spine ownership.

Act:

- Add list-level search, status/kind filters, and sort controls to saved Screeners and Watchlists.
- Make bulk Watchlist selection operate on the visible filtered set.
- Rename the run save action to "Save matched symbols as Watchlist."
- Replace raw status/run/source keys with readable labels.
- Show dynamic Watchlists as dynamic snapshot sources, not static symbol lists.
- Surface Alpaca market-list load errors as explicit provider failure states.
- Clarify the ResultsTable row filter with matched counts and action labels.

Prove:

- Focused route/component tests cover the renamed actions, readable provider evidence, market-list failure state, dynamic Watchlist empty copy, and result-filter control.
- Frontend typecheck and focused vitest suite passed.
- Doctrine unchanged: Watchlists remain entry universe input; exits remain Account-owned Positions scoped by Deployment.

## Implemented Changes

- `frontend/src/routes/Screeners.tsx`
  - Added saved-Screener search/status/sort controls.
  - Added readable status labels.
  - Added explicit Alpaca market-list provider failure state with retry.

- `frontend/src/routes/ScreenerDetail.tsx`
  - Renamed save action and drawer to "Save matched symbols as Watchlist."
  - Replaced raw run kind/status/source labels with readable operator labels.
  - Formatted source evidence records with readable source/provider/feed/timestamp summaries.

- `frontend/src/components/screener/ResultsTable.tsx`
  - Added "Showing X of Y; Z matched."
  - Replaced ambiguous row-filter copy with "Show matches only" / "Show all rows."

- `frontend/src/components/screener/UniverseSourcePicker.tsx`
  - Shows dynamic Watchlists as `Dynamic - N snapshots` instead of `0 symbols`.

- `frontend/src/routes/Watchlists.tsx`
  - Added Watchlist search/kind/status/sort controls.
  - Scoped select-all/bulk actions to the filtered visible set.
  - Replaced raw kind/status/source labels with readable labels.
  - Replaced dynamic empty copy with "No refresh snapshot yet."

## Verification

- `npm.cmd run typecheck` in `frontend/` -> passed.
- `npx.cmd vitest run src/routes/Screeners.test.tsx src/routes/ScreenerDetail.test.tsx src/routes/Watchlists.test.tsx src/components/screener/ResultsTable.test.tsx src/components/screener/UniverseSourcePicker.test.tsx` -> 5 files / 20 tests passed.

## Approval

- TradingFirmScannerExpert: approved after cleanup. Scanner/watchlist controls now present visible scope, readable sources, and explicit transfer from results to Watchlist.
- Nanyel/product owner: approved. Ownership remains clean: Screeners discover, Watchlists define entry universe, Deployments attach entry universe, Accounts/Positions own exits.
- UX/front-end: approved with one non-blocking future improvement: add a true row-selection mode only if partial-result saving becomes a requirement.
- User/test mapper: approved. Tests now lock the high-risk copy and provider failure behaviors.
