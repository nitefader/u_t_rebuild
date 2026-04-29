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
