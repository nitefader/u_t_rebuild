from __future__ import annotations

from datetime import datetime, time, timezone, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain import (
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    TradingMode,
    TradingModeBoundaryError,
    UniverseSnapshot,
    UniverseSymbol,
    validate_trading_mode_boundary,
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


def test_strategy_version_does_not_own_risk_or_account_sizing() -> None:
    forbidden_fields = {
        "account_id",
        "account_ids",
        "risk",
        "risk_settings",
        "risk_profile_id",
        "risk_profile_version_id",
        "account_risk",
        "position_size",
        "position_sizing",
        "sizing_method",
        "risk_per_trade_pct",
        "max_loss",
        "buying_power",
        "broker_account_id",
        "deployment_id",
        "runtime_overrides",
        "runtime_state",
    }

    assert forbidden_fields.isdisjoint(StrategyVersion.model_fields)


@pytest.mark.parametrize(
    "field_name",
    [
        "risk_profile_version_id",
        "risk_per_trade_pct",
        "position_sizing",
        "buying_power",
        "account_id",
        "watchlist_id",
        "watchlist_ids",
        "universe_id",
        "universe_snapshot_id",
        "symbols",
        "deployment_id",
        "runtime_overrides",
    ],
)
def test_strategy_version_rejects_risk_universe_account_and_runtime_ownership_fields(
    field_name: str,
) -> None:
    condition = ConditionNode(
        left_feature="5m.close[0]",
        operator=ConditionOperator.GT,
        right_feature="5m.ema:length=20[0]",
    )
    payload: dict[str, object] = {
        "id": uuid4(),
        "strategy_id": uuid4(),
        "version": 1,
        "name": "EMA Breakout",
        "feature_refs": ["5m.close[0]", "5m.ema:length=20[0]"],
        "entry_rules": [
            SignalRule(
                name="long_breakout",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=condition,
            )
        ],
        field_name: uuid4(),
    }

    with pytest.raises(ValidationError, match="strategy version cannot own"):
        StrategyVersion(**payload)


def test_deployment_owns_watchlists_and_account_subscriptions_not_strategy_version() -> None:
    strategy_fields = set(StrategyVersion.model_fields)

    assert "watchlist_ids" not in strategy_fields
    assert "subscribed_account_ids" not in strategy_fields


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


def test_chart_lab_modes_cannot_access_broker_adapter() -> None:
    with pytest.raises(TradingModeBoundaryError, match="cannot access BrokerAdapter"):
        validate_trading_mode_boundary(
            TradingMode.CHART_LAB_BATCH,
            broker_adapter=object(),
        )


def test_chart_lab_modes_cannot_create_orders_or_mutate_ledgers() -> None:
    for forbidden in (
        {"creates_orders": True},
        {"mutates_order_ledger": True},
        {"mutates_trade_ledger": True},
    ):
        with pytest.raises(TradingModeBoundaryError):
            validate_trading_mode_boundary(TradingMode.CHART_LAB_LIVE_PREVIEW, **forbidden)


def test_sim_lab_modes_cannot_access_broker_adapter_or_real_broker_data() -> None:
    with pytest.raises(TradingModeBoundaryError, match="cannot access BrokerAdapter"):
        validate_trading_mode_boundary(
            TradingMode.SIM_LAB_HISTORICAL,
            broker_adapter=object(),
        )
    with pytest.raises(TradingModeBoundaryError, match="cannot use real broker data"):
        validate_trading_mode_boundary(
            TradingMode.SIM_LAB_LIVE_SIMULATION,
            uses_real_broker_data=True,
        )


def test_broker_modes_require_adapter_and_sync() -> None:
    with pytest.raises(TradingModeBoundaryError, match="requires BrokerAdapter"):
        validate_trading_mode_boundary(TradingMode.BROKER_PAPER)
    with pytest.raises(TradingModeBoundaryError, match="requires BrokerSync"):
        validate_trading_mode_boundary(TradingMode.BROKER_LIVE, broker_adapter=object())
    validate_trading_mode_boundary(TradingMode.BROKER_PAPER, broker_adapter=object(), broker_sync=object())


def test_no_ambiguous_mode_string_literals_remain_in_backend_app() -> None:
    app_dir = Path(__file__).parents[3] / "app"
    ambiguous_patterns = [
        'mode="paper"',
        "mode='paper'",
        'mode: "paper"',
        "mode: 'paper'",
        'mode="live"',
        "mode='live'",
        'mode: "live"',
        "mode: 'live'",
        'mode="simulation"',
        "mode='simulation'",
        'mode: "simulation"',
        "mode: 'simulation'",
        'mode="chart"',
        "mode='chart'",
        'mode: "chart"',
        "mode: 'chart'",
        "HISTORICAL_REPLAY",
        "STRATEGY_PREVIEW",
        "PROGRAM_PREVIEW",
        "BrokerAccountMode",
    ]
    offenders: list[str] = []

    for path in app_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in ambiguous_patterns:
            if pattern in text:
                offenders.append(f"{path.relative_to(app_dir)}:{pattern}")

    assert offenders == []
