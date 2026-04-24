from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import (
    CandidateSide,
    IntentType,
    SimulationSession,
    TradingMode,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.features import (
    BatchFeatureEngine,
    FeatureAvailability,
    FeatureFrame,
    FeatureFrameSet,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    NormalizedBar,
    ResolvedProgramComponents,
    build_feature_plan,
)

from .models import (
    EquityPoint,
    SimulatedEventType,
    SimulatedFill,
    SimulatedOrder,
    SimulatedOrderIntent,
    SimulatedOrderSide,
    SimulatedOrderStatus,
    SimulatedOrderType,
    SimulatedPosition,
    SimulatedTrade,
    SimulationError,
    SimulationEvent,
    SimulationReplayResult,
)


class SimulationEventLog:
    def __init__(self) -> None:
        self._events: list[SimulationEvent] = []

    def append(
        self,
        *,
        timestamp: datetime,
        event_type: SimulatedEventType,
        message: str,
        symbol: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._events.append(
            SimulationEvent(
                sequence=len(self._events) + 1,
                timestamp=timestamp,
                event_type=event_type,
                symbol=symbol,
                message=message,
                details=details or {},
            )
        )

    def snapshot(self) -> tuple[SimulationEvent, ...]:
        return tuple(self._events)


class SimulatedPositionLedger:
    def __init__(self) -> None:
        self._positions: dict[str, SimulatedPosition] = {}
        self._entry_order_by_symbol: dict[str, str] = {}
        self._entry_time_by_symbol: dict[str, datetime] = {}

    def position_for(self, symbol: str) -> SimulatedPosition:
        normalized_symbol = symbol.upper()
        return self._positions.get(normalized_symbol, SimulatedPosition(symbol=normalized_symbol))

    def apply_open_fill(
        self,
        fill: SimulatedFill,
        *,
        stop: float | None,
        target: float | None,
        entry_order_id: str,
        trailing_enabled: bool,
    ) -> SimulatedPosition:
        position = self.position_for(fill.symbol)
        total_qty = position.qty + fill.qty
        avg_price = ((position.avg_price * position.qty) + (fill.price * fill.qty)) / total_qty
        trailing_distance = position.trailing_distance
        if trailing_enabled and stop is not None:
            trailing_distance = max(fill.price - stop, 0.01)
        updated = position.model_copy(
            update={
                "qty": total_qty,
                "avg_price": avg_price,
                "open_stop": stop if stop is not None else position.open_stop,
                "open_target": target if target is not None else position.open_target,
                "trailing_distance": trailing_distance,
            }
        )
        self._positions[fill.symbol] = updated
        self._entry_order_by_symbol.setdefault(fill.symbol, entry_order_id)
        self._entry_time_by_symbol.setdefault(fill.symbol, fill.timestamp)
        return updated

    def apply_close_fill(self, fill: SimulatedFill) -> tuple[SimulatedPosition, float, float, str, datetime]:
        position = self.position_for(fill.symbol)
        if position.qty <= 0:
            raise SimulationError(f"cannot close empty position for {fill.symbol}")
        close_qty = min(fill.qty, position.qty)
        realized = (fill.price - position.avg_price) * close_qty
        remaining_qty = position.qty - close_qty
        entry_order_id = self._entry_order_by_symbol.get(fill.symbol, "")
        opened_at = self._entry_time_by_symbol.get(fill.symbol, fill.timestamp)
        if remaining_qty == 0:
            updated = SimulatedPosition(symbol=fill.symbol, realized_pnl=position.realized_pnl + realized)
            self._entry_order_by_symbol.pop(fill.symbol, None)
            self._entry_time_by_symbol.pop(fill.symbol, None)
        else:
            updated = position.model_copy(update={"qty": remaining_qty, "realized_pnl": position.realized_pnl + realized})
        self._positions[fill.symbol] = updated
        return updated, realized, position.avg_price, entry_order_id, opened_at

    def update_trailing_stop(self, symbol: str, new_stop: float) -> SimulatedPosition:
        position = self.position_for(symbol)
        updated = position.model_copy(update={"open_stop": new_stop})
        self._positions[symbol.upper()] = updated
        return updated

    def open_positions(self) -> tuple[SimulatedPosition, ...]:
        return tuple(position for position in self._positions.values() if position.qty > 0)

    def all_positions(self) -> tuple[SimulatedPosition, ...]:
        return tuple(self._positions.values())


class SimulatedTradeLedger:
    def __init__(self) -> None:
        self._trades: list[SimulatedTrade] = []

    def record(
        self,
        *,
        symbol: str,
        qty: float,
        entry_price: float,
        exit_price: float,
        entry_order_id: str,
        exit_order_id: str,
        opened_at: datetime,
        closed_at: datetime,
        realized_pnl: float,
        exit_reason: SimulatedOrderIntent,
    ) -> None:
        self._trades.append(
            SimulatedTrade(
                id=f"SIM-TRD-{len(self._trades) + 1:06d}",
                symbol=symbol,
                side="long",
                qty=qty,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_order_id=entry_order_id,
                exit_order_id=exit_order_id,
                opened_at=opened_at,
                closed_at=closed_at,
                realized_pnl=realized_pnl,
                exit_reason=exit_reason,
            )
        )

    def snapshot(self) -> tuple[SimulatedTrade, ...]:
        return tuple(self._trades)


class SimulatedOrderManager:
    def __init__(self, *, partial_fill_ratio: float = 1.0) -> None:
        if not 0 < partial_fill_ratio <= 1:
            raise SimulationError("partial_fill_ratio must be > 0 and <= 1")
        self._partial_fill_ratio = partial_fill_ratio
        self._orders: list[SimulatedOrder] = []
        self._fills: list[SimulatedFill] = []

    def create_order(
        self,
        *,
        symbol: str,
        intent: SimulatedOrderIntent,
        side: SimulatedOrderSide,
        order_type: SimulatedOrderType,
        qty: float,
        timestamp: datetime,
        limit_price: float | None = None,
        stop_price: float | None = None,
        parent_order_id: str | None = None,
        signal_name: str | None = None,
    ) -> SimulatedOrder:
        order = SimulatedOrder(
            id=f"SIM-ORD-{len(self._orders) + 1:06d}",
            symbol=symbol.upper(),
            intent=intent,
            side=side,
            order_type=order_type,
            qty=qty,
            status=SimulatedOrderStatus.OPEN,
            limit_price=limit_price,
            stop_price=stop_price,
            parent_order_id=parent_order_id,
            created_at=timestamp,
            updated_at=timestamp,
            signal_name=signal_name,
        )
        self._orders.append(order)
        return order

    def fill_order(self, order: SimulatedOrder, *, price: float, timestamp: datetime) -> tuple[SimulatedOrder, SimulatedFill]:
        remaining = order.qty - order.filled_qty
        qty = remaining if self._partial_fill_ratio == 1 else min(remaining, max(remaining * self._partial_fill_ratio, 0.000001))
        filled_qty = order.filled_qty + qty
        status = SimulatedOrderStatus.FILLED if filled_qty >= order.qty else SimulatedOrderStatus.PARTIALLY_FILLED
        updated = order.model_copy(update={"filled_qty": filled_qty, "status": status, "updated_at": timestamp})
        self._replace_order(updated)
        fill = SimulatedFill(
            id=f"SIM-FILL-{len(self._fills) + 1:06d}",
            order_id=updated.id,
            symbol=updated.symbol,
            side=updated.side,
            qty=qty,
            price=price,
            timestamp=timestamp,
        )
        self._fills.append(fill)
        return updated, fill

    def active_open_orders(self) -> tuple[SimulatedOrder, ...]:
        return tuple(
            order
            for order in self._orders
            if order.intent == SimulatedOrderIntent.OPEN
            and order.status in {SimulatedOrderStatus.OPEN, SimulatedOrderStatus.PARTIALLY_FILLED}
        )

    def active_protective_orders(self, symbol: str) -> tuple[SimulatedOrder, ...]:
        return tuple(
            order
            for order in self._orders
            if order.symbol == symbol.upper()
            and order.intent in {
                SimulatedOrderIntent.STOP_LOSS,
                SimulatedOrderIntent.TAKE_PROFIT,
                SimulatedOrderIntent.TRAILING_STOP,
            }
            and order.status == SimulatedOrderStatus.OPEN
        )

    def cancel_active_protective_orders(self, symbol: str, *, timestamp: datetime) -> None:
        for order in self.active_protective_orders(symbol):
            self._replace_order(order.model_copy(update={"status": SimulatedOrderStatus.CANCELED, "updated_at": timestamp}))

    def snapshot_orders(self) -> tuple[SimulatedOrder, ...]:
        return tuple(self._orders)

    def snapshot_fills(self) -> tuple[SimulatedFill, ...]:
        return tuple(self._fills)

    def _replace_order(self, order: SimulatedOrder) -> None:
        for index, existing in enumerate(self._orders):
            if existing.id == order.id:
                self._orders[index] = order
                return
        raise SimulationError(f"unknown simulated order '{order.id}'")


class SimulatedBroker:
    def __init__(
        self,
        *,
        order_manager: SimulatedOrderManager,
        position_ledger: SimulatedPositionLedger,
        trade_ledger: SimulatedTradeLedger,
        event_log: SimulationEventLog,
        trailing_stop_enabled: bool,
    ) -> None:
        self._orders = order_manager
        self._positions = position_ledger
        self._trades = trade_ledger
        self._events = event_log
        self._trailing_stop_enabled = trailing_stop_enabled

    def process_bar(self, bar: NormalizedBar) -> None:
        self._update_trailing_stop(bar)
        self._process_protective_orders(bar)
        self._process_open_orders(bar)

    def submit_open_order(
        self,
        *,
        symbol: str,
        qty: float,
        timestamp: datetime,
        price: float,
        signal_name: str,
        stop: float | None,
        target: float | None,
    ) -> None:
        order = self._orders.create_order(
            symbol=symbol,
            intent=SimulatedOrderIntent.OPEN,
            side=SimulatedOrderSide.BUY,
            order_type=SimulatedOrderType.MARKET,
            qty=qty,
            timestamp=timestamp,
            signal_name=signal_name,
        )
        self._events.append(
            timestamp=timestamp,
            event_type=SimulatedEventType.ORDER_CREATED,
            symbol=symbol,
            message="simulated open order created",
            details={"order_id": order.id, "qty": qty, "stop": stop, "target": target},
        )
        updated, fill = self._orders.fill_order(order, price=price, timestamp=timestamp)
        position = self._positions.apply_open_fill(
            fill,
            stop=stop,
            target=target,
            entry_order_id=updated.id,
            trailing_enabled=self._trailing_stop_enabled,
        )
        self._log_fill(updated, fill)
        self._events.append(
            timestamp=timestamp,
            event_type=SimulatedEventType.POSITION_OPENED if position.qty == fill.qty else SimulatedEventType.POSITION_UPDATED,
            symbol=symbol,
            message="simulated position updated from open fill",
            details={"qty": position.qty, "avg_price": position.avg_price},
        )
        self._refresh_protective_orders(symbol=symbol, timestamp=timestamp, parent_order_id=updated.id)

    def _process_open_orders(self, bar: NormalizedBar) -> None:
        for order in self._orders.active_open_orders():
            if order.symbol != bar.symbol.upper():
                continue
            updated, fill = self._orders.fill_order(order, price=bar.close, timestamp=bar.timestamp)
            position = self._positions.apply_open_fill(
                fill,
                stop=self._positions.position_for(bar.symbol).open_stop,
                target=self._positions.position_for(bar.symbol).open_target,
                entry_order_id=updated.id,
                trailing_enabled=self._trailing_stop_enabled,
            )
            self._log_fill(updated, fill)
            self._events.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.POSITION_UPDATED,
                symbol=bar.symbol,
                message="simulated position updated from partial open fill",
                details={"qty": position.qty, "avg_price": position.avg_price},
            )
            self._refresh_protective_orders(symbol=bar.symbol, timestamp=bar.timestamp, parent_order_id=updated.id)

    def _process_protective_orders(self, bar: NormalizedBar) -> None:
        for order in self._orders.active_protective_orders(bar.symbol):
            trigger_price: float | None = None
            event_type: SimulatedEventType | None = None
            if order.intent in {SimulatedOrderIntent.STOP_LOSS, SimulatedOrderIntent.TRAILING_STOP}:
                if order.stop_price is not None and bar.low <= order.stop_price:
                    trigger_price = order.stop_price
                    event_type = SimulatedEventType.STOP_TRIGGERED
            elif order.intent == SimulatedOrderIntent.TAKE_PROFIT:
                if order.limit_price is not None and bar.high >= order.limit_price:
                    trigger_price = order.limit_price
                    event_type = SimulatedEventType.TARGET_TRIGGERED
            if trigger_price is None or event_type is None:
                continue

            updated, fill = self._orders.fill_order(order, price=trigger_price, timestamp=bar.timestamp)
            position, realized, entry_price, entry_order_id, opened_at = self._positions.apply_close_fill(fill)
            self._trades.record(
                symbol=bar.symbol.upper(),
                qty=fill.qty,
                entry_price=entry_price,
                exit_price=trigger_price,
                entry_order_id=entry_order_id,
                exit_order_id=updated.id,
                opened_at=opened_at,
                closed_at=bar.timestamp,
                realized_pnl=realized,
                exit_reason=order.intent,
            )
            self._log_fill(updated, fill)
            self._events.append(
                timestamp=bar.timestamp,
                event_type=event_type,
                symbol=bar.symbol,
                message=f"simulated {order.intent.value} triggered",
                details={"order_id": order.id, "price": trigger_price, "realized_pnl": realized},
            )
            if position.qty == 0:
                self._orders.cancel_active_protective_orders(bar.symbol, timestamp=bar.timestamp)
                self._events.append(
                    timestamp=bar.timestamp,
                    event_type=SimulatedEventType.POSITION_CLOSED,
                    symbol=bar.symbol,
                    message="simulated position closed",
                    details={"realized_pnl": realized},
                )
            break

    def _refresh_protective_orders(self, *, symbol: str, timestamp: datetime, parent_order_id: str) -> None:
        position = self._positions.position_for(symbol)
        if position.qty <= 0:
            return
        self._orders.cancel_active_protective_orders(symbol, timestamp=timestamp)
        if position.open_stop is not None:
            intent = SimulatedOrderIntent.TRAILING_STOP if self._trailing_stop_enabled else SimulatedOrderIntent.STOP_LOSS
            order = self._orders.create_order(
                symbol=symbol,
                intent=intent,
                side=SimulatedOrderSide.SELL,
                order_type=SimulatedOrderType.STOP,
                qty=position.qty,
                timestamp=timestamp,
                stop_price=position.open_stop,
                parent_order_id=parent_order_id,
            )
            self._events.append(
                timestamp=timestamp,
                event_type=SimulatedEventType.ORDER_CREATED,
                symbol=symbol,
                message="simulated protective stop created",
                details={"order_id": order.id, "stop_price": position.open_stop, "qty": position.qty},
            )
        if position.open_target is not None:
            order = self._orders.create_order(
                symbol=symbol,
                intent=SimulatedOrderIntent.TAKE_PROFIT,
                side=SimulatedOrderSide.SELL,
                order_type=SimulatedOrderType.LIMIT,
                qty=position.qty,
                timestamp=timestamp,
                limit_price=position.open_target,
                parent_order_id=parent_order_id,
            )
            self._events.append(
                timestamp=timestamp,
                event_type=SimulatedEventType.ORDER_CREATED,
                symbol=symbol,
                message="simulated protective target created",
                details={"order_id": order.id, "limit_price": position.open_target, "qty": position.qty},
            )

    def _update_trailing_stop(self, bar: NormalizedBar) -> None:
        if not self._trailing_stop_enabled:
            return
        position = self._positions.position_for(bar.symbol)
        if position.qty <= 0 or position.trailing_distance is None:
            return
        new_stop = bar.high - position.trailing_distance
        if position.open_stop is None or new_stop > position.open_stop:
            updated = self._positions.update_trailing_stop(bar.symbol, new_stop)
            self._refresh_protective_orders(symbol=bar.symbol, timestamp=bar.timestamp, parent_order_id="")
            self._events.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.TRAILING_STOP_UPDATED,
                symbol=bar.symbol,
                message="simulated trailing stop updated",
                details={"stop_price": updated.open_stop},
            )

    def _fill_price(self, order: SimulatedOrder, bar: NormalizedBar | None) -> float:
        if order.order_type == SimulatedOrderType.MARKET:
            if bar is None:
                raise SimulationError("market order fill requires bar price")
            return bar.close
        if order.limit_price is not None:
            return order.limit_price
        if order.stop_price is not None:
            return order.stop_price
        raise SimulationError(f"order '{order.id}' has no fill price")

    def _log_fill(self, order: SimulatedOrder, fill: SimulatedFill) -> None:
        event_type = (
            SimulatedEventType.ORDER_FILLED
            if order.status == SimulatedOrderStatus.FILLED
            else SimulatedEventType.ORDER_PARTIALLY_FILLED
        )
        self._events.append(
            timestamp=fill.timestamp,
            event_type=event_type,
            symbol=fill.symbol,
            message="simulated order fill recorded",
            details={"order_id": order.id, "fill_id": fill.id, "qty": fill.qty, "price": fill.price},
        )


class HistoricalReplayEngine:
    def __init__(
        self,
        *,
        feature_engine: BatchFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
        partial_fill_ratio: float = 1.0,
    ) -> None:
        self._feature_engine = feature_engine or BatchFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._partial_fill_ratio = partial_fill_ratio

    def run(
        self,
        *,
        components: ResolvedProgramComponents,
        bars: Sequence[NormalizedBar],
        start: datetime,
        end: datetime,
        initial_cash: float = 100_000,
        session_id: UUID | None = None,
    ) -> SimulationReplayResult:
        session = SimulationSession(
            id=session_id or uuid4(),
            mode=TradingMode.SIM_LAB_HISTORICAL,
            program_version_id=components.program.id,
            symbol_count=len(components.universe.symbols),
            start=start,
            end=end,
            initial_cash=initial_cash,
            partial_fill_model_id="deterministic_ratio" if self._partial_fill_ratio != 1 else "none",
        )
        plan = build_feature_plan(components, consumer="sim_replay")
        frame_set = self._feature_engine.compute(plan, bars)
        event_log = SimulationEventLog()
        order_manager = SimulatedOrderManager(partial_fill_ratio=self._partial_fill_ratio)
        position_ledger = SimulatedPositionLedger()
        trade_ledger = SimulatedTradeLedger()
        broker = SimulatedBroker(
            order_manager=order_manager,
            position_ledger=position_ledger,
            trade_ledger=trade_ledger,
            event_log=event_log,
            trailing_stop_enabled=components.execution_style.trailing_stop_enabled,
        )
        equity_curve = self._replay(
            components=components,
            plan=plan,
            frame_set=frame_set,
            bars=bars,
            broker=broker,
            order_manager=order_manager,
            position_ledger=position_ledger,
            trade_ledger=trade_ledger,
            event_log=event_log,
            initial_cash=initial_cash,
        )
        realized_pnl = sum(trade.realized_pnl for trade in trade_ledger.snapshot())
        gross_exposure = equity_curve[-1].gross_exposure if equity_curve else 0
        max_drawdown = max((point.drawdown for point in equity_curve), default=0)
        return SimulationReplayResult(
            session=session.model_copy(update={"feature_plan_id": plan.id, "current_timestamp": end}),
            orders=order_manager.snapshot_orders(),
            fills=order_manager.snapshot_fills(),
            positions=position_ledger.all_positions(),
            trades=trade_ledger.snapshot(),
            events=event_log.snapshot(),
            equity_curve=tuple(equity_curve),
            realized_pnl=realized_pnl,
            max_drawdown=max_drawdown,
            gross_exposure=gross_exposure,
        )

    def _replay(
        self,
        *,
        components: ResolvedProgramComponents,
        plan: FeaturePlan,
        frame_set: FeatureFrameSet,
        bars: Sequence[NormalizedBar],
        broker: SimulatedBroker,
        order_manager: SimulatedOrderManager,
        position_ledger: SimulatedPositionLedger,
        trade_ledger: SimulatedTradeLedger,
        event_log: SimulationEventLog,
        initial_cash: float,
    ) -> list[EquityPoint]:
        frames_by_symbol_timeframe = {
            (frame.symbol, frame.timeframe): frame
            for frame in frame_set.frames
        }
        equity_curve: list[EquityPoint] = []
        peak_equity = initial_cash
        for bar in sorted(bars, key=lambda item: item.timestamp):
            normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
            broker.process_bar(normalized_bar)
            if normalized_bar.timeframe == components.strategy_controls.timeframe:
                aligned_snapshot = self._aligned_snapshot(
                    plan=plan,
                    frames_by_symbol_timeframe=frames_by_symbol_timeframe,
                    bar=normalized_bar,
                )
                self._evaluate_signals(
                    components=components,
                    snapshot=aligned_snapshot,
                    broker=broker,
                    position_ledger=position_ledger,
                    event_log=event_log,
                    order_manager=order_manager,
                    bar=normalized_bar,
                    initial_cash=initial_cash,
                )
            realized = sum(trade.realized_pnl for trade in trade_ledger.snapshot())
            equity = initial_cash + realized + self._unrealized_pnl(position_ledger.open_positions(), {normalized_bar.symbol: normalized_bar.close})
            peak_equity = max(peak_equity, equity)
            drawdown = peak_equity - equity
            gross_exposure = self._gross_exposure(position_ledger.open_positions(), {normalized_bar.symbol: normalized_bar.close})
            equity_curve.append(
                EquityPoint(
                    timestamp=normalized_bar.timestamp,
                    cash=initial_cash + realized,
                    equity=equity,
                    realized_pnl=realized,
                    unrealized_pnl=equity - initial_cash - realized,
                    gross_exposure=gross_exposure,
                    drawdown=drawdown,
                )
            )
            event_log.append(
                timestamp=normalized_bar.timestamp,
                event_type=SimulatedEventType.PNL_UPDATED,
                symbol=normalized_bar.symbol,
                message="simulated equity updated",
                details={"equity": equity, "realized_pnl": realized, "gross_exposure": gross_exposure},
            )
        return equity_curve

    def _evaluate_signals(
        self,
        *,
        components: ResolvedProgramComponents,
        snapshot: FeatureSnapshot,
        broker: SimulatedBroker,
        position_ledger: SimulatedPositionLedger,
        event_log: SimulationEventLog,
        order_manager: SimulatedOrderManager,
        bar: NormalizedBar,
        initial_cash: float,
    ) -> None:
        if not self._controls_allow(components, bar.timestamp):
            event_log.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=bar.symbol,
                message="strategy controls blocked signal evaluation",
            )
            return
        try:
            evaluation = self._signal_engine.evaluate(components.strategy, snapshot)
        except SignalEvaluationError as exc:
            event_log.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=bar.symbol,
                message=str(exc),
            )
            return

        for intent in evaluation.intents:
            event_log.append(
                timestamp=intent.timestamp,
                event_type=SimulatedEventType.SIGNAL_CANDIDATE,
                symbol=intent.symbol,
                message="candidate trade intent emitted",
                details={"signal_name": intent.signal_name, "side": intent.side.value, "intent_type": intent.intent_type.value},
            )
            if intent.intent_type != IntentType.ENTRY or intent.side != CandidateSide.LONG:
                continue
            if position_ledger.position_for(intent.symbol).qty > 0:
                event_log.append(
                    timestamp=intent.timestamp,
                    event_type=SimulatedEventType.SIGNAL_BLOCKED,
                    symbol=intent.symbol,
                    message="open position already exists",
                )
                continue
            if order_manager.active_open_orders():
                event_log.append(
                    timestamp=intent.timestamp,
                    event_type=SimulatedEventType.SIGNAL_BLOCKED,
                    symbol=intent.symbol,
                    message="pending open order already exists",
                )
                continue
            qty = self._size_order(components=components, price=bar.close, initial_cash=initial_cash)
            broker.submit_open_order(
                symbol=intent.symbol,
                qty=qty,
                timestamp=bar.timestamp,
                price=bar.close,
                signal_name=intent.signal_name,
                stop=intent.stop_candidate,
                target=intent.target_candidate,
            )

    def _aligned_snapshot(
        self,
        *,
        plan: FeaturePlan,
        frames_by_symbol_timeframe: dict[tuple[str, str], FeatureFrame],
        bar: NormalizedBar,
    ) -> FeatureSnapshot:
        values: dict[str, FeatureValue] = {}
        for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            frame = frames_by_symbol_timeframe.get((bar.symbol.upper(), spec.timeframe))
            if frame is None:
                values[feature_key] = FeatureValue(value=None, availability=FeatureAvailability.MISSING)
                continue
            source_snapshot = self._latest_snapshot_at_or_before(frame, bar.timestamp)
            if source_snapshot is None:
                values[feature_key] = FeatureValue(value=None, availability=FeatureAvailability.MISSING)
                continue
            values[feature_key] = source_snapshot.values[feature_key]
        return FeatureSnapshot(symbol=bar.symbol.upper(), timeframe=bar.timeframe, timestamp=bar.timestamp, values=values)

    def _latest_snapshot_at_or_before(self, frame: FeatureFrame, timestamp: datetime) -> FeatureSnapshot | None:
        latest: FeatureSnapshot | None = None
        for snapshot in frame.snapshots:
            if snapshot.timestamp <= timestamp:
                latest = snapshot
            else:
                break
        return latest

    def _controls_allow(self, components: ResolvedProgramComponents, timestamp: datetime) -> bool:
        windows = components.strategy_controls.session_windows
        if not windows:
            return True
        current_time = timestamp.timetz().replace(tzinfo=None)
        return any(window.start <= current_time <= window.end for window in windows)

    def _size_order(self, *, components: ResolvedProgramComponents, price: float, initial_cash: float) -> float:
        risk_profile = components.risk_profile
        if risk_profile.sizing_method == PositionSizingMethod.FIXED_SHARES:
            if risk_profile.fixed_shares is None:
                raise SimulationError("fixed_shares sizing requires fixed_shares")
            return float(risk_profile.fixed_shares)
        if risk_profile.sizing_method == PositionSizingMethod.FIXED_DOLLAR:
            if risk_profile.fixed_notional is None:
                raise SimulationError("fixed_dollar sizing requires fixed_notional")
            return max(risk_profile.fixed_notional / price, 0.000001)
        if risk_profile.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY:
            if risk_profile.risk_per_trade_pct is None:
                raise SimulationError("risk_percent_equity sizing requires risk_per_trade_pct")
            notional = initial_cash * (risk_profile.risk_per_trade_pct / 100)
            return max(notional / price, 0.000001)
        raise SimulationError(f"unsupported sizing method '{risk_profile.sizing_method}'")

    def _unrealized_pnl(self, positions: Sequence[SimulatedPosition], latest_prices: dict[str, float]) -> float:
        return sum((latest_prices.get(position.symbol, position.avg_price) - position.avg_price) * position.qty for position in positions)

    def _gross_exposure(self, positions: Sequence[SimulatedPosition], latest_prices: dict[str, float]) -> float:
        return sum(abs(latest_prices.get(position.symbol, position.avg_price) * position.qty) for position in positions)
