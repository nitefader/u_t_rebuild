# System Rebuild Prompt Kit - All-In-One Reference

Use the ZIP for execution. This file is only a readable backup reference.



---

# File: RUN_ORDER.md

# Trading OS System Rebuild - Execution Order

## Purpose

This folder contains the agent prompts and execution workflow for redesigning the trading platform into a unified Trading Operating System.

The goal is not to patch random screens. The goal is to establish one governing architecture that all AI agents, code changes, backend routes, frontend pages, runtime services, and future features must follow.

## Master Principle

Build a Trading OS, not a collection of disconnected tools.

Canonical loop:

```text
Idea -> Program Draft -> Validate -> Chart Lab -> Sim Lab -> Backtest -> Optimize -> Walk-Forward -> Paper -> Live -> Monitor -> Improve
```

## Execution Phases

### Phase 1 - Foundation

Run these first.

1. `00_master_reset.md`
2. `01_system_unification.md`

Expected output:
- one corrected architecture
- one canonical flow
- clear component boundaries
- decision on Governor vs Broker Account responsibility
- corrected deployment model

### Phase 2 - Core Engine

3. `02_feature_engine.md`

Expected output:
- one Feature Engine
- two execution modes
- batch/replay path
- incremental/streaming path
- parity plan across Backtest, Sim Lab, Paper, and Live

### Phase 3 - Validation and Simulation Surfaces

4. `03_sim_lab.md`
5. `04_chart_lab.md`

Expected output:
- permanent distinction between Chart Lab and Sim Lab
- UI model for both
- backend runtime boundaries
- correct data and Feature Engine dependencies

### Phase 4 - Intelligence and Infrastructure

6. `05_ai_architecture.md`
7. `07_alpaca_integration.md`

Expected output:
- AI Program Builder model
- AI Watchlist Analyzer model
- AI signal/news confidence model
- Alpaca streaming, order, account, and fill lifecycle design

### Phase 5 - Cleanup

8. `06_repo_cleanup.md`

Expected output:
- deletion list
- refactor list
- keep list
- new repo/module structure
- migration sequence

### Final Phase - Synthesis

9. `08_synthesis_blueprint.md`

Expected output:
- one canonical architecture document
- one implementation roadmap
- one backend/frontend fix sequence
- one test and acceptance strategy

## How To Run With AI Agents

Run each markdown file as a separate task.

Do not paste all prompts into one chat.

Each agent must produce a markdown output into:

```text
/docs/system_rebuild_outputs/
```

Recommended output names:

```text
00_master_reset_output.md
01_system_unification_output.md
02_feature_engine_output.md
03_sim_lab_output.md
04_chart_lab_output.md
05_ai_architecture_output.md
06_repo_cleanup_output.md
07_alpaca_integration_output.md
08_synthesis_blueprint_output.md
```

## Non-Negotiable Instruction For Every Agent

Every agent must start by reading:

```text
/docs/Canonical_Architecture.md
/docs/Feature_Engine_Spec.md
/docs/Feature_Engine_Build.md
/docs/Feature_Vocabulary_Catalog.md
/docs/Control_Plane_Spec.md
/docs/User_Journey_Validations.md
```

If these files are not present in the new folder, copy them from the old repo first.

## Final Rule

No agent is allowed to invent a new architecture.

Agents may propose improvements, but all changes must converge into one canonical system.


---

# File: 00_master_reset.md

# Agent 00 - Master System Reset

## Role

You are the Chief Systems Architect for a Trading Operating System.

Your job is to unify, audit, and redesign the system into a clean, modular, production-grade architecture.

## Context

The platform must become a Trading OS, not a collection of disconnected tools.

Canonical loop:

```text
Idea -> Program Draft -> Validate -> Chart Lab -> Sim Lab -> Backtest -> Optimize -> Walk-Forward -> Paper -> Live -> Monitor -> Improve
```

## Assumptions

You MUST assume:

- The system is currently fragmented and inconsistent.
- There are duplicate responsibilities across components.
- UI, backend, and runtime are not fully aligned.
- Feature computation, simulation, and execution are partially coupled incorrectly.
- Some pages exist before the architecture is clean.
- Some backend services may be legacy, duplicated, or incorrectly named.

## Required Inputs

Read these before producing output:

```text
/docs/Canonical_Architecture.md
/docs/Feature_Engine_Spec.md
/docs/Feature_Engine_Build.md
/docs/Feature_Vocabulary_Catalog.md
/docs/Control_Plane_Spec.md
/docs/User_Journey_Validations.md
```

Also inspect:

```text
/backend
/frontend/src
/docs
```

## Goal

Create one governing architecture that every AI agent and future code change must follow.

## Hard Rules

- Components are reusable and versioned.
- Programs reference components. Programs do not copy component logic.
- Feature Engine is the single computation authority.
- Chart Lab equals signal and component validation only.
- Sim Lab equals full Program execution simulation.
- Portfolio Governor is the final internal authority before broker submission.
- Broker Account is external broker truth, not internal policy.
- Deployment is a runtime instance of a Program on a Broker Account.
- Strategy must never compute indicators directly.
- Runtime must not use a different feature meaning from backtest.

## Tasks

1. Identify architectural violations.
2. Identify duplicated responsibilities.
3. Identify missing layers.
4. Define a corrected system blueprint.
5. Define strict boundaries between all components.
6. Define the correct end-to-end flow.
7. Define what must be deleted, renamed, merged, or split.
8. Define what the new repo must enforce before any coding continues.

## Output Format

Produce:

```markdown
# Master System Reset Output

## 1. Executive Diagnosis

## 2. Architectural Violations

## 3. Duplicated Responsibilities

## 4. Missing Layers

## 5. Corrected Architecture

## 6. Component Responsibility Table

## 7. End-to-End Flow

## 8. Hard Boundary Rules

## 9. Immediate Fix Sequence

## 10. Stop-Ship Risks
```

## Style

Be direct, strict, and corrective.

Do not be polite.

Do not preserve bad design for convenience.

Do not create a second architecture.


---

# File: 01_system_unification.md

# Agent 01 - System Unification

## Role

You are a Systems Integration Architect.

Your job is to unify the platform into one coherent Trading OS.

## Current Problem

The system is fragmented across:

- Strategies
- Strategy Controls
- Risk Profiles
- Execution Styles
- Watchlists
- Programs
- Chart Lab
- Sim Lab
- Backtest
- Optimization
- Walk-Forward
- Deployments
- Portfolio Governor
- Broker Accounts
- Live Monitor

There is no strong enough unifying path.

## Required Inputs

Read:

```text
/docs/Canonical_Architecture.md
/docs/Control_Plane_Spec.md
/docs/User_Journey_Validations.md
```

Inspect backend and frontend route/page structure.

## Required Decisions

You must decide and document:

1. What is the exact canonical flow?
2. Should Portfolio Governor exist separately from Broker Account?
3. What does Broker Account own?
4. What does Deployment own?
5. Who receives signals?
6. Who turns signals into orders?
7. Who calls Alpaca?
8. Who owns market data streaming?
9. How do multiple Programs run under one Broker Account?
10. How do multiple Broker Accounts work?

## Target Architecture

Use this canonical component stack:

```text
Strategy -> Strategy Controls -> Risk Profile -> Execution Style -> Portfolio Governor -> Broker Account
```

Design-time package:

```text
Program = Strategy + Strategy Controls + Risk Profile + Execution Style + Universe
```

Runtime package:

```text
Deployment = Program running on Broker Account
```

## Tasks

1. Define the canonical object model.
2. Define the runtime object model.
3. Define the signal-to-order flow.
4. Define the deployment model.
5. Define account and portfolio control semantics.
6. Define where AI may participate and where AI must not block deterministic safety.
7. Identify backend services that need renaming or splitting.
8. Identify frontend navigation that should be reorganized.

## Output Format

```markdown
# System Unification Output

## 1. Corrected Mental Model

## 2. Design-Time Model

## 3. Runtime Model

## 4. Component Ownership Matrix

## 5. Signal-to-Order Flow

## 6. Deployment Model

## 7. Multi-Account Model

## 8. Governor vs Broker Account Decision

## 9. Backend Refactor Requirements

## 10. Frontend Navigation Refactor Requirements

## 11. Final System Rules
```

## Non-Negotiable Position

Do not merge Portfolio Governor into Broker Account unless you can prove no policy ambiguity remains.

Broker Account is broker truth.

Portfolio Governor is internal policy authority.


---

# File: 02_feature_engine.md

# Agent 02 - Feature Engine Completion

## Role

You are the Principal Engineer responsible for completing the Feature Engine.

## Required Inputs

Read:

```text
/docs/Feature_Engine_Spec.md
/docs/Feature_Engine_Build.md
/docs/Feature_Engine_Spec_DRD.md
/docs/Feature_Vocabulary_Catalog.md
/docs/Canonical_Architecture.md
```

Inspect:

```text
/backend/app/features
/backend/app/cerebro
/backend/app/core/backtest.py
/backend/app/services/market_data_service.py
/backend/app/services/alpaca_stream_manager.py
/backend/app/api/routes/strategies.py
/backend/app/api/routes/backtests.py
/backend/tests
```

## Completion Bar

The Feature Engine is complete only when one canonical feature system serves:

- Backtest
- Sim Lab historical replay
- Sim Lab live stream
- Paper runtime
- Live runtime

All five must use the same:

- FeatureSpec
- FeatureKey
- Feature Planner
- Feature Registry
- Feature Cache
- Session and calendar semantics

## Required Architecture

One engine, two modes:

```text
Batch / Replay Mode:
Backtest, Sim Lab historical replay, optimization, walk-forward

Incremental / Streaming Mode:
Sim Lab live stream, paper trading, live trading
```

## Hard Rules

- Strategy declares feature requirements.
- Strategy never computes indicators.
- Sim Lab never computes features independently.
- Backtest never owns feature semantics.
- Feature keys must be deterministic.
- Multi-timeframe features must be explicit.
- Session/calendar context must be first-class.
- Portfolio/governor features must fail closed if broker/control truth is stale.
- No legacy indicator-name shortcut may remain in runtime paths.

## Specific Concerns To Address

1. `IndicatorCache` must evolve into or be replaced by `FeatureCache`.
2. `BacktestEngine._compute_indicators(...)` must not be the runtime feature authority.
3. `CerebroRegistry` must become a demand registry for Programs, symbols, timeframes, and feature specs.
4. Alpaca streaming must feed normalized bars into the Feature Engine, not bypass it.
5. Historical replay and streaming continuation must preserve feature parity.
6. Sim Lab must support both replay and live stream modes.

## Tasks

1. Audit current implementation.
2. Identify violations.
3. Define target module layout.
4. Define exact interfaces.
5. Define migration plan.
6. Define file-by-file execution order.
7. Define tests and acceptance gates.
8. Define what transitional code must be deleted.

## Output Format

```markdown
# Feature Engine Completion Output

## 1. Current State Diagnosis

## 2. Critical Violations

## 3. Target Architecture

## 4. Canonical Interfaces

## 5. Batch / Replay Mode Design

## 6. Incremental / Streaming Mode Design

## 7. Cache and Feature Store Design

## 8. Multi-Timeframe Alignment Design

## 9. Session and Calendar Design

## 10. Portfolio Feature Design

## 11. File-by-File Implementation Plan

## 12. Test Plan

## 13. Acceptance Gates

## 14. Transitional Code Removal List

## 15. Final Completion Definition
```

## Be Strict

Do not mark anything complete unless parity is provable.


---

# File: 03_sim_lab.md

# Agent 03 - Sim Lab Architecture

## Role

You are responsible for defining and correcting Sim Lab.

## Required Inputs

Read:

```text
/docs/Canonical_Architecture.md
/docs/Feature_Engine_Spec.md
/docs/User_Journey_Validations.md
```

Inspect:

```text
/frontend/src/pages/SimulationLab.tsx
/backend/app/api/routes/simulations*
/backend/app/core/backtest.py
/backend/app/features
/backend/app/cerebro
```

## Correct Definition

Sim Lab is the full Program simulation surface.

It answers:

```text
What happens over time if this Program runs?
```

## Sim Lab Must Run

A complete Program:

```text
Strategy -> Strategy Controls -> Risk Profile -> Execution Style -> Sim Engine
```

Optional validation mode:

```text
Portfolio Governor preview / rejection simulation
```

## Sim Lab Supports Two Modes

### Historical Replay

- uses cached/historical data
- steps through bars
- deterministic
- supports pause/play/step/rewind
- should match Backtest feature behavior

### Live Stream

- uses warm-up plus streaming continuation
- receives live bars from Market Data Plane
- uses incremental Feature Engine path
- does not submit real orders
- simulates what would happen in live conditions

## Sim Lab Must Validate

- strategy signals
- feature computation
- multi-timeframe alignment
- strategy controls
- session windows
- risk sizing
- execution style behavior
- fills and slippage assumptions
- drawdown and exposure behavior
- broker-style rejection assumptions where simulated

## Sim Lab Must Not

- compute its own features
- create feature semantics
- bypass Feature Engine
- submit orders to broker
- pretend to be a statistical proof engine
- replace Backtest or Walk-Forward

## Special Requirement

Sim Lab must support Programs with large universes, including 50+ symbols.

It needs a UI model for:

- symbol grouping
- active signal list
- filtered symbol focus
- top movers / triggered symbols
- timeline replay
- event log
- selected-symbol chart
- portfolio-level simulated state

## Tasks

1. Define Sim Lab responsibilities.
2. Define what it validates.
3. Define what it must not own.
4. Define Historical Replay architecture.
5. Define Live Stream architecture.
6. Define how Sim Lab handles 50+ symbols.
7. Define API contracts.
8. Define UI design.
9. Define tests.

## Output Format

```markdown
# Sim Lab Architecture Output

## 1. Final Definition

## 2. Responsibilities

## 3. Forbidden Responsibilities

## 4. Historical Replay Mode

## 5. Live Stream Mode

## 6. Program Execution Model

## 7. Governor Validation Mode

## 8. Multi-Symbol UI Model

## 9. Data and Feature Flow

## 10. Backend API Requirements

## 11. Frontend UX Requirements

## 12. Acceptance Tests
```

## Boundary Rule

Chart Lab stops at signal/component preview.

Sim Lab starts at order lifecycle simulation.


---

# File: 04_chart_lab.md

# Agent 04 - Chart Lab Definition

## Role

You are responsible for defining Chart Lab correctly.

## Required Inputs

Read:

```text
/docs/Canonical_Architecture.md
/docs/Feature_Engine_Spec.md
/docs/User_Journey_Validations.md
```

Inspect:

```text
/frontend/src/pages/ChartLab*
/frontend/src/components
/backend/app/api/routes/data*
/backend/app/features
```

## Correct Definition

Chart Lab is the visual signal and component validation surface.

It answers:

```text
What happens here on this chart?
```

It does not answer:

```text
What happens to my account over time?
```

That is Sim Lab.

## Chart Lab May Show

- raw bars
- indicators/features
- feature values
- multi-timeframe overlays
- signal triggers
- strategy condition truth
- Strategy Controls preview
- Risk sizing preview
- Execution preview
- Governor allow/block preview

## Chart Lab Must Not Show

- account PnL curve
- actual trade lifecycle
- account state evolution
- simulated fills over time
- broker calls
- deployment status as if live

## Required UI Philosophy

Chart Lab should feel like a diagnostic cockpit:

- select symbol
- select timeframe
- overlay features
- attach Strategy or Program
- inspect why a signal fired
- inspect why a signal did not fire
- compare indicator values against external tools
- verify multi-timeframe alignment

## Tasks

1. Define Chart Lab purpose.
2. Define boundaries vs Sim Lab.
3. Define allowed component previews.
4. Define data flow through Feature Engine.
5. Define UI model.
6. Define backend API requirements.
7. Define acceptance tests.

## Output Format

```markdown
# Chart Lab Definition Output

## 1. Final Definition

## 2. Responsibilities

## 3. Forbidden Responsibilities

## 4. Difference vs Sim Lab

## 5. Feature Engine Dependency

## 6. Strategy and Program Preview Model

## 7. UI Model

## 8. Backend API Requirements

## 9. Acceptance Tests
```

## Hard Boundary

No PnL curve in Chart Lab.


---

# File: 05_ai_architecture.md

# Agent 05 - AI Architecture and Leverage Analysis

## Role

You are an AI Quant Architect.

Your job is to define where AI creates leverage in the Trading OS without corrupting deterministic trading safety.

## Required Inputs

Read:

```text
/docs/Canonical_Architecture.md
/docs/Feature_Engine_Spec.md
/docs/Feature_Vocabulary_Catalog.md
/docs/User_Journey_Validations.md
```

Inspect:

```text
/backend/app/services
/backend/app/api/routes
/frontend/src/pages
/frontend/src/components
```

## AI System Goals

The platform should support:

1. AI Program Builder
2. AI Strategy Generator
3. AI Watchlist Analyzer
4. AI Component Reuse / Fork Recommendation
5. AI Backtest Recommendation
6. AI Signal Context Analyzer
7. AI Operator Explanation

## Core Product Principle

User should be able to say:

```text
Build me a 5-minute ORB strategy that trades blue-chip morning momentum, uses 15-minute opening range, 5-minute ATR for stops, daily trend confirmation, conservative risk, and deploys to paper first.
```

The system should generate:

- Strategy
- Strategy Controls
- Risk Profile
- Execution Style
- Watchlist/Screener attachment
- Program draft
- validation plan
- backtest plan
- suggested next action

## AI Must Reuse Existing Components

The AI must decide:

- use existing component
- create variant
- create new
- compare similar

It must not blindly create duplicates.

## AI Watchlist Analyzer

Should support:

- top movers
- earnings today/yesterday/tomorrow
- blue-chip filters
- volume spikes
- news/event context
- market regime
- symbol confidence scores
- long/short bias notes
- reasons and timestamps

## AI Signal Context Analyzer

Optional lightweight AI layer.

It may add context, but must not override deterministic safety.

It may answer:

- Is there major news on this symbol?
- Is market sentiment aligned?
- Is there macro risk today?
- Should this signal be flagged for review?

It must not be the final safety authority.

## Tasks

1. Define AI architecture.
2. Define where AI sits in the workflow.
3. Define what AI may create.
4. Define what AI may only recommend.
5. Define cheap/free model strategy.
6. Define data inputs.
7. Define storage model for AI assessments.
8. Define frontend UX.
9. Define safety rules.

## Output Format

```markdown
# AI Architecture Output

## 1. AI Opportunities

## 2. AI Program Builder

## 3. AI Component Reuse Engine

## 4. AI Strategy Generator

## 5. AI Watchlist Analyzer

## 6. AI Signal Context Analyzer

## 7. AI Backtest Recommendation Engine

## 8. Data Inputs

## 9. Storage Model

## 10. Frontend UX

## 11. Cost-Control Strategy

## 12. Safety Rules

## 13. Implementation Plan
```

## Hard Rule

AI can propose.

Deterministic systems approve.


---

# File: 06_repo_cleanup.md

# Agent 06 - Repo Cleanup and Sample Data Audit

## Role

You are a Senior Codebase Auditor.

Your job is to clean the repo for a fresh rebuild.

## Required Inputs

Read any available system audit docs, especially:

```text
/docs/System Audit/COMPLETE_REPO_CLEANUP_SAMPLE_DATA_AUDIT.md
/docs/System Audit/COMPLETE_ENTITY_MODEL_INVENTORY.md
/docs/System Audit/STRUCTURAL_PROBLEMS_AUDIT.md
/docs/System Audit/page_inventory.md
/docs/System Audit/user_journeys.md
/docs/System Audit/ux_ia_redesign.md
/docs/System Audit/feature_engine_audit.md
/docs/System Audit/ai_capability_audit.md
/docs/System Audit/COMPLETE_ALPACA_AGENT_INSPECTION.md
```

Inspect:

```text
/backend
/frontend
/data
/docs
```

## Goal

Prepare the codebase for a clean rebuild by identifying:

- dead files
- duplicate services
- legacy paths
- sample/mock data
- fake UI routes
- unused components
- confusing names
- boundary violations
- old strategy/backtest pathways that conflict with canonical architecture

## Tasks

1. Identify what to delete.
2. Identify what to keep.
3. Identify what to refactor.
4. Identify what must be quarantined.
5. Identify sample data and fake demo data.
6. Identify duplicate concepts.
7. Define a clean target folder structure.
8. Define a safe migration plan.

## Output Format

```markdown
# Repo Cleanup Output

## 1. Executive Summary

## 2. Delete List

| Path | Reason | Risk | Safe Delete? |
|---|---|---|---|

## 3. Keep List

| Path | Why Keep | Owner Domain |
|---|---|---|

## 4. Refactor List

| Path | Problem | Target Location / Shape |
|---|---|---|

## 5. Quarantine List

| Path | Why Quarantine | What Proof Decides Fate |
|---|---|---|

## 6. Sample / Mock Data Findings

## 7. Duplicate Concept Findings

## 8. Naming Problems

## 9. Proposed Folder Structure

## 10. Migration Plan

## 11. Stop-Ship Cleanup Items
```

## Be Aggressive

This is a reset.

Do not preserve junk because it might be useful someday.


---

# File: 07_alpaca_integration.md

# Agent 07 - Alpaca Integration and Streaming Inspection

## Role

You are a Trading Infrastructure Engineer.

Your job is to define the correct Alpaca integration architecture.

## Required Inputs

Read:

```text
/docs/Canonical_Architecture.md
/docs/Control_Plane_Spec.md
/docs/Feature_Engine_Spec.md
/docs/System Audit/COMPLETE_ALPACA_AGENT_INSPECTION.md
```

Inspect:

```text
/backend/app/services/alpaca_service.py
/backend/app/services/alpaca_stream_manager.py
/backend/app/services/market_data_service.py
/backend/app/services/market_data_bus.py
/backend/app/cerebro
/backend/app/api/routes/accounts*
/backend/app/api/routes/deployments*
/backend/app/api/routes/control*
```

## Required Architecture Position

Alpaca is not the Trading OS.

Alpaca provides:

- broker account truth
- market data streaming
- historical market data if configured
- order submission
- order status
- fills
- positions
- buying power
- restrictions

Alpaca must not own:

- strategy logic
- feature semantics
- portfolio policy
- signal truth
- internal Program design

## Required Design

Define:

1. Market data streaming model.
2. Historical warm-up model.
3. WebSocket subscription lifecycle.
4. Multiple accounts model.
5. Multiple paper accounts and live accounts.
6. Program-to-account deployment model.
7. Order attribution using deployment id.
8. Signal-to-order lifecycle.
9. Broker state reconciliation.
10. Failure and stale-state behavior.

## Critical Safety Requirements

- No opening order without `can_open_new_position`.
- Pause/kill cancels resting opening orders only.
- Protective exits must survive pause/kill.
- Unknown order intent must be kept and flagged.
- Broker sync stale must fail closed for new opens.
- Program pause must be scoped to deployment, not strategy.
- Account pause must not flatten positions.
- Flatten must be explicit.

## Tasks

1. Audit current Alpaca integration.
2. Define correct streaming architecture.
3. Define order lifecycle.
4. Define state reconciliation.
5. Define failure modes.
6. Define tests.
7. Define file-level implementation plan.

## Output Format

```markdown
# Alpaca Integration Output

## 1. Current State Diagnosis

## 2. Correct Alpaca Responsibility Model

## 3. Market Data Streaming Architecture

## 4. Historical Warm-Up Architecture

## 5. Multi-Account Model

## 6. Deployment-to-Account Model

## 7. Signal-to-Order Lifecycle

## 8. Order Attribution Model

## 9. Broker Sync and Reconciliation

## 10. Pause / Kill / Flatten Behavior

## 11. Failure Modes

## 12. File-Level Implementation Plan

## 13. Acceptance Tests
```

## Hard Rule

Alpaca is an external service boundary, not an architecture layer.


---

# File: 08_synthesis_blueprint.md

# Agent 08 - Final Synthesis Blueprint

## Role

You are the Architecture Review Board.

You must synthesize outputs from all prior agents into one canonical implementation blueprint.

## Required Inputs

Read all outputs:

```text
/docs/system_rebuild_outputs/00_master_reset_output.md
/docs/system_rebuild_outputs/01_system_unification_output.md
/docs/system_rebuild_outputs/02_feature_engine_output.md
/docs/system_rebuild_outputs/03_sim_lab_output.md
/docs/system_rebuild_outputs/04_chart_lab_output.md
/docs/system_rebuild_outputs/05_ai_architecture_output.md
/docs/system_rebuild_outputs/06_repo_cleanup_output.md
/docs/system_rebuild_outputs/07_alpaca_integration_output.md
```

Also read canonical docs:

```text
/docs/Canonical_Architecture.md
/docs/Feature_Engine_Spec.md
/docs/Feature_Engine_Build.md
/docs/Feature_Vocabulary_Catalog.md
/docs/Control_Plane_Spec.md
/docs/User_Journey_Validations.md
```

## Goal

Produce the final master blueprint that guides backend, frontend, runtime, AI, Alpaca, Feature Engine, and UX work.

## Your Job

1. Resolve contradictions between agents.
2. Select one final architecture.
3. Define backend implementation order.
4. Define frontend implementation order.
5. Define test plan.
6. Define migration plan.
7. Define what must be blocked until prerequisites are complete.

## Output Format

```markdown
# Trading OS Rebuild Master Blueprint

## 1. Executive Summary

## 2. Final Architecture

## 3. Canonical Domain Model

## 4. Canonical Runtime Flow

## 5. Backend Implementation Roadmap

## 6. Frontend Implementation Roadmap

## 7. Feature Engine Roadmap

## 8. Sim Lab Roadmap

## 9. Chart Lab Roadmap

## 10. Alpaca Runtime Roadmap

## 11. AI Capability Roadmap

## 12. Repo Cleanup Roadmap

## 13. Test and Acceptance Strategy

## 14. Migration Sequence

## 15. Stop-Ship Rules

## 16. First 10 Engineering Tasks
```

## Final Rule

This output becomes the source of truth.

Do not leave competing models unresolved.


---

# File: COPILOT_VSCODE_WORKFLOW.md

# VS Code + Copilot Execution Workflow

## Goal

Use VS Code and Copilot/Codex/Claude-style agents to rebuild the trading system without random wandering.

This workflow is designed for a fresh folder or fresh branch.

## Recommended Folder Setup

Inside the new repo or new working folder:

```text
Ultimate_Trading_OS_Rebuild/
  docs/
    Canonical_Architecture.md
    Feature_Engine_Spec.md
    Feature_Engine_Build.md
    Feature_Engine_Spec_DRD.md
    Feature_Vocabulary_Catalog.md
    Control_Plane_Spec.md
    User_Journey_Validations.md
    system_rebuild_prompts/
      RUN_ORDER.md
      00_master_reset.md
      01_system_unification.md
      02_feature_engine.md
      03_sim_lab.md
      04_chart_lab.md
      05_ai_architecture.md
      06_repo_cleanup.md
      07_alpaca_integration.md
      08_synthesis_blueprint.md
    system_rebuild_outputs/
  backend/
  frontend/
```

## Step 1 - Create a Clean Branch

Use one of these approaches.

### Option A - New Branch

```bash
git checkout -b trading-os-rebuild
```

### Option B - New Folder

```bash
mkdir Ultimate_Trading_OS_Rebuild
cd Ultimate_Trading_OS_Rebuild
git clone <your-repo-url> .
git checkout -b trading-os-rebuild
```

## Step 2 - Copy Canonical Docs First

Before asking any AI to code, copy the governing docs into:

```text
/docs/
```

Required:

```text
Canonical_Architecture.md
Feature_Engine_Spec.md
Feature_Engine_Build.md
Feature_Engine_Spec_DRD.md
Feature_Vocabulary_Catalog.md
Control_Plane_Spec.md
User_Journey_Validations.md
```

If these are missing, the agents will drift.

## Step 3 - Add Prompt Files

Copy all files from this prompt kit into:

```text
/docs/system_rebuild_prompts/
```

Create:

```text
/docs/system_rebuild_outputs/
```

## Step 4 - Run Agents As Separate Tasks

Do not run all prompts together.

Run them in this order:

```text
00_master_reset.md
01_system_unification.md
02_feature_engine.md
03_sim_lab.md
04_chart_lab.md
05_ai_architecture.md
07_alpaca_integration.md
06_repo_cleanup.md
08_synthesis_blueprint.md
```

For each prompt, tell the agent:

```text
Read the prompt file at docs/system_rebuild_prompts/<file>.md.
Inspect the repo.
Produce the requested output only.
Save the output to docs/system_rebuild_outputs/<matching_output_name>.md.
Do not modify source code yet.
```

## Step 5 - Freeze Blueprint Before Coding

After `08_synthesis_blueprint.md` runs, review:

```text
/docs/system_rebuild_outputs/08_synthesis_blueprint_output.md
```

This becomes the working plan.

No coding starts until this exists.

## Step 6 - Convert Blueprint Into Engineering Tasks

Ask Copilot/Codex:

```text
Read docs/system_rebuild_outputs/08_synthesis_blueprint_output.md.

Create docs/system_rebuild_outputs/09_engineering_task_breakdown.md with:
1. backend tasks
2. frontend tasks
3. test tasks
4. migration tasks
5. acceptance criteria
6. exact file targets
7. safe execution order

Do not modify code.
```

## Step 7 - Code In Small Slices

For each task, use this execution wrapper:

```text
You are implementing one bounded task only.

Read:
- docs/system_rebuild_outputs/08_synthesis_blueprint_output.md
- docs/system_rebuild_outputs/09_engineering_task_breakdown.md
- docs/Canonical_Architecture.md
- docs/Feature_Engine_Spec.md
- docs/Control_Plane_Spec.md

Implement only Task <ID>.

Before modifying files:
1. list files you will touch
2. explain why
3. identify rollback point

After modifying files:
1. run relevant tests
2. update docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md
3. summarize changed files
4. state what remains blocked

Do not start the next task.
```

## Step 8 - Force Tests After Every Slice

Minimum commands to ask the agent to run, adjusted for your repo:

```bash
pytest backend/tests
npm test
npm run build
```

If full tests are too heavy, require targeted tests plus build.

## Step 9 - Protect Against AI Wandering

Use this rule in every coding prompt:

```text
Do not refactor unrelated files.
Do not rename public APIs unless the task explicitly requires it.
Do not create new architecture.
Do not add demo/sample data.
Do not bypass canonical docs.
Do not mark task complete unless tests pass or failures are documented with exact cause.
```

## Step 10 - Pull Request Discipline

Each slice should become one commit.

Commit message pattern:

```text
Trading OS Rebuild: <slice name>
```

Examples:

```text
Trading OS Rebuild: canonical feature specs
Trading OS Rebuild: simulation replay boundary
Trading OS Rebuild: portfolio governor gate
```

## Recommended First Engineering Slices

1. Canonical docs copied and indexed.
2. Repo cleanup audit completed.
3. Route/page inventory completed.
4. Feature Engine identity and planner locked.
5. Feature cache interface stabilized.
6. Chart Lab boundary corrected.
7. Sim Lab historical replay corrected.
8. Sim Lab live stream design added.
9. Alpaca streaming ownership clarified.
10. Deployment-to-account model corrected.

## Anti-Pattern Warnings

Stop the agent if it does any of these:

- starts coding before architecture output exists
- says “I updated everything” without file list
- creates new abstractions not in blueprint
- puts risk/session/order logic inside Strategy
- computes indicators in Strategy
- makes Chart Lab simulate PnL
- lets Broker Account own internal policy
- lets Alpaca define feature semantics
- marks unsupported features as supported in UI
- uses mock/demo data without labeling it

## Final Working Rule

One architecture.

One task at a time.

Tests after every task.

No silent drift.
