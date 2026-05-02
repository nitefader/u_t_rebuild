from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import JsonDict
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.simulation import HistoricalReplayEngine
from backend.app.simulation.models import SimulatedEventType, SimulationEvent, SimulationReplayResult

SimLabStreamType = Literal[
    "session_started",
    "bar",
    "signal_plan",
    "virtual_fill",
    "position",
    "equity",
    "event",
    "session_completed",
]


@dataclass(frozen=True)
class SimLabBatchRunRequest:
    strategy_id: UUID
    strategy_version_id: UUID
    scenario_name: str
    start: datetime
    end: datetime
    universe: tuple[str, ...]
    timeframe: str = "5m"
    initial_cash: float = 100_000
    bar_count: int = 12


class SimLabStreamMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: SimLabStreamType
    sequence: int = Field(ge=0)
    run_id: UUID
    timestamp: datetime
    payload: JsonDict


@dataclass(frozen=True)
class _SimLabExecution:
    bars: tuple[NormalizedBar, ...]
    result: SimulationReplayResult


class SimLabBatchRunService:
    """Execute a deterministic Sim Lab batch replay over a fixed window.

    The service delegates signal generation and simulated fills to the existing
    historical replay engine. It does not call broker providers and does not
    write broker truth.
    """

    def __init__(self, *, replay_engine: HistoricalReplayEngine | None = None) -> None:
        self._replay_engine = replay_engine or HistoricalReplayEngine()

    def create_run(
        self,
        request: SimLabBatchRunRequest,
        *,
        components: ResolvedDeploymentComponents,
        run_id: UUID | None = None,
    ) -> SimulationReplayResult:
        return self._execute(request, components=components, run_id=run_id).result

    def stream_messages(
        self,
        request: SimLabBatchRunRequest,
        *,
        components: ResolvedDeploymentComponents,
        run_id: UUID | None = None,
    ) -> tuple[SimLabStreamMessage, ...]:
        messages, _ = self.stream_result(request, components=components, run_id=run_id)
        return messages

    def stream_result(
        self,
        request: SimLabBatchRunRequest,
        *,
        components: ResolvedDeploymentComponents,
        run_id: UUID | None = None,
    ) -> tuple[tuple[SimLabStreamMessage, ...], SimulationReplayResult]:
        execution = self._execute(request, components=components, run_id=run_id)
        result = execution.result
        if result.evidence is None:  # pragma: no cover - HistoricalReplayEngine records evidence for every run.
            raise ValueError("sim lab stream run did not produce evidence")

        run_id = result.evidence.run_id
        messages: list[SimLabStreamMessage] = [
            SimLabStreamMessage(
                type="session_started",
                sequence=0,
                run_id=run_id,
                timestamp=result.session.start,
                payload={
                    "scenario_name": request.scenario_name,
                    "strategy_id": request.strategy_id,
                    "strategy_version_id": request.strategy_version_id,
                    "universe": list(request.universe),
                    "timeframe": request.timeframe,
                    "initial_cash": request.initial_cash,
                },
            )
        ]

        fills_by_id = {fill.id: fill for fill in result.fills}
        positions_by_symbol = {position.symbol: position for position in result.positions}
        artifacts: list[tuple[datetime, int, int, NormalizedBar | SimulationEvent]] = []
        artifacts.extend(
            (bar.timestamp, 0, index, bar)
            for index, bar in enumerate(sorted(execution.bars, key=lambda item: (item.timestamp, item.symbol)))
        )
        artifacts.extend((event.timestamp, 1, event.sequence, event) for event in result.events)

        sequence = 1
        for _, _, _, artifact in sorted(artifacts, key=lambda item: (item[0], item[1], item[2])):
            if isinstance(artifact, NormalizedBar):
                messages.append(
                    SimLabStreamMessage(
                        type="bar",
                        sequence=sequence,
                        run_id=run_id,
                        timestamp=artifact.timestamp,
                        payload=artifact.model_dump(mode="json"),
                    )
                )
            else:
                messages.append(
                    self._event_message(
                        event=artifact,
                        sequence=sequence,
                        run_id=run_id,
                        request=request,
                        fills_by_id=fills_by_id,
                        positions_by_symbol=positions_by_symbol,
                    )
                )
            sequence += 1

        messages.append(
            SimLabStreamMessage(
                type="session_completed",
                sequence=sequence,
                run_id=run_id,
                timestamp=result.session.end,
                payload={
                    "realized_pnl": result.realized_pnl,
                    "max_drawdown": result.max_drawdown,
                    "gross_exposure": result.gross_exposure,
                    "signal_plan_count": result.evidence.signal_plan_count,
                    "simulated_order_count": result.evidence.simulated_order_count,
                    "simulated_fill_count": result.evidence.simulated_fill_count,
                },
            )
        )
        return tuple(messages), result

    def _execute(
        self,
        request: SimLabBatchRunRequest,
        *,
        components: ResolvedDeploymentComponents,
        run_id: UUID | None = None,
    ) -> _SimLabExecution:
        if request.start >= request.end:
            raise ValueError("sim lab run start must be before end")
        if request.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        symbols = tuple(symbol.strip().upper() for symbol in request.universe if symbol.strip())
        if not symbols:
            raise ValueError("universe must contain at least one symbol")
        if request.bar_count < 2:
            raise ValueError("bar_count must be at least 2")

        component_symbols = tuple(symbol.symbol.upper() for symbol in components.universe.symbols)
        if symbols != component_symbols:
            raise ValueError("sim lab universe must match resolved component symbols")
        if components.strategy is None:
            raise ValueError("sim lab requires a resolved StrategyVersion")
        bars = self._bars(request=request, symbols=symbols)
        result = self._replay_engine.run(
            components=components,
            bars=bars,
            start=request.start,
            end=request.end,
            initial_cash=request.initial_cash,
            session_id=run_id or uuid4(),
            run_id=run_id,
            scenario_name=request.scenario_name,
        )
        return _SimLabExecution(bars=bars, result=result)

    def _event_message(
        self,
        *,
        event: SimulationEvent,
        sequence: int,
        run_id: UUID,
        request: SimLabBatchRunRequest,
        fills_by_id: dict[str, Any],
        positions_by_symbol: dict[str, Any],
    ) -> SimLabStreamMessage:
        payload: JsonDict = {
            "event_type": event.event_type.value,
            "symbol": event.symbol,
            "message": event.message,
            "details": dict(event.details),
        }
        message_type: SimLabStreamType = "event"
        if event.event_type == SimulatedEventType.SIGNAL_CANDIDATE:
            message_type = "signal_plan"
            payload["signal_plan"] = self._signal_plan_payload(event=event, run_id=run_id, request=request)
        elif event.event_type in {SimulatedEventType.ORDER_FILLED, SimulatedEventType.ORDER_PARTIALLY_FILLED}:
            message_type = "virtual_fill"
            fill = fills_by_id.get(str(event.details.get("fill_id")))
            if fill is not None:
                fill_payload = fill.model_dump(mode="json")
                payload.update(
                    {
                        "fill": fill_payload,
                        "fill_id": fill.id,
                        "order_id": fill.order_id,
                        "symbol": fill.symbol,
                        "side": fill.side.value,
                        "qty": fill.qty,
                        "price": fill.price,
                    }
                )
        elif event.event_type in {
            SimulatedEventType.POSITION_OPENED,
            SimulatedEventType.POSITION_UPDATED,
            SimulatedEventType.POSITION_CLOSED,
        }:
            message_type = "position"
            position = positions_by_symbol.get((event.symbol or "").upper())
            if position is not None:
                position_payload = position.model_dump(mode="json")
                payload.update(
                    {
                        "position": position_payload,
                        "symbol": position.symbol,
                        "qty": event.details.get("qty", position.qty),
                        "avg_price": event.details.get("avg_price", position.avg_price),
                        "realized_pnl": position.realized_pnl,
                        "unrealized_pnl": 0,
                        "open_stop": position.open_stop,
                        "open_target": position.open_target,
                    }
                )
        elif event.event_type == SimulatedEventType.PNL_UPDATED:
            message_type = "equity"
            payload.update(event.details)
        return SimLabStreamMessage(
            type=message_type,
            sequence=sequence,
            run_id=run_id,
            timestamp=event.timestamp,
            payload=payload,
        )

    def _signal_plan_payload(self, *, event: SimulationEvent, run_id: UUID, request: SimLabBatchRunRequest) -> JsonDict:
        details = event.details
        return {
            "signal_plan_id": uuid5(NAMESPACE_URL, f"sim-lab:{run_id}:{event.sequence}"),
            "simulation_only": True,
            "status": "created",
            "strategy_id": request.strategy_id,
            "strategy_version_id": request.strategy_version_id,
            "symbol": event.symbol,
            "side": details.get("side"),
            "intent": "open" if details.get("intent_type") == "entry" else details.get("intent_type"),
            "reason": details.get("signal_name"),
            "lineage": {
                "strategy_id": request.strategy_id,
                "strategy_version_id": request.strategy_version_id,
                "scenario_name": request.scenario_name,
                "source_event_sequence": event.sequence,
            },
        }

    def _bars(self, *, request: SimLabBatchRunRequest, symbols: tuple[str, ...]) -> tuple[NormalizedBar, ...]:
        total_seconds = max((request.end - request.start).total_seconds(), 1)
        step_seconds = max(int(total_seconds // max(request.bar_count - 1, 1)), 1)
        bars: list[NormalizedBar] = []
        for symbol_index, symbol in enumerate(symbols):
            base = 100 + (symbol_index * 10)
            for index in range(request.bar_count):
                timestamp = request.start + timedelta(seconds=step_seconds * index)
                open_price = base + index
                close = open_price + (1 if index % 2 == 0 else -0.25)
                high = max(open_price, close) + 2
                low = min(open_price, close) - 1
                bars.append(
                    NormalizedBar(
                        symbol=symbol,
                        timeframe=request.timeframe,
                        timestamp=min(timestamp, request.end),
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=100_000 + index,
                    )
                )
        return tuple(bars)
