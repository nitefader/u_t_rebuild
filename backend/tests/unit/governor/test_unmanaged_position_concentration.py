"""M2 Governor concentration include — unmanaged broker positions count.

Pins that ``PortfolioSnapshot`` aggregates managed + unmanaged
positions into:
- ``open_position_count()``
- ``symbol_market_value(symbol)``
- ``gross_market_value()``
- ``net_market_value()``

so per-Account caps (max_open_positions, max_symbol_concentration_pct,
max_gross_exposure_pct, max_net_exposure_pct) cannot be silently
bypassed by manual or unknown-origin broker positions.

Doctrine: HARD.MD P0-2 + Playbook §15. Adoption itself stays explicit
and gated; this slice only ensures Governor *sees* the exposure.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from backend.app.governor import (
    PortfolioSnapshot,
    PositionSummary,
    UnmanagedPositionSummary,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-1111-2222-3333-444444444444")


def _managed(symbol: str = "SPY", qty: float = 10, mv: float = 1000) -> PositionSummary:
    return PositionSummary(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        symbol=symbol,
        quantity=qty,
        market_value=mv,
    )


def _unmanaged(symbol: str = "SPY", qty: float = 5, mv: float = 500) -> UnmanagedPositionSummary:
    return UnmanagedPositionSummary(
        account_id=ACCOUNT_ID,
        symbol=symbol,
        quantity=qty,
        market_value=mv,
    )


def test_open_position_count_aggregates_managed_and_unmanaged() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10), _managed("MSFT", qty=5)),
        unmanaged_positions=(_unmanaged("AAPL", qty=3),),
    )
    assert snap.open_position_count() == 3


def test_open_position_count_skips_zero_quantity_in_both_buckets() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=0),),
        unmanaged_positions=(_unmanaged("AAPL", qty=0),),
    )
    assert snap.open_position_count() == 0


def test_symbol_market_value_includes_unmanaged_for_same_symbol() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10, mv=1000),),
        unmanaged_positions=(_unmanaged("SPY", qty=5, mv=500),),
    )
    # Should be |1000| + |500| = 1500.
    assert snap.symbol_market_value("SPY") == 1500


def test_symbol_market_value_filters_other_symbols() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10, mv=1000),),
        unmanaged_positions=(_unmanaged("AAPL", qty=5, mv=500),),
    )
    assert snap.symbol_market_value("SPY") == 1000
    assert snap.symbol_market_value("AAPL") == 500
    assert snap.symbol_market_value("MSFT") == 0


def test_gross_market_value_sums_absolute_managed_and_unmanaged() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10, mv=1000), _managed("MSFT", qty=-5, mv=-500)),
        unmanaged_positions=(_unmanaged("AAPL", qty=3, mv=300),),
    )
    # |1000| + |-500| + |300| = 1800.
    assert snap.gross_market_value() == 1800


def test_net_market_value_sums_signed_managed_and_unmanaged() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10, mv=1000), _managed("MSFT", qty=-5, mv=-500)),
        unmanaged_positions=(_unmanaged("AAPL", qty=3, mv=300),),
    )
    # 1000 + -500 + 300 = 800.
    assert snap.net_market_value() == 800


def test_unmanaged_position_count_helper_is_distinct() -> None:
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10),),
        unmanaged_positions=(_unmanaged("AAPL", qty=3), _unmanaged("MSFT", qty=2)),
    )
    assert snap.unmanaged_position_count() == 2
    assert snap.unmanaged_gross_market_value() == _unmanaged("AAPL", qty=3, mv=500).market_value + _unmanaged(
        "MSFT", qty=2, mv=500
    ).market_value


def test_open_risk_excludes_unmanaged_positions_by_design() -> None:
    """Unmanaged positions have no risk_resolver lineage so open_risk is N/A.

    The existing open_risk() helper sums only the managed positions.
    Concentration / exposure caps still see them; risk-percent caps do not.
    """
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="SPY",
                quantity=10,
                market_value=1000,
                open_risk=100,
            ),
        ),
        unmanaged_positions=(_unmanaged("AAPL", qty=3, mv=300),),
    )
    assert snap.open_risk() == 100


def test_default_unmanaged_positions_is_empty_tuple() -> None:
    snap = PortfolioSnapshot(equity=10_000)
    assert snap.unmanaged_positions == ()
    assert snap.unmanaged_position_count() == 0
    assert snap.unmanaged_gross_market_value() == 0


def test_back_compat_only_managed_positions_unchanged() -> None:
    """When unmanaged_positions is omitted, all aggregates match the
    pre-M2 behavior — back-compat for callers that haven't started
    populating the new field yet."""
    snap = PortfolioSnapshot(
        equity=10_000,
        positions=(_managed("SPY", qty=10, mv=1000),),
    )
    assert snap.open_position_count() == 1
    assert snap.symbol_market_value("SPY") == 1000
    assert snap.gross_market_value() == 1000
    assert snap.net_market_value() == 1000
