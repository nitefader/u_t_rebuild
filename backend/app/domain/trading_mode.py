from __future__ import annotations

from enum import StrEnum


class TradingMode(StrEnum):
    CHART_LAB_BATCH = "CHART_LAB_BATCH"
    CHART_LAB_LIVE_PREVIEW = "CHART_LAB_LIVE_PREVIEW"
    SIM_LAB_HISTORICAL = "SIM_LAB_HISTORICAL"
    SIM_LAB_LIVE_SIMULATION = "SIM_LAB_LIVE_SIMULATION"
    BROKER_PAPER = "BROKER_PAPER"
    BROKER_LIVE = "BROKER_LIVE"


class TradingModeBoundaryError(ValueError):
    """Raised when a trading mode is paired with forbidden runtime resources."""


CHART_LAB_MODES = frozenset(
    {
        TradingMode.CHART_LAB_BATCH,
        TradingMode.CHART_LAB_LIVE_PREVIEW,
    }
)
SIM_LAB_MODES = frozenset(
    {
        TradingMode.SIM_LAB_HISTORICAL,
        TradingMode.SIM_LAB_LIVE_SIMULATION,
    }
)
BROKER_MODES = frozenset(
    {
        TradingMode.BROKER_PAPER,
        TradingMode.BROKER_LIVE,
    }
)


def validate_trading_mode_boundary(
    mode: TradingMode,
    *,
    broker_adapter: object | None = None,
    broker_sync: object | None = None,
    creates_orders: bool = False,
    mutates_order_ledger: bool = False,
    mutates_trade_ledger: bool = False,
    uses_real_broker_data: bool = False,
) -> None:
    if mode in CHART_LAB_MODES:
        _reject(
            mode,
            broker_adapter=broker_adapter,
            creates_orders=creates_orders,
            mutates_order_ledger=mutates_order_ledger,
            mutates_trade_ledger=mutates_trade_ledger,
        )
        return
    if mode in SIM_LAB_MODES:
        _reject(mode, broker_adapter=broker_adapter, uses_real_broker_data=uses_real_broker_data)
        return
    if mode in BROKER_MODES:
        if broker_adapter is None:
            raise TradingModeBoundaryError(f"{mode.value} requires BrokerAdapter")
        if broker_sync is None:
            raise TradingModeBoundaryError(f"{mode.value} requires BrokerSync")
        return
    raise TradingModeBoundaryError(f"unsupported trading mode: {mode}")


def _reject(
    mode: TradingMode,
    *,
    broker_adapter: object | None = None,
    creates_orders: bool = False,
    mutates_order_ledger: bool = False,
    mutates_trade_ledger: bool = False,
    uses_real_broker_data: bool = False,
) -> None:
    if broker_adapter is not None:
        raise TradingModeBoundaryError(f"{mode.value} cannot access BrokerAdapter")
    if creates_orders:
        raise TradingModeBoundaryError(f"{mode.value} cannot create orders")
    if mutates_order_ledger:
        raise TradingModeBoundaryError(f"{mode.value} cannot mutate OrderLedger")
    if mutates_trade_ledger:
        raise TradingModeBoundaryError(f"{mode.value} cannot mutate TradeLedger")
    if uses_real_broker_data:
        raise TradingModeBoundaryError(f"{mode.value} cannot use real broker data")
