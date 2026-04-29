"""BacktestMetricsService — apply post-fill cost model + compute the 11 metrics.

Cost model is **post-fill, metrics-only** in this slice. Commission and
slippage adjust the PnL of fills the spine already produced; they do not
change which fills the spine produces. Cost-aware execution (slippage moving
the broker's fill price, spread gating limit fills, partial fills tied to
volume) is a follow-up slice on ``SimulatedBroker``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import JsonDict
from backend.app.research.regimes import RegimeClassifier
from backend.app.simulation import SimulationReplayResult


class CostModel(BaseModel):
    """Per-trade commission + per-notional slippage haircut."""

    model_config = ConfigDict(extra="allow", frozen=True)

    commission_per_trade: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=0.0, ge=0)


@dataclass(frozen=True)
class BacktestMetricsBundle:
    """Cost-adjusted equity curve, trade ledger, and the 11 metrics."""

    metrics: dict[str, Any]
    equity_curve: tuple[dict[str, Any], ...]
    drawdown_series: tuple[dict[str, Any], ...]
    trade_ledger: tuple[dict[str, Any], ...]
    per_symbol_breakdown: tuple[dict[str, Any], ...]
    regime_tags: tuple[dict[str, Any], ...]
    per_regime_metrics: dict[str, dict[str, float]]
    cost_model: dict[str, float]


class BacktestMetricsService:
    def __init__(self, *, regime_classifier: RegimeClassifier | None = None) -> None:
        self._regimes = regime_classifier or RegimeClassifier()

    def compute(
        self,
        *,
        replay: SimulationReplayResult,
        cost_model: CostModel,
        initial_capital: float,
        timeframe: str,
    ) -> BacktestMetricsBundle:
        cost = cost_model
        adjusted_trades: list[dict[str, Any]] = []
        gross_wins = 0.0
        gross_losses = 0.0
        per_symbol: dict[str, dict[str, float]] = {}
        for trade in replay.trades:
            notional = trade.qty * trade.entry_price
            cost_amount = cost.commission_per_trade + notional * cost.slippage_bps / 10_000
            net_pnl = trade.realized_pnl - cost_amount
            adjusted_trades.append(
                {
                    "trade_ref": trade.id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "qty": trade.qty,
                    "entry_price": round(trade.entry_price, 4),
                    "exit_price": round(trade.exit_price, 4),
                    "notional": round(notional, 2),
                    "gross_return": (
                        round((trade.exit_price - trade.entry_price) / trade.entry_price, 6)
                        if trade.entry_price > 0
                        else 0.0
                    ),
                    "cost": round(cost_amount, 4),
                    "net_pnl": round(net_pnl, 4),
                    "opened_at": trade.opened_at.isoformat(),
                    "closed_at": trade.closed_at.isoformat(),
                    "exit_reason": trade.exit_reason.value,
                    "risk_decision_id": str(trade.risk_decision_id) if trade.risk_decision_id else None,
                    "signal_plan_id": str(trade.signal_plan_id) if trade.signal_plan_id else None,
                    "risk_plan_version_id": (
                        str(trade.risk_plan_version_id) if trade.risk_plan_version_id else None
                    ),
                }
            )
            if net_pnl >= 0:
                gross_wins += net_pnl
            else:
                gross_losses += abs(net_pnl)
            sym_acc = per_symbol.setdefault(
                trade.symbol,
                {"trade_count": 0, "net_pnl": 0.0, "turnover": 0.0},
            )
            sym_acc["trade_count"] = float(int(sym_acc["trade_count"]) + 1)
            sym_acc["net_pnl"] = round(sym_acc["net_pnl"] + net_pnl, 4)
            sym_acc["turnover"] = round(sym_acc["turnover"] + notional, 2)

        # Cost-adjusted equity curve = original equity curve - cumulative cost-adjustments at each trade close
        equity_curve_points: list[dict[str, Any]] = []
        drawdown_points: list[dict[str, Any]] = []
        equity = initial_capital
        peak = initial_capital
        if not replay.equity_curve:
            equity_curve_points.append({"step": 0, "label": "start", "equity": round(equity, 2)})
            drawdown_points.append({"step": 0, "drawdown": 0.0})
        else:
            adjustments_by_close = self._cumulative_adjustments_by_timestamp(adjusted_trades, replay)
            cumulative_adjustment = 0.0
            for index, point in enumerate(replay.equity_curve):
                ts_iso = point.timestamp.isoformat()
                cumulative_adjustment = adjustments_by_close.get(ts_iso, cumulative_adjustment)
                adjusted_equity = round(point.equity - cumulative_adjustment, 4)
                equity = adjusted_equity
                peak = max(peak, adjusted_equity)
                drawdown = 0.0 if peak == 0 else round((adjusted_equity - peak) / peak, 6)
                equity_curve_points.append(
                    {
                        "step": index + 1,
                        "label": ts_iso,
                        "equity": adjusted_equity,
                    }
                )
                drawdown_points.append({"step": index + 1, "drawdown": drawdown})

        trade_count = len(adjusted_trades)
        wins = sum(1 for trade in adjusted_trades if trade["net_pnl"] >= 0)
        net_profit = equity - initial_capital
        max_drawdown = min((float(p["drawdown"]) for p in drawdown_points), default=0.0)
        returns = [float(t["gross_return"]) for t in adjusted_trades]
        avg_return = sum(returns) / trade_count if trade_count else 0.0
        downside = [r for r in returns if r < 0]
        volatility = _stddev(returns)
        downside_dev = _stddev(downside)
        cagr = round((equity / initial_capital) - 1.0, 6) if initial_capital > 0 else 0.0
        sharpe = round(avg_return / volatility * sqrt(trade_count), 6) if volatility else 0.0
        sortino = round(avg_return / downside_dev * sqrt(trade_count), 6) if downside_dev else 0.0
        calmar = round(cagr / abs(max_drawdown), 6) if max_drawdown else 0.0
        hit_rate = round(wins / trade_count, 6) if trade_count else 0.0
        profit_factor = (
            round(gross_wins / gross_losses, 6)
            if gross_losses
            else round(gross_wins, 6)
        )
        expectancy = round(net_profit / trade_count, 6) if trade_count else 0.0
        turnover_total = sum(float(s["turnover"]) for s in per_symbol.values())
        turnover = round(turnover_total / initial_capital, 6) if initial_capital else 0.0
        time_in_market = round(min(1.0, len(adjusted_trades) / max(len(equity_curve_points), 1)), 6)
        exposure = time_in_market

        # Per-symbol breakdown
        per_symbol_rows = [
            {
                "symbol": symbol,
                "trade_count": int(values["trade_count"]),
                "net_pnl": round(values["net_pnl"], 4),
                "return": round(values["net_pnl"] / values["turnover"], 6) if values["turnover"] else 0.0,
                "turnover": round(values["turnover"], 2),
            }
            for symbol, values in sorted(per_symbol.items())
        ]

        # Per-regime tags + per-regime metrics
        regime_tags, per_regime_metrics = self._build_regime_attribution(replay, timeframe)

        metrics = {
            "cagr": cagr,
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "max_drawdown": max_drawdown,
            "hit_rate": hit_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "exposure": exposure,
            "turnover": turnover,
            "time_in_market": time_in_market,
        }
        return BacktestMetricsBundle(
            metrics=metrics,
            equity_curve=tuple(equity_curve_points),
            drawdown_series=tuple(drawdown_points),
            trade_ledger=tuple(adjusted_trades),
            per_symbol_breakdown=tuple(per_symbol_rows),
            regime_tags=tuple(regime_tags),
            per_regime_metrics=per_regime_metrics,
            cost_model={
                "commission_per_trade": cost.commission_per_trade,
                "slippage_bps": cost.slippage_bps,
            },
        )

    @staticmethod
    def _cumulative_adjustments_by_timestamp(
        adjusted_trades: list[dict[str, Any]],
        replay: SimulationReplayResult,
    ) -> dict[str, float]:
        adjustments: list[tuple[str, float]] = []
        cum = 0.0
        for trade, original in zip(adjusted_trades, replay.trades):
            adjustment = original.realized_pnl - trade["net_pnl"]
            cum += adjustment
            adjustments.append((original.closed_at.isoformat(), cum))
        return dict(adjustments)

    def _build_regime_attribution(
        self,
        replay: SimulationReplayResult,
        timeframe: str,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
        if not replay.equity_curve:
            return [], {}
        prices_by_symbol: dict[str, list[float]] = {}
        regime_tags: list[dict[str, Any]] = []
        regime_pnl: dict[str, float] = {}
        regime_counts: dict[str, int] = {}
        regime_confidence: dict[str, float] = {}
        for trade in replay.trades:
            window = prices_by_symbol.setdefault(trade.symbol, [])
            window.append(trade.entry_price)
            window.append(trade.exit_price)
            if len(window) < 2:
                continue
            classification = self._regimes.classify(
                symbol=trade.symbol,
                timeframe=timeframe,
                bar_window=tuple(window[-8:]),
            )
            regime_tags.append(
                {
                    "trade_ref": trade.id,
                    "symbol": trade.symbol,
                    "regime": classification.label,
                    "confidence": classification.confidence,
                }
            )
            regime_counts[classification.label] = regime_counts.get(classification.label, 0) + 1
            regime_confidence[classification.label] = (
                regime_confidence.get(classification.label, 0.0) + classification.confidence
            )
            regime_pnl[classification.label] = regime_pnl.get(classification.label, 0.0) + trade.realized_pnl
        per_regime_metrics = {
            label: {
                "bar_count": float(regime_counts[label]),
                "avg_confidence": round(regime_confidence[label] / regime_counts[label], 6),
                "net_pnl": round(regime_pnl.get(label, 0.0), 4),
            }
            for label in sorted(regime_counts)
        }
        return regime_tags, per_regime_metrics


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return sqrt(variance)
