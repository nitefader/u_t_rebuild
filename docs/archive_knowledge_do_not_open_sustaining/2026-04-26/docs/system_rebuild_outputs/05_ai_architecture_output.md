AI Architecture Output
1. AI System Overview
AI is an assistant layer, not an authority layer.

AI may propose:

Programs
Strategies
Strategy Controls
Risk Profiles
Execution Styles
Universes
watchlist candidates
parameter variants
backtest plans
optimization ranges
context notes
AI may not enforce:

feature semantics
signal truth
risk approval
order creation
governor approval
broker execution
live safety
Final rule:

AI suggests.
Feature Engine validates.
Deterministic components execute.
Governor approves.
Broker Adapter submits.
AI output must always pass deterministic validation before it becomes usable.

Core AI services:

AI Program Builder
AI Strategy Generator
AI Watchlist Analyzer
AI Signal Context Analyzer
AI Backtest / Optimization Assistant
All AI outputs are stored as drafts until accepted, validated, and versioned.

2. AI Program Builder
AI Program Builder takes plain English and proposes a complete Program.

Input example:

Build an intraday ORB strategy for liquid large caps.
Trade 5m bars.
Use 15-minute opening range breakout.
Avoid earnings days.
Risk 0.5% per trade.
Use bracket orders with 2R target and 1R stop.
Only trade symbols with strong premarket volume.
Output:

ProgramDraft
  StrategyDraft
  StrategyControlsDraft
  RiskProfileDraft
  ExecutionStyleDraft
  UniverseDraft
  reuse_decisions
  validation_results
  unresolved_questions
AI Program Builder must decide for each component:

use existing
create variant
create new
Builder flow:

Plain English request
→ intent extraction
→ component search
→ reuse/variant/new decision
→ registry-compatible feature generation
→ draft Program assembly
→ Feature Planner validation
→ component boundary validation
→ user review
→ save as draft Program
The builder may not create a deployable Program directly.

It must produce a draft requiring human review.

Required Builder Output
For every generated component, AI must explain:

why this component exists
which existing components were considered
why it reused or did not reuse them
which features it requires
which consumers support those features
paper/live compatibility status
known limitations
Required Validation
AI Program Builder output must pass:

Feature Registry validation
Program boundary validation
component completeness validation
consumer compatibility validation
paper/live eligibility validation if requested
If validation fails, the UI shows exact blockers.

Example:

Blocked:
- Feature "supertrend" is not supported.
- 60m timeframe is invalid; use 1h.
- Strategy contains position sizing fields; move them to Risk Profile.
3. AI Component Reuse Logic
AI must prefer reuse over creating duplicates.

Component reuse order:

1. Exact existing component
2. Existing component with safe parameter variant
3. New component
Similarity Matching
AI searches existing components by:

name
tags
timeframe
duration mode
feature requirements
risk limits
execution behavior
universe rules
previous validation status
Reuse Decision Rules
Use existing when:

component behavior matches request
params are identical or acceptable
component is current and not deprecated
component feature compatibility matches target mode
Create variant when:

same concept but different timeframe
same strategy family but different params
same risk profile but different max loss/sizing
same execution style but different bracket/trailing behavior
existing component is validated and variant is small
Create new when:

no close match exists
existing component violates boundary rules
existing component uses unsupported features
existing component is deprecated
requested behavior is materially different
AI must not silently clone near-duplicates.

Every new or variant component needs:

source_request
parent_component_id if variant
diff_summary
AI generation metadata
validation status
4. AI Strategy Generator
AI Strategy Generator creates Strategy drafts only.

It does not create Risk Profiles, Execution Styles, Strategy Controls, or Universes unless called through AI Program Builder.

Supported strategy families for v1:

ORB breakout
VWAP pullback
EMA trend continuation
RSI mean reversion
ATR volatility breakout
prior-day high/low breakout
gap fade
Ichimoku trend filter, only if registry supports required features
Hard rule:

A named strategy is only supported if every required feature exists in the Feature Registry.
If Ichimoku is not in the registry, AI may describe it but cannot generate a deployable Ichimoku Strategy.

Timeframe Conversion
AI may convert strategy concepts between:

intraday
swing
position
But conversion must be explicit.

Example:

Intraday ORB:
  5m execution
  15m opening range
  same-session exit

Swing breakout:
  1d execution
  prior 20-day high
  multi-day hold
  no ORB
AI cannot simply change 5m to 1d.

It must adjust:

features
controls
hold assumptions
event sensitivity
risk expectations
execution style assumptions
Parameter Variants
AI may generate parameter variants for testing.

Example:

ORB windows: 5, 15, 30 minutes
ATR stop lengths: 14, 20
Target R multiples: 1.5, 2.0, 3.0
RSI thresholds: 25/75, 30/70, 35/65
Variants are test candidates, not recommendations.

Each variant must include:

hypothesis
changed params
expected behavior
risk of overfit
required backtest/validation plan
5. AI Watchlist Analyzer
AI Watchlist Analyzer builds dynamic universes.

It outputs a UniverseDraft or WatchlistCandidateSet.

Inputs:

price action
volume
relative volume
gap %
trend features
volatility
earnings/events
sector/industry metadata
news, optional
existing watchlists
broker tradability constraints
Outputs:

symbols
long_bias | short_bias | neutral
confidence_score
reasoning
feature evidence
event/news evidence if used
expires_at
refresh_policy
Required Output Shape
WatchlistCandidate
  symbol
  bias
  confidence
  reasons
  evidence
  exclusions
  data_timestamp
Confidence Rules
Confidence is not trading permission.

It means:

confidence in watchlist inclusion, not confidence the trade will win
AI confidence cannot bypass:

Strategy signal
Strategy Controls
Risk Profile
Portfolio Governor
broker restrictions
Dynamic Universe Rules
Dynamic universes must be versioned snapshots.

A Program must reference a frozen Universe snapshot for backtest/sim reproducibility.

Live/paper may use a refresh policy, but every refresh produces a new resolved snapshot.

No runtime trade may occur without knowing which Universe snapshot admitted the symbol.

News Use
News is optional and expensive.

If used, AI must store:

source
timestamp
headline/reference
summary
symbol relevance
staleness
News cannot be the only reason for symbol inclusion in v1. It must be supporting context.

6. AI Signal Context Analyzer
AI Signal Context Analyzer is lightweight and optional.

It runs after deterministic candidate signal generation and before final execution approval.

It may add context such as:

recent news
macro event awareness
earnings proximity
sentiment summary
abnormal headline risk
sector context
It may output:

context_note
risk_flag
confidence_note
suggested_operator_review
It may not output:

approve_trade
reject_trade
override_signal
override_governor
change_position_size
change_order_type
submit_order
Final deterministic handling:

Signal Engine emits candidate
→ Strategy Controls / Risk / Execution Style process candidate
→ AI context may attach advisory note
→ Portfolio Governor may consume AI risk_flag only if explicitly configured
→ Governor remains final authority
AI context default mode:

advisory only
Allowed AI context flags:

news_risk_high
macro_event_nearby
earnings_uncertain
sentiment_conflict
data_stale
operator_review_suggested
If AI context is unavailable, trading must continue according to deterministic rules unless the Program explicitly requires context availability. Default is not required.

7. AI Backtest / Optimization Assistant
This assistant helps plan tests. It does not judge deployability alone.

It may suggest:

parameter ranges
ablation tests
walk-forward configurations
symbol subsets
stress scenarios
slippage sensitivity tests
overfit warnings
next experiments
It may analyze:

backtest metrics
trade distribution
walk-forward results
drawdown profile
parameter sensitivity
feature usage
market regime split
It may not:

mark paper-ready
mark live-ready
fabricate OOS results
hide missing evidence
optimize directly against live results without explicit user action
Overfit Detection
AI can flag possible overfit based on deterministic evidence:

large IS/OOS gap
small trade count
high parameter sensitivity
one-symbol dependency
one-month performance concentration
fragile win rate
unrealistic profit factor
too many tuned parameters
AI must label these as warnings unless backed by explicit validation rules.

Example:

Overfit warning:
The best variant has 84% of profit from 3 trades and fails 4 of 7 OOS folds.
Do not promote. Test simpler parameter ranges and longer OOS windows.
8. Data Inputs
AI can read only approved inputs.

Approved inputs:

Feature Vocabulary Catalog
existing component library
Program drafts
Strategy definitions
Validation Evidence
Backtest metrics
Walk-forward summaries
Simulation evidence
Universe snapshots
market metadata
event calendar
news summaries if enabled
operator prompts
AI must not read:

raw broker credentials
secret keys
encrypted credential payloads
private account tokens
unredacted logs containing secrets
Broker/account data available to AI must be sanitized:

paper/live mode
equity range or rounded equity
position symbols if permitted
risk state
drawdown state
no credentials
For cost control, AI should consume summaries before raw data.

Preferred input order:

structured summaries
feature catalogs
component metadata
validation summaries
selected detailed artifacts only when requested
9. Storage Model
AI outputs are stored as auditable drafts and suggestions.

Required models:

AIGenerationRequest
AIGenerationResult
AIComponentProposal
AIProgramDraft
AIWatchlistAnalysis
AISignalContextNote
AIOptimizationSuggestion
AIGenerationRequest
Stores:

id
user_prompt
task_type
model_used
input_artifact_refs
created_by
created_at
cost_estimate
AIGenerationResult
Stores:

request_id
status
raw_model_output
parsed_output
validation_errors
warnings
token_usage
cost_actual
AIComponentProposal
Stores:

component_type
proposed_action: use_existing | create_variant | create_new
existing_component_id
parent_component_id
draft_payload
diff_summary
reasoning
validation_status
AIProgramDraft
Stores:

strategy_proposal_id
controls_proposal_id
risk_proposal_id
execution_proposal_id
universe_proposal_id
feature_plan_validation_status
paper_live_compatibility
human_review_status
AIWatchlistAnalysis
Stores:

universe_snapshot_id
candidate_symbols
biases
confidence_scores
reasoning
data_sources
expires_at
AISignalContextNote
Stores:

candidate_trade_intent_id
timestamp
symbol
flags
summary
sources
expires_at
AIOptimizationSuggestion
Stores:

source_run_ids
suggested_tests
parameter_ranges
overfit_warnings
priority
reasoning
All accepted AI drafts become normal deterministic components with AI provenance attached.

AI provenance must remain visible but not change execution behavior.

10. Frontend UX
AI UX must make review and validation unavoidable.

AI Program Builder UI
Required panels:

Prompt
Interpreted Intent
Component Reuse Decisions
Generated Draft Components
Feature Compatibility
Validation Blockers
Cost Estimate
Review / Accept
The user must see:

reused components
variants
new components
unsupported features
paper/live support status
boundary violations
Primary action:

Save Draft Program
Not allowed as primary action:

Deploy
Start Paper
Start Live
AI Strategy Generator UI
Required panels:

Strategy family
timeframe profile
generated conditions
feature references
parameter variants
registry compatibility
validation errors
AI Watchlist Analyzer UI
Required panels:

candidate symbols
bias
confidence
reasons
data timestamp
expiry
included/excluded explanation
create Universe snapshot
AI Signal Context UI
Displayed as advisory badges:

news risk
macro nearby
sentiment conflict
operator review suggested
No green “AI approved” labels.

AI Optimization Assistant UI
Required panels:

next suggested tests
parameter ranges
overfit warnings
evidence gaps
cost estimate
launch selected tests
AI language must avoid certainty.

Bad:

This strategy will be profitable.
Allowed:

This variant is worth testing because it reduces parameter count and targets the failure seen in OOS fold 3.
11. Cost Strategy
AI must be cost-aware by design.

Default model policy:

cheap/free model first
expensive model only for complex synthesis
no expensive model in tight runtime loops
cache all reusable outputs
summarize before sending long artifacts
Task routing:

Task	Model Class
Feature compatibility check	no LLM; deterministic validator
Component search/reuse	embeddings or local similarity first
Simple strategy template generation	cheap model or deterministic template
Program synthesis	mid-tier model
Long audit of backtest results	mid-tier model with summaries
News summarization	cheap model with strict source limits
Signal context note	cheap fast model or deterministic rules
Live pre-execution context	disabled by default; cheap model only if explicitly enabled
Final architecture synthesis	expensive model allowed manually
Cost controls:

per-task budget
per-day budget
user confirmation above threshold
token limits
artifact summarization
result caching
dedupe repeated prompts
batch watchlist analysis
no AI calls per symbol per bar
Signal Context Analyzer must not run on every bar for every symbol.

Allowed cadence:

on candidate signal only
on watchlist refresh
on major event update
manual request
12. Safety Rules
AI cannot create unsupported features.

AI cannot define feature semantics.

AI cannot bypass Feature Planner.

AI cannot mark a Program deployable.

AI cannot submit orders.

AI cannot call Alpaca.

AI cannot override Strategy Controls.

AI cannot override Risk Profile.

AI cannot override Portfolio Governor.

AI cannot change position size at runtime.

AI cannot change order type at runtime.

AI cannot flatten, pause, resume, or kill anything.

AI cannot hide validation blockers.

AI cannot fabricate backtest, walk-forward, or simulation results.

AI cannot use news as sole permission for a trade.

AI context is advisory unless explicitly configured as a Governor input flag.

If AI fails, deterministic trading continues unless the Program explicitly requires AI context.

AI-generated components are drafts until human accepted.

Accepted AI components are executed by deterministic engines only.

AI must store provenance for every suggestion.

AI must not read secrets.

AI must not output broker credentials.

AI must not label anything “safe” without deterministic validation.

AI must not produce live-trading actions from plain English.

All AI runtime outputs must expire.

13. Implementation Plan
Create AI boundary contract
Define what AI can output:

draft components
suggestions
context notes
watchlist candidates
test plans
Block all execution actions.

Generate Feature Vocabulary Catalog from registry
AI must use this catalog.

Do not hand-maintain AI feature lists.

Build deterministic validators first
Before model integration:

feature reference validator
Program boundary validator
component completeness validator
consumer compatibility validator
Implement component search
Use deterministic filters first:

component type
timeframe
tags
supported features
paper/live compatibility
Embeddings can improve ranking later.

Implement AI Program Builder as draft-only
Output component proposals, not deployable Programs.

Implement AI Strategy Generator with templates first
Start with:

ORB
VWAP pullback
EMA trend continuation
RSI mean reversion
prior-day breakout
Avoid unsupported Ichimoku until registry supports it.

Implement AI Watchlist Analyzer without news first
Use:

price action
volume
relative volume
events
Add news only after source handling and cost controls exist.

Implement AI Backtest Assistant from summaries
Feed it:

metrics summary
fold summary
parameter sensitivity summary
trade distribution summary
Do not feed full trade logs by default.

Add AI provenance storage
Every proposal must be traceable to prompt, model, inputs, validation, and cost.

Add frontend review screens
Do not allow one-click deploy from AI output.

Add Signal Context Analyzer last
Keep disabled by default.

Start advisory-only.

Add cost controls
Implement:

token/cost tracking
cache
daily budget
per-request estimate
explicit confirmation for expensive calls
Add safety tests
Test that AI cannot:

invent unsupported features
save invalid Program
submit orders
override Governor
read secrets
mark live-ready without validation evidence