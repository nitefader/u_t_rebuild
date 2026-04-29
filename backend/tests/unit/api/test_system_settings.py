from __future__ import annotations

import pytest

from backend.app.api.routes.system_settings import (
    SystemSettings,
    SystemSettingsUpdate,
    get_system_settings,
    put_system_settings,
)
from backend.app.api.system_settings_store import SystemSettingsStore, setting


def test_store_round_trip(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    assert store.load() == {}
    store.update(alpaca_data_feed="sip", alpaca_use_test_stream=True)
    loaded = store.load()
    assert loaded["alpaca_data_feed"] == "sip"
    assert loaded["alpaca_use_test_stream"] is True


def test_store_rejects_unknown_keys(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    with pytest.raises(ValueError):
        store.update(secret_key="leaked")


def test_store_clears_value_when_set_to_none(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    store.update(alpaca_data_feed="sip")
    store.update(alpaca_data_feed=None)
    assert "alpaca_data_feed" not in store.load()


def test_get_route_returns_defaults_when_store_empty(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    settings = get_system_settings(store)
    assert isinstance(settings, SystemSettings)
    assert settings.alpaca_use_test_stream is False
    assert settings.alpaca_data_feed == "iex"
    assert settings.chart_lab_default_symbol == "SPY"
    assert settings.chart_lab_one_symbol_fakepaca is None


def test_put_route_persists_changes(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    payload = SystemSettingsUpdate(
        alpaca_use_test_stream=True,
        alpaca_data_feed="sip",
        chart_lab_default_symbol="qqq",
    )
    settings = put_system_settings(payload, store)
    assert settings.alpaca_use_test_stream is True
    assert settings.alpaca_data_feed == "sip"
    assert settings.chart_lab_default_symbol == "QQQ"
    # Persisted across a fresh store instance.
    fresh = SystemSettingsStore(tmp_path / "settings.json")
    assert fresh.load()["alpaca_data_feed"] == "sip"


def test_put_route_persists_chart_lab_one_symbol_override(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    settings = put_system_settings(SystemSettingsUpdate(chart_lab_one_symbol_fakepaca=False), store)
    assert settings.chart_lab_one_symbol_fakepaca is False
    assert SystemSettingsStore(tmp_path / "settings.json").load()["chart_lab_one_symbol_fakepaca"] is False
    cleared = put_system_settings(SystemSettingsUpdate(chart_lab_one_symbol_fakepaca=None), store)
    assert cleared.chart_lab_one_symbol_fakepaca is None
    assert "chart_lab_one_symbol_fakepaca" not in SystemSettingsStore(tmp_path / "settings.json").load()


def test_put_route_rejects_unsupported_data_feed(tmp_path) -> None:
    store = SystemSettingsStore(tmp_path / "settings.json")
    payload = SystemSettingsUpdate(alpaca_data_feed="moonbeam")
    with pytest.raises(Exception) as excinfo:
        put_system_settings(payload, store)
    assert "moonbeam" in str(excinfo.value)


def test_setting_helper_resolves_env_then_store_then_default(monkeypatch, tmp_path) -> None:
    """env wins over store; store fills in when env is unset; default is last resort."""
    import backend.app.api.system_settings_store as module

    fresh_store = SystemSettingsStore(tmp_path / "settings.json")
    monkeypatch.setattr(module, "_default_store", fresh_store)

    # Default: env unset, store empty.
    monkeypatch.delenv("ALPACA_DATA_FEED", raising=False)
    assert setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex") == "iex"

    # Store-only: still no env.
    fresh_store.update(alpaca_data_feed="sip")
    assert setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex") == "sip"

    # Env wins over store — operator's .env edit always takes effect.
    monkeypatch.setenv("ALPACA_DATA_FEED", "delayed_sip")
    assert setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex") == "delayed_sip"
