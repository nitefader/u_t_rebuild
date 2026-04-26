"""One-shot migration from legacy ``data/services_catalog.json``.

Older builds persisted both market-data services and AI providers in a
single ``services_catalog.json``. The current code reads from split
files (``market_data_catalog.json`` + ``ai_provider_catalog.json``).
This route migrates rows forward and renames the legacy file so it
doesn't keep being mistaken for live data.

Idempotent: re-running after migration is a no-op (legacy file gone).
Records that already exist in the new stores by id are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.config.runtime_paths import get_runtime_db_path


_MARKET_DATA_FIELDS = {
    "id", "name", "provider", "service_type", "status", "is_default",
    "credentials_ref", "has_api_key", "has_api_secret",
    "api_key_shape_valid", "api_secret_shape_valid",
    "capabilities", "capability_source", "capability_notes",
    "capability_updated_at", "capability_manual_override",
    "validation_status", "validation_message", "last_validated_at",
    "created_at", "updated_at", "disabled_at",
}

_AI_FIELDS = {
    "id", "name", "provider", "service_type", "status", "is_default",
    "credentials_ref", "has_api_key", "capability_label",
    "validation_status", "validation_message", "last_validated_at",
    "created_at", "updated_at", "disabled_at",
}


class MigrationResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    legacy_file_found: bool
    market_data_added: int
    market_data_skipped_existing: int
    ai_added: int
    ai_skipped_existing: int
    legacy_file_renamed_to: str | None = None


def _legacy_path() -> Path:
    return get_runtime_db_path().with_name("services_catalog.json")


def _market_data_path() -> Path:
    return get_runtime_db_path().with_name("market_data_catalog.json")


def _ai_path() -> Path:
    return get_runtime_db_path().with_name("ai_provider_catalog.json")


def _filter_record(record: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k in allowed}


def _load_records(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return list(payload.get(key, []))


def _write_records(path: Path, key: str, records: list[dict[str, Any]]) -> None:
    from backend.app.persistence import write_json_atomic

    write_json_atomic(path, {key: records})


def migrate_legacy_catalog() -> MigrationResponse:
    legacy = _legacy_path()
    if not legacy.exists():
        return MigrationResponse(
            legacy_file_found=False,
            market_data_added=0,
            market_data_skipped_existing=0,
            ai_added=0,
            ai_skipped_existing=0,
        )

    try:
        legacy_payload = json.loads(legacy.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"legacy services_catalog.json is not valid JSON: {exc}") from exc

    legacy_market = list(legacy_payload.get("market_data_services", []))
    legacy_ai = list(legacy_payload.get("ai_services", []))

    md_path = _market_data_path()
    ai_path = _ai_path()
    existing_md = _load_records(md_path, "market_data_services")
    existing_ai = _load_records(ai_path, "ai_services")
    existing_md_ids = {str(r.get("id")) for r in existing_md}
    existing_ai_ids = {str(r.get("id")) for r in existing_ai}

    md_added = 0
    md_skipped = 0
    for record in legacy_market:
        record_id = str(record.get("id"))
        if record_id in existing_md_ids:
            md_skipped += 1
            continue
        existing_md.append(_filter_record(record, _MARKET_DATA_FIELDS))
        existing_md_ids.add(record_id)
        md_added += 1

    ai_added = 0
    ai_skipped = 0
    for record in legacy_ai:
        record_id = str(record.get("id"))
        if record_id in existing_ai_ids:
            ai_skipped += 1
            continue
        existing_ai.append(_filter_record(record, _AI_FIELDS))
        existing_ai_ids.add(record_id)
        ai_added += 1

    _write_records(md_path, "market_data_services", existing_md)
    _write_records(ai_path, "ai_services", existing_ai)

    backup = legacy.with_suffix(legacy.suffix + ".migrated")
    legacy.rename(backup)

    return MigrationResponse(
        legacy_file_found=True,
        market_data_added=md_added,
        market_data_skipped_existing=md_skipped,
        ai_added=ai_added,
        ai_skipped_existing=ai_skipped,
        legacy_file_renamed_to=str(backup),
    )


router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/migrate-legacy-catalog/preview", response_model=MigrationResponse)
def preview_legacy_catalog() -> MigrationResponse:
    """Report what would be migrated without actually moving anything."""
    legacy = _legacy_path()
    if not legacy.exists():
        return MigrationResponse(
            legacy_file_found=False,
            market_data_added=0,
            market_data_skipped_existing=0,
            ai_added=0,
            ai_skipped_existing=0,
        )
    try:
        legacy_payload = json.loads(legacy.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return MigrationResponse(
            legacy_file_found=True,
            market_data_added=0,
            market_data_skipped_existing=0,
            ai_added=0,
            ai_skipped_existing=0,
        )
    existing_md_ids = {str(r.get("id")) for r in _load_records(_market_data_path(), "market_data_services")}
    existing_ai_ids = {str(r.get("id")) for r in _load_records(_ai_path(), "ai_services")}
    legacy_market = list(legacy_payload.get("market_data_services", []))
    legacy_ai = list(legacy_payload.get("ai_services", []))
    md_added = sum(1 for r in legacy_market if str(r.get("id")) not in existing_md_ids)
    md_skipped = len(legacy_market) - md_added
    ai_added = sum(1 for r in legacy_ai if str(r.get("id")) not in existing_ai_ids)
    ai_skipped = len(legacy_ai) - ai_added
    return MigrationResponse(
        legacy_file_found=True,
        market_data_added=md_added,
        market_data_skipped_existing=md_skipped,
        ai_added=ai_added,
        ai_skipped_existing=ai_skipped,
    )


@router.post("/migrate-legacy-catalog", response_model=MigrationResponse)
def run_legacy_catalog_migration() -> MigrationResponse:
    return migrate_legacy_catalog()
