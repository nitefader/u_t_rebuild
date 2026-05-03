from __future__ import annotations

import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[3] / "app"

PROGRAM_LINEAGE_PATTERNS = (
    "ProgramVersion",
    "program_id",
    "program_version_id",
    "OrderOrigin.PROGRAM",
    "build_program_client_order_id",
)

PROGRAM_LINEAGE_ALLOWED_FILES = frozenset(
    {
        "domain/__init__.py",
        "domain/program.py",
        "domain/validation.py",
        "features/planner.py",
        "market_data/stream_hub.py",
        "operations/models.py",
        "operations/service.py",
        "promotion/models.py",
        "promotion/service.py",
        "runtime/__init__.py",
        "runtime/account_trading_orchestrator.py",
        "runtime/account_trading_supervisor.py",
        "runtime/engine.py",
        "runtime/models.py",
    }
)

RUNTIME_AUTHORITY_CLASS_NAMES = frozenset(
    {
        "RuntimeEngine",
        "RuntimeOrchestrator",
        "BrokerRuntimeOrchestrator",
        "BrokerRuntimeSupervisor",
    }
)

RUNTIME_AUTHORITY_ALLOWED_FILES = frozenset(
    {
        "pipeline/orchestrator.py",
        "runtime/account_trading_orchestrator.py",
        "runtime/account_trading_supervisor.py",
    }
)


def _python_files() -> list[Path]:
    return [path for path in BACKEND_ROOT.rglob("*.py") if "__pycache__" not in path.parts]


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def test_no_new_program_lineage_outside_migration_shims() -> None:
    offenders: list[str] = []
    for path in _python_files():
        relative = _rel(path)
        if relative in PROGRAM_LINEAGE_ALLOWED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PROGRAM_LINEAGE_PATTERNS:
            if pattern in text:
                offenders.append(f"{relative}:{pattern}")

    assert offenders == []


def test_no_new_runtime_authority_classes_without_approval() -> None:
    offenders: list[str] = []
    for path in _python_files():
        relative = _rel(path)
        if relative in RUNTIME_AUTHORITY_ALLOWED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in RUNTIME_AUTHORITY_CLASS_NAMES:
                offenders.append(f"{relative}:{node.name}")

    assert offenders == []
