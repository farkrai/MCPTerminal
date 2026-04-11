from __future__ import annotations

from mcp_assistant import config
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.schema import MCPCall
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner

try:
    from fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - optional dependency
    raise ImportError("Install the server extra to use FastMCP: pip install 'mcp-assistant[server]'") from exc


config.ensure_dirs()
policy = PolicyConfig.load_or_default(config.MCPRC_FILE)
registry = ToolRegistry()
registry.register(FileHandler(policy))
registry.register(GitTool())
registry.register(SystemTool())
registry.register(TestRunner())
audit = AuditLogger(config.AUDIT_LOG_DIR)
dispatcher = MCPDispatcher(registry, policy, audit, confirm_fn=lambda _: True)

mcp = FastMCP(
    name="MCP Terminal Assistant",
    instructions="Executes file, git, system, and test operations safely via MCP.",
)


def _dispatch(tool: str, action: str, params: dict) -> str:
    call = MCPCall(tool=tool, action=action, params=params, confidence=1.0)
    result = dispatcher.dispatch(call)
    if not result.success:
        raise ValueError(result.error or result.output)
    return result.output


@mcp.tool()
def git_status(cwd: str = ".") -> str:
    """Show git status for the current repository."""
    return _dispatch("GitTool", "status", {"cwd": cwd})


@mcp.tool()
def git_diff(staged: bool = False, cwd: str = ".") -> str:
    """Show git diff. Set staged=True to see staged changes."""
    return _dispatch("GitTool", "diff", {"staged": staged, "cwd": cwd})


@mcp.tool()
def git_log(n: int = 10, cwd: str = ".") -> str:
    """Show recent git commit history."""
    return _dispatch("GitTool", "log", {"n": n, "cwd": cwd})


@mcp.tool()
def file_read(path: str) -> str:
    """Read and return the contents of a file."""
    return _dispatch("FileHandler", "read", {"path": path})


@mcp.tool()
def file_list(path: str = ".") -> str:
    """List files and directories in a folder."""
    return _dispatch("FileHandler", "list", {"path": path})


@mcp.tool()
def file_search(pattern: str, path: str = ".") -> str:
    """Find files recursively matching a glob pattern."""
    return _dispatch("FileHandler", "search", {"pattern": pattern, "path": path})


@mcp.tool()
def system_cpu() -> str:
    """Show CPU usage statistics."""
    return _dispatch("SystemTool", "cpu_stats", {})


@mcp.tool()
def system_ram() -> str:
    """Show RAM/memory usage statistics."""
    return _dispatch("SystemTool", "ram_stats", {})


@mcp.tool()
def system_disk() -> str:
    """Show disk usage per partition."""
    return _dispatch("SystemTool", "disk_stats", {})


@mcp.tool()
def system_processes(n: int = 15) -> str:
    """List top N running processes by CPU usage."""
    return _dispatch("SystemTool", "list_processes", {"n": n})


@mcp.tool()
def test_detect(cwd: str = ".") -> str:
    """Detect the test framework in the project."""
    return _dispatch("TestRunner", "detect", {"cwd": cwd})


@mcp.tool()
def test_run(cwd: str = ".") -> str:
    """Run the full test suite."""
    return _dispatch("TestRunner", "run", {"cwd": cwd})


def main() -> None:
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="sse", host="0.0.0.0", port=8765)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
