"""Meta-tools for efficient tool lookup and discovery.

These tools help the LLM (and users) find the right tool for a given task
without having to scan all 26 tools in the system prompt.

Mounted on the main server directly (no sub-namespace), producing:
  describe_tools  — returns filtered tool schemas matching a query
  toolkit_status  — shows active ToolKit and available kits
"""
from __future__ import annotations
import json
from typing import Annotated

from fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations

meta_mcp = FastMCP("MetaTools")


@meta_mcp.tool(
    name="describe_tools",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"meta", "read-only"},
)
async def describe_tools(
    query: Annotated[str, "What you're trying to do, e.g. 'read a file', 'check git status'"],
    ctx: Context = None,
) -> str:
    """Find tools relevant to a task description.

    Use this when you are unsure which tool to call.
    Returns matching tool names, descriptions, and parameter signatures.

    Examples
    --------
    query="read a file"           → file_read
    query="show git changes"      → git_diff, git_status
    query="check cpu usage"       → system_cpu_stats
    query="run tests"             → test_run, test_detect
    query="check if port is open" → network_port_check
    """
    from fastmcp.server.dependencies import get_context as _get_ctx
    from mcp_assistant.server.app import get_server

    query_lower = query.lower()
    mcp = get_server()
    tools = await mcp.list_tools()

    # Keyword → tag mapping for fast routing
    KEYWORD_TAGS: list[tuple[list[str], str]] = [
        (["file", "read", "write", "list", "search", "delete", "directory", "folder", "path"], "file"),
        (["git", "commit", "diff", "status", "branch", "log", "stage", "repo"], "git"),
        (["cpu", "ram", "memory", "disk", "process", "kill", "uptime", "system", "os", "env"], "system"),
        (["test", "pytest", "jest", "fail", "failure", "spec", "suite"], "test"),
        (["ping", "dns", "http", "port", "network", "connect", "latency", "probe"], "network"),
    ]

    # Find matching tag from query keywords
    matched_tags: set[str] = set()
    for keywords, tag in KEYWORD_TAGS:
        if any(kw in query_lower for kw in keywords):
            matched_tags.add(tag)

    def score(tool) -> int:
        t_tags = tool.tags or set()
        # Direct tag match
        if matched_tags & t_tags:
            return 2
        # Description keyword match
        desc = (tool.description or "").lower()
        if any(kw in desc for kw in query_lower.split()):
            return 1
        return 0

    scored = [(score(t), t) for t in tools]
    relevant = [t for s, t in sorted(scored, key=lambda x: -x[0]) if s > 0]

    if not relevant:
        relevant = tools[:5]  # fallback: first 5

    lines = [f"Tools matching '{query}':\n"]
    for t in relevant[:8]:
        schema = t.inputSchema or {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        params = []
        for pname, pdef in props.items():
            if pname in {"ctx", "context"}:
                continue
            ptype = pdef.get("type", "any")
            pdesc = pdef.get("description", "")
            req = "required" if pname in required else "optional"
            params.append(f"    {pname} ({ptype}, {req}): {pdesc}")
        desc = (t.description or "").splitlines()[0]
        lines.append(f"  {t.name}")
        lines.append(f"    {desc}")
        if params:
            lines.append("    Parameters:")
            lines.extend(params)
        lines.append("")

    return "\n".join(lines)


@meta_mcp.tool(
    name="toolkit_status",
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    tags={"meta", "read-only"},
)
async def toolkit_status(ctx: Context = None) -> dict:
    """Show the currently active ToolKit and all available kits.

    Use this to understand what tools are currently visible to the LLM
    and which kits can be activated to narrow the tool set.
    """
    from mcp_assistant.server.toolkit import ALL_KITS
    return {
        "available_kits": [
            {
                "name": k.name,
                "tags": sorted(k.tags),
                "description": k.description,
            }
            for k in ALL_KITS.values()
        ],
        "usage": "Call toolkit_activate with a kit name to focus on a specific domain",
    }


@meta_mcp.tool(
    name="toolkit_activate",
    annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True),
    tags={"meta"},
)
async def toolkit_activate(
    kit: Annotated[str, "Kit name: 'file', 'git', 'system', 'test', 'network', 'read-only', 'all'"],
    ctx: Context = None,
) -> str:
    """Activate a ToolKit to focus on a specific domain.

    Narrows the visible tool set to prevent confusion when working in one area.
    Pass 'all' to restore full visibility (all 26 tools).

    Examples
    --------
    kit='git'       → only git_* tools visible
    kit='read-only' → only non-destructive tools visible
    kit='all'       → reset, all tools visible
    """
    from mcp_assistant.server.app import get_server
    from mcp_assistant.server.toolkit import ToolRouter

    mcp = get_server()
    router = ToolRouter(mcp)

    if kit.lower() == "all":
        router.activate_all()
        return "All tools are now visible."

    if router.activate(kit.lower()):
        return f"ToolKit '{kit}' activated. Only {kit}-tagged tools are now visible."
    return f"Unknown kit '{kit}'. Available: {', '.join(['all', 'file', 'git', 'system', 'test', 'network', 'read-only', 'monitoring', 'diagnostic'])}"
