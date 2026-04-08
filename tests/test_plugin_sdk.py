from pathlib import Path
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.schema import MCPCall
from mcp_assistant import config


def test_plugin_discovery():
    registry = ToolRegistry()
    discovered = registry.discover_plugins(config.PLUGINS_DIR)
    assert "TimeTool" in discovered
    assert registry.get("TimeTool") is not None


def test_plugin_execute():
    registry = ToolRegistry()
    registry.discover_plugins(config.PLUGINS_DIR)
    tool = registry.get("TimeTool")
    assert tool is not None

    call = MCPCall("TimeTool", "now", {})
    result = tool.execute(call)
    assert result.success
    assert "time" in result.output.lower()


def test_plugin_in_summary():
    registry = ToolRegistry()
    registry.discover_plugins(config.PLUGINS_DIR)
    summary = registry.generate_summary()
    assert "TimeTool" in summary


def test_plugin_schema_summary():
    registry = ToolRegistry()
    registry.discover_plugins(config.PLUGINS_DIR)
    tool = registry.get("TimeTool")
    schema = tool.get_schema_summary()
    assert "TimeTool" in schema
    assert "now" in schema
