"""Composition-layer types for resolving deployment strategy artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class StrategyArtifactKind(StrEnum):
    EXPRESSION_V1 = "expression_v1"


@dataclass(frozen=True)
class StrategyArtifactMetadata:
    kind: StrategyArtifactKind
    strategy_version_v4_id: UUID
    strategy_id: UUID
