"""Pin the unified broker-accounts route contract.

Per the no-fork rule: ONE create endpoint and ONE replace-credentials
endpoint, both parametrized over (provider, mode). Paper-specific URL
suffixes (e.g. ``/alpaca-paper``) are deleted, and the request shape
takes ``provider`` + ``mode`` as fields.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from backend.app.api.routes import broker_accounts
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.broker_accounts.models import (
    AccountRestrictions,
    AccountRiskConfig,
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountCredentialValidationStatus,
    BrokerAccountDeletionResponse,
    BrokerAccountDeletionStatus,
    UpdateBrokerAccountDetailsRequest,
)
from backend.app.broker_accounts.risk_plan_map_models import (
    AccountRiskPlanMap,
    AccountRiskPlanMapUpdateRequest,
)
from backend.app.domain.strategy_controls import TradingHorizon
from backend.app.broker_accounts.service import BrokerAccountCreationResult
from backend.app.domain import TradingMode
from backend.app.persistence import SQLiteRuntimeStore


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


class RecordingBrokerAccountService:
    def __init__(self) -> None:
        self.calls = []

    def create_account(
        self, *, display_name: str, provider: str, mode: TradingMode, api_key: str, api_secret: str
    ) -> BrokerAccountCreationResult:
        self.calls.append((display_name, provider, mode, api_key, api_secret))
        return BrokerAccountCreationResult(
            account=BrokerAccount(
                id=ACCOUNT_ID,
                display_name=display_name,
                provider=provider,
                mode=mode,
                external_account_id=f"{provider}-{mode.value.lower()}-account-1",
                credentials_ref=f"{provider}-{mode.value.lower()}:{ACCOUNT_ID}:abcdef",
                validation_status=BrokerAccountValidationStatus.VALID,
            ),
            already_exists=True,
        )

    def replace_credentials(
        self, *, account_id: UUID, api_key: str, api_secret: str
    ) -> BrokerAccountCredentialUpdateResponse:
        self.calls.append(("replace", account_id, api_key, api_secret))
        return BrokerAccountCredentialUpdateResponse(
            account=None,
            validation_status=BrokerAccountCredentialValidationStatus.VALID,
            message="ok",
        )

    def delete_or_archive_account(
        self, *, account_id: UUID, confirm_display_name: str, confirm_mode: TradingMode
    ) -> BrokerAccountDeletionResponse:
        self.calls.append(("delete", account_id, confirm_display_name, confirm_mode))
        return BrokerAccountDeletionResponse(
            account_id=account_id,
            status=BrokerAccountDeletionStatus.HARD_DELETED,
            message="deleted",
        )

    def update_account_details(self, *, account_id: UUID, display_name: str) -> BrokerAccount:
        self.calls.append(("details", account_id, display_name))
        return BrokerAccount(
            id=account_id,
            display_name=display_name,
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            external_account_id="ext-1",
            credentials_ref="alpaca-broker_paper:ref",
            validation_status=BrokerAccountValidationStatus.VALID,
        )


class RuntimeStoreBackedService:
    def __init__(self, store: SQLiteRuntimeStore) -> None:
        self._runtime_store = store


def test_broker_account_routes_registered_with_unified_paths() -> None:
    registered = {(route.method, route.path): route.response_model for route in broker_accounts.router.routes}

    assert registered[("POST", "/api/v1/broker-accounts")] is broker_accounts.BrokerAccountResponse
    assert registered[("PATCH", "/api/v1/broker-accounts/{account_id}")] is broker_accounts.BrokerAccountResponse
    assert registered[("PUT", "/api/v1/broker-accounts/{account_id}/credentials")] is BrokerAccountCredentialUpdateResponse
    assert registered[("POST", "/api/v1/broker-accounts/{account_id}/delete")] is BrokerAccountDeletionResponse
    assert registered[("GET", "/api/v1/broker-accounts/{account_id}/risk-config")] is AccountRiskConfig
    assert registered[("PUT", "/api/v1/broker-accounts/{account_id}/risk-config")] is AccountRiskConfig
    assert registered[("GET", "/api/v1/broker-accounts/{account_id}/restrictions")] is AccountRestrictions
    assert registered[("PUT", "/api/v1/broker-accounts/{account_id}/restrictions")] is AccountRestrictions
    # Paper-specific URLs must not exist.
    assert ("POST", "/api/v1/broker-accounts/alpaca-paper") not in registered
    assert ("PUT", "/api/v1/broker-accounts/{account_id}/alpaca-paper/credentials") not in registered


@pytest.mark.parametrize("mode", [TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE])
def test_create_route_delegates_with_provider_and_mode(mode: TradingMode) -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.CreateBrokerAccountRequest(
        display_name=f"acct-{mode.value}",
        provider="alpaca",
        mode=mode,
        api_key="key",
        api_secret="secret",
    )

    response = broker_accounts.create_broker_account(request, service=service)

    assert response.account.id == ACCOUNT_ID
    assert response.account.provider == "alpaca"
    assert response.account.mode == mode
    assert response.already_exists is True
    assert service.calls == [(f"acct-{mode.value}", "alpaca", mode, "key", "secret")]


def test_create_route_wires_broker_sync_before_starting_trade_stream(monkeypatch) -> None:
    calls: list[str] = []
    service = RecordingBrokerAccountService()
    request = broker_accounts.CreateBrokerAccountRequest(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="key",
        api_secret="secret",
    )

    monkeypatch.setattr(
        broker_accounts,
        "_ensure_manual_trade_composition_for_account",
        lambda service, account: calls.append("manual_sync"),
    )
    monkeypatch.setattr(
        broker_accounts,
        "_ensure_trade_stream_started",
        lambda service, account, *, restart=False: calls.append("trade_stream"),
    )

    broker_accounts.create_broker_account(request, service=service)

    assert calls == ["manual_sync", "trade_stream"]


def test_create_request_rejects_unknown_fields() -> None:
    try:
        broker_accounts.CreateBrokerAccountRequest(
            display_name="x",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            api_key="K",
            api_secret="S",
            base_url="https://example.invalid",
        )
    except Exception as exc:
        assert "Extra inputs are not permitted" in str(exc)
    else:
        raise AssertionError("base_url must not be accepted")


def test_replace_credentials_route_delegates_without_exposing_secret() -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.ReplaceBrokerAccountCredentialsRequest(api_key="new-key", api_secret="new-secret")

    response = broker_accounts.replace_broker_account_credentials(ACCOUNT_ID, request, service=service)

    assert response.validation_status == BrokerAccountCredentialValidationStatus.VALID
    assert service.calls[-1] == ("replace", ACCOUNT_ID, "new-key", "new-secret")
    assert "new-secret" not in response.model_dump_json()


def test_update_details_route_delegates() -> None:
    service = RecordingBrokerAccountService()
    request = UpdateBrokerAccountDetailsRequest(display_name="Renamed")

    response = broker_accounts.update_broker_account_details(ACCOUNT_ID, request, service=service)

    assert response.account.display_name == "Renamed"
    assert response.already_exists is False
    assert service.calls[-1] == ("details", ACCOUNT_ID, "Renamed")


def test_delete_account_route_delegates_with_explicit_confirmation() -> None:
    service = RecordingBrokerAccountService()
    request = broker_accounts.DeleteBrokerAccountRequest(
        confirm_display_name="Paper",
        confirm_mode=TradingMode.BROKER_PAPER,
    )

    response = broker_accounts.delete_broker_account(ACCOUNT_ID, request, service=service)

    assert response.status == BrokerAccountDeletionStatus.HARD_DELETED
    assert service.calls[-1] == ("delete", ACCOUNT_ID, "Paper", TradingMode.BROKER_PAPER)


def test_account_risk_config_routes_default_and_persist(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="alpaca-paper:test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    service = RuntimeStoreBackedService(store)

    default = broker_accounts.get_account_risk_config(ACCOUNT_ID, service=service)
    assert default.account_id == ACCOUNT_ID
    assert default.version == 1
    assert default.sizing_method == "risk_percent_equity"

    updated = broker_accounts.put_account_risk_config(
        ACCOUNT_ID,
        broker_accounts.AccountRiskConfigUpdateRequest(
            sizing_method="fixed_shares",
            fixed_shares=3,
            risk_per_trade_pct=None,
            max_open_positions=2,
        ),
        service=service,
    )

    assert updated.version == 1
    assert updated.fixed_shares == 3
    assert store.load_account_risk_config(ACCOUNT_ID).fixed_shares == 3

    updated_again = broker_accounts.put_account_risk_config(
        ACCOUNT_ID,
        broker_accounts.AccountRiskConfigUpdateRequest(
            sizing_method="fixed_shares",
            fixed_shares=4,
            risk_per_trade_pct=None,
        ),
        service=service,
    )
    assert updated_again.version == 2


def test_account_restriction_routes_default_and_persist(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="alpaca-paper:test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    service = RuntimeStoreBackedService(store)

    default = broker_accounts.get_account_restrictions(ACCOUNT_ID, service=service)
    assert default.symbol_blocklist == ()
    assert default.long_only is False

    updated = broker_accounts.put_account_restrictions(
        ACCOUNT_ID,
        broker_accounts.AccountRestrictionsUpdateRequest(
            symbol_blocklist=("TSLA", "GME"),
            long_only=True,
            notes="operator block",
        ),
        service=service,
    )

    assert updated.version == 1
    assert updated.symbol_blocklist == ("TSLA", "GME")
    assert store.load_account_restrictions(ACCOUNT_ID).notes == "operator block"


# ---------------------------------------------------------------------------
# Slice B: risk-plan-map routes
# ---------------------------------------------------------------------------

RISK_PLAN_VERSION_ID = UUID("cccccccc-dddd-eeee-ffff-000000000000")
RISK_PLAN_VERSION_ID_2 = UUID("dddddddd-eeee-ffff-0000-111111111111")


def _seed_risk_plan_version(store: SQLiteRuntimeStore, version_id: UUID, name: str = "Test Plan") -> None:
    # Slice B adversarial fix B-BUG-1: route validates the version exists in
    # risk_plan_versions before writing the map row, so PUT tests must seed
    # the version they reference instead of using a random UUID.
    from backend.app.domain.risk_plan import (
        RiskPlan,
        RiskPlanConfig,
        RiskPlanSizingMethod,
        RiskPlanStatus,
        RiskPlanTier,
        RiskPlanVersion,
        RiskPlanVersionStatus,
    )

    plan = RiskPlan(
        name=name,
        status=RiskPlanStatus.DRAFT,
        risk_score=5,
        risk_tier=RiskPlanTier.BALANCED,
    )
    version = RiskPlanVersion(
        risk_plan_version_id=version_id,
        risk_plan_id=plan.risk_plan_id,
        version=1,
        # DRAFT status doesn't require activated_at; the resolver
        # treats DRAFT versions the same as ACTIVE for config lookup
        # (Slice B fix B-RISK-3 only excludes DEPRECATED).
        status=RiskPlanVersionStatus.DRAFT,
        config=RiskPlanConfig(
            sizing_method=RiskPlanSizingMethod.RISK_PERCENT,
            risk_per_trade_pct=1,
        ),
    )
    store.save_risk_plan(plan)
    store.save_risk_plan_version(version)


def _make_store_with_account(tmp_path) -> SQLiteRuntimeStore:
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="alpaca-paper:test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    # Seed both shared RiskPlanVersion ids so PUT tests can reference them.
    _seed_risk_plan_version(store, RISK_PLAN_VERSION_ID, "Test Plan A")
    _seed_risk_plan_version(store, RISK_PLAN_VERSION_ID_2, "Test Plan B")
    return store


def test_risk_plan_map_routes_registered() -> None:
    registered = {(route.method, route.path): route.response_model for route in broker_accounts.router.routes}
    assert ("GET", "/api/v1/broker-accounts/{account_id}/risk-plan-map") in registered
    assert ("PUT", "/api/v1/broker-accounts/{account_id}/risk-plan-map") in registered
    assert registered[("GET", "/api/v1/broker-accounts/{account_id}/risk-plan-map")] is AccountRiskPlanMap
    assert registered[("PUT", "/api/v1/broker-accounts/{account_id}/risk-plan-map")] is AccountRiskPlanMap


def test_get_risk_plan_map_returns_empty_when_no_entries(tmp_path) -> None:
    store = _make_store_with_account(tmp_path)
    service = RuntimeStoreBackedService(store)

    result = broker_accounts.get_account_risk_plan_map(ACCOUNT_ID, service=service)

    assert isinstance(result, AccountRiskPlanMap)
    assert result.account_id == ACCOUNT_ID
    assert result.entries == ()


def test_get_risk_plan_map_returns_404_for_unknown_account(tmp_path) -> None:
    import pytest
    from fastapi import HTTPException

    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    service = RuntimeStoreBackedService(store)
    unknown_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    with pytest.raises(HTTPException) as exc_info:
        broker_accounts.get_account_risk_plan_map(unknown_id, service=service)

    assert exc_info.value.status_code == 404


def test_put_risk_plan_map_upserts_entry(tmp_path) -> None:
    store = _make_store_with_account(tmp_path)
    service = RuntimeStoreBackedService(store)
    request = AccountRiskPlanMapUpdateRequest(
        horizon=TradingHorizon.INTRADAY,
        risk_plan_version_id=RISK_PLAN_VERSION_ID,
    )

    result = broker_accounts.put_account_risk_plan_map(ACCOUNT_ID, request, service=service)

    assert isinstance(result, AccountRiskPlanMap)
    assert len(result.entries) == 1
    assert result.entries[0].horizon == TradingHorizon.INTRADAY
    assert result.entries[0].risk_plan_version_id == RISK_PLAN_VERSION_ID


def test_put_risk_plan_map_with_none_deletes_entry(tmp_path) -> None:
    store = _make_store_with_account(tmp_path)
    service = RuntimeStoreBackedService(store)
    # First upsert an entry.
    broker_accounts.put_account_risk_plan_map(
        ACCOUNT_ID,
        AccountRiskPlanMapUpdateRequest(
            horizon=TradingHorizon.SWING,
            risk_plan_version_id=RISK_PLAN_VERSION_ID,
        ),
        service=service,
    )
    # Then clear it with None.
    result = broker_accounts.put_account_risk_plan_map(
        ACCOUNT_ID,
        AccountRiskPlanMapUpdateRequest(horizon=TradingHorizon.SWING, risk_plan_version_id=None),
        service=service,
    )

    assert result.entries == ()


def test_put_risk_plan_map_upsert_replaces_existing(tmp_path) -> None:
    store = _make_store_with_account(tmp_path)
    service = RuntimeStoreBackedService(store)
    broker_accounts.put_account_risk_plan_map(
        ACCOUNT_ID,
        AccountRiskPlanMapUpdateRequest(
            horizon=TradingHorizon.INTRADAY,
            risk_plan_version_id=RISK_PLAN_VERSION_ID,
        ),
        service=service,
    )
    result = broker_accounts.put_account_risk_plan_map(
        ACCOUNT_ID,
        AccountRiskPlanMapUpdateRequest(
            horizon=TradingHorizon.INTRADAY,
            risk_plan_version_id=RISK_PLAN_VERSION_ID_2,
        ),
        service=service,
    )

    assert len(result.entries) == 1
    assert result.entries[0].risk_plan_version_id == RISK_PLAN_VERSION_ID_2


def test_put_risk_plan_map_returns_404_for_unknown_account(tmp_path) -> None:
    import pytest
    from fastapi import HTTPException

    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    service = RuntimeStoreBackedService(store)
    unknown_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    request = AccountRiskPlanMapUpdateRequest(
        horizon=TradingHorizon.INTRADAY,
        risk_plan_version_id=RISK_PLAN_VERSION_ID,
    )

    with pytest.raises(HTTPException) as exc_info:
        broker_accounts.put_account_risk_plan_map(unknown_id, request, service=service)

    assert exc_info.value.status_code == 404


def test_put_risk_plan_map_multiple_horizons_accumulate(tmp_path) -> None:
    store = _make_store_with_account(tmp_path)
    service = RuntimeStoreBackedService(store)
    broker_accounts.put_account_risk_plan_map(
        ACCOUNT_ID,
        AccountRiskPlanMapUpdateRequest(
            horizon=TradingHorizon.SCALPING,
            risk_plan_version_id=RISK_PLAN_VERSION_ID,
        ),
        service=service,
    )
    result = broker_accounts.put_account_risk_plan_map(
        ACCOUNT_ID,
        AccountRiskPlanMapUpdateRequest(
            horizon=TradingHorizon.POSITION,
            risk_plan_version_id=RISK_PLAN_VERSION_ID_2,
        ),
        service=service,
    )

    assert len(result.entries) == 2
    horizons = {e.horizon for e in result.entries}
    assert TradingHorizon.SCALPING in horizons
    assert TradingHorizon.POSITION in horizons


def test_put_risk_plan_map_rejects_unknown_risk_plan_version_id(tmp_path) -> None:
    # Slice B adversarial fix B-BUG-1: PUT must validate the
    # risk_plan_version_id exists in risk_plan_versions before writing.
    # Without this guard the operator can silently create a dangling map
    # row that the runtime will then treat as "no plan for this horizon"
    # and reject every entry signal forever.
    import pytest
    from fastapi import HTTPException

    store = _make_store_with_account(tmp_path)
    service = RuntimeStoreBackedService(store)
    unknown_version = UUID("ffffffff-aaaa-bbbb-cccc-ddddddddeeee")
    request = AccountRiskPlanMapUpdateRequest(
        horizon=TradingHorizon.SWING,
        risk_plan_version_id=unknown_version,
    )

    with pytest.raises(HTTPException) as exc_info:
        broker_accounts.put_account_risk_plan_map(ACCOUNT_ID, request, service=service)

    assert exc_info.value.status_code == 400
    assert "unknown risk_plan_version_id" in str(exc_info.value.detail).lower() or str(unknown_version) in str(exc_info.value.detail)
    # And no row was written.
    result = broker_accounts.get_account_risk_plan_map(ACCOUNT_ID, service=service)
    assert result.entries == ()
