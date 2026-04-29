# Implementation Log Contract (All Agents)

## Purpose

Every change must be recorded in a consistent, minimal, and truthful way.

This log is used to understand system evolution and debug decisions later.

---

## File Location

Update:

docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md

---

## When to Log

Add a new entry when:

- a feature is implemented
- behavior changes
- logic is fixed or corrected
- UX behavior changes
- contracts or architecture decisions change

Do NOT log:
- minor formatting changes
- comments-only changes
- exploratory or incomplete work

---

## Entry Format

Use:

```text
## YYYY-MM-DD HH:MM ET - <Short Title>

# Ensure that when you Stop:
- no architecture violations
- backend stable
- UI stable
- worktree clean


# Code Change Contract (All Agents)

## Purpose

Ensure all code changes are:
- minimal
- correct
- aligned with system architecture
- non-destructive

Agents must not overbuild, refactor unnecessarily, or introduce duplicate logic.

---

## Core Principle

> Change only what is required.
> Do not “improve” unrelated parts of the system.

---

## Allowed Changes

Agents MAY:

- add new files required for the task
- modify existing files directly related to the task
- extend existing logic in place
- add tests for new behavior
- update UI components tied to the task
- update documentation and implementation log

---

## Forbidden Changes

Agents MUST NOT:

- refactor unrelated modules
- rename files, folders, or core concepts
- duplicate existing logic in new locations
- bypass existing system layers (FeatureEngine, Governor, etc.)
- move logic across layers without explicit instruction
- add new architecture patterns
- introduce parallel systems (e.g., second resolver, second runtime loop)
- modify BrokerAdapter, OrderManager, or core engines unless explicitly required
- hardcode values that should come from backend or configuration
- remove existing functionality unless fixing a bug

---

## File Scope Rule

Before editing any file, the agent must:

1. Identify the minimal set of files required
2. Limit changes to that set only

If more than ~5 files are being modified:
→ STOP and reassess

---

## Change Size Rule

Changes should be:

- small
- focused
- incremental

Avoid:
- large rewrites
- sweeping refactors
- multi-system changes

---

## Existing Logic Rule

If functionality already exists:

- reuse it
- extend it

Do NOT:
- reimplement it
- copy it into a new file

---

## Data & Logic Rules

- Do not hardcode:
  - provider selections
  - resolver outputs
  - credentials
  - capability values

- All dynamic behavior must come from:
  - backend APIs
  - resolver logic
  - stored configuration

---

## UI Rules

- UI reflects system state, not assumptions
- Do not fake data for display
- Do not simulate backend responses unless explicitly instructed
- Do not invent values for empty states

---

## Testing Requirements

For any change:

- add or update relevant tests
- ensure existing tests pass
- do not remove tests unless invalid

---

## Validation Commands

Agents must run:

```bash
python -m compileall -q backend/app backend/tests
python -m pytest backend/tests -q
cd frontend && npm.cmd run build
cd frontend && npm.cmd test
