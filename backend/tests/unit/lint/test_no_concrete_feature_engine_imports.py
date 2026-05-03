from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3] / "app"
FEATURES_ROOT = APP_ROOT / "features"
ALLOWED_PATHS = {
    APP_ROOT / "api" / "server.py",
    APP_ROOT / "runtime" / "account_trading_entrypoint.py",
    APP_ROOT / "composition" / "feature_engine.py",
}
BANNED_NAME = "IncrementalFeatureEngine"
BANNED_MODULES = {
    "backend.app.features.incremental",
    "features.incremental",
}


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def _rel(path: Path) -> str:
    return path.relative_to(APP_ROOT).as_posix()


def _imports(path: Path) -> list[tuple[str, tuple[str, ...], int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, tuple[str, ...], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, (), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(alias.name for alias in node.names), node.lineno))
    return found


def _is_allowed_path(path: Path) -> bool:
    return path.is_relative_to(FEATURES_ROOT) or path in ALLOWED_PATHS


def test_app_code_does_not_import_concrete_feature_engine_outside_composition_roots() -> None:
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        if _is_allowed_path(path):
            continue
        for module, names, lineno in _imports(path):
            if module in BANNED_MODULES:
                offenders.append(f"{_rel(path)}:{lineno} imports {module}")
            if module in {"backend.app.features", "features"} and BANNED_NAME in names:
                offenders.append(f"{_rel(path)}:{lineno} imports {BANNED_NAME} from {module}")
            if module in BANNED_MODULES and BANNED_NAME in names:
                offenders.append(f"{_rel(path)}:{lineno} imports {BANNED_NAME} from {module}")

    assert offenders == []
