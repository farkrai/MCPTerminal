"""Tests for atomic FastMCP tools via the in-process client."""
import json
import pytest
import pytest_asyncio
from fastmcp import Client
from mcp_assistant.server.app import create_server
from mcp_assistant import config


def _text(result) -> str:
    """Extract text from a call_tool result."""
    if hasattr(result, "content"):
        for item in result.content:
            if hasattr(item, "text"):
                return item.text
    return str(result)


# ── file_* tools ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_file_list(mcp_client):
    result = await mcp_client.call_tool("file_list", {"path": "."})
    data = json.loads(_text(result))
    assert "entries" in data
    assert any("mcp_assistant" in e for e in data["entries"])


@pytest.mark.asyncio
async def test_file_read(mcp_client):
    result = await mcp_client.call_tool("file_read", {"path": "pyproject.toml"})
    text = _text(result)
    assert "fastmcp" in text.lower()


@pytest.mark.asyncio
async def test_file_read_missing(mcp_client):
    with pytest.raises(Exception):
        await mcp_client.call_tool("file_read", {"path": "nonexistent_xyz_abc.txt"})


@pytest.mark.asyncio
async def test_file_search(mcp_client):
    result = await mcp_client.call_tool(
        "file_search", {"path": "mcp_assistant", "pattern": "*.py"}
    )
    data = json.loads(_text(result))
    assert data["count"] > 0
    assert all(m.endswith(".py") for m in data["matches"])


@pytest.mark.asyncio
async def test_file_write_and_read(mcp_client, tmp_path, monkeypatch):
    """Write to a temp file then read it back."""
    monkeypatch.setattr("mcp_assistant.server.tools.file.policy.sandbox_root", tmp_path)
    target = str(tmp_path / "test_write.txt")
    await mcp_client.call_tool("file_write", {"path": target, "content": "hello fastmcp"})
    result = await mcp_client.call_tool("file_read", {"path": target})
    assert "hello fastmcp" in _text(result)


@pytest.mark.asyncio
async def test_file_write_dry_run(mcp_client):
    result = await mcp_client.call_tool(
        "file_write", {"path": "test.txt", "content": "data", "dry_run": True}
    )
    assert "DRY RUN" in _text(result)


# ── git_* tools ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_git_status(mcp_client):
    result = await mcp_client.call_tool("git_status", {})
    assert "branch" in _text(result).lower()


@pytest.mark.asyncio
async def test_git_log(mcp_client):
    result = await mcp_client.call_tool("git_log", {"n": 3})
    text = _text(result)
    assert text and text != "(no output)"


@pytest.mark.asyncio
async def test_git_branch_list(mcp_client):
    result = await mcp_client.call_tool("git_branch_list", {})
    assert "main" in _text(result) or "master" in _text(result) or "*" in _text(result)


@pytest.mark.asyncio
async def test_git_diff(mcp_client):
    result = await mcp_client.call_tool("git_diff", {"staged": False})
    assert _text(result) is not None


@pytest.mark.asyncio
async def test_git_commit_dry_run(mcp_client):
    result = await mcp_client.call_tool(
        "git_commit", {"message": "test commit", "dry_run": True}
    )
    assert "DRY RUN" in _text(result)


# ── system_* tools ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_system_cpu_stats(mcp_client):
    result = await mcp_client.call_tool("system_cpu_stats", {})
    data = json.loads(_text(result))
    assert "percent" in data
    assert "logical_cores" in data


@pytest.mark.asyncio
async def test_system_ram_stats(mcp_client):
    result = await mcp_client.call_tool("system_ram_stats", {})
    data = json.loads(_text(result))
    assert "ram_percent" in data
    assert data["ram_total_gb"] > 0


@pytest.mark.asyncio
async def test_system_disk_stats(mcp_client):
    result = await mcp_client.call_tool("system_disk_stats", {})
    partitions = json.loads(_text(result))
    assert isinstance(partitions, list)
    assert len(partitions) > 0


@pytest.mark.asyncio
async def test_system_list_processes(mcp_client):
    result = await mcp_client.call_tool("system_list_processes", {"n": 5})
    procs = json.loads(_text(result))
    assert isinstance(procs, list)
    assert len(procs) <= 5


@pytest.mark.asyncio
async def test_system_env_info(mcp_client):
    result = await mcp_client.call_tool("system_env_info", {})
    data = json.loads(_text(result))
    assert "os" in data
    assert "python" in data
    assert "hostname" in data


@pytest.mark.asyncio
async def test_system_kill_dry_run(mcp_client):
    import os
    result = await mcp_client.call_tool(
        "system_kill_process", {"pid": os.getpid(), "dry_run": True}
    )
    assert "DRY RUN" in _text(result)


# ── test_* tools ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_detect_pytest(mcp_client):
    result = await mcp_client.call_tool("test_detect", {"cwd": "."})
    data = json.loads(_text(result))
    assert "pytest" in data.get("frameworks", [])


@pytest.mark.asyncio
async def test_run_file(mcp_client, tmp_path):
    test_file = tmp_path / "test_simple.py"
    test_file.write_text("def test_ok(): assert True\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    result = await mcp_client.call_tool("test_run_file", {"path": str(test_file)})
    data = json.loads(_text(result))
    assert data["status"] == "passed"


# ── network_* tools ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_network_dns_lookup(mcp_client):
    result = await mcp_client.call_tool("network_dns_lookup", {"host": "localhost"})
    data = json.loads(_text(result))
    assert "addresses" in data
    assert len(data["addresses"]) > 0


@pytest.mark.asyncio
async def test_network_port_check_closed(mcp_client):
    result = await mcp_client.call_tool(
        "network_port_check", {"host": "127.0.0.1", "port": 19999, "timeout": 1}
    )
    data = json.loads(_text(result))
    assert data["status"] in ("closed", "filtered/timeout")
