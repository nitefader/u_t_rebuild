from __future__ import annotations

from datetime import datetime, time, timezone, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain import (
    ChartLabMode,
    ChartLabSession,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    GovernorMode,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    SimulationMode,
    SimulationSession,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.program import ProgramStatus
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import CandidateSide, IntentType, SignalRule
from backend.app.domain.strategy_controls import SessionName, SessionWindow


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _program_payload() -> dict[str, object]:
    return {
        "id": uuid4(),
        "program_id": uuid4(),
        "name": "ORB Program",
        "version": 1,
        "strategy_version_id": uuid4(),
        "strategy_controls_version_id": uuid4(),
        "risk_profile_version_id": uuid4(),
        "execution_style_version_id": uuid4(),
        "universe_snapshot_id": uuid4(),
    }


def test_program_version_contains_component_references_only() -> None:
    program = ProgramVersion(**_program_payload())

    assert program.strategy_version_id
    assert program.strategy_controls_version_id
    assert program.risk_profile_version_id
    assert program.execution_style_version_id
    assert program.universe_snapshot_id
    assert not hasattr(program, "execution_policy")
    assert not hasattr(program, "broker_account_id")
    assert not hasattr(program, "runtime_state")


@pytest.mark.parametrize(
    "field_name",
    [
        "conditions",
        "feature_refs",
        "indicators",
        "risk",
        "risk_settings",
        "execution_policy",
        "session_windows",
        "symbols",
        "broker_account_id",
        "deployment_status",
        "runtime_state",
        "live_universe_cache",
    ],
)
def test_program_version_rejects_inline_behavior_fields(field_name: str) -> None:
    payload = _program_payload()
    payload[field_name] = {}

    with pytest.raises(ValidationError):
        ProgramVersion(**payload)


def test_frozen_program_requires_frozen_timestamp() -> None:
    payload = _program_payload()
    payload["status"] = ProgramStatus.FROZEN

    with pytest.raises(ValidationError):
        ProgramVersion(**payload)


def test_strategy_version_contains_signal_definition_and_feature_refs_only() -> None:
    condition = ConditionNode(
        left_feature="5m.close[0]",
        operator=ConditionOperator.GT,
        right_feature="5m.ema:length=20[0]",
    )
    strategy = StrategyVersion(
        id=uuid4(),
        strategy_id=uuid4(),
        version=1,
        name="EMA Breakout",
        feature_refs=["5m.close[0]", "5m.ema:length=20[0]"],
        entry_rules=[
            SignalRule(
                name="long_breakout",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=condition,
            )
        ],
    )

    assert strategy.feature_refs == ["5m.close[0]", "5m.ema:length=20[0]"]
    assert strategy.entry_rules[0].condition == condition
    assert not hasattr(strategy, "position_size")
    assert not hasattr(strategy, "order_type")
    assert not hasattr(strategy, "broker_account_id")


def test_component_schemas_are_separate() -> None:
    controls = StrategyControlsVersion(
        id=uuid4(),
        strategy_controls_id=uuid4(),
        version=1,
        name="Regular Hours",
        timeframe="5m",
        session_windows=[
            SessionWindow(
                session=SessionName.REGULAR,
                start=time(hour=9, minute=30),
                end=time(hour=15, minute=55),
            )
        ],
    )
    risk = RiskProfileVersion(
        id=uuid4(),
        risk_profile_id=uuid4(),
        version=1,
        name="Half Percent Risk",
        sizing_method=PositionSizingMethod.RISK_PERCENT_EQUITY,
        risk_per_trade_pct=0.5,
    )
    execution = ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="Market Day",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=uuid4(),
        universe_id=uuid4(),
        version=1,
        name="Liquid Large Caps",
        symbols=[UniverseSymbol(symbol="SPY")],
    )

    assert controls.timeframe == "5m"
    assert risk.risk_per_trade_pct == 0.5
    assert execution.entry_order_type == OrderType.MARKET
    assert universe.symbols[0].symbol == "SPY"


@pytest.mark.parametrize(
    "field_name",
    [
        "orders",
        "fills",
        "positions",
        "pnl",
        "equity",
        "drawdown",
        "cash",
        "broker_account_id",
        "deployment_id",
    ],
)
def test_chart_lab_session_rejects_execution_state(field_name: str) -> None:
    now = _now()
    payload: dict[str, object] = {
        "id": uuid4(),
        "mode": ChartLabMode.STRATEGY_PREVIEW,
        "symbol": "SPY",
        "timeframe": "5m",
        "start": now,
        "end": now + timedelta(days=1),
        "strategy_version_id": uuid4(),
        field_name: [],
    }

    with pytest.raises(ValidationError):
        ChartLabSession(**payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "broker_account_id",
        "alpaca_order_id",
        "client_order_id",
        "real_order_id",
        "deployment_id",
    ],
)
def test_simulation_session_rejects_real_broker_submission_fields(field_name: str) -> None:
    now = _now()
    payload: dict[str, object] = {
        "id": uuid4(),
        "mode": SimulationMode.HISTORICAL_REPLAY,
        "program_version_id": uuid4(),
        "symbol_count": 3,
        "start": now,
        "end": now + timedelta(days=1),
        "initial_cash": 100000,
        "governor_mode": GovernorMode.OFF,
        field_name: "forbidden",
    }

    with pytest.raises(ValidationError):
        SimulationSession(**payload)


def test_banned_names_do_not_appear_in_domain_files() -> None:
    domain_dir = Path(__file__).parents[3] / "app" / "domain"
    banned = ["StrategyGovernor", "AccountGovernor", "AccountAllocation"]
    offenders: list[str] = []

    for path in domain_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned_name in banned:
            if banned_name in text:
                offenders.append(f"{path.name}:{banned_name}")

    assert offenders == []
