"""Integration test: each starter strategy draft round-trips through StrategyV4Service.save
without UUID validation errors.

Source-of-truth for starter shapes lives in:
  frontend/src/strategy_ide_v4/starterStrategies.ts

This test mirrors the draft data from that file and confirms the backend
accepts it. Any change to the starter registry must keep both files consistent.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.strategies_v4.models import (
    OnFillActionV4Draft,
    StrategyEntriesV4Draft,
    StrategyEntryV4Draft,
    StrategyLegV4Draft,
    StrategyLogicalExitV4Draft,
    StrategyLogicalExitsV4Draft,
    StrategyStopV4Draft,
    StrategyVersionV4Draft,
)
from backend.app.strategies_v4.persistence import StrategyV4Repository
from backend.app.strategies_v4.service import StrategyV4Service


@pytest.fixture()
def svc(tmp_path: Path) -> StrategyV4Service:
    repo = StrategyV4Repository(tmp_path / "starter_save_test.db")
    return StrategyV4Service(repo)


def _stop_pct(value: float) -> StrategyStopV4Draft:
    return StrategyStopV4Draft(id=uuid4(), mode="simple", scope="all", simple_type="%", simple_value=value)


def _stop_atr(value: float) -> StrategyStopV4Draft:
    return StrategyStopV4Draft(id=uuid4(), mode="simple", scope="all", simple_type="ATR", simple_value=value)


def _leg_target_pct(position: int, size_pct: float, target_value: float) -> StrategyLegV4Draft:
    return StrategyLegV4Draft(
        id=uuid4(),
        position=position,
        kind="target",
        size_pct=size_pct,
        target_type="%",
        target_value=target_value,
        on_fill_action=OnFillActionV4Draft(kind="be_exact"),
    )


def _leg_target_atr(position: int, size_pct: float, target_value: float) -> StrategyLegV4Draft:
    return StrategyLegV4Draft(
        id=uuid4(),
        position=position,
        kind="target",
        size_pct=size_pct,
        target_type="ATR",
        target_value=target_value,
        on_fill_action=OnFillActionV4Draft(kind="be_exact"),
    )


def _leg_target_r(position: int, size_pct: float, target_value: float) -> StrategyLegV4Draft:
    return StrategyLegV4Draft(
        id=uuid4(),
        position=position,
        kind="target",
        size_pct=size_pct,
        target_type="R",
        target_value=target_value,
        on_fill_action=OnFillActionV4Draft(kind="be_exact"),
    )


def _leg_runner_trail_atr(position: int, size_pct: float, target_value: float) -> StrategyLegV4Draft:
    return StrategyLegV4Draft(
        id=uuid4(),
        position=position,
        kind="runner",
        size_pct=size_pct,
        target_type="trail-ATR",
        target_value=target_value,
        on_fill_action=OnFillActionV4Draft(kind="be_exact"),
    )


def _leg_runner_trail_pct(position: int, size_pct: float, target_value: float) -> StrategyLegV4Draft:
    return StrategyLegV4Draft(
        id=uuid4(),
        position=position,
        kind="runner",
        size_pct=size_pct,
        target_type="trail-%",
        target_value=target_value,
        on_fill_action=OnFillActionV4Draft(kind="be_exact"),
    )


def _exit_opposite_cross() -> StrategyLogicalExitV4Draft:
    return StrategyLogicalExitV4Draft(id=uuid4(), template_id="opposite_cross", params={})


def _exit_session_end() -> StrategyLogicalExitV4Draft:
    return StrategyLogicalExitV4Draft(id=uuid4(), template_id="session_end", params={})


STARTER_DRAFTS: list[tuple[str, StrategyVersionV4Draft]] = [
    (
        "rsi-mean-reversion",
        StrategyVersionV4Draft(
            name="RSI Mean Reversion",
            description="Long when RSI(14) < 30 in an uptrend (close > SMA(50)).",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(expression_text="1d.rsi(14) < 30 AND 1d.close > 1d.sma(50)")
            ),
            stops=[_stop_pct(2.0)],
            legs=[_leg_target_pct(1, 1.0, 4.0)],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_opposite_cross()]),
        ),
    ),
    (
        "low-ibs-bounce",
        StrategyVersionV4Draft(
            name="Low IBS Bounce",
            description="Long when price closes near the day's low (IBS proxy < 0.2) and above SMA(200).",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(
                    expression_text="(1d.close - 1d.low) / 1d.range < 0.2 AND 1d.close > 1d.sma(200)"
                )
            ),
            stops=[_stop_pct(1.5)],
            legs=[_leg_target_pct(1, 1.0, 3.0)],
        ),
    ),
    (
        "ema-trend-pullback",
        StrategyVersionV4Draft(
            name="EMA Trend Pullback",
            description="Long when EMA(20) > EMA(50) and price crosses back above EMA(20).",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(
                    expression_text="1d.ema(20) > 1d.ema(50) AND 1d.close crosses_above 1d.ema(20)"
                )
            ),
            stops=[_stop_atr(1.5)],
            legs=[
                _leg_target_atr(1, 0.5, 3.0),
                _leg_runner_trail_atr(2, 0.5, 2.0),
            ],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_opposite_cross()]),
        ),
    ),
    (
        "supertrend-trend-follow",
        StrategyVersionV4Draft(
            name="Supertrend Trend Follow",
            description="Long on Supertrend up-cross; short on Supertrend down-cross.",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(expression_text="1h.close crosses_above 1h.supertrend(10, 3)"),
                short=StrategyEntryV4Draft(expression_text="1h.close crosses_below 1h.supertrend(10, 3)"),
            ),
            stops=[_stop_atr(1.0)],
            legs=[_leg_runner_trail_atr(1, 1.0, 1.0)],
            logical_exits=StrategyLogicalExitsV4Draft(
                long=[_exit_opposite_cross()],
                short=[_exit_opposite_cross()],
            ),
        ),
    ),
    (
        "donchian-breakout",
        StrategyVersionV4Draft(
            name="Donchian Breakout",
            description="Long when close > 20-bar Donchian channel high.",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(expression_text="1d.close > 1d.donchian_high(20)")
            ),
            stops=[_stop_pct(3.0)],
            legs=[_leg_runner_trail_pct(1, 1.0, 3.0)],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_opposite_cross()]),
        ),
    ),
    (
        "vwap-reclaim",
        StrategyVersionV4Draft(
            name="VWAP Reclaim",
            description="Long when price crosses above VWAP in the morning session.",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(
                    expression_text="5m.close crosses_above 5m.vwap() AND session.minutes_since_open < 90"
                )
            ),
            stops=[_stop_atr(1.0)],
            legs=[
                _leg_target_atr(1, 0.6, 2.0),
                _leg_runner_trail_atr(2, 0.4, 1.0),
            ],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_session_end()]),
        ),
    ),
    (
        "orb",
        StrategyVersionV4Draft(
            name="Opening Range Breakout",
            description="Long on break above first 30-min opening range high.",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(expression_text="5m.close > orb.high(30) AND session.is_open")
            ),
            stops=[_stop_pct(1.0)],
            legs=[
                _leg_target_r(1, 0.5, 2.0),
                _leg_runner_trail_pct(2, 0.5, 0.5),
            ],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_session_end()]),
        ),
    ),
    (
        "macd-cross",
        StrategyVersionV4Draft(
            name="MACD Cross Momentum",
            description="Long when MACD line crosses above signal and price is above EMA(50).",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(
                    expression_text="1h.macd_line(12, 26, 9) crosses_above 1h.macd_signal(12, 26, 9) AND 1h.close > 1h.ema(50)"
                )
            ),
            stops=[_stop_atr(2.0)],
            legs=[_leg_target_atr(1, 1.0, 3.0)],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_opposite_cross()]),
        ),
    ),
    (
        "bb-breakout",
        StrategyVersionV4Draft(
            name="Bollinger Band Breakout",
            description="Long when close > BB upper band with expanding band width.",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(
                    expression_text="1d.close > 1d.bb_upper(20, 2) AND 1d.bb_width(20, 2) > 0.02"
                )
            ),
            stops=[_stop_pct(2.0)],
            legs=[_leg_target_pct(1, 1.0, 5.0)],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_opposite_cross()]),
        ),
    ),
    (
        "prior-day-high-breakout",
        StrategyVersionV4Draft(
            name="Prior Day High Breakout",
            description="Long when 5m close > prior day high with elevated relative volume.",
            entries=StrategyEntriesV4Draft(
                long=StrategyEntryV4Draft(
                    expression_text="5m.close > prior_day.high AND 5m.rvol(20) > 1.5 AND session.minutes_since_open < 120"
                )
            ),
            stops=[_stop_atr(1.0)],
            legs=[
                _leg_target_atr(1, 0.5, 2.0),
                _leg_runner_trail_atr(2, 0.5, 1.0),
            ],
            logical_exits=StrategyLogicalExitsV4Draft(long=[_exit_session_end()]),
        ),
    ),
]


@pytest.mark.parametrize(
    "starter_id,draft",
    STARTER_DRAFTS,
    ids=[pair[0] for pair in STARTER_DRAFTS],
)
def test_starter_draft_saves_without_uuid_error(
    svc: StrategyV4Service,
    starter_id: str,
    draft: StrategyVersionV4Draft,
) -> None:
    """Each starter draft must save through the service with no UUID validation error."""
    version = svc.save(draft)
    assert version is not None
    assert version.version == 1
    assert version.name == draft.name
