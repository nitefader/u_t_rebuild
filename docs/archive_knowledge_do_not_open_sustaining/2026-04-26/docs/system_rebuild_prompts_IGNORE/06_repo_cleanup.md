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
