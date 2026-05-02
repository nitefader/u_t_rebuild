"""M10: BrokerErrorEvent taxonomy + client_order_id audit log tests.

Tests:
1. BrokerErrorEvent model validates all required fields for each family.
2. BrokerSync.apply_result emits structured audit log with expected fields.
3. BrokerSyncService.reconcile emits BrokerErrorEvent on adapter failure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerErrorEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.orders.ledger import OrderLedger as InMemoryOrderLedger
from backend.tests.fixtures.modern_order import make_signal_plan_order


ACCOUNT_ID = UUID("11111111-2222-3333-4444-999999999999")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-222222222222")


# ---------------------------------------------------------------------------
# BrokerErrorEvent model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    ["preflight", "submit", "stream", "reconcile", "credentials"],
)
def test_broker_error_event_all_families_validate(family: str) -> None:
    """Each Playbook §17 family produces a structurally valid BrokerErrorEvent."""
    event = BrokerErrorEvent(
        family=family,
        severity="error",
        source="test_source",
        operator_advisory="Investigate the issue and retry.",
        account_id=ACCOUNT_ID,
    )
    assert event.family == family
    assert event.severity == "error"
    assert event.source == "test_source"
    assert event.operator_advisory == "Investigate the issue and retry."
    assert event.account_id == ACCOUNT_ID
    assert event.occurred_at is not None


def test_broker_error_event_optional_fields_default_none() -> None:
    event = BrokerErrorEvent(
        family="submit",
        severity="warning",
        source="alpaca_adapter",
        operator_advisory="Retry with a valid order.",
    )
    assert event.raw_broker_code is None
    assert event.raw_broker_message is None
    assert event.account_id is None
    assert event.symbol is None


def test_broker_error_event_invalid_family_raises() -> None:
    with pytest.raises(Exception):
        BrokerErrorEvent(
            family="unknown_family",  # type: ignore[arg-type]
            severity="error",
            source="test",
            operator_advisory="N/A",
        )


def test_broker_error_event_invalid_severity_raises() -> None:
    with pytest.raises(Exception):
        BrokerErrorEvent(
            family="submit",
            severity="verbose",  # type: ignore[arg-type]
            source="test",
            operator_advisory="N/A",
        )


# ---------------------------------------------------------------------------
# BrokerSync.apply_result audit log
# ---------------------------------------------------------------------------


def _make_open_order_via_manager() -> tuple[InternalOrder, InMemoryOrderLedger]:
    """Create a valid SIGNAL_PLAN InternalOrder using the canonical factory path."""
    manager = OrderManager()
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)
    return order, manager.ledger  # type: ignore[return-value]


def test_apply_result_emits_audit_log(caplog: pytest.LogCaptureFixture) -> None:
    """BrokerSync.apply_result logs structured client_order_id mapping."""
    order, ledger = _make_open_order_via_manager()
    broker_sync = BrokerSync(ledger=ledger, provider="alpaca")  # type: ignore[arg-type]

    result = BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.ACCEPTED,
        broker_order_id="broker-xyz-001",
    )

    with caplog.at_level(logging.INFO, logger="backend.app.brokers.sync"):
        broker_sync.apply_result(result)

    audit_records = [r for r in caplog.records if "broker_sync_apply_result" in r.getMessage()]
    assert len(audit_records) >= 1, f"Expected audit log; got records: {[r.getMessage() for r in caplog.records]}"

    record = audit_records[0]
    # Verify all required fields are present in the extra dict.
    assert hasattr(record, "internal_order_id"), "Missing internal_order_id in audit log"
    assert hasattr(record, "client_order_id"), "Missing client_order_id in audit log"
    assert hasattr(record, "broker_order_id"), "Missing broker_order_id in audit log"
    assert hasattr(record, "broker_status"), "Missing broker_status in audit log"
    assert hasattr(record, "provider"), "Missing provider in audit log"

    assert record.internal_order_id == str(order.order_id)  # type: ignore[attr-defined]
    assert record.client_order_id == order.client_order_id  # type: ignore[attr-defined]
    assert record.broker_order_id == "broker-xyz-001"  # type: ignore[attr-defined]
    assert record.provider == "alpaca"  # type: ignore[attr-defined]


def test_apply_result_audit_log_maps_broker_order_id_none(caplog: pytest.LogCaptureFixture) -> None:
    """audit log works when broker_order_id is None (not-yet-confirmed order)."""
    order, ledger = _make_open_order_via_manager()
    broker_sync = BrokerSync(ledger=ledger, provider="fake")  # type: ignore[arg-type]

    result = BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.ACCEPTED,
        broker_order_id=None,
    )

    with caplog.at_level(logging.INFO, logger="backend.app.brokers.sync"):
        broker_sync.apply_result(result)

    audit_records = [r for r in caplog.records if "broker_sync_apply_result" in r.getMessage()]
    assert len(audit_records) >= 1
    assert audit_records[0].broker_order_id is None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# BrokerSyncService.reconcile emits BrokerErrorEvent on adapter failure
# ---------------------------------------------------------------------------


class _FailingAdapter:
    """Adapter that always fails get_order so reconcile hits the error path."""

    provider = "fake"

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        raise BrokerAdapterError("order not found at broker")

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        return ()

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return ()

    def cancel_order(self, order: InternalOrder) -> BrokerOrderResult:
        raise BrokerAdapterError("cancel not supported")

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        raise BrokerAdapterError("submit not supported")


def test_reconcile_emits_broker_error_event_on_adapter_failure(caplog: pytest.LogCaptureFixture) -> None:
    """BrokerSyncService.reconcile logs a BrokerErrorEvent when get_order fails."""
    order, ledger = _make_open_order_via_manager()

    adapter = _FailingAdapter()
    broker_sync = BrokerSync(ledger=ledger)
    service = BrokerSyncService(
        adapter=adapter,  # type: ignore[arg-type]
        broker_sync=broker_sync,
        order_ledger=ledger,
        max_stale_seconds=300,
    )

    with caplog.at_level(logging.WARNING, logger="backend.app.brokers.sync"):
        report = service.reconcile(ACCOUNT_ID)

    assert report.has_issues, "Reconcile should report issues when get_order fails"
    from backend.app.brokers.models import BrokerReconciliationIssueType
    missing_issues = [
        i for i in report.issues
        if i.issue_type == BrokerReconciliationIssueType.MISSING_BROKER_ORDER
    ]
    assert len(missing_issues) >= 1

    # Verify structured BrokerErrorEvent was logged.
    error_records = [r for r in caplog.records if "broker_sync_reconcile_error" in r.getMessage()]
    assert len(error_records) >= 1, (
        f"Expected structured reconcile error log; got: {[r.getMessage() for r in caplog.records]}"
    )
    # The event dict should contain family=reconcile.
    record = error_records[0]
    assert hasattr(record, "event"), "Missing event dict in reconcile error log"
    event_dict = record.event  # type: ignore[attr-defined]
    assert event_dict["family"] == "reconcile"
    assert event_dict["severity"] == "warning"
    assert event_dict["source"] == "broker_sync"
