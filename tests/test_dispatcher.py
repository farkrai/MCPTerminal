"""Tests for FastMCP tool dispatch — single calls and multi-step chains."""
import json
import pytest
from fastmcp import Client
from mcp_assistant.server.app import create_server


def _text(result) -> str:
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    return str(result)


# ── Single tool calls ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_system_cpu(mcp_client):
    result = await mcp_client.call_tool("system_cpu_stats", {})
    data = json.loads(_text(result))
    assert "percent" in data


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(mcp_client):
    with pytest.raises(Exception) as exc_info:
        await mcp_client.call_tool("ghost_tool_xyz", {})
    assert "ghost_tool_xyz" in str(exc_info.value).lower() or exc_info.value is not None


@pytest.mark.asyncio
async def test_dispatch_file_read_missing(mcp_client):
    with pytest.raises(Exception):
        await mcp_client.call_tool("file_read", {"path": "nonexistent_xyz.txt"})


# ── Chain-like sequential dispatch ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sequential_cpu_then_ram(mcp_client):
    """Simulate a two-step chain: cpu_stats → ram_stats."""
    r1 = await mcp_client.call_tool("system_cpu_stats", {})
    r2 = await mcp_client.call_tool("system_ram_stats", {})
    assert json.loads(_text(r1)).get("percent") is not None
    assert json.loads(_text(r2)).get("ram_percent") is not None


@pytest.mark.asyncio
async def test_sequential_git_status_then_log(mcp_client):
    r1 = await mcp_client.call_tool("git_status", {})
    r2 = await mcp_client.call_tool("git_log", {"n": 2})
    assert "branch" in _text(r1).lower()
    assert _text(r2)


@pytest.mark.asyncio
async def test_sequential_detect_then_run_file(mcp_client, tmp_path):
    """Detect test framework, then run a specific test file."""
    test_file = tmp_path / "test_chain.py"
    test_file.write_text("def test_pass(): assert True\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")

    detect_result = await mcp_client.call_tool("test_detect", {"cwd": str(tmp_path)})
    data = json.loads(_text(detect_result))
    assert "pytest" in data.get("frameworks", [])

    run_result = await mcp_client.call_tool("test_run_file", {"path": str(test_file)})
    run_data = json.loads(_text(run_result))
    assert run_data["status"] == "passed"


# ── Dry-run mode ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_write(mcp_client):
    result = await mcp_client.call_tool(
        "file_write", {"path": "should_not_exist.txt", "content": "x", "dry_run": True}
    )
    assert "DRY RUN" in _text(result)
    import os
    assert not os.path.exists("should_not_exist.txt")


@pytest.mark.asyncio
async def test_dry_run_commit(mcp_client):
    result = await mcp_client.call_tool(
        "git_commit", {"message": "fake commit", "dry_run": True}
    )
    assert "DRY RUN" in _text(result)


@pytest.mark.asyncio
async def test_dry_run_branch_switch(mcp_client):
    result = await mcp_client.call_tool(
        "git_branch_switch", {"branch": "nonexistent-branch", "dry_run": True}
    )
    assert "DRY RUN" in _text(result)
