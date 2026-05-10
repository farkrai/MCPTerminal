"""FastMCP server – main entry point.

Creates and wires together the complete MCP Terminal Assistant server:
  - Five tool namespaces: file, git, system, test, network
  - Policy + audit middleware
  - Config, audit, session resources
  - Prompt templates

Usage
-----
Embedded (in-process):
    from mcp_assistant.server.app import create_server
    mcp = create_server()
    # then: async with Client(mcp) as client: ...

Standalone (stdio for Claude Desktop / any MCP client):
    python -m mcp_assistant.server.app
    # or via pyproject entry-point: mcp-server
"""
from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools

from mcp_assistant.server.middleware import AuditMiddleware, PolicyMiddleware, TimingMiddleware
from mcp_assistant.server.prompts import register_prompts
from mcp_assistant.server.resources import register_resources
from mcp_assistant.server.tools.code import code_mcp
from mcp_assistant.server.tools.database import db_mcp
from mcp_assistant.server.tools.docker import docker_mcp
from mcp_assistant.server.tools.file import file_mcp
from mcp_assistant.server.tools.git import git_mcp
from mcp_assistant.server.tools.memory import memory_mcp
from mcp_assistant.server.tools.meta import meta_mcp
from mcp_assistant.server.tools.network import network_mcp
from mcp_assistant.server.tools.shell import shell_mcp
from mcp_assistant.server.tools.system import system_mcp
from mcp_assistant.server.tools.test import test_mcp


def create_server() -> FastMCP:
    """Build and return a fully-wired FastMCP server instance.

    Tool inventory (54 total after transforms):
    ─────────────────────────────────────────────────────────────────────
    Namespace "file"    → file_read, file_write, file_list,
                          file_search, file_delete                  (5)
    Namespace "git"     → git_status, git_diff, git_log, git_add,
                          git_commit, git_branch_list,
                          git_branch_switch                         (7)
    Namespace "system"  → system_cpu_stats, system_ram_stats,
                          system_disk_stats, system_list_processes,
                          system_kill_process, system_env_info      (6)
    Namespace "test"    → test_detect, test_run, test_run_file,
                          test_explain_failures                     (4)
    Namespace "network" → network_ping, network_dns_lookup,
                          network_http_probe, network_port_check    (4)
    Namespace "shell"   → shell_run, shell_which, shell_env         (3)
    Namespace "docker"  → docker_ps, docker_logs, docker_inspect,
                          docker_images, docker_start, docker_stop  (6)
    Namespace "db"      → db_tables, db_schema, db_query,
                          db_execute                                (4)
    Namespace "code"    → code_symbols, code_lint, code_complexity  (3)
    Namespace "memory"  → memory_set, memory_get, memory_list,
                          memory_delete, memory_search              (5)
    Meta (no namespace) → describe_tools, toolkit_status,
                          toolkit_activate                          (3)
    PromptsAsTools      → prompt_system-instructions,
                          prompt_clarify-intent,
                          prompt_explain-test-failures,
                          prompt_summarize-git-diff                 (4)
    ResourcesAsTools    → resource_config, resource_audit-today,
                          resource_audit-verify, resource_session   (4)
    ─────────────────────────────────────────────────────────────────────
    Total: 58 tools visible to the LLM
    """
    mcp = FastMCP(
        name="MCP Terminal Assistant",
        instructions=(
            "An offline, privacy-preserving AI terminal assistant. "
            "Translate natural language to structured tool calls for file, git, "
            "system, network, and test operations. All execution is local. "
            "Use describe_tools to find the right tool for any task. "
            "Use toolkit_activate to focus on a specific domain."
        ),
        middleware=[
            PolicyMiddleware(),
            TimingMiddleware(),
            AuditMiddleware(),
        ],
        on_duplicate="warn",
    )

    # ── Domain tool sub-servers (namespaced) ───────────────────────────────────
    mcp.mount(file_mcp,    namespace="file")
    mcp.mount(git_mcp,     namespace="git")
    mcp.mount(system_mcp,  namespace="system")
    mcp.mount(test_mcp,    namespace="test")
    mcp.mount(network_mcp, namespace="network")
    mcp.mount(shell_mcp,   namespace="shell")
    mcp.mount(docker_mcp,  namespace="docker")
    mcp.mount(db_mcp,      namespace="db")
    mcp.mount(code_mcp,    namespace="code")
    mcp.mount(memory_mcp,  namespace="memory")

    # ── Meta-tools (no namespace — describe_tools, toolkit_status/activate) ───
    mcp.mount(meta_mcp)

    # ── Resources & prompts ────────────────────────────────────────────────────
    register_resources(mcp)
    register_prompts(mcp)

    # ── FastMCP transforms: expose prompts & resources as callable tools ───────
    # PromptsAsTools: each @mcp.prompt() becomes callable as "prompt_<name>"
    # ResourcesAsTools: each @mcp.resource() becomes callable as "resource_<name>"
    mcp.add_transform(PromptsAsTools(mcp))
    mcp.add_transform(ResourcesAsTools(mcp))

    return mcp


# Singleton used by the CLI/TUI (lazy-initialised once per process)
_server: FastMCP | None = None


def get_server() -> FastMCP:
    """Return the process-level singleton server (creates on first call)."""
    global _server
    if _server is None:
        _server = create_server()
    return _server


# ── Standalone entry points ───────────────────────────────────────────────────

def _standalone() -> None:
    """pyproject.toml entry point: ``mcp-server`` runs in stdio mode."""
    get_server().run()


if __name__ == "__main__":
    _standalone()
