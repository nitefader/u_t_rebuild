"""StrategyV4Service — validation, save, load, duplicate, delete."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyIdentityV4,
    StrategyLegV4,
    StrategyLogicalExitV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVariableV4,
    StrategyVersionV4,
    ValidationStatusV4,
)
from backend.app.strategies.expression_engine import (
    CANONICAL_TIMEFRAMES,
    CANONICAL_TIMEFRAMES_ORDER,
)
from backend.app.strategies.expression_api import validate_expression
from backend.app.strategies_v4.models import (
    StrategyEntriesV4Draft,
    StrategyVersionV4Draft,
)
from backend.app.strategies_v4.persistence import (
    StrategyV4Repository,
    StrategyV4ValidationError,
    StrategyV4VersionNotFoundError,
)


DEFAULT_ATR_FEATURE_REF = "atr:length=14[0]"


def _simple_stop_feature_requirements(stop: object) -> tuple[str, ...]:
    if getattr(stop, "mode", None) == "simple" and getattr(stop, "simple_type", None) == "ATR":
        return (DEFAULT_ATR_FEATURE_REF,)
    return ()


def _leg_feature_requirements(leg: object) -> tuple[str, ...]:
    refs: list[str] = []
    target_type = getattr(leg, "target_type", None)
    if target_type in {"ATR", "trail-ATR"}:
        refs.append(DEFAULT_ATR_FEATURE_REF)
    on_fill_action = getattr(leg, "on_fill_action", None)
    if getattr(on_fill_action, "kind", None) == "tighten_atr":
        refs.append(DEFAULT_ATR_FEATURE_REF)
    return tuple(dict.fromkeys(refs))


class StrategyV4InUseError(RuntimeError):
    """Raised when attempting to delete a strategy that is bound by one or more
    active Deployments."""

    def __init__(self, *, deployment_ids: list[str]) -> None:
        super().__init__(
            f"strategy is bound by {len(deployment_ids)} deployment(s): "
            + ", ".join(deployment_ids)
        )
        self.deployment_ids = deployment_ids


class StrategyV4Service:

    def __init__(self, repository: StrategyV4Repository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # validate_draft — no persist
    # ------------------------------------------------------------------

    def validate_draft(self, draft: StrategyVersionV4Draft) -> ValidationStatusV4:
        """Validate all expressions. Returns status without saving."""
        errors: list[str] = []
        warnings: list[str] = []

        # variables
        for idx, var in enumerate(draft.variables):
            if var.kind == "timeframe":
                lit = var.expression_text.strip()
                if lit not in CANONICAL_TIMEFRAMES:
                    opts = ", ".join(CANONICAL_TIMEFRAMES_ORDER)
                    errors.append(
                        f"variable '{var.name}': timeframe must be one of {opts}, "
                        f"got {lit!r}"
                    )
                continue

            preceding_expr = [
                v.name for v in draft.variables[:idx] if v.kind == "expression"
            ]
            preceding_tf = frozenset(
                v.name for v in draft.variables[:idx] if v.kind == "timeframe"
            )

            result = validate_expression(
                var.expression_text,
                preceding_expr,
                timeframe_variable_names=preceding_tf,
            )
            for e in result.errors:
                errors.append(f"variable '{var.name}': {e.message}")
            for w in result.warnings:
                warnings.append(f"variable '{var.name}': {w.message}")

        expr_names_all = [v.name for v in draft.variables if v.kind == "expression"]
        tf_names_all = frozenset(v.name for v in draft.variables if v.kind == "timeframe")

        # entries
        if draft.entries.long is not None:
            result = validate_expression(
                draft.entries.long.expression_text,
                expr_names_all,
                timeframe_variable_names=tf_names_all,
            )
            for e in result.errors:
                errors.append(f"entry.long: {e.message}")
            for w in result.warnings:
                warnings.append(f"entry.long: {w.message}")

        if draft.entries.short is not None:
            result = validate_expression(
                draft.entries.short.expression_text,
                expr_names_all,
                timeframe_variable_names=tf_names_all,
            )
            for e in result.errors:
                errors.append(f"entry.short: {e.message}")
            for w in result.warnings:
                warnings.append(f"entry.short: {w.message}")

        # stops (expression mode only)
        for idx, stop in enumerate(draft.stops):
            if stop.mode == "expression" and stop.expression_text:
                result = validate_expression(
                    stop.expression_text,
                    expr_names_all,
                    timeframe_variable_names=tf_names_all,
                )
                for e in result.errors:
                    errors.append(f"stop[{idx}]: {e.message}")
                for w in result.warnings:
                    warnings.append(f"stop[{idx}]: {w.message}")

        return ValidationStatusV4(
            valid=len(errors) == 0,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # save
    # ------------------------------------------------------------------

    def save(
        self,
        draft: StrategyVersionV4Draft,
        *,
        strategy_v4_id: UUID | None = None,
    ) -> StrategyVersionV4:
        """Create (strategy_v4_id=None) or append a new version."""
        status = self.validate_draft(draft)
        if not status.valid:
            raise StrategyV4ValidationError(
                f"draft has {len(status.errors)} error(s): {'; '.join(status.errors)}"
            )

        is_create = strategy_v4_id is None
        actual_strategy_id = strategy_v4_id if strategy_v4_id is not None else uuid4()
        version_num = self._repo.next_version_number(actual_strategy_id)

        # aggregate feature requirements
        feat_keys: set[str] = set()

        vars_domain: list[StrategyVariableV4] = []
        for idx, var in enumerate(draft.variables):
            if var.kind == "timeframe":
                vars_domain.append(
                    StrategyVariableV4(
                        name=var.name,
                        expression_text=var.expression_text,
                        kind="timeframe",
                        feature_requirements=(),
                    )
                )
                continue

            preceding_expr = [
                v.name for v in draft.variables[:idx] if v.kind == "expression"
            ]
            preceding_tf = frozenset(
                v.name for v in draft.variables[:idx] if v.kind == "timeframe"
            )
            result = validate_expression(
                var.expression_text,
                preceding_expr,
                timeframe_variable_names=preceding_tf,
            )
            keys = [f.key for f in result.feature_requirements]
            feat_keys.update(keys)
            vars_domain.append(
                StrategyVariableV4(
                    name=var.name,
                    expression_text=var.expression_text,
                    kind="expression",
                    feature_requirements=tuple(keys),
                )
            )

        expr_names_all = [v.name for v in draft.variables if v.kind == "expression"]
        tf_names_all = frozenset(v.name for v in draft.variables if v.kind == "timeframe")

        long_entry: StrategyEntryV4 | None = None
        short_entry: StrategyEntryV4 | None = None

        if draft.entries.long is not None:
            result = validate_expression(
                draft.entries.long.expression_text,
                expr_names_all,
                timeframe_variable_names=tf_names_all,
            )
            keys = [f.key for f in result.feature_requirements]
            feat_keys.update(keys)
            long_entry = StrategyEntryV4(
                expression_text=draft.entries.long.expression_text,
                feature_requirements=tuple(keys),
            )

        if draft.entries.short is not None:
            result = validate_expression(
                draft.entries.short.expression_text,
                expr_names_all,
                timeframe_variable_names=tf_names_all,
            )
            keys = [f.key for f in result.feature_requirements]
            feat_keys.update(keys)
            short_entry = StrategyEntryV4(
                expression_text=draft.entries.short.expression_text,
                feature_requirements=tuple(keys),
            )

        stops_domain: list[StrategyStopV4] = []
        for stop in draft.stops:
            stop_feat: list[str] = list(_simple_stop_feature_requirements(stop))
            feat_keys.update(stop_feat)
            if stop.mode == "expression" and stop.expression_text:
                result = validate_expression(
                    stop.expression_text,
                    expr_names_all,
                    timeframe_variable_names=tf_names_all,
                )
                stop_feat = [f.key for f in result.feature_requirements]
                feat_keys.update(stop_feat)
            stops_domain.append(
                StrategyStopV4(
                    id=stop.id,
                    mode=stop.mode,
                    scope=stop.scope,
                    simple_type=stop.simple_type,
                    simple_value=stop.simple_value,
                    expression_text=stop.expression_text,
                    feature_requirements=tuple(stop_feat),
                )
            )

        legs_domain: list[StrategyLegV4] = []
        for leg in draft.legs:
            feat_keys.update(_leg_feature_requirements(leg))
            legs_domain.append(
                StrategyLegV4(
                    id=leg.id,
                    position=leg.position,
                    kind=leg.kind,
                    size_pct=leg.size_pct,
                    target_type=leg.target_type,
                    target_value=leg.target_value,
                    on_fill_action=OnFillActionV4(
                        kind=leg.on_fill_action.kind,
                        offset_value=leg.on_fill_action.offset_value,
                    ),
                )
            )

        long_exits = [
            StrategyLogicalExitV4(
                id=ex.id,
                template_id=ex.template_id,
                params=dict(ex.params),
            )
            for ex in draft.logical_exits.long
        ]
        short_exits = [
            StrategyLogicalExitV4(
                id=ex.id,
                template_id=ex.template_id,
                params=dict(ex.params),
            )
            for ex in draft.logical_exits.short
        ]

        version = StrategyVersionV4(
            id=uuid4(),
            strategy_v4_id=actual_strategy_id,
            version=version_num,
            name=draft.name,
            description=draft.description,
            identity=StrategyIdentityV4(
                tags=tuple(draft.identity.tags),
                direction=draft.identity.direction,
            ),
            default_strategy_controls_version_id=draft.default_strategy_controls_version_id,
            default_execution_plan_version_id=draft.default_execution_plan_version_id,
            variables=tuple(vars_domain),
            entries=StrategyEntriesV4(long=long_entry, short=short_entry),
            stops=tuple(stops_domain),
            legs=tuple(legs_domain),
            logical_exits=StrategyLogicalExitsV4(
                long=tuple(long_exits),
                short=tuple(short_exits),
            ),
            feature_requirements=tuple(sorted(feat_keys)),
            validation_status=status,
            created_at=datetime.now(timezone.utc),
        )
        self._repo.save_version(version)
        return version

    # ------------------------------------------------------------------
    # get / list
    # ------------------------------------------------------------------

    def get(self, strategy_version_v4_id: UUID) -> StrategyVersionV4:
        return self._repo.load_version(strategy_version_v4_id)

    def list(self, strategy_v4_id: UUID) -> tuple[StrategyVersionV4, ...]:
        return self._repo.list_versions(strategy_v4_id)

    def list_all_heads(self) -> list[dict]:
        """Return one summary row per strategy (the head version)."""
        return self._repo.list_all_heads()

    # ------------------------------------------------------------------
    # duplicate
    # ------------------------------------------------------------------

    def duplicate(
        self, source_version_v4_id: UUID, *, new_name: str
    ) -> StrategyVersionV4:
        source = self._repo.load_version(source_version_v4_id)
        new_strategy_id = uuid4()

        # Build draft from source
        from backend.app.strategies_v4.models import (
            OnFillActionV4Draft,
            StrategyEntriesV4Draft,
            StrategyEntryV4Draft,
            StrategyIdentityV4Draft,
            StrategyLegV4Draft,
            StrategyLogicalExitV4Draft,
            StrategyLogicalExitsV4Draft,
            StrategyStopV4Draft,
            StrategyVariableV4Draft,
            StrategyVersionV4Draft,
        )

        draft = StrategyVersionV4Draft(
            name=new_name,
            description=source.description,
            identity=StrategyIdentityV4Draft(
                tags=list(source.identity.tags),
                direction=source.identity.direction,
            ),
            default_strategy_controls_version_id=source.default_strategy_controls_version_id,
            default_execution_plan_version_id=source.default_execution_plan_version_id,
            variables=[
                StrategyVariableV4Draft(
                    name=v.name,
                    expression_text=v.expression_text,
                    kind=v.kind,
                )
                for v in source.variables
            ],
            entries=StrategyEntriesV4Draft(
                long=(
                    StrategyEntryV4Draft(expression_text=source.entries.long.expression_text)
                    if source.entries.long
                    else None
                ),
                short=(
                    StrategyEntryV4Draft(expression_text=source.entries.short.expression_text)
                    if source.entries.short
                    else None
                ),
            ),
            stops=[
                StrategyStopV4Draft(
                    id=uuid4(),
                    mode=s.mode,
                    scope=s.scope,
                    simple_type=s.simple_type,
                    simple_value=s.simple_value,
                    expression_text=s.expression_text,
                )
                for s in source.stops
            ],
            legs=[
                StrategyLegV4Draft(
                    id=uuid4(),
                    position=l.position,
                    kind=l.kind,
                    size_pct=l.size_pct,
                    target_type=l.target_type,
                    target_value=l.target_value,
                    on_fill_action=OnFillActionV4Draft(
                        kind=l.on_fill_action.kind,
                        offset_value=l.on_fill_action.offset_value,
                    ),
                )
                for l in source.legs
            ],
            logical_exits=StrategyLogicalExitsV4Draft(
                long=[
                    StrategyLogicalExitV4Draft(
                        id=uuid4(),
                        template_id=ex.template_id,
                        params=dict(ex.params),
                    )
                    for ex in source.logical_exits.long
                ],
                short=[
                    StrategyLogicalExitV4Draft(
                        id=uuid4(),
                        template_id=ex.template_id,
                        params=dict(ex.params),
                    )
                    for ex in source.logical_exits.short
                ],
            ),
        )
        return self.save(draft, strategy_v4_id=new_strategy_id)

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def delete(self, strategy_v4_id: UUID, *, deployment_repo=None) -> None:
        """Delete an entire strategy (all versions).

        Raises ``StrategyV4InUseError`` if any version is currently bound by a
        Deployment. Pass a ``DeploymentRepository`` instance via
        ``deployment_repo`` to enable this guard (required in production; tests
        may omit it to exercise isolated service behaviour).
        """
        if deployment_repo is not None:
            version_ids = {
                v.id
                for v in self._repo.list_versions(strategy_v4_id)
            }
            if version_ids:
                bound = deployment_repo.list_deployments_for_strategy_v4_versions(
                    version_ids
                )
                if bound:
                    raise StrategyV4InUseError(
                        deployment_ids=[
                            str(d.deployment_id) for d in bound
                        ]
                    )
        self._repo.delete_strategy(strategy_v4_id)
