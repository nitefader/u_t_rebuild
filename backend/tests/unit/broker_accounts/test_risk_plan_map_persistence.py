"""Unit tests for AccountRiskPlanMap persistence.

Tests cover:
- CRUD round-trip: save, load, delete for map entries
- UNIQUE (account_id, horizon) constraint: second upsert replaces first
- load_account_risk_plan_map returns empty map when no rows exist (never raises)
- load_risk_plan_config_for_horizon joins through to RiskPlanVersion.config
- load_risk_plan_config_for_horizon returns None when no map row exists
- load_risk_plan_config_for_horizon returns None when RiskPlanVersion no longer exists
- CASCADE delete: deleting broker account cascades to map rows
- Multiple horizons per account are independent
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.broker_accounts.risk_plan_map_models import (
    AccountRiskPlanMap,
    AccountRiskPlanMapEntry,
)
from backend.app.domain import TradingMode
from backend.app.domain.risk_plan import (
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSizingMethod,
    RiskPlanSource,
    RiskPlanStatus,
    RiskPlanTier,
    RiskPlanVersion,
    RiskPlanVersionStatus,
)
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.persistence import SQLiteRuntimeStore


ACCOUNT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ACCOUNT_ID_2 = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PLAN_ID = UUID("11111111-1111-1111-1111-111111111111")
VERSION_ID = UUID("22222222-2222-2222-2222-222222222222")
VERSION_ID_2 = UUID("33333333-3333-3333-3333-333333333333")


def _make_store(tmp_path) -> SQLiteRuntimeStore:
    return SQLiteRuntimeStore(tmp_path / "runtime.db")


def _make_broker_account(account_id: UUID = ACCOUNT_ID) -> BrokerAccount:
    return BrokerAccount(
        id=account_id,
        display_name="Test Account",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref=f"alpaca-paper:{account_id}:ref",
        validation_status=BrokerAccountValidationStatus.VALID,
    )


def _make_risk_plan_version(
    version_id: UUID = VERSION_ID,
    plan_id: UUID = PLAN_ID,
    *,
    max_open_positions: int | None = 3,
    max_gross_exposure_pct: float | None = 50.0,
) -> RiskPlanVersion:
    config = RiskPlanConfig(
        sizing_method=RiskPlanSizingMethod.RISK_PERCENT,
        risk_per_trade_pct=1.0,
        max_open_positions=max_open_positions,
        max_gross_exposure_pct=max_gross_exposure_pct,
    )
    return RiskPlanVersion(
        risk_plan_version_id=version_id,
        risk_plan_id=plan_id,
        version=1,
        status=RiskPlanVersionStatus.ACTIVE,
        config=config,
        config_fingerprint="test-fp",
        created_at=datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
        activated_at=datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
    )


def _make_risk_plan(plan_id: UUID = PLAN_ID) -> RiskPlan:
    return RiskPlan(
        risk_plan_id=plan_id,
        name="Test Plan",
        status=RiskPlanStatus.ACTIVE,
        risk_tier=RiskPlanTier.BALANCED,
        risk_score=5,
        source=RiskPlanSource.MANUAL,
        created_at=datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# load_account_risk_plan_map — empty map when no rows
# ---------------------------------------------------------------------------


def test_load_map_returns_empty_when_no_rows(tmp_path) -> None:
    store = _make_store(tmp_path)
    result = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert isinstance(result, AccountRiskPlanMap)
    assert result.account_id == ACCOUNT_ID
    assert result.entries == ()


# ---------------------------------------------------------------------------
# save → load round-trip
# ---------------------------------------------------------------------------


def test_save_and_load_single_entry(tmp_path) -> None:
    store = _make_store(tmp_path)
    entry = store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)

    assert isinstance(entry, AccountRiskPlanMapEntry)
    assert entry.account_id == ACCOUNT_ID
    assert entry.horizon == TradingHorizon.INTRADAY
    assert entry.risk_plan_version_id == VERSION_ID

    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].horizon == TradingHorizon.INTRADAY
    assert loaded.entries[0].risk_plan_version_id == VERSION_ID


def test_multiple_horizons_per_account_are_independent(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.SWING, VERSION_ID_2)

    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert len(loaded.entries) == 2
    horizons = {e.horizon for e in loaded.entries}
    assert horizons == {TradingHorizon.INTRADAY, TradingHorizon.SWING}


def test_all_five_horizons_save_independently(tmp_path) -> None:
    store = _make_store(tmp_path)
    for horizon in TradingHorizon:
        store.save_account_risk_plan_map_entry(ACCOUNT_ID, horizon, uuid4())

    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert len(loaded.entries) == len(TradingHorizon)


# ---------------------------------------------------------------------------
# UNIQUE (account_id, horizon) — upsert replaces
# ---------------------------------------------------------------------------


def test_upsert_replaces_existing_entry(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID_2)

    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].risk_plan_version_id == VERSION_ID_2


# ---------------------------------------------------------------------------
# delete entry
# ---------------------------------------------------------------------------


def test_delete_entry_removes_one_horizon(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.SWING, VERSION_ID_2)

    store.delete_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY)

    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert len(loaded.entries) == 1
    assert loaded.entries[0].horizon == TradingHorizon.SWING


def test_delete_entry_noop_when_no_row(tmp_path) -> None:
    store = _make_store(tmp_path)
    # Must not raise when the row does not exist.
    store.delete_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY)
    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert loaded.entries == ()


# ---------------------------------------------------------------------------
# load_risk_plan_config_for_horizon — the join path
# ---------------------------------------------------------------------------


def test_load_risk_plan_config_returns_none_when_no_map_row(tmp_path) -> None:
    store = _make_store(tmp_path)
    result = store.load_risk_plan_config_for_horizon(ACCOUNT_ID, TradingHorizon.INTRADAY)
    assert result is None


def test_load_risk_plan_config_returns_config_when_version_exists(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_risk_plan(_make_risk_plan())
    store.save_risk_plan_version(_make_risk_plan_version(max_open_positions=5, max_gross_exposure_pct=80.0))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.SWING, VERSION_ID)

    config = store.load_risk_plan_config_for_horizon(ACCOUNT_ID, TradingHorizon.SWING)

    assert config is not None
    assert isinstance(config, RiskPlanConfig)
    assert config.max_open_positions == 5
    assert config.max_gross_exposure_pct == 80.0


def test_load_risk_plan_config_returns_none_when_version_no_longer_exists(tmp_path) -> None:
    # Map row points to a version that was never saved (or was deleted).
    store = _make_store(tmp_path)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, UUID("deadbeef-dead-dead-dead-deaddeadbeef"))

    result = store.load_risk_plan_config_for_horizon(ACCOUNT_ID, TradingHorizon.INTRADAY)
    assert result is None


def test_load_risk_plan_config_horizon_isolation(tmp_path) -> None:
    """Intraday vs Swing return different configs when both mapped."""
    store = _make_store(tmp_path)
    plan_id_2 = uuid4()
    store.save_risk_plan(_make_risk_plan())
    store.save_risk_plan(_make_risk_plan(plan_id_2))
    store.save_risk_plan_version(_make_risk_plan_version(max_open_positions=2))
    store.save_risk_plan_version(
        RiskPlanVersion(
            risk_plan_version_id=VERSION_ID_2,
            risk_plan_id=plan_id_2,
            version=1,
            status=RiskPlanVersionStatus.ACTIVE,
            config=RiskPlanConfig(
                sizing_method=RiskPlanSizingMethod.RISK_PERCENT,
                risk_per_trade_pct=1.0,
                max_open_positions=10,
            ),
            config_fingerprint="fp-2",
            created_at=datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
            activated_at=datetime(2026, 4, 29, 18, 0, tzinfo=timezone.utc),
        )
    )
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.SWING, VERSION_ID_2)

    intraday_config = store.load_risk_plan_config_for_horizon(ACCOUNT_ID, TradingHorizon.INTRADAY)
    swing_config = store.load_risk_plan_config_for_horizon(ACCOUNT_ID, TradingHorizon.SWING)

    assert intraday_config is not None
    assert swing_config is not None
    assert intraday_config.max_open_positions == 2
    assert swing_config.max_open_positions == 10


# ---------------------------------------------------------------------------
# CASCADE delete: broker account deletion cascades to map rows
# ---------------------------------------------------------------------------


def test_broker_account_deletion_cascades_to_map_rows(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_broker_account(_make_broker_account())
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.SWING, VERSION_ID_2)

    store.delete_broker_account(ACCOUNT_ID)

    # Map rows must be gone.
    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert loaded.entries == ()


def test_cascade_delete_does_not_affect_other_accounts(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_broker_account(_make_broker_account(ACCOUNT_ID))
    store.save_broker_account(_make_broker_account(ACCOUNT_ID_2))
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.INTRADAY, VERSION_ID)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID_2, TradingHorizon.SWING, VERSION_ID_2)

    store.delete_broker_account(ACCOUNT_ID)

    loaded_2 = store.load_account_risk_plan_map(ACCOUNT_ID_2)
    assert len(loaded_2.entries) == 1
    assert loaded_2.entries[0].account_id == ACCOUNT_ID_2


# ---------------------------------------------------------------------------
# OTHER horizon vocabulary
# ---------------------------------------------------------------------------


def test_other_horizon_saves_and_loads_correctly(tmp_path) -> None:
    store = _make_store(tmp_path)
    store.save_account_risk_plan_map_entry(ACCOUNT_ID, TradingHorizon.OTHER, VERSION_ID)
    loaded = store.load_account_risk_plan_map(ACCOUNT_ID)
    assert any(e.horizon == TradingHorizon.OTHER for e in loaded.entries)
