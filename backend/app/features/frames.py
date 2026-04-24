from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FeatureAvailability(StrEnum):
    AVAILABLE = "available"
    WARMUP = "warmup"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


class NormalizedBar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class FeatureValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: float | None
    availability: FeatureAvailability


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    timestamp: datetime
    values: dict[str, FeatureValue] = Field(default_factory=dict)

    def value_for(self, feature_key: str) -> float | None:
        return self.values[feature_key].value

    def availability_for(self, feature_key: str) -> FeatureAvailability:
        return self.values[feature_key].availability


class FeatureFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    snapshots: tuple[FeatureSnapshot, ...]


class FeatureFrameSet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    frames: tuple[FeatureFrame, ...]

    def frame_for(self, symbol: str, timeframe: str) -> FeatureFrame:
        normalized_symbol = symbol.upper()
        for frame in self.frames:
            if frame.symbol == normalized_symbol and frame.timeframe == timeframe:
                return frame
        raise KeyError(f"no feature frame for {normalized_symbol}/{timeframe}")
