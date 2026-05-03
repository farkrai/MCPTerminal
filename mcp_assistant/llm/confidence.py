"""Confidence gating for ToolCall / ToolChain objects.

Compares predicted tool names against the live FastMCP tool registry to detect
hallucinated tool names, and surfaces low-confidence calls for user clarification.
"""
from __future__ import annotations

from mcp_assistant import config
from mcp_assistant.server.schema import ToolCall, ToolChain

# All known FastMCP tool names — populated at startup via register_known_tools()
_KNOWN_TOOLS: set[str] = {
    "file_read", "file_write", "file_list", "file_search", "file_delete",
    "git_status", "git_diff", "git_log", "git_add", "git_commit",
    "git_branch_list", "git_branch_switch",
    "system_cpu_stats", "system_ram_stats", "system_disk_stats",
    "system_list_processes", "system_kill_process", "system_env_info",
    "test_detect", "test_run", "test_run_file", "test_explain_failures",
    "network_ping", "network_dns_lookup", "network_http_probe", "network_port_check",
    "unknown",
}


def register_known_tools(tool_names: set[str]) -> None:
    """Refresh the known-tools registry from the live FastMCP server."""
    global _KNOWN_TOOLS
    _KNOWN_TOOLS = tool_names | {"unknown"}


def is_hallucinated(call: ToolCall) -> bool:
    """Return True if the tool name is not in the registered tool list."""
    return call.tool not in _KNOWN_TOOLS


def should_clarify(call: ToolCall, threshold: float = config.CONFIDENCE_THRESHOLD) -> bool:
    """Return True if confidence is below *threshold* or the tool is hallucinated."""
    return call.confidence < threshold or is_hallucinated(call)


def should_clarify_chain(
    chain: ToolChain, threshold: float = config.CONFIDENCE_THRESHOLD
) -> bool:
    """Return True if any chain step falls below *threshold*."""
    return chain.min_confidence() < threshold
