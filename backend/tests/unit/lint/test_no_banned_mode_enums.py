"""Banned-name lint — block PAPER/LIVE in *Mode*(Enum) classes.

Per plan_review.md A13/X7 and the Mode Naming Contract:

    "Standalone ``paper`` / ``live`` are banned mode names."

This test rejects any backend Python source that defines a ``*Mode*`` enum
class containing a member named exactly ``PAPER`` or ``LIVE`` (or a member
whose value is the bare string ``"paper"`` / ``"live"``).

Allowed surfaces:
- ``backend/app/domain/trading_mode.py`` — the canonical ``TradingMode`` enum
  uses qualified names (``BROKER_PAPER`` / ``BROKER_LIVE``), so it would not
  trip the rule even without the allowlist; the allowlist exists only as
  an explicit "this file is the single source of truth" marker.
- This test file itself (it lists the banned names as data).

Compound members like ``DataIntentMode.LIVE_PREVIEW`` / ``LIVE_RUNTIME`` are
allowed — they are qualified terms, not standalone ``LIVE``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "app"

ALLOWED_FILES = frozenset(
    {
        BACKEND_ROOT / "domain" / "trading_mode.py",
    }
)

BANNED_MEMBER_NAMES = frozenset({"PAPER", "LIVE"})
BANNED_MEMBER_VALUES = frozenset({"paper", "live"})


def _collect_python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def _is_mode_enum(class_node: ast.ClassDef) -> bool:
    if "Mode" not in class_node.name:
        return False
    for base in class_node.bases:
        name = _base_name(base)
        if name and "Enum" in name:
            return True
    return False


def _base_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr
    return None


def _banned_members(class_node: ast.ClassDef) -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []
    for body_item in class_node.body:
        if isinstance(body_item, ast.Assign):
            targets = body_item.targets
            value = body_item.value
        elif isinstance(body_item, ast.AnnAssign) and body_item.value is not None:
            targets = [body_item.target]
            value = body_item.value
        else:
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in BANNED_MEMBER_NAMES:
                findings.append((target.id, body_item.lineno))
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if value.value.lower() in BANNED_MEMBER_VALUES:
                    findings.append((target.id, body_item.lineno))
    return findings


@pytest.mark.parametrize("source_file", _collect_python_files(BACKEND_ROOT), ids=lambda path: str(path.relative_to(BACKEND_ROOT)))
def test_no_banned_mode_enum_members(source_file: Path) -> None:
    if source_file in ALLOWED_FILES:
        return
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    offenses: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_mode_enum(node):
            continue
        for member, lineno in _banned_members(node):
            offenses.append(
                f"{source_file.relative_to(BACKEND_ROOT)}:{lineno} -- "
                f"{node.name}.{member} is banned. Use TradingMode.BROKER_PAPER / BROKER_LIVE "
                f"from backend.app.domain.trading_mode."
            )
    assert not offenses, "Banned PAPER/LIVE enum members found:\n  " + "\n  ".join(offenses)
