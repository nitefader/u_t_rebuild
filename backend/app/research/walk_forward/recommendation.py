"""Aggregate per-fold OOS metrics into a single ship/no-ship recommendation.

Defaults (operator-authorized 2026-04-27):

- Recommendation score = ``score_weights.oos_sharpe_p25 * oos_sharpe_p25 +
  score_weights.stability * stability_score``. Default weights are
  ``{oos_sharpe_p25: 0.5, stability: 0.5}`` (50/50 — operator preferred this
  over a Sharpe-leaning blend; both weights configurable per-run via the
  ``score_weights`` payload, with ``DEFAULT_SCORE_WEIGHTS`` as the reset
  reference).
- ship_recommended: ``oos_sharpe_p25 >= 0.5`` AND ``is_oos_decay.sharpe <
  0.5`` AND ``folds_passed_ratio >= 0.6`` AND ``oos_max_dd >= -0.25``.
- do_not_ship: ``oos_sharpe_p50 < 0`` OR ``is_oos_decay.sharpe > 1.5`` OR
  ``oos_max_dd <= -0.40`` (max drawdown floor; deeper than 40% rejects
  outright regardless of Sharpe).
- needs_more_data: everything else.

All weights and thresholds are tunable per-request via ``score_weights`` +
``ship_thresholds`` payloads.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal


RecommendationOutcome = Literal["ship_recommended", "needs_more_data", "do_not_ship"]


DEFAULT_SCORE_WEIGHTS: dict[str, float] = {
    "oos_sharpe_p25": 0.5,
    "stability": 0.5,
}

DEFAULT_SHIP_THRESHOLDS: dict[str, float] = {
    "ship_oos_sharpe_p25_min": 0.5,
    "ship_is_oos_decay_max": 0.5,
    "ship_folds_passed_ratio_min": 0.6,
    # Max-DD floor for ship: drawdowns deeper than 25% disqualify the run.
    "ship_oos_max_dd_min": -0.25,
    "do_not_ship_oos_sharpe_p50_max": 0.0,
    "do_not_ship_is_oos_decay_min": 1.5,
    # Max-DD ceiling for do-not-ship: anything ≤ -40% is disqualified outright.
    "do_not_ship_oos_max_dd_max": -0.40,
}


@dataclass(frozen=True)
class CandidateAggregate:
    parameters: dict[str, Any]
    oos_sharpe: float
    oos_max_dd: float
    oos_return: float
    oos_hit_rate: float
    stability: float
    picked_in_folds: int
    score: float
    recommended: bool


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 1:
        return ordered[-1]
    idx = (len(ordered) - 1) * pct
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _params_key(parameters: dict[str, Any]) -> str:
    return ",".join(f"{k}={parameters[k]}" for k in sorted(parameters))


def build_recommendation(
    *,
    fold_results: list[dict[str, Any]],
    folds_passed_threshold_sharpe: float = 0.0,
    ship_thresholds: dict[str, float] | None = None,
    score_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate per-fold OOS metrics + sweep results into the WF recommendation.

    ``fold_results`` is a list of dicts shaped like::

        {
            "fold_index": int,
            "is_metrics": {...},
            "oos_metrics": {...},
            "selected_parameters": {...} | None,
            "candidate_scores": [(parameters, oos_metrics), ...],
        }

    Returns the aggregate metrics block + recommended_risk_plan + recommendation
    enum that callers persist on the WalkForwardRun.metrics JsonDict.
    """
    weights = {**DEFAULT_SCORE_WEIGHTS, **(score_weights or {})}
    sharpe_weight = float(weights.get("oos_sharpe_p25", DEFAULT_SCORE_WEIGHTS["oos_sharpe_p25"]))
    stability_weight = float(weights.get("stability", DEFAULT_SCORE_WEIGHTS["stability"]))

    if not fold_results:
        return {
            "fold_count": 0,
            "metrics": {},
            "recommended_risk_plan": None,
            "recommendation": "needs_more_data",
            "candidates": [],
            "score_weights": {"oos_sharpe_p25": sharpe_weight, "stability": stability_weight},
            "default_score_weights": dict(DEFAULT_SCORE_WEIGHTS),
        }

    thresholds = {**DEFAULT_SHIP_THRESHOLDS, **(ship_thresholds or {})}

    oos_sharpes = [float(f["oos_metrics"].get("sharpe", 0) or 0) for f in fold_results]
    oos_returns = [float(f["oos_metrics"].get("cagr", 0) or 0) for f in fold_results]
    oos_hit_rates = [float(f["oos_metrics"].get("hit_rate", 0) or 0) for f in fold_results]
    oos_max_dds = [float(f["oos_metrics"].get("max_drawdown", 0) or 0) for f in fold_results]
    is_sharpes = [float(f["is_metrics"].get("sharpe", 0) or 0) for f in fold_results]

    # Per-fold IS-vs-OOS decay (lower = better forwarding; large positive = overfitting alarm)
    is_oos_decays = [
        max(is_sharpes[i] - oos_sharpes[i], 0.0) for i in range(len(fold_results))
    ]
    decay_sharpe = _mean(is_oos_decays)

    folds_passed = sum(1 for s in oos_sharpes if s >= folds_passed_threshold_sharpe)
    folds_passed_ratio = folds_passed / len(fold_results)

    # Stability: how often the same parameter set was picked across folds.
    selected_params = [f.get("selected_parameters") for f in fold_results if f.get("selected_parameters")]
    parameter_stability_score = 0.0
    if selected_params:
        param_keys = [_params_key(p) for p in selected_params]
        most_common_count = Counter(param_keys).most_common(1)[0][1]
        parameter_stability_score = most_common_count / len(selected_params)

    # Regime fit: standard deviation of OOS Sharpe across folds, normalised.
    if len(oos_sharpes) > 1:
        mean_oos = _mean(oos_sharpes)
        var = sum((s - mean_oos) ** 2 for s in oos_sharpes) / (len(oos_sharpes) - 1)
        sigma = var ** 0.5
        denom = max(abs(mean_oos), 1e-6)
        regime_fit_score = max(0.0, min(1.0, 1.0 - sigma / (denom + 1.0)))
    else:
        regime_fit_score = 0.5  # single fold = unknown stability

    # Build candidate landscape (across-fold OOS aggregates per parameter set)
    candidates_by_key: dict[str, list[tuple[dict[str, Any], dict[str, Any], bool]]] = {}
    for fold in fold_results:
        was_winner_params = fold.get("selected_parameters")
        was_winner_key = _params_key(was_winner_params) if was_winner_params else None
        for parameters, oos_metrics in fold.get("candidate_scores", []):
            key = _params_key(parameters)
            picked_here = key == was_winner_key
            candidates_by_key.setdefault(key, []).append((parameters, oos_metrics, picked_here))

    candidates: list[CandidateAggregate] = []
    for key, entries in candidates_by_key.items():
        parameters = entries[0][0]
        sharpes = [float(e[1].get("sharpe", 0) or 0) for e in entries]
        max_dds = [float(e[1].get("max_drawdown", 0) or 0) for e in entries]
        returns = [float(e[1].get("cagr", 0) or 0) for e in entries]
        hit_rates = [float(e[1].get("hit_rate", 0) or 0) for e in entries]
        picked = sum(1 for e in entries if e[2])

        cand_p25 = _percentile(sharpes, 0.25)
        # Per-candidate stability: 1 - sigma/(|mean|+1)
        cand_stability = 0.5
        if len(sharpes) > 1:
            mean_s = _mean(sharpes)
            v = sum((s - mean_s) ** 2 for s in sharpes) / (len(sharpes) - 1)
            sigma = v ** 0.5
            cand_stability = max(0.0, min(1.0, 1.0 - sigma / (abs(mean_s) + 1.0)))
        score = sharpe_weight * cand_p25 + stability_weight * cand_stability
        candidates.append(
            CandidateAggregate(
                parameters=parameters,
                oos_sharpe=round(_mean(sharpes), 6),
                oos_max_dd=round(min(max_dds) if max_dds else 0.0, 6),
                oos_return=round(_mean(returns), 6),
                oos_hit_rate=round(_mean(hit_rates), 6),
                stability=round(cand_stability, 6),
                picked_in_folds=picked,
                score=round(score, 6),
                recommended=False,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    if candidates:
        winner = candidates[0]
        candidates = [
            CandidateAggregate(
                parameters=c.parameters,
                oos_sharpe=c.oos_sharpe,
                oos_max_dd=c.oos_max_dd,
                oos_return=c.oos_return,
                oos_hit_rate=c.oos_hit_rate,
                stability=c.stability,
                picked_in_folds=c.picked_in_folds,
                score=c.score,
                recommended=(c is winner),
            )
            for c in candidates
        ]
    else:
        winner = None

    aggregate_metrics = {
        "median_oos_sharpe": round(_percentile(oos_sharpes, 0.5), 6),
        "mean_oos_sharpe": round(_mean(oos_sharpes), 6),
        "oos_sharpe_p25": round(_percentile(oos_sharpes, 0.25), 6),
        "oos_sharpe_p75": round(_percentile(oos_sharpes, 0.75), 6),
        "median_oos_return": round(_percentile(oos_returns, 0.5), 6),
        "oos_max_dd": round(min(oos_max_dds) if oos_max_dds else 0.0, 6),
        "oos_hit_rate": round(_mean(oos_hit_rates), 6),
        "is_oos_decay": {
            "sharpe": round(decay_sharpe, 6),
        },
        "parameter_stability_score": round(parameter_stability_score, 6),
        "regime_fit_score": round(regime_fit_score, 6),
        "folds_passed_ratio": round(folds_passed_ratio, 6),
        "folds_passed_count": folds_passed,
    }

    recommended_risk_plan: dict[str, Any] | None = None
    if winner is not None:
        explanation = (
            f"Selected because score {winner.score:.3f} = "
            f"{sharpe_weight:.2f} × OOS-Sharpe-p25 ({_percentile([c.oos_sharpe for c in candidates if c.recommended], 0.5):.3f}) + "
            f"{stability_weight:.2f} × stability ({winner.stability:.3f}); "
            f"picked in {winner.picked_in_folds} of {len(fold_results)} fold(s); "
            f"OOS Sharpe avg {winner.oos_sharpe:.3f}, max-DD {winner.oos_max_dd:.3%}. "
            f"Stability-aware: prefers consistent over brilliant-then-disastrous."
        )
        recommended_risk_plan = {
            "source": "walk_forward",
            "candidate_risk_plan_version_id": None,  # populated when contract slice 2 lands
            "parameters": winner.parameters,
            "score": winner.score,
            "stability_metrics": {
                "stability": winner.stability,
                "picked_in_folds": winner.picked_in_folds,
                "fold_count": len(fold_results),
            },
            "drawdown_metrics": {"oos_max_dd": winner.oos_max_dd},
            "out_of_sample_metrics": {
                "oos_sharpe_avg": winner.oos_sharpe,
                "oos_return_avg": winner.oos_return,
                "oos_hit_rate_avg": winner.oos_hit_rate,
            },
            "explanation": explanation,
        }

    # Recommendation enum.
    # Max-DD is part of *both* gates: a strategy with brutal drawdowns can't
    # ship even if Sharpe looks fine, and an outright catastrophic drawdown
    # forces do-not-ship regardless of other signals.
    aggregate_max_dd = aggregate_metrics["oos_max_dd"]
    if (
        aggregate_metrics["oos_sharpe_p25"] >= thresholds["ship_oos_sharpe_p25_min"]
        and aggregate_metrics["is_oos_decay"]["sharpe"] < thresholds["ship_is_oos_decay_max"]
        and folds_passed_ratio >= thresholds["ship_folds_passed_ratio_min"]
        and aggregate_max_dd >= thresholds["ship_oos_max_dd_min"]
    ):
        recommendation: RecommendationOutcome = "ship_recommended"
    elif (
        aggregate_metrics["median_oos_sharpe"] < thresholds["do_not_ship_oos_sharpe_p50_max"]
        or aggregate_metrics["is_oos_decay"]["sharpe"] > thresholds["do_not_ship_is_oos_decay_min"]
        or aggregate_max_dd <= thresholds["do_not_ship_oos_max_dd_max"]
    ):
        recommendation = "do_not_ship"
    else:
        recommendation = "needs_more_data"

    return {
        "fold_count": len(fold_results),
        "metrics": aggregate_metrics,
        "recommended_risk_plan": recommended_risk_plan,
        "recommendation": recommendation,
        "score_weights": {"oos_sharpe_p25": sharpe_weight, "stability": stability_weight},
        "default_score_weights": dict(DEFAULT_SCORE_WEIGHTS),
        "default_thresholds": dict(DEFAULT_SHIP_THRESHOLDS),
        "candidates": [
            {
                "parameters": c.parameters,
                "oos_sharpe": c.oos_sharpe,
                "oos_max_dd": c.oos_max_dd,
                "oos_return": c.oos_return,
                "oos_hit_rate": c.oos_hit_rate,
                "stability": c.stability,
                "picked_in_folds": c.picked_in_folds,
                "score": c.score,
                "recommended": c.recommended,
            }
            for c in candidates
        ],
        "thresholds_applied": thresholds,
    }
