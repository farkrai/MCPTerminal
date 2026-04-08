from __future__ import annotations
from mcp_assistant.mcp.schema import MCPCall, MCPChain
from mcp_assistant import config

# Known registered tool names — updated at runtime by ToolRegistry
_KNOWN_TOOLS: set[str] = {
    "FileHandler", "GitTool", "SystemTool", "TestRunner", "unknown"
}


def register_known_tools(tool_names: set[str]) -> None:
    global _KNOWN_TOOLS
    _KNOWN_TOOLS = tool_names | {"unknown"}


def should_clarify(call: MCPCall, threshold: float = config.CONFIDENCE_THRESHOLD) -> bool:
    if call.confidence < threshold:
        return True
    if call.tool not in _KNOWN_TOOLS:
        return True
    return False


def is_hallucinated_tool(call: MCPCall) -> bool:
    return call.tool not in _KNOWN_TOOLS and call.tool != "unknown"


def chain_min_confidence(chain: MCPChain) -> float:
    if not chain.steps:
        return 0.0
    return min(s.confidence for s in chain.steps)


def should_clarify_chain(
    chain: MCPChain, threshold: float = config.CONFIDENCE_THRESHOLD
) -> bool:
    return chain_min_confidence(chain) < threshold
