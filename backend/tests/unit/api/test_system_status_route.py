from __future__ import annotations

from backend.app.api.routes.system_status import (
    SystemStatusResponse,
    system_status,
)


def test_status_no_creds_reports_missing(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_USE_TEST_STREAM", raising=False)
    monkeypatch.delenv("ALPACA_DATA_FEED", raising=False)
    response = system_status()
    assert isinstance(response, SystemStatusResponse)
    assert response.alpaca_credentials_present is False
    assert response.alpaca_test_stream is False
    assert response.alpaca_data_feed == "iex"


def test_status_data_feed_propagates_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.delenv("ALPACA_USE_TEST_STREAM", raising=False)
    monkeypatch.setenv("ALPACA_DATA_FEED", "SIP")
    response = system_status()
    assert response.alpaca_data_feed == "sip"


def test_status_test_stream_overrides_data_feed(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.setenv("ALPACA_USE_TEST_STREAM", "1")
    monkeypatch.setenv("ALPACA_DATA_FEED", "sip")
    response = system_status()
    assert response.alpaca_data_feed == "test"


def test_status_with_creds_reports_present(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    response = system_status()
    assert response.alpaca_credentials_present is True


def test_status_test_stream_flag_propagates(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.setenv("ALPACA_USE_TEST_STREAM", "1")
    response = system_status()
    assert response.alpaca_test_stream is True


def test_status_endpoint_defaults_to_paper(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_BASE_URL", raising=False)
    monkeypatch.delenv("UTOS_ENVIRONMENT", raising=False)
    response = system_status()
    assert "paper-api" in response.alpaca_endpoint
    assert response.operator_environment == "paper"


def test_status_recognizes_live_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.delenv("UTOS_ENVIRONMENT", raising=False)
    response = system_status()
    assert response.operator_environment == "live"
    assert response.operator_environment_source == "inferred_from_endpoint"
    assert response.operator_environment_conflict is None


def test_status_uses_explicit_utos_environment_over_url(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("UTOS_ENVIRONMENT", "paper")
    response = system_status()
    assert response.operator_environment == "paper"
    assert response.operator_environment_source == "explicit"
    assert response.operator_environment_conflict is None


def test_status_normalizes_production_alias_to_live(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    monkeypatch.setenv("UTOS_ENVIRONMENT", "production")
    response = system_status()
    assert response.operator_environment == "live"
    assert response.operator_environment_source == "explicit"
    assert response.operator_environment_conflict is None


def test_status_surfaces_conflict_when_explicit_disagrees_with_url(monkeypatch) -> None:
    """UTOS_ENVIRONMENT wins, but the conflict is surfaced for the operator."""
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("UTOS_ENVIRONMENT", "live")
    response = system_status()
    assert response.operator_environment == "live"  # explicit wins
    assert response.operator_environment_source == "explicit"
    assert "disagrees" in (response.operator_environment_conflict or "")
    assert "paper" in (response.operator_environment_conflict or "")


def test_status_warns_on_unknown_utos_environment(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("UTOS_ENVIRONMENT", "staging")
    response = system_status()
    assert response.operator_environment == "staging"  # used as-is
    assert response.operator_environment_source == "explicit"
    assert response.operator_environment_conflict is not None
    assert "not one of" in response.operator_environment_conflict
