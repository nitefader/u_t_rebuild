# Alpaca-First Screener And Watchlist Execution Plan

Created: 2026-04-28 22:06:35 -04:00

Owner: Codex, Operation Turtle Shell

Status: planning_ready_for_new_window_execution

## Mission

Build an end-to-end Alpaca-first Screener and Watchlist system that lets the
operator discover, test, run, rerun, compare, refresh, save, archive, and delete
symbol universes without breaking the Ultimate Trader spine.

The system must make it easier for an operator who does not know what to search
for. It must support templates, AI-assisted composition, fresh computed
screeners, static watchlists, dynamic watchlists, market movers, and broker
capability filtering.

It must not become a second trading runtime.

## Non-Negotiable Spine

The existing doctrine remains locked:

```text
Strategy
-> Deployment
-> SignalPlan
-> Account Evaluation
-> RiskResolver
-> Governor
-> Order
-> BrokerAdapter
-> BrokerSync
-> Position Truth
```

Implications:

- Strategy remains symbol-agnostic.
- Watchlists provide entry symbols only.
- Deployments evaluate Strategy logic over Watchlist symbols.
- SignalPlans are emitted by Deployment only.
- Accounts decide whether to act.
- Exits come from Account-owned Positions scoped by deployment_id.
- BrokerSync is the only broker truth writer.
- Screener never submits orders, attaches accounts, mutates positions, or emits
  SignalPlans.
- AI is advisory and compiles into visible typed rules only.

## Current State From Code

Observed files:

- `backend/app/screener/domain.py`
- `backend/app/screener/service.py`
- `backend/app/screener/runtime.py`
- `backend/app/api/routes/screener.py`
- `backend/app/watchlists/service.py`
- `backend/app/deployments/service.py`
- `backend/app/brokers/preflight.py`
- `backend/app/brokers/alpaca.py`
- `frontend/src/routes/Screeners.tsx`
- `frontend/src/routes/ScreenerDetail.tsx`
- `frontend/src/routes/Watchlists.tsx`

Current behavior:

- Screener V1 has typed metrics:
  - price
  - avg_volume_20d
  - relative_volume
  - gap_pct
  - change_pct
  - rsi_14
  - atr_14_pct
  - prior_day_close
  - prior_day_range_pct
- Criteria are flat rows with gte/lte/gt/lt/between/eq.
- A ScreenerRun is immutable in concept: rerun creates a new run id.
- Screener can save matched symbols as a new static Watchlist through
  WatchlistService.
- Screener currently resolves explicit, preset, and watchlist universes.
- WatchlistService supports static and dynamic shape, but dynamic snapshot
  behavior is currently placeholder:
  "dynamic resolver pending; using static base".
- Deployment requires watchlist_ids and subscribed_account_ids before start.
- Known honest gap: full persisted active Deployment watchlist expansion into
  runtime components is not yet proven as a complete bridge.

## Provider Decision

Alpaca is the primary provider pack.

Yahoo is not a production provider for this system unless a licensed and stable
Yahoo agreement exists. Yahoo pages are product inspiration only.

Primary official sources:

- Alpaca market movers:
  `https://docs.alpaca.markets/reference/movers-1`
- Alpaca most actives:
  `https://docs.alpaca.markets/v1.3/reference/screener`
- Alpaca market data:
  `https://docs.alpaca.markets/docs/about-market-data-api`
- Alpaca assets:
  `https://docs.alpaca.markets/docs/working-with-assets`
- Alpaca fractional trading:
  `https://docs.alpaca.markets/docs/fractional-trading`

Fallback or optional providers only after Alpaca-first is stable:

- Alpha Vantage:
  `https://www.alphavantage.co/documentation/`
- FMP:
  `https://site.financialmodelingprep.com/developer/docs/stock-screener-api/?direct=true`
- Polygon/Massive:
  `https://polygon.io/docs/rest/stocks/snapshots/top-market-movers`
- Finnhub:
  `https://finnhubio.github.io/`

## Provider Boundary Rules

Alpaca may provide:

- tradable
- active/status
- fractionable
- shortable
- easy_to_borrow
- exchange
- asset class
- market movers
- most actives
- bars/snapshots
- market session context

Alpaca must not own:

- Strategy logic
- Watchlist doctrine
- Deployment runtime ownership
- SignalPlan generation
- Account truth writes outside BrokerSync
- UI workflow semantics

Provider metadata must be recorded as source evidence on ScreenerRun and
WatchlistSnapshot. It must not leak into Strategy state.

Implementation correction from Alpaca/provider review:

- Keep Alpaca-first behavior in Data Center and Screener runtime.
- Do not put provider mode on Watchlist or Deployment.
- If operator override is required, prefer a source-preference field on
  ScreenerVersion or ScreenerRunRequest, such as:
  `auto | alpaca | yahoo`.
- Surface provenance back on ScreenerRun, such as:
  historical_provider, dataset_ids, sources_used, source_freshness.
- Use existing Market Data service defaults where they already exist; do not
  create a hidden parallel provider selector.
- Preserve `HistoricalBarIngestService.ensure_bars` cache-hit behavior.
- Preserve `alpaca_bars_source_from_runtime` as the credential-injected path.

## Human Review Council

Build side by side with these reviewers:

1. Operator/Nanyel
   - The primary user, guide, conscience, and approval standard.
   - Wants AI-assisted workflows, but not black boxes.
   - Rejects raw IDs as primary operator language.

2. Expert Day Trader
   - Uses premarket/open-hour movers.
   - Needs speed, chart-first scanning, one-click save to active worklist,
     and clear session context.

3. Swing/Quant User
   - Needs rerun, compare, versioning, reproducibility, and stable inputs.
   - Cares about what changed since the last run.

4. Alpaca Expert
   - Guards provider correctness, asset capabilities, market data limits,
     rate limits, sessions, tradability, shortability, fractional eligibility,
     and official API usage.

5. Enemy Agent
   - Tries to reject every slice.
   - Looks for vague scope, provider leakage, audit gaps, duplicate runtime,
     UX confusion, weak tests, and spine violations.
   - Does not own the plan, but every finding must be answered or explicitly
     deferred.

## Agent Cost Schedule

Use high-reasoning coordinator work only for architecture, spine boundaries,
provider decisions, and final integration.

Use lower-cost subagents for:

- Endpoint inventory and file mapping.
- Test inventory.
- UI copy scan for raw IDs.
- Provider docs summarization.
- Persona journey review.
- Simple regression checklists.

Do not delegate:

- Final ownership decisions.
- Spine changes.
- Runtime bridge decisions.
- Broker truth boundary decisions.
- Final acceptance.

## What Must Not Happen

- Do not call Yahoo scraping endpoints as the production data backbone.
- Do not put symbols into Strategy.
- Do not let AI emit SignalPlans, orders, broker actions, or deployment starts.
- Do not use Watchlists for exits.
- Do not mutate existing Watchlists silently.
- Do not overwrite ScreenerRuns.
- Do not hard-delete audit history.
- Do not create a second runtime path.
- Do not call Alpaca directly from random UI/backend code.
- Do not expose UUIDs as primary user-facing labels.
- Do not claim dynamic Watchlists are live until the resolver is real.
- Do not skip broker capability validation for fractionable/shortable/tradable
  claims.

## Data Objects To Introduce Or Extend

Inspect existing models before implementing. Use existing tables and patterns
when possible.

Likely additions:

- ScreenerTemplate
- ScreenerExpression
- ScreenerExpressionNode
- ScreenerFieldDefinition
- ScreenerProviderCapability
- ScreenerValidationReport
- ScreenerRunDiff
- MarketListDefinition
- MarketListRun
- RefreshPolicy
- WatchlistSource
- WatchlistRefreshResult
- WatchlistSymbolEvidence
- WatchlistSnapshotDiff
- ScreenerAuditEvent or reuse existing audit/event model if present

Likely expression shape:

```json
{
  "kind": "all",
  "children": [
    {"kind": "criterion", "field": "price", "operator": "lt", "value": 50},
    {"kind": "criterion", "field": "relative_volume", "operator": "gte", "value": 2},
    {"kind": "criterion", "field": "broker.fractionable", "operator": "eq", "value": true}
  ]
}
```

Allowed logical operators:

- all
- any
- not
- criterion

No arbitrary eval. No raw SQL from AI. No provider-specific unvalidated fields.

## API Surface To Plan

Final names can change after inspecting route conventions. Proposed surface:

```text
GET    /api/v1/screeners/fields
GET    /api/v1/screeners/templates
POST   /api/v1/screeners/from-template
POST   /api/v1/screeners/ai/interpret
POST   /api/v1/screeners/validate-expression
POST   /api/v1/screeners/{id}/run
POST   /api/v1/screeners/runs/{run_id}/rerun
GET    /api/v1/screeners/runs/{run_id}/diff?against_run_id=...
POST   /api/v1/screeners/runs/{run_id}/save-as-watchlist
GET    /api/v1/market-lists
POST   /api/v1/market-lists/{template_key}/run
POST   /api/v1/watchlists/{id}/refresh
POST   /api/v1/watchlists/{id}/archive
POST   /api/v1/screeners/{id}/archive
```

Delete rule:

- If no runs and no references: hard delete may be allowed.
- If runs, snapshots, audit events, or deployment references exist: archive.
- If active deployment references it: block until detached or stopped.

## Refresh Model

Screener refresh:

- Manual run creates a new ScreenerRun.
- Rerun creates a new ScreenerRun pinned to the same version and inputs.
- Scheduled run creates a new ScreenerRun with scheduler metadata.
- Live preview may be ephemeral only if clearly marked and not used for
  deployment.

Watchlist refresh:

- Static Watchlist never changes automatically.
- Dynamic Watchlist refresh creates a new WatchlistSnapshot.
- Watchlist refresh must include source run id, template id, provider snapshot,
  symbol evidence, added/removed/stayed diff, and operator/session metadata.
- Deployment entries use the current approved WatchlistSnapshot or resolved
  symbols at the configured boundary.
- Existing positions continue to be managed even if a symbol falls out of a
  refreshed Watchlist.

## Ten Implementation Slices

### Step 1: Current-State Audit And Acceptance Gates

Goal:

Create a precise map of existing Screener, Watchlist, Provider, Deployment, and
runtime bridge behavior.

Tasks:

- Inspect backend and frontend files.
- Confirm route inventory.
- Confirm persistence schemas.
- Confirm where Alpaca data currently enters.
- Confirm all known gaps with code references.
- Write acceptance gates in tests/docs before changing behavior.

Deliverables:

- Updated plan notes with exact file ownership.
- Doctrine test list.
- No behavioral changes unless required to unblock tests.

Agents:

- Coordinator: Codex.
- Lower-cost explorer: file and route inventory.
- Enemy Agent: reject vague or missing ownership.

Exit gate:

- The plan names every touched module.
- No unknown runtime bridge is assumed.

### Step 2: Field Registry And Provider Capability Registry

Goal:

Create a typed registry of every field a Screener can use and every provider
capability needed to compute it.

Tasks:

- Add field definitions for existing metrics.
- Add broker capability fields:
  - broker.tradable
  - broker.fractionable
  - broker.shortable
  - broker.easy_to_borrow
  - broker.active
  - broker.exchange
  - broker.asset_class
- Add source metadata:
  - alpaca_assets
  - alpaca_screener
  - data_center.bar_cache
  - computed_from_bars
- Add validation that unsupported fields fail before run.

Deliverables:

- `GET /screeners/fields` or equivalent.
- Unit tests for field registry.
- No AI yet.

Agents:

- Alpaca Expert: validate field semantics.
- Enemy Agent: attack provider leakage.

Exit gate:

- Every field has type, unit, source, cadence, and unavailable behavior.

### Step 3: Expression Engine

Goal:

Replace flat-only criteria with a typed logical expression engine while
preserving backwards compatibility.

Tasks:

- Add expression AST.
- Support all/any/not/criterion.
- Compile old criteria rows into all([...]) internally.
- Add deterministic validation.
- Add result reasons for pass/fail.
- Add tests for nested logic.

Deliverables:

- Expression domain model.
- Evaluation service.
- Backwards-compatible API behavior.

Agents:

- Coordinator: Codex.
- Lower-cost tester: edge-case matrix.
- Enemy Agent: attack ambiguity and hidden state.

Exit gate:

- No arbitrary eval.
- No string-based filter execution.
- Every pass/fail is explainable.

### Step 4: Alpaca Provider Pack

Goal:

Make Alpaca the main provider pack for market movers, most actives, asset
capabilities, and bar-backed computation.

Tasks:

- Add Alpaca screener adapter for:
  - market movers
  - most actives
- Add Alpaca asset capability lookup/cache.
- Keep all bar-backed metrics through HistoricalBarIngestService.
- Record source evidence and freshness.
- Fail closed on provider errors with readable reason codes.
- Avoid direct random Alpaca calls outside provider/data/broker boundaries.

Deliverables:

- Alpaca provider adapter(s).
- Provider capability tests.
- Rate-limit and unavailable behavior.

Agents:

- Alpaca Expert: primary reviewer.
- Lower-cost explorer: docs and SDK surface.
- Enemy Agent: attack direct-provider leakage.

Exit gate:

- Alpaca is first provider, not core architecture.

### Step 5: Templates And Market Lists

Goal:

Turn common user goals into reusable, visible templates and Yahoo-style market
lists without depending on Yahoo data.

Initial templates:

- Day Gainers
- Day Losers
- Most Active
- 52-Week Gainers
- 52-Week Losers
- Recent 52-Week Highs
- Recent 52-Week Lows
- High Relative Volume
- Premarket Gap Up
- Premarket Gap Down
- Fractionable Momentum
- Shortable Fade Candidates
- Liquid Large Caps
- High Volume ETFs
- User Symbol Basket

Tasks:

- Add template definitions.
- Add template categories:
  - Market Movers
  - Day Trading
  - Premarket
  - Swing
  - Broker Capability
  - User Custom
- Add "Edit in Screener" path.
- Add "Run template now" path.
- Add tests proving templates compile to normal ScreenerVersions.

Deliverables:

- Template API.
- Market list API.
- Seed templates.

Agents:

- Day Trader persona: template usefulness.
- Swing/Quant persona: reproducibility.
- Enemy Agent: attack magic templates.

Exit gate:

- Every template is just typed rules plus source config, not hidden logic.

### Step 6: AI Composer For Screeners

Goal:

Let the operator ask for non-template ideas while keeping AI advisory-only.

Tasks:

- Add AI interpret endpoint:
  - prompt -> suggested template(s)
  - prompt -> typed expression draft
  - prompt -> unsupported clauses
  - prompt -> assumptions
- AI must not run, save, deploy, or mutate.
- Operator must approve before creating a ScreenerVersion.
- Add prompt and compiled output to audit trail.
- Add tests using deterministic fake AI provider.

Examples:

- "Find fractionable stocks under $30 with RVOL over 3."
- "Find shortable open-hour fade candidates."
- "Find 52-week gainers that are still liquid."

Deliverables:

- AI advisory compile endpoint.
- UI-ready response schema.
- Unsupported request report.

Agents:

- Operator/Nanyel persona: approval language.
- Enemy Agent: attack black-box AI.

Exit gate:

- AI cannot mutate runtime state.

### Step 7: Run, Rerun, Compare, Archive, Delete

Goal:

Make test/run/rerun/delete a first-class operator lifecycle.

Tasks:

- Add rerun behavior pinned to exact version/input.
- Add run diff:
  - added
  - removed
  - stayed
  - newly failed
  - reason changes
- Add archive semantics for Screeners and Watchlists.
- Add hard delete only where safe.
- Add active Deployment reference checks.
- Add readable audit and run history.

Deliverables:

- Rerun endpoint.
- Diff endpoint.
- Archive/delete rules.
- Tests for all lifecycle states.

Agents:

- Swing/Quant persona: compare workflow.
- Enemy Agent: attack audit loss.

Exit gate:

- No run history is overwritten.
- Active deployment references cannot be broken silently.

### Step 8: Dynamic Watchlist Refresh

Goal:

Replace the current "dynamic resolver pending" behavior with real dynamic
Watchlist snapshots.

Tasks:

- Define dynamic Watchlist source:
  - screener_version_id
  - template_key
  - provider pack
  - refresh_policy
  - approval policy
- Add manual refresh.
- Add scheduled review mode.
- Add optional auto-snapshot mode only behind explicit operator approval.
- Create new WatchlistSnapshot per refresh.
- Attach symbol evidence and diff.

Deliverables:

- Watchlist refresh service.
- Snapshot evidence.
- Dynamic resolver tests.

Agents:

- Coordinator: Codex.
- Day Trader persona: premarket/open-hour refresh.
- Enemy Agent: attack watchlist-exit confusion.

Exit gate:

- Watchlist refresh affects entries only.
- Existing positions remain exit-managed by Account Positions.

### Step 9: UI Integration And User Journeys

Goal:

Build the operator journey around useful starting points, not blank forms.

Screens:

- Market Lists
- Screener Lab
- Template Library
- AI Screener Composer
- Run History
- Run Compare
- Watchlist Manager
- Dynamic Watchlist Refresh
- Deployment readiness view, if existing deployment UI supports it

UI principles:

- Human-readable names first.
- Symbols and company names before IDs.
- Chart-first for day trader workflows.
- Dense table available for quant workflows.
- Every row explains why it passed and why it is broker-blocked.
- Every AI suggestion visibly says advisory.
- Every run shows source/freshness.

Deliverables:

- Frontend routes/components.
- API schemas.
- UX tests.
- No UUID-primary UI.

Agents:

- Claude coordination required before frontend edits.
- UX reviewer: three personas.
- Enemy Agent: attack operator confusion.

Exit gate:

- Operator can start from a template, AI prompt, static symbol list, or market
  list without guessing raw filter names.

### Step 10: End-To-End Build, Hardening, And Release Gate

Goal:

Everything built end to end.

Required complete flows:

1. Run Alpaca Day Gainers.
2. Edit it as a Screener.
3. Add broker fractionable filter.
4. Run now.
5. Rerun.
6. Compare runs.
7. Save matched symbols as static Watchlist.
8. Create dynamic Watchlist from ScreenerVersion.
9. Refresh dynamic Watchlist to create a new snapshot.
10. Attach Watchlist to a Deployment entry universe without Strategy owning
    symbols.
11. Confirm exits still evaluate Account Positions, not Watchlist membership.
12. Archive a Screener safely.
13. Attempt unsafe delete and see a readable block.
14. Review audit trail from AI/template/provider/run/watchlist snapshot.

Tests:

- Backend unit tests.
- API contract tests.
- Frontend typecheck.
- Frontend vitest.
- Doctrine tests.
- Provider fake tests.
- Alpaca paper opt-in tests if credentials are available.
- E2E browser smoke if dev server can run.

Release gate:

- Strategy remains symbol-agnostic.
- SignalPlans are still Deployment-owned.
- No duplicate runtime exists.
- BrokerSync remains only broker truth writer.
- AI cannot mutate runtime state.
- Watchlists are entry-only.
- Dynamic refresh uses snapshots.
- Runs are immutable.
- UI is human-readable first.
- All new APIs have tests.
- OPERATION_STATUS and coordination ledger are updated.

## Test Plan Summary

Domain tests:

- Field registry validation.
- Expression compile/evaluation.
- Template compile.
- AI advisory compile fake.
- Run/rerun/diff.
- Watchlist snapshot refresh.
- Archive/delete rules.

Provider tests:

- Alpaca movers fake response.
- Alpaca most-active fake response.
- Alpaca asset capability fake response.
- Provider unavailable.
- Provider rate limited.
- Provider returns partial data.
- Direct Alpaca history path.
- Yahoo fallback path where still intentionally supported.
- Cache-hit path with zero provider calls.
- Save-as-watchlist remains create-only through WatchlistService.

Doctrine tests:

- Screener cannot emit SignalPlan.
- Watchlist cannot drive exits.
- Strategy does not store symbols.
- Deployment still requires Watchlist and Account.
- BrokerSync remains only broker truth writer.
- AI cannot save or deploy without operator action.

UI tests:

- Template starts a Screener draft.
- AI output shows assumptions and unsupported clauses.
- Run history shows names/symbols, not raw IDs.
- Compare shows added/removed/stayed.
- Unsafe delete is blocked with readable reason.
- Broker capability blocked rows show readable reason.

E2E smoke:

- Create static watchlist from typed symbols.
- Run Alpaca-backed market list with mocked provider.
- Save results as Watchlist.
- Create dynamic Watchlist from ScreenerVersion.
- Refresh snapshot.
- Attach to Deployment.
- Confirm no Strategy symbol ownership.

## Restart Prompt For New Window

Paste this prompt into a new Codex window:

```text
You are Codex in c:\Users\potij\Projects\Ultimate_Trading_OS_Rebuild.

Read first:
- AGENTS.md
- MAP__MASTER_AGENT_PROMPT.md
- COORDINATION/LOCKS.md
- COORDINATION/INBOX_CODEX.md
- COORDINATION/LEDGER.md
- Operations_Turtle_Shell_Artifacts/OPERATION_STATUS.md
- Operations_Turtle_Shell_Artifacts/ALPACA_FIRST_SCREENER_WATCHLIST_PLAN.md

Your mission:
Execute the 10-step Alpaca-first Screener and Watchlist plan end to end.
Do not stop after analysis. Continue through implementation, verification, and
coordination updates. If context compacts, continue from the plan and latest
ledger. The only acceptable stop is a real blocker, missing credential for an
opt-in live Alpaca test, or tool/session exhaustion.

Hard doctrine:
- Strategy remains symbol-agnostic.
- Watchlists provide entries only.
- Exits come from Account-owned Positions scoped by deployment_id.
- Deployment emits SignalPlans only.
- Account/RiskResolver/Governor/Order/BrokerAdapter/BrokerSync/Position Truth
  remain the trading spine.
- BrokerSync is the only broker truth writer.
- Screener is discovery only.
- AI is advisory only and compiles into visible typed rules.
- Do not use Yahoo scraping as production provider.
- Alpaca is the primary provider pack but not core architecture.

Use subagents:
- Alpaca Expert for provider/API/capability checks.
- UX reviewer for the three users:
  1. Nanyel/operator as guide and conscience.
  2. Expert day trader using premarket/open-hour movers.
  3. Swing/quant user needing rerun/compare/versioning.
- Enemy Agent whose job is to reject vague, overbuilt, spine-breaking,
  under-tested, non-auditable, or UX-hostile work.
- Use lower-cost agents for simple inventory, test mapping, docs summaries, and
  UI copy scans. Keep final architecture and spine decisions local.

Execution:
Start at Step 1 in the plan. Lease files before edits. Coordinate with Claude
before frontend/shared work. After every slice, update tests, ledger,
OPERATION_STATUS, locks, and inbox if shared state changed. Do not silently
revert other users' changes.

Definition of done:
Step 10 complete, including end-to-end flows, tests, audit, archive/delete,
dynamic Watchlist refresh, Alpaca-first providers, AI advisory composer,
templates, run/rerun/compare, UI alignment, and doctrine gates.
```

## Planning Verdict

This plan is approved for execution only if the implementation keeps every
Screener/Watchlist capability on the discovery/universe side of the spine.

The enemy-agent rejection is answered by:

- explicit ownership boundaries,
- provider adapter boundary,
- AI advisory boundary,
- audit model,
- human-readable UI rule,
- dynamic snapshot rule,
- run immutability,
- doctrine tests,
- and Step 10 end-to-end gates.
