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
    ServicePurpose,
)
from .resolver import (
    InvocationContext,
    Provider,
    ResolverResult,
    SelectionStrategy,
    ServiceStatus,
    resolve_market_data_service,
)
from .validation import MarketDataProviderValidator


class MarketDataCatalogError(ValueError):
    """Operator-readable Market Data catalog failure."""


CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION = 2  # v2 added ServicePurpose default_for tags


class MarketDataCatalogSnapshot(BaseModel):
    """Persisted market-data catalog envelope.

    ``extra="ignore"`` so a newer file written with additional top-level
    fields can still be loaded by older code. Field additions on persisted
    records use the same pattern; ``schema_version`` lets ``_load``
    distinguish "old, fine" from "newer than this binary understands"
    without a Pydantic crash.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: int = CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION
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
        credential_store: object | None = None,
    ) -> None:
        self._store_path = Path(store_path) if store_path is not None else None
        self._validator = validator or MarketDataProviderValidator()
        self._credential_store = credential_store
        self._records: dict[UUID, MarketDataServiceRecord] = {}
        self._load()

    def list_services(self) -> MarketDataServiceList:
        return MarketDataServiceList(
            services=tuple(sorted(self._records.values(), key=lambda service: service.created_at))
        )

    def create_service(self, request: MarketDataServiceWrite) -> MarketDataServiceRecord:
        profile = provider_capability_profile(request.provider)
        manual_capabilities = request.capabilities is not None
        new_ref = _credential_ref(request.api_key)
        # Duplicate prevention: same provider + same credentials hash is the
        # same logical account. Re-registering returns the existing record
        # (idempotent for bootstrap-from-env, hard rejection for distinct
        # service names sharing one credential).
        existing = self.find_by_credentials(request.provider, new_ref)
        if existing is not None:
            if existing.name != request.name:
                raise MarketDataCatalogError(
                    f"a {request.provider.value} service with these credentials already exists "
                    f"as '{existing.name}' (id={existing.id}); duplicates are not allowed"
                )
            self._store_credentials(existing.id, request)
            return existing
        record = MarketDataServiceRecord(
            name=request.name,
            provider=request.provider,
            credentials_ref=new_ref,
            has_api_key=bool(request.api_key),
            has_api_secret=bool(request.api_secret),
            api_key_shape_valid=(not request.api_key or len(request.api_key.strip()) >= 6),
            api_secret_shape_valid=(not request.api_secret or len(request.api_secret.strip()) >= 8),
            capabilities=request.capabilities or profile.capabilities,
            capability_source="manual_override" if manual_capabilities else profile.source,
            capability_notes=request.capability_notes or profile.notes,
            capability_updated_at=utc_now(),
            capability_manual_override=manual_capabilities,
            default_for=tuple(_dedupe_purposes(request.default_for)),
        )
        self._records[record.id] = record
        self._store_credentials(record.id, request)
        # Single-canonical-default per purpose: any other Service that held one
        # of the new tags loses it. Stays consistent with set_default_for.
        if record.default_for:
            self._records = self._enforce_purpose_uniqueness(record.id, record.default_for)
        self._save()
        return record

    def find_by_credentials(self, provider: Provider, credentials_ref: str | None) -> MarketDataServiceRecord | None:
        """Return the existing service matching ``(provider, creds-hash)``, if any.

        Compares only the credential hash suffix (after the colon) so that
        legacy ``service-credential:HASH`` records dedupe against current
        ``market-data-credential:HASH`` records sharing the same secret.
        """
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

    def get_service(self, service_id: UUID) -> MarketDataServiceRecord:
        return self._records[_known(service_id, self._records, "market data service")]

    def get_credentials(self, service_id: UUID) -> tuple[str, str]:
        self.get_service(service_id)
        if self._credential_store is None or not hasattr(self._credential_store, "get"):
            raise MarketDataCatalogError(f"no credential store configured for market data service {service_id}")
        return self._credential_store.get(service_id)

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
        self._store_credentials(service_id, request)
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

    def set_default_for(
        self,
        service_id: UUID,
        purposes: tuple[ServicePurpose, ...] | list[ServicePurpose] | set[ServicePurpose],
    ) -> MarketDataServiceRecord:
        """Replace the ``default_for`` tag set on a Service.

        Single-canonical-default semantics: any other Service holding a
        purpose in ``purposes`` loses that tag. Disabled / draft Services
        cannot hold tags — same constraint as ``set_default``.
        """
        selected = self.get_service(service_id)
        _ensure_can_default(selected)
        normalized = tuple(_dedupe_purposes(purposes))
        # First strip the new tags off any other Service that held them, then
        # rewrite the target Service with the full new tag set.
        self._records = self._enforce_purpose_uniqueness(service_id, normalized)
        target = self._records[service_id]
        self._records[service_id] = target.model_copy(
            update={"default_for": normalized, "updated_at": utc_now()}
        )
        self._save()
        return self._records[service_id]

    def add_default_for(self, service_id: UUID, purpose: ServicePurpose) -> MarketDataServiceRecord:
        existing = self.get_service(service_id)
        merged = tuple(_dedupe_purposes((*existing.default_for, purpose)))
        return self.set_default_for(service_id, merged)

    def clear_default_for(self, service_id: UUID, purpose: ServicePurpose) -> MarketDataServiceRecord:
        existing = self.get_service(service_id)
        if purpose not in existing.default_for:
            return existing
        remaining = tuple(p for p in existing.default_for if p != purpose)
        updated = existing.model_copy(update={"default_for": remaining, "updated_at": utc_now()})
        self._records[service_id] = updated
        self._save()
        return updated

    def find_default_for(
        self, purpose: ServicePurpose, *, provider: Provider | None = None
    ) -> MarketDataServiceRecord | None:
        """Return the Service tagged ``default_for=purpose``, or ``None``.

        Replaces env-var lookup as the canonical "which credential do we use
        for this context?" path. Disabled Services are excluded.
        """
        for service in self._records.values():
            if service.status == ServiceStatus.DISABLED:
                continue
            if purpose not in service.default_for:
                continue
            if provider is not None and service.provider != provider:
                continue
            return service
        return None

    def _enforce_purpose_uniqueness(
        self, owner_id: UUID, purposes: tuple[ServicePurpose, ...]
    ) -> dict[UUID, MarketDataServiceRecord]:
        """Strip ``purposes`` from every Service except ``owner_id``."""
        if not purposes:
            return self._records
        purpose_set = set(purposes)
        result: dict[UUID, MarketDataServiceRecord] = {}
        for key, service in self._records.items():
            if key == owner_id:
                result[key] = service
                continue
            stripped = tuple(p for p in service.default_for if p not in purpose_set)
            if stripped == service.default_for:
                result[key] = service
            else:
                result[key] = service.model_copy(
                    update={"default_for": stripped, "updated_at": utc_now()}
                )
        return result

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

    def enable_service(self, service_id: UUID) -> MarketDataServiceRecord:
        existing = self.get_service(service_id)
        restored_status = (
            ServiceStatus.VALID
            if existing.validation_status == MarketDataValidationStatus.VALID
            else ServiceStatus.DRAFT
        )
        updated = existing.model_copy(
            update={
                "status": restored_status,
                "disabled_at": None,
                "updated_at": utc_now(),
            }
        )
        self._records[service_id] = updated
        self._save()
        return updated

    def delete_service(self, service_id: UUID) -> None:
        """Remove the service record from the catalog (hard delete).

        Callers must ensure no pipelines still reference this ``service_id``.
        """
        _known(service_id, self._records, "market data service")
        del self._records[service_id]
        if self._credential_store is not None and hasattr(self._credential_store, "delete"):
            self._credential_store.delete(service_id)
        self._save()

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
        version = payload.get("schema_version", 0)
        if version > CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION:
            raise MarketDataCatalogError(
                f"market data catalog on disk is schema_version={version}, but this binary "
                f"only understands up to {CURRENT_MARKET_DATA_CATALOG_SCHEMA_VERSION}; "
                "rolling back? upgrade the binary or restore an older snapshot."
            )
        try:
            snapshot = MarketDataCatalogSnapshot.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError + json sanity
            raise MarketDataCatalogError(
                f"market data catalog at {self._store_path} could not be parsed: {exc}"
            ) from exc
        self._records = self._dedupe(snapshot.market_data_services)

    def _store_credentials(self, service_id: UUID, request: MarketDataServiceWrite) -> None:
        if self._credential_store is None or not hasattr(self._credential_store, "put"):
            return
        if request.api_key and request.api_secret:
            self._credential_store.put(service_id, api_key=request.api_key, api_secret=request.api_secret)

    @staticmethod
    def _dedupe(services: tuple[MarketDataServiceRecord, ...]) -> dict[UUID, MarketDataServiceRecord]:
        """Drop duplicates by ``(provider, credentials_hash)``.

        Keeps the oldest (by ``created_at``) record so an
        operator-customized name survives when a bootstrap-from-env
        later registered a generic copy. ``is_default`` and the union
        of ``default_for`` tags are preserved across duplicates.
        """
        groups: dict[tuple[Provider, str | None], list[MarketDataServiceRecord]] = {}
        unkeyed: list[MarketDataServiceRecord] = []
        for service in services:
            ref_hash = _credential_hash_from_ref(service.credentials_ref)
            if ref_hash is None:
                unkeyed.append(service)
                continue
            groups.setdefault((service.provider, ref_hash), []).append(service)
        result: dict[UUID, MarketDataServiceRecord] = {}
        for service in unkeyed:
            result[service.id] = service
        for group in groups.values():
            group.sort(key=lambda s: s.created_at)
            kept = group[0]
            updates: dict[str, object] = {}
            if any(other.is_default for other in group[1:]):
                updates["is_default"] = True
            merged_purposes = tuple(_dedupe_purposes(
                p for record in group for p in record.default_for
            ))
            if merged_purposes != kept.default_for:
                updates["default_for"] = merged_purposes
            if updates:
                kept = kept.model_copy(update=updates)
            result[kept.id] = kept
        return result

    def _save(self) -> None:
        if self._store_path is None:
            return
        from backend.app.persistence import write_text_atomic

        snapshot = MarketDataCatalogSnapshot(market_data_services=tuple(self._records.values()))
        write_text_atomic(self._store_path, snapshot.model_dump_json(indent=2))


def _credential_ref(secret: str | None) -> str | None:
    if not secret:
        return None
    return f"market-data-credential:{sha256(secret.encode('utf-8')).hexdigest()[:12]}"


def _credential_hash_from_ref(ref: str | None) -> str | None:
    """Strip the prefix from a ``credentials_ref`` to get just the hash.

    Legacy records use ``service-credential:HASH``, current code uses
    ``market-data-credential:HASH``. Both refer to the same logical
    account when HASH matches; we dedup on the hash alone.
    """
    if not ref:
        return None
    if ":" in ref:
        return ref.split(":", 1)[1]
    return ref


def _known(service_id: UUID, records: dict[UUID, MarketDataServiceRecord], label: str) -> UUID:
    if service_id not in records:
        raise MarketDataCatalogError(f"unknown {label}: {service_id}")
    return service_id


def _ensure_can_default(service: MarketDataServiceRecord) -> None:
    if service.status == ServiceStatus.DISABLED:
        raise MarketDataCatalogError("disabled service cannot be default")
    if service.status != ServiceStatus.VALID:
        raise MarketDataCatalogError("invalid service cannot be default")


def _dedupe_purposes(purposes) -> list[ServicePurpose]:
    """Order-preserving dedup over an iterable of purpose tags."""
    seen: set[ServicePurpose] = set()
    result: list[ServicePurpose] = []
    for purpose in purposes:
        if purpose in seen:
            continue
        seen.add(purpose)
        result.append(purpose)
    return result
