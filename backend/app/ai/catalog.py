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


class AIProviderCatalogSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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
        record = AIServiceRecord(
            name=request.name,
            provider=request.provider,
            credentials_ref=_credential_ref(request.api_key),
            has_api_key=bool(request.api_key),
            capability_label=request.capability_label,
        )
        self._records[record.id] = record
        self._save()
        return record

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
        snapshot = AIProviderCatalogSnapshot.model_validate(payload)
        self._records = {service.id: service for service in snapshot.ai_services}

    def _save(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = AIProviderCatalogSnapshot(ai_services=tuple(self._records.values()))
        self._store_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def _credential_ref(secret: str | None) -> str | None:
    if not secret:
        return None
    return f"ai-provider-credential:{sha256(secret.encode('utf-8')).hexdigest()[:12]}"


def _known(service_id: UUID, records: dict[UUID, AIServiceRecord], label: str) -> UUID:
    if service_id not in records:
        raise AIProviderCatalogError(f"unknown {label}: {service_id}")
    return service_id


def _ensure_can_default(service: AIServiceRecord) -> None:
    if service.status == AIProviderStatus.DISABLED:
        raise AIProviderCatalogError("disabled service cannot be default")
    if service.status != AIProviderStatus.VALID:
        raise AIProviderCatalogError("invalid service cannot be default")
