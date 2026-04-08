from __future__ import annotations
import importlib.util
import inspect
from pathlib import Path
from mcp_assistant.mcp.base import MCPTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        self._tools[tool.TOOL_NAME] = tool

    def get(self, tool_name: str) -> MCPTool | None:
        return self._tools.get(tool_name)

    def all_tools(self) -> list[MCPTool]:
        return list(self._tools.values())

    def tool_names(self) -> set[str]:
        return set(self._tools.keys())

    def generate_summary(self) -> str:
        return "\n\n".join(t.get_schema_summary() for t in self._tools.values())

    def discover_plugins(self, plugin_dir: Path) -> list[str]:
        """
        Walk plugin_dir, import any .py file, register non-abstract MCPTool subclasses.
        Returns list of discovered tool names.
        """
        discovered: list[str] = []
        if not plugin_dir.is_dir():
            return discovered

        for py_file in plugin_dir.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
            except Exception:
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, MCPTool)
                    and obj is not MCPTool
                    and not inspect.isabstract(obj)
                    and obj.TOOL_NAME
                    and obj.TOOL_NAME not in self._tools
                ):
                    self.register(obj())
                    discovered.append(obj.TOOL_NAME)

        return discovered
