"""
Example Plugin — demonstrates the MCP Terminal Assistant Plugin SDK.

To create a new tool plugin:
1. Create a directory under plugins/your_plugin_name/
2. Add a tool.py file with a class that extends MCPTool
3. Set TOOL_NAME, TOOL_DESCRIPTION, SUPPORTED_ACTIONS
4. Implement execute()
5. The ToolRegistry auto-discovers and loads it on startup — no core changes needed.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from mcp_assistant.mcp.base import MCPTool
from mcp_assistant.mcp.schema import MCPCall, MCPResult


class TimeTool(MCPTool):
    TOOL_NAME = "TimeTool"
    TOOL_DESCRIPTION = "Date, time, and timezone information."
    SUPPORTED_ACTIONS = {
        "now":      "Show current local date and time. Params: (none)",
        "utc":      "Show current UTC date and time. Params: (none)",
        "timestamp":"Show current Unix timestamp. Params: (none)",
    }

    def execute(self, call: MCPCall) -> MCPResult:
        start = time.perf_counter()
        action = call.action

        if action == "now":
            now = datetime.now()
            out = f"Local time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
            data = {"local": now.isoformat()}
        elif action == "utc":
            utc = datetime.now(timezone.utc)
            out = f"UTC time: {utc.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            data = {"utc": utc.isoformat()}
        elif action == "timestamp":
            ts = int(time.time())
            out = f"Unix timestamp: {ts}"
            data = {"timestamp": ts}
        else:
            return self._err(call, f"Unknown action: {action}")

        return self._ok(call, out, data, round((time.perf_counter() - start) * 1000, 2))
