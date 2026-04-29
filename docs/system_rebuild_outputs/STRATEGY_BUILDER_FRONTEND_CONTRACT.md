# Strategy Builder Frontend Contract

Last updated: 2026-04-27 22:05:00 -04:00

Owner: Codex / Operation Turtle Shell

Consumer: Claude / Operation Production Readiness

Scope: backend contracts for the Strategy Builder and AI Composer UI. This does not deploy a Strategy, attach an Account, submit orders, or claim live readiness.

## Endpoint Map

| Route | Request Schema | Response Schema | Validation Behavior | Test Coverage |
| --- | --- | --- | --- | --- |
| `GET /api/v1/strategies/builder/features` | none | `tuple[FeatureCatalogItem, ...]` | Returns FeatureRegistry vocabulary only. `batch_executable=false` means the feature is registered but cannot be used in batch research yet. | `backend/tests/unit/api/test_strategy_composer_api.py` |
| `GET /api/v1/strategies/builder/features/aliases` | none | `dict[str, str]` | Returns shorthand aliases such as `sma20 -> 5m.sma:length=20[0]`. | `backend/tests/unit/api/test_strategy_composer_api.py` |
| `POST /api/v1/strategies/builder/features/validate` | `FeatureReferenceValidationRequest` | `FeatureReferenceValidation` | Normalizes aliases, validates registry support, and rejects batch-research features that are not executable. HTTP 200 with `valid=false` for validation failures. | `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`, `backend/tests/unit/api/test_strategy_composer_api.py` |
| `POST /api/v1/strategies/builder/features/plan-preview` | `FeaturePlanPreviewRequest` | `FeaturePlanPreview` | Builds the FeaturePlan preview without saving. Invalid plans return HTTP 200 with `valid=false` and `errors`. | `backend/tests/unit/strategy_composer/test_strategy_composer_service.py` |
| `POST /api/v1/strategies/builder/conditions/parse` | `ConditionParseRequest` | `ConditionParseResponse` | Validates condition trees and `LogicalExitRule` payloads. Supports `feature_condition`, `bars_since_entry`, `time_in_position_seconds`, `time_of_day_et`, `minutes_before_session_close`, `session_window`, and `hybrid`. | `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`, `backend/tests/unit/api/test_strategy_composer_api.py` |
| `POST /api/v1/strategies/builder/reuse-matches` | `ReuseMatchRequest` | `ReuseMatchResponse` | Finds similar Strategies and returns draft component suggestions for Risk Plans, Execution Styles, Watchlists, and Screeners with score + reason. | `backend/tests/unit/api/test_strategy_composer_api.py` |
| `POST /api/v1/strategies/composer/preview` | `AIComposerRequest` | `StrategyDraft` | Creates a draft-only Strategy suggestion. AI output is deterministic-validated against FeatureRegistry vocabulary. Unsupported prompt features produce `validation.valid=false`; no save occurs. | `backend/tests/unit/strategy_composer/test_strategy_composer_service.py`, `backend/tests/unit/api/test_strategy_composer_api.py` |
| `POST /api/v1/strategies/composer/drafts` | `StrategyDraftSaveRequest` | `StrategyDraftSaveResponse` | Saves draft Strategy + draft StrategyVersion only. Rejects invalid drafts with HTTP 400. Does not create Deployment, Account attachment, broker action, or live-readiness claim. | `backend/tests/unit/strategy_composer/test_strategy_composer_service.py` |

## Core Field Definitions

`FeatureCatalogItem`

- `kind`: registry kind, for example `close`, `sma`, `rsi`.
- `display_name`: operator-facing name.
- `allowed_params`, `default_params`: valid parameter vocabulary.
- `supported_timeframes`, `supported_consumers`, `supported_modes`: capability hints.
- `batch_executable`: true only when the batch research engine can compute it today.
- `example_refs`: ready-to-use feature reference examples.

`FeatureReferenceValidationRequest`

```json
{
  "feature_refs": ["sma20", "5m.close[0]"],
  "consumer": "backtest"
}
```

`ConditionParseRequest`

```json
{
  "condition": {
    "kind": "condition",
    "left_feature": "close",
    "operator": "gt",
    "right_feature": "open"
  },
  "consumer": "backtest"
}
```

`LogicalExitRule`

- `feature_condition`: exit based on a feature condition tree.
- `bars_since_entry`: exit after N bars in position.
- `time_in_position_seconds`: exit after N seconds in position.
- `time_of_day_et`: exit at or after HH:MM Eastern time.
- `minutes_before_session_close`: exit N minutes before regular session close.
- `session_window`: exit based on session bucket.
- `hybrid`: compose child rules with `operator = all | any`.

`StrategyDraft`

- `strategy`: draft `StrategyVersion`.
- `suggested_risk_plan`: draft research Risk Plan suggestion only. Strategy does not own Risk.
- `suggested_execution_style`: draft execution-style suggestion only.
- `suggested_universe`: draft Universe snapshot suggestion only. Strategy does not own Universe.
- `backtest_plan`: legacy simple backtest plan fields for display.
- `launch_plans`: action-ready route + payload templates for Chart Lab, Backtest, and Walk-Forward.
- `validation`: deterministic validation result. Only save when `valid=true`.

`StrategyDraftLaunchPlans`

- `chart_lab`: `GET /api/v1/chart-lab/stream`, ready when a symbol exists.
- `backtest`: `POST /api/v1/research/jobs/backtest`, not ready until `risk_plan_version_id`, `start`, and `end` are supplied.
- `walk_forward`: `POST /api/v1/research/jobs/walk-forward`, not ready until `start` and `end` are supplied.

## Example Payloads

Feature validation:

```json
POST /api/v1/strategies/builder/features/validate
{
  "feature_refs": ["sma20", "rsi21"],
  "consumer": "backtest"
}
```

Expected behavior: `sma20` normalizes and validates. `rsi21` normalizes but returns `valid=false` for backtest until RSI is batch-executable.

Logical exit parse:

```json
POST /api/v1/strategies/builder/conditions/parse
{
  "logical_exit_rule": {
    "kind": "hybrid",
    "operator": "all",
    "children": [
      { "kind": "bars_since_entry", "bars": 5 },
      {
        "kind": "feature_condition",
        "feature_condition": {
          "kind": "condition",
          "left_feature": "close",
          "operator": "lt",
          "right_feature": "open"
        }
      }
    ]
  },
  "consumer": "backtest"
}
```

Composer preview:

```json
POST /api/v1/strategies/composer/preview
{
  "prompt": "Green bar long entry and exit after 30 minutes",
  "symbols": ["SPY", "QQQ"],
  "timeframe": "5m",
  "initial_capital": 100000
}
```

Save draft:

```json
POST /api/v1/strategies/composer/drafts
{
  "draft": { "...": "StrategyDraft returned by /composer/preview" }
}
```

## Example AI Composer Response Shape

```json
{
  "draft_id": "uuid",
  "prompt": "Green bar long entry and exit after 30 minutes",
  "strategy": {
    "id": "uuid",
    "strategy_id": "uuid",
    "version": 1,
    "name": "Green Bar Long Entry And Exit After 30 Minutes",
    "feature_refs": ["5m.close[0]", "5m.open[0]"],
    "entry_rules": ["..."],
    "exit_rules": ["... logical_exit ..."],
    "tags": ["ai_composer", "draft"]
  },
  "suggested_risk_plan": { "name": "Composer draft fixed shares", "version": 1 },
  "suggested_execution_style": { "name": "Composer draft market day", "version": 1 },
  "suggested_universe": { "name": "Composer draft universe", "symbols": [{ "symbol": "SPY" }] },
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": [],
    "normalized_feature_refs": ["5m.close[0]", "5m.open[0]"],
    "feature_plan_preview": { "valid": true, "feature_keys": ["..."] }
  },
  "launch_plans": {
    "chart_lab": {
      "surface": "chart_lab",
      "method": "GET",
      "route": "/api/v1/chart-lab/stream",
      "request": { "symbol": "SPY", "query": { "symbol": "SPY" } },
      "ready": true,
      "missing_fields": []
    },
    "backtest": {
      "surface": "backtest",
      "method": "POST",
      "route": "/api/v1/research/jobs/backtest",
      "request": {
        "request": {
          "strategy_id": "uuid",
          "strategy_version_id": "uuid",
          "risk_plan_version_id": null,
          "symbols": ["SPY"],
          "timeframe": "5m",
          "start": null,
          "end": null,
          "initial_capital": 100000
        }
      },
      "ready": false,
      "missing_fields": ["risk_plan_version_id", "start", "end"]
    },
    "walk_forward": {
      "surface": "walk_forward",
      "method": "POST",
      "route": "/api/v1/research/jobs/walk-forward",
      "ready": false,
      "missing_fields": ["start", "end"]
    }
  }
}
```

Frontend schemas should use typed core fields with `.passthrough()` so additive backend fields do not break the UI.

## Validation Errors

Unsupported feature reference:

```json
{
  "valid": false,
  "errors": ["not_a_feature: unsupported feature kind: not_a_feature"],
  "items": [
    {
      "input": "not_a_feature",
      "valid": false,
      "error_code": "unsupported_feature",
      "message": "unsupported feature kind: not_a_feature"
    }
  ]
}
```

AI prompt invents unsupported features:

```json
{
  "validation": {
    "valid": false,
    "errors": ["unsupported prompt feature terms require operator revision: macd"],
    "warnings": ["composer returned a placeholder using supported features only; revise before save"]
  }
}
```

Invalid draft save:

```json
HTTP 400
{
  "detail": "strategy draft failed validation: (...)"
}
```

## Recommended Frontend Flow

1. Load `GET /builder/features` and `GET /builder/features/aliases`.
2. Let the operator build manually or call `POST /composer/preview`.
3. For every edited condition tree, call `POST /builder/conditions/parse`.
4. Call `POST /builder/features/plan-preview` before enabling Save.
5. Show `POST /builder/reuse-matches` suggestions as reusable component hints.
6. Save only with `POST /composer/drafts` when `draft.validation.valid=true`.
7. After save, use `launch_plans` to offer Chart Lab / Backtest / Walk-Forward actions. Require missing fields before POSTing research jobs.

## Known Gaps / TODOs

- External AI provider integration is not active here; `/composer/preview` is a deterministic guarded composer.
- RSI, ATR, VWAP may exist in FeatureRegistry but are not batch-executable until their batch computation support lands.
- Save snapshots suggested components in the response, but only Strategy + StrategyVersion are persisted by this endpoint today.
- Backtest launch needs a saved Risk Plan version. The draft suggestion is not a persisted Risk Plan.
- Strategy does not own Risk or Universe. The UI must present those as suggested reusable components, not Strategy fields.
- No Deployment or Account attachment is allowed from Strategy Builder / AI Composer.
