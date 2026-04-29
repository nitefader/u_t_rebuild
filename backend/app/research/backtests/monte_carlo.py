"""MonteCarloAnalyzer — bootstrap-on-trades and block-bootstrap-on-bar-returns.

Operator-confirmed methods (see ``RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT.md``
and the approved plan): trade-PnL bootstrap with replacement, plus block
bootstrap on bar returns to preserve serial correlation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import sqrt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MonteCarloMethod = Literal["trade_bootstrap", "block_bootstrap"]


class MonteCarloConfig(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    enabled: bool = True
    method: MonteCarloMethod = "trade_bootstrap"
    replications: int = Field(default=1000, ge=10, le=100_000)
    block_size: int = Field(default=5, ge=2, le=200)
    seed: int = Field(default=42, ge=0)


@dataclass(frozen=True)
class MonteCarloResult:
    method: str
    replications: int
    seed: int
    terminal_equity: dict[str, float]
    sharpe: dict[str, float]
    max_drawdown: dict[str, float]
    final_equity_histogram: list[dict[str, float]]


class MonteCarloAnalyzer:
    def run(
        self,
        *,
        trade_pnls: list[float],
        bar_returns: list[float],
        initial_capital: float,
        config: MonteCarloConfig,
    ) -> MonteCarloResult:
        if not config.enabled:
            return _empty_result(config)
        rng = random.Random(config.seed)
        terminal_values: list[float] = []
        sharpes: list[float] = []
        max_drawdowns: list[float] = []

        for _ in range(config.replications):
            sample = self._sample(
                method=config.method,
                trade_pnls=trade_pnls,
                bar_returns=bar_returns,
                rng=rng,
                block_size=config.block_size,
            )
            equity, sharpe, max_dd = _equity_path_stats(
                sample=sample,
                initial_capital=initial_capital,
                method=config.method,
            )
            terminal_values.append(equity)
            sharpes.append(sharpe)
            max_drawdowns.append(max_dd)

        return MonteCarloResult(
            method=config.method,
            replications=config.replications,
            seed=config.seed,
            terminal_equity=_percentile_bands(terminal_values),
            sharpe=_percentile_bands(sharpes),
            max_drawdown=_percentile_bands(max_drawdowns),
            final_equity_histogram=_histogram(terminal_values, bins=20),
        )

    @staticmethod
    def _sample(
        *,
        method: MonteCarloMethod,
        trade_pnls: list[float],
        bar_returns: list[float],
        rng: random.Random,
        block_size: int,
    ) -> list[float]:
        if method == "trade_bootstrap":
            if not trade_pnls:
                return []
            return [rng.choice(trade_pnls) for _ in range(len(trade_pnls))]
        if not bar_returns:
            return []
        n = len(bar_returns)
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(0, max(n - block_size + 1, 1))
            block = bar_returns[start : start + block_size]
            sample.extend(block)
        return sample[:n]


def _empty_result(config: MonteCarloConfig) -> MonteCarloResult:
    empty_band = {"p05": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0}
    return MonteCarloResult(
        method=config.method,
        replications=0,
        seed=config.seed,
        terminal_equity=dict(empty_band),
        sharpe=dict(empty_band),
        max_drawdown=dict(empty_band),
        final_equity_histogram=[],
    )


def _equity_path_stats(
    *,
    sample: list[float],
    initial_capital: float,
    method: str,
) -> tuple[float, float, float]:
    if not sample:
        return initial_capital, 0.0, 0.0
    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    rets: list[float] = []
    for value in sample:
        if method == "trade_bootstrap":
            equity += value
            if initial_capital > 0:
                rets.append(value / initial_capital)
        else:
            equity *= 1 + value
            rets.append(value)
        peak = max(peak, equity)
        if peak > 0:
            dd = (equity - peak) / peak
            max_dd = min(max_dd, dd)
    if not rets:
        return equity, 0.0, max_dd
    mean = sum(rets) / len(rets)
    variance = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    sigma = sqrt(variance)
    sharpe = round(mean / sigma * sqrt(len(rets)), 6) if sigma else 0.0
    return round(equity, 4), sharpe, round(max_dd, 6)


def _percentile_bands(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p05": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "p95": 0.0}
    ordered = sorted(values)
    return {
        "p05": round(_percentile(ordered, 0.05), 4),
        "p25": round(_percentile(ordered, 0.25), 4),
        "p50": round(_percentile(ordered, 0.50), 4),
        "p75": round(_percentile(ordered, 0.75), 4),
        "p95": round(_percentile(ordered, 0.95), 4),
    }


def _percentile(ordered: list[float], q: float) -> float:
    if not ordered:
        return 0.0
    if q <= 0:
        return ordered[0]
    if q >= 1:
        return ordered[-1]
    idx = (len(ordered) - 1) * q
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _histogram(values: list[float], *, bins: int) -> list[dict[str, float]]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [{"bin_start": lo, "bin_end": lo, "count": float(len(values))}]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / width), bins - 1)
        counts[idx] += 1
    return [
        {
            "bin_start": round(lo + i * width, 4),
            "bin_end": round(lo + (i + 1) * width, 4),
            "count": float(counts[i]),
        }
        for i in range(bins)
    ]
