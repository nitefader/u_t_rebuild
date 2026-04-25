"""Market-data provider catalog — CRUD, validation, and resolver invocation.

This catalog is the canonical replacement for the deleted ``app/services``
bucket's ``ServicesCenterService`` market-data half. It carries no
``ServiceMode`` concept; broker-side mode is owned exclusively by
``BrokerAccount``.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain._base import utc_now

from .capability_profiles import provider_capability_profile
from .data_intent import DataIntent
from .models import (
    MarketDataServiceList,
    MarketDataServiceRecord,
    MarketDataServiceWrite,
    MarketDataValidationStatus,
)
from .resolver import (
    InvocationContext,
    ResolverResult,
    SelectionStrategy,
    ServiceStatus,
    resolve_market_data_service,
)
from .validation import MarketDataProviderValidator


class MarketDataCatalogError(ValueError):
    """Operator-readable Market Data catalog failure."""


class MarketDataCatalogSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_data_services: tuple[MarketDataServiceRecord, ...] = ()


class ResolveMarketDataRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: DataIntent
    selection_strategy: SelectionStrategy
    selected_service_id: UUID | None = None
    invocation_context: InvocationContext = InvocationContext.OPERATIONS_PREVIEW


class MarketDataServiceCatalog:
    def __init__(
        self,
        *,
        store_path: str | Path | None = None,
        validator: MarketDataProviderValidator | None = None,
    ) -> None:
        self._store_path = Path(store_path) if store_path is not None else None
        self._validator = validator or MarketDataProviderValidator()
        self._records: dict[UUID, MarketDataServiceRecord] = {}
        self._load()

    def list_services(self) -> MarketDataServiceList:
        return MarketDataServiceList(
            services=tuple(sorted(self._records.values(), key=lambda service: service.created_at))
        )

    def create_service(self, request: MarketDataServiceWrite) -> MarketDataServiceRecord:
        profile = provider_capability_profile(request.provider)
        manual_capabilities = request.capabilities is not None
        record = MarketDataServiceRecord(
            name=request.name,
            provider=request.provider,
            credentials_ref=_credential_ref(request.api_key),
            has_api_key=bool(request.api_key),
            has_api_secret=bool(request.api_secret),
            api_key_shape_valid=(not request.api_key or len(request.api_key.strip()) >= 6),
            api_secret_shape_valid=(not request.api_secret or len(request.api_secret.strip()) >= 8),
            capabilities=request.capabilities or profile.capabilities,
            capability_source="manual_override" if manual_capabilities else profile.source,
            capability_notes=request.capability_notes or profile.notes,
            capability_updated_at=utc_now(),
            capability_manual_override=manual_capabilities,
        )
        self._records[record.id] = record
        self._save()
        return record

    def get_service(self, service_id: UUID) -> MarketDataServiceRecord:
        return self._records[_known(service_id, self._records, "market data service")]

    def update_service(self, service_id: UUID, request: MarketDataServiceWrite) -> MarketDataServiceRecord:
        existing = self.get_service(service_id)
        manual_capabilities = request.capabilities is not None
        profile = provider_capability_profile(request.provider)
        updated = existing.model_copy(
            update={
                "name": request.name,
                "provider": request.provider,
                "credentials_ref": _credential_ref(request.api_key) or existing.credentials_ref,
                "has_api_key": existing.has_api_key or bool(request.api_key),
                "has_api_secret": existing.has_api_secret or bool(request.api_secret),
                "api_key_shape_valid": existing.api_key_shape_valid if not request.api_key else len(request.api_key.strip()) >= 6,
                "api_secret_shape_valid": existing.api_secret_shape_valid if not request.api_secret else len(request.api_secret.strip()) >= 8,
                "capabilities": request.capabilities or (profile.capabilities if existing.provider != request.provider else existing.capabilities),
                "capability_source": "manual_override" if manual_capabilities else (profile.source if existing.provider != request.provider else existing.capability_source),
                "capability_notes": request.capability_notes or (profile.notes if existing.provider != request.provider else existing.capability_notes),
                "capability_updated_at": utc_now() if manual_capabilities or existing.provider != request.provider else existing.capability_updated_at,
                "capability_manual_override": manual_capabilities or (existing.capability_manual_override and existing.provider == request.provider),
                "status": ServiceStatus.DRAFT if existing.status == ServiceStatus.VALID else existing.status,
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def validate_service(self, service_id: UUID) -> MarketDataServiceRecord:
        existing = self.get_service(service_id)
        if existing.status == ServiceStatus.DISABLED:
            result_status = MarketDataValidationStatus.DISABLED
            message = "Disabled services cannot be validated."
            capabilities = existing.capabilities
            capability_source = existing.capability_source
            capability_notes = existing.capability_notes
        else:
            result = self._validator.validate(
                provider=existing.provider,
                has_api_key=existing.has_api_key,
                has_api_secret=existing.has_api_secret,
                api_key=None if existing.api_key_shape_valid else "bad",
                api_secret=None if existing.api_secret_shape_valid else "bad",
            )
            result_status = result.status
            message = result.message
            capabilities = existing.capabilities if existing.capability_manual_override else result.capabilities
            capability_source = existing.capability_source if existing.capability_manual_override else result.capability_source
            capability_notes = existing.capability_notes if existing.capability_manual_override else result.capability_notes
        updated = existing.model_copy(
            update={
                "status": ServiceStatus.VALID if result_status == MarketDataValidationStatus.VALID else ServiceStatus.INVALID,
                "capabilities": capabilities,
                "capability_source": capability_source,
                "capability_notes": capability_notes,
                "capability_updated_at": utc_now(),
                "validation_status": result_status,
                "validation_message": message,
                "last_validated_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def set_default(self, service_id: UUID) -> MarketDataServiceRecord:
        selected = self.get_service(service_id)
        _ensure_can_default(selected)
        self._records = {
            key: service.model_copy(update={"is_default": key == service_id, "updated_at": utc_now()})
            for key, service in self._records.items()
        }
        self._save()
        return self._records[service_id]

    def disable_service(self, service_id: UUID) -> MarketDataServiceRecord:
        existing = self.get_service(service_id)
        updated = existing.model_copy(
            update={
                "status": ServiceStatus.DISABLED,
                "is_default": False,
                "disabled_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def resolve(self, request: ResolveMarketDataRequest, *, pipeline_registry: object | None = None) -> ResolverResult:
        lookup = pipeline_registry.lookup_default_for_provider if pipeline_registry is not None else None
        return resolve_market_data_service(
            request.intent,
            tuple(service.to_resolver_config() for service in self._records.values()),
            request.selection_strategy,
            selected_service_id=str(request.selected_service_id) if request.selected_service_id is not None else None,
            invocation_context=request.invocation_context,
            pipeline_lookup=lookup,
        )

    def _load(self) -> None:
        if self._store_path is None or not self._store_path.exists():
            return
        payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        snapshot = MarketDataCatalogSnapshot.model_validate(payload)
        self._records = {service.id: service for service in snapshot.market_data_services}

    def _save(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = MarketDataCatalogSnapshot(market_data_services=tuple(self._records.values()))
        self._store_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def _credential_ref(secret: str | None) -> str | None:
    if not secret:
        return None
    return f"market-data-credential:{sha256(secret.encode('utf-8')).hexdigest()[:12]}"


def _known(service_id: UUID, records: dict[UUID, MarketDataServiceRecord], label: str) -> UUID:
    if service_id not in records:
        raise MarketDataCatalogError(f"unknown {label}: {service_id}")
    return service_id


def _ensure_can_default(service: MarketDataServiceRecord) -> None:
    if service.status == ServiceStatus.DISABLED:
        raise MarketDataCatalogError("disabled service cannot be default")
    if service.status != ServiceStatus.VALID:
        raise MarketDataCatalogError("invalid service cannot be default")
