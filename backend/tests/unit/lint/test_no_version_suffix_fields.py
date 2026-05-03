from __future__ import annotations

import ast
import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3] / "app"
VERSION_FIELD_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*_v(\d+)_id\b")
ALLOWED_FIELDS = {"strategy_version_v4_id"}


def _python_files() -> list[Path]:
    return [path for path in APP_ROOT.rglob("*.py") if "__pycache__" not in path.parts]


def _field_names(tree: ast.AST) -> list[tuple[str, int]]:
    names: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append((node.id, node.lineno))
        elif isinstance(node, ast.Attribute):
            names.append((node.attr, node.lineno))
        elif isinstance(node, ast.arg):
            names.append((node.arg, node.lineno))
        elif isinstance(node, ast.keyword) and node.arg is not None:
            names.append((node.arg, node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.extend((match.group(0), node.lineno) for match in VERSION_FIELD_RE.finditer(node.value))
    return names


def test_no_future_version_suffix_id_fields() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(APP_ROOT).as_posix()
        for field_name, lineno in _field_names(tree):
            if field_name in ALLOWED_FIELDS:
                continue
            match = VERSION_FIELD_RE.fullmatch(field_name)
            if match and int(match.group(1)) >= 5:
                offenders.append(f"{rel}:{lineno} uses future versioned field {field_name}")

    assert offenders == []
