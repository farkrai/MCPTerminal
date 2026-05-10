"""Persistent key-value memory store for the MCP assistant.

Mounted under namespace "memory" → tool names become:
  memory_set, memory_get, memory_list, memory_delete, memory_search

Backed by SQLite in ~/.mcp_assistant/memory.db so memories survive
across sessions. Tags allow grouping (e.g. "project", "fact", "todo").
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant import config

memory_mcp = FastMCP("MemoryTools")

# Path is set once at import time; config.ensure_dirs() creates the directory.
_DB_PATH: Path = config.CONTEXT_PERSIST_DIR / "memory.db"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            tags       TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    con.commit()
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["tags"] = [t for t in d["tags"].split(",") if t] if d["tags"] else []
    return d


# ── Tools ──────────────────────────────────────────────────────────────────────

@memory_mcp.tool(
    name="set",
    annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True),
    tags={"memory"},
)
async def set_memory(
    key: Annotated[str, "Unique key for this memory (e.g. 'project_goal', 'last_error')"],
    value: Annotated[str, "Content to store"],
    tags: Annotated[list[str], "Optional labels for grouping (e.g. ['fact', 'project'])"] = None,
    ctx: Context = None,
) -> dict:
    """Store or update a named memory entry.

    If the key already exists it is overwritten and updated_at is refreshed.
    """
    now = _now()
    tag_str = ",".join(tags or [])
    with _conn() as con:
        con.execute(
            """
            INSERT INTO memories (key, value, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                tags       = excluded.tags,
                updated_at = excluded.updated_at
            """,
            (key, value, tag_str, now, now),
        )
    if ctx:
        await ctx.info(f"Memory stored: {key!r}")
    return {"key": key, "tags": tags or [], "stored_at": now}


@memory_mcp.tool(
    name="get",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"memory", "read-only"},
)
async def get_memory(
    key: Annotated[str, "Key of the memory to retrieve"],
    ctx: Context = None,
) -> dict:
    """Retrieve a single memory entry by key."""
    with _conn() as con:
        row = con.execute("SELECT * FROM memories WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise ToolError(f"Memory not found: {key!r}")
    return _row_to_dict(row)


@memory_mcp.tool(
    name="list",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"memory", "read-only"},
)
async def list_memories(
    tag: Annotated[str | None, "Filter by tag (returns all if omitted)"] = None,
    limit: Annotated[int, "Maximum entries to return"] = 50,
    ctx: Context = None,
) -> dict:
    """List stored memories, optionally filtered by tag."""
    with _conn() as con:
        if tag:
            rows = con.execute(
                "SELECT * FROM memories WHERE (',' || tags || ',') LIKE ? ORDER BY updated_at DESC LIMIT ?",
                (f"%,{tag},%", limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
    entries = [_row_to_dict(r) for r in rows]
    return {"count": len(entries), "tag_filter": tag, "entries": entries}


@memory_mcp.tool(
    name="delete",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True),
    tags={"memory", "destructive"},
)
async def delete_memory(
    key: Annotated[str, "Key of the memory to permanently delete"],
    ctx: Context = None,
) -> dict:
    """Permanently delete a memory entry by key."""
    with _conn() as con:
        cursor = con.execute("DELETE FROM memories WHERE key = ?", (key,))
    if cursor.rowcount == 0:
        raise ToolError(f"Memory not found: {key!r}")
    if ctx:
        await ctx.warning(f"Memory deleted: {key!r}")
    return {"key": key, "deleted": True}


@memory_mcp.tool(
    name="search",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"memory", "read-only"},
)
async def search_memories(
    query: Annotated[str, "Text to search for in keys and values (case-insensitive)"],
    limit: Annotated[int, "Maximum results to return"] = 20,
    ctx: Context = None,
) -> dict:
    """Full-text search across memory keys and values."""
    pattern = f"%{query}%"
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM memories
            WHERE key LIKE ? OR value LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()
    results = [_row_to_dict(r) for r in rows]
    return {"query": query, "count": len(results), "results": results}
