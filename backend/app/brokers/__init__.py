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
    BrokerOrderMapping,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from .sync import BrokerSync

__all__ = [
    "AlpacaBrokerAdapter",
    "AlpacaBrokerCapabilities",
    "AlpacaBrokerError",
    "AlpacaBrokerErrorDetails",
    "BrokerAccountMode",
    "BrokerAccountSnapshot",
    "BrokerAdapter",
    "BrokerAdapterError",
    "BrokerOrderMapping",
    "BrokerOrderResult",
    "BrokerOrderStatus",
    "BrokerPositionSide",
    "BrokerPositionSnapshot",
    "BrokerSync",
    "FakeBrokerAdapter",
]
