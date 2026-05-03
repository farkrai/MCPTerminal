"""
Example FastMCP Plugin — demonstrates adding custom atomic tools.

To create a new tool plugin using FastMCP:
1. Create a FastMCP sub-server in this file
2. Decorate functions with @mcp.tool()
3. Mount it in mcp_assistant/server/app.py via:
       from plugins.example_plugin.tool import plugin_mcp
       mcp.mount(plugin_mcp, namespace="time")
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

plugin_mcp = FastMCP("ExamplePlugin")


@plugin_mcp.tool(
    name="now",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"time", "read-only"},
)
async def time_now() -> dict:
    """Return the current local date and time."""
    now = datetime.now()
    return {"local": now.isoformat(), "formatted": now.strftime("%Y-%m-%d %H:%M:%S")}


@plugin_mcp.tool(
    name="utc",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"time", "read-only"},
)
async def time_utc() -> dict:
    """Return the current UTC date and time."""
    utc = datetime.now(timezone.utc)
    return {"utc": utc.isoformat(), "formatted": utc.strftime("%Y-%m-%d %H:%M:%S UTC")}


@plugin_mcp.tool(
    name="timestamp",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=False),
    tags={"time", "read-only"},
)
async def time_timestamp() -> dict:
    """Return the current Unix timestamp."""
    return {"timestamp": int(time.time())}
