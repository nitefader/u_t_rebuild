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
