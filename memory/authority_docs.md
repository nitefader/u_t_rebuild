---
name: Authority docs (read order)
description: Active authority order for Ultimate Trader after the 2026-04-26 doctrine cleanup
type: reference
---

Read active docs in this order before non-trivial work:

1. **`docs/README.md`** - active documentation entrypoint and read order.
2. **`docs/ULTIMATE_TRADER_MANDATE.md`** - product mandate: one platform, one Account concept, production-grade from day zero, no silent failures.
3. **`docs/architecture/NAMING_CONTRACT.md`** - canonical names and banned confusing names.
4. **`docs/architecture/CANONICAL_RUNTIME_ARCHITECTURE.md`** - Strategy -> Deployment -> SignalPlan -> Account decision -> Governor -> OrderManager -> BrokerAdapter -> BrokerSync.
5. **`docs/architecture/SIGNALPLAN_POSITION_LIFECYCLE.md`** - Account-owned position lifecycle and related close/reduce SignalPlans.
6. **`docs/architecture/STREAMS_AND_PROVIDERS.md`** - Market Data Providers, AI Providers, Live Stock Market Data Stream, Account Trade Sync.
7. **`docs/architecture/BACKEND_MODULE_MAP.md`** - backend module ownership and target changes.
8. **`docs/architecture/OPERATOR_EXPERIENCE.md`** - simplified navigation, Settings cleanup, explainers, visible failures.
9. **`docs/architecture/UI_VISUAL_DIRECTION.md`** - reusable visual/UI recommendations from the original repo, filtered through current doctrine.
10. **`docs/implementation/NEXT_BUILD_PLAN.md`** - current execution plan.
11. **`docs/operations/RUNTIME_SHIP_GATE.md`** and **`docs/operations/DAY_ZERO_RUNBOOK.md`** - runtime validation and operator procedure.

Archived markdown under `docs/archive_knowledge_do_not_open_sustaining/2026-04-26/` is historical only and must not be treated as active authority.
