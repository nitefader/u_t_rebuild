"""Execution-style preset registry for the Strategy Composer.

Each preset is a deterministic builder that:

1. Fills in default knobs and constructs a typed ``ExecutionStylePresetSpec``
   from operator overrides (the discriminated union in ``execution_style``).
2. Builds a fully-populated ``ExecutionStyleVersion`` so existing legacy
   downstream code continues to function with the populated fields.
3. Produces a ``SignalPlanShapePreview`` that the composer's Tier-1 (no-AI)
   live preview renders against an ``[symbol]`` placeholder. The preview
   contains no UUIDs and never binds to a concrete symbol — symbol binding
   happens at Deployment time via the Watchlist (per the spine doctrine
   `feedback_strategy_symbol_agnostic_spine.md`).

The mapping below is the source of truth for preset → SignalPlan shape.
The runtime can also consume the persisted ``ExecutionStylePresetSpec`` to
reproduce the same intent set when emitting symbol-specific SignalPlans.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.execution_style import (
    BracketSpec,
    BracketRunnerPreset,
    BracketStopTargetPreset,
    ExecutionStylePresetKind,
    ExecutionStylePresetSpec,
    ExecutionStyleVersion,
    MarketEntryMarketExitPreset,
    MultiTargetScaleOutPreset,
    MultiTargetTier,
    OrderType,
    StopEntryMarketExitPreset,
    TimeInForce,
)
from backend.app.domain.signal_plan import (
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanRunner,
    SignalPlanRunnerManagement,
    SignalPlanSide,
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
)


# ---------------------------------------------------------------------------
# Tier-1 SignalPlan shape preview
# ---------------------------------------------------------------------------


class SignalPlanShapePreview(BaseModel):
    """Operator-facing preview of the SignalPlan shape an execution preset emits.

    This is a Tier-1 (no-AI) shape. It deliberately omits ``signal_plan_id``,
    ``deployment_id``, ``strategy_id``, ``strategy_version_id``,
    ``watchlist_snapshot_id``, ``status``, and lifecycle timestamps — they
    are runtime-bound, not composer-bound. ``symbol`` is also absent: the
    operator-facing copy renders ``[symbol]`` as placeholder with the line
    ``"Bound at deployment via Watchlist."``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    preset: ExecutionStylePresetKind
    side_hint: SignalPlanSide
    intent: SignalPlanIntent = SignalPlanIntent.OPEN
    entry: SignalPlanEntry
    stop: SignalPlanStop | None = None
    targets: tuple[SignalPlanTarget, ...] = ()
    runner: SignalPlanRunner | None = None
    notes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Override coercion + spec builder
# ---------------------------------------------------------------------------


def _filter_overrides(payload: dict[str, Any] | None, allowed: set[str]) -> dict[str, Any]:
    if not payload:
        return {}
    return {key: value for key, value in payload.items() if key in allowed}


def build_preset_spec(
    kind: ExecutionStylePresetKind | str,
    overrides: dict[str, Any] | None = None,
) -> ExecutionStylePresetSpec:
    """Build a typed preset spec from a kind string + customize overrides.

    Each preset rejects unknown override keys via Pydantic ``extra="forbid"``
    on ``DomainSchema``. Numeric constraints are also enforced by Pydantic.
    Unknown ``kind`` raises ``ValueError``.
    """

    resolved_kind = ExecutionStylePresetKind(kind) if not isinstance(kind, ExecutionStylePresetKind) else kind

    if resolved_kind is ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT:
        return MarketEntryMarketExitPreset()
    if resolved_kind is ExecutionStylePresetKind.STOP_ENTRY_MARKET_EXIT:
        allowed = _filter_overrides(overrides, {"entry_stop_offset_bps"})
        return StopEntryMarketExitPreset(**allowed)
    if resolved_kind is ExecutionStylePresetKind.BRACKET_STOP_TARGET:
        allowed = _filter_overrides(overrides, {"stop_pct", "target_pct"})
        return BracketStopTargetPreset(**allowed)
    if resolved_kind is ExecutionStylePresetKind.BRACKET_RUNNER:
        allowed = _filter_overrides(overrides, {"first_target_pct", "first_slice_pct", "trail_pct"})
        return BracketRunnerPreset(**allowed)
    if resolved_kind is ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT:
        targets_payload = (overrides or {}).get("targets")
        if targets_payload is None:
            tiers = tuple(
                MultiTargetTier(target_pct=pct, slice_pct=0.25)
                for pct in (1.0, 2.0, 3.0, 4.0)
            )
        else:
            tiers = tuple(
                MultiTargetTier(target_pct=row["target_pct"], slice_pct=row["slice_pct"])
                for row in targets_payload
            )
        stop_pct = (overrides or {}).get("stop_pct")
        return MultiTargetScaleOutPreset(targets=tiers, stop_pct=stop_pct)

    raise ValueError(f"unknown execution_style_preset kind: {kind!r}")


# ---------------------------------------------------------------------------
# ExecutionStyleVersion builder
# ---------------------------------------------------------------------------


_PRESET_DISPLAY_NAMES: dict[ExecutionStylePresetKind, str] = {
    ExecutionStylePresetKind.MARKET_ENTRY_MARKET_EXIT: "Market Entry / Market Exit",
    ExecutionStylePresetKind.STOP_ENTRY_MARKET_EXIT: "Stop Entry / Market Exit",
    ExecutionStylePresetKind.BRACKET_STOP_TARGET: "Bracket: Stop + Target",
    ExecutionStylePresetKind.BRACKET_RUNNER: "Bracket + Runner",
    ExecutionStylePresetKind.MULTI_TARGET_SCALE_OUT: "Multi-Target Scale-Out",
}


def preset_display_name(kind: ExecutionStylePresetKind) -> str:
    return _PRESET_DISPLAY_NAMES[kind]


def build_execution_style_version(
    preset_spec: ExecutionStylePresetSpec,
) -> ExecutionStyleVersion:
    """Construct a fully-populated ExecutionStyleVersion from a preset spec.

    The returned version has its legacy fields (entry_order_type, bracket,
    scale_out_enabled, etc.) populated to be consistent with the preset, so
    legacy callers that read those fields keep working. The preset itself
    is also persisted on the ``preset`` field so the runtime can reproduce
    the SignalPlan shape deterministically.
    """

    base_kwargs = {
        "id": uuid4(),
        "execution_style_id": uuid4(),
        "version": 1,
        "name": _PRESET_DISPLAY_NAMES[preset_spec.kind],
        "time_in_force": TimeInForce.DAY,
        "preset": preset_spec,
    }

    if isinstance(preset_spec, MarketEntryMarketExitPreset):
        return ExecutionStyleVersion(
            entry_order_type=OrderType.MARKET,
            exit_order_type=OrderType.MARKET,
            bracket=BracketSpec(enabled=False),
            trailing_stop_enabled=False,
            scale_out_enabled=False,
            **base_kwargs,
        )
    if isinstance(preset_spec, StopEntryMarketExitPreset):
        return ExecutionStyleVersion(
            entry_order_type=OrderType.STOP,
            exit_order_type=OrderType.MARKET,
            entry_limit_offset_bps=preset_spec.entry_stop_offset_bps,
            bracket=BracketSpec(enabled=False),
            trailing_stop_enabled=False,
            scale_out_enabled=False,
            **base_kwargs,
        )
    if isinstance(preset_spec, BracketStopTargetPreset):
        return ExecutionStyleVersion(
            entry_order_type=OrderType.MARKET,
            exit_order_type=OrderType.MARKET,
            bracket=BracketSpec(
                enabled=True,
                stop_loss_r_multiple=preset_spec.stop_pct,
                take_profit_r_multiple=preset_spec.target_pct,
            ),
            trailing_stop_enabled=False,
            scale_out_enabled=False,
            **base_kwargs,
        )
    if isinstance(preset_spec, BracketRunnerPreset):
        return ExecutionStyleVersion(
            entry_order_type=OrderType.MARKET,
            exit_order_type=OrderType.MARKET,
            bracket=BracketSpec(
                enabled=True,
                stop_loss_r_multiple=preset_spec.trail_pct,
                take_profit_r_multiple=preset_spec.first_target_pct,
            ),
            trailing_stop_enabled=True,
            scale_out_enabled=True,
            **base_kwargs,
        )
    if isinstance(preset_spec, MultiTargetScaleOutPreset):
        last_target_pct = preset_spec.targets[-1].target_pct
        return ExecutionStyleVersion(
            entry_order_type=OrderType.MARKET,
            exit_order_type=OrderType.MARKET,
            bracket=BracketSpec(
                enabled=preset_spec.stop_pct is not None,
                stop_loss_r_multiple=preset_spec.stop_pct,
                take_profit_r_multiple=last_target_pct if preset_spec.stop_pct is not None else None,
            )
            if preset_spec.stop_pct is not None
            else BracketSpec(enabled=False),
            trailing_stop_enabled=False,
            scale_out_enabled=True,
            **base_kwargs,
        )

    raise TypeError(f"unsupported preset type: {type(preset_spec).__name__}")


# ---------------------------------------------------------------------------
# SignalPlan shape preview (Tier-1, symbol-agnostic)
# ---------------------------------------------------------------------------


def _percent_to_quantity_pct(slice_pct: float) -> float:
    """Convert a 0..1 slice percentage to a SignalPlanTarget.quantity_pct (0..100).

    SignalPlanTarget enforces ``0 < quantity_pct <= 100``, so this clamps the
    upper bound at 100 to satisfy the validator while preserving operator intent.
    """

    return max(0.000_001, min(100.0, slice_pct * 100.0))


def build_signal_plan_shape_preview(
    preset_spec: ExecutionStylePresetSpec,
    side_hint: SignalPlanSide = SignalPlanSide.LONG,
) -> SignalPlanShapePreview:
    """Render a Tier-1 SignalPlan-shape preview for the given preset.

    The preview is symbol-agnostic; the UI renders ``[symbol]`` placeholder.
    """

    if isinstance(preset_spec, MarketEntryMarketExitPreset):
        return SignalPlanShapePreview(
            preset=preset_spec.kind,
            side_hint=side_hint,
            entry=SignalPlanEntry(order_type=OrderType.MARKET),
            notes=(
                "Market order in on entry signal; market order out on exit signal.",
                "logical_exit (if declared) overrides the market-out path.",
            ),
        )
    if isinstance(preset_spec, StopEntryMarketExitPreset):
        return SignalPlanShapePreview(
            preset=preset_spec.kind,
            side_hint=side_hint,
            entry=SignalPlanEntry(order_type=OrderType.STOP),
            notes=(
                f"Stop order at signal-bar reference + {preset_spec.entry_stop_offset_bps:g} bps offset.",
                "Reference = signal-bar high for long, signal-bar low for short.",
                "Market order out on exit signal.",
            ),
        )
    if isinstance(preset_spec, BracketStopTargetPreset):
        return SignalPlanShapePreview(
            preset=preset_spec.kind,
            side_hint=side_hint,
            entry=SignalPlanEntry(order_type=OrderType.MARKET),
            stop=SignalPlanStop(
                type="static_pct",
                rule=f"entry * (1 - {preset_spec.stop_pct:g}/100) for long; mirrored for short",
                required=True,
            ),
            targets=(
                SignalPlanTarget(
                    label="bracket_target",
                    action=SignalPlanTargetAction.CLOSE,
                    quantity_pct=100.0,
                    rule=f"entry * (1 + {preset_spec.target_pct:g}/100) for long; mirrored for short",
                    order_type_preference=OrderType.LIMIT,
                ),
            ),
            notes=(
                "Market in. OCO bracket: stop and target are linked.",
                "Whichever fills first cancels the other.",
                "logical_exit (if declared) cancels both.",
            ),
        )
    if isinstance(preset_spec, BracketRunnerPreset):
        first_qty_pct = _percent_to_quantity_pct(preset_spec.first_slice_pct)
        runner_qty_pct = max(0.0, 100.0 - first_qty_pct)
        return SignalPlanShapePreview(
            preset=preset_spec.kind,
            side_hint=side_hint,
            entry=SignalPlanEntry(order_type=OrderType.MARKET),
            targets=(
                SignalPlanTarget(
                    label="first_target",
                    action=SignalPlanTargetAction.REDUCE,
                    quantity_pct=first_qty_pct,
                    rule=f"entry * (1 + {preset_spec.first_target_pct:g}/100) for long",
                    order_type_preference=OrderType.LIMIT,
                ),
            ),
            runner=SignalPlanRunner(
                quantity_pct=runner_qty_pct,
                management=SignalPlanRunnerManagement.TRAIL,
                trail_rule=f"trailing_pct={preset_spec.trail_pct:g}",
            ),
            notes=(
                f"First target releases {first_qty_pct:g}% of position.",
                f"Runner ({runner_qty_pct:g}%) trails by {preset_spec.trail_pct:g}%.",
                "logical_exit on the runner falls through to MANUAL_REVIEW unless declared.",
            ),
        )
    if isinstance(preset_spec, MultiTargetScaleOutPreset):
        targets: list[SignalPlanTarget] = []
        for index, tier in enumerate(preset_spec.targets, start=1):
            targets.append(
                SignalPlanTarget(
                    label=f"target_{index}",
                    action=SignalPlanTargetAction.REDUCE if index < len(preset_spec.targets) else SignalPlanTargetAction.CLOSE,
                    quantity_pct=_percent_to_quantity_pct(tier.slice_pct),
                    rule=f"entry * (1 + {tier.target_pct:g}/100) for long",
                    order_type_preference=OrderType.LIMIT,
                )
            )
        stop = (
            SignalPlanStop(
                type="static_pct",
                rule=f"entry * (1 - {preset_spec.stop_pct:g}/100) for long; mirrored for short",
                required=True,
            )
            if preset_spec.stop_pct is not None
            else None
        )
        notes_lines = [
            f"{len(targets)} scaling targets; each fill reduces the position by its slice%.",
        ]
        if preset_spec.stop_pct is not None:
            notes_lines.append(f"Static stop at {preset_spec.stop_pct:g}% covers the remainder.")
        else:
            notes_lines.append("No stop attached; rely on logical_exit if a tail risk policy is needed.")
        return SignalPlanShapePreview(
            preset=preset_spec.kind,
            side_hint=side_hint,
            entry=SignalPlanEntry(order_type=OrderType.MARKET),
            stop=stop,
            targets=tuple(targets),
            notes=tuple(notes_lines),
        )

    raise TypeError(f"unsupported preset type: {type(preset_spec).__name__}")
