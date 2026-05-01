from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from backend.app.decision import PositionContext, SignalEngine, SignalEvaluationError
from backend.app.decision.signal_plan_builder import SignalPlanBuilder
from backend.app.domain import (
    CandidateSide,
    CandidateTradeIntent,
    IntentType,
    LogicalExitRule,
    LogicalExitRuleKind,
    RiskDecisionCard,
    RiskDecisionMode,
    RiskDecisionStatus,
    SignalPlanLogicalExitScope,
    SignalPlanTargetAction,
    SignalRule,
    SimulationRunEvidence,
    SimulationSession,
    TradingMode,
)
from backend.app.features import (
    FeatureAvailability,
    FeatureFrame,
    FeatureFrameSet,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedDeploymentComponents,
    build_feature_plan,
)
from backend.app.risk_resolver import (
    AccountStateSnapshot,
    RiskDecisionCardSink,
    RiskResolver,
)
from backend.app.orders.protective_placer import ProtectiveOrderPlacer

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
        self._entry_signal_plan_by_symbol: dict[str, UUID] = {}
        self._entry_bar_index_by_symbol: dict[str, int] = {}

    def record_entry_lineage(
        self,
        *,
        symbol: str,
        signal_plan_id: UUID | None,
        bar_index: int,
    ) -> None:
        normalized = symbol.upper()
        if signal_plan_id is not None:
            self._entry_signal_plan_by_symbol.setdefault(normalized, signal_plan_id)
        self._entry_bar_index_by_symbol.setdefault(normalized, bar_index)

    def entry_signal_plan_id(self, symbol: str) -> UUID | None:
        return self._entry_signal_plan_by_symbol.get(symbol.upper())

    def entry_bar_index(self, symbol: str) -> int | None:
        return self._entry_bar_index_by_symbol.get(symbol.upper())

    def entry_timestamp(self, symbol: str) -> datetime | None:
        return self._entry_time_by_symbol.get(symbol.upper())

    def clear_entry_lineage(self, symbol: str) -> None:
        normalized = symbol.upper()
        self._entry_signal_plan_by_symbol.pop(normalized, None)
        self._entry_bar_index_by_symbol.pop(normalized, None)

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
        # Doctrine: qty is signed — positive for long, negative for short. The
        # weighted-avg price uses absolute share counts so SHORT opens (SELL
        # fills) and LONG opens (BUY fills) average the same way.
        position = self.position_for(fill.symbol)
        existing_abs = abs(position.qty)
        new_abs_qty = existing_abs + fill.qty
        avg_price = ((position.avg_price * existing_abs) + (fill.price * fill.qty)) / new_abs_qty
        if fill.side == SimulatedOrderSide.SELL:
            total_qty = position.qty - fill.qty  # short: more negative
        else:
            total_qty = position.qty + fill.qty  # long: more positive
        trailing_distance = position.trailing_distance
        if trailing_enabled and stop is not None:
            if fill.side == SimulatedOrderSide.SELL:
                # SHORT trailing: stop sits ABOVE entry, distance = stop - entry.
                trailing_distance = max(stop - fill.price, 0.01)
            else:
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
        # Doctrine: BUY-to-cover closes a SHORT (qty<0); SELL-to-close closes a
        # LONG (qty>0). Realized PnL flips sign with side: long earns when
        # exit > entry; short earns when entry > exit.
        position = self.position_for(fill.symbol)
        if position.qty == 0:
            raise SimulationError(f"cannot close empty position for {fill.symbol}")
        existing_abs = abs(position.qty)
        close_qty = min(fill.qty, existing_abs)
        if position.qty > 0:
            realized = (fill.price - position.avg_price) * close_qty
            remaining_qty = position.qty - close_qty
        else:
            realized = (position.avg_price - fill.price) * close_qty
            remaining_qty = position.qty + close_qty
        entry_order_id = self._entry_order_by_symbol.get(fill.symbol, "")
        opened_at = self._entry_time_by_symbol.get(fill.symbol, fill.timestamp)
        if remaining_qty == 0:
            updated = SimulatedPosition(symbol=fill.symbol, realized_pnl=position.realized_pnl + realized)
            self._entry_order_by_symbol.pop(fill.symbol, None)
            self._entry_time_by_symbol.pop(fill.symbol, None)
            self._entry_signal_plan_by_symbol.pop(fill.symbol, None)
            self._entry_bar_index_by_symbol.pop(fill.symbol, None)
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
        return tuple(position for position in self._positions.values() if position.qty != 0)

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
        side: str = "long",
        risk_decision_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        risk_plan_version_id: UUID | None = None,
    ) -> None:
        self._trades.append(
            SimulatedTrade(
                id=f"SIM-TRD-{len(self._trades) + 1:06d}",
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_order_id=entry_order_id,
                exit_order_id=exit_order_id,
                opened_at=opened_at,
                closed_at=closed_at,
                realized_pnl=realized_pnl,
                exit_reason=exit_reason,
                risk_decision_id=risk_decision_id,
                signal_plan_id=signal_plan_id,
                risk_plan_version_id=risk_plan_version_id,
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
        risk_decision_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        risk_plan_version_id: UUID | None = None,
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
            risk_decision_id=risk_decision_id,
            signal_plan_id=signal_plan_id,
            risk_plan_version_id=risk_plan_version_id,
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
            risk_decision_id=updated.risk_decision_id,
            signal_plan_id=updated.signal_plan_id,
            risk_plan_version_id=updated.risk_plan_version_id,
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

    def get_order(self, order_id: str) -> SimulatedOrder:
        for order in self._orders:
            if order.id == order_id:
                return order
        raise SimulationError(f"unknown simulated order '{order_id}'")

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

    def submit_close_order(
        self,
        *,
        symbol: str,
        qty: float,
        timestamp: datetime,
        price: float,
        signal_name: str,
        risk_decision_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        risk_plan_version_id: UUID | None = None,
    ) -> None:
        """Signal-driven exit fill.

        Cancels any active protective stop/target for the symbol (the position
        is being closed by an explicit logical_exit decision), creates a
        market order in the direction that closes the position (SELL for
        LONG positions, BUY-to-cover for SHORT positions), fills it at
        ``price``, and records the trade with full lineage
        (``risk_decision_id`` + ``signal_plan_id`` + ``risk_plan_version_id``).
        """
        position = self._positions.position_for(symbol)
        if position.qty == 0:
            return
        existing_abs = abs(position.qty)
        close_qty = min(qty, existing_abs)
        if close_qty <= 0:
            return
        close_side = SimulatedOrderSide.SELL if position.qty > 0 else SimulatedOrderSide.BUY
        position_side = "long" if position.qty > 0 else "short"
        self._orders.cancel_active_protective_orders(symbol, timestamp=timestamp)
        order = self._orders.create_order(
            symbol=symbol,
            intent=SimulatedOrderIntent.CLOSE,
            side=close_side,
            order_type=SimulatedOrderType.MARKET,
            qty=close_qty,
            timestamp=timestamp,
            signal_name=signal_name,
            risk_decision_id=risk_decision_id,
            signal_plan_id=signal_plan_id,
            risk_plan_version_id=risk_plan_version_id,
        )
        self._events.append(
            timestamp=timestamp,
            event_type=SimulatedEventType.ORDER_CREATED,
            symbol=symbol,
            message="signal-driven logical_exit close order created",
            details={
                "order_id": order.id,
                "qty": close_qty,
                "risk_decision_id": str(risk_decision_id) if risk_decision_id else None,
                "signal_plan_id": str(signal_plan_id) if signal_plan_id else None,
            },
        )
        updated, fill = self._orders.fill_order(order, price=price, timestamp=timestamp)
        position_after, realized, entry_price, entry_order_id, opened_at = self._positions.apply_close_fill(fill)
        self._trades.record(
            symbol=symbol.upper(),
            qty=fill.qty,
            entry_price=entry_price,
            exit_price=price,
            entry_order_id=entry_order_id,
            exit_order_id=updated.id,
            opened_at=opened_at,
            closed_at=timestamp,
            realized_pnl=realized,
            exit_reason=SimulatedOrderIntent.CLOSE,
            side=position_side,
            risk_decision_id=risk_decision_id,
            signal_plan_id=signal_plan_id,
            risk_plan_version_id=risk_plan_version_id,
        )
        self._log_fill(updated, fill)
        self._events.append(
            timestamp=timestamp,
            event_type=SimulatedEventType.POSITION_CLOSED if position_after.qty == 0 else SimulatedEventType.POSITION_UPDATED,
            symbol=symbol,
            message="signal-driven logical_exit fill recorded",
            details={
                "qty": fill.qty,
                "realized_pnl": realized,
                "remaining_qty": position_after.qty,
                "risk_decision_id": str(risk_decision_id) if risk_decision_id else None,
            },
        )

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
        side: SimulatedOrderSide = SimulatedOrderSide.BUY,
        risk_decision_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        risk_plan_version_id: UUID | None = None,
    ) -> None:
        order = self._orders.create_order(
            symbol=symbol,
            intent=SimulatedOrderIntent.OPEN,
            side=side,
            order_type=SimulatedOrderType.MARKET,
            qty=qty,
            timestamp=timestamp,
            signal_name=signal_name,
            risk_decision_id=risk_decision_id,
            signal_plan_id=signal_plan_id,
            risk_plan_version_id=risk_plan_version_id,
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
        # Doctrine: protective triggers are side-aware. A LONG protective stop
        # is a SELL fill triggered when bar.low <= stop_price; a LONG target
        # is a SELL when bar.high >= limit. A SHORT protective stop is a
        # BUY-to-cover triggered when bar.high >= stop_price; a SHORT target
        # is a BUY when bar.low <= limit.
        position_side_at_trigger = self._positions.position_for(bar.symbol)
        is_short = position_side_at_trigger.qty < 0
        for order in self._orders.active_protective_orders(bar.symbol):
            trigger_price: float | None = None
            event_type: SimulatedEventType | None = None
            if order.intent in {SimulatedOrderIntent.STOP_LOSS, SimulatedOrderIntent.TRAILING_STOP}:
                if order.stop_price is not None:
                    triggered = (
                        bar.high >= order.stop_price if is_short else bar.low <= order.stop_price
                    )
                    if triggered:
                        trigger_price = order.stop_price
                        event_type = SimulatedEventType.STOP_TRIGGERED
            elif order.intent == SimulatedOrderIntent.TAKE_PROFIT:
                if order.limit_price is not None:
                    triggered = (
                        bar.low <= order.limit_price if is_short else bar.high >= order.limit_price
                    )
                    if triggered:
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
                side="short" if is_short else "long",
                risk_decision_id=updated.risk_decision_id,
                signal_plan_id=updated.signal_plan_id,
                risk_plan_version_id=updated.risk_plan_version_id,
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
        # Doctrine: protective close direction mirrors the open direction —
        # SELL closes a LONG, BUY-to-cover closes a SHORT.
        position = self._positions.position_for(symbol)
        if position.qty == 0:
            return
        protective_side = SimulatedOrderSide.SELL if position.qty > 0 else SimulatedOrderSide.BUY
        protective_qty = abs(position.qty)
        parent = self._safe_get_order(parent_order_id)
        risk_decision_id = parent.risk_decision_id if parent is not None else None
        signal_plan_id = parent.signal_plan_id if parent is not None else None
        risk_plan_version_id = parent.risk_plan_version_id if parent is not None else None
        self._orders.cancel_active_protective_orders(symbol, timestamp=timestamp)
        if position.open_stop is not None:
            intent = SimulatedOrderIntent.TRAILING_STOP if self._trailing_stop_enabled else SimulatedOrderIntent.STOP_LOSS
            order = self._orders.create_order(
                symbol=symbol,
                intent=intent,
                side=protective_side,
                order_type=SimulatedOrderType.STOP,
                qty=protective_qty,
                timestamp=timestamp,
                stop_price=position.open_stop,
                parent_order_id=parent_order_id,
                risk_decision_id=risk_decision_id,
                signal_plan_id=signal_plan_id,
                risk_plan_version_id=risk_plan_version_id,
            )
            self._events.append(
                timestamp=timestamp,
                event_type=SimulatedEventType.ORDER_CREATED,
                symbol=symbol,
                message="simulated protective stop created",
                details={"order_id": order.id, "stop_price": position.open_stop, "qty": protective_qty},
            )
        if position.open_target is not None:
            order = self._orders.create_order(
                symbol=symbol,
                intent=SimulatedOrderIntent.TAKE_PROFIT,
                side=protective_side,
                order_type=SimulatedOrderType.LIMIT,
                qty=protective_qty,
                timestamp=timestamp,
                limit_price=position.open_target,
                parent_order_id=parent_order_id,
                risk_decision_id=risk_decision_id,
                signal_plan_id=signal_plan_id,
                risk_plan_version_id=risk_plan_version_id,
            )
            self._events.append(
                timestamp=timestamp,
                event_type=SimulatedEventType.ORDER_CREATED,
                symbol=symbol,
                message="simulated protective target created",
                details={"order_id": order.id, "limit_price": position.open_target, "qty": protective_qty},
            )

    def _update_trailing_stop(self, bar: NormalizedBar) -> None:
        # Doctrine: a LONG trailing stop ratchets UP using bar.high; a SHORT
        # trailing stop ratchets DOWN using bar.low. Distance is always
        # positive — direction is determined by position sign.
        if not self._trailing_stop_enabled:
            return
        position = self._positions.position_for(bar.symbol)
        if position.qty == 0 or position.trailing_distance is None:
            return
        if position.qty > 0:
            new_stop = bar.high - position.trailing_distance
            ratchet = position.open_stop is None or new_stop > position.open_stop
        else:
            new_stop = bar.low + position.trailing_distance
            ratchet = position.open_stop is None or new_stop < position.open_stop
        if ratchet:
            updated = self._positions.update_trailing_stop(bar.symbol, new_stop)
            self._refresh_protective_orders(symbol=bar.symbol, timestamp=bar.timestamp, parent_order_id="")
            self._events.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.TRAILING_STOP_UPDATED,
                symbol=bar.symbol,
                message="simulated trailing stop updated",
                details={"stop_price": updated.open_stop},
            )

    def _safe_get_order(self, order_id: str | None) -> SimulatedOrder | None:
        if not order_id:
            return None
        try:
            return self._orders.get_order(order_id)
        except SimulationError:
            return None

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
    """Unified research spine: FeatureEngine → SignalEngine → SignalPlanBuilder → RiskResolver → SimulatedBroker.

    RiskPlan belongs to the Account or selected research run. SignalPlan describes
    the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
    and current account or simulated account state to produce a RiskDecisionCard.
    No simulated or real order may be created without that RiskDecisionCard.
    """

    def __init__(
        self,
        *,
        feature_engine: IncrementalFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
        signal_plan_builder: SignalPlanBuilder | None = None,
        risk_resolver: RiskResolver | None = None,
        protective_placer: ProtectiveOrderPlacer | None = None,
        risk_decision_sink: RiskDecisionCardSink | None = None,
        mode: RiskDecisionMode | str = RiskDecisionMode.SIM_LAB,
        partial_fill_ratio: float = 1.0,
        evidence_recorder: object | None = None,
    ) -> None:
        self._feature_engine = feature_engine or IncrementalFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._signal_plan_builder = signal_plan_builder or SignalPlanBuilder()
        self._risk_resolver = risk_resolver or RiskResolver()
        self._protective_placer = protective_placer or ProtectiveOrderPlacer()
        self._risk_decision_sink = risk_decision_sink
        self._mode = RiskDecisionMode(mode) if isinstance(mode, str) else mode
        self._partial_fill_ratio = partial_fill_ratio
        self._evidence_recorder = evidence_recorder
        self._risk_decision_cards: list[RiskDecisionCard] = []

    def run(
        self,
        *,
        components: ResolvedDeploymentComponents,
        bars: Sequence[NormalizedBar],
        start: datetime,
        end: datetime,
        initial_cash: float = 100_000,
        session_id: UUID | None = None,
        run_id: UUID | None = None,
    ) -> SimulationReplayResult:
        self._risk_decision_cards = []
        session = SimulationSession(
            id=session_id or uuid4(),
            mode=TradingMode.SIM_LAB_HISTORICAL,
            strategy_version_id=components.strategy.id,
            symbol_count=len(components.universe.symbols),
            start=start,
            end=end,
            initial_cash=initial_cash,
            partial_fill_model_id="deterministic_ratio" if self._partial_fill_ratio != 1 else "none",
        )
        self._current_run_id = run_id or session.id
        self._current_session_id = session.id
        self._intent_sequence = 0
        self._deterministic_deployment_id = uuid5(NAMESPACE_URL, f"sim-deployment:{self._current_run_id}")
        self._deterministic_simulated_account_id = uuid5(
            NAMESPACE_URL, f"sim-account:{self._current_run_id}"
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
        evidence = SimulationRunEvidence(
            run_id=session.id,
            strategy_id=components.strategy.strategy_id,
            strategy_version_id=components.strategy.id,
            scenario_name="historical_replay",
            start=start,
            end=end,
            signal_plan_count=sum(1 for event in event_log.snapshot() if event.event_type == SimulatedEventType.SIGNAL_CANDIDATE),
            simulated_order_count=len(order_manager.snapshot_orders()),
            simulated_fill_count=len(order_manager.snapshot_fills()),
            metrics={
                "realized_pnl": realized_pnl,
                "max_drawdown": max_drawdown,
                "gross_exposure": gross_exposure,
            },
        )
        self._save_evidence(evidence)
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
            evidence=evidence,
        )

    def _save_evidence(self, evidence: SimulationRunEvidence) -> None:
        if self._evidence_recorder is not None and hasattr(self._evidence_recorder, "save_research_evidence"):
            self._evidence_recorder.save_research_evidence(evidence)

    def _replay(
        self,
        *,
        components: ResolvedDeploymentComponents,
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
        bar_index_by_symbol: dict[str, int] = {}
        for bar in sorted(bars, key=lambda item: item.timestamp):
            normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
            symbol = normalized_bar.symbol
            bar_index_by_symbol[symbol] = bar_index_by_symbol.get(symbol, -1) + 1
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
                    trade_ledger=trade_ledger,
                    bar=normalized_bar,
                    initial_cash=initial_cash,
                    bar_index_by_symbol=bar_index_by_symbol,
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
        components: ResolvedDeploymentComponents,
        snapshot: FeatureSnapshot,
        broker: SimulatedBroker,
        position_ledger: SimulatedPositionLedger,
        event_log: SimulationEventLog,
        order_manager: SimulatedOrderManager,
        trade_ledger: SimulatedTradeLedger,
        bar: NormalizedBar,
        initial_cash: float,
        bar_index_by_symbol: dict[str, int],
    ) -> None:
        if not self._controls_allow(components, bar.timestamp):
            event_log.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=bar.symbol,
                message="strategy controls blocked signal evaluation",
            )
            return

        # Build per-symbol PositionContext for exit-rule evaluation.
        position_contexts: dict[str, PositionContext] = {}
        for symbol_key, current_index in bar_index_by_symbol.items():
            position = position_ledger.position_for(symbol_key)
            position_contexts[symbol_key] = PositionContext(
                has_position=position.qty > 0,
                entry_timestamp=position_ledger.entry_timestamp(symbol_key),
                entry_bar_index=position_ledger.entry_bar_index(symbol_key),
                current_bar_index=current_index,
                bar_timestamp=bar.timestamp,
            )

        try:
            evaluation = self._signal_engine.evaluate(
                components.strategy,
                snapshot,
                position_contexts=position_contexts,
            )
        except SignalEvaluationError as exc:
            event_log.append(
                timestamp=bar.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=bar.symbol,
                message=str(exc),
            )
            return

        rules_by_name = {rule.name: rule for rule in [*components.strategy.entry_rules, *components.strategy.exit_rules]}

        for intent in evaluation.intents:
            event_log.append(
                timestamp=intent.timestamp,
                event_type=SimulatedEventType.SIGNAL_CANDIDATE,
                symbol=intent.symbol,
                message="candidate trade intent emitted",
                details={"signal_name": intent.signal_name, "side": intent.side.value, "intent_type": intent.intent_type.value},
            )

            if intent.intent_type == IntentType.EXIT:
                self._handle_exit_intent(
                    intent=intent,
                    components=components,
                    bar=bar,
                    broker=broker,
                    position_ledger=position_ledger,
                    event_log=event_log,
                    rules_by_name=rules_by_name,
                    bar_index_by_symbol=bar_index_by_symbol,
                )
                continue

            if intent.side not in {CandidateSide.LONG, CandidateSide.SHORT}:
                continue
            existing_position = position_ledger.position_for(intent.symbol)
            same_side = (
                (intent.side == CandidateSide.LONG and existing_position.qty > 0)
                or (intent.side == CandidateSide.SHORT and existing_position.qty < 0)
            )
            opposite_side = (
                (intent.side == CandidateSide.LONG and existing_position.qty < 0)
                or (intent.side == CandidateSide.SHORT and existing_position.qty > 0)
            )
            if same_side:
                event_log.append(
                    timestamp=intent.timestamp,
                    event_type=SimulatedEventType.SIGNAL_BLOCKED,
                    symbol=intent.symbol,
                    message="open position already exists",
                )
                continue
            if opposite_side:
                # Cross-side flips (long↔short while a position is open)
                # require a flatten leg the spine doesn't yet emit; reject
                # with a stable reason code so the operator sees the gap.
                event_log.append(
                    timestamp=intent.timestamp,
                    event_type=SimulatedEventType.SIGNAL_BLOCKED,
                    symbol=intent.symbol,
                    message="opposite_side_position_open",
                    details={"existing_qty": existing_position.qty, "candidate_side": intent.side.value},
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

            # Spine: CandidateTradeIntent -> SignalPlan -> RiskResolver -> RiskDecisionCard
            self._intent_sequence += 1
            seq = self._intent_sequence
            deterministic_signal_plan_id = uuid5(
                NAMESPACE_URL, f"signal-plan:{self._current_run_id}:{seq}"
            )
            deterministic_risk_decision_id = uuid5(
                NAMESPACE_URL, f"risk-decision:{self._current_run_id}:{seq}"
            )
            raw_signal_plan = self._signal_plan_builder.build_from_candidate(
                candidate=intent,
                deployment_id=self._deterministic_deployment_id,
                strategy_id=components.strategy.strategy_id,
                strategy_version_id=components.strategy.id,
                execution_plan=components.execution_style,
            )
            signal_plan = raw_signal_plan.model_copy(update={"signal_plan_id": deterministic_signal_plan_id})
            realized = sum(t.realized_pnl for t in trade_ledger.snapshot())
            existing = position_ledger.position_for(intent.symbol)
            existing_abs_qty = abs(existing.qty)
            account_state = AccountStateSnapshot(
                account_equity=initial_cash + realized,
                account_cash=initial_cash + realized,
                buying_power=initial_cash + realized,
                existing_position_quantity=existing_abs_qty,
                existing_position_notional=existing_abs_qty * existing.avg_price,
                existing_open_orders_count=len(order_manager.active_open_orders()),
                existing_open_order_notional=0,
                simulated_account_id=self._deterministic_simulated_account_id,
            )
            raw_card = self._risk_resolver.decide(
                mode=self._mode,
                run_id=self._current_run_id,
                signal_plan=signal_plan,
                risk_plan_version=components.risk_profile,
                account_state=account_state,
                current_price=bar.close,
                stop_candidate=intent.stop_candidate,
                session_id=self._current_session_id,
                deployment_id=signal_plan.deployment_id,
                sink=None,
            )
            card = raw_card.model_copy(update={"risk_decision_id": deterministic_risk_decision_id})
            if self._risk_decision_sink is not None:
                self._risk_decision_sink.save_risk_decision_card(card)
            self._risk_decision_cards.append(card)

            if card.decision != RiskDecisionStatus.APPROVED and card.decision not in {
                RiskDecisionStatus.REDUCED,
                RiskDecisionStatus.CAPPED,
            }:
                event_log.append(
                    timestamp=intent.timestamp,
                    event_type=SimulatedEventType.SIGNAL_BLOCKED,
                    symbol=intent.symbol,
                    message=f"risk decision: {card.decision.value}",
                    details={
                        "risk_decision_id": str(card.risk_decision_id),
                        "signal_plan_id": str(signal_plan.signal_plan_id),
                        "violations": list(card.violations),
                        "reason_codes": list(card.reason_codes),
                    },
                )
                continue

            stop_price, target_price = self._protective_prices(
                signal_plan=signal_plan,
                fill_price=bar.close,
                qty=card.final_quantity,
                fallback_stop=intent.stop_candidate,
                fallback_target=intent.target_candidate,
            )
            broker.submit_open_order(
                symbol=intent.symbol,
                qty=card.final_quantity,
                timestamp=bar.timestamp,
                price=bar.close,
                signal_name=intent.signal_name,
                stop=stop_price,
                target=target_price,
                side=(
                    SimulatedOrderSide.SELL
                    if intent.side == CandidateSide.SHORT
                    else SimulatedOrderSide.BUY
                ),
                risk_decision_id=card.risk_decision_id,
                signal_plan_id=signal_plan.signal_plan_id,
                risk_plan_version_id=components.risk_profile.id,
            )
            position_ledger.record_entry_lineage(
                symbol=intent.symbol,
                signal_plan_id=signal_plan.signal_plan_id,
                bar_index=bar_index_by_symbol.get(intent.symbol.upper(), 0),
            )

    def _handle_exit_intent(
        self,
        *,
        intent: CandidateTradeIntent,
        components: ResolvedDeploymentComponents,
        bar: NormalizedBar,
        broker: SimulatedBroker,
        position_ledger: SimulatedPositionLedger,
        event_log: SimulationEventLog,
        rules_by_name: dict[str, SignalRule],
        bar_index_by_symbol: dict[str, int],
    ) -> None:
        """Spine: EXIT candidate -> SignalPlan(logical_exit) -> RiskResolver -> broker.submit_close_order.

        Doctrine: ``logical_exit`` is the only exit intent. Time / bar /
        session / feature / hybrid exits all flow through this single path.
        """
        position = position_ledger.position_for(intent.symbol)
        if position.qty == 0:
            event_log.append(
                timestamp=intent.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=intent.symbol,
                message="exit candidate ignored: no open position",
            )
            return

        source_rule = rules_by_name.get(intent.signal_name)
        if source_rule is None:
            event_log.append(
                timestamp=intent.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=intent.symbol,
                message=f"exit candidate references unknown rule '{intent.signal_name}'",
            )
            return

        # Build the LogicalExitRule payload for the SignalPlan. Pure
        # feature-condition exits wrap the rule's condition tree as
        # FEATURE_CONDITION; structured exits use the rule's own
        # logical_exit_rule (time / bar / session / hybrid).
        if source_rule.logical_exit_rule is not None:
            exit_rule_payload = source_rule.logical_exit_rule
        elif source_rule.condition is not None:
            exit_rule_payload = LogicalExitRule(
                kind=LogicalExitRuleKind.FEATURE_CONDITION,
                feature_condition=source_rule.condition,
                label=f"{source_rule.name}_feature_condition",
            )
        else:
            event_log.append(
                timestamp=intent.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=intent.symbol,
                message=f"exit rule '{source_rule.name}' has no condition or logical_exit_rule",
            )
            return

        self._intent_sequence += 1
        seq = self._intent_sequence
        deterministic_signal_plan_id = uuid5(
            NAMESPACE_URL, f"signal-plan:{self._current_run_id}:{seq}"
        )
        deterministic_risk_decision_id = uuid5(
            NAMESPACE_URL, f"risk-decision:{self._current_run_id}:{seq}"
        )

        opening_signal_plan_id = position_ledger.entry_signal_plan_id(intent.symbol)
        # The SignalPlan validator requires non-OPEN plans to reference an
        # opening_signal_plan_id or a related_position_lineage_id; for sim
        # bar-by-bar replay we always have the opener tracked on the ledger.
        if opening_signal_plan_id is None:
            opening_signal_plan_id = uuid5(
                NAMESPACE_URL, f"sim-position-lineage:{self._current_run_id}:{intent.symbol.upper()}"
            )

        raw_signal_plan = self._signal_plan_builder.build_from_candidate(
            candidate=intent,
            deployment_id=self._deterministic_deployment_id,
            strategy_id=components.strategy.strategy_id,
            strategy_version_id=components.strategy.id,
            opening_signal_plan_id=opening_signal_plan_id,
            logical_exit_rule=exit_rule_payload,
            logical_exit_action=SignalPlanTargetAction.CLOSE,
            logical_exit_quantity_pct=None,
            logical_exit_scope=SignalPlanLogicalExitScope.REMAINING_QUANTITY,
        )
        signal_plan = raw_signal_plan.model_copy(update={"signal_plan_id": deterministic_signal_plan_id})

        existing_abs_qty = abs(position.qty)
        existing_notional = existing_abs_qty * position.avg_price
        account_state = AccountStateSnapshot(
            account_equity=existing_notional,
            account_cash=existing_notional,
            buying_power=existing_notional,
            existing_position_quantity=existing_abs_qty,
            existing_position_notional=existing_notional,
            existing_open_orders_count=0,
            existing_open_order_notional=0,
            simulated_account_id=self._deterministic_simulated_account_id,
        )

        raw_card = self._risk_resolver.decide(
            mode=self._mode,
            run_id=self._current_run_id,
            signal_plan=signal_plan,
            risk_plan_version=components.risk_profile,
            account_state=account_state,
            current_price=bar.close,
            stop_candidate=None,
            session_id=self._current_session_id,
            deployment_id=signal_plan.deployment_id,
            sink=None,
            exit_quantity_pct=None,
        )
        card = raw_card.model_copy(update={"risk_decision_id": deterministic_risk_decision_id})
        if self._risk_decision_sink is not None:
            self._risk_decision_sink.save_risk_decision_card(card)
        self._risk_decision_cards.append(card)

        if card.decision == RiskDecisionStatus.SKIPPED or card.final_quantity <= 0:
            event_log.append(
                timestamp=intent.timestamp,
                event_type=SimulatedEventType.SIGNAL_BLOCKED,
                symbol=intent.symbol,
                message=f"exit risk decision: {card.decision.value}",
                details={
                    "risk_decision_id": str(card.risk_decision_id),
                    "signal_plan_id": str(signal_plan.signal_plan_id),
                    "violations": list(card.violations),
                    "reason_codes": list(card.reason_codes),
                },
            )
            return

        broker.submit_close_order(
            symbol=intent.symbol,
            qty=card.final_quantity,
            timestamp=bar.timestamp,
            price=bar.close,
            signal_name=intent.signal_name,
            risk_decision_id=card.risk_decision_id,
            signal_plan_id=signal_plan.signal_plan_id,
            risk_plan_version_id=components.risk_profile.id,
        )
        # If the position fully closed, the ledger has already cleared lineage
        # in apply_close_fill; otherwise (partial reduce) lineage stays so
        # subsequent exit rules continue to reference the same opener.

    def _protective_prices(
        self,
        *,
        signal_plan,
        fill_price: float,
        qty: float,
        fallback_stop: float | None,
        fallback_target: float | None,
    ) -> tuple[float | None, float | None]:
        # P1-6: replay should run through the same post-fill protective
        # planner as the broker runtime when SignalPlan uses post_fill_pct intent.
        # Legacy candidate-based stop/target remains as fallback so historical
        # tests that still emit concrete candidates keep behaving deterministically.
        plan = self._protective_placer.compute_protective_plan(
            signal_plan=signal_plan,
            parent_order_id=uuid5(NAMESPACE_URL, f"sim-parent:{signal_plan.signal_plan_id}"),
            account_id=self._deterministic_simulated_account_id,
            fill_price=fill_price,
            cumulative_filled_qty=qty,
            already_covered_qty=0.0,
        )
        stop_leg = next((leg for leg in plan.legs if leg.stop_price is not None), None)
        target_leg = next((leg for leg in plan.legs if leg.limit_price is not None), None)
        stop = stop_leg.stop_price if stop_leg is not None else fallback_stop
        target = target_leg.limit_price if target_leg is not None else fallback_target
        return stop, target

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

    def _controls_allow(self, components: ResolvedDeploymentComponents, timestamp: datetime) -> bool:
        windows = components.strategy_controls.session_windows
        if not windows:
            return True
        current_time = timestamp.timetz().replace(tzinfo=None)
        return any(window.start <= current_time <= window.end for window in windows)

    def risk_decision_cards(self) -> tuple[RiskDecisionCard, ...]:
        return tuple(self._risk_decision_cards)

    def _unrealized_pnl(self, positions: Sequence[SimulatedPosition], latest_prices: dict[str, float]) -> float:
        # Signed qty makes this side-correct without a branch: SHORT qty<0
        # against (price - avg)>0 yields negative PnL (short losing as price
        # rises); LONG qty>0 against (price - avg)>0 yields positive PnL.
        return sum(
            (latest_prices.get(position.symbol, position.avg_price) - position.avg_price) * position.qty
            for position in positions
        )

    def _gross_exposure(self, positions: Sequence[SimulatedPosition], latest_prices: dict[str, float]) -> float:
        return sum(
            abs(latest_prices.get(position.symbol, position.avg_price)) * abs(position.qty)
            for position in positions
        )
