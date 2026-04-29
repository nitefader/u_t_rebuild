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
