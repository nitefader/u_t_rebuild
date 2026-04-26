"""AI provider catalog — CRUD, validation, and default-provider selection.

This catalog is the canonical replacement for the deleted ``app/services``
bucket's AI half.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain._base import utc_now

from .providers import (
    AIProviderStatus,
    AIServiceList,
    AIServiceRecord,
    AIServiceWrite,
    AIValidationStatus,
)
from .validation import AIProviderValidator


class AIProviderCatalogError(ValueError):
    """Operator-readable AI provider catalog failure."""


CURRENT_AI_PROVIDER_CATALOG_SCHEMA_VERSION = 1


class AIProviderCatalogSnapshot(BaseModel):
    """Persisted AI-provider catalog envelope.

    ``extra="ignore"`` so a newer file written with additional top-level
    fields can still be loaded by older code; ``schema_version`` lets
    ``_load`` distinguish "old, fine" from "newer than this binary
    understands" without a Pydantic crash.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: int = CURRENT_AI_PROVIDER_CATALOG_SCHEMA_VERSION

    ai_services: tuple[AIServiceRecord, ...] = ()


class AIProviderCatalog:
    def __init__(
        self,
        *,
        store_path: str | Path | None = None,
        validator: AIProviderValidator | None = None,
    ) -> None:
        self._store_path = Path(store_path) if store_path is not None else None
        self._validator = validator or AIProviderValidator()
        self._records: dict[UUID, AIServiceRecord] = {}
        self._load()

    def list_services(self) -> AIServiceList:
        return AIServiceList(services=tuple(sorted(self._records.values(), key=lambda service: service.created_at)))

    def create_service(self, request: AIServiceWrite) -> AIServiceRecord:
        new_ref = _credential_ref(request.api_key)
        existing = self.find_by_credentials(request.provider, new_ref)
        if existing is not None:
            if existing.name != request.name:
                raise AIProviderCatalogError(
                    f"a {request.provider.value} provider with these credentials already exists "
                    f"as '{existing.name}' (id={existing.id}); duplicates are not allowed"
                )
            return existing
        record = AIServiceRecord(
            name=request.name,
            provider=request.provider,
            credentials_ref=new_ref,
            has_api_key=bool(request.api_key),
            capability_label=request.capability_label,
        )
        self._records[record.id] = record
        self._save()
        return record

    def find_by_credentials(self, provider, credentials_ref: str | None) -> AIServiceRecord | None:
        if credentials_ref is None:
            return None
        target_hash = _credential_hash_from_ref(credentials_ref)
        if target_hash is None:
            return None
        for service in self._records.values():
            if service.provider != provider:
                continue
            existing_hash = _credential_hash_from_ref(service.credentials_ref)
            if existing_hash == target_hash:
                return service
        return None

    def get_service(self, service_id: UUID) -> AIServiceRecord:
        return self._records[_known(service_id, self._records, "AI service")]

    def update_service(self, service_id: UUID, request: AIServiceWrite) -> AIServiceRecord:
        existing = self.get_service(service_id)
        updated = existing.model_copy(
            update={
                "name": request.name,
                "provider": request.provider,
                "credentials_ref": _credential_ref(request.api_key) or existing.credentials_ref,
                "has_api_key": existing.has_api_key or bool(request.api_key),
                "capability_label": request.capability_label,
                "status": AIProviderStatus.DRAFT if existing.status == AIProviderStatus.VALID else existing.status,
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def validate_service(self, service_id: UUID) -> AIServiceRecord:
        existing = self.get_service(service_id)
        result = self._validator.validate(provider=existing.provider, has_api_key=existing.has_api_key)
        updated = existing.model_copy(
            update={
                "status": AIProviderStatus.VALID if result.status == AIValidationStatus.VALID else AIProviderStatus.INVALID,
                "validation_status": result.status,
                "validation_message": result.message,
                "last_validated_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def set_default(self, service_id: UUID) -> AIServiceRecord:
        selected = self.get_service(service_id)
        _ensure_can_default(selected)
        self._records = {
            key: service.model_copy(update={"is_default": key == service_id, "updated_at": utc_now()})
            for key, service in self._records.items()
        }
        self._save()
        return self._records[service_id]

    def disable_service(self, service_id: UUID) -> AIServiceRecord:
        existing = self.get_service(service_id)
        updated = existing.model_copy(
            update={
                "status": AIProviderStatus.DISABLED,
                "is_default": False,
                "disabled_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def _load(self) -> None:
        if self._store_path is None or not self._store_path.exists():
            return
        payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        version = payload.get("schema_version", 0)
        if version > CURRENT_AI_PROVIDER_CATALOG_SCHEMA_VERSION:
            raise AIProviderCatalogError(
                f"AI provider catalog on disk is schema_version={version}, but this binary "
                f"only understands up to {CURRENT_AI_PROVIDER_CATALOG_SCHEMA_VERSION}; "
                "rolling back? upgrade the binary or restore an older snapshot."
            )
        snapshot = AIProviderCatalogSnapshot.model_validate(payload)
        self._records = self._dedupe(snapshot.ai_services)

    @staticmethod
    def _dedupe(services: tuple[AIServiceRecord, ...]) -> dict[UUID, AIServiceRecord]:
        groups: dict[tuple, list[AIServiceRecord]] = {}
        unkeyed: list[AIServiceRecord] = []
        for service in services:
            ref_hash = _credential_hash_from_ref(service.credentials_ref)
            if ref_hash is None:
                unkeyed.append(service)
                continue
            groups.setdefault((service.provider, ref_hash), []).append(service)
        result: dict[UUID, AIServiceRecord] = {}
        for service in unkeyed:
            result[service.id] = service
        for group in groups.values():
            group.sort(key=lambda s: s.created_at)
            kept = group[0]
            if any(other.is_default for other in group[1:]):
                kept = kept.model_copy(update={"is_default": True})
            result[kept.id] = kept
        return result

    def _save(self) -> None:
        if self._store_path is None:
            return
        from backend.app.persistence import write_text_atomic

        snapshot = AIProviderCatalogSnapshot(ai_services=tuple(self._records.values()))
        write_text_atomic(self._store_path, snapshot.model_dump_json(indent=2))


def _credential_ref(secret: str | None) -> str | None:
    if not secret:
        return None
    return f"ai-provider-credential:{sha256(secret.encode('utf-8')).hexdigest()[:12]}"


def _credential_hash_from_ref(ref: str | None) -> str | None:
    """Strip the prefix from a ``credentials_ref`` to get just the hash.

    Older records used the ``service-credential:`` prefix; newer ones use
    ``ai-provider-credential:``. Both refer to the same logical account
    when the hash matches.
    """
    if not ref:
        return None
    if ":" in ref:
        return ref.split(":", 1)[1]
    return ref


def _known(service_id: UUID, records: dict[UUID, AIServiceRecord], label: str) -> UUID:
    if service_id not in records:
        raise AIProviderCatalogError(f"unknown {label}: {service_id}")
    return service_id


def _ensure_can_default(service: AIServiceRecord) -> None:
    if service.status == AIProviderStatus.DISABLED:
        raise AIProviderCatalogError("disabled service cannot be default")
    if service.status != AIProviderStatus.VALID:
        raise AIProviderCatalogError("invalid service cannot be default")
