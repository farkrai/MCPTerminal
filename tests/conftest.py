import pytest
import pytest_asyncio
from fastmcp import Client
from mcp_assistant.server.app import create_server
from mcp_assistant.mcp.policy import PolicyConfig
from mcp_assistant.audit.logger import AuditLogger
from mcp_assistant import config


@pytest.fixture
def mcp_server():
    return create_server()


@pytest_asyncio.fixture
async def mcp_client(mcp_server):
    async with Client(mcp_server) as client:
        yield client


@pytest.fixture
def policy():
    return PolicyConfig.load_or_default(config.MCPRC_FILE)


@pytest.fixture
def audit(tmp_path):
    return AuditLogger(tmp_path)
