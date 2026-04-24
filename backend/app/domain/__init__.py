"""Canonical Trading OS domain schemas.

These are Pydantic contracts only. They are not database models and they do not
own API, broker, or persistence behavior.
"""

from .chart_lab import ChartLabSession
from .execution_style import ExecutionStyleVersion, OrderType, TimeInForce
from .program import ProgramStatus, ProgramVersion, ValidationStatus
from .risk_profile import RiskProfileVersion
from .simulation import GovernorMode, SimulationSession
from .strategy import (
    CandidateSide,
    CandidateTradeIntent,
    ConditionGroup,
    ConditionNode,
    ConditionOperator,
    IntentType,
    SignalRule,
    StrategyVersion,
)
from .strategy_controls import StrategyControlsVersion
from .trading_mode import (
    BROKER_MODES,
    CHART_LAB_MODES,
    SIM_LAB_MODES,
    TradingMode,
    TradingModeBoundaryError,
    validate_trading_mode_boundary,
)
from .universe import UniverseSnapshot, UniverseSymbol
from .validation import EvidenceKind, ValidationEvidence

__all__ = [
    "CandidateSide",
    "CandidateTradeIntent",
    "ChartLabSession",
    "ConditionGroup",
    "ConditionNode",
    "ConditionOperator",
    "EvidenceKind",
    "ExecutionStyleVersion",
    "GovernorMode",
    "IntentType",
    "OrderType",
    "ProgramStatus",
    "ProgramVersion",
    "RiskProfileVersion",
    "SignalRule",
    "SimulationSession",
    "BROKER_MODES",
    "CHART_LAB_MODES",
    "SIM_LAB_MODES",
    "StrategyControlsVersion",
    "StrategyVersion",
    "TimeInForce",
    "TradingMode",
    "TradingModeBoundaryError",
    "UniverseSnapshot",
    "UniverseSymbol",
    "ValidationEvidence",
    "ValidationStatus",
    "validate_trading_mode_boundary",
]
