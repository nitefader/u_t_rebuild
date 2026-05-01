"""Tests for new ExecutionPlan retry/cancel fields (A.5)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.domain.execution_style import (
    ExecutionMode,
    OrderCancelPolicy,
    OrderRetryPolicy,
    OrderType,
    TimeInForce,
)
from backend.app.execution_plans.persistence import ExecutionPlanRepository
from backend.app.execution_plans.registry import ExecutionPlanRegistry
from backend.app.execution_plans.service import ExecutionPlanService
from backend.app.execution_plans.service_models import ExecutionPlanDraft
from backend.app.deployments.persistence import DeploymentRepository


def _make_service(tmp_path: Path) -> ExecutionPlanService:
    db = tmp_path / "test.db"
    return ExecutionPlanService(
        repository=ExecutionPlanRepository(db),
        registry=ExecutionPlanRegistry(db),
        deployment_repository=DeploymentRepository(db),
    )


def _base_draft(**overrides) -> ExecutionPlanDraft:
    defaults = dict(
        name="Retry Test",
        entry_order_type=OrderType.MARKET,
        exit_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
    )
    defaults.update(overrides)
    return ExecutionPlanDraft(**defaults)


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

def test_defaults_are_none() -> None:
    d = _base_draft()
    assert d.order_retry_policy == OrderRetryPolicy.NONE
    assert d.order_cancel_policy == OrderCancelPolicy.HOLD
    assert d.order_retry_max_attempts is None
    assert d.order_retry_offset_bps is None


def test_reprice_once_requires_both_fields() -> None:
    d = _base_draft(
        order_retry_policy=OrderRetryPolicy.REPRICE_ONCE,
        order_retry_max_attempts=3,
        order_retry_offset_bps=5.0,
    )
    assert d.order_retry_policy == OrderRetryPolicy.REPRICE_ONCE
    assert d.order_retry_max_attempts == 3
    assert d.order_retry_offset_bps == 5.0


def test_reprice_once_missing_max_attempts_rejected() -> None:
    with pytest.raises(ValidationError, match="order_retry_max_attempts is required"):
        _base_draft(
            order_retry_policy=OrderRetryPolicy.REPRICE_ONCE,
            order_retry_offset_bps=5.0,
        )


def test_reprice_once_missing_offset_bps_rejected() -> None:
    with pytest.raises(ValidationError, match="order_retry_offset_bps is required"):
        _base_draft(
            order_retry_policy=OrderRetryPolicy.REPRICE_ONCE,
            order_retry_max_attempts=3,
        )


def test_none_policy_with_max_attempts_rejected() -> None:
    with pytest.raises(ValidationError, match="order_retry_max_attempts must be None"):
        _base_draft(
            order_retry_policy=OrderRetryPolicy.NONE,
            order_retry_max_attempts=3,
        )


def test_none_policy_with_offset_bps_rejected() -> None:
    with pytest.raises(ValidationError, match="order_retry_offset_bps must be None"):
        _base_draft(
            order_retry_policy=OrderRetryPolicy.NONE,
            order_retry_offset_bps=5.0,
        )


def test_cancel_on_opposite_signal() -> None:
    d = _base_draft(order_cancel_policy=OrderCancelPolicy.CANCEL_ON_OPPOSITE_SIGNAL)
    assert d.order_cancel_policy == OrderCancelPolicy.CANCEL_ON_OPPOSITE_SIGNAL


def test_reprice_until_filled() -> None:
    d = _base_draft(
        order_retry_policy=OrderRetryPolicy.REPRICE_UNTIL_FILLED,
        order_retry_max_attempts=10,
        order_retry_offset_bps=2.5,
    )
    assert d.order_retry_policy == OrderRetryPolicy.REPRICE_UNTIL_FILLED


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

def test_roundtrip_retry_fields(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _base_draft(
        order_retry_policy=OrderRetryPolicy.REPRICE_ONCE,
        order_cancel_policy=OrderCancelPolicy.CANCEL_AFTER_BARS,
        order_retry_max_attempts=3,
        order_retry_offset_bps=5.0,
    )
    record = svc.create(draft.name, draft)
    loaded = svc.get_library(record.payload.execution_style_id).head.payload

    assert loaded.order_retry_policy == OrderRetryPolicy.REPRICE_ONCE
    assert loaded.order_cancel_policy == OrderCancelPolicy.CANCEL_AFTER_BARS
    assert loaded.order_retry_max_attempts == 3
    assert loaded.order_retry_offset_bps == 5.0


def test_roundtrip_default_retry_fields(tmp_path: Path) -> None:
    svc = _make_service(tmp_path)
    draft = _base_draft()
    record = svc.create(draft.name, draft)
    loaded = svc.get_library(record.payload.execution_style_id).head.payload

    assert loaded.order_retry_policy == OrderRetryPolicy.NONE
    assert loaded.order_cancel_policy == OrderCancelPolicy.HOLD
    assert loaded.order_retry_max_attempts is None
    assert loaded.order_retry_offset_bps is None
