"""Tests for the expression engine validator."""
from __future__ import annotations

import pytest

from backend.app.strategies.expression_engine import CANONICAL_TIMEFRAMES_ORDER
from backend.app.strategies.expression_engine.ast_nodes import (
    FeatureRef,
    NumberLit,
    TimeframedFeature,
)
from backend.app.strategies.expression_engine.errors import ValidationError
from backend.app.strategies.expression_engine.features import default_catalog
from backend.app.strategies.expression_engine.parser import parse
from backend.app.strategies.expression_engine.validator import validate


# ---------------------------------------------------------------------------
# Happy-path: valid expressions
# ---------------------------------------------------------------------------

def test_valid_ema_crossover():
    ast = parse("5m.ema(9) crosses_above 5m.ema(21)")
    vast = validate(ast, default_catalog())
    assert vast.root is ast


def test_valid_session_feature():
    ast = parse("session.is_open AND session.minutes_since_open > 15")
    vast = validate(ast, default_catalog())
    assert len(vast.feature_requirements) > 0


def test_valid_orb_feature():
    ast = parse("5m.close > orb.high(15)")
    vast = validate(ast, default_catalog())


def test_valid_prior_day_feature():
    ast = parse("5m.close > prior_day.close * 1.02")
    vast = validate(ast, default_catalog())


def test_valid_bar_lookback():
    ast = parse("5m.close > bar[-1].high")
    vast = validate(ast, default_catalog())
    # Should have bar FeatureRef in requirements
    bar_reqs = [r for r in vast.feature_requirements if isinstance(r, FeatureRef) and r.bar_offset is not None]
    assert len(bar_reqs) == 1


def test_feature_requirements_deduped():
    # Same feature used twice
    ast = parse("5m.ema(9) > 5m.ema(9)")
    vast = validate(ast, default_catalog())
    # Should appear only once
    ema_reqs = [r for r in vast.feature_requirements
                if isinstance(r, TimeframedFeature) and r.name == "ema"]
    assert len(ema_reqs) == 1


def test_feature_requirements_multiple():
    ast = parse("5m.ema(9) > 5m.ema(21) AND 5m.rsi(14) < 70")
    vast = validate(ast, default_catalog())
    names = {r.name for r in vast.feature_requirements if isinstance(r, TimeframedFeature)}
    assert "ema" in names
    assert "rsi" in names


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

def test_valid_variable_ref():
    ast = parse("my_var > 100")
    vast = validate(ast, default_catalog(), variable_names=["my_var"])
    assert "my_var" in vast.variables_used


def test_variables_used_deduped():
    ast = parse("short_ema crosses_above long_ema AND short_ema > 0")
    vast = validate(ast, default_catalog(), variable_names=["short_ema", "long_ema"])
    assert vast.variables_used.count("short_ema") == 1


def test_unknown_variable_rejected():
    ast = parse("unknown_var > 100")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    issues = exc_info.value.issues
    assert any("unknown_var" in i.message for i in issues)


# ---------------------------------------------------------------------------
# Unknown features
# ---------------------------------------------------------------------------

def test_unknown_timeframed_feature():
    ast = parse("5m.bogus_indicator(9)")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    issues = exc_info.value.issues
    assert any("bogus_indicator" in i.message for i in issues)


def test_unknown_session_feature():
    ast = parse("session.unknown_field")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    issues = exc_info.value.issues
    assert any("unknown_field" in i.message for i in issues)


def test_unknown_namespace_rejected():
    ast = parse("fake_ns.something > 0")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())


# ---------------------------------------------------------------------------
# Arity mismatches
# ---------------------------------------------------------------------------

def test_wrong_arity_too_many_args():
    # ema takes 1 arg; give it 3
    ast = parse("5m.ema(9, 21, 5)")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    issues = exc_info.value.issues
    assert any("ema" in i.message for i in issues)


def test_wrong_arity_too_few_args():
    # macd_line takes 3 args; give it 1
    ast = parse("5m.macd_line(12)")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())


def test_zero_arity_feature_no_args():
    # vwap takes 0 args — valid
    ast = parse("5m.vwap()")
    vast = validate(ast, default_catalog())
    assert vast is not None


def test_zero_arity_non_tf_no_args():
    ast = parse("session.is_open")
    vast = validate(ast, default_catalog())
    assert vast is not None


# ---------------------------------------------------------------------------
# Validation error structure
# ---------------------------------------------------------------------------

def test_validation_error_has_issues_list():
    ast = parse("5m.bogus(9)")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    err = exc_info.value
    assert isinstance(err.issues, list)
    assert len(err.issues) > 0


def test_validation_issue_level_is_error():
    ast = parse("5m.bogus(9)")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    err = exc_info.value
    assert all(i.level in ("error", "warning") for i in err.issues)
    assert any(i.level == "error" for i in err.issues)


def test_validation_issue_has_location():
    ast = parse("5m.bogus(9)")
    with pytest.raises(ValidationError) as exc_info:
        validate(ast, default_catalog())
    err = exc_info.value
    for issue in err.issues:
        assert isinstance(issue.location, str)


# ---------------------------------------------------------------------------
# Feature requirements are correct types
# ---------------------------------------------------------------------------

def test_feature_requirements_types():
    ast = parse("5m.ema(9) > session.minutes_since_open")
    vast = validate(ast, default_catalog())
    for req in vast.feature_requirements:
        assert isinstance(req, (TimeframedFeature, FeatureRef))


def test_validator_rejects_overlapping_expression_and_timeframe_variable_names():
    ast = parse("5m.ema(9) > 0")
    with pytest.raises(ValidationError, match="both an expression variable"):
        validate(ast, default_catalog(), ["dup"], timeframe_variable_names=["dup"])


def test_validator_rejects_bare_timeframe_variable_reference():
    ast = parse(
        "sig_tf > 5m.close",
        timeframe_variable_names=frozenset({"sig_tf"}),
    )
    with pytest.raises(ValidationError):
        validate(ast, default_catalog(), [], timeframe_variable_names=["sig_tf"])


def test_validator_expands_timeframe_variable_to_every_literal_timeframe():
    ast = parse("sig_tf.ema(9) > 0", timeframe_variable_names=frozenset({"sig_tf"}))
    vast = validate(ast, default_catalog(), (), timeframe_variable_names=["sig_tf"])
    tfs = {
        req.timeframe
        for req in vast.feature_requirements
        if isinstance(req, TimeframedFeature) and req.name == "ema"
    }
    assert tfs == set(CANONICAL_TIMEFRAMES_ORDER)
