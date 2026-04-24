from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SimulationEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    event_type: str
    symbol: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class SimulationEventLog:
    def __init__(self) -> None:
        self._events: list[SimulationEvent] = []

    def emit(self, timestamp: datetime, event_type: str, *, symbol: str | None = None, **detail: Any) -> None:
        self._events.append(SimulationEvent(timestamp=timestamp, event_type=event_type, symbol=symbol, detail=detail))

    @property
    def events(self) -> tuple[SimulationEvent, ...]:
        return tuple(self._events)
