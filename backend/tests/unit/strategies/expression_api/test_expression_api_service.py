"""Direct unit tests of the expression_api service layer (no HTTP)."""
from __future__ import annotations

import pytest

from backend.app.strategies.expression_api import (
    FeatureRequirementDTO,
    ValidateResult,
    CatalogEntryDTO,
    MirrorResult,
    list_features,
    mirror_expression,
    validate_expression,
)
from backend.app.strategies.expression_engine.errors import ParseError


# ---------------------------------------------------------------------------
# validate_expression
# ---------------------------------------------------------------------------

class TestValidateExpression:
    def test_valid_returns_valid_true(self) -> None:
        result = validate_expression("5m.ema(9) crosses_above 5m.ema(21)")
        assert result.valid is True
        assert result.errors == ()
        assert result.warnings == ()

    def test_timeframe_variables_accept_prefix_syntax(self) -> None:
        result = validate_expression(
            "sig_tf.ema(9) crosses_above sig_tf.ema(21)",
            (),
            timeframe_variable_names=("sig_tf",),
        )
        assert result.valid is True

    def test_overlapping_expr_and_timeframe_binding_names_invalid(self) -> None:
        result = validate_expression(
            "5m.ema(9) > 0",
            ("overlap",),
            timeframe_variable_names=("overlap",),
        )
        assert result.valid is False
        assert len(result.errors) >= 1

    def test_valid_populates_feature_requirements(self) -> None:
        result = validate_expression("5m.ema(9) crosses_above 5m.ema(21)")
        keys = {f.key for f in result.feature_requirements}
        assert "5m.ema(9)" in keys
        assert "5m.ema(21)" in keys

    def test_duplicate_features_deduplicated(self) -> None:
        # Same feature used twice should appear once.
        result = validate_expression("5m.ema(9) > 5m.ema(9)")
        keys = [f.key for f in result.feature_requirements]
        assert keys.count("5m.ema(9)") == 1

    def test_parse_error_sets_valid_false_with_line_col(self) -> None:
        result = validate_expression("5m.ema(")
        assert result.valid is False
        assert len(result.errors) >= 1
        err = result.errors[0]
        assert err.level == "error"
        assert err.line is not None
        assert err.col is not None

    def test_validation_error_sets_valid_false(self) -> None:
        result = validate_expression("5m.bogus(99) > 5m.close")
        assert result.valid is False
        assert any("bogus" in e.message for e in result.errors)

    def test_empty_source_is_valid(self) -> None:
        # Empty input is "no condition" — not a parse error.
        result = validate_expression("")
        assert result.valid is True
        assert result.errors == ()

    def test_whitespace_only_is_valid(self) -> None:
        result = validate_expression("   \n  \n  ")
        assert result.valid is True
        assert result.errors == ()

    def test_comment_only_is_valid(self) -> None:
        result = validate_expression("// just a comment")
        assert result.valid is True
        assert result.errors == ()

    def test_comment_then_whitespace_is_valid(self) -> None:
        result = validate_expression("// comment\n  ")
        assert result.valid is True
        assert result.errors == ()

    def test_trailing_newline_is_valid(self) -> None:
        result = validate_expression("5m.ema(9) > 100\n")
        assert result.valid is True

    def test_single_equals_is_invalid(self) -> None:
        result = validate_expression("5m.ema(9) =")
        assert result.valid is False

    def test_single_equals_error_message_hint(self) -> None:
        result = validate_expression("5m.ema(9) =")
        assert any("did you mean '=='" in e.message for e in result.errors)

    def test_variables_used_populated(self) -> None:
        result = validate_expression("my_var > 5m.close", variable_names=["my_var"])
        assert result.valid is True
        assert "my_var" in result.variables_used

    def test_unknown_variable_is_error(self) -> None:
        # my_var not declared -> validation error
        result = validate_expression("my_var > 5m.close")
        assert result.valid is False

    def test_tf_feature_requirement_shape(self) -> None:
        result = validate_expression("5m.rsi(14) > 50")
        assert result.valid is True
        rsi = next((f for f in result.feature_requirements if f.name == "rsi"), None)
        assert rsi is not None
        assert rsi.timeframe == "5m"
        assert rsi.namespace is None
        assert rsi.args == (14.0,)
        assert rsi.key == "5m.rsi(14)"

    def test_nontf_feature_requirement_shape(self) -> None:
        result = validate_expression("session.is_open")
        assert result.valid is True
        sess = next((f for f in result.feature_requirements if f.name == "is_open"), None)
        assert sess is not None
        assert sess.namespace == "session"
        assert sess.timeframe is None
        assert sess.key == "session.is_open"

    def test_error_warning_split(self) -> None:
        # A valid expression should have no errors or warnings.
        result = validate_expression("5m.close > 5m.ema(20)")
        assert result.valid is True
        assert result.errors == ()
        assert result.warnings == ()

    def test_feature_requirements_preserve_insertion_order(self) -> None:
        # first 5m.ema(9), then 5m.ema(21)
        result = validate_expression("5m.ema(9) crosses_above 5m.ema(21)")
        keys = [f.key for f in result.feature_requirements]
        assert keys.index("5m.ema(9)") < keys.index("5m.ema(21)")

    def test_zero_arity_tf_feature_key(self) -> None:
        result = validate_expression("5m.vwap > 5m.close")
        assert result.valid is True
        keys = {f.key for f in result.feature_requirements}
        assert "5m.vwap" in keys
        assert "5m.close" in keys


# ---------------------------------------------------------------------------
# list_features
# ---------------------------------------------------------------------------

class TestListFeatures:
    def test_returns_at_least_50(self) -> None:
        features = list_features()
        assert len(features) >= 50

    def test_all_are_catalog_entry_dtos(self) -> None:
        features = list_features()
        for f in features:
            assert isinstance(f, CatalogEntryDTO)

    def test_ema_entry_shape(self) -> None:
        features = list_features()
        ema = next((f for f in features if f.key == "ema"), None)
        assert ema is not None
        assert ema.name == "ema"
        assert ema.timeframe_bound is True
        assert ema.arity == 1
        assert ema.category == "trend"

    def test_session_is_open_entry_shape(self) -> None:
        features = list_features()
        entry = next((f for f in features if f.key == "session.is_open"), None)
        assert entry is not None
        assert entry.namespace == "session"
        assert entry.timeframe_bound is False
        assert entry.return_type == "bool"
        assert entry.category == "time"

    def test_categories_all_present(self) -> None:
        features = list_features()
        cats = {f.category for f in features}
        for expected in ("trend", "momentum", "volatility", "volume", "bb", "time", "bar"):
            assert expected in cats, f"Missing category: {expected}"


# ---------------------------------------------------------------------------
# mirror_expression
# ---------------------------------------------------------------------------

class TestMirrorExpression:
    def test_crosses_above_inverted(self) -> None:
        result = mirror_expression("5m.ema(9) crosses_above 5m.ema(21)")
        assert isinstance(result, MirrorResult)
        assert "crosses_below" in result.mirrored_text

    def test_header_prepended(self) -> None:
        result = mirror_expression("5m.close > 5m.ema(20)")
        assert "Auto-mirrored" in result.mirrored_text

    def test_parse_error_raises(self) -> None:
        with pytest.raises(ParseError):
            mirror_expression("@invalid_char")
