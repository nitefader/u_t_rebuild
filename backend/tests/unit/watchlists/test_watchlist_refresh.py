from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.watchlists import WatchlistKind, WatchlistService, WatchlistServiceError, WatchlistWriteRequest
from backend.app.watchlists.models import Watchlist, WatchlistDynamicRules
from backend.app.watchlists.persistence import WatchlistRepository


@dataclass(frozen=True)
class _Resolution:
    symbols: tuple[str, ...]
    note: str | None
    source_run_id: UUID | None
    source_label: str | None
    evidence: dict[str, object]


class _Resolver:
    def __init__(self) -> None:
        self.symbols = ("AAPL", "MSFT")
        self.run_id = uuid4()

    def refresh(self, watchlist: Watchlist) -> _Resolution:  # noqa: D401, ARG002
        return _Resolution(
            symbols=self.symbols,
            note="Refreshed from Screener run",
            source_run_id=self.run_id,
            source_label="Screener refresh: Fractionable Momentum",
            evidence={"source_type": "screener_version", "matched_count": len(self.symbols)},
        )


class _References:
    def __init__(self, names: tuple[str, ...]) -> None:
        self.names = names

    def active_deployment_names_for_watchlist(self, watchlist_id: UUID) -> tuple[str, ...]:  # noqa: D401, ARG002
        return self.names


def _service(
    tmp_path: Path,
    *,
    resolver: _Resolver | None = None,
    refs: tuple[str, ...] = (),
) -> WatchlistService:
    return WatchlistService(
        repository=WatchlistRepository(tmp_path / "watchlists.db"),
        dynamic_resolver=resolver,
        reference_lookup=_References(refs),
    )


def test_dynamic_watchlist_refresh_creates_snapshot_with_diff_and_evidence(tmp_path: Path) -> None:
    resolver = _Resolver()
    service = _service(tmp_path, resolver=resolver)
    watchlist = service.create_watchlist(
        WatchlistWriteRequest(
            name="Fractionable Momentum",
            kind=WatchlistKind.DYNAMIC,
            static_symbols=("AAPL",),
            dynamic_rules=WatchlistDynamicRules(
                source_type="screener_version",
                screener_id=uuid4(),
                screener_version_id=uuid4(),
            ),
        )
    )

    first = service.take_snapshot(watchlist.watchlist_id)
    resolver.symbols = ("AAPL", "NVDA")
    second = service.take_snapshot(watchlist.watchlist_id)

    assert first.symbols == ("AAPL", "MSFT")
    assert first.source_run_id == resolver.run_id
    assert first.added_symbols == ("AAPL", "MSFT")
    assert second.added_symbols == ("NVDA",)
    assert second.removed_symbols == ("MSFT",)
    assert second.stayed_symbols == ("AAPL",)
    assert second.evidence["source_type"] == "screener_version"


def test_dynamic_watchlist_without_resolver_fails_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    watchlist = service.create_watchlist(
        WatchlistWriteRequest(
            name="Dynamic",
            kind=WatchlistKind.DYNAMIC,
            dynamic_rules=WatchlistDynamicRules(source_type="screener_version"),
        )
    )

    with pytest.raises(WatchlistServiceError):
        service.take_snapshot(watchlist.watchlist_id)


def test_delete_blocks_snapshot_history_and_archive_blocks_active_deployments(tmp_path: Path) -> None:
    service = _service(tmp_path, resolver=_Resolver())
    watchlist = service.create_watchlist(
        WatchlistWriteRequest(name="Static", static_symbols=("AAPL",))
    )
    service.take_snapshot(watchlist.watchlist_id)

    with pytest.raises(WatchlistServiceError, match="snapshot history"):
        service.delete_watchlist(watchlist.watchlist_id)

    referenced = _service(tmp_path / "refs", refs=("Mean Reversion Deployment",))
    active = referenced.create_watchlist(
        WatchlistWriteRequest(name="Active", static_symbols=("MSFT",))
    )
    with pytest.raises(WatchlistServiceError, match="Mean Reversion Deployment"):
        referenced.archive_watchlist(active.watchlist_id)
