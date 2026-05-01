"""Expression engine error hierarchy.

All public exceptions are subclasses of ExpressionError.
ParseError carries line/col for IDE integration.
ValidationError carries a list of ValidationIssue instances.
"""
from __future__ import annotations

from dataclasses import dataclass


class ExpressionError(Exception):
    """Base class for all expression-engine errors."""


class ParseError(ExpressionError):
    """Raised when the source text cannot be lexed or parsed."""

    def __init__(self, message: str, line: int, col: int) -> None:
        super().__init__(f"[{line}:{col}] {message}")
        self.message = message
        self.line = line
        self.col = col


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding."""

    level: str          # "error" | "warning"
    message: str
    location: str       # human-readable hint, e.g. "5m.ema(9)"


class ValidationError(ExpressionError):
    """Raised when one or more validation issues at level 'error' are found."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        msgs = "; ".join(f"[{i.level}] {i.message}" for i in issues)
        super().__init__(msgs)
        self.issues = issues


class EvalError(ExpressionError):
    """Raised at evaluation time when required data is missing or evaluation fails."""
