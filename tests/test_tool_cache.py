from mcp_assistant.mcp import tool_cache
from mcp_assistant.mcp.schema import MCPCall, MCPResult


def test_tool_cache_put_and_get():
    tool_cache.clear()
    call = MCPCall("GitTool", "status", {})
    result = MCPResult(call=call, success=True, output="ok")
    tool_cache.put(call, result)
    cached = tool_cache.get(call)
    assert cached is not None
    assert cached.output == "ok"


def test_tool_cache_skips_destructive_actions():
    tool_cache.clear()
    call = MCPCall("GitTool", "commit", {"message": "x"})
    result = MCPResult(call=call, success=True, output="done")
    tool_cache.put(call, result)
    assert tool_cache.get(call) is None
