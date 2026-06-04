"""SQLite database inspection and query tools.

Mounted under namespace "db" → tool names become:
  db_tables, db_schema, db_query, db_execute

Safety model
------------
- db_query enforces SELECT-only (read-only by policy).
- db_execute allows DML/DDL but requires dry_run=False and respects policy.dry_run_mode.
- Paths are resolved against PROJECT_ROOT if relative.
- Only .db, .sqlite, .sqlite3 extensions are accepted to prevent misuse.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Annotated, Optional

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from mcp_assistant.server.state import policy

db_mcp = FastMCP("DatabaseTools")

_ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


def _resolve_db(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = policy.sandbox_root / p
    p = p.resolve()
    if p.suffix not in _ALLOWED_EXTENSIONS:
        raise ToolError(
            f"Only SQLite files are supported ({', '.join(_ALLOWED_EXTENSIONS)}). Got: {p.suffix}"
        )
    if not p.exists():
        raise ToolError(f"Database file not found: {p}")
    return p


def _is_select(sql: str) -> bool:
    stripped = sql.strip().lstrip("(").upper()
    return stripped.startswith("SELECT") or stripped.startswith("WITH")


# ── Tools ──────────────────────────────────────────────────────────────────────

@db_mcp.tool(
    name="tables",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"db", "read-only"},
)
async def tables(
    path: Annotated[str, "Path to the SQLite database file"],
    ctx: Context = None,
) -> dict:
    """List all tables (and views) in a SQLite database."""
    if ctx:
        await ctx.info(f"Listing tables in: {path}")
    db_path = _resolve_db(path)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
        ).fetchall()
    return {
        "database": str(db_path),
        "count": len(rows),
        "tables": [{"name": r[0], "type": r[1]} for r in rows],
    }


@db_mcp.tool(
    name="schema",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"db", "read-only"},
)
async def schema(
    path: Annotated[str, "Path to the SQLite database file"],
    table: Annotated[str, "Table or view name"],
    ctx: Context = None,
) -> dict:
    """Return column names, types, and constraints for a table."""
    if ctx:
        await ctx.info(f"Fetching schema for {table} in: {path}")
    db_path = _resolve_db(path)
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
    if not rows:
        raise ToolError(f"Table '{table}' not found in {db_path}")
    columns = [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "not_null": bool(r[3]),
            "default": r[4],
            "primary_key": bool(r[5]),
        }
        for r in rows
    ]
    ddl_row = sqlite3.connect(str(db_path)).execute(
        "SELECT sql FROM sqlite_master WHERE name=?", (table,)
    ).fetchone()
    return {
        "database": str(db_path),
        "table": table,
        "columns": columns,
        "ddl": ddl_row[0] if ddl_row else None,
    }


@db_mcp.tool(
    name="query",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"db", "read-only"},
)
async def query(
    path: Annotated[str, "Path to the SQLite database file"],
    sql: Annotated[str, "SELECT (or WITH) statement only — no INSERT/UPDATE/DELETE"],
    params: Annotated[Optional[list], "Optional list of ? placeholder values. Omit if none."] = None,
    limit: Annotated[int, "Max rows to return (default 100). Only valid on db_query, NOT db_execute."] = 100,
    ctx: Context = None,
) -> dict:
    """Execute a read-only SELECT query and return rows as a list of dicts. Use db_execute for writes."""
    if not _is_select(sql):
        raise ToolError("db_query only allows SELECT statements. Use db_execute for DML.")
    if ctx:
        await ctx.info(f"Querying {path}: {sql[:80]}")
    db_path = _resolve_db(path)
    safe_sql = sql.rstrip(";") + f" LIMIT {limit}"
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(safe_sql, params or [])
        rows = [dict(r) for r in cursor.fetchall()]
        columns = [d[0] for d in cursor.description] if cursor.description else []
    return {"sql": sql, "columns": columns, "count": len(rows), "rows": rows}


@db_mcp.tool(
    name="execute",
    annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False),
    tags={"db", "destructive"},
)
async def execute(
    path: Annotated[str, "Path to the SQLite database file"],
    sql: Annotated[str, "SQL statement to execute (INSERT, UPDATE, DELETE, CREATE, DROP). Do NOT use SELECT — use db_query for reads."],
    params: Annotated[Optional[list], "Optional list of positional ? placeholder values, e.g. ['Alice', 'alice@test.com']. Omit if the SQL has no placeholders."] = None,
    dry_run: Annotated[bool, "If true, preview without committing. No 'limit' parameter exists on this tool."] = False,
    ctx: Context = None,
) -> dict:
    """Execute a write SQL statement (INSERT/UPDATE/DELETE/CREATE/DROP). No limit parameter.

    - sql: full SQL string with literal values or ? placeholders
    - params: list of values for ? placeholders, or omit entirely
    - dry_run: set True to preview without writing
    Changes are rolled back automatically when dry_run=True.
    """
    if _is_select(sql):
        raise ToolError("Use db_query for SELECT statements.")
    if policy.dry_run_mode or dry_run:
        return {"dry_run": True, "sql": sql, "message": "No changes made — dry_run mode"}
    if ctx:
        await ctx.warning(f"Executing DML on {path}: {sql[:80]}")
    db_path = _resolve_db(path)
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute(sql, params or [])
        conn.commit()
    return {
        "sql": sql,
        "rowcount": cursor.rowcount,
        "lastrowid": cursor.lastrowid,
        "message": f"{cursor.rowcount} row(s) affected",
    }
