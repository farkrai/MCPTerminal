import pytest
from mcp_assistant.mcp.schema import MCPCall
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner
from mcp_assistant import config


# ── FileHandler ───────────────────────────────────────────────────────────────

def test_file_list(policy):
    tool = FileHandler(policy)
    call = MCPCall(tool="FileHandler", action="list", params={"path": "."})
    result = tool.execute(call)
    assert result.success
    assert "mcp_assistant" in result.output


def test_file_read_existing(policy):
    tool = FileHandler(policy)
    call = MCPCall(tool="FileHandler", action="read", params={"path": "requirements.txt"})
    result = tool.execute(call)
    assert result.success
    assert result.data is not None


def test_file_read_outside_sandbox(policy):
    tool = FileHandler(policy)
    call = MCPCall(tool="FileHandler", action="read", params={"path": "/etc/passwd"})
    result = tool.execute(call)
    assert not result.success
    assert "not allowed" in result.error.lower() or "permission" in result.error.lower()


def test_file_read_missing(policy):
    tool = FileHandler(policy)
    call = MCPCall(tool="FileHandler", action="read", params={"path": "nonexistent_file_xyz.txt"})
    result = tool.execute(call)
    assert not result.success


def test_file_write_and_read(policy, tmp_path, monkeypatch):
    # Patch sandbox to tmp_path so we can write safely in tests
    p = PolicyConfig.default()
    p.sandbox_root = tmp_path
    tool = FileHandler(p)
    target = tmp_path / "test_write.txt"

    write_call = MCPCall("FileHandler", "write", {"path": str(target), "content": "hello world"})
    write_result = tool.execute(write_call)
    assert write_result.success

    read_call = MCPCall("FileHandler", "read", {"path": str(target)})
    read_result = tool.execute(read_call)
    assert read_result.success
    assert read_result.data == "hello world"


def test_file_dry_run_write(policy):
    tool = FileHandler(policy)
    call = MCPCall("FileHandler", "write", {"path": "test.txt", "content": "data"})
    preview = tool.dry_run(call)
    assert "DRY RUN" in preview
    assert "test.txt" in preview


def test_file_unknown_action(policy):
    tool = FileHandler(policy)
    call = MCPCall("FileHandler", "fly", {"path": "."})
    result = tool.execute(call)
    assert not result.success


# ── GitTool ───────────────────────────────────────────────────────────────────

def test_git_status():
    tool = GitTool()
    call = MCPCall("GitTool", "status", {})
    result = tool.execute(call)
    assert result.success
    assert "branch" in result.output.lower()


def test_git_log():
    tool = GitTool()
    call = MCPCall("GitTool", "log", {"n": 5})
    result = tool.execute(call)
    assert result.success


def test_git_branch_list():
    tool = GitTool()
    call = MCPCall("GitTool", "branch_list", {})
    result = tool.execute(call)
    assert result.success


def test_git_commit_no_message():
    tool = GitTool()
    call = MCPCall("GitTool", "commit", {})
    result = tool.execute(call)
    assert not result.success
    assert "message" in result.error.lower()


# ── SystemTool ────────────────────────────────────────────────────────────────

def test_system_ram_stats():
    tool = SystemTool()
    call = MCPCall("SystemTool", "ram_stats", {})
    result = tool.execute(call)
    assert result.success
    assert "RAM" in result.output
    assert isinstance(result.data, dict)
    assert "percent" in result.data


def test_system_cpu_stats():
    tool = SystemTool()
    call = MCPCall("SystemTool", "cpu_stats", {})
    result = tool.execute(call)
    assert result.success
    assert "CPU" in result.output


def test_system_disk_stats():
    tool = SystemTool()
    call = MCPCall("SystemTool", "disk_stats", {})
    result = tool.execute(call)
    assert result.success


def test_system_list_processes():
    tool = SystemTool()
    call = MCPCall("SystemTool", "list_processes", {"n": 5})
    result = tool.execute(call)
    assert result.success
    assert isinstance(result.data, list)


def test_system_env_info():
    tool = SystemTool()
    call = MCPCall("SystemTool", "env_info", {})
    result = tool.execute(call)
    assert result.success
    assert "Python" in result.output


# ── TestRunner ────────────────────────────────────────────────────────────────

def test_runner_detect():
    tool = TestRunner()
    call = MCPCall("TestRunner", "detect", {"cwd": "."})
    result = tool.execute(call)
    assert result.success
    assert "pytest" in result.output.lower()


def test_runner_run(tmp_path):
    # Create a minimal isolated test file so we don't trigger recursion
    (tmp_path / "test_simple.py").write_text("def test_ok(): assert True\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    tool = TestRunner()
    call = MCPCall("TestRunner", "run_file", {"path": str(tmp_path / "test_simple.py")})
    result = tool.execute(call)
    assert result.success
    assert "passed" in result.output.lower()
