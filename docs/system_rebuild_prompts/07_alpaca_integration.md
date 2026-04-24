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
