from __future__ import annotations

from backend.app.api import server
from backend.app.runtime import runtime_context


def test_startup_wires_broker_sync_before_opening_streams(monkeypatch) -> None:
    calls: list[str] = []

    def fake_manual_bootstrap():
        calls.append("manual_sync")
        return {"registered_account_ids": [], "skipped": [], "total_accounts_seen": 0}

    def fake_stream_bootstrap():
        calls.append("streams")
        return {"started_account_ids": [], "skipped": [], "total_accounts_seen": 0}

    monkeypatch.setattr(runtime_context, "bootstrap_manual_trade_composition", fake_manual_bootstrap)
    monkeypatch.setattr(runtime_context, "bootstrap_streams", fake_stream_bootstrap)

    server._bootstrap_streams()

    assert calls == ["manual_sync", "streams"]
