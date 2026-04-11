from __future__ import annotations

import copy
import hashlib
import json
import time

from mcp_assistant.mcp.schema import MCPCall, MCPResult

TOOL_CACHE_TTL: int = 15

_CACHEABLE: dict[str, set[str]] = {
    "FileHandler": {"list", "search", "read"},
    "GitTool": {"status", "diff", "log", "branch_list"},
    "SystemTool": {"cpu_stats", "ram_stats", "disk_stats", "list_processes", "env_info"},
    "TestRunner": {"detect"},
}

_STORE: dict[str, tuple[MCPResult, float]] = {}


def _key(call: MCPCall) -> str:
    raw = f"{call.tool}:{call.action}:{json.dumps(call.params, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get(call: MCPCall) -> MCPResult | None:
    if call.action not in _CACHEABLE.get(call.tool, set()):
        return None

    key = _key(call)
    entry = _STORE.get(key)
    if entry is None:
        return None

    result, ts = entry
    if time.time() - ts > TOOL_CACHE_TTL:
        _STORE.pop(key, None)
        return None

    return copy.deepcopy(result)


def put(call: MCPCall, result: MCPResult) -> None:
    if result.success and call.action in _CACHEABLE.get(call.tool, set()):
        _STORE[_key(call)] = (copy.deepcopy(result), time.time())


def clear() -> None:
    _STORE.clear()
