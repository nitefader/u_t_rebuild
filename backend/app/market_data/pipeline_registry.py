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

from backend.app.domain._base import utc_now

from .pipeline import (
    MarketDataPipeline,
    MarketDataPipelineList,
    MarketDataPipelineWrite,
    PipelineStatus,
)
from .resolver import Provider


class PipelineRegistryError(ValueError):
    """Operator-readable Pipeline registry failure."""


class PipelineRegistrySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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
        pipeline = MarketDataPipeline(
            display_name=request.display_name,
            provider=request.provider,
            trading_mode=request.trading_mode,
            capabilities=capabilities,
            status=PipelineStatus.ACTIVE,
        )
        self._records[pipeline.id] = pipeline
        self._save()
        return pipeline

    def get_pipeline(self, pipeline_id: UUID) -> MarketDataPipeline:
        if pipeline_id not in self._records:
            raise PipelineRegistryError(f"unknown pipeline: {pipeline_id}")
        return self._records[pipeline_id]

    def update_pipeline(self, pipeline_id: UUID, request: MarketDataPipelineWrite) -> MarketDataPipeline:
        existing = self.get_pipeline(pipeline_id)
        updated = existing.model_copy(
            update={
                "display_name": request.display_name,
                "provider": request.provider,
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
        snapshot = PipelineRegistrySnapshot.model_validate(payload)
        self._records = {pipeline.id: pipeline for pipeline in snapshot.pipelines}

    def _save(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = PipelineRegistrySnapshot(pipelines=tuple(self._records.values()))
        self._store_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
