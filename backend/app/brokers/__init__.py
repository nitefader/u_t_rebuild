"""Broker adapter boundary contracts.

No real broker implementation lives here yet.
"""

from .adapter import BrokerAdapter
from .fake import FakeBrokerAdapter
from .models import BrokerAdapterError, BrokerOrderResult, BrokerOrderStatus
from .sync import BrokerSync

__all__ = [
    "BrokerAdapter",
    "BrokerAdapterError",
    "BrokerOrderResult",
    "BrokerOrderStatus",
    "BrokerSync",
    "FakeBrokerAdapter",
]
