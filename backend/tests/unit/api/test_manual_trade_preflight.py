from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException

from backend.app.api.routes.manual_trade import ManualOrderRequest, submit_manual_order
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import BrokerAccountSnapshot, BrokerSync
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.orders import OrderManager


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


class FakeBrokerAccountService:
    def __init__(self, account: BrokerAccount) -> None:
        self._account = account

    def list_broker_accounts(self) -> tuple[BrokerAccount, ...]:
        return (self._account,)


class RejectIfSubmittedAdapter:
    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )

    def submit_order(self, order):  # type: ignore[no-untyped-def]
        _ = order
        raise AssertionError("manual preflight rejection must happen before broker submit")


class FakeRegistry:
    def __init__(self, entry: dict) -> None:
        self._entry = entry

    def get(self, account_id: UUID):  # type: ignore[no-untyped-def]
        return self._entry if account_id == ACCOUNT_ID else None


class FakeRuntimeStore:
    def __init__(self) -> None:
        self.released_keys: list[str] = []
        self.audit_events: list[dict] = []

    def reserve_manual_idempotency_key(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        return "reserved"

    def release_manual_idempotency_key(self, *, account_id: UUID, idempotency_key: str) -> None:
        _ = account_id
        self.released_keys.append(idempotency_key)

    def commit_manual_idempotency_key(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        raise AssertionError("rejected preflight must not commit idempotency")

    def record_manual_trade_audit_event(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.audit_events.append(kwargs)


def test_manual_trade_preflight_blocks_limit_without_limit_price_before_submit() -> None:
    account = BrokerAccount(
        id=ACCOUNT_ID,
        display_name="Paper",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        external_account_id="alpaca-paper-1",
        credentials_ref="alpaca-paper-ref",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    manager = OrderManager()
    sync = BrokerSync(ledger=manager.ledger)
    manager._broker_sync = sync
    runtime_store = FakeRuntimeStore()
    registry = FakeRegistry(
        {
            "order_manager": manager,
            "broker_adapter": RejectIfSubmittedAdapter(),
            "broker_sync_service": object(),
            "runtime_store": runtime_store,
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        submit_manual_order(
            ACCOUNT_ID,
            ManualOrderRequest(
                symbol="SPY",
                side=CandidateSide.LONG,
                qty=1,
                order_type=OrderType.LIMIT,
                time_in_force=TimeInForce.DAY,
                reason="operator limit smoke",
                idempotency_key="manual-preflight-1",
            ),
            service=FakeBrokerAccountService(account),
            registry=registry,
            runtime_store=runtime_store,
            operator_session_id="operator-session",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "broker_preflight_rejected"
    assert runtime_store.released_keys == ["manual-preflight-1"]
    assert manager.ledger.all()[0].status.value == "rejected"
