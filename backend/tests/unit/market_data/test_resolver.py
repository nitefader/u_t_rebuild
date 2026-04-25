from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.market_data import (
    DataConsumer,
    DataIntent,
    DataIntentMode,
    DataPurpose,
    InvocationContext,
    MarketDataCapabilities,
    MarketDataServiceConfig,
    MarketDataValidationStatus,
    PerSymbolResolution,
    Provider,
    RESOLVER_VERSION,
    ResolverDecision,
    ResolverRejectionCode,
    ResolverResult,
    ResolverSelectionCode,
    SelectionStrategy,
    ServiceStatus,
    Timeframe,
    alpaca_market_data_service,
    resolve_market_data_service,
    yahoo_market_data_service,
)
from backend.app.market_data.resolver import (
    _VALIDATION_STATUS_TO_REJECTION,
    _compute_resolver_input_hash,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _backtest_intent(symbols: list[str] | None = None) -> DataIntent:
    return DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=symbols if symbols is not None else ["SPY"],
        timeframe=Timeframe.D1,
        start_at=_dt("2023-01-01"),
        end_at=_dt("2026-01-01"),
        purpose=DataPurpose.BACKTEST,
    )


def _row(result: ResolverResult, index: int = 0) -> PerSymbolResolution:
    return result.per_symbol_rows[index]


# ---------------------------------------------------------------------------
# Selection paths
# ---------------------------------------------------------------------------


def test_backtest_daily_three_year_intent_auto_selects_yahoo_when_alpaca_is_also_valid() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [alpaca_market_data_service(), yahoo_market_data_service()],
        SelectionStrategy.AUTO,
    )

    head = _row(result)
    assert result.decision == ResolverDecision.SELECTED
    assert head.selected_service_id == "yahoo-historical"
    assert head.selected_provider == Provider.YAHOO
    assert "long-range historical" in head.explanation


def test_auto_prefers_compatible_default_before_best_fit_scoring() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [alpaca_market_data_service(is_default=True), yahoo_market_data_service()],
        SelectionStrategy.AUTO,
    )

    head = _row(result)
    assert result.decision == ResolverDecision.SELECTED
    assert head.selected_service_id == "alpaca-main-data"
    assert head.reason == ResolverSelectionCode.SELECTED_DEFAULT_PREFERRED.value


def test_broker_runtime_five_minute_intent_auto_selects_alpaca_for_streaming_realtime() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(
        intent,
        [yahoo_market_data_service(is_default=True), alpaca_market_data_service()],
        SelectionStrategy.AUTO,
    )

    head = _row(result)
    assert result.decision == ResolverDecision.SELECTED
    assert head.selected_service_id == "alpaca-main-data"
    assert head.selected_provider == Provider.ALPACA
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.STREAM_NOT_AVAILABLE


def test_default_alpaca_is_selected_when_default_strategy_satisfies_intent() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M1,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(
        intent,
        [alpaca_market_data_service(is_default=True), yahoo_market_data_service()],
        SelectionStrategy.DEFAULT_PREFERRED,
    )

    head = _row(result)
    assert result.decision == ResolverDecision.SELECTED
    assert head.reason == ResolverSelectionCode.SELECTED_DEFAULT_PREFERRED.value
    assert head.selected_service_id == "alpaca-main-data"


def test_invalid_default_service_is_rejected_in_default_strategy() -> None:
    intent = DataIntent(
        consumer=DataConsumer.CHART_LAB,
        mode=DataIntentMode.BATCH,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.SIGNAL_PREVIEW,
    )

    result = resolve_market_data_service(
        intent,
        [yahoo_market_data_service(status=ServiceStatus.INVALID, is_default=True)],
        SelectionStrategy.DEFAULT_PREFERRED,
    )

    head = _row(result)
    assert result.decision == ResolverDecision.REJECTED
    assert head.reason == ResolverRejectionCode.PROVIDER_NOT_VALIDATED.value


def test_explicit_yahoo_selection_for_runtime_five_minute_is_rejected_without_streaming() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(
        intent,
        [yahoo_market_data_service(), alpaca_market_data_service()],
        SelectionStrategy.MANUAL_OVERRIDE,
        selected_service_id="yahoo-historical",
    )

    head = _row(result)
    assert result.decision == ResolverDecision.REJECTED
    assert head.reason == ResolverRejectionCode.STREAM_NOT_AVAILABLE.value
    assert head.rejected_providers[0].service_id == "yahoo-historical"


# ---------------------------------------------------------------------------
# Aggregate decision (SELECTED / REJECTED / PARTIAL)
# ---------------------------------------------------------------------------


def test_aggregate_decision_is_selected_only_when_all_rows_selected() -> None:
    intent = _backtest_intent(symbols=["SPY", "AAPL", "MSFT"])
    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionStrategy.AUTO)

    assert all(row.decision == ResolverDecision.SELECTED for row in result.per_symbol_rows)
    assert result.decision == ResolverDecision.SELECTED


def test_aggregate_decision_is_rejected_only_when_all_rows_rejected() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY", "AAPL"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )
    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionStrategy.AUTO)

    assert all(row.decision == ResolverDecision.REJECTED for row in result.per_symbol_rows)
    assert result.decision == ResolverDecision.REJECTED


def test_partial_decision_when_some_symbols_resolve_and_others_reject() -> None:
    """Today the resolver resolves uniformly per intent, so PARTIAL is reachable
    only by injecting a per-symbol asymmetry. Construct one manually to pin
    aggregate behavior; per-FeatureKey/per-symbol heterogeneity lands in 1B/1C.
    """
    rows = (
        PerSymbolResolution(
            symbol="SPY",
            decision=ResolverDecision.SELECTED,
            selected_service_id="x",
            selected_service_name="X",
            selected_provider=Provider.YAHOO,
            reason=ResolverSelectionCode.SELECTED_AUTO_BEST_FIT.value,
            explanation="ok",
        ),
        PerSymbolResolution(
            symbol="AAPL",
            decision=ResolverDecision.REJECTED,
            reason=ResolverRejectionCode.STREAM_NOT_AVAILABLE.value,
            explanation="no stream",
        ),
    )
    from backend.app.market_data.resolver import _aggregate_decision

    assert _aggregate_decision(rows) == ResolverDecision.PARTIAL


# ---------------------------------------------------------------------------
# Top-level mirror is gone
# ---------------------------------------------------------------------------


def test_resolver_result_has_no_top_level_selection_mirror() -> None:
    forbidden = {
        "selected_service_id",
        "selected_service_name",
        "selected_provider",
        "pipeline_id",
        "reason",
        "explanation",
        "rejected_providers",
    }
    fields = set(ResolverResult.model_fields)
    assert forbidden.isdisjoint(fields), f"top-level mirror still present: {forbidden & fields}"
    assert {
        "selection_strategy",
        "decision",
        "per_symbol_rows",
        "resolver_version",
        "resolver_input_hash",
        "invocation_context",
        "decided_at",
    } <= fields


def test_pipeline_id_lives_only_on_per_symbol_rows_and_is_null_until_phase_1b() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionStrategy.AUTO)

    assert "pipeline_id" not in ResolverResult.model_fields
    assert "pipeline_id" in PerSymbolResolution.model_fields
    assert all(row.pipeline_id is None for row in result.per_symbol_rows)


# ---------------------------------------------------------------------------
# Validation-status → rejection-code lossless mapping
# ---------------------------------------------------------------------------


def _service_with_validation_status(status: str, *, service_status: ServiceStatus = ServiceStatus.INVALID) -> MarketDataServiceConfig:
    return MarketDataServiceConfig(
        service_id=f"svc-{status}",
        service_name=f"Service ({status})",
        provider=Provider.ALPACA,
        status=service_status,
        is_default=False,
        capabilities=MarketDataCapabilities(),
        validation_status=status,
        validation_message="(prose that should not affect routing)",
    )


def test_validation_status_to_rejection_table_covers_every_enum_member() -> None:
    """Load-bearing — prevents the mapping going stale if the enum grows."""
    expected = {member.value for member in MarketDataValidationStatus}
    actual = set(_VALIDATION_STATUS_TO_REJECTION.keys())
    assert expected == actual, f"missing mappings: {expected - actual}; extra: {actual - expected}"


def test_invalid_validation_status_maps_to_provider_not_validated() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [_service_with_validation_status("invalid")],
        SelectionStrategy.AUTO,
    )
    head = _row(result)
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.PROVIDER_NOT_VALIDATED


def test_missing_credentials_validation_status_maps_to_credential_missing() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [_service_with_validation_status("missing_credentials")],
        SelectionStrategy.AUTO,
    )
    head = _row(result)
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.CREDENTIAL_MISSING


def test_provider_unreachable_validation_status_maps_to_provider_unreachable_code() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [_service_with_validation_status("provider_unreachable")],
        SelectionStrategy.AUTO,
    )
    head = _row(result)
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.PROVIDER_UNREACHABLE


def test_unsupported_provider_validation_status_maps_to_capability_tier_insufficient() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [_service_with_validation_status("unsupported_provider")],
        SelectionStrategy.AUTO,
    )
    head = _row(result)
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.CAPABILITY_TIER_INSUFFICIENT


def test_draft_never_validated_service_maps_to_provider_not_validated() -> None:
    """DRAFT with validation_status=None means the operator never ran validate."""
    service = MarketDataServiceConfig(
        service_id="svc-draft",
        service_name="Never Validated",
        provider=Provider.ALPACA,
        status=ServiceStatus.DRAFT,
        is_default=False,
        capabilities=MarketDataCapabilities(),
        validation_status=None,
    )
    result = resolve_market_data_service(_backtest_intent(), [service], SelectionStrategy.AUTO)
    head = _row(result)
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.PROVIDER_NOT_VALIDATED


def test_disabled_takes_precedence_over_validation_status() -> None:
    """DISABLED always wins regardless of validation_status — operator-veto is authoritative."""
    service = MarketDataServiceConfig(
        service_id="svc-disabled-but-invalid",
        service_name="Disabled With Invalid",
        provider=Provider.ALPACA,
        status=ServiceStatus.DISABLED,
        is_default=False,
        capabilities=MarketDataCapabilities(),
        validation_status="invalid",  # would normally route to PROVIDER_NOT_VALIDATED
    )
    result = resolve_market_data_service(_backtest_intent(), [service], SelectionStrategy.AUTO)
    head = _row(result)
    assert head.rejected_providers[0].reason_code == ResolverRejectionCode.OPERATOR_VETO


def test_disabled_status_maps_to_operator_veto_via_table_when_status_value_is_routed() -> None:
    """Defensive: table entry for ``disabled`` is OPERATOR_VETO."""
    assert _VALIDATION_STATUS_TO_REJECTION["disabled"] == ResolverRejectionCode.OPERATOR_VETO


def test_resolver_rejection_code_enum_has_twelve_members() -> None:
    assert len(list(ResolverRejectionCode)) == 12
    assert ResolverRejectionCode.PROVIDER_NOT_VALIDATED in ResolverRejectionCode


# ---------------------------------------------------------------------------
# Manual override unknown id → synthetic rejection entry
# ---------------------------------------------------------------------------


def test_manual_override_with_unknown_id_emits_rejection_entry() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(
        intent,
        [yahoo_market_data_service()],
        SelectionStrategy.MANUAL_OVERRIDE,
        selected_service_id="does-not-exist",
    )
    head = _row(result)
    assert result.decision == ResolverDecision.REJECTED
    assert head.reason == ResolverRejectionCode.NO_COMPATIBLE_PROVIDER.value
    assert len(head.rejected_providers) == 1
    rejection = head.rejected_providers[0]
    assert rejection.service_id == "does-not-exist"
    assert rejection.reason_code == ResolverRejectionCode.NO_COMPATIBLE_PROVIDER
    assert "unknown service id" in rejection.explanation.lower()


# ---------------------------------------------------------------------------
# Determinism: resolver_input_hash is the equality contract; decided_at is not
# ---------------------------------------------------------------------------


def test_resolver_input_hash_is_stable_for_equivalent_input() -> None:
    intent = _backtest_intent()
    services = [alpaca_market_data_service(), yahoo_market_data_service()]
    fixed = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)

    a = resolve_market_data_service(
        intent, services, SelectionStrategy.AUTO,
        invocation_context=InvocationContext.BACKTEST, decided_at=fixed,
    )
    b = resolve_market_data_service(
        _backtest_intent(), list(reversed(services)), SelectionStrategy.AUTO,
        invocation_context=InvocationContext.BACKTEST, decided_at=fixed,
    )

    assert a.resolver_input_hash == b.resolver_input_hash
    assert a.resolver_input_hash.startswith("sha256:")
    assert a.resolver_version == RESOLVER_VERSION
    assert a.invocation_context == InvocationContext.BACKTEST


def test_resolver_input_hash_changes_when_invocation_context_changes() -> None:
    intent = _backtest_intent()
    services = [alpaca_market_data_service(), yahoo_market_data_service()]

    chart = resolve_market_data_service(intent, services, SelectionStrategy.AUTO, invocation_context=InvocationContext.CHART_LAB)
    backtest = resolve_market_data_service(intent, services, SelectionStrategy.AUTO, invocation_context=InvocationContext.BACKTEST)

    assert chart.resolver_input_hash != backtest.resolver_input_hash


def test_decided_at_is_not_part_of_resolver_input_hash() -> None:
    intent = _backtest_intent()
    services = [yahoo_market_data_service()]

    a = resolve_market_data_service(
        intent, services, SelectionStrategy.AUTO,
        decided_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    b = resolve_market_data_service(
        intent, services, SelectionStrategy.AUTO,
        decided_at=datetime(2099, 12, 31, tzinfo=timezone.utc),
    )

    assert a.resolver_input_hash == b.resolver_input_hash
    assert a.decided_at != b.decided_at


def test_resolver_input_hash_is_stable_when_validation_message_changes() -> None:
    """Cosmetic prose must not mutate the resolver hash."""
    base = MarketDataServiceConfig(
        service_id="svc",
        service_name="A",
        provider=Provider.ALPACA,
        status=ServiceStatus.VALID,
        is_default=False,
        capabilities=MarketDataCapabilities(supports_historical=True, supports_daily=True, supports_long_range_history=True),
        validation_status="valid",
        validation_message="version 1 prose",
    )
    rephrased = base.model_copy(update={"validation_message": "version 2 — significantly different prose"})

    h1 = _compute_resolver_input_hash(
        intent=_backtest_intent(),
        services=(base,),
        selection_strategy=SelectionStrategy.AUTO,
        selected_service_id=None,
        invocation_context=InvocationContext.BACKTEST,
    )
    h2 = _compute_resolver_input_hash(
        intent=_backtest_intent(),
        services=(rephrased,),
        selection_strategy=SelectionStrategy.AUTO,
        selected_service_id=None,
        invocation_context=InvocationContext.BACKTEST,
    )

    assert h1 == h2


def test_resolver_input_hash_is_stable_when_service_name_changes() -> None:
    base = MarketDataServiceConfig(
        service_id="svc",
        service_name="Pretty Name",
        provider=Provider.ALPACA,
        status=ServiceStatus.VALID,
        is_default=False,
        capabilities=MarketDataCapabilities(supports_historical=True, supports_daily=True, supports_long_range_history=True),
        validation_status="valid",
    )
    renamed = base.model_copy(update={"service_name": "Different Display Name"})

    h1 = _compute_resolver_input_hash(
        intent=_backtest_intent(), services=(base,), selection_strategy=SelectionStrategy.AUTO,
        selected_service_id=None, invocation_context=InvocationContext.BACKTEST,
    )
    h2 = _compute_resolver_input_hash(
        intent=_backtest_intent(), services=(renamed,), selection_strategy=SelectionStrategy.AUTO,
        selected_service_id=None, invocation_context=InvocationContext.BACKTEST,
    )

    assert h1 == h2


def test_resolver_input_hash_changes_when_service_status_changes() -> None:
    base = yahoo_market_data_service()
    disabled = base.model_copy(update={"status": ServiceStatus.DISABLED})

    h1 = _compute_resolver_input_hash(
        intent=_backtest_intent(), services=(base,), selection_strategy=SelectionStrategy.AUTO,
        selected_service_id=None, invocation_context=InvocationContext.BACKTEST,
    )
    h2 = _compute_resolver_input_hash(
        intent=_backtest_intent(), services=(disabled,), selection_strategy=SelectionStrategy.AUTO,
        selected_service_id=None, invocation_context=InvocationContext.BACKTEST,
    )

    assert h1 != h2


def test_resolver_module_documents_determinism_contract() -> None:
    from backend.app.market_data import resolver as resolver_module

    docstring = resolver_module.__doc__ or ""
    assert "Determinism contract" in docstring
    assert "decided_at" in docstring


# ---------------------------------------------------------------------------
# Per-symbol fan-out
# ---------------------------------------------------------------------------


def test_per_symbol_result_rows_when_intent_lists_multiple_symbols() -> None:
    intent = _backtest_intent(symbols=["SPY", "AAPL", "MSFT"])
    result = resolve_market_data_service(
        intent,
        [yahoo_market_data_service(is_default=True), alpaca_market_data_service()],
        SelectionStrategy.AUTO,
    )

    assert len(result.per_symbol_rows) == 3
    assert [row.symbol for row in result.per_symbol_rows] == ["SPY", "AAPL", "MSFT"]
    assert all(row.selected_provider == Provider.YAHOO for row in result.per_symbol_rows)


def test_per_symbol_rows_default_to_wildcard_when_intent_has_no_symbols() -> None:
    intent = DataIntent(
        consumer=DataConsumer.CHART_LAB,
        mode=DataIntentMode.BATCH,
        symbols=[],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.SIGNAL_PREVIEW,
    )

    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionStrategy.AUTO)

    assert len(result.per_symbol_rows) == 1
    assert result.per_symbol_rows[0].symbol == "*"


# ---------------------------------------------------------------------------
# Contract guards
# ---------------------------------------------------------------------------


def test_resolver_rejects_only_via_frozen_enum_codes() -> None:
    """§12 stop condition 7: free-text rejection reasons are forbidden."""
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(
        intent,
        [
            yahoo_market_data_service(),
            yahoo_market_data_service(service_id="yahoo-disabled", service_name="Yahoo Disabled", status=ServiceStatus.DISABLED),
        ],
        SelectionStrategy.AUTO,
    )

    valid_codes = {code.value for code in ResolverRejectionCode}
    head = _row(result)
    for candidate in head.rejected_providers:
        assert candidate.reason_code.value in valid_codes
    assert head.reason in valid_codes


def test_selection_strategy_replaces_legacy_selection_mode_naming() -> None:
    assert {strategy.value for strategy in SelectionStrategy} == {
        "auto",
        "default_preferred",
        "manual_override",
    }
    assert "mode" not in ResolverResult.model_fields
    assert "selection_mode" not in ResolverResult.model_fields
    assert "selection_strategy" in ResolverResult.model_fields


def test_market_data_service_config_does_not_carry_a_trading_mode_field() -> None:
    """Per plan_review.md A1: market-data records have no system mode."""
    assert "mode" not in MarketDataServiceConfig.model_fields


def test_chart_lab_batch_daily_historical_intent_does_not_require_streaming() -> None:
    intent = DataIntent(
        consumer=DataConsumer.CHART_LAB,
        mode=DataIntentMode.BATCH,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        start_at=_dt("2025-01-01"),
        end_at=_dt("2026-01-01"),
        requires_realtime=True,
        purpose=DataPurpose.SIGNAL_PREVIEW,
    )

    assert intent.requires_streaming is False
    assert intent.requires_historical is True


def test_sim_lab_live_simulation_requires_live_data_without_broker_adapter_identity() -> None:
    intent = DataIntent(
        consumer=DataConsumer.SIM_LAB,
        mode=DataIntentMode.LIVE_PREVIEW,
        symbols=["SPY"],
        timeframe=Timeframe.M1,
        purpose=DataPurpose.SIGNAL_PREVIEW,
    )

    assert intent.requires_streaming is True
    assert intent.requires_realtime is True
    assert intent.requires_intraday is True
    assert "broker_adapter" not in DataIntent.model_fields
    assert "broker_account_id" not in DataIntent.model_fields


def test_auto_strategy_ignores_invalid_or_disabled_services() -> None:
    intent = DataIntent(
        consumer=DataConsumer.CHART_LAB,
        mode=DataIntentMode.BATCH,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.SIGNAL_PREVIEW,
    )

    result = resolve_market_data_service(
        intent,
        [
            yahoo_market_data_service(status=ServiceStatus.DISABLED),
            alpaca_market_data_service(status=ServiceStatus.INVALID),
            yahoo_market_data_service(service_id="yahoo-valid", service_name="Yahoo Valid"),
        ],
        SelectionStrategy.AUTO,
    )

    head = _row(result)
    assert head.selected_service_id == "yahoo-valid"
    assert {candidate.reason_code for candidate in head.rejected_providers} >= {
        ResolverRejectionCode.OPERATOR_VETO,
        ResolverRejectionCode.PROVIDER_NOT_VALIDATED,
    }


def test_no_compatible_service_returns_no_compatible_provider() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionStrategy.AUTO)
    head = _row(result)

    assert result.decision == ResolverDecision.REJECTED
    assert head.reason == ResolverRejectionCode.NO_COMPATIBLE_PROVIDER.value


def test_broker_accounts_are_not_part_of_resolver_input() -> None:
    intent = _backtest_intent()
    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionStrategy.AUTO)

    assert _row(result).selected_service_id == "yahoo-historical"
    assert "broker_account_id" not in DataIntent.model_fields
    assert "account_id" not in DataIntent.model_fields


def test_invalid_selection_strategy_value_raises() -> None:
    with pytest.raises(ValueError):
        resolve_market_data_service(_backtest_intent(), [], "default")
