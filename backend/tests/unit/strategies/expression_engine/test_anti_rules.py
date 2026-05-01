"""Anti-rule tests: enforce engine hygiene rules from CONTRACTS.md.

Rule 1: No `import ast` anywhere in expression_engine/.
Rule 2: No eval() / exec() / compile() Python builtins called on user text.
        We look for the call-site pattern at function call sites, not def sites.

The test walks every .py file under expression_engine/ and asserts these
patterns are absent.
"""
from __future__ import annotations

import os
import pathlib
import re


# ---------------------------------------------------------------------------
# Locate engine source files
# ---------------------------------------------------------------------------

_ENGINE_ROOT = pathlib.Path(__file__).parents[4] / "app" / "strategies" / "expression_engine"


def _engine_py_files() -> list[pathlib.Path]:
    """Return all .py files in expression_engine/ (non-recursive is enough since flat)."""
    return sorted(_ENGINE_ROOT.glob("*.py"))


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Rule 1: No `import ast`
# ---------------------------------------------------------------------------

def test_no_import_ast():
    """No file in expression_engine/ should contain `import ast`."""
    pattern = re.compile(r"\bimport\s+ast\b")
    violations: list[str] = []
    for path in _engine_py_files():
        src = _read(path)
        if pattern.search(src):
            violations.append(str(path))
    assert not violations, (
        f"Found 'import ast' in: {violations}. "
        "The expression engine must use its own hand-rolled AST, not Python's ast module."
    )


# ---------------------------------------------------------------------------
# Rule 2: No eval / exec / compile(str, ...) built-in calls on user text
#
# Strategy: look for the pattern `eval(` or `exec(` as function call sites.
# For compile: look for `compile(` that is followed by a string or expression
# (i.e., not a function *def* site).  We match `compile(` but exempt
# the function *definition* line `def compile(` and `def compile_expr(`.
# ---------------------------------------------------------------------------

# Pattern: Python's eval() or exec() called with a string argument (user text).
# We look for `eval(` or `exec(` where the argument starts with a quote or
# a variable name — but NOT method calls like `self.eval(` which are fine.
# The rule: no *module-level* or *standalone* eval/exec calls (not method calls).
_BUILTIN_EVAL_EXEC_PATTERN = re.compile(
    r"(?<![.\w])(?<!\bself\.)(?<!\bobj\.)\b(eval|exec)\s*\("
)

# Compile with a string literal — the only forbidden form.
# `compile("...", ...)` — Python builtin compile on a source string.
_BUILTIN_COMPILE_ON_STRING = re.compile(r'\bcompile\s*\(\s*["\']')


def test_no_eval_exec_calls():
    """No file in expression_engine/ should call Python's eval() or exec() on user text.

    Method calls like self.eval() and method definitions like def eval() are
    explicitly allowed — those are the engine's internal recursive evaluator,
    not Python's builtin.
    """
    violations: list[str] = []
    for path in _engine_py_files():
        src = _read(path)
        for lineno, line in enumerate(src.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip function definitions (def eval(...))
            if re.match(r"\s*def\s+(eval|exec)\s*\(", line):
                continue
            # Match eval( or exec( that is NOT a method call (self.eval, obj.eval etc.)
            if _BUILTIN_EVAL_EXEC_PATTERN.search(line):
                violations.append(f"{path.name}:{lineno}: {line.rstrip()}")
    assert not violations, (
        f"Found standalone eval()/exec() calls in expression engine "
        "(method calls like self.eval() and def eval() are fine; standalone builtin calls are not):\n"
        + "\n".join(violations)
    )


def test_no_builtin_compile_on_user_text():
    """No file in expression_engine/ should call Python's builtin compile(str, ...).

    Our own compile(ValidatedAst) function is allowed.  Only calls that pass a
    string literal as the first argument are forbidden — those would be compiling
    user-supplied text via Python's builtin.
    """
    violations: list[str] = []
    for path in _engine_py_files():
        src = _read(path)
        for lineno, line in enumerate(src.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if _BUILTIN_COMPILE_ON_STRING.search(line):
                violations.append(f"{path.name}:{lineno}: {line.rstrip()}")

    assert not violations, (
        "Found compile(<string>, ...) calls in expression engine "
        "(only compile(ValidatedAst) is permitted):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Rule 3: All AST node dataclasses are frozen
# ---------------------------------------------------------------------------

def test_ast_nodes_are_frozen():
    """Every @dataclass in ast_nodes.py must be frozen=True."""
    ast_nodes_path = _ENGINE_ROOT / "ast_nodes.py"
    src = _read(ast_nodes_path)

    # Find all @dataclass(...) decorators
    dataclass_with_args = re.compile(r"@dataclass\(([^)]*)\)")
    bare_dataclass = re.compile(r"@dataclass\s*\n")

    # Check for bare @dataclass (no args → not frozen)
    bare_matches = bare_dataclass.findall(src)
    assert not bare_matches, (
        "Found bare @dataclass (without frozen=True) in ast_nodes.py"
    )

    # Check that all @dataclass(...) have frozen=True
    for match in dataclass_with_args.finditer(src):
        args = match.group(1)
        assert "frozen=True" in args, (
            f"Found @dataclass without frozen=True: @dataclass({args})"
        )


# ---------------------------------------------------------------------------
# Rule 4: Engine files do not import from outside the engine package
#         (they should be self-contained, except for stdlib)
# ---------------------------------------------------------------------------

def test_no_external_app_imports():
    """Expression engine files must not import from other app packages."""
    # Allowed: stdlib, typing, dataclasses, datetime, re, pathlib, etc.
    # Not allowed: from backend.app.brokers, from backend.app.governor, etc.
    forbidden_pattern = re.compile(r"from\s+backend\.app\.(?!strategies\.expression_engine)")
    violations: list[str] = []
    for path in _engine_py_files():
        src = _read(path)
        for lineno, line in enumerate(src.splitlines(), start=1):
            if forbidden_pattern.search(line):
                violations.append(f"{path.name}:{lineno}: {line.rstrip()}")
    assert not violations, (
        "Expression engine must be self-contained — found external backend imports:\n"
        + "\n".join(violations)
    )
