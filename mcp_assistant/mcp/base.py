from __future__ import annotations
from abc import ABC, abstractmethod
from mcp_assistant.mcp.schema import MCPCall, MCPResult


class MCPTool(ABC):
    # Set by each subclass
    TOOL_NAME: str = ""
    TOOL_DESCRIPTION: str = ""
    SUPPORTED_ACTIONS: dict[str, str] = {}
    DESTRUCTIVE_ACTIONS: set[str] = set()
    ALWAYS_CONFIRM_ACTIONS: set[str] = set()

    @abstractmethod
    def execute(self, call: MCPCall) -> MCPResult:
        """Execute the tool call. Must not raise — catch all exceptions internally."""
        ...

    def dry_run(self, call: MCPCall) -> str:
        """Return a human-readable preview of what execute() would do."""
        return f"Would run: {self.TOOL_NAME}.{call.action}  params={call.params}"

    def validate_params(self, call: MCPCall) -> list[str]:
        """Return a list of validation error strings. Empty list means valid."""
        return []

    def get_schema_summary(self) -> str:
        """Text block injected into the LLM system prompt."""
        lines = [
            f"Tool: {self.TOOL_NAME}",
            f"  {self.TOOL_DESCRIPTION}",
            "  Actions:",
        ]
        for action, desc in self.SUPPORTED_ACTIONS.items():
            tag = " [DESTRUCTIVE]" if action in self.DESTRUCTIVE_ACTIONS else ""
            lines.append(f"    - {action}: {desc}{tag}")
        return "\n".join(lines)

    def _ok(self, call: MCPCall, output: str, data=None, duration_ms: float = 0.0) -> MCPResult:
        return MCPResult(call=call, success=True, output=output, data=data, duration_ms=duration_ms)

    def _err(self, call: MCPCall, error: str, duration_ms: float = 0.0) -> MCPResult:
        return MCPResult(call=call, success=False, output=f"Error: {error}", error=error, duration_ms=duration_ms)
