from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataConsumer(StrEnum):
    CHART_LAB = "chart_lab"
    SIM_LAB = "sim_lab"
    BACKTEST = "backtest"
    BROKER_RUNTIME = "broker_runtime"
    OPERATIONS_PREVIEW = "operations_preview"


class DataIntentMode(StrEnum):
    BATCH = "batch"
    REPLAY = "replay"
    LIVE_PREVIEW = "live_preview"
    LIVE_RUNTIME = "live_runtime"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"
    MO1 = "1mo"


class DataTolerance(StrEnum):
    LOW_LATENCY = "low_latency"
    NORMAL = "normal"
    FAULT_TOLERANT = "fault_tolerant"


class DataPurpose(StrEnum):
    WARMUP = "warmup"
    SIGNAL_PREVIEW = "signal_preview"
    SIMULATION_REPLAY = "simulation_replay"
    BACKTEST = "backtest"
    RUNTIME_TRADING = "runtime_trading"
    LONG_HORIZON_ANALYSIS = "long_horizon_analysis"


INTRADAY_TIMEFRAMES = {
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.M30,
    Timeframe.H1,
    Timeframe.H4,
}

LONG_RANGE_TIMEFRAMES = {Timeframe.D1, Timeframe.W1, Timeframe.MO1}


class DataIntent(BaseModel):
    """Machine-readable market data need for service resolution.

    The intent describes data requirements only. It does not carry broker
    account identity and does not authorize broker execution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    consumer: DataConsumer
    mode: DataIntentMode
    symbols: list[str] = Field(default_factory=list)
    timeframe: Timeframe
    start_at: datetime | None = None
    end_at: datetime | None = None
    requires_streaming: bool = False
    requires_intraday: bool = False
    requires_historical: bool = False
    requires_realtime: bool = False
    tolerance: DataTolerance = DataTolerance.NORMAL
    purpose: DataPurpose

    @model_validator(mode="before")
    @classmethod
    def apply_context_rules(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        values = dict(data)
        consumer = _enum_value(DataConsumer, values.get("consumer"))
        mode = _enum_value(DataIntentMode, values.get("mode"))
        timeframe = _enum_value(Timeframe, values.get("timeframe"))
        purpose = _enum_value(DataPurpose, values.get("purpose"))

        is_intraday = timeframe in {item.value for item in INTRADAY_TIMEFRAMES}
        is_live = mode in {DataIntentMode.LIVE_PREVIEW.value, DataIntentMode.LIVE_RUNTIME.value}
        is_historical = bool(values.get("start_at") or values.get("end_at")) or mode == DataIntentMode.REPLAY.value
        is_historical = is_historical or purpose in {
            DataPurpose.WARMUP.value,
            DataPurpose.SIMULATION_REPLAY.value,
            DataPurpose.BACKTEST.value,
            DataPurpose.LONG_HORIZON_ANALYSIS.value,
        }

        if "requires_intraday" not in values:
            values["requires_intraday"] = is_intraday
        if "requires_historical" not in values:
            values["requires_historical"] = is_historical
        if "requires_realtime" not in values:
            values["requires_realtime"] = is_live
        if "requires_streaming" not in values:
            values["requires_streaming"] = is_live

        if consumer == DataConsumer.BROKER_RUNTIME.value:
            values["requires_streaming"] = True
            values["requires_realtime"] = True
            values["requires_intraday"] = bool(values.get("requires_intraday") or is_intraday)
            values["purpose"] = purpose or DataPurpose.RUNTIME_TRADING.value
            if "tolerance" not in values:
                values["tolerance"] = DataTolerance.LOW_LATENCY.value

        if consumer == DataConsumer.BACKTEST.value and timeframe in {item.value for item in LONG_RANGE_TIMEFRAMES}:
            values["requires_streaming"] = False
            values["requires_realtime"] = False
            values["requires_historical"] = True

        if consumer == DataConsumer.CHART_LAB.value and mode == DataIntentMode.BATCH.value:
            values["requires_streaming"] = False

        if consumer == DataConsumer.SIM_LAB.value and mode == DataIntentMode.REPLAY.value:
            values["requires_streaming"] = False
            values["requires_historical"] = True

        if consumer == DataConsumer.SIM_LAB.value and is_live:
            values["requires_realtime"] = True
            values["requires_streaming"] = True

        return values

    @property
    def is_long_range_historical(self) -> bool:
        if self.timeframe not in LONG_RANGE_TIMEFRAMES or not self.requires_historical:
            return False
        if self.purpose == DataPurpose.LONG_HORIZON_ANALYSIS:
            return True
        if self.start_at is None or self.end_at is None:
            return self.consumer == DataConsumer.BACKTEST
        return (self.end_at - self.start_at).days >= 365


def _enum_value(enum_type: type[StrEnum], value: object) -> str:
    if isinstance(value, enum_type):
        return value.value
    return str(value) if value is not None else ""
