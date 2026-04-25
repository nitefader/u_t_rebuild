"""Architecture isolation lint — Phase 1 §12 stop condition 1.

  "Feature Engine must never call Alpaca, Yahoo, news APIs, or any external
   provider."

This test scans ``backend/app/features/`` and ``backend/app/decision/`` for
any direct provider-SDK imports or imports that would couple feature/decision
code to a specific provider boundary. The only seam is the resolver / pipeline
manager (``backend.app.market_data.*``) — and even that is only imported via
TYPE_CHECKING in feature/decision modules, never at runtime.

Allowed inside features/ + decision/:
- imports of other feature/decision modules
- imports from ``backend.app.domain``
- standard library and ``pydantic`` / dataclasses

Forbidden:
- ``alpaca``, ``yfinance``, ``polygon``, any third-party provider SDK
- any module under ``backend.app.brokers``, ``backend.app.market_data.alpaca``
- AI SDKs (``openai``, ``anthropic``, ``groq``)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "app"
SCAN_PACKAGES = ("features", "decision")

FORBIDDEN_TOP_LEVEL_MODULES = frozenset(
    {
        "alpaca",
        "alpaca_py",
        "alpaca_trade_api",
        "yfinance",
        "polygon",
        "openai",
        "anthropic",
        "groq",
    }
)

FORBIDDEN_INTERNAL_PREFIXES = (
    "backend.app.brokers",
    "backend.app.market_data.alpaca",
)


def _collect_python_files(package: str) -> list[Path]:
    root = BACKEND_ROOT / package
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def _imports_in(tree: ast.AST) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append((node.module, node.lineno))
    return out


def _all_files_to_scan() -> list[Path]:
    files: list[Path] = []
    for package in SCAN_PACKAGES:
        files.extend(_collect_python_files(package))
    return files


@pytest.mark.parametrize("source_file", _all_files_to_scan(), ids=lambda path: str(path.relative_to(BACKEND_ROOT)))
def test_feature_or_decision_module_does_not_import_provider_sdk(source_file: Path) -> None:
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    offenses: list[str] = []
    for module_name, lineno in _imports_in(tree):
        top_level = module_name.split(".", 1)[0]
        if top_level in FORBIDDEN_TOP_LEVEL_MODULES:
            offenses.append(f"{source_file.relative_to(BACKEND_ROOT)}:{lineno} — forbidden provider SDK import: {module_name}")
        for prefix in FORBIDDEN_INTERNAL_PREFIXES:
            if module_name == prefix or module_name.startswith(prefix + "."):
                offenses.append(
                    f"{source_file.relative_to(BACKEND_ROOT)}:{lineno} — feature/decision code must not import {module_name}; "
                    f"go through resolver / SubscriptionManager seams instead."
                )
    assert not offenses, "Provider-SDK / broker imports leaked into Feature Engine or Decision layer:\n  " + "\n  ".join(offenses)
