# RiskPlan, SignalPlan, RiskDecisionCard, and Backtest Backend Contract

Status: Ready for Codex implementation review
Owner: Nanyel
Purpose: Lock backend and UI requirements so Backtest, Sim Lab, Paper, and Live all use traceable risk decisions instead of hidden sizing assumptions.

---

## 1. Executive Decision

Ultimate Trader must not create a simulated order, backtest trade, paper order, or live order without a traceable risk decision.

The system must use this spine:

```text
FeatureSnapshot
-> SignalEngine
-> CandidateTradeIntent
-> SignalPlanBuilder
-> SignalPlan
-> RiskPlan
-> RiskResolver
-> RiskDecisionCard
-> Governor, where applicable
-> SimulatedBroker or OrderManager
```

The key doctrine is:

```text
SignalPlan describes the trade opportunity and lifecycle intent.
RiskPlan describes the Account or simulation risk policy.
RiskResolver combines SignalPlan + RiskPlan + Account State.
RiskDecisionCard records the sizing and decision trace.
```

No hidden assumptions. No silent sizing. No direct sizing inside Backtest, Sim Lab, or runtime loops.

---

## 2. Core Vocabulary

## 2.1 SignalPlan

SignalPlan is the neutral trade or position-management plan.

It answers:

```text
What is the system proposing to do?
```

SignalPlan must not contain final account-specific quantity.

SignalPlan may contain:

- symbol
- side
- lifecycle intent
- entry plan
- stop plan
- target plan
- runner plan
- logical exit plan
- related position lineage
- opening SignalPlan reference, when managing an existing position
- Strategy and Deployment lineage
- FeatureSnapshot evidence
- warnings

SignalPlan must not contain:

- final quantity
- broker order id
- final approval
- actual fill state
- account-specific buying power decision

## 2.2 SignalPlan Lifecycle Intent

SignalPlan must include a lifecycle intent.

Use:

```text
SignalPlan.intent
```

Allowed values:

```text
open
close
reduce
target
stop
trail
breakeven
runner
logical_exit
```

Meaning:

| Intent | Meaning |
|---|---|
| open | Propose opening a new position. |
| close | Propose fully closing an existing position. |
| reduce | Propose partially reducing an existing position. |
| target | Propose target-based scale-out. |
| stop | Propose protective stop exit. |
| trail | Propose trailing stop update or trailing exit action. |
| breakeven | Propose moving protection to breakeven. |
| runner | Propose runner management action. |
| logical_exit | Propose exit or reduction based on strategy logic. |

Required rule:

```text
Every SignalPlan must say whether it opens a new position or manages an existing position.
```

## 2.3 RiskPlan

RiskPlan is the reusable risk policy attached to an Account or simulation run.

It answers:

```text
How is this Account or simulation allowed to take risk?
```

RiskPlan is product-facing. If the backend already has `RiskProfileVersion`, it may remain as an internal migration name, but the user-facing product should say `RiskPlan`.

RiskPlan belongs to:

- Account, for paper/live runtime
- Simulated account, for Sim Lab and Backtest
- Backtest run request, as an explicit selected risk plan
- Walk-Forward or Optimization output, when recommending a better risk plan later

## 2.4 RiskResolver

RiskResolver is the calculation service.

It answers:

```text
Given this SignalPlan and this RiskPlan, what size is allowed, and why?
```

RiskResolver reads:

- SignalPlan
- RiskPlan
- Account or simulated account state
- cash
- equity
- buying power
- current price
- stop price or stop distance
- existing position
- open orders
- current exposure
- symbol restrictions
- fractional rules
- rounding rules
- max position rules
- daily loss and drawdown rules

RiskResolver emits:

```text
RiskDecisionCard
```

## 2.5 RiskDecisionCard

RiskDecisionCard is the traceable sizing and risk decision artifact.

It answers:

```text
How did the system arrive at this position size and decision?
```

No position size may exist without a RiskDecisionCard.

Required in:

- Backtest
- Sim Lab
- Paper runtime
- Live runtime
- future Walk-Forward
- future Optimization

## 2.6 Governor

Governor is the final protection gate before real order creation.

Governor should read the RiskDecisionCard, but it should not duplicate the sizing math.

Research surfaces may skip live Governor approval, but they must still create RiskDecisionCards.

---

## 3. Target Backend Flow By Mode

## 3.1 Backtest Flow

Backtest must use the unified research spine.

```text
Historical bars from Data Center
-> BatchFeatureEngine
-> FeatureSnapshot
-> SignalEngine.evaluate()
-> CandidateTradeIntent
-> SignalPlanBuilder.build_from_candidate()
-> SignalPlan
-> selected RiskPlan
-> RiskResolver
-> RiskDecisionCard
-> HistoricalReplayEngine / SimulatedBroker
-> simulated fills
-> trade ledger
-> metrics
-> Monte Carlo
```

Backtest must not:

- use synthetic `_simulate()`
- fabricate one trade per symbol
- compute features outside FeatureEngine
- size trades directly from capital without RiskResolver
- create trades without RiskDecisionCard
- mark a Strategy live-ready by itself

## 3.2 Sim Lab Flow

Sim Lab must use the same SignalPlan and RiskDecisionCard path as Backtest.

```text
FeatureSnapshot
-> SignalEngine
-> CandidateTradeIntent
-> SignalPlanBuilder
-> SignalPlan
-> Simulated RiskPlan
-> RiskResolver
-> RiskDecisionCard
-> SimulatedBroker
-> simulated orders/fills/positions
```

Sim Lab must not rely only on `HistoricalReplayEngine._size_order()` as the final sizing authority unless that method is refactored to call RiskResolver and produce RiskDecisionCard.

## 3.3 Paper Broker Runtime Flow

```text
FeatureSnapshot
-> SignalEngine
-> CandidateTradeIntent
-> SignalPlanBuilder
-> SignalPlan
-> Account RiskPlan
-> RiskResolver
-> RiskDecisionCard
-> Governor
-> OrderManager
-> BrokerAdapter
-> BrokerSync
```

## 3.4 Live Broker Runtime Flow

Same as Paper Runtime, but against a live broker account.

```text
SignalPlan
-> Account RiskPlan
-> RiskResolver
-> RiskDecisionCard
-> Governor
-> OrderManager
-> BrokerAdapter
-> BrokerSync
```

Live Runtime must never skip Governor.

---

## 4. RiskPlan Product Model

## 4.1 RiskPlan Entity

Minimum fields:

```text
RiskPlan
  risk_plan_id
  name
  description
  status: draft | active | archived
  risk_score: 0..10
  risk_tier: conservative | balanced | aggressive | custom
  version
  created_at
  updated_at
  created_by
  ai_generated: true | false
  ai_summary
  source: manual | ai_generated | optimization_generated | walk_forward_recommended
```

## 4.2 RiskPlan Versioning

RiskPlans must be versioned.

A BacktestRun, SimLabSession, Account, Paper run, or Live order must reference the exact RiskPlan version used.

Minimum version fields:

```text
RiskPlanVersion
  risk_plan_version_id
  risk_plan_id
  version
  status: draft | active | deprecated
  config_fingerprint
  created_at
  activated_at
  archived_at
```

## 4.3 RiskPlan Config

Minimum config:

```text
RiskPlanConfig
  sizing_method:
    fixed_shares | fixed_notional | risk_percent | volatility_adjusted | account_percent | custom

  fixed_shares
  fixed_notional
  risk_per_trade_pct
  account_allocation_pct
  max_trade_notional
  min_trade_notional

  max_position_notional
  max_position_pct_of_equity
  max_symbol_exposure_pct
  max_sector_exposure_pct
  max_gross_exposure_pct
  max_net_exposure_pct
  max_open_positions
  max_open_risk_pct

  max_daily_loss_pct
  max_drawdown_pct
  max_trades_per_day
  cooldown_after_loss_minutes

  fractional_quantity_allowed
  whole_share_rounding:
    floor | round | ceil

  min_quantity
  max_quantity

  stop_required: true | false
  reject_if_no_stop: true | false
  default_stop_policy

  target_required: true | false
  runner_allowed: true | false

  allow_scale_in: true | false
  allow_scale_out: true | false
  allow_short: true | false
  allow_extended_hours: true | false

  symbol_restrictions
  asset_class_restrictions
  account_mode_restrictions
```

## 4.4 Risk Score

RiskPlan should expose a 0 to 10 risk score.

Example:

| Score | Meaning |
|---|---|
| 0 | No trading or observation only. |
| 1-2 | Very conservative. |
| 3-4 | Conservative. |
| 5-6 | Balanced. |
| 7-8 | Aggressive. |
| 9-10 | Very aggressive or experimental. |

AI may help estimate risk_score, but deterministic rules must store the final value.

AI may say:

```text
This RiskPlan appears aggressive because it risks 2 percent per trade, allows 8 concurrent positions, and allows extended-hours trading.
```

AI must not silently change RiskPlan settings.

## 4.5 Account Relationship

An Account should have a default RiskPlan.

```text
Account
  account_id
  default_risk_plan_id
  default_risk_plan_version_id
```

Account may support overrides later:

```text
AccountDeploymentRiskOverride
  account_id
  deployment_id
  risk_plan_version_id
```

But V1 should keep it simple:

```text
Account -> default RiskPlan
Backtest/Sim Lab -> selected RiskPlan
```

---

## 5. RiskDecisionCard Contract

RiskDecisionCard must be persisted and queryable.

## 5.1 Minimum Fields

```text
RiskDecisionCard
  risk_decision_id
  mode: backtest | sim_lab | paper | live | walk_forward | optimization
  run_id
  session_id
  account_id
  simulated_account_id
  strategy_id
  strategy_version_id
  deployment_id
  signal_plan_id
  candidate_trade_intent_id
  feature_snapshot_id
  symbol
  side
  lifecycle_intent
  timestamp

  risk_plan_id
  risk_plan_version_id
  risk_score
  risk_tier

  account_equity
  account_cash
  buying_power
  current_price
  entry_price
  stop_price
  stop_distance
  stop_distance_pct

  sizing_method
  formula_used
  raw_quantity
  rounded_quantity
  final_quantity
  final_notional
  rejected_quantity
  capped_quantity

  max_loss_estimate
  risk_amount_requested
  risk_amount_allowed
  buying_power_required
  projected_gross_exposure
  projected_net_exposure
  projected_symbol_exposure
  projected_open_risk

  existing_position_quantity
  existing_position_notional
  existing_open_orders_count
  existing_open_order_notional

  fractional_quantity_allowed
  whole_share_rounding
  constraints_applied
  violations
  warnings
  decision: approved | rejected | reduced | capped | skipped | requires_operator
  reason_codes
  human_summary

  risk_resolver_version
  config_fingerprint
  created_at
```

## 5.2 Human Explanation

Each RiskDecisionCard must provide a plain-language explanation.

Example:

```text
Approved 42 shares of SPY because the SignalPlan proposed an open long with a stop 2.35 dollars below entry. The selected Balanced RiskPlan allows 1.0 percent account risk per trade. With simulated equity of 100,000 dollars, max allowed risk is 1,000 dollars. Raw quantity was 425.53 shares, capped to 42 shares by max position notional and whole-share rounding.
```

## 5.3 Calculation Trace

RiskDecisionCard must include machine-readable calculation steps.

Example:

```json
{
  "steps": [
    {"name": "risk_budget", "formula": "equity * risk_per_trade_pct", "inputs": {"equity": 100000, "risk_per_trade_pct": 0.01}, "output": 1000},
    {"name": "stop_distance", "formula": "entry_price - stop_price", "inputs": {"entry_price": 500, "stop_price": 497.5}, "output": 2.5},
    {"name": "raw_quantity", "formula": "risk_budget / stop_distance", "inputs": {"risk_budget": 1000, "stop_distance": 2.5}, "output": 400},
    {"name": "rounding", "formula": "floor(raw_quantity)", "inputs": {"raw_quantity": 400}, "output": 400}
  ]
}
```

No black-box sizing.

---

## 6. Backtest Requirements

## 6.1 Backtest Request Must Include RiskPlan

Backtest run request must include one of:

```text
risk_plan_version_id
```

or

```text
risk_plan_mode: default | selected | generated_candidate
```

For V1, require:

```text
risk_plan_version_id
```

If not provided, backend may default to a configured System Default RiskPlan only if the response clearly says which RiskPlan was used.

## 6.2 Backtest Run Metadata

BacktestRun must store:

```text
backtest_run_id
strategy_id
strategy_version_id
risk_plan_id
risk_plan_version_id
symbols
start
end
timeframe
initial_capital
source
cost_model
monte_carlo_config
feature_plan_id
historical_dataset_ids
created_at
status
```

## 6.3 Trade Ledger Must Link RiskDecisionCard

Each trade and simulated order must link to:

```text
signal_plan_id
risk_decision_id
risk_plan_version_id
```

## 6.4 Backtest Detail Must Show Risk Trace

Backtest detail must allow operator to click:

- trade
- order
- fill
- position lifecycle event

And see:

- SignalPlan
- RiskDecisionCard
- selected RiskPlan
- sizing formula
- constraints applied
- warnings

---

## 7. Walk-Forward and Optimization Future Direction

Do not implement full Walk-Forward or Optimization in the current Backtest slice unless already approved.

But design must support them.

## 7.1 Walk-Forward RiskPlan Recommendation

Walk-Forward may later test multiple RiskPlan variants and recommend the most stable one.

Output:

```text
RiskPlanRecommendation
  source: walk_forward
  candidate_risk_plan_version_id
  score
  stability_metrics
  drawdown_metrics
  out_of_sample_metrics
  explanation
```

## 7.2 Optimization Generated RiskPlan

Optimization may later generate RiskPlan candidates.

Examples:

- risk_per_trade_pct sweep
- max_positions sweep
- max_daily_loss sweep
- stop-required policy sweep
- exposure cap sweep

Generated candidates must be saved as draft RiskPlans first. They must not become account defaults without user approval.

---

## 8. Backend API Requirements

## 8.1 RiskPlan APIs

Add or verify:

```text
GET    /api/v1/risk-plans
POST   /api/v1/risk-plans
GET    /api/v1/risk-plans/{risk_plan_id}
PATCH  /api/v1/risk-plans/{risk_plan_id}
POST   /api/v1/risk-plans/{risk_plan_id}/versions
GET    /api/v1/risk-plans/{risk_plan_id}/versions
POST   /api/v1/risk-plans/{risk_plan_id}/activate
POST   /api/v1/risk-plans/{risk_plan_id}/archive
POST   /api/v1/risk-plans/ai-draft
```

## 8.2 Account RiskPlan APIs

```text
GET   /api/v1/accounts/{account_id}/risk-plan
PUT   /api/v1/accounts/{account_id}/risk-plan
```

## 8.3 RiskDecisionCard APIs

```text
GET /api/v1/risk-decisions/{risk_decision_id}
GET /api/v1/risk-decisions?run_id=...
GET /api/v1/risk-decisions?signal_plan_id=...
GET /api/v1/risk-decisions?account_id=...
```

## 8.4 Backtest Request Extension

```text
POST /api/v1/research/backtests
```

Must accept:

```json
{
  "strategy_version_id": "...",
  "risk_plan_version_id": "...",
  "symbols": ["SPY"],
  "start": "2020-01-01",
  "end": "2024-12-31",
  "timeframe": "1d",
  "initial_capital": 100000,
  "cost_model": {
    "commission_per_trade": 0,
    "slippage_bps": 0
  },
  "source": "yahoo",
  "monte_carlo": {
    "enabled": true,
    "method": "trade_bootstrap",
    "replications": 1000,
    "seed": 42
  }
}
```

---

## 9. Frontend Screens Required

The user must be able to see, create, edit, and select RiskPlans.

## 9.1 Navigation

Add a top-level or Components-level screen:

```text
Risk Plans
```

Preferred placement:

```text
Build / Components / Risk Plans
```

Alternative if navigation is flatter:

```text
Components -> Risk Plans
```

Do not hide RiskPlans only inside Account settings. They are reusable trading components.

## 9.2 Risk Plans List Screen

Purpose:

```text
Manage reusable RiskPlans and see which Accounts or research runs use them.
```

Layout:

```text
Header
  Risk Plans
  Create Risk Plan
  Generate with AI
  Compare

Filters
  Status: draft | active | archived
  Tier: conservative | balanced | aggressive | custom
  Score: 0..10
  Source: manual | ai | optimization | walk_forward

Table / Cards
  Name
  Risk Score
  Tier
  Sizing Method
  Risk per Trade
  Max Positions
  Max Daily Loss
  Max Open Risk
  Linked Accounts
  Last Used
  Status
  Actions
```

Actions:

- View
- Edit Draft
- Duplicate
- Create Variant
- Archive
- Assign to Account
- Use in Backtest
- Compare

## 9.3 Risk Plan Detail Screen

Tabs:

```text
Overview
Sizing
Exposure Limits
Loss Limits
Position Rules
Account Assignments
Backtest Usage
Decision Cards
Versions
AI Notes
```

Overview should show:

- risk score
- tier
- status
- description
- human explanation
- created by
- source
- active version
- config fingerprint

Sizing tab:

- sizing method
- fixed shares
- fixed notional
- risk per trade percent
- account allocation percent
- stop required
- rounding rule
- fractional quantity allowed

Exposure Limits tab:

- max trade notional
- max position percent
- max symbol exposure
- max sector exposure
- max gross exposure
- max net exposure
- max open positions
- max open risk percent

Loss Limits tab:

- max daily loss
- max drawdown
- cooldown after loss
- max trades per day

Position Rules tab:

- allow scale-in
- allow scale-out
- allow short
- allow extended hours
- runner allowed
- target required
- stop required

Account Assignments tab:

- accounts using this RiskPlan
- account mode
- paper/live
- active status
- last risk decision

Backtest Usage tab:

- recent backtests using this RiskPlan
- metrics
- Monte Carlo summary
- warnings

Decision Cards tab:

- recent RiskDecisionCards
- approved/rejected/reduced/capped counts
- top rejection reasons

Versions tab:

- version history
- changes between versions
- activate version
- duplicate version

AI Notes tab:

- AI-generated explanation
- risk score reasoning
- warnings
- suggested improvements

## 9.4 Create / Edit RiskPlan Drawer

Fields:

```text
Name
Description
Risk Score 0..10
Risk Tier
Sizing Method
Risk Per Trade Percent
Fixed Shares
Fixed Notional
Max Trade Notional
Max Position Percent
Max Symbol Exposure
Max Gross Exposure
Max Open Positions
Max Daily Loss
Max Drawdown
Fractional Allowed
Rounding Rule
Stop Required
Target Required
Runner Allowed
Allow Short
Allow Extended Hours
```

Add validation feedback:

- missing stop policy while risk percent sizing is selected
- risk per trade too high
- max exposure too high
- whole-share rounding conflict with fractional allowed
- aggressive settings warning

## 9.5 Backtest Run Drawer Update

Backtest drawer must include:

```text
RiskPlan selector
```

Display inline:

```text
Risk Score
Risk Tier
Sizing Method
Risk Per Trade
Max Position Limit
```

Add link:

```text
View RiskPlan
```

Backtest cannot run without a selected RiskPlan unless a clearly visible System Default RiskPlan is applied.

## 9.6 Risk Decision Card UI

RiskDecisionCard should appear as a drawer or detail panel.

Entry points:

- Backtest trade ledger row
- Backtest chart trade marker
- Sim Lab decision inspector
- Sim Lab event stream
- Account order detail
- Position detail
- Operations decision trace

Card layout:

```text
Header
  Approved 42 shares of SPY
  RiskPlan: Balanced Momentum Risk v3
  SignalPlan: Open Long SPY
  Mode: Backtest

Decision Summary
  Approved / Rejected / Reduced / Capped
  Human explanation

Inputs
  Equity
  Cash
  Buying Power
  Price
  Stop
  Stop Distance
  Existing Position
  Open Orders

Formula
  Step-by-step calculation

Constraints Applied
  Max trade notional
  Max exposure
  Rounding
  Fractional rule

Warnings / Violations
  List

Lineage
  FeatureSnapshot
  CandidateTradeIntent
  SignalPlan
  RiskPlan Version
  RiskResolver Version
```

---

## 10. AI Requirements

AI may help create RiskPlans, but deterministic validators own enforcement.

AI may:

- draft a RiskPlan from plain English
- explain a RiskPlan
- suggest risk_score
- compare RiskPlans
- suggest improvements
- generate optimization candidates

AI may not:

- silently assign a RiskPlan to an Account
- approve live risk
- override RiskResolver
- change RiskDecisionCard results
- hide risk warnings
- mark a Strategy ready for live

AI draft prompt should produce:

```text
name
description
risk_score
risk_tier
sizing_method
risk_per_trade_pct
limits
warnings
explanation
```

---

## 11. Acceptance Tests

## 11.1 Backend Tests

Required tests:

- RiskPlan can be created, versioned, activated, and archived.
- Account can be assigned a default RiskPlan.
- Backtest request requires RiskPlan or explicitly applies System Default RiskPlan.
- SignalPlanBuilder is called during Backtest replay.
- SignalPlanBuilder is called during Sim Lab replay.
- RiskResolver is called after SignalPlan creation.
- RiskDecisionCard is created for every sized SignalPlan.
- RiskDecisionCard records formula, inputs, constraints, final quantity, and decision.
- Backtest trade ledger links to risk_decision_id.
- Sim Lab event log links to risk_decision_id.
- Runtime order links to risk_decision_id.
- No simulated order may be created without risk_decision_id.
- No real order may be created without risk_decision_id.
- RiskDecisionCard is persisted and queryable by run_id, signal_plan_id, and account_id.
- Same FeatureSnapshot produces same CandidateTradeIntent and SignalPlan across Chart Lab, Sim Lab, and Backtest.
- Backtest no longer calls synthetic `_simulate()`.

## 11.2 Frontend Tests

Required tests:

- Risk Plans list renders.
- Create RiskPlan drawer validates fields.
- RiskPlan detail screen shows tabs.
- Backtest drawer includes RiskPlan selector.
- Backtest request includes risk_plan_version_id.
- RiskDecisionCard drawer opens from Backtest trade ledger.
- RiskDecisionCard drawer shows formula steps and constraints.
- AI-generated RiskPlan requires user save/approval.

## 11.3 Guardrail Tests

- No sizing function may return final quantity without creating RiskDecisionCard.
- HistoricalReplayEngine sizing path must call RiskResolver or an approved adapter that emits RiskDecisionCard.
- Backtest and Sim Lab must not use separate sizing logic.
- FeatureEngine remains the only feature computation path.
- SignalPlan remains neutral and does not contain final account quantity.

---

## 12. Implementation Order For Codex

Do this in slices.

## Slice 1: Audit and Name Mapping

Verify current names:

- RiskProfileVersion
- RiskResolver
- SignalPlan
- SignalPlanBuilder
- HistoricalReplayEngine._size_order
- BacktestExecutionService._simulate
- SimLabBatchRunService
- OrderManager.create_signal_plan_order

Produce a short mapping:

```text
Product RiskPlan -> backend RiskProfileVersion or new RiskPlan alias
RiskDecisionCard -> new model
RiskResolver -> existing service to extend
```

## Slice 2: RiskPlan Backend Contract

- Add product-facing RiskPlan route/model or alias current RiskProfileVersion cleanly.
- Add versioning if missing.
- Add Account default RiskPlan assignment.
- Add tests.

## Slice 3: RiskDecisionCard Model

- Add RiskDecisionCard domain model.
- Add persistence.
- Add API read routes.
- Add tests.

## Slice 4: RiskResolver Emits RiskDecisionCard

- Extend RiskResolver so every sizing output produces RiskDecisionCard.
- Preserve existing sizing behavior.
- Add formula trace.
- Add constraints trace.

## Slice 5: Insert SignalPlan Into Research Spine

- Update Sim Lab / HistoricalReplayEngine to call SignalPlanBuilder after CandidateTradeIntent.
- Update Backtest to use HistoricalReplayEngine, SignalPlanBuilder, RiskResolver, and RiskDecisionCard.
- Remove synthetic Backtest `_simulate()`.

## Slice 6: Backtest RiskPlan Selection

- Extend Backtest request schema with risk_plan_version_id.
- Persist risk_plan_version_id on BacktestRun.
- Link trades to risk_decision_id.

## Slice 7: Frontend RiskPlan Screens

- Risk Plans list
- RiskPlan detail
- Create/Edit drawer
- Account assignment view
- Backtest selector
- RiskDecisionCard drawer

## Slice 8: Verification

Run:

```text
pytest backend/tests/unit/research/test_backtest_spine_integration.py
pytest backend/tests/unit/research/test_monte_carlo.py
pytest backend/tests/unit/risk_resolver
pytest backend/tests/unit/api/test_research_run_routes.py
pytest backend/tests/unit/api/test_frontend_api_contract.py
npm test
```

Also run the full backend unit suite if shared models changed.

---

## 13. Non-Negotiables

- No final quantity without RiskDecisionCard.
- No Backtest synthetic engine.
- No separate Sim Lab sizing shortcut.
- No duplicated feature computation.
- No SignalPlan with final account quantity.
- No real order without Governor.
- No UI hiding RiskPlan selection.
- No AI-generated RiskPlan silently attached to Account.
- No live-readiness approval from Backtest alone.
- No missing lineage from FeatureSnapshot to SignalPlan to RiskDecisionCard to Trade/Order.

---

## 14. Final Backend Doctrine Sentence

Use this sentence in code comments and docs:

```text
RiskPlan belongs to the Account or selected research run. SignalPlan describes the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan, and current account or simulated account state to produce a RiskDecisionCard. No simulated or real order may be created without that RiskDecisionCard.
```
