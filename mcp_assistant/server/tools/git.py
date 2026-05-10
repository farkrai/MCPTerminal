"""Git operation tools for the FastMCP server.

Mounted under namespace "git" → tool names become:
  git_status, git_diff, git_log, git_add, git_commit,
  git_branch_list, git_branch_switch, git_push
"""
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant.server.state import policy

git_mcp = FastMCP("GitTools")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _cwd(cwd: str | None) -> Path:
    if cwd:
        p = Path(cwd)
        return p if p.is_absolute() else policy.sandbox_root / p
    return policy.sandbox_root


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise ToolError(result.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    return result.stdout.strip() or "(no output)"


# ── Tools ──────────────────────────────────────────────────────────────────────

@git_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), tags={"git", "read-only"})
async def status(
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    ctx: Context = None,
) -> str:
    """Show the git working tree status."""
    if ctx:
        await ctx.info("Running git status")
    return _run(["git", "status"], _cwd(cwd))


@git_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), tags={"git", "read-only"})
async def diff(
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    staged: Annotated[bool, "Show staged (--cached) diff instead of unstaged"] = False,
    ctx: Context = None,
) -> str:
    """Show unstaged or staged git diff."""
    if ctx:
        await ctx.info(f"Running git diff (staged={staged})")
    cmd = ["git", "diff", "--cached"] if staged else ["git", "diff"]
    out = _run(cmd, _cwd(cwd))
    return out if out != "(no output)" else ("(nothing staged)" if staged else "(no changes)")


@git_mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True), tags={"git", "read-only"})
async def log(
    n: Annotated[int, "Number of commits to show (default: 10)"] = 10,
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    ctx: Context = None,
) -> str:
    """Show the recent git commit log (one-line format)."""
    if ctx:
        await ctx.info(f"Running git log -{n}")
    n = max(1, min(n, 100))
    return _run(["git", "log", "--oneline", f"-{n}"], _cwd(cwd))


@git_mcp.tool(annotations=ToolAnnotations(idempotentHint=False), tags={"git"})
async def add(
    path: Annotated[str, "File path or '.' to stage all changes"] = ".",
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    ctx: Context = None,
) -> str:
    """Stage files for commit (git add)."""
    if ctx:
        await ctx.info(f"Staging: {path}")
    _run(["git", "add", path], _cwd(cwd))
    return f"Staged: {path}"


@git_mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False), tags={"git", "destructive"})
async def commit(
    message: Annotated[str, "Commit message (required)"],
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    dry_run: Annotated[bool, "Preview staged diff without committing"] = False,
    ctx: Context = None,
) -> str:
    """Commit staged changes with a message."""
    work_dir = _cwd(cwd)
    if policy.dry_run_mode or dry_run:
        staged = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            capture_output=True, text=True, cwd=work_dir
        ).stdout.strip()
        return (
            f"[DRY RUN] Would commit: \"{message}\"\n"
            f"Staged changes:\n{staged or '(nothing staged)'}"
        )
    if ctx:
        await ctx.info(f"Committing: {message}")
    return _run(["git", "commit", "-m", message], work_dir)


@git_mcp.tool(
    name="push",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"git", "destructive"},
)
async def push(
    remote: Annotated[str, "Remote name (default: origin)"] = "origin",
    branch: Annotated[str | None, "Branch to push (default: current branch)"] = None,
    dry_run: Annotated[bool, "Preview without pushing"] = False,
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    ctx: Context = None,
) -> str:
    """Push commits to a remote git repository."""
    if policy.dry_run_mode or dry_run:
        target = f"{remote}/{branch}" if branch else remote
        return f"[DRY RUN] Would push to: {target}"
    if ctx:
        await ctx.info(f"Pushing to {remote}" + (f"/{branch}" if branch else ""))
    cmd = ["git", "push", remote] + ([branch] if branch else [])
    return _run(cmd, _cwd(cwd))


@git_mcp.tool(
    name="branch_list",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"git", "read-only"},
)
async def branch_list(
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    ctx: Context = None,
) -> str:
    """List all local and remote git branches."""
    if ctx:
        await ctx.info("Listing branches")
    return _run(["git", "branch", "-a"], _cwd(cwd))


@git_mcp.tool(
    name="branch_switch",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"git", "destructive"},
)
async def branch_switch(
    branch: Annotated[str, "Branch name to switch to"],
    cwd: Annotated[str | None, "Working directory (default: project root)"] = None,
    dry_run: Annotated[bool, "Preview without switching"] = False,
    ctx: Context = None,
) -> str:
    """Switch to another git branch (git checkout)."""
    if policy.dry_run_mode or dry_run:
        return f"[DRY RUN] Would switch to branch: {branch}"
    if ctx:
        await ctx.info(f"Switching to branch: {branch}")
    return _run(["git", "checkout", branch], _cwd(cwd))
