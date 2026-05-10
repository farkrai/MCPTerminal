"""Python code quality and analysis tools.

Mounted under namespace "code" → tool names become:
  code_symbols, code_lint, code_complexity

All tools work on .py files or directories.
- code_symbols: uses stdlib `ast` — no external dependencies.
- code_lint: delegates to `ruff` if installed, falls back to `py_compile` check.
- code_complexity: uses `ast` to count functions, classes, branches.
"""
from __future__ import annotations
import ast
import shutil
import subprocess
import tokenize
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant.server.state import policy

code_mcp = FastMCP("CodeTools")


def _resolve(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = policy.sandbox_root / p
    return p.resolve()


def _read_py(path: Path) -> str:
    if not path.exists():
        raise ToolError(f"Not found: {path}")
    if path.suffix != ".py":
        raise ToolError(f"Only .py files are supported: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


# ── Tools ──────────────────────────────────────────────────────────────────────

@code_mcp.tool(
    name="symbols",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"code", "read-only"},
)
async def symbols(
    path: Annotated[str, "Path to a .py file"],
    ctx: Context = None,
) -> dict:
    """Extract all top-level and nested classes and functions from a Python file.

    Returns their names, line numbers, and docstrings (first line only).
    """
    if ctx:
        await ctx.info(f"Extracting symbols from: {path}")
    file_path = _resolve(path)
    source = _read_py(file_path)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ToolError(f"Syntax error in {path}: {e}")

    result: list[dict] = []

    def _doc(node: ast.AST) -> str | None:
        docstring = ast.get_docstring(node)
        return docstring.splitlines()[0][:120] if docstring else None

    def _walk(node: ast.AST, parent: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{parent}.{child.name}" if parent else child.name
                args = [a.arg for a in child.args.args if a.arg != "self"]
                result.append({
                    "kind": "function",
                    "name": qualname,
                    "line": child.lineno,
                    "args": args,
                    "doc": _doc(child),
                })
                _walk(child, qualname)
            elif isinstance(child, ast.ClassDef):
                qualname = f"{parent}.{child.name}" if parent else child.name
                bases = [ast.unparse(b) for b in child.bases]
                result.append({
                    "kind": "class",
                    "name": qualname,
                    "line": child.lineno,
                    "bases": bases,
                    "doc": _doc(child),
                })
                _walk(child, qualname)

    _walk(tree)
    return {"file": str(file_path), "count": len(result), "symbols": result}


@code_mcp.tool(
    name="lint",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"code", "read-only"},
)
async def lint(
    path: Annotated[str, "Path to a .py file or directory to lint"],
    fix: Annotated[bool, "Auto-fix safe issues (ruff only, default false)"] = False,
    ctx: Context = None,
) -> dict:
    """Lint Python code with ruff (if installed) or py_compile as fallback.

    Returns a list of issues with file, line, code, and message.
    """
    target = _resolve(path)
    if not target.exists():
        raise ToolError(f"Not found: {target}")

    if ctx:
        await ctx.info(f"Linting: {target}")

    ruff = shutil.which("ruff")
    if ruff:
        args = [ruff, "check", "--output-format", "json"]
        if fix:
            args.append("--fix")
        args.append(str(target))
        r = subprocess.run(args, capture_output=True, text=True, timeout=30)
        import json
        try:
            issues = json.loads(r.stdout) if r.stdout.strip() else []
        except Exception:
            issues = []
        return {
            "linter": "ruff",
            "target": str(target),
            "issue_count": len(issues),
            "issues": [
                {
                    "file": i.get("filename", ""),
                    "line": i.get("location", {}).get("row", 0),
                    "col": i.get("location", {}).get("column", 0),
                    "code": i.get("code", ""),
                    "message": i.get("message", ""),
                    "fixable": i.get("fix") is not None,
                }
                for i in issues[:50]
            ],
        }

    # Fallback: py_compile (catches syntax errors only)
    files = list(target.rglob("*.py")) if target.is_dir() else [target]
    import py_compile
    issues = []
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            issues.append({"file": str(f), "line": 0, "code": "E999", "message": str(e)})
    return {
        "linter": "py_compile (ruff not installed)",
        "target": str(target),
        "issue_count": len(issues),
        "issues": issues,
    }


@code_mcp.tool(
    name="complexity",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"code", "read-only"},
)
async def complexity(
    path: Annotated[str, "Path to a .py file"],
    ctx: Context = None,
) -> dict:
    """Report cyclomatic complexity metrics for a Python file.

    Counts branches (if/elif/for/while/except/with/assert) per function.
    A score ≤ 10 is considered maintainable; > 20 is high risk.
    """
    if ctx:
        await ctx.info(f"Analysing complexity: {path}")
    file_path = _resolve(path)
    source = _read_py(file_path)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ToolError(f"Syntax error in {path}: {e}")

    _BRANCH_NODES = (
        ast.If, ast.For, ast.AsyncFor, ast.While,
        ast.ExceptHandler, ast.With, ast.AsyncWith,
        ast.Assert, ast.comprehension,
    )

    def _cyclomatic(func_node: ast.AST) -> int:
        count = 1
        for node in ast.walk(func_node):
            if isinstance(node, _BRANCH_NODES):
                count += 1
            elif isinstance(node, ast.BoolOp):
                count += len(node.values) - 1
        return count

    metrics: list[dict] = []
    total_lines = source.count("\n") + 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            score = _cyclomatic(node)
            end_line = getattr(node, "end_lineno", node.lineno)
            metrics.append({
                "name": node.name,
                "line": node.lineno,
                "lines": end_line - node.lineno + 1,
                "complexity": score,
                "risk": "low" if score <= 10 else ("medium" if score <= 20 else "high"),
            })

    metrics.sort(key=lambda x: -x["complexity"])
    avg = round(sum(m["complexity"] for m in metrics) / len(metrics), 1) if metrics else 0
    return {
        "file": str(file_path),
        "total_lines": total_lines,
        "function_count": len(metrics),
        "avg_complexity": avg,
        "functions": metrics,
    }
