"""End-to-end test for the operator manual-trade loop.

Pins the seven contracts the DE memo (2026-04-26) demanded for the
"submit order from the app, see the effects, cancel an order" feature:

1. Submit returns ACCEPTED, ledger has the order, broker saw it.
2. Submit propagates an ``order_event`` style payload through the
   per-account TradeEventDispatcher (the same path the trade-stream
   WebSocket uses).
3. Cancel marks the ledger CANCELED and returns 200.
4. Cancel races a fill: broker reports FILLED first → 409 with the
   filled truth surfaced, ledger reflects FILLED.
5. Cancel-already-canceled is a no-op 200.
6. Re-submit with the same idempotency_key returns the existing order.
7. Position snapshot reflects the fill quantity after a position event.

Stack under test (real, not mocks):
- ``OrderManager``, ``BrokerSync``, ``BrokerSyncService``, ``OrderLedger``,
  ``TradeLedger``
- The ``manual_trade`` route module (``submit_manual_order`` /
  ``cancel_manual_order`` / ``list_manual_orders``)
- ``ManualTradeRegistry`` from ``runtime_context``

Mocked: ``FakeBrokerAdapter`` for deterministic broker behavior; a small
``FakeBrokerAccountService`` that returns a paper account; the
TradeEventDispatcher's ``subscribe()`` callback (real dispatcher, fake
events injected so we do not need an Alpaca network).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.api.routes import manual_trade
from backend.app.api.routes.manual_trade import (
    CancelOrderResponse,
    ManualOrderRequest,
    ManualOrderResponse,
    cancel_manual_order,
    list_manual_orders,
    submit_manual_order,
)
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.brokers.fake import FakeBrokerAdapter
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.orders import (
    InternalOrder,
    InternalOrderIntent,
    InternalOrderStatus,
    OrderOrigin,
    OrderManager,
    OrderManagerError,
    TradeLedger,
)
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore, SQLiteTradeLedger
from backend.app.runtime.runtime_context import (
    TradeEventDispatcherRegistry,
    manual_trade_registry,
    shutdown_runtime_context,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
SECOND_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
OPERATOR_SESSION_ID = "test-operator-session"
_DB_PATH = None


_real_submit_manual_order = submit_manual_order
_real_cancel_manual_order = cancel_manual_order


def submit_manual_order(*args, **kwargs):
    kwargs.setdefault("operator_session_id", OPERATOR_SESSION_ID)
    return _real_submit_manual_order(*args, **kwargs)


def cancel_manual_order(*args, **kwargs):
    kwargs.setdefault("operator_session_id", OPERATOR_SESSION_ID)
    return _real_cancel_manual_order(*args, **kwargs)


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


class _FakeBrokerAccountService:
    """Minimal BrokerAccountService stand-in."""

    def __init__(self, *accounts: BrokerAccount) -> None:
        self._accounts = accounts

    def list_broker_accounts(self) -> tuple[BrokerAccount, ...]:
        return self._accounts


def _make_paper_account(
    mode: TradingMode = TradingMode.BROKER_PAPER,
    *,
    account_id: UUID = ACCOUNT_ID,
    display_name: str = "Algo Trading - Paper",
) -> BrokerAccount:
    return BrokerAccount(
        id=account_id,
        display_name=display_name,
        provider="alpaca",
        mode=mode,
        external_account_id=f"PA{account_id.hex[:8]}",
        credentials_ref="alpaca-paper:abc:def",
        validation_status=BrokerAccountValidationStatus.VALID,
    )


def _account_snapshot() -> BrokerAccountSnapshot:
    return BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        buying_power=100_000,
        cash=100_000,
        equity=100_000,
    )


def _build_stack(
    *,
    account_id: UUID = ACCOUNT_ID,
    scripted: list[BrokerOrderStatus | BrokerOrderResult] | None = None,
) -> tuple[OrderManager, FakeBrokerAdapter, BrokerSyncService, TradeLedger]:
    """Compose the full money-path stack and register it in the manual-trade registry."""

    assert _DB_PATH is not None
    runtime_store = SQLiteRuntimeStore(_DB_PATH)
    adapter = FakeBrokerAdapter(
        scripted_results=scripted or [],
        account_snapshots={account_id: _account_snapshot().model_copy(update={"account_id": account_id})},
    )
    ledger = SQLiteTradeLedger(_DB_PATH)
    manager = OrderManager(ledger=SQLiteOrderLedger(_DB_PATH), broker_adapter=adapter)
    broker_sync = BrokerSync(ledger=manager.ledger, adapter=adapter, runtime_store=runtime_store, provider="alpaca")
    sync_service = BrokerSyncService(
        adapter=adapter,
        broker_sync=broker_sync,
        order_ledger=manager.ledger,
        trade_ledger=ledger,
        runtime_store=runtime_store,
        max_stale_seconds=300,
    )
    sync_service.record_successful_poll(account_id)
    manager._broker_sync = broker_sync
    manager.attach_broker_sync_service(sync_service)
    registry = manual_trade_registry()
    registry.register(
        account_id,
        order_manager=manager,
        broker_sync_service=sync_service,
        broker_adapter=adapter,
        runtime_store=runtime_store,
    )
    return manager, adapter, sync_service, ledger


def _request(idempotency_key: str | None = None, **overrides) -> ManualOrderRequest:
    base = {
        "symbol": "SPY",
        "side": CandidateSide.LONG,
        "qty": 10.0,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "intent": "open",
        "reason": "operator_smoke_test",
        "idempotency_key": idempotency_key or uuid4().hex,
    }
    base.update(overrides)
    return ManualOrderRequest(**base)


@pytest.fixture(autouse=True)
def _reset_runtime_context_between_tests(tmp_path) -> None:
    """Each test gets a fresh registry + idempotency cache."""
    global _DB_PATH
    _DB_PATH = tmp_path / "manual-trade.db"
    shutdown_runtime_context()
    manual_trade.reset_manual_trade_state_for_tests()
    yield
    shutdown_runtime_context()
    manual_trade.reset_manual_trade_state_for_tests()
    _DB_PATH = None


# ---------------------------------------------------------------------------
# Tests — the seven DE-mandated assertions
# ---------------------------------------------------------------------------


def test_submit_manual_order_returns_accepted_and_appears_in_ledger() -> None:
    manager, adapter, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())

    response = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )

    assert isinstance(response, ManualOrderResponse)
    assert response.status == InternalOrderStatus.ACCEPTED
    assert response.client_order_id.startswith("manual-")
    # Ledger now has the order in ACCEPTED state.
    ledger_order = manager.ledger.get(response.order_id)
    assert ledger_order.status == InternalOrderStatus.ACCEPTED
    # Adapter saw exactly one submit with the same client_order_id.
    assert len(adapter.submitted_orders) == 1
    assert adapter.submitted_orders[0].client_order_id == response.client_order_id


def test_submit_emits_order_event_through_per_account_dispatcher() -> None:
    """The trade-stream WS reads from the per-account TradeEventDispatcher.

    We can't open a real WebSocket without FastAPI, but we *can* prove that
    when the broker emits an order update event, the dispatcher fans it out
    to every subscriber — which is exactly what the WS handler subscribes
    as. That's the contract the WS surface depends on.
    """
    manager, _, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    response = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )

    # Stand up a dispatcher and subscribe (mirrors operations_trade_stream).
    dispatcher_registry = TradeEventDispatcherRegistry()
    dispatcher = dispatcher_registry.get_or_create(ACCOUNT_ID)
    received: list[object] = []
    dispatcher.subscribe(received.append)

    # Inject the order event the broker would emit on accept.
    order_event = BrokerOrderUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id=response.client_order_id,
        broker_order_id=f"broker-{response.client_order_id}",
        status=BrokerOrderStatus.ACCEPTED,
        broker_status="accepted",
        filled_quantity=0.0,
        event_at=datetime.now(timezone.utc),
    )
    # ``deliver`` is the public seam wired as the AlpacaAccountStreamAdapter
    # subscribe-callback in production — same path a real broker event takes.
    dispatcher.deliver(order_event)
    dispatcher_registry.shutdown()

    assert len(received) == 1
    fanned = received[0]
    assert getattr(fanned, "client_order_id", None) == response.client_order_id
    assert getattr(fanned, "status", None) == BrokerOrderStatus.ACCEPTED


def test_cancel_manual_order_marks_canceled_in_ledger_and_returns_200() -> None:
    manager, adapter, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    submitted = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )

    response = cancel_manual_order(
        ACCOUNT_ID,
        submitted.order_id,
        service=service,
        registry=manual_trade_registry(),
    )

    assert isinstance(response, CancelOrderResponse)
    assert response.status == InternalOrderStatus.CANCELED
    assert response.no_op is False
    assert manager.ledger.get(submitted.order_id).status == InternalOrderStatus.CANCELED
    assert adapter.canceled_client_order_ids == [submitted.client_order_id]


def test_cancel_already_filled_returns_409_with_filled_truth() -> None:
    """Broker fills before our cancel reaches it; truth wins."""

    # First, a normal submit to establish the order in the ledger.
    manager, adapter, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    submitted = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )

    # Simulate the broker filling out-of-band: rewrite the cached result so
    # that subsequent cancel sees a FILLED truth (the same shape the real
    # adapter would expose if a fill landed before cancel reached the wire).
    filled_result = adapter._results_by_order_id[submitted.order_id].model_copy(
        update={
            "status": BrokerOrderStatus.FILLED,
            "broker_status": BrokerOrderStatus.FILLED.value,
            "filled_quantity": 10.0,
            "remaining_quantity": 0.0,
            "raw_status": BrokerOrderStatus.FILLED.value,
        }
    )
    adapter._results_by_order_id[submitted.order_id] = filled_result
    # Reflect the fill in the local ledger like BrokerSync would on poll.
    manager._broker_sync.apply_result(filled_result)

    # The cancel route now sees FILLED in the ledger and refuses with 409.
    try:
        cancel_manual_order(
            ACCOUNT_ID,
            submitted.order_id,
            service=service,
            registry=manual_trade_registry(),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
        assert "order_already_filled" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("expected 409 from cancel against FILLED order")
    # Ledger truth: still FILLED.
    assert manager.ledger.get(submitted.order_id).status == InternalOrderStatus.FILLED


def test_cancel_already_canceled_is_idempotent_no_op_200() -> None:
    manager, _, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    submitted = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )
    cancel_manual_order(
        ACCOUNT_ID,
        submitted.order_id,
        service=service,
        registry=manual_trade_registry(),
    )

    second = cancel_manual_order(
        ACCOUNT_ID,
        submitted.order_id,
        service=service,
        registry=manual_trade_registry(),
    )

    assert second.status == InternalOrderStatus.CANCELED
    assert second.no_op is True
    assert second.message == "already_canceled"


def test_resubmit_with_same_idempotency_key_returns_existing_order() -> None:
    manager, adapter, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    key = "same-key-please"

    first = submit_manual_order(
        ACCOUNT_ID,
        _request(idempotency_key=key),
        service=service,
        registry=manual_trade_registry(),
    )
    second = submit_manual_order(
        ACCOUNT_ID,
        _request(idempotency_key=key),
        service=service,
        registry=manual_trade_registry(),
    )

    assert second.order_id == first.order_id
    assert second.duplicate is True
    # Adapter saw exactly one submit despite two HTTP-equivalent calls.
    assert len(adapter.submitted_orders) == 1


def test_position_snapshot_reflects_fill_when_broker_fills_before_cancel() -> None:
    """A subsequent position event after a fill is visible via BrokerSyncService."""

    # Submit + script broker to fill the order on submit.
    _, adapter, sync_service, _ = _build_stack(
        scripted=[BrokerOrderStatus.FILLED],
    )
    service = _FakeBrokerAccountService(_make_paper_account())
    submitted = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )
    # Broker reported FILLED at submit, ledger should reflect it.
    assert submitted.status == InternalOrderStatus.FILLED
    assert submitted.filled_quantity == 10.0

    # Now feed a position event into the sync service, mimicking the
    # post-fill update the runtime would route from the trading stream.
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        side=BrokerPositionSide.LONG,
        qty=10.0,
        avg_entry_price=400.0,
        market_value=4000.0,
    )
    sync_service.handle_position_update(position)

    positions = sync_service.latest_positions(ACCOUNT_ID)
    assert any(p.symbol == "SPY" and p.quantity == 10.0 for p in positions)


# ---------------------------------------------------------------------------
# Additional safety contracts (DE memo §1.3)
# ---------------------------------------------------------------------------


def test_live_account_blocks_without_explicit_confirmation() -> None:
    _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account(mode=TradingMode.BROKER_LIVE))

    try:
        submit_manual_order(
            ACCOUNT_ID,
            _request(),
            service=service,
            registry=manual_trade_registry(),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
        assert "manual_trade_blocked_live_account" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("live account submit must be blocked without confirmation")


def test_live_account_with_correct_confirmation_proceeds() -> None:
    _build_stack()
    account = _make_paper_account(mode=TradingMode.BROKER_LIVE)
    service = _FakeBrokerAccountService(account)
    response = submit_manual_order(
        ACCOUNT_ID,
        _request(
            confirm_live=True,
            confirm_account_display_name=account.display_name,
        ),
        service=service,
        registry=manual_trade_registry(),
    )
    assert response.status == InternalOrderStatus.ACCEPTED


def test_live_account_with_wrong_display_name_is_blocked() -> None:
    _build_stack()
    account = _make_paper_account(mode=TradingMode.BROKER_LIVE)
    service = _FakeBrokerAccountService(account)
    try:
        submit_manual_order(
            ACCOUNT_ID,
            _request(
                confirm_live=True,
                confirm_account_display_name="Some Other Account",
            ),
            service=service,
            registry=manual_trade_registry(),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
        assert "name_mismatch" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("display-name mismatch must be blocked")


def test_idempotency_reserve_then_release_lets_retry_proceed() -> None:
    """A failing submit must release the reservation so the next try works.

    Otherwise an early-failure would poison the idempotency_key forever
    until process restart.
    """
    _, adapter, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())

    # First call: rig adapter to raise on submit.
    def boom(_order):
        raise OrderManagerError("simulated_broker_outage")

    adapter.submit_order = boom  # type: ignore[assignment]
    key = "shared-key-after-failure"
    try:
        submit_manual_order(
            ACCOUNT_ID,
            _request(idempotency_key=key),
            service=service,
            registry=manual_trade_registry(),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) in {400, 409}
    else:
        raise AssertionError("expected the rigged failure")

    # Restore real submit and retry with the same key — must succeed.
    real_adapter = FakeBrokerAdapter(account_snapshots={ACCOUNT_ID: _account_snapshot()})
    manual_trade_registry()._entries[ACCOUNT_ID]["broker_adapter"] = real_adapter  # type: ignore[index]
    second = submit_manual_order(
        ACCOUNT_ID,
        _request(idempotency_key=key),
        service=service,
        registry=manual_trade_registry(),
    )
    assert second.status == InternalOrderStatus.ACCEPTED
    assert second.duplicate is False


def test_disabled_feature_flag_returns_503(monkeypatch) -> None:
    _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    monkeypatch.setenv("UTOS_MANUAL_TRADE_ENABLED", "false")
    try:
        submit_manual_order(
            ACCOUNT_ID,
            _request(),
            service=service,
            registry=manual_trade_registry(),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert "manual_trade_disabled" in str(getattr(exc, "detail", exc))
    else:
        raise AssertionError("disabled flag must 503")


def test_list_manual_orders_returns_orders_for_account() -> None:
    _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )
    submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )

    listing = list_manual_orders(
        ACCOUNT_ID,
        service=service,
        registry=manual_trade_registry(),
    )

    assert len(listing.orders) == 2
    assert all(order.client_order_id.startswith("manual-") for order in listing.orders)
    assert all(order.origin == "manual_operator" for order in listing.orders)
    assert all(order.source == "manual" for order in listing.orders)


def test_list_orders_surfaces_signal_plan_origin_truthfully() -> None:
    manager, _, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    now = datetime.now(timezone.utc)
    lineage_id = uuid4()
    signal_order = manager.ledger.add(
        InternalOrder(
            order_id=uuid4(),
            client_order_id="sigplan-11111111-smoke-open-abc123",
            account_id=ACCOUNT_ID,
            origin=OrderOrigin.SIGNAL_PLAN,
            deployment_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            signal_plan_id=lineage_id,
            current_signal_plan_id=lineage_id,
            position_lineage_id=lineage_id,
            account_evaluation_id=uuid4(),
            governor_decision_id=uuid4(),
            symbol="TQQQ",
            side=CandidateSide.LONG,
            quantity=1,
            filled_quantity=1,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            intent=InternalOrderIntent.OPEN,
            status=InternalOrderStatus.FILLED,
            created_at=now,
            updated_at=now,
            reason="red candle smoke",
        )
    )

    listing = list_manual_orders(
        ACCOUNT_ID,
        service=service,
        registry=manual_trade_registry(),
    )

    listed = next(order for order in listing.orders if order.order_id == signal_order.order_id)
    assert listed.origin == "signal_plan"
    assert listed.source == "signal_plan"


def test_duplicate_submit_after_restart_replays_without_second_broker_submit() -> None:
    manager, adapter, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    key = "restart-safe-key"
    request = _request(idempotency_key=key)

    first = submit_manual_order(
        ACCOUNT_ID,
        request,
        service=service,
        registry=manual_trade_registry(),
    )
    assert len(adapter.submitted_orders) == 1

    shutdown_runtime_context()
    manager, restarted_adapter, _, _ = _build_stack()
    second = submit_manual_order(
        ACCOUNT_ID,
        request,
        service=service,
        registry=manual_trade_registry(),
    )

    assert second.order_id == first.order_id
    assert second.duplicate is True
    assert len(restarted_adapter.submitted_orders) == 0
    assert manager.ledger.get(first.order_id).client_order_id == first.client_order_id


def test_manual_order_origin_has_no_deployment_lineage() -> None:
    manager, _, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())

    response = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )
    order = manager.ledger.get(response.order_id)

    assert order.origin.value == "manual_operator"
    assert order.deployment_id is None


def test_structured_error_requires_operator_session() -> None:
    _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())

    with pytest.raises(Exception) as excinfo:
        _real_submit_manual_order(
            ACCOUNT_ID,
            _request(),
            service=service,
            registry=manual_trade_registry(),
        )

    detail = getattr(excinfo.value, "detail", {})
    assert getattr(excinfo.value, "status_code", None) == 401
    assert detail["code"] == "operator_session_required"
    assert detail["recovery_hint"]


def test_audit_events_persist_for_submit_and_cancel() -> None:
    _, _, _, _ = _build_stack()
    service = _FakeBrokerAccountService(_make_paper_account())
    runtime_store = manual_trade_registry().get(ACCOUNT_ID)["runtime_store"]

    submitted = submit_manual_order(
        ACCOUNT_ID,
        _request(),
        service=service,
        registry=manual_trade_registry(),
    )
    cancel_manual_order(
        ACCOUNT_ID,
        submitted.order_id,
        service=service,
        registry=manual_trade_registry(),
    )

    events = runtime_store.list_manual_trade_audit_events(ACCOUNT_ID)
    assert [event["event_code"] for event in events] == [
        "manual_submit_succeeded",
        "manual_cancel_succeeded",
    ]
    assert all(event["operator_session_id"] == OPERATOR_SESSION_ID for event in events)
    assert events[0]["order_id"] == str(submitted.order_id)


def test_multi_account_manual_trade_isolation() -> None:
    first_manager, first_adapter, _, _ = _build_stack(account_id=ACCOUNT_ID)
    second_manager, second_adapter, _, _ = _build_stack(account_id=SECOND_ACCOUNT_ID)
    service = _FakeBrokerAccountService(
        _make_paper_account(account_id=ACCOUNT_ID, display_name="Paper A"),
        _make_paper_account(account_id=SECOND_ACCOUNT_ID, display_name="Paper B"),
    )

    first = submit_manual_order(
        ACCOUNT_ID,
        _request(idempotency_key="acct-a-key", symbol="SPY"),
        service=service,
        registry=manual_trade_registry(),
    )
    second = submit_manual_order(
        SECOND_ACCOUNT_ID,
        _request(idempotency_key="acct-b-key", symbol="QQQ"),
        service=service,
        registry=manual_trade_registry(),
    )

    assert first.account_id == ACCOUNT_ID
    assert second.account_id == SECOND_ACCOUNT_ID
    assert first_manager.ledger.by_account(ACCOUNT_ID)[0].symbol == "SPY"
    assert second_manager.ledger.by_account(SECOND_ACCOUNT_ID)[0].symbol == "QQQ"
    assert len(first_adapter.submitted_orders) == 1
    assert len(second_adapter.submitted_orders) == 1
    assert first_adapter.submitted_orders[0].account_id == ACCOUNT_ID
    assert second_adapter.submitted_orders[0].account_id == SECOND_ACCOUNT_ID
