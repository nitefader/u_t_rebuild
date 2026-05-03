from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3] / "app"
SCAN_ROOTS = (APP_ROOT / "pipeline", APP_ROOT / "runtime", APP_ROOT / "research")
V4_BUILDER = "backend.app.decision.signal_plan_builder_v4"
V4_ALLOWED_ROOT = APP_ROOT / "decision" / "signal_sources"
BANNED_SIGNAL_MODULES = {
    "backend.app.decision.signal_engine",
    "backend.app.decision.signal_plan_builder",
}
BANNED_DECISION_NAMES = {
    "SignalEngine",
    "SignalEvaluation",
    "SignalEvaluationError",
    "PositionContext",
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


def _is_banned_signal_module(module: str) -> bool:
    return module in BANNED_SIGNAL_MODULES or module in {
        "decision.signal_engine",
        "decision.signal_plan_builder",
    }


def test_pipeline_runtime_and_research_do_not_import_concrete_signal_modules() -> None:
    offenders: list[str] = []
    for root in SCAN_ROOTS:
        for path in _python_files(root):
            for module, names, lineno in _imports(path):
                if _is_banned_signal_module(module):
                    offenders.append(f"{_rel(path)}:{lineno} imports {module}")
                if module in {"backend.app.decision", "decision"}:
                    banned = sorted(set(names) & BANNED_DECISION_NAMES)
                    if banned:
                        offenders.append(f"{_rel(path)}:{lineno} imports {banned} from {module}")

    assert offenders == []


def test_signal_plan_builder_v4_imports_stay_inside_signal_sources() -> None:
    offenders: list[str] = []
    for path in _python_files(APP_ROOT):
        if path.is_relative_to(V4_ALLOWED_ROOT):
            continue
        for module, _names, lineno in _imports(path):
            if module == V4_BUILDER or module == "decision.signal_plan_builder_v4":
                offenders.append(f"{_rel(path)}:{lineno} imports {module}")
            if module in {"backend.app.decision", "decision"} and "signal_plan_builder_v4" in _names:
                offenders.append(f"{_rel(path)}:{lineno} imports signal_plan_builder_v4 from {module}")

    assert offenders == []
