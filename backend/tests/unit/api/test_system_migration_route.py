from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import backend.app.api.routes.system_migration as migration_module
from backend.app.api.routes.system_migration import (
    MigrationResponse,
    migrate_legacy_catalog,
    preview_legacy_catalog,
)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point all migration paths at a temp directory."""
    monkeypatch.setattr(migration_module, "_legacy_path", lambda: tmp_path / "services_catalog.json")
    monkeypatch.setattr(migration_module, "_market_data_path", lambda: tmp_path / "market_data_catalog.json")
    monkeypatch.setattr(migration_module, "_ai_path", lambda: tmp_path / "ai_provider_catalog.json")
    return tmp_path


def _legacy(market_services=(), ai_services=()) -> dict:
    return {
        "market_data_services": list(market_services),
        "ai_services": list(ai_services),
    }


def _md_record(record_id: str, name: str = "Alpaca", **extra) -> dict:
    base = {
        "id": record_id,
        "name": name,
        "provider": "alpaca",
        "service_type": "market_data",
        "is_default": False,
        "credentials_ref": "service-credential:abc",
        "has_api_key": True,
        "has_api_secret": True,
        "created_at": "2026-04-25T00:00:00Z",
        "updated_at": "2026-04-25T00:00:00Z",
    }
    base.update(extra)
    return base


def _ai_record(record_id: str, name: str = "GROQ", **extra) -> dict:
    base = {
        "id": record_id,
        "name": name,
        "provider": "groq",
        "service_type": "ai",
        "is_default": False,
        "credentials_ref": "service-credential:def",
        "has_api_key": True,
        "created_at": "2026-04-25T00:00:00Z",
        "updated_at": "2026-04-25T00:00:00Z",
    }
    base.update(extra)
    return base


def test_migration_no_legacy_file_is_a_noop(isolated_data_dir) -> None:
    response = migrate_legacy_catalog()
    assert response.legacy_file_found is False
    assert response.market_data_added == 0
    assert response.ai_added == 0


def test_migration_moves_legacy_records_to_split_files(isolated_data_dir) -> None:
    legacy_path = isolated_data_dir / "services_catalog.json"
    legacy_path.write_text(
        json.dumps(_legacy(
            market_services=[_md_record("11111111-1111-1111-1111-111111111111")],
            ai_services=[_ai_record("22222222-2222-2222-2222-222222222222")],
        )),
        encoding="utf-8",
    )
    response = migrate_legacy_catalog()
    assert response.legacy_file_found is True
    assert response.market_data_added == 1
    assert response.ai_added == 1
    md = json.loads((isolated_data_dir / "market_data_catalog.json").read_text(encoding="utf-8"))
    ai = json.loads((isolated_data_dir / "ai_provider_catalog.json").read_text(encoding="utf-8"))
    assert len(md["market_data_services"]) == 1
    assert len(ai["ai_services"]) == 1
    # Legacy renamed.
    assert not legacy_path.exists()
    assert (isolated_data_dir / "services_catalog.json.migrated").exists()


def test_migration_skips_records_already_in_split_files_by_id(isolated_data_dir) -> None:
    same_id = "11111111-1111-1111-1111-111111111111"
    (isolated_data_dir / "market_data_catalog.json").write_text(
        json.dumps({"market_data_services": [_md_record(same_id, name="Existing")]}),
        encoding="utf-8",
    )
    (isolated_data_dir / "services_catalog.json").write_text(
        json.dumps(_legacy(market_services=[_md_record(same_id, name="Legacy")])),
        encoding="utf-8",
    )
    response = migrate_legacy_catalog()
    assert response.market_data_added == 0
    assert response.market_data_skipped_existing == 1
    md = json.loads((isolated_data_dir / "market_data_catalog.json").read_text(encoding="utf-8"))
    assert md["market_data_services"][0]["name"] == "Existing"  # not overwritten


def test_migration_strips_unknown_fields_pydantic_would_reject(isolated_data_dir) -> None:
    """Legacy file has fields the new model rejects (extra='forbid'); migration filters them."""
    record = _md_record("11111111-1111-1111-1111-111111111111")
    record["mode"] = "paper"  # legacy field, not in MarketDataServiceRecord
    record["legacy_only"] = "drop me"
    (isolated_data_dir / "services_catalog.json").write_text(
        json.dumps(_legacy(market_services=[record])),
        encoding="utf-8",
    )
    response = migrate_legacy_catalog()
    assert response.market_data_added == 1
    persisted = json.loads((isolated_data_dir / "market_data_catalog.json").read_text(encoding="utf-8"))
    persisted_record = persisted["market_data_services"][0]
    assert "mode" not in persisted_record
    assert "legacy_only" not in persisted_record


def test_migration_corrupt_legacy_json_raises_clear_error(isolated_data_dir) -> None:
    (isolated_data_dir / "services_catalog.json").write_text("not json {{", encoding="utf-8")
    with pytest.raises(Exception) as excinfo:
        migrate_legacy_catalog()
    assert "valid JSON" in str(excinfo.value)
    # Legacy file preserved (not renamed) so the operator can fix it.
    assert (isolated_data_dir / "services_catalog.json").exists()


def test_migration_is_idempotent(isolated_data_dir) -> None:
    (isolated_data_dir / "services_catalog.json").write_text(
        json.dumps(_legacy(market_services=[_md_record("11111111-1111-1111-1111-111111111111")])),
        encoding="utf-8",
    )
    first = migrate_legacy_catalog()
    second = migrate_legacy_catalog()
    assert first.market_data_added == 1
    assert second.legacy_file_found is False  # already renamed
    assert second.market_data_added == 0


def test_preview_returns_counts_without_modifying_files(isolated_data_dir) -> None:
    legacy_path = isolated_data_dir / "services_catalog.json"
    legacy_path.write_text(
        json.dumps(_legacy(
            market_services=[
                _md_record("11111111-1111-1111-1111-111111111111"),
                _md_record("33333333-3333-3333-3333-333333333333", name="Yahoo", provider="yahoo"),
            ],
            ai_services=[_ai_record("22222222-2222-2222-2222-222222222222")],
        )),
        encoding="utf-8",
    )
    response = preview_legacy_catalog()
    assert response.legacy_file_found is True
    assert response.market_data_added == 2
    assert response.ai_added == 1
    # Legacy still on disk; nothing migrated.
    assert legacy_path.exists()
    assert not (isolated_data_dir / "market_data_catalog.json").exists()


def test_migration_uses_atomic_write(isolated_data_dir) -> None:
    """If the atomic write fails on the AI side, the market_data side already-written
    file should be valid JSON (not partially written)."""
    (isolated_data_dir / "services_catalog.json").write_text(
        json.dumps(_legacy(
            market_services=[_md_record("11111111-1111-1111-1111-111111111111")],
            ai_services=[_ai_record("22222222-2222-2222-2222-222222222222")],
        )),
        encoding="utf-8",
    )
    # Patch os.replace to fail only on the second call (the AI write).
    real_replace = __import__("os").replace
    call_count = {"n": 0}

    def selective_replace(src, dst):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated AI write failure")
        return real_replace(src, dst)

    with patch("backend.app.persistence.atomic_io.os.replace", side_effect=selective_replace):
        with pytest.raises(OSError):
            migrate_legacy_catalog()

    # Market data file is fully written and valid JSON; no torn write.
    md_path = isolated_data_dir / "market_data_catalog.json"
    assert md_path.exists()
    payload = json.loads(md_path.read_text(encoding="utf-8"))
    assert len(payload["market_data_services"]) == 1
    # Legacy file not yet renamed because the migration aborted before that step.
    assert (isolated_data_dir / "services_catalog.json").exists()
