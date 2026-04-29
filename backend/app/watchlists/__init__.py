"""Watchlist CRUD package.

Watchlists are the eligible-symbol source for Deployment entries.
Static watchlists are an explicit symbol list; dynamic watchlists
carry a JSON-encoded rules block evaluated at snapshot time. Both
forms produce ``WatchlistSnapshot`` records that the runtime spine
consumes.

Doctrine: this package does NOT introduce a runtime root, does NOT
mutate broker truth.
"""

from .models import (
    Watchlist,
    WatchlistKind,
    WatchlistListResponse,
    WatchlistResponse,
    WatchlistSnapshot,
    WatchlistWriteRequest,
)
from .service import WatchlistService, WatchlistServiceError

__all__ = [
    "Watchlist",
    "WatchlistKind",
    "WatchlistListResponse",
    "WatchlistResponse",
    "WatchlistService",
    "WatchlistServiceError",
    "WatchlistSnapshot",
    "WatchlistWriteRequest",
]
