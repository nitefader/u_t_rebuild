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
