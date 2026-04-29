"""Banned-name lint — block doctrine-banned product names from production code.

Per ``docs/architecture/NAMING_CONTRACT.md`` the following names must
NOT appear as active product concepts in Ultimate Trader:

- Account Governor (the class is ``PortfolioGovernor``; user-facing
  ``Account Governor`` is banned)
- Services Center
- Paper Runtime as a separate product path
- Live Runtime as a separate product path
- Deployment per Account
- Strategy Account
- Broker SubAccount
- Market Data Service Center

This test scans ``backend/app/**/*.py`` for the banned phrases and
class/identifier shapes. It is deliberately separate from the
``ProgramVersion`` lineage guardrail in
``test_turtle_shell_architecture_guardrails.py`` — Program is being
retired through staged slices and has its own allowlist; the names
checked here are banned outright with no migration window.

Allowed surfaces:

- This lint test (defines the banned tokens as data).
- ``backend/app/domain/trading_mode.py`` may contain qualified
  compound terms like ``BROKER_PAPER`` / ``BROKER_LIVE`` — the
  banned phrases here are the standalone "Paper Runtime" /
  "Live Runtime" labels, not the qualified TradingMode members.
- Any file under ``backend/app/__pycache__`` (already excluded).

Doctrine docs under ``docs/`` legitimately reference the banned
names in negative/banned-name contexts; this test only runs against
``backend/app``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "app"


# Banned phrases as they would appear in human-readable strings,
# UI labels, error messages, comments, or docstrings inside code.
# Match is case-insensitive and word-boundaried so "PaperRuntimeFoo"
# would NOT trip; "Paper Runtime" would.
BANNED_HUMAN_PHRASES: tuple[str, ...] = (
    "Account Governor",
    "Services Center",
    "Paper Runtime",
    "Live Runtime",
    "Deployment per Account",
    "Strategy Account",
    "Broker SubAccount",
    "Market Data Service Center",
)


# Banned identifier shapes — class names, function names, attributes
# that encode banned product entities directly. Match is exact on
# the identifier token.
BANNED_IDENTIFIERS: tuple[str, ...] = (
    "AccountGovernor",
    "ServicesCenter",
    "PaperRuntime",
    "LiveRuntime",
    "StrategyAccount",
    "BrokerSubAccount",
    "MarketDataServiceCenter",
)


# Files that are allowed to mention banned names because they are
# the lint definition itself.
ALLOWED_FILES: frozenset[str] = frozenset()


def _python_files() -> list[Path]:
    return [p for p in BACKEND_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


_PHRASE_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
    for phrase in BANNED_HUMAN_PHRASES
)
_IDENTIFIER_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(name)}\b") for name in BANNED_IDENTIFIERS
)


def test_no_banned_product_phrases_in_backend_source() -> None:
    """No banned human-readable product names anywhere in backend/app."""
    offenders: list[str] = []
    for path in _python_files():
        rel = _rel(path)
        if rel in ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for phrase, pattern in zip(BANNED_HUMAN_PHRASES, _PHRASE_PATTERNS, strict=True):
            for match in pattern.finditer(text):
                # locate line number
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{rel}:{line_no} -- '{phrase}' is banned")
    assert offenders == [], (
        "Banned product-name phrases found in backend source. "
        "Per docs/architecture/NAMING_CONTRACT.md these names must not appear "
        "as active product concepts:\n  " + "\n  ".join(offenders)
    )


def test_no_banned_product_identifiers_in_backend_source() -> None:
    """No banned identifier shapes (class/function/attribute names)."""
    offenders: list[str] = []
    for path in _python_files():
        rel = _rel(path)
        if rel in ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for name, pattern in zip(BANNED_IDENTIFIERS, _IDENTIFIER_PATTERNS, strict=True):
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{rel}:{line_no} -- identifier '{name}' is banned")
    assert offenders == [], (
        "Banned product-name identifiers found in backend source. "
        "Per docs/architecture/NAMING_CONTRACT.md these names must not "
        "appear as classes/functions/attributes:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("phrase", BANNED_HUMAN_PHRASES)
def test_banned_phrase_is_documented(phrase: str) -> None:
    """Sanity: every banned phrase must be listed in NAMING_CONTRACT.md."""
    contract_path = BACKEND_ROOT.parents[1] / "docs" / "architecture" / "NAMING_CONTRACT.md"
    contract_text = contract_path.read_text(encoding="utf-8")
    assert phrase.lower() in contract_text.lower(), (
        f"Banned phrase '{phrase}' must be listed in {contract_path.name} "
        "(banned-names section) to keep doctrine and lint synchronized."
    )
