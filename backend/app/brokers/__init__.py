"""Broker adapter boundary contracts.

No real broker implementation lives here yet.
"""

from .adapter import BrokerAdapter
from .alpaca import AlpacaBrokerAdapter, AlpacaBrokerCapabilities, AlpacaBrokerError, AlpacaBrokerErrorDetails
from .fake import FakeBrokerAdapter
from .models import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionDelta,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerReconciliationIssue,
    BrokerReconciliationIssueType,
    BrokerReconciliationReport,
    BrokerSyncState,
)
from .stream import AlpacaAccountStreamAdapter, BrokerStreamEvent
from .sync import BrokerSync, BrokerSyncService

__all__ = [
    "AlpacaBrokerAdapter",
    "AlpacaBrokerCapabilities",
    "AlpacaBrokerError",
    "AlpacaBrokerErrorDetails",
    "BrokerAccountMode",
    "BrokerAccountSnapshot",
    "BrokerAdapter",
    "BrokerAdapterError",
    "AlpacaAccountStreamAdapter",
    "BrokerFillUpdateEvent",
    "BrokerOpenOrderSnapshot",
    "BrokerOrderMapping",
    "BrokerOrderResult",
    "BrokerOrderStatus",
    "BrokerOrderUpdateEvent",
    "BrokerPositionDelta",
    "BrokerPositionSide",
    "BrokerPositionSnapshot",
    "BrokerReconciliationIssue",
    "BrokerReconciliationIssueType",
    "BrokerReconciliationReport",
    "BrokerSync",
    "BrokerSyncService",
    "BrokerSyncState",
    "BrokerStreamEvent",
    "FakeBrokerAdapter",
]
