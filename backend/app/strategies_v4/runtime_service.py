"""Composition root for StrategyV4Service."""
from __future__ import annotations

from backend.app.config.runtime_paths import get_runtime_db_path

from .persistence import StrategyV4Repository
from .service import StrategyV4Service


def create_strategy_v4_service_from_environment() -> StrategyV4Service:
    db_path = get_runtime_db_path()
    return StrategyV4Service(repository=StrategyV4Repository(db_path))
