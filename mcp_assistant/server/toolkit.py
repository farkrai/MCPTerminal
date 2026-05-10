"""ToolKit — context-aware tool routing via FastMCP Visibility transforms.

A ToolKit is a named subset of tools identified by tags.  The ToolRouter
applies the appropriate ToolKit to the FastMCP server to reduce the tool
list exposed to the LLM, preventing confusion in large tool sets.

Usage
-----
    from mcp_assistant.server.toolkit import ToolRouter
    from mcp_assistant.server.app import get_server

    router = ToolRouter(get_server())
    router.activate("git")          # LLM only sees git_* tools
    router.activate("read-only")    # LLM only sees read-only tools
    router.activate_all()           # Reset: all 26 tools visible

Why it matters
--------------
Reducing the tool list in the system prompt directly reduces hallucination rate:
fewer candidates → lower chance of the LLM picking a wrong tool name or
fabricating a parameter it misremembered from a different tool's schema.
"""
from __future__ import annotations
from dataclasses import dataclass

from fastmcp import FastMCP


@dataclass(frozen=True)
class ToolKit:
    """A named group of tools identified by one or more tags."""
    name: str
    tags: set[str]
    description: str

    def activate(self, mcp: FastMCP) -> None:
        """Enable only tools matching this kit's tags (disable all others)."""
        mcp.enable(tags=self.tags, only=True)

    def deactivate(self, mcp: FastMCP) -> None:
        """Disable tools matching this kit (re-enable all others)."""
        mcp.disable(tags=self.tags)


# ── Built-in kits ──────────────────────────────────────────────────────────────

FILE_KIT = ToolKit(
    name="file",
    tags={"file"},
    description="File read/write/list/search/delete operations",
)
GIT_KIT = ToolKit(
    name="git",
    tags={"git"},
    description="Git status, diff, log, commit, branch operations",
)
SYSTEM_KIT = ToolKit(
    name="system",
    tags={"system"},
    description="CPU/RAM/disk monitoring and process management",
)
TEST_KIT = ToolKit(
    name="test",
    tags={"test"},
    description="Test framework detection, execution, and failure explanation",
)
NETWORK_KIT = ToolKit(
    name="network",
    tags={"network"},
    description="Network diagnostics: ping, DNS, HTTP, port check",
)
READ_ONLY_KIT = ToolKit(
    name="read-only",
    tags={"read-only"},
    description="All non-destructive, read-only tools across all namespaces",
)
MONITORING_KIT = ToolKit(
    name="monitoring",
    tags={"monitoring"},
    description="System monitoring tools (CPU, RAM, disk, processes, env)",
)
DIAGNOSTIC_KIT = ToolKit(
    name="diagnostic",
    tags={"diagnostic"},
    description="Network diagnostic tools",
)

SHELL_KIT = ToolKit(
    name="shell",
    tags={"shell"},
    description="Safe sandboxed shell command execution",
)
DOCKER_KIT = ToolKit(
    name="docker",
    tags={"docker"},
    description="Docker container and image management",
)
DATABASE_KIT = ToolKit(
    name="database",
    tags={"db"},
    description="SQLite database inspection and querying",
)
CODE_KIT = ToolKit(
    name="code",
    tags={"code"},
    description="Python code quality: symbols, lint, complexity",
)
MEMORY_KIT = ToolKit(
    name="memory",
    tags={"memory"},
    description="Persistent key-value memory store across sessions",
)

ALL_KITS: dict[str, ToolKit] = {
    k.name: k for k in [
        FILE_KIT, GIT_KIT, SYSTEM_KIT, TEST_KIT, NETWORK_KIT,
        SHELL_KIT, DOCKER_KIT, DATABASE_KIT, CODE_KIT, MEMORY_KIT,
        READ_ONLY_KIT, MONITORING_KIT, DIAGNOSTIC_KIT,
    ]
}


class ToolRouter:
    """Manage context-aware tool visibility on a FastMCP server.

    Calling ``activate(kit_name)`` narrows the LLM's tool view to only the
    relevant subset, reducing hallucination.  Call ``activate_all()`` to
    restore full visibility.
    """

    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp
        self._active: str | None = None

    def activate(self, kit_name: str) -> bool:
        """Activate a named ToolKit.  Returns False if kit not found."""
        kit = ALL_KITS.get(kit_name)
        if kit is None:
            return False
        kit.activate(self._mcp)
        self._active = kit_name
        return True

    def activate_all(self) -> None:
        """Reset visibility: all tools enabled."""
        self._mcp.enable(components={"tool"})
        self._active = None

    @property
    def active(self) -> str | None:
        return self._active

    def available_kits(self) -> list[dict]:
        return [
            {"name": k.name, "tags": sorted(k.tags), "description": k.description}
            for k in ALL_KITS.values()
        ]

    def __repr__(self) -> str:
        return f"ToolRouter(active={self._active!r}, kits={list(ALL_KITS.keys())})"
