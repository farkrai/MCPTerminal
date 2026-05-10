"""Test-runner tools for the FastMCP server.

Mounted under namespace "test" → tool names become:
  test_detect, test_run, test_run_file, test_explain_failures
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant.server.state import policy

test_mcp = FastMCP("TestTools")

# Pytest exit-code meanings
_PYTEST_EXIT = {
    0: "passed",
    1: "failures",
    2: "error",
    3: "interrupted",
    4: "no_tests",
    5: "no_tests_collected",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_cwd(cwd: str | None) -> Path:
    if cwd:
        p = Path(cwd)
        return p if p.is_absolute() else policy.sandbox_root / p
    return policy.sandbox_root


def _run_pytest(cwd: Path, extra_args: list[str] | None = None) -> dict:
    cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q"] + (extra_args or [])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    combined = (result.stdout + result.stderr)[:4000]
    status = _PYTEST_EXIT.get(result.returncode, f"code_{result.returncode}")
    return {
        "framework": "pytest",
        "exit_code": result.returncode,
        "status": status,
        "output": combined,
    }


def _run_jest(cwd: Path) -> dict:
    result = subprocess.run(
        ["npx", "jest", "--no-coverage"],
        capture_output=True, text=True, cwd=cwd,
    )
    combined = (result.stdout + result.stderr)[:4000]
    return {
        "framework": "jest",
        "exit_code": result.returncode,
        "status": "passed" if result.returncode == 0 else "failures",
        "output": combined,
    }


# ── Tools ──────────────────────────────────────────────────────────────────────

@test_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), tags={"test", "read-only"})
async def detect(
    cwd: Annotated[str | None, "Directory to inspect (default: project root)"] = None,
    ctx: Context = None,
) -> dict:
    """Detect which test frameworks (pytest, jest) are configured in a directory."""
    work_dir = _resolve_cwd(cwd)
    if ctx:
        await ctx.info(f"Detecting test frameworks in: {work_dir}")
    frameworks: list[str] = []
    details: dict = {}

    for marker in ["pytest.ini", "setup.cfg", "pyproject.toml", "conftest.py"]:
        if (work_dir / marker).exists():
            frameworks.append("pytest")
            details["pytest_marker"] = marker
            break

    jest_found = False
    for marker in ["jest.config.js", "jest.config.ts", "jest.config.json"]:
        if (work_dir / marker).exists():
            frameworks.append("jest")
            details["jest_config"] = marker
            jest_found = True
            break
    if not jest_found and (work_dir / "package.json").exists():
        if '"jest"' in (work_dir / "package.json").read_text():
            frameworks.append("jest")
            details["jest_marker"] = "package.json"

    return {"frameworks": frameworks, "directory": str(work_dir), **details}


@test_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False), tags={"test"})
async def run(
    cwd: Annotated[str | None, "Directory containing the test suite (default: project root)"] = None,
    ctx: Context = None,
) -> dict:
    """Auto-detect and run the full test suite (pytest or jest)."""
    work_dir = _resolve_cwd(cwd)
    if ctx:
        await ctx.info(f"Running test suite in: {work_dir}")
        await ctx.report_progress(0, 100)

    detected = await detect(cwd, ctx=None)
    frameworks = detected.get("frameworks", [])

    if "pytest" in frameworks:
        result = _run_pytest(work_dir, [])
    elif "jest" in frameworks:
        result = _run_jest(work_dir)
    else:
        raise ToolError("No supported test framework found. Run 'test_detect' first.")

    if ctx:
        await ctx.report_progress(100, 100)
    return result


@test_mcp.tool(
    name="run_file",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"test"},
)
async def run_file(
    path: Annotated[str, "Path to the specific test file to run"],
    ctx: Context = None,
) -> dict:
    """Run a specific test file with pytest."""
    test_path = Path(path)
    if not test_path.is_absolute():
        test_path = policy.sandbox_root / test_path
    if not test_path.exists():
        raise ToolError(f"Test file not found: {test_path}")
    if ctx:
        await ctx.info(f"Running test file: {test_path}")
    return _run_pytest(test_path.parent, [str(test_path)])


@test_mcp.tool(
    name="explain_failures",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"test", "read-only"},
)
async def explain_failures(
    output: Annotated[str, "The test failure output to explain"],
    ctx: Context = None,
) -> str:
    """Send test failure output to the LLM for plain-English explanation and fix suggestions.

    Requires the Ollama LLM to be running. Falls back to echoing the output if unavailable.
    """
    if not output.strip():
        raise ToolError("'output' must not be empty.")
    if ctx:
        await ctx.info("Asking LLM to explain test failures")
    try:
        from mcp_assistant.llm.client import OllamaClient
        from mcp_assistant.llm.prompt_builder import PromptBuilder
        client = OllamaClient()
        if not client.is_available():
            return f"LLM unavailable – raw failure output:\n{output[:2000]}"
        prompt = PromptBuilder().explain_failures_prompt(output)
        return client.generate(prompt, temperature=0.7)
    except Exception as e:
        return f"Could not get LLM explanation ({e}).\n\nRaw output:\n{output[:2000]}"
