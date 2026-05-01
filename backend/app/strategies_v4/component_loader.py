"""Component loader for StrategyVersionV4 at runtime.

Fetches a persisted v4 strategy version and returns the domain object.
Called by the pipeline composition root when a Deployment carries a
``strategy_version_v4_id``.
"""
from __future__ import annotations

from uuid import UUID

from backend.app.domain.strategy_v4 import StrategyVersionV4


def load_v4_component(
    strategy_v4_service: object,
    strategy_version_v4_id: UUID,
) -> StrategyVersionV4:
    """Load a StrategyVersionV4 from the service layer.

    Parameters
    ----------
    strategy_v4_service:
        Any object that exposes ``get(strategy_version_v4_id: UUID) ->
        StrategyVersionV4``.  In production this is ``StrategyV4Service``;
        in tests callers may pass a duck-typed stub.
    strategy_version_v4_id:
        The PK of the ``strategy_versions_v4`` row to load.

    Returns
    -------
    StrategyVersionV4
        The fully assembled domain object (variables, entries, stops, legs,
        logical exits — all sub-tables loaded).

    Raises
    ------
    LookupError
        When the repository cannot find the requested version.
    AttributeError
        When ``strategy_v4_service`` does not expose a ``get`` method.
    """
    version: StrategyVersionV4 = strategy_v4_service.get(strategy_version_v4_id)
    return version
