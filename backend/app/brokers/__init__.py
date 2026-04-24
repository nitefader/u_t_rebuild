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
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionDelta,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerReconciliationIssue,
    BrokerReconciliationIssueType,
    BrokerReconciliationReport,
    BrokerSyncState,
)
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
    "BrokerOpenOrderSnapshot",
    "BrokerOrderMapping",
    "BrokerOrderResult",
    "BrokerOrderStatus",
    "BrokerPositionDelta",
    "BrokerPositionSide",
    "BrokerPositionSnapshot",
    "BrokerReconciliationIssue",
    "BrokerReconciliationIssueType",
    "BrokerReconciliationReport",
    "BrokerSync",
    "BrokerSyncService",
    "BrokerSyncState",
    "FakeBrokerAdapter",
]
