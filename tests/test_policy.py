import pytest
from pathlib import Path
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant import config


def test_default_policy_loads():
    p = PolicyConfig.default()
    assert p.sandbox_root == config.PROJECT_ROOT
    assert p.max_file_size_mb == 10
    assert "FileHandler.write" in p.confirm_required


def test_mcprc_loads(policy):
    assert policy.sandbox_root is not None
    assert isinstance(policy.allowed_tools, list)
    assert isinstance(policy.confirm_required, set)


def test_path_inside_sandbox_allowed(policy):
    safe = config.PROJECT_ROOT / "mcp_assistant" / "config.py"
    assert policy.is_path_allowed(safe)


def test_path_outside_sandbox_blocked(policy):
    assert not policy.is_path_allowed("/etc/passwd")
    assert not policy.is_path_allowed("/home/krshrivathsan/.ssh/id_rsa")


def test_env_file_blocked(policy):
    env = config.PROJECT_ROOT / ".env"
    assert not policy.is_path_allowed(env)


def test_tool_allowed(policy):
    assert policy.is_tool_allowed("FileHandler")
    assert policy.is_tool_allowed("GitTool")


def test_disabled_tool_blocked():
    p = PolicyConfig.default()
    p.disabled_tools = ["SystemTool"]
    assert not p.is_tool_allowed("SystemTool")
    assert p.is_tool_allowed("GitTool")


def test_confirmation_required(policy):
    assert policy.requires_confirmation("FileHandler", "write")
    assert policy.requires_confirmation("GitTool", "commit")
    assert not policy.requires_confirmation("GitTool", "status")


def test_audit_retention_days(policy):
    assert isinstance(policy.audit_retention_days, int)
    assert policy.audit_retention_days >= 0
