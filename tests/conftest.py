import pytest
from pathlib import Path
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.mcp.registry import ToolRegistry
from mcp_assistant.mcp.dispatcher import MCPDispatcher
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant.tools.file_handler import FileHandler
from mcp_assistant.tools.git_tool import GitTool
from mcp_assistant.tools.system_tool import SystemTool
from mcp_assistant.tools.test_runner import TestRunner
from mcp_assistant import config


@pytest.fixture
def policy():
    return PolicyConfig.load_or_default(config.MCPRC_FILE)


@pytest.fixture
def registry(policy, tmp_path):
    r = ToolRegistry()
    r.register(FileHandler(policy))
    r.register(GitTool())
    r.register(SystemTool())
    r.register(TestRunner())
    return r


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(tmp_path)


@pytest.fixture
def dispatcher(registry, policy, audit):
    return MCPDispatcher(registry, policy, audit, confirm_fn=lambda _: True)
