from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import utc_now

from .data_intent import DataIntent
from .models import (
    AIServiceList,
    AIServiceRecord,
    AIServiceWrite,
    MarketDataServiceList,
    MarketDataServiceRecord,
    MarketDataServiceWrite,
    ServiceValidationStatus,
)
from .service_resolver import (
    MarketDataCapabilities,
    ResolverResult,
    SelectionMode,
    ServiceStatus,
    resolve_market_data_service,
)
from .validation import AIProviderValidator, MarketDataProviderValidator, yahoo_capabilities


class ServicesCenterError(ValueError):
    """Operator-readable Services Center failure."""


class ServiceCatalogSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_data_services: tuple[MarketDataServiceRecord, ...] = ()
    ai_services: tuple[AIServiceRecord, ...] = ()


class ResolveMarketDataRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: DataIntent
    selection_mode: SelectionMode
    selected_service_id: UUID | None = None


class ServicesCenterService:
    def __init__(
        self,
        *,
        store_path: str | Path | None = None,
        market_data_validator: MarketDataProviderValidator | None = None,
        ai_validator: AIProviderValidator | None = None,
    ) -> None:
        self._store_path = Path(store_path) if store_path is not None else None
        self._market_data_validator = market_data_validator or MarketDataProviderValidator()
        self._ai_validator = ai_validator or AIProviderValidator()
        self._market_data: dict[UUID, MarketDataServiceRecord] = {}
        self._ai: dict[UUID, AIServiceRecord] = {}
        self._load()

    def list_market_data_services(self) -> MarketDataServiceList:
        return MarketDataServiceList(services=tuple(sorted(self._market_data.values(), key=lambda service: service.created_at)))

    def create_market_data_service(self, request: MarketDataServiceWrite) -> MarketDataServiceRecord:
        record = MarketDataServiceRecord(
            name=request.name,
            provider=request.provider,
            mode=request.mode,
            credentials_ref=_credential_ref(request.api_key),
            has_api_key=bool(request.api_key),
            has_api_secret=bool(request.api_secret),
            api_key_shape_valid=(not request.api_key or len(request.api_key.strip()) >= 6),
            api_secret_shape_valid=(not request.api_secret or len(request.api_secret.strip()) >= 8),
            capabilities=yahoo_capabilities() if request.provider.value == "yahoo" else MarketDataCapabilities(),
        )
        self._market_data[record.id] = record
        self._save()
        return record

    def get_market_data_service(self, service_id: UUID) -> MarketDataServiceRecord:
        return self._market_data[_known(service_id, self._market_data, "market data service")]

    def update_market_data_service(self, service_id: UUID, request: MarketDataServiceWrite) -> MarketDataServiceRecord:
        existing = self.get_market_data_service(service_id)
        updated = existing.model_copy(
            update={
                "name": request.name,
                "provider": request.provider,
                "mode": request.mode,
                "credentials_ref": _credential_ref(request.api_key) or existing.credentials_ref,
                "has_api_key": existing.has_api_key or bool(request.api_key),
                "has_api_secret": existing.has_api_secret or bool(request.api_secret),
                "api_key_shape_valid": existing.api_key_shape_valid if not request.api_key else len(request.api_key.strip()) >= 6,
                "api_secret_shape_valid": existing.api_secret_shape_valid if not request.api_secret else len(request.api_secret.strip()) >= 8,
                "status": ServiceStatus.DRAFT if existing.status == ServiceStatus.VALID else existing.status,
                "updated_at": utc_now(),
            }
        )
        self._market_data[service_id] = updated
        self._save()
        return updated

    def validate_market_data_service(self, service_id: UUID) -> MarketDataServiceRecord:
        existing = self.get_market_data_service(service_id)
        if existing.status == ServiceStatus.DISABLED:
            result_status = ServiceValidationStatus.DISABLED
            message = "Disabled services cannot be validated."
            capabilities = existing.capabilities
        else:
            result = self._market_data_validator.validate(
                provider=existing.provider,
                mode=existing.mode,
                has_api_key=existing.has_api_key,
                has_api_secret=existing.has_api_secret,
                api_key=None if existing.api_key_shape_valid else "bad",
                api_secret=None if existing.api_secret_shape_valid else "bad",
            )
            result_status = result.status
            message = result.message
            capabilities = result.capabilities
        updated = existing.model_copy(
            update={
                "status": ServiceStatus.VALID if result_status == ServiceValidationStatus.VALID else ServiceStatus.INVALID,
                "capabilities": capabilities,
                "validation_status": result_status,
                "validation_message": message,
                "last_validated_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._market_data[service_id] = updated
        self._save()
        return updated

    def set_default_market_data_service(self, service_id: UUID) -> MarketDataServiceRecord:
        selected = self.get_market_data_service(service_id)
        _ensure_can_default(selected)
        self._market_data = {
            key: service.model_copy(update={"is_default": key == service_id, "updated_at": utc_now()})
            for key, service in self._market_data.items()
        }
        self._save()
        return self._market_data[service_id]

    def disable_market_data_service(self, service_id: UUID) -> MarketDataServiceRecord:
        existing = self.get_market_data_service(service_id)
        updated = existing.model_copy(update={"status": ServiceStatus.DISABLED, "is_default": False, "disabled_at": utc_now(), "updated_at": utc_now()})
        self._market_data[service_id] = updated
        self._save()
        return updated

    def resolve_market_data(self, request: ResolveMarketDataRequest) -> ResolverResult:
        return resolve_market_data_service(
            request.intent,
            tuple(service.to_resolver_config() for service in self._market_data.values()),
            request.selection_mode,
            selected_service_id=str(request.selected_service_id) if request.selected_service_id is not None else None,
        )

    def list_ai_services(self) -> AIServiceList:
        return AIServiceList(services=tuple(sorted(self._ai.values(), key=lambda service: service.created_at)))

    def create_ai_service(self, request: AIServiceWrite) -> AIServiceRecord:
        record = AIServiceRecord(
            name=request.name,
            provider=request.provider,
            credentials_ref=_credential_ref(request.api_key),
            has_api_key=bool(request.api_key),
            capability_label=request.capability_label,
        )
        self._ai[record.id] = record
        self._save()
        return record

    def get_ai_service(self, service_id: UUID) -> AIServiceRecord:
        return self._ai[_known(service_id, self._ai, "AI service")]

    def update_ai_service(self, service_id: UUID, request: AIServiceWrite) -> AIServiceRecord:
        existing = self.get_ai_service(service_id)
        updated = existing.model_copy(
            update={
                "name": request.name,
                "provider": request.provider,
                "credentials_ref": _credential_ref(request.api_key) or existing.credentials_ref,
                "has_api_key": existing.has_api_key or bool(request.api_key),
                "capability_label": request.capability_label,
                "status": ServiceStatus.DRAFT if existing.status == ServiceStatus.VALID else existing.status,
                "updated_at": utc_now(),
            }
        )
        self._ai[service_id] = updated
        self._save()
        return updated

    def validate_ai_service(self, service_id: UUID) -> AIServiceRecord:
        existing = self.get_ai_service(service_id)
        result = self._ai_validator.validate(provider=existing.provider, has_api_key=existing.has_api_key)
        updated = existing.model_copy(
            update={
                "status": ServiceStatus.VALID if result.status == ServiceValidationStatus.VALID else ServiceStatus.INVALID,
                "validation_status": result.status,
                "validation_message": result.message,
                "last_validated_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._ai[service_id] = updated
        self._save()
        return updated

    def set_default_ai_service(self, service_id: UUID) -> AIServiceRecord:
        selected = self.get_ai_service(service_id)
        _ensure_can_default(selected)
        self._ai = {
            key: service.model_copy(update={"is_default": key == service_id, "updated_at": utc_now()})
            for key, service in self._ai.items()
        }
        self._save()
        return self._ai[service_id]

    def disable_ai_service(self, service_id: UUID) -> AIServiceRecord:
        existing = self.get_ai_service(service_id)
        updated = existing.model_copy(update={"status": ServiceStatus.DISABLED, "is_default": False, "disabled_at": utc_now(), "updated_at": utc_now()})
        self._ai[service_id] = updated
        self._save()
        return updated

    def _load(self) -> None:
        if self._store_path is None or not self._store_path.exists():
            return
        payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        snapshot = ServiceCatalogSnapshot.model_validate(payload)
        self._market_data = {service.id: service for service in snapshot.market_data_services}
        self._ai = {service.id: service for service in snapshot.ai_services}

    def _save(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = ServiceCatalogSnapshot(market_data_services=tuple(self._market_data.values()), ai_services=tuple(self._ai.values()))
        self._store_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def _credential_ref(secret: str | None) -> str | None:
    if not secret:
        return None
    return f"service-credential:{sha256(secret.encode('utf-8')).hexdigest()[:12]}"


def _known(service_id: UUID, records: dict[UUID, object], label: str) -> UUID:
    if service_id not in records:
        raise ServicesCenterError(f"unknown {label}: {service_id}")
    return service_id


def _ensure_can_default(service: MarketDataServiceRecord | AIServiceRecord) -> None:
    if service.status == ServiceStatus.DISABLED:
        raise ServicesCenterError("disabled service cannot be default")
    if service.status != ServiceStatus.VALID:
        raise ServicesCenterError("invalid service cannot be default")
