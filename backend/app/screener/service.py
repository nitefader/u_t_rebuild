"""ScreenerExecutionService — runs a Screener and persists the run + results."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from .domain import (
    Screener,
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerExpression,
    ScreenerExpressionKind,
    ScreenerMetric,
    ScreenerResultRow,
    ScreenerRun,
    ScreenerRunStatus,
    ScreenerVersion,
)
from .fields import get_field_definition
from .sources import MetricSource, UniverseResolver
from .store import ScreenerNotFoundError, ScreenerStore


class ScreenerValidationError(ValueError):
    """Operator-readable validation failure."""


class ScreenerSourceError(RuntimeError):
    """Operator-readable failure when a metric/universe source fails fatally."""


# Re-exported so the routes module can import a single error namespace.
ScreenerNotFoundError = ScreenerNotFoundError  # noqa: F811


class ScreenerExecutionService:
    """Run a saved Screener.

    Doctrine guards (per ``AGENTS.md``):

    - The service NEVER mutates Watchlists or any other component model.
    - It NEVER calls a broker API directly — all data flows through the
      Data Center cache via ``HistoricalBarsLookup``.
    - ``ScreenerRun`` is immutable: a re-run produces a new ``ScreenerRun``
      with a fresh id; an existing run is never mutated post-completion.
    """

    def __init__(
        self,
        *,
        store: ScreenerStore,
        universe_resolver: UniverseResolver,
        metric_source: MetricSource,
    ) -> None:
        self._store = store
        self._universe = universe_resolver
        self._metrics = metric_source

    # ---------------- CRUD --------------------------------------------

    def create_screener(
        self,
        *,
        name: str,
        description: str | None,
        version: ScreenerVersion,
        tags: tuple[str, ...] = (),
    ) -> tuple[Screener, ScreenerVersion]:
        if not name.strip():
            raise ScreenerValidationError("screener name is required")
        _validate_version(version)
        screener_id = version.screener_id
        screener = Screener(
            id=screener_id,
            name=name.strip(),
            description=description,
            tags=tags,
            version_count=1,
            latest_version_id=version.id,
        )
        self._store.save_screener(screener)
        self._store.save_version(version)
        return screener, version

    def add_version(
        self,
        screener_id: UUID,
        *,
        name: str,
        version_payload: ScreenerVersion,
    ) -> ScreenerVersion:
        _validate_version(version_payload)
        existing_versions = self._store.list_versions(screener_id)
        next_number = (existing_versions[-1].version + 1) if existing_versions else 1
        new_version = version_payload.model_copy(
            update={
                "id": uuid4(),
                "screener_id": screener_id,
                "version": next_number,
                "name": name.strip(),
                "created_at": datetime.now(timezone.utc),
            }
        )
        self._store.save_version(new_version)
        screener = self._store.get_screener(screener_id)
        self._store.save_screener(
            screener.model_copy(
                update={
                    "version_count": len(existing_versions) + 1,
                    "latest_version_id": new_version.id,
                }
            )
        )
        return new_version

    def list_screeners(self) -> tuple[Screener, ...]:
        return self._store.list_screeners()

    def get_screener(self, screener_id: UUID) -> tuple[Screener, tuple[ScreenerVersion, ...]]:
        return self._store.get_screener(screener_id), self._store.list_versions(screener_id)

    def archive_screener(self, screener_id: UUID) -> Screener:
        screener = self._store.get_screener(screener_id)
        archived = screener.model_copy(update={"status": "archived"})
        return self._store.save_screener(archived)

    def delete_screener(self, screener_id: UUID) -> None:
        run_count = len(self._store.list_runs(screener_id=screener_id, limit=1))
        if run_count:
            raise ScreenerValidationError(
                "screener has run history; archive it instead of deleting audit evidence"
            )
        self._store.delete_screener(screener_id)

    # ---------------- Run ---------------------------------------------

    def run_screener(
        self,
        screener_id: UUID,
        *,
        version_id: UUID | None = None,
        operator_session_id: str | None = None,
        run_kind: str = "run",
        parent_run_id: UUID | None = None,
    ) -> ScreenerRun:
        screener = self._store.get_screener(screener_id)
        if version_id is None:
            version = self._store.latest_version(screener_id)
            if version is None:
                raise ScreenerValidationError(
                    f"screener {screener_id} has no versions to run",
                )
        else:
            version = self._store.get_version(version_id)
            if version.screener_id != screener_id:
                raise ScreenerValidationError(
                    "version does not belong to this screener; run blocked to preserve lineage"
                )

        _validate_version(version)
        started = datetime.now(timezone.utc)
        run = ScreenerRun(
            id=uuid4(),
            screener_id=screener_id,
            screener_version_id=version.id,
            started_at=started,
            status=ScreenerRunStatus.RUNNING,
            run_kind=run_kind,  # type: ignore[arg-type]
            parent_run_id=parent_run_id,
            operator_session_id=operator_session_id,
            audit_events=(
                {
                    "type": "screener_run_started",
                    "screener_id": str(screener_id),
                    "screener_version_id": str(version.id),
                    "run_kind": run_kind,
                    "at": started.isoformat(),
                },
            ),
        )
        self._store.save_run(run)

        try:
            universe = self._universe.resolve(version.universe_source)
        except Exception as exc:  # noqa: BLE001
            run = run.model_copy(
                update={
                    "status": ScreenerRunStatus.FAILED,
                    "completed_at": datetime.now(timezone.utc),
                    "error": f"universe resolution failed: {exc}",
                }
            )
            self._store.save_run(run)
            return run

        results: list[ScreenerResultRow] = []
        cache_hits = 0
        attempts = 0
        expression = _expression_for_version(version)
        criteria = _criteria_for_version(version)
        for symbol in universe.symbols:
            attempts += 1
            snapshot = self._metrics.compute(
                symbol=symbol,
                timeframe=version.timeframe,
                criteria=criteria,
                as_of=started,
            )
            evaluation = _evaluate_expression(snapshot.metrics, expression)
            matched = evaluation.matched and bool(snapshot.metrics)
            score = _score(snapshot.metrics, version.sort_metric)
            results.append(
                ScreenerResultRow(
                    symbol=symbol,
                    matched=matched,
                    metrics={k: _round_or_none(v) for k, v in snapshot.metrics.items()},
                    failed_criteria=evaluation.failed,
                    passed_criteria=evaluation.passed,
                    blocked_reasons=_blocked_reasons(snapshot.metrics, criteria),
                    score=score,
                    sparkline=tuple(_round(v) for v in snapshot.sparkline),
                    evidence=snapshot.evidence or {},
                )
            )
            if snapshot.metrics and "error" not in (snapshot.evidence or {}):
                cache_hits += 1

        results.sort(
            key=lambda row: (
                0 if row.matched else 1,
                _score_for_sort(row.score, version.sort_descending),
                row.symbol,
            )
        )
        results = results[: version.max_results]

        cache_hit_rate = (cache_hits / attempts) if attempts > 0 else None
        completed = datetime.now(timezone.utc)
        run = run.model_copy(
            update={
                "status": ScreenerRunStatus.COMPLETED,
                "completed_at": completed,
                "universe_size": len(universe.symbols),
                "matched_count": sum(1 for r in results if r.matched),
                "results": tuple(results),
                "sources_used": tuple(
                    dict.fromkeys((universe.source_label, "Alpaca/Data Center bar cache"))
                ),
                "source_evidence": universe.evidence or {},
                "source_freshness": (universe.evidence or {}).get("freshness", {}) if universe.evidence else {},
                "cache_hit_rate": round(cache_hit_rate, 4) if cache_hit_rate is not None else None,
                "audit_events": (
                    *run.audit_events,
                    {
                        "type": "screener_run_completed",
                        "matched_count": sum(1 for r in results if r.matched),
                        "universe_size": len(universe.symbols),
                        "at": completed.isoformat(),
                    },
                ),
            }
        )
        self._store.save_run(run)
        self._store.update_last_run(screener_id, run, completed)
        return run

    # ---------------- Read --------------------------------------------

    def get_run(self, run_id: UUID) -> ScreenerRun:
        return self._store.get_run(run_id)

    def list_runs(self, *, screener_id: UUID | None = None, limit: int = 50) -> tuple[ScreenerRun, ...]:
        return self._store.list_runs(screener_id=screener_id, limit=limit)

    def rerun(self, run_id: UUID, *, operator_session_id: str | None = None) -> ScreenerRun:
        previous = self._store.get_run(run_id)
        return self.run_screener(
            previous.screener_id,
            version_id=previous.screener_version_id,
            operator_session_id=operator_session_id,
            run_kind="rerun",
            parent_run_id=run_id,
        )

    def diff_runs(self, run_id: UUID, *, against_run_id: UUID) -> dict[str, object]:
        current = self._store.get_run(run_id)
        against = self._store.get_run(against_run_id)
        current_by_symbol = {row.symbol: row for row in current.results if row.matched}
        against_by_symbol = {row.symbol: row for row in against.results if row.matched}
        current_symbols = set(current_by_symbol)
        against_symbols = set(against_by_symbol)
        stayed = current_symbols & against_symbols
        reason_changes = []
        for symbol in sorted(stayed):
            before = against_by_symbol[symbol]
            after = current_by_symbol[symbol]
            if before.metrics != after.metrics or before.failed_criteria != after.failed_criteria:
                reason_changes.append(
                    {
                        "symbol": symbol,
                        "before_metrics": before.metrics,
                        "after_metrics": after.metrics,
                        "before_failed_criteria": before.failed_criteria,
                        "after_failed_criteria": after.failed_criteria,
                    }
                )
        newly_failed = tuple(
            row.symbol
            for row in current.results
            if not row.matched and row.symbol in against_symbols
        )
        return {
            "run_id": str(run_id),
            "against_run_id": str(against_run_id),
            "added": tuple(sorted(current_symbols - against_symbols)),
            "removed": tuple(sorted(against_symbols - current_symbols)),
            "stayed": tuple(sorted(stayed)),
            "newly_failed": newly_failed,
            "reason_changes": tuple(reason_changes),
        }


# ---------------- Pure helpers ----------------------------------------


class _ExpressionEvaluation:
    def __init__(
        self,
        *,
        matched: bool,
        passed: tuple[str, ...] = (),
        failed: tuple[str, ...] = (),
    ) -> None:
        self.matched = matched
        self.passed = passed
        self.failed = failed


def _criteria_for_version(version: ScreenerVersion) -> tuple[ScreenerCriterion, ...]:
    if version.expression is None:
        return version.criteria
    return _flatten_expression_criteria(version.expression)


def _flatten_expression_criteria(expression: ScreenerExpression) -> tuple[ScreenerCriterion, ...]:
    if expression.kind == ScreenerExpressionKind.CRITERION:
        return (expression.criterion,) if expression.criterion is not None else ()
    criteria: list[ScreenerCriterion] = []
    for child in expression.children:
        criteria.extend(_flatten_expression_criteria(child))
    return tuple(criteria)


def _expression_for_version(version: ScreenerVersion) -> ScreenerExpression:
    if version.expression is not None:
        return version.expression
    return ScreenerExpression(
        kind=ScreenerExpressionKind.ALL,
        children=tuple(
            ScreenerExpression(kind=ScreenerExpressionKind.CRITERION, criterion=criterion)
            for criterion in version.criteria
        ),
    )


def _evaluate_expression(
    metrics: dict[str, bool | float | str | None],
    expression: ScreenerExpression,
) -> _ExpressionEvaluation:
    if expression.kind == ScreenerExpressionKind.CRITERION:
        criterion = expression.criterion
        if criterion is None:
            return _ExpressionEvaluation(matched=False, failed=("invalid criterion",))
        label = _default_criterion_label(criterion)
        value = metrics.get(criterion.metric.value)
        label = criterion.label or label
        if value is None:
            return _ExpressionEvaluation(matched=False, failed=(f"{label} (metric unavailable)",))
        if _criterion_matches(value, criterion):
            return _ExpressionEvaluation(matched=True, passed=(label,))
        return _ExpressionEvaluation(matched=False, failed=(label,))

    child_results = tuple(_evaluate_expression(metrics, child) for child in expression.children)
    if expression.kind == ScreenerExpressionKind.ALL:
        matched = all(result.matched for result in child_results)
    elif expression.kind == ScreenerExpressionKind.ANY:
        matched = any(result.matched for result in child_results)
    elif expression.kind == ScreenerExpressionKind.NOT:
        matched = not child_results[0].matched if child_results else False
    else:
        matched = False
    passed = tuple(label for result in child_results for label in result.passed)
    failed = tuple(label for result in child_results for label in result.failed)
    if expression.kind == ScreenerExpressionKind.NOT and child_results:
        passed, failed = failed, passed
    return _ExpressionEvaluation(matched=matched, passed=passed, failed=failed if not matched else ())


def _criterion_matches(value: bool | float | str, c: ScreenerCriterion) -> bool:
    op = c.operator
    if op == ScreenerCriterionOperator.GTE:
        return isinstance(value, int | float) and isinstance(c.value, int | float) and value >= c.value
    if op == ScreenerCriterionOperator.GT:
        return isinstance(value, int | float) and isinstance(c.value, int | float) and value > c.value
    if op == ScreenerCriterionOperator.LTE:
        return isinstance(value, int | float) and isinstance(c.value, int | float) and value <= c.value
    if op == ScreenerCriterionOperator.LT:
        return isinstance(value, int | float) and isinstance(c.value, int | float) and value < c.value
    if op == ScreenerCriterionOperator.EQ:
        return _normalize_eq(value) == _normalize_eq(c.value)
    if op == ScreenerCriterionOperator.BETWEEN:
        upper = c.value_max if c.value_max is not None else c.value
        return (
            isinstance(value, int | float)
            and isinstance(c.value, int | float)
            and isinstance(upper, int | float)
            and c.value <= value <= upper
        )
    return False


def _default_criterion_label(c: ScreenerCriterion) -> str:
    op = c.operator.value
    metric = get_field_definition(c.metric).label
    if c.operator == ScreenerCriterionOperator.BETWEEN:
        return f"{metric} between {c.value} and {c.value_max}"
    return f"{metric} {op} {c.value}"


def _score(metrics: dict[str, bool | float | str | None], sort_metric: ScreenerMetric | None) -> float | None:
    if sort_metric is None:
        return None
    value = metrics.get(sort_metric.value)
    return float(value) if isinstance(value, int | float) else None


def _score_for_sort(score: float | None, descending: bool) -> float:
    if score is None:
        # Push None scores to the bottom regardless of direction.
        return float("inf")
    return -score if descending else score


def _round(value: float) -> float:
    return round(value, 4)


def _round_or_none(value: bool | float | str | None) -> bool | float | str | None:
    if isinstance(value, bool | str) or value is None:
        return value
    return round(value, 4) if value is not None else None


def _validate_version(version: ScreenerVersion) -> None:
    criteria = _criteria_for_version(version)
    for criterion in criteria:
        definition = get_field_definition(criterion.metric)
        if criterion.operator not in definition.supported_operators:
            raise ScreenerValidationError(
                f"{definition.label} does not support operator {criterion.operator.value}"
            )
        if criterion.operator == ScreenerCriterionOperator.BETWEEN and definition.value_type.value != "number":
            raise ScreenerValidationError(f"{definition.label} does not support BETWEEN")


def _blocked_reasons(
    metrics: dict[str, bool | float | str | None],
    criteria: tuple[ScreenerCriterion, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    broker_fields = {
        ScreenerMetric.BROKER_TRADABLE: (
            "asset is not tradable at Alpaca",
            "Alpaca tradability evidence unavailable",
        ),
        ScreenerMetric.BROKER_FRACTIONABLE: (
            "asset is not fractionable at Alpaca",
            "Alpaca fractionability evidence unavailable",
        ),
        ScreenerMetric.BROKER_SHORTABLE: (
            "asset is not shortable at Alpaca",
            "Alpaca shortability evidence unavailable",
        ),
        ScreenerMetric.BROKER_EASY_TO_BORROW: (
            "asset is not easy to borrow at Alpaca",
            "Alpaca easy-to-borrow evidence unavailable",
        ),
        ScreenerMetric.BROKER_ACTIVE: (
            "asset is not active at Alpaca",
            "Alpaca active-asset evidence unavailable",
        ),
    }
    for criterion in criteria:
        reason_pair = broker_fields.get(criterion.metric)
        if reason_pair is None:
            continue
        false_reason, unavailable_reason = reason_pair
        expected_true = _normalize_eq(criterion.value) is True
        actual = _normalize_eq(metrics.get(criterion.metric.value))
        if expected_true and actual is not True:
            reasons.append(false_reason if actual is not None else unavailable_reason)
    return tuple(dict.fromkeys(reasons))


def _normalize_eq(value: object) -> object:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        return lowered
    return value
