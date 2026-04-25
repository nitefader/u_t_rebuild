from __future__ import annotations

from datetime import datetime, timezone

from backend.app.services import (
    DataConsumer,
    DataIntent,
    DataIntentMode,
    DataPurpose,
    MarketDataCapabilities,
    ResolverDecision,
    ResolverReasonCode,
    SelectionMode,
    ServiceStatus,
    Timeframe,
    alpaca_market_data_service,
    resolve_market_data_service,
    yahoo_market_data_service,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_backtest_daily_three_year_intent_auto_selects_yahoo_when_alpaca_is_also_valid() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        start_at=_dt("2023-01-01"),
        end_at=_dt("2026-01-01"),
        purpose=DataPurpose.BACKTEST,
    )

    result = resolve_market_data_service(
        intent,
        [
            alpaca_market_data_service(is_default=True),
            yahoo_market_data_service(),
        ],
        SelectionMode.AUTO,
    )

    assert result.decision == ResolverDecision.SELECTED
    assert result.selected_service_id == "yahoo-historical"
    assert result.provider == "yahoo"
    assert "long-range historical" in result.explanation


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
        SelectionMode.AUTO,
    )

    assert result.decision == ResolverDecision.SELECTED
    assert result.selected_service_id == "alpaca-main-data"
    assert result.provider == "alpaca"
    assert result.rejected_candidates[0].reason_code == ResolverReasonCode.REJECTED_NO_STREAMING


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
        SelectionMode.EXPLICIT,
        selected_service_id="yahoo-historical",
    )

    assert result.decision == ResolverDecision.REJECTED
    assert result.reason_code == ResolverReasonCode.REJECTED_NO_STREAMING
    assert result.rejected_candidates[0].service_id == "yahoo-historical"


def test_default_alpaca_is_selected_when_default_mode_satisfies_intent() -> None:
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
        SelectionMode.DEFAULT,
    )

    assert result.decision == ResolverDecision.SELECTED
    assert result.reason_code == ResolverReasonCode.SELECTED_DEFAULT
    assert result.selected_service_id == "alpaca-main-data"


def test_invalid_default_service_is_rejected_in_default_mode() -> None:
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
        SelectionMode.DEFAULT,
    )

    assert result.decision == ResolverDecision.REJECTED
    assert result.reason_code == ResolverReasonCode.REJECTED_INVALID_SERVICE


def test_auto_mode_ignores_invalid_or_disabled_services() -> None:
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
        SelectionMode.AUTO,
    )

    assert result.selected_service_id == "yahoo-valid"
    assert {candidate.reason_code for candidate in result.rejected_candidates} >= {
        ResolverReasonCode.REJECTED_DISABLED_SERVICE,
        ResolverReasonCode.REJECTED_INVALID_SERVICE,
    }


def test_resolver_returns_clear_rejected_candidate_explanations() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionMode.AUTO)

    assert result.decision == ResolverDecision.REJECTED
    assert result.rejected_candidates
    assert result.rejected_candidates[0].explanation == "Yahoo Historical does not support streaming market data."


def test_no_compatible_service_returns_no_compatible_service() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BROKER_RUNTIME,
        mode=DataIntentMode.LIVE_RUNTIME,
        symbols=["SPY"],
        timeframe=Timeframe.M5,
        purpose=DataPurpose.RUNTIME_TRADING,
    )

    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionMode.AUTO)

    assert result.decision == ResolverDecision.REJECTED
    assert result.reason_code == ResolverReasonCode.REJECTED_NO_COMPATIBLE_SERVICE
    assert "no_compatible_service" in result.explanation


def test_broker_accounts_are_not_part_of_resolver_input() -> None:
    intent = DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.BACKTEST,
    )

    result = resolve_market_data_service(intent, [yahoo_market_data_service()], SelectionMode.AUTO)

    assert result.selected_service_id == "yahoo-historical"
    assert "broker_account_id" not in DataIntent.model_fields
    assert "account_id" not in DataIntent.model_fields


def test_broker_account_event_streams_are_not_market_data_service_capabilities() -> None:
    service = alpaca_market_data_service()

    assert service.service_type == "market_data"
    assert "broker_account_event_stream" not in MarketDataCapabilities.model_fields
    assert "order_updates" not in MarketDataCapabilities.model_fields
