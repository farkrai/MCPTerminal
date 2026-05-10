"""File operation tools for the FastMCP server.

Mounted under namespace "file" → tool names become:
  file_read, file_write, file_list, file_search, file_delete
"""
from __future__ import annotations
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant import config
from mcp_assistant.server.state import policy

file_mcp = FastMCP("FileTools")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_sandboxed(raw_path: str) -> Path:
    """Resolve *raw_path* against project root and enforce sandbox policy."""
    path = Path(raw_path.strip())
    if not path.is_absolute():
        path = config.PROJECT_ROOT / path
    path = path.resolve()
    if not policy.is_path_allowed(path):
        raise ToolError(f"Path not allowed by policy: {path}")
    return path


# ── Tools ──────────────────────────────────────────────────────────────────────

@file_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"file", "read-only"},
)
async def read(
    path: Annotated[str, "File path (absolute or relative to project root)"],
    ctx: Context,
) -> str:
    """Read and return the full text content of a file."""
    await ctx.info(f"Reading file: {path}")
    file_path = _resolve_sandboxed(path)
    if not file_path.exists():
        raise ToolError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise ToolError(f"Not a file: {file_path}")
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > policy.max_file_size_mb:
        raise ToolError(
            f"File too large ({size_mb:.1f} MB > {policy.max_file_size_mb} MB limit)"
        )
    return file_path.read_text(encoding="utf-8", errors="replace")


@file_mcp.tool(
    name="write",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"file", "destructive"},
)
async def write_file(
    path: Annotated[str, "Destination path (absolute or relative to project root)"],
    content: Annotated[str, "Text content to write"],
    dry_run: Annotated[bool, "Preview write without executing (default: use policy setting)"] = False,
    ctx: Context = None,
) -> str:
    """Write text content to a file. Creates parent directories as needed."""
    if policy.dry_run_mode or dry_run:
        preview = content[:300] + ("…" if len(content) > 300 else "")
        return f"[DRY RUN] Would write {len(content)} chars to: {path}\nPreview:\n{preview}"
    if ctx:
        await ctx.info(f"Writing {len(content)} chars to: {path}")
    file_path = _resolve_sandboxed(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {file_path}"


@file_mcp.tool(
    name="list",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"file", "read-only"},
)
async def list_directory(
    path: Annotated[str, "Directory path to list (default: project root)"] = ".",
    pattern: Annotated[str, "Glob pattern to filter entries (default: all)"] = "*",
    ctx: Context = None,
) -> dict:
    """List files and directories inside a directory."""
    if ctx:
        await ctx.info(f"Listing directory: {path} (pattern={pattern})")
    dir_path = _resolve_sandboxed(path)
    if not dir_path.is_dir():
        raise ToolError(f"Not a directory: {dir_path}")
    entries = sorted(dir_path.glob(pattern))
    names = [str(e.relative_to(dir_path)) for e in entries]
    return {"path": str(dir_path), "count": len(names), "entries": names[:100]}


@file_mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"file", "read-only"},
)
async def search(
    path: Annotated[str, "Root directory to search in"],
    pattern: Annotated[str, "Glob pattern (e.g. '*.py', 'test_*.py', '**/*.json')"],
    ctx: Context = None,
) -> dict:
    """Recursively search for files matching a glob pattern."""
    if ctx:
        await ctx.info(f"Searching {path} for pattern '{pattern}'")
    root = _resolve_sandboxed(path)
    if not root.is_dir():
        raise ToolError(f"Not a directory: {root}")
    matches = sorted(root.rglob(pattern))
    paths = [str(m) for m in matches if m.is_file()]
    return {"root": str(root), "pattern": pattern, "count": len(paths), "matches": paths[:100]}


@file_mcp.tool(
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"file", "destructive"},
)
async def delete(
    path: Annotated[str, "Path to the file to delete (directories are NOT supported)"],
    dry_run: Annotated[bool, "Preview deletion without executing"] = False,
    ctx: Context = None,
) -> str:
    """Permanently delete a single file (not a directory)."""
    if policy.dry_run_mode or dry_run:
        return f"[DRY RUN] Would permanently delete: {path}"
    if ctx:
        await ctx.warning(f"Deleting file: {path}")
    file_path = _resolve_sandboxed(path)
    if not file_path.exists():
        raise ToolError(f"File not found: {file_path}")
    if file_path.is_dir():
        raise ToolError(f"Cannot delete a directory: {file_path}")
    file_path.unlink()
    return f"Deleted: {file_path}"
