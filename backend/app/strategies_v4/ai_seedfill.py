"""AI seed-fill service for StrategyVersion v4.

The service:
1. Builds a strict schema-constrained system prompt (including DSL grammar,
   validator rules, feature catalog, and JSON output shape).
2. Calls the LLM via the provided ``LLMClient``.
3. Parses the JSON response.
4. Validates it against ``StrategyVersionV4Draft``.
5. Runs ``validate_expression_fn`` on every expression field.
6. Returns ``AISeedFillResponse`` — draft + validation status.

The service does NOT save anything.  It is advisory only.
"""
from __future__ import annotations

import json
from typing import Callable, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydanticValidationError

from backend.app.ai.llm_client import LLMClient, LLMClientError, LLMRequest
from backend.app.ai.providers import AIProvider
from backend.app.domain.strategy_v4 import ValidationStatusV4
from backend.app.strategies_v4.models import StrategyVersionV4Draft


# ---------------------------------------------------------------------------
# Public request / response types
# ---------------------------------------------------------------------------

class AISeedFillRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(min_length=8, max_length=2000)
    current_draft: StrategyVersionV4Draft | None = None


class AISeedFillResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    draft: StrategyVersionV4Draft
    validation_status: ValidationStatusV4
    provider_used: AIProvider
    model_used: str
    raw_response_excerpt: str
    notes: tuple[str, ...]


class AISeedFillError(RuntimeError):
    """Wraps LLMClientError, JSON parse errors, and schema validation failures."""


# ---------------------------------------------------------------------------
# System prompt construction
# ---------------------------------------------------------------------------

_DSL_GRAMMAR = """
EXPRESSION LANGUAGE GRAMMAR (strict subset — do not invent syntax):

Atoms:
  - Numbers:         42   3.14   0.5
  - Timeframed feat: <tf>.<name>(<args>)   e.g.  5m.ema(9)  1h.rsi(14)  15m.atr(14)
  - Non-tf features: <ns>.<name>           e.g.  session.is_open  orb.high  prior_day.close
  - Bar field refs:  bar.close  bar.high  bar.low  bar.volume  bar.open
  - Variables:       any identifier matching ^[a-z_][a-z0-9_]*$
  - True / False

Operators (in precedence order, low to high):
  OR
  AND
  NOT <expr>
  >  <  >=  <=  ==  !=
  +  -
  *  /
  ( <expr> )   (grouping)

Special forms:
  crosses_above(<a>, <b>)   — boolean: a crossed above b this bar
  crosses_below(<a>, <b>)   — boolean: a crossed below b this bar
  within(<value>, <lo>, <hi>) — boolean: lo <= value <= hi
  any_of(<e1>, <e2>, ...)   — boolean OR of all args
  all_of(<e1>, <e2>, ...)   — boolean AND of all args

Comments:
  // rest-of-line comment

Timeframe identifiers:  1m  3m  5m  10m  15m  30m  1h  2h  4h  1d  1w

RULES:
  - Entry expressions must evaluate to bool.
  - Variable expressions may evaluate to float or bool.
  - Stop expression mode: expression_text must evaluate to float (the stop price).
  - Do NOT use eval/exec. Write expressions as text; the backend compiles them.
"""

_VALIDATOR_RULES = """
DRAFT VALIDATOR RULES:
  1. entries.long OR entries.short (or both) must be present — at least one entry.
  2. stops array must have at least one element.
  3. If legs are present, sum of size_pct must equal 1.0 (±1e-6).
  4. Leg positions must be contiguous 1..N.
  5. At most one leg with kind="runner".
  6. variable.name must match ^[a-z_][a-z0-9_]*$.
  7. variable names must be unique.
  8. timeframe_aliases keys match ^[a-z_][a-z0-9_]*$; values match ^\\d+[mhdw]$.
  9. on_fill_action kinds {be_plus, be_minus, tighten_atr, tighten_pct} require offset_value != null.
  10. on_fill_action kinds {be_exact, leave} require offset_value == null.
  11. simple stop requires simple_type + simple_value; expression stop requires expression_text.
"""

_EXAMPLE_EXPRESSIONS = """
EXAMPLE EXPRESSIONS (use these patterns as reference):

Trend / momentum (entries):
  5m.ema(9) crosses_above 5m.ema(21)
  5m.rsi(14) < 30 AND 5m.close > prior_day.close
  1h.ema(20) > 1h.ema(50) AND 5m.macd_hist > 0

Mean reversion (entries):
  5m.rsi(2) < 10 AND session.is_open
  5m.close < 5m.bb_lower(20, 2.0)
  5m.adx(14) < 25 AND 5m.rsi(14) < 40

Variables (float expressions):
  my_fast_ma = 5m.ema(9)
  ref_price   = prior_day.close
  range_size  = orb.high - orb.low

Stop expression (must evaluate to a float price level):
  bar.close - 2.0 * 5m.atr(14)
"""

_OUTPUT_SCHEMA = """
REQUIRED JSON OUTPUT SHAPE (StrategyVersionV4Draft):
{
  "name": "<string — concise strategy name>",
  "description": "<string | null>",
  "identity": {
    "tags": ["<string>", ...],
    "direction": "long" | "short" | "both"
  },
  "timeframe_aliases": { "<alias>": "<Nm|Nh|Nd|Nw>", ... },
  "variables": [
    { "name": "<snake_case>", "expression_text": "<expr>", "kind": "expression" | "timeframe" }
  ],
  "entries": {
    "long": { "expression_text": "<bool-expr>" } | null,
    "short": { "expression_text": "<bool-expr>" } | null
  },
  "stops": [
    {
      "mode": "simple" | "expression",
      "scope": "all",
      "simple_type": "%" | "ATR" | "$" | "R" | null,
      "simple_value": <number> | null,
      "expression_text": "<float-expr>" | null
    }
  ],
  "legs": [
    {
      "position": <int starting at 1>,
      "kind": "target" | "runner",
      "size_pct": <0 < float <= 1>,
      "target_type": "%" | "ATR" | "$" | "R" | "feature" | "trail-ATR" | "trail-%" | "trail-$",
      "target_value": <number> | null,
      "on_fill_action": {
        "kind": "be_exact" | "be_plus" | "be_minus" | "tighten_atr" | "tighten_pct" | "leave",
        "offset_value": <number> | null
      }
    }
  ],
  "logical_exits": {
    "long": [{ "template_id": "no_progress"|"opposite_cross"|"session_end"|"bars_since", "params": {} }],
    "short": []
  },
  "notes": ["<natural language commentary string>", ...]
}

IMPORTANT:
  - Return ONLY the JSON object. No markdown. No prose outside the JSON.
  - "notes" is a top-level key you may add; the backend extracts it before parsing the draft.
  - Do not include id, version, created_at, or feature_requirements — these are server-derived.
  - default_strategy_controls_version_id and default_execution_plan_version_id must be null or omitted.
  - Legs size_pct values must sum to exactly 1.0.
"""


def _build_system_prompt() -> str:
    """Build the system prompt, reading the feature catalog at call time."""
    from backend.app.strategies.expression_engine import default_catalog

    catalog = default_catalog()
    feature_lines: list[str] = []
    for spec in sorted(catalog.all(), key=lambda s: (s.category, s.namespace, s.name)):
        if spec.is_timeframed:
            example = f"<tf>.{spec.name}"
            if spec.arity > 0:
                args = ", ".join(f"<{a}>" for a in spec.arg_names)
                example = f"<tf>.{spec.name}({args})"
            feature_lines.append(f"  {example}  [{spec.category}]  — {spec.description}")
        else:
            key = f"{spec.namespace}.{spec.name}" if spec.namespace else spec.name
            feature_lines.append(f"  {key}  [{spec.category}]  — {spec.description}")

    features_block = "\n".join(feature_lines)

    return (
        "You are a trading strategy code generator for the UTOS Trading OS v4.\n"
        "Your ONLY job is to output a valid StrategyVersionV4Draft JSON object.\n\n"
        + _DSL_GRAMMAR
        + "\n"
        + _VALIDATOR_RULES
        + "\n"
        + _EXAMPLE_EXPRESSIONS
        + "\n"
        + "AVAILABLE FEATURE CATALOG (use ONLY these feature names):\n"
        + features_block
        + "\n\n"
        + _OUTPUT_SCHEMA
    )


# ---------------------------------------------------------------------------
# Expression extraction helpers
# ---------------------------------------------------------------------------

def _collect_expressions(draft: StrategyVersionV4Draft) -> list[str]:
    """Return every expression_text present in the draft."""
    exprs: list[str] = []
    for var in draft.variables:
        if var.expression_text.strip():
            exprs.append(var.expression_text)
    if draft.entries.long and draft.entries.long.expression_text.strip():
        exprs.append(draft.entries.long.expression_text)
    if draft.entries.short and draft.entries.short.expression_text.strip():
        exprs.append(draft.entries.short.expression_text)
    for stop in draft.stops:
        if stop.mode == "expression" and stop.expression_text and stop.expression_text.strip():
            exprs.append(stop.expression_text)
    return exprs


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------

def seed_fill_strategy(
    request: AISeedFillRequest,
    llm_client: LLMClient,
    *,
    validate_expression_fn: Callable[..., object],
) -> AISeedFillResponse:
    """Generate a StrategyVersionV4Draft from operator prompt via LLM.

    Steps:
      1. Build system + user prompts.
      2. Call LLM.
      3. Extract optional "notes" key from raw JSON, strip it before Draft parse.
      4. Parse JSON → StrategyVersionV4Draft.
      5. Validate every expression; aggregate errors.
      6. Return AISeedFillResponse (never auto-saves).

    Raises AISeedFillError on:
      - JSON parse failure
      - Pydantic schema validation failure

    Returns AISeedFillResponse even when expressions have errors (valid=False).
    """
    system_prompt = _build_system_prompt()

    user_prompt = request.prompt
    if request.current_draft is not None:
        try:
            draft_json = request.current_draft.model_dump_json(indent=None)
        except Exception:  # noqa: BLE001
            draft_json = "{}"
        user_prompt = (
            user_prompt
            + "\n\nCurrent draft for context (do not copy verbatim; use as reference):\n"
            + draft_json
        )

    llm_req = LLMRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_format_json=True,
        max_tokens=4096,
        temperature=0.3,
    )

    llm_resp = llm_client.invoke(llm_req)
    raw_text = llm_resp.text
    raw_excerpt = raw_text[:500]

    # Parse JSON
    try:
        raw_dict = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AISeedFillError(
            f"LLM returned non-JSON: {raw_excerpt}"
        ) from exc

    if not isinstance(raw_dict, dict):
        raise AISeedFillError(
            f"LLM returned non-object JSON: {raw_excerpt}"
        )

    # Extract notes before pydantic validation (notes is not part of Draft schema)
    notes_raw = raw_dict.pop("notes", [])
    if isinstance(notes_raw, list):
        notes: tuple[str, ...] = tuple(str(n) for n in notes_raw if isinstance(n, str))
    elif isinstance(notes_raw, str):
        notes = (notes_raw,)
    else:
        notes = ()

    # Validate against StrategyVersionV4Draft schema
    try:
        draft = StrategyVersionV4Draft.model_validate(raw_dict)
    except PydanticValidationError as exc:
        raise AISeedFillError(
            f"LLM output did not match draft schema: {exc}"
        ) from exc

    # Validate expressions — collect all errors/warnings; do not raise
    variable_names = [v.name for v in draft.variables]
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for expr_text in _collect_expressions(draft):
        result = validate_expression_fn(expr_text, variable_names)
        # result is a ValidateResult dataclass from expression_api
        if hasattr(result, "errors"):
            for issue in result.errors:
                msg = getattr(issue, "message", str(issue))
                all_errors.append(f"{expr_text!r}: {msg}")
        if hasattr(result, "warnings"):
            for issue in result.warnings:
                msg = getattr(issue, "message", str(issue))
                all_warnings.append(f"{expr_text!r}: {msg}")

    valid = len(all_errors) == 0
    validation_status = ValidationStatusV4(
        valid=valid,
        errors=tuple(all_errors),
        warnings=tuple(all_warnings),
    )

    return AISeedFillResponse(
        draft=draft,
        validation_status=validation_status,
        provider_used=llm_resp.provider,
        model_used=llm_resp.model,
        raw_response_excerpt=raw_excerpt,
        notes=notes,
    )
