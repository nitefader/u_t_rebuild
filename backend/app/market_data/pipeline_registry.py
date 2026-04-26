"""Persistent registry for ``MarketDataPipeline``.

Invariants:

- At most one pipeline per ``Provider`` is marked ``is_default_for_provider``.
  Setting a new default un-sets the previous default for that provider only —
  defaults are scoped per-provider, not globally (a Yahoo default and an
  Alpaca default coexist).
- Disabled pipelines cannot be set as default and lose their default flag on
  disable.
- Persistence shape mirrors ``MarketDataServiceCatalog``: a JSON file under the
  runtime DB path. SQLite migration is a separate slice.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now

from .pipeline import (
    DEFAULT_DATA_FEED,
    MarketDataPipeline,
    MarketDataPipelineList,
    MarketDataPipelineWrite,
    PipelineStatus,
)
from .resolver import Provider


class PipelineRegistryError(ValueError):
    """Operator-readable Pipeline registry failure."""


CURRENT_PIPELINE_REGISTRY_SCHEMA_VERSION = 2  # v2 added service_id + data_feed


class PipelineRegistrySnapshot(BaseModel):
    """Persisted pipeline registry envelope.

    ``extra="ignore"`` on the snapshot so a newer file written with
    additional top-level fields can still be loaded by older code.
    Field additions on persisted records still need a tolerant reader,
    but ``schema_version`` lets ``_load`` distinguish "old, fine" from
    "newer than this binary understands" without a Pydantic crash.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: int = CURRENT_PIPELINE_REGISTRY_SCHEMA_VERSION
    pipelines: tuple[MarketDataPipeline, ...] = ()


class MarketDataPipelineRegistry:
    def __init__(self, *, store_path: str | Path | None = None) -> None:
        self._store_path = Path(store_path) if store_path is not None else None
        self._records: dict[UUID, MarketDataPipeline] = {}
        self._load()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_pipelines(self) -> MarketDataPipelineList:
        return MarketDataPipelineList(
            pipelines=tuple(sorted(self._records.values(), key=lambda pipeline: pipeline.created_at))
        )

    def create_pipeline(self, request: MarketDataPipelineWrite) -> MarketDataPipeline:
        from .capability_profiles import provider_capability_profile

        capabilities = request.capabilities or provider_capability_profile(request.provider).capabilities
        # Invariant: ≤1 ACTIVE pipeline per (service_id, trading_mode, data_feed).
        # Reject create that would create a duplicate ACTIVE stream identity.
        self._enforce_pipeline_key_uniqueness(
            service_id=request.service_id,
            trading_mode=request.trading_mode,
            data_feed=request.data_feed,
        )
        pipeline = MarketDataPipeline(
            display_name=request.display_name,
            provider=request.provider,
            service_id=request.service_id,
            data_feed=request.data_feed,
            trading_mode=request.trading_mode,
            capabilities=capabilities,
            status=PipelineStatus.ACTIVE,
        )
        self._records[pipeline.id] = pipeline
        self._save()
        return pipeline

    def _enforce_pipeline_key_uniqueness(
        self,
        *,
        service_id: UUID | None,
        trading_mode: TradingMode | None,
        data_feed: str,
        ignore_pipeline_id: UUID | None = None,
    ) -> None:
        """Reject duplicate ACTIVE pipelines for the same stream identity.

        ``service_id=None`` (vendor-only / not yet bound) is exempt — at most
        one such legacy pipeline is allowed via dedup-on-load, but the
        invariant only fires when a Service is bound. Once Round-2
        backfill assigns service_id everywhere this becomes total.
        """
        if service_id is None:
            return
        normalized_feed = (data_feed or DEFAULT_DATA_FEED).lower()
        for pipeline_id, existing in self._records.items():
            if pipeline_id == ignore_pipeline_id:
                continue
            if existing.status != PipelineStatus.ACTIVE:
                continue  # invariant only fires against ACTIVE pipelines (per DE B2)
            if existing.service_id != service_id:
                continue
            if existing.trading_mode != trading_mode:
                continue
            if (existing.data_feed or DEFAULT_DATA_FEED).lower() != normalized_feed:
                continue
            raise PipelineRegistryError(
                f"a pipeline already exists for service={service_id} "
                f"mode={trading_mode.value if trading_mode else 'none'} "
                f"feed={normalized_feed!r} (id={pipeline_id}); "
                "duplicate active streams are not allowed"
            )

    def get_pipeline(self, pipeline_id: UUID) -> MarketDataPipeline:
        if pipeline_id not in self._records:
            raise PipelineRegistryError(f"unknown pipeline: {pipeline_id}")
        return self._records[pipeline_id]

    def update_pipeline(self, pipeline_id: UUID, request: MarketDataPipelineWrite) -> MarketDataPipeline:
        existing = self.get_pipeline(pipeline_id)
        # If the operator is rebinding to a new (service, mode, feed), the
        # invariant must hold under the new key as well.
        self._enforce_pipeline_key_uniqueness(
            service_id=request.service_id,
            trading_mode=request.trading_mode,
            data_feed=request.data_feed,
            ignore_pipeline_id=pipeline_id,
        )
        updated = existing.model_copy(
            update={
                "display_name": request.display_name,
                "provider": request.provider,
                "service_id": request.service_id if request.service_id is not None else existing.service_id,
                "data_feed": request.data_feed,
                "trading_mode": request.trading_mode,
                "capabilities": request.capabilities or existing.capabilities,
                "updated_at": utc_now(),
            }
        )
        self._records[pipeline_id] = updated
        self._save()
        return updated

    def set_default_for_provider(self, pipeline_id: UUID) -> MarketDataPipeline:
        target = self.get_pipeline(pipeline_id)
        if target.status == PipelineStatus.DISABLED:
            raise PipelineRegistryError("disabled pipeline cannot be default")
        provider = target.provider
        self._records = {
            key: pipeline.model_copy(
                update={
                    "is_default_for_provider": (
                        key == pipeline_id
                        if pipeline.provider == provider
                        else pipeline.is_default_for_provider
                    ),
                    "updated_at": utc_now() if pipeline.provider == provider else pipeline.updated_at,
                }
            )
            for key, pipeline in self._records.items()
        }
        self._save()
        return self._records[pipeline_id]

    def disable_pipeline(self, pipeline_id: UUID) -> MarketDataPipeline:
        existing = self.get_pipeline(pipeline_id)
        updated = existing.model_copy(
            update={
                "status": PipelineStatus.DISABLED,
                "is_default_for_provider": False,
                "disabled_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        self._records[pipeline_id] = updated
        self._save()
        return updated

    # ------------------------------------------------------------------
    # Resolver lookup
    # ------------------------------------------------------------------

    def lookup_default_for_provider(self, provider: Provider) -> str | None:
        """Return the default pipeline_id for ``provider``, or ``None``.

        Used as the resolver's ``pipeline_lookup`` callback so per-symbol
        resolution rows get a real ``pipeline_id``. Returns ``None`` when no
        default is set for the provider — the resolver tolerates this and
        leaves ``pipeline_id`` null (graceful degradation).
        """
        for pipeline in self._records.values():
            if (
                pipeline.provider == provider
                and pipeline.is_default_for_provider
                and pipeline.status != PipelineStatus.DISABLED
            ):
                return str(pipeline.id)
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._store_path is None or not self._store_path.exists():
            return
        payload = json.loads(self._store_path.read_text(encoding="utf-8"))
        version = payload.get("schema_version", 0)
        if version > CURRENT_PIPELINE_REGISTRY_SCHEMA_VERSION:
            raise PipelineRegistryError(
                f"pipeline registry on disk is schema_version={version}, but this binary "
                f"only understands up to {CURRENT_PIPELINE_REGISTRY_SCHEMA_VERSION}; "
                "rolling back? upgrade the binary or restore an older snapshot."
            )
        try:
            snapshot = PipelineRegistrySnapshot.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise PipelineRegistryError(
                f"pipeline registry at {self._store_path} could not be parsed: {exc}"
            ) from exc
        # v1 → v2 backfill: legacy pipelines have no service_id and a default
        # data_feed. We don't auto-bind service_id here (that requires the
        # catalog, which the registry doesn't see). attach_service_id() is
        # the explicit operator action that backfills.
        self._records = {pipeline.id: pipeline for pipeline in snapshot.pipelines}

    def attach_service_id(self, pipeline_id: UUID, service_id: UUID) -> MarketDataPipeline:
        """Backfill ``service_id`` on a legacy pipeline that loaded without one.

        Composes with ``_enforce_pipeline_key_uniqueness`` so the operator
        can't bind the same Service+mode+feed twice via two pipelines.
        """
        existing = self.get_pipeline(pipeline_id)
        self._enforce_pipeline_key_uniqueness(
            service_id=service_id,
            trading_mode=existing.trading_mode,
            data_feed=existing.data_feed,
            ignore_pipeline_id=pipeline_id,
        )
        updated = existing.model_copy(update={"service_id": service_id, "updated_at": utc_now()})
        self._records[pipeline_id] = updated
        self._save()
        return updated

    def _save(self) -> None:
        if self._store_path is None:
            return
        from backend.app.persistence import write_text_atomic

        snapshot = PipelineRegistrySnapshot(pipelines=tuple(self._records.values()))
        write_text_atomic(self._store_path, snapshot.model_dump_json(indent=2))
