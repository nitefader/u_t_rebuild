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
