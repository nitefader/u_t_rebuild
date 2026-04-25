# Phase 1 Data Flow Lock — Written Plan

**Authority:** `final_roadmap_and_arch_decisions_and_guidelines.md` §11 Phase 1 + §9 Resolver Contract + §18 Immediate Next Task; `plan_review.md` §I FINAL alignment + §J Resolver Visibility.

**Posture:** Scope only. Code is not started until the user reviews and approves this plan.

---

## Goal (single sentence)

> Lock the contract: a Deployment declares feature demand, the FeaturePlanner derives `data_requirements`, the Resolver picks a `MarketDataPipeline` per FeatureKey (transparent + deterministic + enum-coded), and FeatureEngine registers subscriptions with demand-dedup at the FeatureKey level — without any provider call leaking into FeatureEngine.

---

## What already exists (do not rebuild)

- `backend/app/features/{spec.py,key.py,registry.py,parser.py,planner.py,frames.py,batch.py,incremental.py}` — `FeatureSpec`, `FeatureKey`, registry, parser, `FeaturePlan`, snapshot contract, batch + incremental engines.
- `FeaturePlan` already carries `feature_specs`, `feature_keys`, `symbols`, `timeframes`, `warmup_by_timeframe` per-Program.
- `backend/app/market_data/{resolver.py,catalog.py,...}` — current resolver with `SelectionMode.AUTO/DEFAULT/EXPLICIT` and reason codes (slice 1).
- `backend/app/decision/signal_engine.py` — Signal Engine consuming `FeatureSnapshot` (does not call providers).

## What is missing (this Phase 1 builds)

1. `MarketDataPipeline` first-class domain model.
2. A pipeline registry/store with demand-dedup at `(provider, environment, FeatureKey)` scope (not `(provider, environment, symbol)` — §I says dedup is FeatureKey-level).
3. Resolver result reshape: per-symbol rows, `pipeline_id`, `selection_strategy` (replaces `selection_mode`), frozen rejection-code enum that matches §9 + §J, `resolver_input_hash`, `resolver_version`, `invocation_context`, `decided_at`.
4. FeaturePlanner `data_requirements` view: per-FeatureKey contract describing `(timeframe, instrument_class, streaming|historical, calendar_dependence, warmup_bars)` derived from registry metadata + `FeatureSpec`. Used as resolver input.
5. FeatureEngine demand registration: when a Deployment's `FeaturePlan` is handed in, the engine resolves each `FeatureKey` to a Pipeline, subscribes once per `(pipeline, FeatureKey)`, and tracks consumer set. Unsubscribe when no consumers remain.
6. Acceptance/parity tests covering §11 Phase 1 exit gate.

---

## Conflict to flag (rejection-code list)

§9 of the roadmap and §J of plan_review.md list nearly-identical but **not identical** rejection-code enums:

| Roadmap §9 | plan_review §J |
|---|---|
| UNSUPPORTED_TIMEFRAME | UNSUPPORTED_TIMEFRAME |
| UNSUPPORTED_STREAMING | STREAM_NOT_AVAILABLE |
| UNSUPPORTED_INTRADAY | — (covered by HISTORICAL_NOT_AVAILABLE inverse?) |
| — | UNSUPPORTED_INSTRUMENT |
| CREDENTIAL_MISSING | CREDENTIAL_MISSING |
| CAPABILITY_TIER_INSUFFICIENT | CAPABILITY_TIER_INSUFFICIENT |
| MODE_MISMATCH | MODE_MISMATCH |
| RATE_LIMIT_EXCEEDED | RATE_LIMIT_EXCEEDED |
| OPERATOR_VETO | OPERATOR_VETO |
| NO_COMPATIBLE_PROVIDER | — |
| — | HISTORICAL_NOT_AVAILABLE |

**Decision needed before coding:** I will surface this for you to pick the merged set. My read is the union — `{UNSUPPORTED_TIMEFRAME, UNSUPPORTED_INSTRUMENT, CREDENTIAL_MISSING, CAPABILITY_TIER_INSUFFICIENT, MODE_MISMATCH, RATE_LIMIT_EXCEEDED, OPERATOR_VETO, STREAM_NOT_AVAILABLE, HISTORICAL_NOT_AVAILABLE, NO_COMPATIBLE_PROVIDER}` — but you should ratify before I freeze it as an enum (free text is banned per §12 stop condition 7).

The current resolver also has `REJECTED_NO_INTRADAY` and `REJECTED_NO_REALTIME` — these need to map onto the new canonical codes (likely `STREAM_NOT_AVAILABLE` for realtime; intraday-vs-daily is a `UNSUPPORTED_TIMEFRAME` flavor or a new `UNSUPPORTED_INTRADAY`).

---

## §I FINAL alignment binding constraints (do not break)

- **No `Deployment.pipeline_id` field.** Deployments declare `FeaturePlan`, not pipelines. Pipeline binding is per-FeatureKey, owned by FeatureEngine.
- **One subscription per `FeatureKey`** in FeatureEngine's subscription map. Different Deployments consuming the same `FeatureKey` share one subscription.
- **A single Deployment can mix Pipelines per FeatureKey.** (e.g. `5m.close[0]` resolves to alpaca-premium; `1w.high[0]` resolves to yfinance-historical.) Multi-pipeline-per-Deployment is normal, not an edge case.
- **One PortfolioGovernor per BrokerAccount** — this Phase 1 doesn't touch governor wiring (Phase 2/4), but no design here can foreclose the per-account scope.

## §12 stop conditions to honor

- **Stop 1:** FeatureEngine must not call Alpaca/Yahoo/news/AI APIs. Any provider work happens in `MarketDataPipeline`.
- **Stop 2:** No duplicate streaming for the same `(provider, environment, FeatureKey)` — this is what dedup enforces.
- **Stop 7:** No free-text rejection reasons. Frozen enum only.

## §16 default decisions to apply

- shared pipeline over per-account stream
- feature-driven over config-driven
- explicit enum over free text
- deterministic over smart

---

## Sub-slices (review gate between each)

### Slice 1A — Resolver contract refresh (no Pipeline model yet)

Goal: ship the new resolver result shape and `selection_strategy` rename. `pipeline_id` is added to the result but populated as `None` for now (real binding lands in 1B). Frozen rejection-code enum.

Files:
- `backend/app/market_data/resolver.py` — replace `SelectionMode` with `SelectionStrategy {AUTO, DEFAULT_PREFERRED, MANUAL_OVERRIDE}`; replace `ResolverResult` with new shape (per-symbol rows; `pipeline_id`; `resolver_input_hash`; `resolver_version`; `invocation_context`; `decided_at`); replace `ResolverReasonCode` with the merged frozen enum; add `resolver_input_hash` computation (stable canonical JSON over intent + service set + resolver_version).
- `backend/app/market_data/catalog.py` — update `ResolveMarketDataRequest` (`selection_mode` -> `selection_strategy`; per-symbol input optional); pipe through `invocation_context`.
- `backend/app/api/routes/market_data.py` — request/response shape; route stays at `/services/resolve` (pipeline-aware route lands in 1B).
- `backend/tests/unit/market_data/test_resolver.py` — adjust to new field names; new tests:
  - `test_resolver_input_hash_is_stable_for_equivalent_input`
  - `test_resolver_rejects_only_via_frozen_enum_codes`
  - `test_per_symbol_result_rows_when_intent_lists_multiple_symbols`
  - `test_selection_strategy_replaces_legacy_selection_mode`
- `backend/tests/unit/market_data/test_market_data_catalog.py` — adjust.
- `frontend/src/api/services.js` + `frontend/src/servicesCenter.js` + `frontend/tests/servicesCenter.test.mjs` — rename payload/state field, adjust expected enum values.

Estimated risk: **MED** — touches resolver contract and frontend; well-bounded by tests.

Exit: `pytest backend/tests -q` green, `npm test` green, lint green, IMPLEMENTATION_LOG entry, commit.

### Slice 1B — `MarketDataPipeline` domain model + registry

Goal: introduce `MarketDataPipeline` as first-class domain. Resolver returns real `pipeline_id` values.

Files:
- `backend/app/market_data/pipeline.py` — new domain model. Fields: `id`, `display_name`, `provider`, `environment` (`paper`/`live`/`historical_only`/etc. — note: `paper`/`live` here are *broker-side credential environments*, not banned standalone mode terms; will stay below the lint threshold because the enum is named `PipelineEnvironment` not `PipelineMode`), `capabilities` (reuse `MarketDataCapabilities`), `is_default_for_provider`, `created_at`, `updated_at`. Frozen Pydantic.
- `backend/app/market_data/pipeline_registry.py` — list/create/update/disable; default-pipeline-per-provider-class invariant; persistence under runtime DB path (`market_data_pipelines.json` style).
- `backend/app/market_data/resolver.py` — `resolve_pipeline_for_feature_key(feature_key, ...)` helper; existing `resolve_market_data_service` becomes a wrapper that selects a pipeline via this helper.
- `backend/app/api/routes/market_data.py` — new endpoints: `GET /pipelines`, `POST /pipelines`, `POST /pipelines/{id}/set-default`, `POST /pipelines/{id}/disable`.
- `backend/tests/unit/market_data/test_pipeline_registry.py` — CRUD + default invariants.
- `backend/tests/unit/market_data/test_resolver.py` — new tests:
  - `test_resolver_returns_pipeline_id_for_selected_provider`
  - `test_resolver_returns_per_feature_key_pipeline_when_intent_carries_keys`
- Lint test exists; verify pipeline_environment enum doesn't trip it (audit-only).

Risk: **MED** — new persisted domain; no broker integration.

Exit: same gates + new tests green.

### Slice 1C — FeaturePlanner `data_requirements` view

Goal: expose a consumable `data_requirements` projection on `FeaturePlan` so the resolver can pick a pipeline per FeatureKey using registry-driven capability matching, not symbol-level heuristics.

Files:
- `backend/app/features/planner.py` — extend `FeaturePlan` with `data_requirements: tuple[FeatureDataRequirement, ...]`; introduce `FeatureDataRequirement` (per-FeatureKey: `feature_key`, `timeframe`, `requires_streaming`, `requires_realtime`, `requires_intraday`, `requires_historical`, `requires_long_range_history`, `instrument_class` — derived from registry + spec). The legacy `symbols`/`timeframes`/`warmup_by_timeframe` fields stay (used by existing code). Backwards-compat in this slice = additive only.
- `backend/app/features/registry.py` — registry metadata gains `instrument_class`, `requires_streaming` defaults so `FeatureDataRequirement` can be derived deterministically.
- `backend/tests/unit/features/test_feature_planner.py` — new tests:
  - `test_feature_plan_exposes_one_data_requirement_per_feature_key`
  - `test_data_requirement_inherits_streaming_flag_from_registry`
  - `test_data_requirements_are_dedup_by_feature_key`

Risk: **LOW–MED** — additive on a stable existing structure.

Exit: same gates.

### Slice 1D — FeatureEngine demand registration + FeatureKey-level dedup

Goal: when a Deployment hands a `FeaturePlan` to FeatureEngine, the engine subscribes once per `FeatureKey`, tracks consumers, and unsubscribes when consumer count hits zero. Multiple Deployments needing the same key share one subscription.

Files:
- `backend/app/features/subscription_manager.py` — new module. `SubscriptionMap`: `feature_key -> {pipeline_id, consumer_deployment_ids: set, subscribed_at, last_emit_ts}`. Methods: `register_plan(deployment_id, plan, resolver) -> SubscriptionDelta`, `unregister_plan(deployment_id) -> SubscriptionDelta`, `subscription_for(feature_key)`. `SubscriptionDelta` reports added/removed `(pipeline_id, feature_key)` tuples — caller wires that to actual provider subscribe/unsubscribe (no provider call yet — that's Phase 2).
- `backend/app/features/__init__.py` — export.
- `backend/tests/unit/features/test_subscription_manager.py`:
  - `test_two_deployments_needing_same_feature_key_subscribe_once`
  - `test_unregister_one_consumer_keeps_subscription_when_others_remain`
  - `test_unregister_last_consumer_removes_subscription`
  - `test_dedup_is_at_feature_key_level_not_symbol_level`
  - `test_one_deployment_can_resolve_different_pipelines_per_feature_key`
- Acceptance test under `backend/tests/acceptance/`:
  - `test_feature_demand_to_pipeline_subscription_e2e` — synthesizes two Deployments with overlapping FeaturePlans, runs them through FeaturePlanner → resolver → SubscriptionManager, asserts §11 Phase 1 exit gate (no provider calls; one subscription per FeatureKey; resolver_input_hash stable).
- Architecture-import scan (already exists at `backend/tests/unit/lint/test_no_banned_mode_enums.py` — extend or create sibling): verify `backend/app/features/*` and `backend/app/decision/*` import nothing from `backend/app/market_data/alpaca.py` or any provider SDK directly. (Stop condition 1 enforcement.)

Risk: **MED** — introduces the new orchestration layer; no provider IO yet.

Exit: §11 Phase 1 exit gate satisfied:
> A Deployment can declare feature demand, resolve a pipeline, and attach data demand without direct provider calls.

---

## What this Phase 1 deliberately does NOT do

- Real provider subscribe/unsubscribe wiring (Phase 2 — BarBuilder + Streaming Runtime Truth).
- BarBuilder calendar-aware aggregation (Phase 2).
- Broker event stream integration / BrokerSync writes (Phase 2).
- Sim Lab / Backtester decision-path alignment (Phase 3).
- Control Plane consolidation, kill/pause result panels, governor consults (Phase 4).
- Operations Center / Resolver Visibility UI panel (Phase 5; backend endpoints land in 1A/1B).
- ProgramVersion `composition_hash` freeze + Evidence reproducibility (Phase 4–5).

---

## Decisions that need your input before I start coding 1A

1. **Rejection-code enum union** (see conflict table above). My recommendation is the union `{UNSUPPORTED_TIMEFRAME, UNSUPPORTED_INSTRUMENT, CREDENTIAL_MISSING, CAPABILITY_TIER_INSUFFICIENT, MODE_MISMATCH, RATE_LIMIT_EXCEEDED, OPERATOR_VETO, STREAM_NOT_AVAILABLE, HISTORICAL_NOT_AVAILABLE, NO_COMPATIBLE_PROVIDER, UNSUPPORTED_INTRADAY}`. OK to proceed with that?
2. **`selection_strategy` value casing** — roadmap §9 says `default_preferred` and `manual_override` (snake_case). plan_review §J says `default-preferred` and `manual-override` (kebab-case). I'd pick **snake_case** for Python enum hygiene; UI maps for display. OK?
3. **`MarketDataPipeline.environment`** — this enum currently doesn't exist; my proposed values are `paper`, `live`, `historical_only`, `mixed`. Note: `paper`/`live` here are environment labels for the *credential set the pipeline uses to authenticate to the provider* — distinct from `TradingMode.BROKER_PAPER/LIVE` (which is on `BrokerAccount`). I'll name the enum `PipelineEnvironment` so the lint doesn't trip and the contract stays clean. OK?
4. **Persistence shape** — pipelines persist at `market_data_pipelines.json` next to `market_data_catalog.json` under the runtime DB path (same pattern as slice 1). OK or do you want SQLite from the start?

---

## Order of operations (proposed)

1. You read this plan + decide questions 1–4 above.
2. I ship 1A → review → commit.
3. 1B → review → commit.
4. 1C → review → commit.
5. 1D → review → commit. Phase 1 exit gate satisfied.

After every slice: §13 commands, §14 log entry, §15 git contract.
