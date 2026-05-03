from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[3] / "app"
RESEARCH_ROOT = APP_ROOT / "research"
BANNED_NAMES = {"SignalEngine", "SignalPlanBuilder", "build_signal_plan_from_v4"}
BANNED_MODULE_SUFFIXES = (
    "decision.signal_engine",
    "decision.signal_plan_builder",
    "decision.signal_plan_builder_v4",
)


def _python_files() -> list[Path]:
    if not RESEARCH_ROOT.exists():
        return []
    return [path for path in RESEARCH_ROOT.rglob("*.py") if "__pycache__" not in path.parts]


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def test_research_replay_uses_signal_source_port_only() -> None:
    files = _python_files()
    if not files:
        # Proactive guard: research source packages are absent after S12.8.
        return

    offenders: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(APP_ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.endswith(BANNED_MODULE_SUFFIXES):
                        offenders.append(f"{rel}:{node.lineno} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = {alias.name for alias in node.names}
                if module.endswith(BANNED_MODULE_SUFFIXES) or names & BANNED_NAMES:
                    offenders.append(f"{rel}:{node.lineno} imports concrete signal builder symbols")
            elif isinstance(node, ast.Call) and _name(node.func) == "build_signal_plan_from_v4":
                offenders.append(f"{rel}:{node.lineno} calls build_signal_plan_from_v4")

    assert offenders == []
