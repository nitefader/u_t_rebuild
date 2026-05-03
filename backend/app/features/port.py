from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .frames import FeatureFrameSet, NormalizedBar
from .incremental import FeatureCache, IncrementalFeatureUpdate
from .planner import FeaturePlan


class FeatureEnginePort(Protocol):
    def update(
        self,
        *,
        plan: FeaturePlan,
        bar: NormalizedBar,
        cache: FeatureCache,
    ) -> IncrementalFeatureUpdate: ...

    def compute(self, plan: FeaturePlan, bars: Sequence[NormalizedBar]) -> FeatureFrameSet: ...
