---
name: Authority docs (read order)
description: Authority order for Trading OS rebuild — locked architecture decisions and execution contract live in final_roadmap_and_arch_decisions_and_guidelines.md alongside plan_review.md
type: reference
---

Read in this order before any non-trivial work:

1. **`final_roadmap_and_arch_decisions_and_guidelines.md`** (repo root) — locked architecture decisions and binding execution contract. Owns: §11 Phase ordering (Phase 1 Data Flow Lock = Feature Planner → Resolver → MarketDataPipeline wiring; phases 2–5 follow), §9 Resolver contract (use `selection_strategy`, frozen enum rejection codes, per-symbol rows, `resolver_input_hash`/`resolver_version`/`invocation_context`/`decided_at`), §12 stop conditions, §13 validation commands, §14 implementation log format, §15 git contract, §16 default decision rules, §18 immediate next task. **Overrides any phase ordering in plan_review.md when they conflict** (e.g. plan_review §G called MarketDataPipeline "Phase 2.5"; this doc calls it Phase 1 and pulls composition_hash / Evidence / ControlPlane consolidation / client_order_id back to phases 4–5).
2. **`plan_review.md`** §I (FINAL alignment — FeatureEngine mediates Pipelines; no `Deployment.pipeline_id`; per-account `PortfolioGovernor`; flat `BrokerAccount`) and §J (Resolver Visibility contract).
3. **`docs/system_rebuild_outputs/08_synthesis_blueprint_output.md`** — Master Blueprint.
4. **`docs/system_rebuild_outputs/MODE_NAMING_CONTRACT.md`** — banned mode terms.
5. **`mockup_review.html`** — UI contract; not authoritative for behavior.

Implementation log lives at `docs/system_rebuild_outputs/IMPLEMENTATION_LOG.md`; entry format is fixed by §14.
