"""Broker adapter boundary contracts.

No real broker implementation lives here yet.
"""

from .adapter import BrokerAdapter
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
