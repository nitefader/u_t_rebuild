"""FeatureEngine subscription manager — Phase 1 §11.4-5 deliverable.

Owns the canonical mapping ``FeatureKey -> Subscription``. When a Deployment
hands its ``FeaturePlan`` to FeatureEngine, the manager:

1. Resolves a ``pipeline_id`` for each FeatureKey (via an injected callable —
   the manager does not know about Provider, MarketDataPipeline, or any
   provider SDK).
2. Adds the Deployment to the consumer set for each FeatureKey.
3. Returns a ``SubscriptionDelta`` listing which ``(pipeline_id, feature_key)``
   tuples were newly added or removed.

Demand-dedup is at the **FeatureKey** level (per plan_review §I FINAL):
two Deployments needing ``5m.close[0]`` for AAPL share one subscription.
A single Deployment may resolve different FeatureKeys to different pipelines
("the normal case, not an edge case").

Hard rule (final_roadmap §12 stop 1): this module must not import any
provider SDK. The pipeline_resolver callable is the only seam — callers
own provider IO.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from uuid import UUID

from backend.app.domain._base import utc_now

from .planner import FeaturePlan
from .spec import FeatureSpec


PipelineResolver = Callable[[FeatureSpec, str], str | None]
"""Resolve ``(spec, feature_key) -> pipeline_id``. None = no pipeline bound yet."""


@dataclass(frozen=True)
class SubscriptionEntry:
    """One row of the FeatureKey → Subscription map."""

    feature_key: str
    pipeline_id: str | None
    consumer_deployment_ids: frozenset[UUID]
    subscribed_at: datetime
    last_updated_at: datetime


@dataclass(frozen=True)
class SubscriptionChange:
    """An addition or removal in the subscription map."""

    feature_key: str
    pipeline_id: str | None


@dataclass(frozen=True)
class SubscriptionDelta:
    """Result of register/unregister: caller wires ``added`` to provider
    subscribe and ``removed`` to provider unsubscribe.

    Plan-evaluation errors surface via ``unresolved`` — FeatureKeys whose
    ``pipeline_resolver`` returned None get a subscription entry with
    ``pipeline_id=None`` (graceful degradation per slice 1B contract) and are
    listed here so operators can see what needs a default pipeline configured.
    """

    added: tuple[SubscriptionChange, ...] = ()
    removed: tuple[SubscriptionChange, ...] = ()
    unchanged: tuple[SubscriptionChange, ...] = ()
    unresolved: tuple[str, ...] = ()


class SubscriptionManager:
    """In-memory FeatureEngine subscription map.

    Persistence is intentionally out of scope for Phase 1 — Deployments hand
    their plan in at startup and the manager rebuilds state then. SQLite /
    durable persistence lands with BarBuilder + Streaming Runtime Truth
    (Phase 2).
    """

    def __init__(self) -> None:
        self._entries: dict[str, _MutableEntry] = {}
        self._plans_by_deployment: dict[UUID, _DeploymentRegistration] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_plan(
        self,
        deployment_id: UUID,
        plan: FeaturePlan,
        pipeline_resolver: PipelineResolver,
    ) -> SubscriptionDelta:
        """Attach a Deployment's plan to the subscription map.

        If the Deployment was previously registered with a different plan, the
        old plan is unregistered first. Re-registering the same plan is
        idempotent (no spurious add/remove deltas).
        """
        previous = self._plans_by_deployment.get(deployment_id)
        if previous is not None and previous.feature_keys == plan.feature_keys:
            # Idempotent: same plan, no change.
            return SubscriptionDelta(
                unchanged=tuple(SubscriptionChange(feature_key=key, pipeline_id=self._entries[key].pipeline_id) for key in plan.feature_keys),
            )

        if previous is not None:
            self._remove_consumer_from_keys(deployment_id, previous.feature_keys)

        added: list[SubscriptionChange] = []
        unchanged: list[SubscriptionChange] = []
        unresolved: list[str] = []
        spec_by_key = {key: spec for key, spec in zip(plan.feature_keys, plan.feature_specs)}

        for feature_key in plan.feature_keys:
            spec = spec_by_key[feature_key]
            now = utc_now()
            existing = self._entries.get(feature_key)
            if existing is None:
                pipeline_id = pipeline_resolver(spec, feature_key)
                self._entries[feature_key] = _MutableEntry(
                    feature_key=feature_key,
                    pipeline_id=pipeline_id,
                    consumer_deployment_ids={deployment_id},
                    subscribed_at=now,
                    last_updated_at=now,
                )
                added.append(SubscriptionChange(feature_key=feature_key, pipeline_id=pipeline_id))
                if pipeline_id is None:
                    unresolved.append(feature_key)
            else:
                existing.consumer_deployment_ids.add(deployment_id)
                existing.last_updated_at = now
                unchanged.append(SubscriptionChange(feature_key=feature_key, pipeline_id=existing.pipeline_id))
                if existing.pipeline_id is None:
                    unresolved.append(feature_key)

        # Removed: keys the previous plan held that the new plan doesn't.
        removed: list[SubscriptionChange] = []
        if previous is not None:
            new_keys = set(plan.feature_keys)
            for old_key in previous.feature_keys:
                if old_key in new_keys:
                    continue
                removed_change = self._sweep_after_removal(old_key)
                if removed_change is not None:
                    removed.append(removed_change)

        self._plans_by_deployment[deployment_id] = _DeploymentRegistration(feature_keys=plan.feature_keys)

        return SubscriptionDelta(
            added=tuple(added),
            removed=tuple(removed),
            unchanged=tuple(unchanged),
            unresolved=tuple(unresolved),
        )

    def unregister_plan(self, deployment_id: UUID) -> SubscriptionDelta:
        """Detach a Deployment from every FeatureKey it consumed.

        Subscriptions whose consumer set drops to zero are removed; their keys
        appear in the ``removed`` delta. Other consumers' subscriptions are
        untouched.
        """
        registration = self._plans_by_deployment.pop(deployment_id, None)
        if registration is None:
            return SubscriptionDelta()

        removed: list[SubscriptionChange] = []
        unchanged: list[SubscriptionChange] = []
        for feature_key in registration.feature_keys:
            entry = self._entries.get(feature_key)
            if entry is None:
                continue
            entry.consumer_deployment_ids.discard(deployment_id)
            if not entry.consumer_deployment_ids:
                removed_change = self._sweep_after_removal(feature_key)
                if removed_change is not None:
                    removed.append(removed_change)
            else:
                unchanged.append(SubscriptionChange(feature_key=feature_key, pipeline_id=entry.pipeline_id))
        return SubscriptionDelta(removed=tuple(removed), unchanged=tuple(unchanged))

    def subscription_for(self, feature_key: str) -> SubscriptionEntry | None:
        entry = self._entries.get(feature_key)
        if entry is None:
            return None
        return entry.frozen()

    def all_subscriptions(self) -> tuple[SubscriptionEntry, ...]:
        return tuple(entry.frozen() for entry in sorted(self._entries.values(), key=lambda e: e.feature_key))

    def consumer_count(self, feature_key: str) -> int:
        entry = self._entries.get(feature_key)
        return len(entry.consumer_deployment_ids) if entry is not None else 0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _remove_consumer_from_keys(self, deployment_id: UUID, feature_keys: tuple[str, ...]) -> None:
        for feature_key in feature_keys:
            entry = self._entries.get(feature_key)
            if entry is None:
                continue
            entry.consumer_deployment_ids.discard(deployment_id)

    def _sweep_after_removal(self, feature_key: str) -> SubscriptionChange | None:
        entry = self._entries.get(feature_key)
        if entry is None:
            return None
        if entry.consumer_deployment_ids:
            return None
        del self._entries[feature_key]
        return SubscriptionChange(feature_key=feature_key, pipeline_id=entry.pipeline_id)


@dataclass
class _MutableEntry:
    feature_key: str
    pipeline_id: str | None
    consumer_deployment_ids: set[UUID]
    subscribed_at: datetime
    last_updated_at: datetime

    def frozen(self) -> SubscriptionEntry:
        return SubscriptionEntry(
            feature_key=self.feature_key,
            pipeline_id=self.pipeline_id,
            consumer_deployment_ids=frozenset(self.consumer_deployment_ids),
            subscribed_at=self.subscribed_at,
            last_updated_at=self.last_updated_at,
        )


@dataclass(frozen=True)
class _DeploymentRegistration:
    feature_keys: tuple[str, ...]
