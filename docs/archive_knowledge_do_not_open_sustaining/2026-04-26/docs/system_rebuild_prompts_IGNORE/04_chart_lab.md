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
