"""Tests for compile_for_storage / load_compiled storage helpers."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.strategies.expression_engine import (
    CompiledExpr,
    FeatureSnapshot,
    compile,
    evaluate,
    parse,
    validate,
    default_catalog,
)
from backend.app.strategies.expression_api import compile_for_storage, load_compiled


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _compile_src(src: str) -> CompiledExpr:
    ast = parse(src)
    vast = validate(ast, default_catalog())
    return compile(vast)


def _snapshot() -> FeatureSnapshot:
    """Synthetic snapshot for 5m.ema(9) crosses_above 5m.ema(21)."""
    now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return FeatureSnapshot(
        timestamp=now,
        values={"5m.ema(9)": 102.0, "5m.ema(21)": 100.0},
        history={
            "5m.ema(9)":  (102.0, 99.0),   # current > prev
            "5m.ema(21)": (100.0, 101.0),  # current < prev (crossed above)
        },
        variables={},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_round_trip_produces_same_result() -> None:
    src = "5m.ema(9) crosses_above 5m.ema(21)"
    original = _compile_src(src)
    snapshot = _snapshot()

    expected = evaluate(original, snapshot)

    blob = compile_for_storage(original)
    assert isinstance(blob, bytes)
    assert len(blob) > 0

    recovered = load_compiled(src, blob)
    assert isinstance(recovered, CompiledExpr)
    assert evaluate(recovered, snapshot) == expected


def test_schema_drift_fallback_corrupt_bytes() -> None:
    """load_compiled must recover via text re-parse when blob is garbage."""
    src = "5m.ema(9) crosses_above 5m.ema(21)"
    corrupt = b"not-a-pickle"

    recovered = load_compiled(src, corrupt)
    assert isinstance(recovered, CompiledExpr)

    snapshot = _snapshot()
    result = evaluate(recovered, snapshot)
    assert isinstance(result, (bool, float))


def test_schema_drift_fallback_partial_pickle() -> None:
    """load_compiled must recover from a truncated / protocol-mismatch pickle."""
    src = "5m.ema(9) crosses_above 5m.ema(21)"
    corrupt = b"\x80\x04bogus_data_that_will_not_unpickle"

    recovered = load_compiled(src, corrupt)
    assert isinstance(recovered, CompiledExpr)


def test_blob_none_uses_text_fallback() -> None:
    """When blob=None, load_compiled should parse and compile from text."""
    src = "5m.ema(9) crosses_above 5m.ema(21)"
    recovered = load_compiled(src, None)
    assert isinstance(recovered, CompiledExpr)

    snapshot = _snapshot()
    result = evaluate(recovered, snapshot)
    assert isinstance(result, (bool, float))


def test_compile_for_storage_returns_bytes() -> None:
    src = "5m.rsi(14) > 50"
    cexpr = _compile_src(src)
    blob = compile_for_storage(cexpr)
    assert isinstance(blob, bytes)
    assert len(blob) > 0


def test_round_trip_numeric_comparison() -> None:
    src = "5m.rsi(14) > 50"
    cexpr = _compile_src(src)
    blob = compile_for_storage(cexpr)
    recovered = load_compiled(src, blob)

    now = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    snapshot = FeatureSnapshot(
        timestamp=now,
        values={"5m.rsi(14)": 60.0},
        history={"5m.rsi(14)": (60.0,)},
        variables={},
    )
    assert evaluate(recovered, snapshot) is True or evaluate(recovered, snapshot) == 1.0
